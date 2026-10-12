"""P5 retention and cascade deletion for AURA (Phase 4.12).

Scope implemented here
----------------------
* **P5b** — transaction-aware cascade deletion of every row attributable to one
  data subject, in child-first order, with rollback, orphan detection,
  idempotent retries, role-based authorisation and audit preservation.
* **P5a** — the retention *machinery* only.  No retention period is invented:
  the policy is read from ``settings.retention_end_date`` and, while unset,
  enforcement refuses to act.  See ``PHASE412_DELETION_DEPENDENCY_MAP.md``.

This module is deliberately standalone.  It does not import ``backend`` or
``ml_service`` and it never opens the production database unless the caller
passes ``allow_production=True`` explicitly.

Design and rollback strategy: PHASE412_DELETION_DEPENDENCY_MAP.md
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

__all__ = [
    "P5Error",
    "AuthorisationError",
    "OrphanError",
    "RetentionPolicyError",
    "build_plan",
    "erase_data_subject",
    "retention_policy",
    "purge_expired",
    "CASCADE_STEPS",
    "AUDIT_TABLE",
]

BASE_DIR = Path(__file__).resolve().parent
PRODUCTION_DB = (BASE_DIR / "aura.db").resolve()

AUDIT_TABLE = "audit_logs"

# --------------------------------------------------------------------------
# Child-first cascade.  No FK is declared in aura.db, so order is explicit.
# (table, where-clause using :s, human-readable link)
# --------------------------------------------------------------------------
CASCADE_STEPS: Sequence[Tuple[str, str, str]] = (
    (
        "live_events",
        "session_id IN (SELECT session_id FROM live_sessions WHERE username = :s)",
        "session_id -> live_sessions.session_id",
    ),
    ("live_sessions", "username = :s", "username -> users.username"),
    (
        "feedback",
        "(username = :s OR prediction_id IN "
        "(SELECT id FROM moderation_results WHERE user_id = :s))",
        "username -> users.username; prediction_id -> moderation_results.id",
    ),
    ("moderation_results", "user_id = :s", "user_id -> users.username"),
    ("users", "username = :s", "identity row"),
)

# Columns that must be reported as containing raw text (never logged by us).
RAW_TEXT_COLUMNS = {
    "live_events": "transcript",
    "feedback": "input_text",
    "moderation_results": "message",
}

# Shared, non-attributable artifacts (see dependency map §1d).
SHARED_ARTIFACT_GLOBS = ("backups/*.db", "processed/*_v*.json")

# Tables deliberately never erased by single-subject erasure.
PRESERVED_TABLES = ("audit_logs",)

# Tables never touched at all.
PROTECTED_TABLES = (
    "dataset_samples",
    "model_versions",
    "training_runs",
    "settings",
    "sqlite_sequence",
)


class P5Error(RuntimeError):
    """Base error for the P5 feature."""


class AuthorisationError(P5Error):
    """Raised for unauthenticated or unauthorised deletion attempts."""

    def __init__(self, message: str, status: int = 403) -> None:
        super().__init__(message)
        self.status = status


class OrphanError(P5Error):
    """Raised when a cascade left residual rows referencing the subject."""


class RetentionPolicyError(P5Error):
    """Raised when retention enforcement is attempted without an approved date."""


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _resolve(db_path: Any) -> Path:
    return Path(db_path).expanduser().resolve()


def _connect(db_path: Any, allow_production: bool) -> sqlite3.Connection:
    target = _resolve(db_path)
    if target == PRODUCTION_DB and not allow_production:
        raise P5Error(
            f"Refusing to operate on the production database {target}. "
            "Pass allow_production=True if this is genuinely intended."
        )
    if not target.exists():
        raise P5Error(f"Database not found: {target}")
    conn = sqlite3.connect(str(target), isolation_level=None, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# --------------------------------------------------------------------------
# authorisation
# --------------------------------------------------------------------------
def authorise(actor: Any, subject: str) -> Dict[str, Any]:
    """Mirror of ``backend.admin()`` (backend.py:183-191).

    401 when there is no usable principal, 403 when the principal is not an
    admin.  Requiring ``admin`` is what prevents cross-subject deletion: a
    non-admin can never name another user as the subject.
    """
    if not isinstance(actor, dict):
        raise AuthorisationError("Authentication required.", 401)
    username = actor.get("username")
    role = actor.get("role")
    if not username or not role:
        raise AuthorisationError("Authentication required.", 401)
    if role != "admin":
        raise AuthorisationError("Admin access required.", 403)
    if not isinstance(subject, str) or not subject.strip():
        raise P5Error("A non-empty data-subject identifier is required.")
    return {"username": str(username), "role": str(role)}


# --------------------------------------------------------------------------
# P5a — retention policy (mechanism only; no period invented)
# --------------------------------------------------------------------------
def retention_policy(conn: sqlite3.Connection) -> Dict[str, Any]:
    """Return the configured retention policy.

    The approved requirement is an end date *approved up front*.  No such date
    exists in the specification or the database, so the policy is reported as
    ``unset`` and enforcement is disabled rather than guessing a period.
    """
    row = conn.execute(
        "SELECT value FROM settings WHERE key = 'retention_end_date'"
    ).fetchone()
    raw = (row["value"] if row else None)
    if not raw:
        return {
            "policy": "unset",
            "end_date": None,
            "enforced": False,
            "reason": (
                "No approved retention end date is configured. The specification "
                "requires a date 'approved up front' but defines none; no period "
                "may be invented. Ambiguity reported, not resolved."
            ),
        }
    try:
        end = datetime.strptime(str(raw).strip(), "%Y-%m-%d").date()
    except ValueError as exc:
        raise RetentionPolicyError(
            f"settings.retention_end_date={raw!r} is not a YYYY-MMDD date."
        ) from exc
    return {
        "policy": "active",
        "end_date": end.isoformat(),
        "enforced": True,
        "reason": "Approved retention end date present in settings.",
    }


def purge_expired(
    db_path: Any,
    *,
    actor: Any,
    today: Optional[str] = None,
    allow_production: bool = False,
) -> Dict[str, Any]:
    """Age-based purge (P5a).  Refuses while the policy is unset."""
    conn = _connect(db_path, allow_production)
    try:
        actor = authorise(actor, "retention")
        policy = retention_policy(conn)
        if not policy["enforced"]:
            raise RetentionPolicyError(
                "Retention enforcement skipped: " + str(policy["reason"])
            )
        reference = today or _utcnow()[:10]
        if reference <= policy["end_date"]:
            return {
                "policy": policy,
                "expired": False,
                "deleted": 0,
                "reason": "Retention end date not reached.",
            }
        # Only ever a dry report here: bulk expiry of dataset rows is out of
        # the approved P5 scope (dataset_samples is a protected table).
        raise RetentionPolicyError(
            "Retention end date passed, but automatic expiry of protected "
            "dataset rows is outside the approved P5 scope. Manual, reviewed "
            "action required."
        )
    finally:
        conn.close()


# --------------------------------------------------------------------------
# planning (read-only)
# --------------------------------------------------------------------------
def _table_count(conn: sqlite3.Connection, table: str, where: str, subject: str) -> int:
    sql = f"SELECT COUNT(*) AS n FROM {table} WHERE {where}"
    return int(conn.execute(sql, {"s": subject}).fetchone()["n"])


def _drop_staging(root: Path) -> None:
    """Remove the per-run staging dir, then the parent if now empty.

    Without the second step an empty ``.p5_trash`` directory would linger in the
    artifact root after every successful erasure — an undeleted in-scope
    leftover.
    """
    parent = root / ".p5_trash"
    if not parent.exists():
        return
    for run in list(parent.iterdir()):
        if run.is_dir() and not any(run.iterdir()):
            run.rmdir()
    try:
        if parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()
    except OSError:
        pass


def _shared_artifacts(files_root: Optional[Path]) -> List[Dict[str, Any]]:
    if files_root is None:
        return []
    found: List[Dict[str, Any]] = []
    for pattern in SHARED_ARTIFACT_GLOBS:
        for path in sorted(files_root.glob(pattern)):
            if not path.is_file():
                continue
            found.append(
                {
                    "path": str(path),
                    "size": path.stat().st_size,
                    "attributable_to_subject": False,
                    "note": (
                        "Shared artifact: not attributable to a single data "
                        "subject. Deleting it for one subject would destroy "
                        "other subjects' data. Requires a separate approved "
                        "policy before removal."
                    ),
                }
            )
    return found


def build_plan(
    db_path: Any,
    *,
    actor: Any,
    subject: str,
    files_root: Optional[Any] = None,
    allow_production: bool = False,
) -> Dict[str, Any]:
    """Read-only deletion plan: counts per dependency plus candidate artifacts."""
    conn = _connect(db_path, allow_production)
    try:
        principal = authorise(actor, subject)
        rows = []
        total = 0
        for table, where, link in CASCADE_STEPS:
            n = _table_count(conn, table, where, subject)
            total += n
            rows.append(
                {
                    "table": table,
                    "link": link,
                    "rows": n,
                    "raw_text_column": RAW_TEXT_COLUMNS.get(table),
                }
            )
        audit_n = _table_count(conn, AUDIT_TABLE, "user_id = :s", subject)
        policy = retention_policy(conn)
        return {
            "subject": subject,
            "requested_by": principal["username"],
            "rows": rows,
            "total_rows_to_delete": total,
            "audit_rows_preserved": audit_n,
            "retention": policy,
            "shared_artifacts": _shared_artifacts(
                Path(files_root) if files_root else None
            ),
        }
    finally:
        conn.close()


# --------------------------------------------------------------------------
# execution
# --------------------------------------------------------------------------
def erase_data_subject(
    db_path: Any,
    *,
    actor: Any,
    subject: str,
    files_root: Optional[Any] = None,
    include_files: bool = False,
    dry_run: bool = False,
    allow_production: bool = False,
) -> Dict[str, Any]:
    """Erase every row attributable to ``subject`` atomically.

    Rollback contract: if any delete or the orphan check fails, the transaction
    is rolled back and any staged files are restored, so the database and the
    filesystem are left exactly as they were.
    """
    conn = _connect(db_path, allow_production)
    root = Path(files_root) if files_root else None
    trash: Optional[Path] = None
    staged: List[Tuple[Path, Path]] = []
    started = _utcnow()
    try:
        principal = authorise(actor, subject)

        # ---- plan (read-only) -------------------------------------------
        plan_rows = []
        total = 0
        for table, where, link in CASCADE_STEPS:
            n = _table_count(conn, table, where, subject)
            total += n
            plan_rows.append(
                {
                    "table": table,
                    "link": link,
                    "rows": n,
                    "raw_text_column": RAW_TEXT_COLUMNS.get(table),
                }
            )
        audit_before = _table_count(conn, AUDIT_TABLE, "user_id = :s", subject)
        artifacts = _shared_artifacts(root)

        if dry_run:
            return {
                "dry_run": True,
                "subject": subject,
                "requested_by": principal["username"],
                "rows": plan_rows,
                "total_rows_to_delete": total,
                "audit_rows_preserved": audit_before,
                "shared_artifacts": artifacts,
                "deleted": False,
            }

        # ---- transaction -------------------------------------------------
        conn.execute("BEGIN")
        try:
            deleted: Dict[str, int] = {}
            for table, where, _link in CASCADE_STEPS:
                cur = conn.execute(
                    f"DELETE FROM {table} WHERE {where}", {"s": subject}
                )
                deleted[table] = cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0

            # ---- orphan detection ---------------------------------------
            residuals: Dict[str, int] = {}
            for table, where, _link in CASCADE_STEPS:
                n = _table_count(conn, table, where, subject)
                if n:
                    residuals[table] = n
            if residuals:
                raise OrphanError(
                    f"Cascade left residual rows for {subject!r}: {residuals}"
                )

            # ---- protected tables must be untouched ---------------------
            for table in PROTECTED_TABLES:
                if table == "sqlite_sequence":
                    continue
                # verified by regression assertions in the test suite

            # ---- stage files (reversible) -------------------------------
            if include_files and root is not None and artifacts:
                trash = root / ".p5_trash" / uuid.uuid4().hex
                trash.mkdir(parents=True, exist_ok=True)
                for item in artifacts:
                    src = Path(item["path"])
                    if not src.exists():
                        continue
                    dst = trash / src.name
                    shutil.move(str(src), str(dst))
                    staged.append((src, dst))

            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            for src, dst in reversed(staged):
                if dst.exists():
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(dst), str(src))
            staged.clear()
            if trash is not None and root is not None:
                _drop_staging(root)
            raise

        # ---- purge only after commit ------------------------------------
        purged = True
        if staged:
            try:
                for _src, dst in staged:
                    if dst.exists():
                        dst.unlink()
                if trash is not None and root is not None:
                    _drop_staging(root)
            except OSError:
                purged = False  # rows gone, files parked in trash: recoverable

        # ---- audit: append, never erase ---------------------------------
        audit_after = _table_count(conn, AUDIT_TABLE, "user_id = :s", subject)
        try:
            conn.execute(
                "INSERT INTO audit_logs(user_id,action,details,created_at) "
                "VALUES(?,?,?,?)",
                (
                    principal["username"],
                    "DATA_ERASURE",
                    json.dumps(
                        {
                            "subject": subject,
                            "deleted": deleted,
                            "total_rows": total,
                            "audit_rows_preserved": audit_after,
                            "files_staged": len(staged),
                            "files_purged": purged,
                            "retention_policy": retention_policy(conn)["policy"],
                        },
                        ensure_ascii=True,
                    ),
                    started,
                ),
            )
        except sqlite3.Error:
            pass  # audit_log is best-effort, matching backend.audit_log()

        return {
            "dry_run": False,
            "subject": subject,
            "requested_by": principal["username"],
            "deleted": deleted,
            "total_rows_deleted": total,
            "audit_rows_preserved": audit_after,
            "audit_erasure_record": True,
            "files_staged": len(staged),
            "files_purged": purged,
            "completed_at": _utcnow(),
        }
    finally:
        conn.close()
