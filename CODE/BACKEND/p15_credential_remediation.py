"""P15 — proposed startup & credential-remediation policy (AURA Phase 4.15).

**Isolated additive prototype.** Imports neither ``backend`` nor any application
module, opens no production file, and requires **no authorization to run**
because it only operates on connections handed to it.

Why this exists
---------------
``backend.py:166-172`` (``init_db``) does not merely *seed* an admin: when the
account already exists it **unconditionally overwrites** ``password_hash``,
``salt``, ``role='admin'`` **and ``blocked=0``** on every start-up. Because
``init_db()`` is invoked at **module scope** (``backend.py:1088``, no
``if __name__ == '__main__'`` guard), that rewrite executes on **every import**
as well as every process start.

Consequences proven by this design:
* any password the operator sets is **silently reverted** on restart;
* a **blocked** admin is **unblocked** on restart;
* a single known credential is therefore **permanent and self-healing**.

This module specifies the *corrected* semantics — **seed-once, never overwrite** —
plus an explicit, audited rotation path. It is a proposal, not a change to
production code.

Safety properties
-----------------
* no hard-coded password literal anywhere in this module;
* no ``backend`` import (importing ``backend`` executes ``init_db()`` against
  the production DB — see ``detect_startup_reseed`` notes);
* no network, no dataset, no model, no frozen artifact;
* every function takes an explicit connection, so tests run on temp DBs.
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

__all__ = [
    "STARTUP_POLICY_VERSION",
    "PBKDF2_ITERATIONS",
    "hash_password",
    "verify_password",
    "ensure_admin_account",
    "rotate_password",
    "set_blocked",
    "record_audit",
    "detect_startup_reseed",
    "StartupPolicy",
    "AuditNotWritten",
]

STARTUP_POLICY_VERSION = "1.0.0"
# Mirrors backend.py:162 so rotation semantics are comparable — parameters are
# copied, the function is NOT imported.
PBKDF2_ITERATIONS = 150_000


class StartupPolicy(ValueError):
    """Raised when a caller attempts an operation the policy forbids."""


class AuditNotWritten(RuntimeError):
    """Raised when an audited operation cannot record its audit row."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------
# Password primitives (same parameters as backend.py:162, reimplemented so no
# application import is required)
# --------------------------------------------------------------------------
def hash_password(password: str, salt: Optional[str] = None) -> Tuple[str, str]:
    """PBKDF2-HMAC-SHA256, 150k iterations, per-call random salt."""
    if not isinstance(password, str) or not password:
        raise StartupPolicy("A non-empty password is required.")
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), PBKDF2_ITERATIONS)
    return digest.hex(), salt


def verify_password(password: str, stored_hash: str, salt: str) -> bool:
    """Constant-time comparison."""
    return secrets.compare_digest(hash_password(password, salt)[0], stored_hash)


# --------------------------------------------------------------------------
# Audit (counts/metadata only — never a password, hash, salt or token)
# --------------------------------------------------------------------------
def record_audit(conn, user_id: Optional[str], action: str, details: Dict[str, Any]) -> None:
    """Append an audit row. Refuses to serialise secret-bearing keys."""
    banned = {"password", "password_hash", "salt", "token", "secret", "key"}
    leaked = banned & {str(k).lower() for k in details}
    if leaked:
        raise AuditNotWritten(f"Refusing to audit secret-bearing keys: {sorted(leaked)}")
    conn.execute(
        "INSERT INTO audit_logs(user_id,action,details,created_at) VALUES(?,?,?,?)",
        (user_id, action, json.dumps(details, ensure_ascii=True), _utc_now()),
    )


# --------------------------------------------------------------------------
# PROPOSED STARTUP BEHAVIOUR — seed once, never overwrite
# --------------------------------------------------------------------------
def ensure_admin_account(
    conn,
    username: str = "admin",
    password_factory: Optional[Callable[[], str]] = None,
    role: str = "admin",
) -> Dict[str, Any]:
    """Create the admin account **only if absent**.

    Deliberately does **NOT**:
      * rewrite ``password_hash`` / ``salt`` when the row exists;
      * reset ``blocked`` back to 0;
      * force ``role`` to admin on an existing row.

    ``password_factory`` supplies the initial secret at creation time only; it
    is never called when the account already exists, so a rotating factory
    cannot accidentally change a live password.
    """
    if not username or not username.strip():
        raise StartupPolicy("username is required.")
    row = conn.execute(
        "SELECT id,role,blocked FROM users WHERE lower(username)=lower(?)", (username.strip(),)
    ).fetchone()
    if row:
        return {
            "action": "preserved",
            "policy_version": STARTUP_POLICY_VERSION,
            "user_id": row[0],
            "role": row[1],
            "blocked": row[2],
            "password_changed": False,
            "blocked_reset": False,
        }
    factory = password_factory or (lambda: secrets.token_urlsafe(24))
    secret = factory()
    digest, salt = hash_password(secret)
    conn.execute(
        "INSERT INTO users(username,password_hash,salt,role,blocked,created_at) VALUES(?,?,?,?,?,?)",
        (username.strip(), digest, salt, role, 0, _utc_now()),
    )
    record_audit(conn, username.strip(), "ADMIN_SEEDED", {"role": role, "policy_version": STARTUP_POLICY_VERSION})
    return {
        "action": "created",
        "policy_version": STARTUP_POLICY_VERSION,
        "role": role,
        "blocked": 0,
        "password_changed": True,
        "blocked_reset": False,
    }


def rotate_password(conn, username: str, new_password: str, actor: str) -> Dict[str, Any]:
    """Explicit, audited password rotation — the ONLY sanctioned path.

    Never touches ``role`` or ``blocked``: rotation is not authorisation.
    """
    row = conn.execute("SELECT id FROM users WHERE lower(username)=lower(?)", (username.strip(),)).fetchone()
    if not row:
        raise StartupPolicy(f"No such account: {username!r}")
    digest, salt = hash_password(new_password)
    cur = conn.execute(
        "UPDATE users SET password_hash=?, salt=? WHERE lower(username)=lower(?)",
        (digest, salt, username.strip()),
    )
    record_audit(
        conn,
        actor,
        "PASSWORD_ROTATION",
        {"target_user_id": row[0], "rows_affected": cur.rowcount, "policy_version": STARTUP_POLICY_VERSION},
    )
    return {"action": "rotated", "target_user_id": row[0], "rows_affected": cur.rowcount}


def set_blocked(conn, username: str, blocked: bool, actor: str) -> Dict[str, Any]:
    """Explicit block/unblock — audited, and NOT undone by start-up."""
    row = conn.execute("SELECT id,blocked FROM users WHERE lower(username)=lower(?)", (username.strip(),)).fetchone()
    if not row:
        raise StartupPolicy(f"No such account: {username!r}")
    cur = conn.execute(
        "UPDATE users SET blocked=? WHERE lower(username)=lower(?)", (1 if blocked else 0, username.strip())
    )
    record_audit(
        conn,
        actor,
        "ADMIN_BLOCK" if blocked else "ADMIN_UNBLOCK",
        {"target_user_id": row[0], "previous": row[1], "rows_affected": cur.rowcount},
    )
    return {"action": "blocked" if blocked else "unblocked", "target_user_id": row[0], "rows_affected": cur.rowcount}


# --------------------------------------------------------------------------
# STATIC detector — proves the defective pattern without executing it
# --------------------------------------------------------------------------
_UPDATE_RE = re.compile(r"UPDATE\s+users\s+SET", re.IGNORECASE)
_SECRET_RESET_RE = re.compile(
    r"UPDATE\s+users\s+SET[^;\n]*password_hash", re.IGNORECASE | re.DOTALL
)
_DEF_RE = re.compile(r"^(?:def |@app\.|class )", re.MULTILINE)


def detect_startup_reseed(source_text: str) -> List[Dict[str, Any]]:
    """Statically detect **start-up** rewrites of credential columns.

    Scans for ``UPDATE users SET …password_hash`` statements and classifies each
    by enclosing scope. A hit inside ``init_db`` (or any module-level scope) is
    the defect: a *start-up* path must never rewrite credentials.

    Text-only analysis — no import, no execution, no production write.
    """
    findings: List[Dict[str, Any]] = []
    lines = source_text.splitlines()
    # Build a scope map. A scope is a *start-up* path only when it runs
    # automatically when the application starts: module scope, init_db(), the
    # ASGI startup hook, or a function decorated with on_event. Routes, CLI
    # helpers and explicitly-invoked operator functions are NOT start-up paths,
    # even though they may rewrite a credential deliberately.
    scope: List[str] = ["<module>"]
    decorators: Dict[str, List[str]] = {}
    current = "<module>"
    pending_decorator: Optional[str] = None
    for line in lines:
        if line.startswith("@"):
            pending_decorator = line.strip()
        elif line.startswith("def "):
            name = line.split("(")[0].replace("def ", "").strip()
            current = name
            decorators[name] = [pending_decorator] if pending_decorator else []
            pending_decorator = None
        elif line.startswith("class "):
            current = line.split("(")[0].replace("class ", "").strip()
            decorators[current] = [pending_decorator] if pending_decorator else []
            pending_decorator = None
        elif line.startswith(" ") or line.startswith("\t"):
            pass  # still inside the current scope
        elif line.strip() and not line.startswith("#"):
            current = "<module>"
            pending_decorator = None
        scope.append(current)

    def _is_start_up(scope_name: str) -> bool:
        if scope_name in ("<module>", "<module-scope>", "init_db", "startup"):
            return True
        # ASGI lifecycle hooks execute automatically at start-up.
        return any("on_event" in d for d in decorators.get(scope_name, []))

    for match in _SECRET_RESET_RE.finditer(source_text):
        line_no = source_text[: match.start()].count("\n") + 1
        enclosing = scope[line_no] if line_no < len(scope) else "<unknown>"
        findings.append(
            {
                "line": line_no,
                "scope": enclosing,
                "rewrites_password": True,
                "is_start_up_path": _is_start_up(enclosing),
                "snippet_shape": "UPDATE users SET ... password_hash ...",
            }
        )
    return findings
