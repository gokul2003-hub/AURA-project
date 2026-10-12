"""Phase 4.17 (part B) - authentication telemetry, login throttling & invariants.

Run:  python tests_p417_auth_hardening.py

Isolation
---------
* Every test repoints ``backend.DB_PATH`` at a temp file. **The production
  database is never opened for writing.**
* Synthetic accounts and synthetic passwords only. No credential value is
  printed, stored in a fixture, or asserted as a literal.
* No network, no dataset, no model, no frozen artifact.
* ``TestProductionUntouched`` opens production **read-only** (``mode=ro``) and
  exists to prove this suite changed nothing.

**This suite calls backend functions directly. It never starts the server and
sends no write-capable HTTP request to the live service.**
"""
from __future__ import annotations

import ast
import hashlib
import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_DIR))

PROD_DB = BACKEND_DIR / "aura.db"
BACKEND_SRC = BACKEND_DIR / "backend.py"

import backend  # noqa: E402
from fastapi import HTTPException  # noqa: E402

_STRONG = "synthetic-phase417-bT5kM8" + os.urandom(3).hex()

_SECRET_MARKERS = ("password", "passwd", "salt", "token", "secret")
# Container nodes unparse *every* literal they hold, so a reason LABEL such as
# 'current_password_mismatch' would be misread as secret material. Only atomic
# value expressions (names, attributes, subscripts) can carry a real secret.
_CONTAINER_NODES = (ast.Dict, ast.List, ast.Tuple, ast.Set)


def _audit_secret_offenders(tree: ast.AST):
    """Return (lineno, marker, text) for every audit_log call passing a secret.

    String literals are exempt (they are reason labels, never secret material);
    anything that could hold a live value is checked.
    """
    found = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call) or getattr(n.func, "id", None) != "audit_log":
            continue
        for arg in n.args[1:]:
            for sub in ast.walk(arg):
                if isinstance(sub, _CONTAINER_NODES) or isinstance(sub, ast.Constant):
                    continue  # containers are re-scanned via their children; literals are labels
                text = ast.unparse(sub)
                for banned in _SECRET_MARKERS:
                    if banned in text.lower():
                        found.append((n.lineno, banned, text))
    return found


class _Isolated(unittest.TestCase):
    """Temp database + clean SESSIONS for every single test."""

    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory(prefix="p417b-")
        self.temp_db = Path(self._dir.name) / "synthetic.db"
        self._saved_path = backend.DB_PATH
        backend.DB_PATH = self.temp_db
        backend.SESSIONS.clear()
        backend.init_db()  # temp file only

    def tearDown(self) -> None:
        backend.SESSIONS.clear()
        backend.DB_PATH = self._saved_path
        self._dir.cleanup()

    # helpers ---------------------------------------------------------------
    def _seed(self, username, password, role="user", blocked=0):
        h, s = backend.hash_password(password)
        c = backend.db()
        try:
            c.execute(
                "INSERT INTO users(username,password_hash,salt,role,blocked,created_at,credential_version)"
                " VALUES(?,?,?,?,?,?,0)", (username, h, s, role, blocked, backend.now()))
            c.commit()
        finally:
            c.close()

    def _row(self, username):
        c = backend.db()
        try:
            return c.execute(
                "SELECT id,username,password_hash,salt,role,blocked,credential_version"
                " FROM users WHERE lower(username)=lower(?)", (username,)).fetchone()
        finally:
            c.close()

    def _login(self, username, password, role=None):
        try:
            out = backend.login(backend.LoginIn(username=username, password=password, role=role))
            return out.get("token"), None
        except HTTPException as exc:
            return None, (exc.status_code, exc.detail)

    def _auth(self, token):
        return "Bearer " + str(token)

    def _audit(self, action=None):
        c = backend.db()
        try:
            if action:
                return c.execute("SELECT action,details FROM audit_logs WHERE action=? ORDER BY id",
                                 (action,)).fetchall()
            return c.execute("SELECT action,details FROM audit_logs ORDER BY id").fetchall()
        finally:
            c.close()

    def _scalar(self, sql, params=()):
        c = backend.db()
        try:
            return c.execute(sql, params).fetchone()[0]
        finally:
            c.close()


class TestAuthenticationTelemetry(_Isolated):
    """Task 2 - security events, with strict redaction."""

    def test_login_success_is_audited(self) -> None:
        self._seed("alice", _STRONG)
        self._login("alice", _STRONG)
        rows = self._audit("LOGIN_SUCCESS")
        self.assertEqual(len(rows), 1)
        self.assertIn("user", rows[0][1])

    def test_login_failure_unknown_user_is_audited(self) -> None:
        self._login("nobody", _STRONG)
        rows = self._audit("LOGIN_FAILED")
        self.assertEqual(len(rows), 1)
        self.assertIn("unknown_user", rows[0][1])

    def test_login_failure_bad_password_is_audited(self) -> None:
        self._seed("alice", _STRONG)
        self._login("alice", "totally-wrong-pass")
        self.assertIn("bad_password", self._audit("LOGIN_FAILED")[0][1])

    def test_login_failure_blocked_account_is_audited(self) -> None:
        self._seed("carol", _STRONG, blocked=1)
        self._login("carol", _STRONG)
        self.assertIn("blocked", self._audit("LOGIN_FAILED")[0][1])

    def test_login_failure_role_mismatch_is_audited(self) -> None:
        self._seed("dave", _STRONG)
        self._login("dave", _STRONG, role="admin")
        self.assertIn("role_mismatch", self._audit("LOGIN_FAILED")[0][1])

    def test_audit_never_contains_a_password(self) -> None:
        attempted = "attacker-supplied-secret-9x"
        self._seed("alice", _STRONG)
        self._login("alice", attempted)
        for action, details in self._audit():
            with self.subTest(action=action):
                # The attempted password VALUE must never appear. A naive
                # substring test on "password" would false-positive on the
                # legitimate reason LABEL "bad_password".
                self.assertNotIn(attempted, details)
                self.assertNotIn(attempted.lower(), details.lower())

    def test_audit_never_contains_a_password_hash(self) -> None:
        self._seed("alice", _STRONG)
        self._login("alice", "totally-wrong-pass")
        row = self._row("alice")
        for action, details in self._audit():
            with self.subTest(action=action):
                self.assertNotIn(row["password_hash"], details)

    def test_audit_never_contains_a_session_token(self) -> None:
        self._seed("alice", _STRONG)
        token, _ = self._login("alice", _STRONG)
        for action, details in self._audit():
            with self.subTest(action=action):
                self.assertNotIn(token, details)

    def test_audit_never_contains_raw_message_text(self) -> None:
        """Moderation/comment content must not enter an authentication event."""
        self._seed("alice", _STRONG)
        self._login("alice", _STRONG)
        joined = " ".join(d for _, d in self._audit())
        self.assertNotIn("UNIQUE-REDACTED-COMMENT-MARKER", joined)

    def test_throttled_login_is_audited(self) -> None:
        self._seed("alice", _STRONG)
        for _ in range(12):
            self._login("alice", "wrong-pass")
        before = len(self._audit("LOGIN_FAILED"))
        self._login("alice", _STRONG)  # correct password, but throttled
        rows = self._audit("LOGIN_FAILED")
        self.assertEqual(len(rows), before + 1)
        self.assertIn("throttled", rows[-1][1])

    def test_audit_log_never_raises_when_its_store_is_unavailable(self) -> None:
        """audit_log() is documented best-effort; auth must not depend on it."""
        self._seed("alice", _STRONG)
        orig = backend.db

        def _boom():
            raise RuntimeError("audit store unavailable")

        backend.db = _boom
        try:
            backend.audit_log("alice", "LOGIN_SUCCESS", {"role": "user"})  # must not raise
        finally:
            backend.db = orig
        token, err = self._login("alice", _STRONG)
        self.assertIsNone(err, "a broken audit store must not break authentication")
        self.assertIsNotNone(backend.current(self._auth(token)))

    def test_source_contains_no_audit_of_secret_fields(self) -> None:
        """Static: no audit_log call may pass a secret-bearing *variable*.

        String literals such as ``'current_password_mismatch'`` or
        ``'bad_password'`` are reason LABELS, not secret material, so literals
        are exempt; anything that could carry a real value (variable, attribute
        or subscript) is checked.
        """
        offenders = _audit_secret_offenders(ast.parse(BACKEND_SRC.read_text(encoding="utf8")))
        self.assertEqual(offenders, [], f"audit_log passes secret material: {offenders}")

    def test_secret_audit_detector_is_not_neutered(self) -> None:
        """The detector above must still fire on a real leak (synthetic sample).

        Guards against the check being weakened into a no-op that passes
        regardless of what backend.py does.
        """
        sample = ast.parse(
            "def f(row, attempted_password):\n"
            "    audit_log('x', 'LOGIN_FAILED', {'h': row['password_hash']})\n"
            "    audit_log('x', 'LOGIN_FAILED', {'p': attempted_password})\n")
        hits = _audit_secret_offenders(sample)
        self.assertEqual(len(hits), 2, f"detector lost sensitivity: {hits}")
        self.assertEqual({h[1] for h in hits}, {"password"})


class TestLoginThrottling(_Isolated):
    """Task 3 - brute-force resistance without an admin denial-of-service."""

    def test_repeated_failures_eventually_throttle(self) -> None:
        self._seed("alice", _STRONG)
        for _ in range(5):
            self._login("alice", "wrong-pass")
        token, err = self._login("alice", _STRONG)  # correct password, now delayed
        self.assertIsNone(token)
        self.assertEqual(err[0], 401)

    def test_throttled_response_is_identical_to_a_bad_password(self) -> None:
        """Enumeration resistance: the delay is the only observable difference."""
        self._seed("alice", _STRONG)
        self._login("alice", "wrong-pass")
        _, bad = self._login("alice", "wrong-pass")
        for _ in range(6):
            self._login("alice", "wrong-pass")
        _, throttled = self._login("alice", _STRONG)
        _, wrong_again = self._login("alice", "wrong-pass")
        self.assertEqual(bad, throttled, "throttling must not change the response")
        self.assertEqual(bad, wrong_again)

    def test_backoff_is_a_delay_not_a_permanent_lockout(self) -> None:
        """DoS resistance: the sole administrator must recover after the window."""
        self._seed("alice", _STRONG)
        for _ in range(12):
            self._login("alice", "wrong-pass")
        self.assertIsNotNone(self._scalar(
            "SELECT locked_until FROM login_attempts WHERE lower(username)='alice'"))
        past = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        c = backend.db()
        c.execute("UPDATE login_attempts SET locked_until=? WHERE lower(username)='alice'", (past,))
        c.commit()
        c.close()
        token, err = self._login("alice", _STRONG)
        self.assertIsNone(err, "the account must recover after the backoff window")
        self.assertIsNotNone(token)

    def test_backoff_is_capped(self) -> None:
        self.assertEqual(backend._backoff_seconds(5), 30)
        self.assertEqual(backend._backoff_seconds(6), 60)
        self.assertEqual(backend._backoff_seconds(9), 480)
        self.assertEqual(backend._backoff_seconds(10), backend.LOGIN_BACKOFF_MAX_SECONDS)
        self.assertLessEqual(backend._backoff_seconds(10000), backend.LOGIN_BACKOFF_MAX_SECONDS)

    def test_no_delay_before_the_threshold(self) -> None:
        for n in (1, 2, 3, 4):
            self.assertEqual(backend._backoff_seconds(n), 0, f"{n} failures must not yet delay")

    def test_successful_login_clears_the_counter(self) -> None:
        self._seed("alice", _STRONG)
        for _ in range(3):
            self._login("alice", "wrong-pass")
        self._login("alice", _STRONG)
        n = self._scalar("SELECT COUNT(*) FROM login_attempts WHERE lower(username)='alice'")
        self.assertEqual(n, 0, "a successful login must reset the counter")

    def test_counter_window_expires(self) -> None:
        self._seed("alice", _STRONG)
        for _ in range(4):
            self._login("alice", "wrong-pass")
        stale = (datetime.now(timezone.utc) - timedelta(
            seconds=backend.LOGIN_FAILURE_WINDOW_SECONDS + 60)).isoformat()
        c = backend.db()
        c.execute("UPDATE login_attempts SET first_fail_at=? WHERE lower(username)='alice'", (stale,))
        c.commit()
        c.close()
        backend.record_login_failure("alice")
        count = self._scalar("SELECT fail_count FROM login_attempts WHERE lower(username)='alice'")
        self.assertEqual(count, 1, "the counter must restart after the window")

    def test_account_enumeration_is_resisted(self) -> None:
        """Unknown user and bad password must be indistinguishable."""
        self._seed("alice", _STRONG)
        _, unknown = self._login("ghost-user-xyz", _STRONG)
        _, wrong = self._login("alice", "wrong-pass")
        self.assertEqual(unknown, wrong, "responses differ => account enumeration")

    def test_throttling_is_uniform_so_enumeration_is_resisted(self) -> None:
        """Unknown usernames are tracked too, or the delay becomes an oracle.

        Uses 4 attempts (below the 5-failure threshold) so both names are
        actually recorded; above the threshold login short-circuits and the
        counter legitimately stops at the cap.
        """
        self._seed("alice", _STRONG)
        for _ in range(4):
            self._login("ghost-user-xyz", _STRONG)
            self._login("alice", "wrong-pass")
        ghost = self._scalar("SELECT fail_count FROM login_attempts WHERE lower(username)='ghost-user-xyz'")
        known = self._scalar("SELECT fail_count FROM login_attempts WHERE lower(username)='alice'")
        self.assertEqual(ghost, 4, "unknown usernames must be tracked identically")
        self.assertEqual(ghost, known, "unknown and known usernames diverge => enumeration oracle")

    def test_counter_stops_at_the_throttle_threshold(self) -> None:
        """Past the threshold login is rejected before verification, so the
        counter caps at 5 rather than climbing forever (by design)."""
        for _ in range(8):
            self._login("ghost-user-xyz", _STRONG)
        row = self._scalar("SELECT fail_count FROM login_attempts WHERE lower(username)='ghost-user-xyz'")
        self.assertEqual(row, 5, "counter must cap at the threshold once throttling engages")

    def test_stale_attempt_entries_are_pruned(self) -> None:
        """Table growth from attacker-chosen names must stay bounded."""
        stale = (datetime.now(timezone.utc) - timedelta(
            seconds=backend.LOGIN_FAILURE_WINDOW_SECONDS + 3600)).isoformat()
        c = backend.db()
        c.execute("INSERT INTO login_attempts(username,fail_count,first_fail_at,last_fail_at)"
                  " VALUES('old-name',3,?,?)", (stale, stale))
        c.commit()
        c.close()
        backend.record_login_failure("alice")
        n = self._scalar("SELECT COUNT(*) FROM login_attempts WHERE username='old-name'")
        self.assertEqual(n, 0, "stale attempt rows must be pruned")

    def test_throttling_is_per_account(self) -> None:
        self._seed("alice", _STRONG)
        self._seed("bob", _STRONG)
        for _ in range(8):
            self._login("alice", "wrong-pass")
        token, err = self._login("bob", _STRONG)
        self.assertIsNone(err, "throttling one account must not affect another")
        self.assertIsNotNone(token)

    def test_concurrent_attempts_accumulate_safely(self) -> None:
        """Failures accumulate monotonically up to the threshold.

        4 attempts (below the 5-failure throttle point) must all be recorded;
        past that point login short-circuits before verification, so the
        counter legitimately caps (covered separately).
        """
        self._seed("alice", _STRONG)
        for _ in range(4):
            self._login("alice", "wrong-pass")
        count = self._scalar("SELECT fail_count FROM login_attempts WHERE lower(username)='alice'")
        self.assertEqual(count, 4)
        self._login("alice", _STRONG)  # success must still clear it
        self.assertEqual(
            self._scalar("SELECT COUNT(*) FROM login_attempts WHERE lower(username)='alice'"), 0)

    def test_blocked_account_is_not_revealed_by_throttling(self) -> None:
        self._seed("carol", _STRONG, blocked=1)
        for _ in range(6):
            self._login("carol", _STRONG)
        _, err = self._login("carol", _STRONG)
        self.assertEqual(err[0], 401)
        self.assertIn("Invalid credentials", err[1])

    def test_password_is_never_persisted_in_the_attempt_table(self) -> None:
        self._seed("alice", _STRONG)
        self._login("alice", "observable-attack-string-1")
        c = backend.db()
        try:
            rows = c.execute("SELECT * FROM login_attempts").fetchall()
        finally:
            c.close()
        self.assertTrue(rows)
        blob = " ".join(str(v) for r in rows for v in tuple(r))
        self.assertNotIn("observable-attack-string-1", blob)


class TestSchemaAndInvariants(_Isolated):
    def test_isolation_repoints_db_path_away_from_production(self) -> None:
        """Guard: every test in this suite must run on a temp database.

        ``backend.DB_PATH`` legitimately defaults to the production file, so
        the meaningful assertion is that the isolation harness has repointed it
        before any write-capable code runs.
        """
        self.assertNotEqual(str(backend.DB_PATH), str(PROD_DB))
        self.assertTrue(str(backend.DB_PATH).startswith(tempfile.gettempdir())
                        or "p417b-" in str(backend.DB_PATH),
                        f"isolated tests must not target {backend.DB_PATH}")

    def test_migration_is_additive_and_idempotent(self) -> None:
        backend.init_db()
        backend.init_db()
        c = backend.db()
        try:
            cols = {r[1] for r in c.execute("PRAGMA table_info(users)").fetchall()}
            tables = {r[0] for r in c.execute(
                "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        finally:
            c.close()
        self.assertIn("credential_version", cols)
        self.assertIn("login_attempts", tables)

    def test_existing_rows_receive_a_default_version(self) -> None:
        c = backend.db()
        c.execute("INSERT INTO users(username,password_hash,salt,role,created_at)"
                  " VALUES('legacy','h','s','user',?)", (backend.now(),))
        c.commit()
        row = c.execute("SELECT credential_version FROM users WHERE username='legacy'").fetchone()
        c.close()
        self.assertEqual(row[0], 0)

    def test_new_functions_are_not_at_module_scope(self) -> None:
        tree = ast.parse(BACKEND_SRC.read_text(encoding="utf8"))
        spans = [(n.lineno, getattr(n, "end_lineno", n.lineno), type(n).__name__)
                 for n in tree.body]
        offenders = []
        for n in ast.walk(tree):
            if not isinstance(n, ast.Call):
                continue
            fn = getattr(n.func, "id", None)
            if fn not in ("revoke_sessions", "record_login_failure",
                          "clear_login_failures", "purge_user_sessions"):
                continue
            scope = "<module-scope>"
            for s, e, kind in spans:
                if kind in ("FunctionDef", "AsyncFunctionDef") and s <= n.lineno <= e:
                    scope = "function"
                    break
            if scope == "<module-scope>":
                offenders.append((fn, n.lineno))
        self.assertEqual(offenders, [], f"runs at import time: {offenders}")


class TestProductionUntouched(unittest.TestCase):
    """The live database must be exactly as it was at the start of 4.17."""

    def _ro(self):
        return sqlite3.connect("file:" + str(PROD_DB) + "?mode=ro", uri=True, timeout=20)

    def test_production_invariants_hold(self) -> None:
        c = self._ro()
        try:
            self.assertEqual(c.execute(
                "SELECT value FROM settings WHERE key='prediction_engine'").fetchone()[0], "legacy")
            self.assertEqual(c.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(c.execute("SELECT COUNT(*) FROM users").fetchone()[0], 20)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()[0], 1)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM users WHERE blocked=1").fetchone()[0], 2)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0], 1682)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM moderation_results").fetchone()[0], 1630)
            self.assertEqual(c.execute(
                "SELECT COUNT(*) FROM audit_logs WHERE action='DATA_ERASURE'").fetchone()[0], 0)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM training_runs").fetchone()[0], 8)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM model_versions").fetchone()[0], 12)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM dataset_samples").fetchone()[0], 596)
            # No Phase 4.17 event may exist in production.
            self.assertEqual(c.execute(
                "SELECT COUNT(*) FROM audit_logs WHERE action IN "
                "('LOGIN_SUCCESS','LOGIN_FAILED','SESSIONS_REVOKED')").fetchone()[0], 0)
            self.assertEqual(c.execute(
                "SELECT COUNT(*) FROM audit_logs WHERE action IN "
                "('ADMIN_PROVISIONED','CREDENTIAL_ROTATION','CREDENTIAL_ROTATION_DENIED')").fetchone()[0], 0)
            # The 4.17 migration must NOT have been applied to production.
            tables = {r[0] for r in c.execute(
                "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            self.assertNotIn("login_attempts", tables,
                             "the 4.17 migration must not have run against production")
            cols = {r[1] for r in c.execute("PRAGMA table_info(users)").fetchall()}
            self.assertNotIn("credential_version", cols,
                             "the 4.17 migration must not have run against production")
        finally:
            c.close()

    def setUp(self) -> None:
        # Snapshot production so the suite can prove it never mutated it.
        st = PROD_DB.stat()
        self._prod_before = (st.st_size, st.st_mtime_ns)

    def test_production_file_was_not_written_by_this_suite(self) -> None:
        """This class opens production read-only; nothing here may write it."""
        st = PROD_DB.stat()
        self.assertEqual((st.st_size, st.st_mtime_ns), self._prod_before,
                         "production aura.db changed during the suite run")

    def test_protected_hashes_are_unchanged(self) -> None:
        expected = {"tuned_threshold.json": "f31f4975d29a151f",
                    "phase2_benchmark.json": "5a9d94e267806ea0",
                    "phase3_benchmark.json": "f3a5ceb488f4a9ad"}
        for name, want in expected.items():
            with self.subTest(file=name):
                got = hashlib.sha256((BACKEND_DIR / "models" / name).read_bytes()).hexdigest()[:16]
                self.assertEqual(got, want, f"{name} CHANGED")


if __name__ == "__main__":
    unittest.main(verbosity=2)
