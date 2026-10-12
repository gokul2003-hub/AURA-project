"""P15 credential-remediation tests (AURA Phase 4.15).

Run:  python tests_p15_credential_remediation.py

**Isolation guarantees**
* temp DBs only — production ``aura.db`` is never opened;
* synthetic users only — the real demo account is never touched;
* ``backend`` is **never imported** (importing it runs ``init_db()`` against the
  production database, see ``backend.py:1088``);
* the one production-adjacent action is **read-only static analysis** of the
  ``backend.py`` source text, which executes nothing.

Covers: no-reseed on start-up, blocked-state preservation, role preservation,
explicit audited rotation, audit secret-refusal, reseed detection, and absence
of hard-coded credentials in the proposed module.
"""
from __future__ import annotations

import os
import re
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import p15_credential_remediation as p15  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parent
BACKEND_SRC = BACKEND_DIR / "backend.py"

DDL = """
CREATE TABLE users(id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL,
                   password_hash TEXT NOT NULL, salt TEXT NOT NULL,
                   role TEXT NOT NULL DEFAULT 'user', blocked INTEGER NOT NULL DEFAULT 0,
                   created_at TEXT NOT NULL);
CREATE TABLE audit_logs(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT,
                        action TEXT NOT NULL, details TEXT, created_at TEXT NOT NULL);
"""

# Clearly-synthetic initial secret; created at call time so no fixed value is
# ever committed as a usable credential.
def _synthetic_secret() -> str:
    return "synthetic-test-only-" + os.urandom(6).hex()


class _TempDB(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory(prefix="p15-")
        self.path = Path(self._dir.name) / "synthetic.db"
        self.conn = sqlite3.connect(self.path)
        self.conn.executescript(DDL)

    def tearDown(self) -> None:
        self.conn.close()
        self._dir.cleanup()


class TestSeedOnceNeverOverwrite(_TempDB):
    """The core defect: init_db() rewrites credentials on every start-up."""

    def test_creates_admin_when_absent(self) -> None:
        out = p15.ensure_admin_account(self.conn, "admin", _synthetic_secret)
        self.assertEqual(out["action"], "created")
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM users").fetchone()[0], 1)

    def test_existing_password_is_preserved_across_starts(self) -> None:
        """A password set by the operator must survive a restart."""
        p15.ensure_admin_account(self.conn, "admin", _synthetic_secret)
        original_hash = self.conn.execute("SELECT password_hash FROM users").fetchone()[0]
        for _ in range(5):  # simulate 5 restarts
            p15.ensure_admin_account(self.conn, "admin", _synthetic_secret)
        self.assertEqual(
            self.conn.execute("SELECT password_hash FROM users").fetchone()[0],
            original_hash,
            "start-up reseeded the admin password",
        )

    def test_password_factory_is_not_called_when_account_exists(self) -> None:
        """A rotating factory must not silently change a live credential."""
        p15.ensure_admin_account(self.conn, "admin", _synthetic_secret)
        calls = []

        def factory() -> str:
            calls.append(1)
            return _synthetic_secret()

        p15.ensure_admin_account(self.conn, "admin", factory)
        self.assertEqual(calls, [], "password_factory was invoked for an existing account")

    def test_blocked_admin_stays_blocked_across_starts(self) -> None:
        p15.ensure_admin_account(self.conn, "admin", _synthetic_secret)
        p15.set_blocked(self.conn, "admin", True, actor="reviewer")
        self.assertEqual(self.conn.execute("SELECT blocked FROM users").fetchone()[0], 1)
        for _ in range(3):
            p15.ensure_admin_account(self.conn, "admin", _synthetic_secret)
        self.assertEqual(
            self.conn.execute("SELECT blocked FROM users").fetchone()[0],
            1,
            "start-up unblocked a blocked admin",
        )

    def test_existing_role_is_not_forced(self) -> None:
        """Start-up must not silently re-escalate a demoted account."""
        self.conn.execute(
            "INSERT INTO users(username,password_hash,salt,role,blocked,created_at) "
            "VALUES(?,?,?,?,?,?)", ("admin", "h", "s", "user", 0, "2026-01-01T00:00:00")
        )
        out = p15.ensure_admin_account(self.conn, "admin", _synthetic_secret)
        self.assertEqual(out["action"], "preserved")
        self.assertEqual(self.conn.execute("SELECT role FROM users").fetchone()[0], "user")

    def test_preserved_result_reports_no_change(self) -> None:
        p15.ensure_admin_account(self.conn, "admin", _synthetic_secret)
        out = p15.ensure_admin_account(self.conn, "admin", _synthetic_secret)
        self.assertEqual(out["action"], "preserved")
        self.assertFalse(out["password_changed"])
        self.assertFalse(out["blocked_reset"])

    def test_case_insensitive_username_lookup(self) -> None:
        p15.ensure_admin_account(self.conn, "Admin", _synthetic_secret)
        self.assertEqual(p15.ensure_admin_account(self.conn, "admin", _synthetic_secret)["action"], "preserved")

    def test_blank_username_rejected(self) -> None:
        with self.assertRaises(p15.StartupPolicy):
            p15.ensure_admin_account(self.conn, "   ", _synthetic_secret)


class TestExplicitRotation(_TempDB):
    """Rotation exists — but only as a deliberate, audited action."""

    def test_rotation_changes_the_credential(self) -> None:
        p15.ensure_admin_account(self.conn, "admin", _synthetic_secret)
        before = self.conn.execute("SELECT password_hash FROM users").fetchone()[0]
        new_secret = _synthetic_secret()
        out = p15.rotate_password(self.conn, "admin", new_secret, actor="reviewer")
        after, salt = self.conn.execute("SELECT password_hash, salt FROM users").fetchone()
        self.assertNotEqual(before, after)
        self.assertEqual(out["rows_affected"], 1)
        self.assertTrue(p15.verify_password(new_secret, after, salt))

    def test_rotation_is_audited_without_secret_material(self) -> None:
        p15.ensure_admin_account(self.conn, "admin", _synthetic_secret)
        p15.rotate_password(self.conn, "admin", _synthetic_secret(), actor="reviewer")
        row = self.conn.execute("SELECT user_id,action,details FROM audit_logs WHERE action='PASSWORD_ROTATION'").fetchone()
        self.assertIsNotNone(row, "rotation was not audited")
        self.assertEqual(row[0], "reviewer")
        for banned in ("password", "password_hash", "salt", "token"):
            self.assertNotIn(banned, row[2].lower())

    def test_rotation_never_grants_role_or_unblocks(self) -> None:
        """Rotation is not authorisation."""
        p15.ensure_admin_account(self.conn, "admin", _synthetic_secret)
        p15.set_blocked(self.conn, "admin", True, actor="reviewer")
        p15.rotate_password(self.conn, "admin", _synthetic_secret(), actor="reviewer")
        role, blocked = self.conn.execute("SELECT role,blocked FROM users").fetchone()
        self.assertEqual(role, "admin")
        self.assertEqual(blocked, 1)

    def test_rotation_of_unknown_account_rejected(self) -> None:
        with self.assertRaises(p15.StartupPolicy):
            p15.rotate_password(self.conn, "ghost", _synthetic_secret(), actor="reviewer")

    def test_empty_password_rejected(self) -> None:
        p15.ensure_admin_account(self.conn, "admin", _synthetic_secret)
        with self.assertRaises(p15.StartupPolicy):
            p15.rotate_password(self.conn, "admin", "", actor="reviewer")

    def test_hash_is_salted_per_call(self) -> None:
        h1, s1 = p15.hash_password("same-input")
        h2, s2 = p15.hash_password("same-input")
        self.assertNotEqual(s1, s2)
        self.assertNotEqual(h1, h2)

    def test_block_and_unblock_are_audited(self) -> None:
        p15.ensure_admin_account(self.conn, "admin", _synthetic_secret)
        p15.set_blocked(self.conn, "admin", True, actor="reviewer")
        p15.set_blocked(self.conn, "admin", False, actor="reviewer")
        acts = [r[0] for r in self.conn.execute("SELECT action FROM audit_logs ORDER BY id").fetchall()]
        self.assertIn("ADMIN_BLOCK", acts)
        self.assertIn("ADMIN_UNBLOCK", acts)


class TestAuditSecretRefusal(_TempDB):
    def test_secret_bearing_keys_are_refused(self) -> None:
        for details in ({"password": "x"}, {"password_hash": "x"}, {"salt": "x"}, {"token": "x"}, {"key": "x"}):
            with self.subTest(keys=list(details)):
                with self.assertRaises(p15.AuditNotWritten):
                    p15.record_audit(self.conn, "u", "TEST", details)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0], 0)

    def test_metadata_is_allowed(self) -> None:
        p15.record_audit(self.conn, "u", "TEST", {"rows_affected": 1, "policy_version": "1.0.0"})
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0], 1)


class TestReseedDetection(unittest.TestCase):
    """Static, read-only analysis of the real source — executes nothing."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.source = BACKEND_SRC.read_text(encoding="utf8")

    def test_backend_contains_no_start_up_reseed(self) -> None:
        """INVERTED in Phase 4.16.

        Phase 4.15 asserted the defect was *found*. It was then removed from
        ``backend.py`` under explicit authorization, so the correct assertion is
        now that **no** start-up path rewrites credentials.
        """
        findings = p15.detect_startup_reseed(self.source)
        start_up = [f for f in findings if f["is_start_up_path"]]
        self.assertEqual(start_up, [],
                         f"start-up still rewrites credentials: {start_up}")

    def test_init_db_never_appears_as_a_reseed_scope(self) -> None:
        findings = p15.detect_startup_reseed(self.source)
        self.assertNotIn("init_db", {f["scope"] for f in findings},
                         "init_db still contains a credential rewrite")

    def test_detector_still_detects_the_defect_when_present(self) -> None:
        """Guards against a neutered detector: the buggy shape must still be found."""
        buggy = (
            "def init_db():\n"
            "    c.execute(\"UPDATE users SET password_hash=?, role='admin', blocked=0 WHERE id=?\", (h, i))\n"
        )
        findings = p15.detect_startup_reseed(buggy)
        self.assertGreaterEqual(len(findings), 1, "detector no longer detects the defect")
        self.assertTrue(findings[0]["is_start_up_path"])
        self.assertEqual(findings[0]["scope"], "init_db")

    def test_classifier_discriminates_route_scoped_rotation(self) -> None:
        """A legitimate route-scoped rotation must NOT be flagged."""
        benign = (
            "def init_db():\n"
            "    c = db()\n\n"
            "@app.post('/rotate')\n"
            "def rotate():\n"
            "    c.execute(\"UPDATE users SET password_hash=? WHERE id=?\", (h, i))\n"
        )
        findings = p15.detect_startup_reseed(benign)
        # The detector reports *every* credential rewrite; a route-scoped one is
        # legitimate, so it must never be classified as a start-up path.
        self.assertEqual(len(findings), 1, "route-scoped rotation should still be reported")
        self.assertFalse(findings[0]["is_start_up_path"],
                         "route-scoped rotation was wrongly flagged as start-up reseed")
        self.assertEqual(findings[0]["scope"], "rotate")

    def test_classifier_ignores_explicit_operator_functions(self) -> None:
        """A CLI/operator helper must not be mistaken for a start-up path."""
        sample = (
            "def init_db():\n"
            "    pass\n\n"
            "def rotate_credential():\n"
            "    c.execute(\"UPDATE users SET password_hash=? WHERE id=?\", (h, i))\n"
        )
        findings = p15.detect_startup_reseed(sample)
        self.assertEqual(len(findings), 1)
        self.assertFalse(findings[0]["is_start_up_path"],
                         "an explicitly-invoked operator function was flagged as start-up")

    def test_clean_source_yields_no_findings(self) -> None:
        self.assertEqual(p15.detect_startup_reseed("def init_db():\n    pass\n"), [])

    def test_init_db_runs_only_from_the_startup_hook(self) -> None:
        """INVERTED in Phase 4.16: a CLI guard now exists and init_db is hook-scoped.

        Phase 4.15 recorded the absence of a ``__main__`` guard; one was added in
        Phase 4.16 alongside the explicit provisioning CLI.
        """
        self.assertIn("init_db()", self.source)
        self.assertIn("if __name__", self.source)
        self.assertIn("@app.on_event('startup')", self.source)


class TestPrototypeHygiene(unittest.TestCase):
    def test_module_contains_no_hard_coded_credential(self) -> None:
        source = Path(p15.__file__).read_text(encoding="utf8")
        # Shape check, not a literal: an Initial-caps word + '@' + 4 digits.
        self.assertIsNone(re.search(r"'[A-Z][a-z]+@[0-9]{3,}'", source),
                          "a hard-coded credential literal appears in the module")

    def test_module_never_imports_application_code(self) -> None:
        source = Path(p15.__file__).read_text(encoding="utf8")
        for forbidden in ("import backend", "import ml_service", "aura.db", "DB_PATH"):
            self.assertNotIn(forbidden, source, f"scope leak: { forbidden }")

    def test_module_opens_no_files(self) -> None:
        source = Path(p15.__file__).read_text(encoding="utf8")
        for forbidden in ("open(", "Path(", "sqlite3.connect", "urllib", "requests"):
            self.assertNotIn(forbidden, source, f"forbidden IO primitive: {forbidden}")

    def test_production_db_is_untouched_by_this_suite(self) -> None:
        prod = BACKEND_DIR / "aura.db"
        if prod.exists():
            before = prod.stat().st_mtime_ns
            conn = sqlite3.connect(f"file:{prod}?mode=ro", uri=True, timeout=20)
            conn.execute("SELECT COUNT(*) FROM users").fetchone()
            conn.close()
            self.assertEqual(prod.stat().st_mtime_ns, before,
                             "test suite modified the production database")


if __name__ == "__main__":
    unittest.main(verbosity=2)
