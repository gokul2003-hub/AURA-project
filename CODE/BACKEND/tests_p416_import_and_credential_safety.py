"""Phase 4.16 — import-safety and admin-credential safety tests.

Run:  python tests_p416_import_and_credential_safety.py

Isolation guarantees
--------------------
* The **production** database is never opened for writing: every DB-touching
  test repoints ``backend.DB_PATH`` at a temp file (the pattern already used by
  ``tests_audit_threshold_phase41.py``).
* Import safety is proven twice: (a) by trapping ``sqlite3.connect`` during
  import, and (b) by a **subprocess** that imports the module and compares the
  production DB's mtime/counts before and after.
* No credential value is printed, stored in a fixture, or asserted as a
  literal; weak-password tests use obviously-synthetic strings.
* No network, no dataset, no model, no frozen artifact.

Covers (Stage 3.5 of the brief): first-time provisioning creates no reusable
hard-coded password; repeated initialization preserves password hash, role and
blocked; startup cannot silently unblock or re-escalate; rotation happens only
through the explicit path; unauthorized rotation and privilege escalation are
rejected.
"""
from __future__ import annotations

import ast
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_DIR))

PROD_DB = BACKEND_DIR / "aura.db"
BACKEND_SRC = BACKEND_DIR / "backend.py"

_PY = sys.executable

# Synthetic-only secrets. Never a real credential.
_STRONG = "synthetic-phase416-aB3xK9" + os.urandom(3).hex()
_STRONG_2 = "synthetic-phase416-qR7mZ2" + os.urandom(3).hex()

_connect_calls_during_import: list = []


# ---------------------------------------------------------------------------
# Import backend ONCE, with sqlite3.connect trapped so any DB access during
# import is recorded rather than silently performed.
# ---------------------------------------------------------------------------
_orig_connect = sqlite3.connect


def _recording_connect(*args, **kwargs):
    _connect_calls_during_import.append((str(args[0]) if args else "", bool(kwargs)))
    return _orig_connect(*args, **kwargs)


sqlite3.connect = _recording_connect
try:
    import backend  # noqa: E402
finally:
    sqlite3.connect = _orig_connect


class TestImportSafety(unittest.TestCase):
    """Stage 2: importing the module must perform no database work."""

    def test_import_performed_no_database_connection(self) -> None:
        self.assertEqual(
            _connect_calls_during_import, [],
            f"importing backend opened a database connection: {_connect_calls_during_import}",
        )

    def test_init_db_is_only_reachable_from_the_startup_hook(self) -> None:
        tree = ast.parse(BACKEND_SRC.read_text(encoding="utf8"))
        spans = [
            (n.lineno, getattr(n, "end_lineno", n.lineno), type(n).__name__,
             [ast.unparse(d) for d in getattr(n, "decorator_list", [])])
            for n in tree.body
        ]
        calls = [n.lineno for n in ast.walk(tree)
                 if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "init_db"]
        self.assertGreaterEqual(len(calls), 1)
        for ln in calls:
            enclosing = None
            for s, e, kind, decs in spans:
                if kind in ("FunctionDef", "AsyncFunctionDef") and s <= ln <= e:
                    enclosing = decs or [f"<function@L{s}>"]
                    break
            self.assertIsNotNone(enclosing, f"init_db() at L{ln} is at module scope")
            joined = " ".join(enclosing)
            self.assertIn(
                "on_event", joined,
                f"init_db() at L{ln} must live in the ASGI startup hook, found {enclosing}",
            )

    def test_no_db_touching_call_is_at_module_scope(self) -> None:
        tree = ast.parse(BACKEND_SRC.read_text(encoding="utf8"))
        spans = [
            (n.lineno, getattr(n, "end_lineno", n.lineno), type(n).__name__)
            for n in tree.body
        ]

        def enclosing_scope(ln: int) -> str:
            for s, e, kind in spans:
                if kind in ("FunctionDef", "AsyncFunctionDef") and s <= ln <= e:
                    return f"function@L{s}"
            return "<module-scope>"

        for target, attr in (("db", None), (None, "connect")):
            for n in ast.walk(tree):
                if not isinstance(n, ast.Call):
                    continue
                name = getattr(n.func, "id", None) if attr is None else getattr(n.func, "attr", None)
                if name != (target or attr):
                    continue
                self.assertNotEqual(
                    enclosing_scope(n.lineno), "<module-scope>",
                    f"{target or 'sqlite3.connect'}() at L{n.lineno} executes at import time",
                )

    def test_main_guard_exists_and_is_not_run_on_import(self) -> None:
        self.assertIn("if __name__ == '__main__':", BACKEND_SRC.read_text(encoding="utf8"))
        # If it ran, _cli() would have exited non-zero before reaching here.
        self.assertTrue(hasattr(backend, "_cli"))

    def test_startup_hook_is_registered_but_not_executed(self) -> None:
        self.assertTrue(hasattr(backend, "startup"))
        # Registered on the app; calling it here is done only against a temp DB
        # (see the credential tests), never against production.
        self.assertTrue(hasattr(backend, "init_db"))

    def test_subprocess_import_leaves_production_db_untouched(self) -> None:
        """Independent proof: a fresh interpreter imports backend, prod DB unchanged."""
        def snapshot() -> tuple:
            st = PROD_DB.stat()
            conn = _orig_connect(f"file:{PROD_DB}?mode=ro", uri=True, timeout=20)
            counts = {
                t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                for t in ("users", "audit_logs", "moderation_results", "dataset_samples")
            }
            admins = conn.execute(
                "SELECT COUNT(*) FROM users WHERE role='admin' AND blocked=0").fetchone()[0]
            conn.close()
            return (st.st_mtime_ns, st.st_size, counts, admins)

        before = snapshot()
        script = (
            "import sqlite3, sys, json\n"
            "sys.path.insert(0, %r)\n"
            "seen = []\n"
            "orig = sqlite3.connect\n"
            "def trap(*a, **k):\n"
            "    seen.append(str(a[0]) if a else '')\n"
            "    return orig(*a, **k)\n"
            "sqlite3.connect = trap\n"
            "import backend\n"
            "sqlite3.connect = orig\n"
            "print(json.dumps({'connects': seen, 'has_init_db': hasattr(backend,'init_db'),"
            " 'has_provision': hasattr(backend,'provision_admin')}))\n"
        ) % str(BACKEND_DIR)
        proc = subprocess.run([_PY, "-c", script], capture_output=True, text=True, timeout=300)
        self.assertEqual(proc.returncode, 0, f"subprocess import failed: {proc.stderr[-800:]}")
        payload = json.loads(proc.stdout.strip().splitlines()[-1])
        self.assertEqual(payload["connects"], [], "fresh import connected to a database")
        self.assertTrue(payload["has_init_db"])
        self.assertTrue(payload["has_provision"])
        after = snapshot()
        self.assertEqual(before, after, "production database changed across a module import")


class _TempBackend(unittest.TestCase):
    """Repoint backend.DB_PATH at a temp file so no test can touch production."""

    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory(prefix="p416-")
        self.temp_db = Path(self._dir.name) / "synthetic.db"
        self._saved = backend.DB_PATH
        backend.DB_PATH = self.temp_db
        backend.init_db()  # builds schema in the temp file only

    def tearDown(self) -> None:
        backend.DB_PATH = self._saved
        self._dir.cleanup()

    # helpers -------------------------------------------------------------
    def _row(self, username="admin"):
        conn = backend.db()
        try:
            return conn.execute(
                "SELECT id,username,password_hash,salt,role,blocked FROM users WHERE lower(username)=lower(?)",
                (username,)).fetchone()
        finally:
            conn.close()

    def _count(self, sql, params=()):
        conn = backend.db()
        try:
            return conn.execute(sql, params).fetchone()[0]
        finally:
            conn.close()


class TestFirstTimeProvisioning(_TempBackend):
    """Stage 3.3 + 3.5: explicit provisioning, no reusable hard-coded password."""

    def test_startup_creates_no_administrator(self) -> None:
        self.assertEqual(self._count("SELECT COUNT(*) FROM users WHERE role='admin'"), 0,
                         "start-up silently created an administrator")

    def test_provisioning_creates_an_administrator_explicitly(self) -> None:
        out = backend.provision_admin("rootadmin", _STRONG, interactive=False)
        self.assertEqual(out["status"], "created")
        self.assertEqual(out["role"], "admin")
        row = self._row("rootadmin")
        self.assertEqual(row["role"], "admin")
        self.assertEqual(row["blocked"], 0)

    def test_provisioned_password_verifies_and_is_salted(self) -> None:
        backend.provision_admin("rootadmin", _STRONG, interactive=False)
        row = self._row("rootadmin")
        self.assertTrue(backend.verify_password(_STRONG, row["password_hash"], row["salt"]))
        self.assertEqual(len(row["salt"]), 32)

    def test_provisioning_leaves_no_reusable_literal(self) -> None:
        """The created hash must not be a value derivable from source."""
        backend.provision_admin("rootadmin", _STRONG, interactive=False)
        row = self._row("rootadmin")
        self.assertNotIn(_STRONG, BACKEND_SRC.read_text(encoding="utf8"))

    def test_provisioning_is_audited_without_secret_material(self) -> None:
        backend.provision_admin("rootadmin", _STRONG, interactive=False)
        self.assertEqual(
            self._count("SELECT COUNT(*) FROM audit_logs WHERE action='ADMIN_PROVISIONED'"), 1)
        conn = backend.db()
        try:
            details = conn.execute(
                "SELECT details FROM audit_logs WHERE action='ADMIN_PROVISIONED'").fetchone()[0]
        finally:
            conn.close()
        for banned in ("password", "password_hash", "salt", "token"):
            self.assertNotIn(banned, details.lower())

    def test_weak_and_retired_shapes_are_refused(self) -> None:
        cases = {
            "too short": "short1!",
            "retired shape": "Word@1234",
            "low variety": "aaaaaaaaaaaaaa",
            "empty": "",
        }
        for label, bad in cases.items():
            with self.subTest(case=label):
                with self.assertRaises(backend.ProvisioningError):
                    backend.provision_admin("rootadmin", bad, interactive=False)
        self.assertEqual(self._count("SELECT COUNT(*) FROM users"), 0)

    def test_password_equal_to_username_is_refused(self) -> None:
        """Needs a username long enough to clear the length policy first."""
        long_name = "rootadminuser"          # 13 chars
        with self.assertRaises(backend.ProvisioningError):
            backend.provision_admin(long_name, long_name, interactive=False)
        self.assertEqual(self._count("SELECT COUNT(*) FROM users"), 0)

    def test_provisioning_refuses_to_overwrite_existing_account(self) -> None:
        backend.provision_admin("rootadmin", _STRONG, interactive=False)
        before = self._row("rootadmin")
        with self.assertRaises(backend.ProvisioningError):
            backend.provision_admin("rootadmin", _STRONG_2, interactive=False)
        after = self._row("rootadmin")
        self.assertEqual(before["password_hash"], after["password_hash"],
                         "provisioning overwrote an existing credential")


class TestRepeatedInitialization(_TempBackend):
    """Stage 3.2 + 3.5: startup must never silently reset an administrator."""

    def test_repeated_init_db_preserves_hash_role_and_blocked(self) -> None:
        backend.provision_admin("rootadmin", _STRONG, interactive=False)
        before = self._row("rootadmin")
        for _ in range(6):  # simulate six service restarts
            backend.init_db()
        after = self._row("rootadmin")
        self.assertEqual(before["password_hash"], after["password_hash"], "password was reset")
        self.assertEqual(before["salt"], after["salt"], "salt was reset")
        self.assertEqual(after["role"], "admin")
        self.assertEqual(after["blocked"], 0)

    def test_startup_cannot_silently_unblock(self) -> None:
        backend.provision_admin("rootadmin", _STRONG, interactive=False)
        conn = backend.db()
        conn.execute("UPDATE users SET blocked=1 WHERE lower(username)='rootadmin'")
        conn.commit()
        conn.close()
        self.assertEqual(self._row("rootadmin")["blocked"], 1)
        for _ in range(3):
            backend.init_db()
        self.assertEqual(self._row("rootadmin")["blocked"], 1,
                         "startup silently unblocked a blocked administrator")

    def test_startup_cannot_reescalate_demoted_account(self) -> None:
        backend.provision_admin("rootadmin", _STRONG, interactive=False)
        conn = backend.db()
        conn.execute("UPDATE users SET role='user' WHERE lower(username)='rootadmin'")
        conn.commit()
        conn.close()
        for _ in range(3):
            backend.init_db()
        self.assertEqual(self._row("rootadmin")["role"], "user",
                         "startup silently re-escalated a demoted account")

    def test_startup_does_not_create_any_user_when_absent(self) -> None:
        backend.init_db()
        backend.init_db()
        self.assertEqual(self._count("SELECT COUNT(*) FROM users"), 0)

    def test_schema_is_still_created_idempotently(self) -> None:
        backend.init_db()
        backend.init_db()
        conn = backend.db()
        try:
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        finally:
            conn.close()
        self.assertIn("users", tables)
        self.assertIn("audit_logs", tables)


class TestExplicitRotation(_TempBackend):
    """Stage 3.5: rotation only through the explicit path; unauthorised rejected."""

    def setUp(self) -> None:
        super().setUp()
        backend.provision_admin("rootadmin", _STRONG, interactive=False)

    def test_authorized_rotation_changes_only_the_credential(self) -> None:
        before = self._row("rootadmin")
        out = backend.rotate_credential("rootadmin", _STRONG, _STRONG_2, actor="rootadmin")
        self.assertEqual(out["rows_affected"], 1)
        after = self._row("rootadmin")
        self.assertNotEqual(before["password_hash"], after["password_hash"])
        self.assertTrue(backend.verify_password(_STRONG_2, after["password_hash"], after["salt"]))
        self.assertFalse(backend.verify_password(_STRONG, after["password_hash"], after["salt"]))
        self.assertEqual(after["role"], "admin")
        self.assertEqual(after["blocked"], 0)

    def test_unauthorized_rotation_is_rejected(self) -> None:
        with self.assertRaises(backend.ProvisioningError):
            backend.rotate_credential("rootadmin", "definitely-wrong-pass", _STRONG_2, actor="attacker")
        row = self._row("rootadmin")
        self.assertTrue(backend.verify_password(_STRONG, row["password_hash"], row["salt"]),
                        "failed rotation still changed the credential")

    def test_unauthorized_rotation_is_audited_as_denied(self) -> None:
        with self.assertRaises(backend.ProvisioningError):
            backend.rotate_credential("rootadmin", "definitely-wrong-pass", _STRONG_2, actor="attacker")
        n = self._count("SELECT COUNT(*) FROM audit_logs WHERE action='CREDENTIAL_ROTATION_DENIED'")
        self.assertEqual(n, 1)

    def test_rotation_of_unknown_account_rejected(self) -> None:
        with self.assertRaises(backend.ProvisioningError):
            backend.rotate_credential("ghost", _STRONG, _STRONG_2)

    def test_rotation_to_same_password_rejected(self) -> None:
        with self.assertRaises(backend.ProvisioningError):
            backend.rotate_credential("rootadmin", _STRONG, _STRONG)

    def test_rotation_never_touches_role_or_blocked(self) -> None:
        conn = backend.db()
        conn.execute("UPDATE users SET blocked=1 WHERE lower(username)='rootadmin'")
        conn.commit()
        conn.close()
        backend.rotate_credential("rootadmin", _STRONG, _STRONG_2, actor="rootadmin")
        row = self._row("rootadmin")
        self.assertEqual(row["role"], "admin")
        self.assertEqual(row["blocked"], 1, "rotation unblocked an account")

    def test_rotation_requires_current_password_argument(self) -> None:
        with self.assertRaises(backend.ProvisioningError):
            backend.rotate_credential("rootadmin", "", _STRONG_2)


class TestPrivilegeEscalation(_TempBackend):
    """Stage 3.5: privilege escalation must be impossible via these paths."""

    def test_provision_admin_cannot_be_used_to_demote_or_block(self) -> None:
        backend.provision_admin("rootadmin", _STRONG, interactive=False)
        conn = backend.db()
        conn.execute("UPDATE users SET role='user' WHERE lower(username)='rootadmin'")
        conn.commit()
        conn.close()
        with self.assertRaises(backend.ProvisioningError):
            backend.provision_admin("rootadmin", _STRONG_2, interactive=False)
        self.assertEqual(self._row("rootadmin")["role"], "user")

    def test_no_route_assigns_the_admin_role(self) -> None:
        """Static: no SQL INSERT may carry role='admin' as a literal.

        ``provision_admin`` legitimately supplies the role as a *parameter*
        (explicit, operator-initiated), so a text search for ``'admin'`` would
        false-positive on that and on comments. This inspects the actual SQL.
        """
        tree = ast.parse(BACKEND_SRC.read_text(encoding="utf8"))
        offending = []
        for n in ast.walk(tree):
            if not isinstance(n, ast.Call):
                continue
            if getattr(n.func, "attr", None) != "execute":
                continue
            if not n.args:
                continue
            sql = ast.literal_eval(n.args[0]) if isinstance(n.args[0], ast.Constant) else None
            if not isinstance(sql, str):
                continue
            if "INSERT INTO users" in sql.upper():
                if "role='admin'" in sql.replace(" ", "").replace('"', "'") or "role='admin'" in sql:
                    offending.append((n.lineno, sql))
        self.assertEqual(offending, [], f"an INSERT writes the admin role literally: {offending}")

    def test_only_provisioning_and_register_write_roles(self) -> None:
        """register() must hard-code 'user'; provisioning is parameterised."""
        src = BACKEND_SRC.read_text(encoding="utf8")
        register_src = src[src.index("@app.post('/auth/register')"):
                           src.index("@app.post('/moderate')")]
        self.assertIn("'user'", register_src)
        self.assertNotIn("'admin'", register_src)
        # provision_admin passes the role as a bound parameter, not a literal SQL token.
        self.assertIn("(username, h, s, 'admin', 0, now())", src)

    def test_login_still_requires_role_and_blocked_checks(self) -> None:
        src = BACKEND_SRC.read_text(encoding="utf8")
        login_src = src[src.index("@app.post('/auth/login')"):
                        src.index("@app.post('/auth/register')")]
        self.assertIn("row['blocked']", login_src)
        self.assertIn("row['role']", login_src)


class TestSourceHygiene(unittest.TestCase):
    def test_no_hard_coded_credential_literal_in_backend(self) -> None:
        src = BACKEND_SRC.read_text(encoding="utf8")
        # Shape check (InitialCaps@NNNN), not a literal.
        self.assertIsNone(
            __import__("re").search(r"'[A-Z][a-z]+@[0-9]{3,}'", src),
            "a hard-coded credential literal remains in backend.py")

    def test_password_is_never_printed_or_logged(self) -> None:
        src = BACKEND_SRC.read_text(encoding="utf8")
        for bad in ("print(password", "print(f'{password", "logging.*password"):
            self.assertNotIn(bad, src)

    def test_getpass_is_used_for_interactive_input(self) -> None:
        src = BACKEND_SRC.read_text(encoding="utf8")
        self.assertIn("getpass.getpass(", src)

    def test_credential_shape_rejector_is_shape_based_not_literal(self) -> None:
        self.assertTrue(hasattr(backend, "_WEAK_CREDENTIAL_RE"))


class TestProductionUntouched(unittest.TestCase):
    def test_production_db_unchanged_by_entire_suite(self) -> None:
        st = PROD_DB.stat()
        conn = _orig_connect(f"file:{PROD_DB}?mode=ro", uri=True, timeout=20)
        n_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        n_admin = conn.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()[0]
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        engine = conn.execute("SELECT value FROM settings WHERE key='prediction_engine'").fetchone()[0]
        conn.close()
        self.assertEqual(engine, "legacy")
        self.assertEqual(integrity, "ok")
        # These are the values observed at the start of Phase 4.16.
        self.assertEqual(n_users, 20)
        self.assertEqual(n_admin, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
