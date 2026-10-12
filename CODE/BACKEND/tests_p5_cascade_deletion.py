"""P5 cascade-deletion test suite (AURA Phase 4.12).

Run:  python tests_p5_cascade_deletion.py

Uses **temporary databases and synthetic fixtures only**.  It never opens,
writes to, or otherwise touches the production ``aura.db``, the frozen Urdu
splits, or any protected artifact — ``p5_deletion`` additionally refuses the
production path unless ``allow_production=True`` (asserted below).

Covers: successful deletion, rollback after failure, retries/idempotency,
authorisation failures, orphan detection, storage/database consistency,
audit preservation, cross-subject isolation, P5a retention ambiguity.
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import p5_deletion as p5  # noqa: E402

SCHEMA = """
CREATE TABLE users(id INTEGER PRIMARY KEY AUTOINCREMENT,username TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,salt TEXT NOT NULL,role TEXT NOT NULL DEFAULT 'user',blocked INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL);
CREATE TABLE moderation_results(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id TEXT NOT NULL,conversation_id TEXT NOT NULL,message TEXT NOT NULL,result_json TEXT NOT NULL,created_at TEXT NOT NULL,source TEXT,overall_label TEXT,confidence REAL,categories_json TEXT,verified INTEGER,language TEXT,language_name TEXT,processing_mode TEXT);
CREATE TABLE audit_logs(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id TEXT,action TEXT NOT NULL,details TEXT,created_at TEXT NOT NULL);
CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE feedback(id INTEGER PRIMARY KEY AUTOINCREMENT,prediction_id INTEGER,username TEXT NOT NULL,input_text TEXT,predicted_label TEXT,confidence REAL,categories_json TEXT,correct INTEGER NOT NULL DEFAULT 0,corrected_label TEXT,note TEXT,created_at TEXT NOT NULL);
CREATE TABLE live_sessions(session_id TEXT PRIMARY KEY,username TEXT NOT NULL,started_at TEXT NOT NULL,ended_at TEXT,status TEXT NOT NULL DEFAULT 'active');
CREATE TABLE live_events(id INTEGER PRIMARY KEY AUTOINCREMENT,session_id TEXT NOT NULL,transcript TEXT NOT NULL,label TEXT,confidence REAL,categories_json TEXT,elapsed_s REAL,created_at TEXT NOT NULL);
CREATE TABLE training_runs(job_id TEXT PRIMARY KEY,status TEXT NOT NULL,config_json TEXT,started_at TEXT,finished_at TEXT,metrics_json TEXT,error TEXT);
CREATE TABLE dataset_samples(id INTEGER PRIMARY KEY AUTOINCREMENT,comment TEXT,toxic INTEGER,severe_toxic INTEGER,obscene INTEGER,threat INTEGER,insult INTEGER,identity_hate INTEGER,source TEXT,created_at TEXT,updated_at TEXT,language TEXT,language_name TEXT,script TEXT,split TEXT,external_id TEXT);
CREATE TABLE model_versions(id INTEGER PRIMARY KEY AUTOINCREMENT,model_name TEXT,model_version TEXT,dataset_version TEXT,training_date TEXT,metrics_json TEXT,status TEXT,path TEXT,created_at TEXT);
"""

ADMIN = {"username": "auditor", "role": "admin"}
PLAIN = {"username": "someone", "role": "user"}
ALPHA = "alice_subject"
BETA = "bob_other_subject"


def _seed(conn: sqlite3.Connection) -> None:
    """Synthetic fixture: two subjects so cross-subject isolation is testable."""
    for name in (ALPHA, BETA):
        conn.execute(
            "INSERT INTO users(username,password_hash,salt,role,created_at) "
            "VALUES(?,?,?,?,?)",
            (name, "h", "s", "user", "2026-01-01T00:00:00Z"),
        )
    for name in (ALPHA, ALPHA, ALPHA, BETA):
        conn.execute(
            "INSERT INTO moderation_results(user_id,conversation_id,message,"
            "result_json,created_at) VALUES(?,?,?,?,?)",
            (name, "c1", f"synthetic message for {name}", "{}", "2026-01-01T00:00:00Z"),
        )
    conn.execute(
        "INSERT INTO feedback(prediction_id,username,input_text,predicted_label,"
        "created_at) VALUES(?,?,?,?,?)",
        (1, ALPHA, "synthetic feedback text", "toxic", "2026-01-01T00:00:00Z"),
    )
    for sid, name in (("sess-1", ALPHA), ("sess-2", BETA)):
        conn.execute(
            "INSERT INTO live_sessions(session_id,username,started_at,status) "
            "VALUES(?,?,?,?)",
            (sid, name, "2026-01-01T00:00:00Z", "active"),
        )
    conn.execute(
        "INSERT INTO live_events(session_id,transcript,created_at) VALUES(?,?,?)",
        ("sess-1", "synthetic transcript", "2026-01-01T00:00:00Z"),
    )
    conn.execute(
        "INSERT INTO audit_logs(user_id,action,details,created_at) VALUES(?,?,?,?)",
        (ALPHA, "MODERATION_DECISION", '{"moderation_id":1}', "2026-01-01T00:00:00Z"),
    )
    conn.execute(
        "INSERT INTO audit_logs(user_id,action,details,created_at) VALUES(?,?,?,?)",
        (BETA, "MODERATION_DECISION", '{"moderation_id":2}', "2026-01-01T00:00:00Z"),
    )
    for i in range(3):
        conn.execute(
            "INSERT INTO dataset_samples(comment,toxic,source,split) "
            "VALUES(?,?,?,?)",
            (f"protected row {i}", i % 2, "external:seed", "train"),
        )
    conn.execute(
        "INSERT INTO model_versions(model_name,model_version,dataset_version,"
        "training_date,status,path,created_at) VALUES(?,?,?,?,?,?,?)",
        ("m", "v1", "d", "2026-01-01", "active", "p", "2026-01-01T00:00:00Z"),
    )
    conn.execute(
        "INSERT INTO training_runs(job_id,status,started_at) VALUES(?,?,?)",
        ("job-1", "done", "2026-01-01T00:00:00Z"),
    )
    conn.commit()


def _counts(conn: sqlite3.Connection) -> dict:
    out = {}
    for table, _w, _l in p5.CASCADE_STEPS:
        out[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    out["audit_logs"] = conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
    for table in ("dataset_samples", "model_versions", "training_runs", "settings"):
        out[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    return out


class P5Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="aura-p5-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.db = self.tmp / "test.db"
        conn = sqlite3.connect(str(self.db))
        conn.executescript(SCHEMA)
        _seed(conn)
        conn.close()
        # synthetic storage artifacts
        (self.tmp / "backups").mkdir()
        (self.tmp / "processed").mkdir()
        (self.tmp / "backups" / "aura-pre-import.db").write_bytes(b"SYNTH-BACKUP")
        (self.tmp / "processed" / "demo_v1.json").write_text("{}", encoding="utf8")

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(str(self.db))
        c.row_factory = sqlite3.Row
        # Close on teardown: an open handle on Windows keeps rmtree from
        # removing the fixture dir, which leaks temp directories.
        self.addCleanup(c.close)
        return c

    def _erase(self, **kw):
        kw.setdefault("actor", ADMIN)
        kw.setdefault("subject", ALPHA)
        return p5.erase_data_subject(self.db, **kw)


# ---------------------------------------------------------------- authorisation
class TestAuthorisation(P5Base):
    def test_unauthenticated_is_401(self) -> None:
        for actor in (None, {}, {"username": "x"}, {"role": "admin"}, "bearer-token"):
            with self.subTest(actor=actor):
                with self.assertRaises(p5.AuthorisationError) as ctx:
                    self._erase(actor=actor)
                self.assertEqual(ctx.exception.status, 401)
        c = self._conn()
        self.assertEqual(_counts(c)["moderation_results"], 4)

    def test_non_admin_is_403_and_changes_nothing(self) -> None:
        with self.assertRaises(p5.AuthorisationError) as ctx:
            self._erase(actor=PLAIN)
        self.assertEqual(ctx.exception.status, 403)
        c = self._conn()
        counts = _counts(c)
        self.assertEqual(counts["users"], 2)
        self.assertEqual(counts["moderation_results"], 4)
        self.assertEqual(counts["live_events"], 1)

    def test_empty_subject_rejected(self) -> None:
        for bad in ("", "   ", None, 123):
            with self.subTest(subject=bad):
                with self.assertRaises(p5.P5Error):
                    self._erase(subject=bad)


# ------------------------------------------------------------------- happy path
class TestSuccessfulDeletion(P5Base):
    def test_cascade_removes_every_attributable_row(self) -> None:
        result = self._erase()
        self.assertFalse(result["dry_run"])
        c = self._conn()
        counts = _counts(c)
        # every subject-owned row gone
        self.assertEqual(counts["users"], 1, "other subject's identity must survive")
        self.assertEqual(counts["moderation_results"], 1)
        self.assertEqual(counts["feedback"], 0)
        self.assertEqual(counts["live_sessions"], 1)
        self.assertEqual(counts["live_events"], 0)
        self.assertGreater(result["total_rows_deleted"], 0)
        # audit evidence preserved, erasure record appended
        self.assertEqual(counts["audit_logs"], 3)  # 2 original + 1 DATA_ERASURE
        self.assertEqual(result["audit_rows_preserved"], 1)

    def test_protected_tables_untouched(self) -> None:
        before = _counts(self._conn())
        self._erase()
        after = _counts(self._conn())
        for table in ("dataset_samples", "model_versions", "training_runs", "settings"):
            self.assertEqual(before[table], after[table], table)

    def test_cross_subject_isolation(self) -> None:
        self._erase()
        c = self._conn()
        rows = c.execute(
            "SELECT username FROM users WHERE username = ?", (BETA,)
        ).fetchall()
        self.assertEqual(len(rows), 1, "erasing one subject must not touch another")
        self.assertEqual(
            c.execute(
                "SELECT COUNT(*) FROM moderation_results WHERE user_id = ?", (BETA,)
            ).fetchone()[0],
            1,
        )
        self.assertEqual(
            c.execute(
                "SELECT COUNT(*) FROM audit_logs WHERE user_id = ?", (BETA,)
            ).fetchone()[0],
            1,
        )

    def test_dry_run_makes_no_changes(self) -> None:
        before = _counts(self._conn())
        result = self._erase(dry_run=True)
        self.assertTrue(result["dry_run"])
        self.assertFalse(Path(self.db).stat().st_size < 0)
        self.assertEqual(_counts(self._conn()), before)

    def test_plan_is_read_only(self) -> None:
        before = _counts(self._conn())
        plan = p5.build_plan(
            self.db, actor=ADMIN, subject=ALPHA, files_root=self.tmp
        )
        self.assertEqual(_counts(self._conn()), before)
        # live_events 1 + live_sessions 1 + feedback 1 + moderation 3 + users 1
        self.assertEqual(plan["total_rows_to_delete"], 7)
        self.assertEqual(plan["audit_rows_preserved"], 1)
        self.assertEqual(len(plan["shared_artifacts"]), 2)
        # shared artifacts are never claimed to be subject-attributable
        for item in plan["shared_artifacts"]:
            self.assertFalse(item["attributable_to_subject"])


# ------------------------------------------------------------- idempotency/retry
class TestIdempotency(P5Base):
    def test_second_erase_is_idempotent(self) -> None:
        first = self._erase()
        self.assertGreater(first["total_rows_deleted"], 0)
        second = self._erase()  # retry: must not raise
        self.assertEqual(second["total_rows_deleted"], 0)
        self.assertEqual(second["deleted"]["moderation_results"], 0)
        # a third attempt is still clean
        third = self._erase()
        self.assertEqual(third["total_rows_deleted"], 0)

    def test_repeated_erasure_does_not_delete_audit_evidence(self) -> None:
        self._erase()
        self._erase()
        c = self._conn()
        self.assertEqual(
            c.execute(
                "SELECT COUNT(*) FROM audit_logs WHERE action != 'DATA_ERASURE'"
            ).fetchone()[0],
            2,
            "historical audit rows must never be erased or duplicated away",
        )


# --------------------------------------------------------------- rollback/failure
class TestRollback(P5Base):
    def test_failure_mid_cascade_rolls_back_everything(self) -> None:
        """A trigger re-inserting a child row simulates a cascade failure."""
        c = self._conn()
        c.execute(
            "CREATE TRIGGER t_orphan AFTER DELETE ON users "
            "BEGIN INSERT INTO moderation_results(user_id,conversation_id,"
            "message,result_json,created_at) VALUES(OLD.username,'x','y','{}',"
            "'2026-01-01T00:00:00Z'); END;"
        )
        c.commit()
        c.close()

        before = _counts(self._conn())
        with self.assertRaises(p5.OrphanError):
            self._erase()

        after = _counts(self._conn())
        self.assertEqual(after, before, "rollback must restore the exact prior state")
        self.assertEqual(after["moderation_results"], 4)
        self.assertEqual(after["users"], 2)
        self.assertEqual(after["audit_logs"], 2, "no audit row written on failure")

    def test_orphan_check_detects_residual_rows(self) -> None:
        c = self._conn()
        c.execute(
            "CREATE TRIGGER t_orphan AFTER DELETE ON users "
            "BEGIN INSERT INTO moderation_results(user_id,conversation_id,"
            "message,result_json,created_at) VALUES(OLD.username,'x','y','{}',"
            "'2026-01-01T00:00:00Z'); END;"
        )
        c.commit()
        c.close()
        with self.assertRaises(p5.OrphanError) as ctx:
            self._erase()
        self.assertIn("moderation_results", str(ctx.exception))


# --------------------------------------------------- storage/database consistency
class TestStorageConsistency(P5Base):
    def test_files_and_rows_deleted_together(self) -> None:
        backup = self.tmp / "backups" / "aura-pre-import.db"
        cached = self.tmp / "processed" / "demo_v1.json"
        self.assertTrue(backup.exists() and cached.exists())

        result = self._erase(files_root=self.tmp, include_files=True)

        self.assertFalse(backup.exists(), "in-scope artifact must be deleted")
        self.assertFalse(cached.exists(), "in-scope artifact must be deleted")
        self.assertTrue(result["files_purged"])
        self.assertEqual(result["files_staged"], 2)
        trash = self.tmp / ".p5_trash"
        self.assertFalse(trash.exists(), "trash staging must not linger")
        c = self._conn()
        self.assertEqual(_counts(c)["moderation_results"], 1)

    def test_files_not_deleted_without_explicit_opt_in(self) -> None:
        result = self._erase(files_root=self.tmp)  # include_files defaults False
        self.assertEqual(result["files_staged"], 0)
        self.assertTrue((self.tmp / "backups" / "aura-pre-import.db").exists())
        self.assertTrue((self.tmp / "processed" / "demo_v1.json").exists())

    def test_failed_file_staging_rolls_back_rows_and_restores_files(self) -> None:
        """Second staging move fails -> rows rolled back, first file restored."""
        backup = self.tmp / "backups" / "aura-pre-import.db"
        cached = self.tmp / "processed" / "demo_v1.json"
        real_move = shutil.move
        calls = {"n": 0}

        def flaky(src, dst):
            calls["n"] += 1
            if calls["n"] == 2:
                raise OSError("simulated storage failure")
            return real_move(src, dst)

        before = _counts(self._conn())
        with mock.patch.object(p5.shutil, "move", side_effect=flaky):
            with self.assertRaises(OSError):
                self._erase(files_root=self.tmp, include_files=True)

        after = _counts(self._conn())
        self.assertEqual(after, before, "DB must be rolled back on storage failure")
        self.assertTrue(backup.exists(), "staged file must be restored")
        self.assertTrue(cached.exists(), "unmoved file must remain in place")
        trash = self.tmp / ".p5_trash"
        self.assertFalse(trash.exists() and any(trash.iterdir()), "no lost files")

    def test_missing_files_root_is_safe(self) -> None:
        result = self._erase(files_root=None, include_files=True)
        self.assertEqual(result["files_staged"], 0)
        self.assertTrue((self.tmp / "backups" / "aura-pre-import.db").exists())


# ------------------------------------------------------------------ P5a retention
class TestRetentionPolicy(P5Base):
    def test_policy_is_unset_and_no_period_is_invented(self) -> None:
        conn = self._conn()
        policy = p5.retention_policy(conn)
        conn.close()
        self.assertEqual(policy["policy"], "unset")
        self.assertIsNone(policy["end_date"])
        self.assertFalse(policy["enforced"])
        self.assertIn("approved up front", policy["reason"])

    def test_purge_refuses_while_policy_unset(self) -> None:
        with self.assertRaises(p5.RetentionPolicyError) as ctx:
            p5.purge_expired(self.db, actor=ADMIN)
        self.assertIn("No approved retention end date", str(ctx.exception))

    def test_active_policy_is_read_from_settings_not_hardcoded(self) -> None:
        conn = self._conn()
        conn.execute(
            "INSERT INTO settings(key,value) VALUES('retention_end_date',"
            "'2030-12-31')"
        )
        conn.commit()
        policy = p5.retention_policy(conn)
        conn.close()
        self.assertEqual(policy["policy"], "active")
        self.assertEqual(policy["end_date"], "2030-12-31")
        self.assertTrue(policy["enforced"])

    def test_malformed_date_is_rejected_not_silently_used(self) -> None:
        conn = self._conn()
        conn.execute(
            "INSERT INTO settings(key,value) VALUES('retention_end_date','soon')"
        )
        conn.commit()
        with self.assertRaises(p5.RetentionPolicyError):
            p5.retention_policy(conn)
        conn.close()

    def test_purge_before_end_date_is_a_no_op(self) -> None:
        conn = self._conn()
        conn.execute(
            "INSERT INTO settings(key,value) VALUES('retention_end_date','2099-01-01')"
        )
        conn.commit()
        conn.close()
        out = p5.purge_expired(self.db, actor=ADMIN, today="2026-01-01")
        self.assertFalse(out["expired"])
        self.assertEqual(out["deleted"], 0)


# ------------------------------------------------------------ production guarding
class TestProductionGuard(P5Base):
    def test_production_db_is_refused_by_default(self) -> None:
        with self.assertRaises(p5.P5Error) as ctx:
            p5.erase_data_subject(p5.PRODUCTION_DB, actor=ADMIN, subject="admin")
        self.assertIn("Refusing to operate on the production database", str(ctx.exception))
        # and build_plan / retention refuse too
        with self.assertRaises(p5.P5Error):
            p5.build_plan(p5.PRODUCTION_DB, actor=ADMIN, subject="admin")

    def test_missing_database_is_an_error(self) -> None:
        with self.assertRaises(p5.P5Error):
            p5.erase_data_subject(self.tmp / "nope.db", actor=ADMIN, subject=ALPHA)


if __name__ == "__main__":
    unittest.main(verbosity=2)
