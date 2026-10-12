"""Phase 4.17 (part A) - session creation, revocation, rotation & expiry.

Run:  python tests_p417_session_security.py

Isolation
---------
* Every test repoints ``backend.DB_PATH`` at a temp file (the pattern from
  ``tests_audit_threshold_phase41.py``). **The production database is never
  opened for writing.**
* ``backend.SESSIONS`` is cleared around each test, so no session leaks between
  cases and no test can touch a live token.
* Synthetic accounts and synthetic passwords only. No credential value is
  printed, stored in a fixture, or asserted as a literal.
* No network, no dataset, no model, no frozen artifact.

**This suite calls backend functions directly. It never starts the server and
sends no write-capable HTTP request to the live service.**
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_DIR))

PROD_DB = BACKEND_DIR / "aura.db"

import backend  # noqa: E402
from fastapi import HTTPException  # noqa: E402

_STRONG = "synthetic-phase417-cV8nQ4" + os.urandom(3).hex()
_STRONG_2 = "synthetic-phase417-hT2wY6" + os.urandom(3).hex()


class _Isolated(unittest.TestCase):
    """Temp database + clean SESSIONS for every single test."""

    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory(prefix="p417a-")
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
        """Call the login route function directly.

        Returns (token, None) on success or (None, (status_code, detail)) on
        rejection. Never raises HTTPException to the caller.
        """
        try:
            out = backend.login(backend.LoginIn(username=username, password=password, role=role))
            return out.get("token"), None
        except HTTPException as exc:
            return None, (exc.status_code, exc.detail)

    def _auth(self, token):
        return "Bearer " + str(token)

    def _scalar(self, sql, params=()):
        c = backend.db()
        try:
            return c.execute(sql, params).fetchone()[0]
        finally:
            c.close()


class TestSessionCreation(_Isolated):
    """Task 1.1 - how sessions are created and bound."""

    def test_token_is_bound_to_credential_version(self) -> None:
        self._seed("alice", _STRONG)
        token, err = self._login("alice", _STRONG)
        self.assertIsNone(err)
        self.assertEqual(backend.SESSIONS[token]["credential_version"], 0)
        self.assertEqual(backend.SESSIONS[token]["username"], "alice")

    def test_token_carries_a_parseable_timestamp(self) -> None:
        self._seed("alice", _STRONG)
        token, _ = self._login("alice", _STRONG)
        self.assertIn("created_at", backend.SESSIONS[token])
        datetime.fromisoformat(backend.SESSIONS[token]["created_at"])  # must parse

    def test_token_is_unpredictable_across_calls(self) -> None:
        self._seed("alice", _STRONG)
        t1, _ = self._login("alice", _STRONG)
        backend.SESSIONS.clear()
        t2, _ = self._login("alice", _STRONG)
        self.assertNotEqual(t1, t2)

    def test_sessions_are_not_persisted_to_the_database(self) -> None:
        self._seed("alice", _STRONG)
        self._login("alice", _STRONG)
        c = backend.db()
        try:
            tables = {r[0] for r in c.execute(
                "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        finally:
            c.close()
        self.assertNotIn("sessions", tables, "session tokens must not be persisted")


class TestSessionRevocation(_Isolated):
    """Task 1.2 + 1.3 + acceptance: revoked sessions are rejected."""

    def setUp(self) -> None:
        super().setUp()
        self._seed("alice", _STRONG)
        self._seed("bob", _STRONG_2)
        self.alice_token, _ = self._login("alice", _STRONG)
        self.bob_token, _ = self._login("bob", _STRONG_2)

    def test_revoked_session_is_rejected_by_current(self) -> None:
        self.assertIsNotNone(backend.current(self._auth(self.alice_token)))
        backend.revoke_sessions("alice", reason="test")
        with self.assertRaises(HTTPException) as ctx:
            backend.current(self._auth(self.alice_token))
        self.assertEqual(ctx.exception.status_code, 401)

    def test_revoked_session_is_rejected_by_admin(self) -> None:
        self._seed("root", _STRONG, role="admin")
        admin_token, err = self._login("root", _STRONG, role="admin")
        self.assertIsNone(err, f"admin login failed unexpectedly: {err}")
        backend.revoke_sessions("root", reason="test")
        with self.assertRaises(HTTPException) as ctx:
            backend.admin(self._auth(admin_token))
        self.assertEqual(ctx.exception.status_code, 401)

    def test_revocation_leaves_other_users_sessions_alone(self) -> None:
        backend.revoke_sessions("alice", reason="test")
        self.assertIsNotNone(backend.current(self._auth(self.bob_token)))

    def test_revocation_purges_the_in_memory_entry(self) -> None:
        self.assertIn(self.alice_token, backend.SESSIONS)
        backend.revoke_sessions("alice", reason="test")
        self.assertNotIn(self.alice_token, backend.SESSIONS)

    def test_revocation_survives_a_process_restart(self) -> None:
        """The version is persisted, so a replayed token fails after restart."""
        backend.revoke_sessions("alice", reason="test")
        backend.SESSIONS.clear()  # simulate restart
        backend.SESSIONS[self.alice_token] = {
            "username": "alice", "role": "user",
            "credential_version": 0, "created_at": backend.now()}
        with self.assertRaises(HTTPException) as ctx:
            backend.current(self._auth(self.alice_token))
        self.assertEqual(ctx.exception.status_code, 401)

    def test_revocation_bumps_the_persisted_version(self) -> None:
        backend.revoke_sessions("alice", reason="test")
        self.assertEqual(self._row("alice")["credential_version"], 1)

    def test_revocation_of_unknown_user_does_not_raise(self) -> None:
        out = backend.revoke_sessions("ghost", reason="test")
        self.assertEqual(out["dropped"], 0)
        self.assertIsNotNone(backend.current(self._auth(self.alice_token)))

    def test_revocation_is_audited_without_secrets(self) -> None:
        backend.revoke_sessions("alice", reason="test")
        c = backend.db()
        try:
            rows = c.execute("SELECT details FROM audit_logs WHERE action='SESSIONS_REVOKED'").fetchall()
        finally:
            c.close()
        self.assertEqual(len(rows), 1)
        details = rows[0][0]
        for banned in ("token", "password", "salt", _STRONG[:8]):
            self.assertNotIn(banned, details.lower())


class TestRotationRevokesSessions(_Isolated):
    """Task 1.2 - explicit password rotation invalidates sessions."""

    def setUp(self) -> None:
        super().setUp()
        self._seed("alice", _STRONG)
        self.alice_token, _ = self._login("alice", _STRONG)

    def test_authorized_rotation_invalidates_the_session(self) -> None:
        out = backend.rotate_credential("alice", _STRONG, _STRONG_2, actor="alice")
        self.assertEqual(out["sessions_revoked"], 1)
        with self.assertRaises(HTTPException) as ctx:
            backend.current(self._auth(self.alice_token))
        self.assertEqual(ctx.exception.status_code, 401)

    def test_login_with_the_new_password_issues_a_valid_session(self) -> None:
        backend.rotate_credential("alice", _STRONG, _STRONG_2, actor="alice")
        token, err = self._login("alice", _STRONG_2)
        self.assertIsNone(err)
        self.assertIsNotNone(backend.current(self._auth(token)))

    def test_old_password_fails_after_rotation(self) -> None:
        backend.rotate_credential("alice", _STRONG, _STRONG_2, actor="alice")
        token, err = self._login("alice", _STRONG)
        self.assertIsNone(token)
        self.assertEqual(err[0], 401)

    def test_rotation_with_concurrent_sessions_revokes_all(self) -> None:
        t2, _ = self._login("alice", _STRONG)
        t3, _ = self._login("alice", _STRONG)
        alice_sessions = [t for t in backend.SESSIONS
                          if backend.SESSIONS[t]["username"] == "alice"]
        self.assertEqual(len(alice_sessions), 3)
        out = backend.rotate_credential("alice", _STRONG, _STRONG_2, actor="alice")
        self.assertEqual(out["sessions_revoked"], 3)
        for t in (self.alice_token, t2, t3):
            with self.assertRaises(HTTPException):
                backend.current(self._auth(t))

    def test_failed_rotation_leaves_sessions_valid(self) -> None:
        with self.assertRaises(backend.ProvisioningError):
            backend.rotate_credential("alice", "wrong-current-pass", _STRONG_2, actor="mallory")
        self.assertIsNotNone(backend.current(self._auth(self.alice_token)),
                             "a failed rotation must not invalidate the session")
        row = self._row("alice")
        self.assertTrue(backend.verify_password(_STRONG, row["password_hash"], row["salt"]))
        self.assertEqual(row["credential_version"], 0)

    def test_unauthorized_rotation_does_not_touch_another_account(self) -> None:
        """Brief Task 1.5 - cross-account isolation."""
        self._seed("bob", _STRONG_2)
        bob_token, _ = self._login("bob", _STRONG_2)
        before_bob = self._row("bob")
        with self.assertRaises(backend.ProvisioningError):
            backend.rotate_credential("alice", "wrong-current-pass", _STRONG_2, actor="mallory")
        after_bob = self._row("bob")
        self.assertEqual(before_bob["password_hash"], after_bob["password_hash"])
        self.assertEqual(before_bob["role"], after_bob["role"])
        self.assertEqual(before_bob["blocked"], after_bob["blocked"])
        self.assertEqual(before_bob["credential_version"], after_bob["credential_version"])
        self.assertIsNotNone(backend.current(self._auth(bob_token)))

    def test_rotation_of_unknown_account_touches_nothing(self) -> None:
        with self.assertRaises(backend.ProvisioningError):
            backend.rotate_credential("ghost", _STRONG, _STRONG_2)
        self.assertIsNotNone(backend.current(self._auth(self.alice_token)))

    def test_rotation_to_the_same_password_is_rejected_and_revokes_nothing(self) -> None:
        with self.assertRaises(backend.ProvisioningError):
            backend.rotate_credential("alice", _STRONG, _STRONG)
        self.assertIsNotNone(backend.current(self._auth(self.alice_token)))

    def test_rotation_does_not_change_role_or_blocked(self) -> None:
        c = backend.db()
        c.execute("UPDATE users SET blocked=1 WHERE lower(username)='alice'")
        c.commit()
        c.close()
        backend.rotate_credential("alice", _STRONG, _STRONG_2, actor="alice")
        row = self._row("alice")
        self.assertEqual(row["role"], "user")
        self.assertEqual(row["blocked"], 1, "rotation must never unblock")

    def test_rotation_audit_contains_no_secret(self) -> None:
        backend.rotate_credential("alice", _STRONG, _STRONG_2, actor="alice")
        c = backend.db()
        try:
            rows = c.execute("SELECT details FROM audit_logs WHERE action='CREDENTIAL_ROTATION'").fetchall()
        finally:
            c.close()
        self.assertEqual(len(rows), 1)
        for banned in (_STRONG[:8], _STRONG_2[:8], "password", "salt", "token"):
            self.assertNotIn(banned, rows[0][0].lower())


class TestSessionExpiry(_Isolated):
    """Task 1.4 - expired sessions, restarts and unknown users."""

    def test_expired_session_is_rejected(self) -> None:
        self._seed("alice", _STRONG)
        token, _ = self._login("alice", _STRONG)
        backend.SESSIONS[token]["created_at"] = (
            datetime.now(timezone.utc) - timedelta(seconds=backend.SESSION_TTL_SECONDS + 60)
        ).isoformat()
        with self.assertRaises(HTTPException) as ctx:
            backend.current(self._auth(token))
        self.assertEqual(ctx.exception.status_code, 401)
        self.assertNotIn(token, backend.SESSIONS, "expired token should be dropped")

    def test_session_within_ttl_is_accepted(self) -> None:
        self._seed("alice", _STRONG)
        token, _ = self._login("alice", _STRONG)
        backend.SESSIONS[token]["created_at"] = (
            datetime.now(timezone.utc) - timedelta(seconds=60)
        ).isoformat()
        self.assertIsNotNone(backend.current(self._auth(token)))

    def test_unparseable_timestamp_rejects_the_session(self) -> None:
        """Fail closed, never open."""
        self._seed("alice", _STRONG)
        token, _ = self._login("alice", _STRONG)
        backend.SESSIONS[token]["created_at"] = "not-a-timestamp"
        with self.assertRaises(HTTPException):
            backend.current(self._auth(token))

    def test_application_restart_invalidates_every_session(self) -> None:
        self._seed("alice", _STRONG)
        token, _ = self._login("alice", _STRONG)
        backend.SESSIONS.clear()  # restart
        with self.assertRaises(HTTPException) as ctx:
            backend.current(self._auth(token))
        self.assertEqual(ctx.exception.status_code, 401)

    def test_deleted_user_cannot_use_a_live_session(self) -> None:
        self._seed("alice", _STRONG)
        token, _ = self._login("alice", _STRONG)
        c = backend.db()
        c.execute("DELETE FROM users WHERE lower(username)='alice'")
        c.commit()
        c.close()
        with self.assertRaises(HTTPException) as ctx:
            backend.current(self._auth(token))
        self.assertEqual(ctx.exception.status_code, 401)

    def test_malformed_authorization_headers_are_rejected(self) -> None:
        for bad in (None, "", "Token abc", "Bearer ", "bearer abc"):
            with self.subTest(header=bad):
                with self.assertRaises(HTTPException) as ctx:
                    backend.current(bad)
                self.assertEqual(ctx.exception.status_code, 401)

    def test_forged_version_in_a_live_session_is_rejected(self) -> None:
        self._seed("alice", _STRONG)
        token, _ = self._login("alice", _STRONG)
        backend.SESSIONS[token]["credential_version"] = 99
        with self.assertRaises(HTTPException):
            backend.current(self._auth(token))


if __name__ == "__main__":
    unittest.main(verbosity=2)
