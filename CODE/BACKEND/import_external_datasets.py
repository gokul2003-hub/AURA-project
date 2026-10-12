"""Safe, idempotent, transactional importer for the Phase 1 external datasets.

Imports the prepared Civil Comments / Wiki Toxic rows in
``data/external/*.csv`` into the SQLite ``dataset_samples`` table.

Safety rules (Phase 3):
  * **Dry run by default** — nothing is written unless ``--apply`` is passed.
  * **Additive only** — the importer NEVER issues DELETE / UPDATE /
    REPLACE on existing rows. It only INSERTs new ones.
  * **Schema-validated** — a source file whose header does not match the
    expected schema aborts the whole run before the transaction opens.
  * **Label-validated** — every label must parse to exactly 0 or 1.
  * **Language-scoped** — only languages AURA can actually detect and score
    are imported; others are *rejected with a reason* (never silently
    mislabelled as English).
  * **Deduplicated** — against existing DB rows, within the file, and across
    files (normalised whitespace + casefold).
  * **Idempotent** — the original dataset row id is preserved in the new
    ``external_id`` column behind a partial UNIQUE index, so re-running
    imports 0 rows instead of duplicating.
  * **Transactional** — one BEGIN IMMEDIATE ... COMMIT; any error rolls the
    whole batch back.
  * **Audited** — every run writes ``data/external/import_report.json``
    (path overridable via ``--report``) with inserted / skipped / rejected
    counts, per-reason rejection tallies, file SHA-256 digests, and
    before/after table counts.

Column mapping (external CSV -> dataset_samples):
    id            -> external_id   (new column, provenance)
    text          -> comment
    toxic, severe_toxic, obscene, threat, insult, identity_hate -> same names
    language/language_name/script                             -> same names
    source        -> source        (normalised: ':' is invalid in AURA's
                                     DATASET_SOURCE_RE, so 'external:civil_comments'
                                     is stored as 'external_civil')
    split         -> (not imported; AURA's deterministic splitter owns it)

Usage:
    python import_external_datasets.py                # dry run (default)
    python import_external_datasets.py --apply        # real import
    python import_external_datasets.py --apply --limit 50
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "aura.db"
EXTERNAL_DIR = BASE_DIR / "data" / "external"
REPORT_PATH = EXTERNAL_DIR / "import_report.json"
BACKUP_DIR = BASE_DIR / "data" / "backups"

EXPECTED_COLUMNS = [
    "id", "text", "language", "language_name", "script",
    "toxic", "severe_toxic", "obscene", "threat", "insult", "identity_hate",
    "source", "split",
]
LABELS = ["toxic", "severe_toxic", "obscene", "threat", "insult", "identity_hate"]

# Languages AURA can detect with mlexicon and score. Anything else would be
# labelled 'und' (or misread as English) at prediction time, so it is rejected
# rather than imported as a mislabelled training row.
SUPPORTED_LANGUAGES = {
    "en", "ta", "ta-Latn", "hi", "te", "ml", "kn", "bn", "mr", "gu", "pa", "ur",
}
MAX_TEXT_CHARS = 20000

SOURCE_FILES = [
    ("civil_comments.csv", "external_civil"),
    ("wiki_toxic.csv", "external_wiki"),
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def norm_text(text: str) -> str:
    """Dedupe key: collapsed whitespace + casefold (mirrors ml_service)."""
    return re.sub(r"\s+", " ", (text or "").strip()).casefold()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_label(value: str):
    """Return 0/1, or raise ValueError for anything not a clean binary label."""
    text = (value or "").strip()
    if text in ("0", "0.0"):
        return 0
    if text in ("1", "1.0"):
        return 1
    raise ValueError(f"label not binary: {value!r}")


def read_source(path: Path, source_tag: str, stats: Counter):
    """Parse + validate one CSV into (rows, rejects)."""
    rows, rejects = [], []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        header = reader.fieldnames or []
        missing = [c for c in EXPECTED_COLUMNS if c not in header]
        if missing:
            raise SystemExit(
                f"ABORT {path.name}: schema mismatch, missing columns {missing}. "
                "Fix the file or the importer before importing."
            )
        for lineno, raw in enumerate(reader, start=2):
            stats["read"] += 1
            text = (raw.get("text") or "").strip()
            if not text:
                rejects.append({"file": path.name, "line": lineno,
                                "reason": "empty_text", "preview": ""})
                stats["reject_empty_text"] += 1
                continue
            if len(text) > MAX_TEXT_CHARS:
                rejects.append({"file": path.name, "line": lineno,
                                "reason": "too_long", "preview": text[:80]})
                stats["reject_too_long"] += 1
                continue
            lang = (raw.get("language") or "").strip()
            if lang not in SUPPORTED_LANGUAGES:
                rejects.append({"file": path.name, "line": lineno,
                                "reason": f"unsupported_language:{lang or 'blank'}",
                                "preview": text[:80]})
                stats["reject_unsupported_language"] += 1
                continue
            labels = {}
            bad = None
            for name in LABELS:
                try:
                    labels[name] = parse_label(raw.get(name))
                except ValueError as exc:
                    bad = str(exc)
                    break
            if bad:
                rejects.append({"file": path.name, "line": lineno,
                                "reason": f"bad_label:{bad}", "preview": text[:80]})
                stats["reject_bad_label"] += 1
                continue
            if sum(labels.values()) == 0 and not any(labels.values()):
                pass  # all-zero is a legitimate non_toxic row
            ext_id = (raw.get("id") or "").strip()
            rows.append({
                "external_id": ext_id or f"{source_tag}:{lineno}",
                "comment": text,
                "labels": labels,
                "language": lang,
                "language_name": (raw.get("language_name") or lang).strip() or lang,
                "script": (raw.get("script") or "Unknown").strip() or "Unknown",
                "source": source_tag,
                "origin_source": (raw.get("source") or "").strip(),
                "origin_split": (raw.get("split") or "").strip(),
                "file": path.name,
                "line": lineno,
            })
    return rows, rejects


def ensure_external_id_column(conn: sqlite3.Connection) -> bool:
    """Add the provenance column if absent. Returns True when it was added.

    SQLite ADD COLUMN is additive: existing rows keep their data and read back
    as NULL for the new column.
    """
    cols = {r[1] for r in conn.execute("PRAGMA table_info(dataset_samples)")}
    if "external_id" in cols:
        return False
    conn.execute("ALTER TABLE dataset_samples ADD COLUMN external_id TEXT")
    conn.commit()
    return True


def ensure_idempotency_index(conn: sqlite3.Connection) -> bool:
    """Partial UNIQUE index on external rows: re-import cannot duplicate."""
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_dataset_samples_external_id "
        "ON dataset_samples(external_id) WHERE external_id IS NOT NULL"
    )
    conn.commit()
    return True


def existing_keys(conn: sqlite3.Connection):
    """Return (normalised comments, external_ids) already present."""
    comments = {
        norm_text(row[0])
        for row in conn.execute("SELECT comment FROM dataset_samples")
        if row and row[0]
    }
    try:
        ext_ids = {
            row[0] for row in conn.execute(
                "SELECT external_id FROM dataset_samples WHERE external_id IS NOT NULL"
            )
            if row and row[0]
        }
    except sqlite3.OperationalError:
        ext_ids = set()
    return comments, ext_ids


def backup_db(db_file: Path, backup_dir: Path) -> Path | None:
    """Best-effort pre-import backup (never fatal)."""
    try:
        # Backups live NEXT TO the database being imported. Hard-coding the
        # project directory would pollute it when --db targets another file
        # (tests run the importer against disposable copies).
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        dest = backup_dir / f"aura-pre-external-import-{stamp}.db"
        src = sqlite3.connect(f"file:{db_file}?mode=ro", uri=True, timeout=30)
        dst = sqlite3.connect(str(dest))
        try:
            src.backup(dst)
            dst.commit()
        finally:
            src.close()
            dst.close()
        return dest
    except Exception as exc:  # noqa: BLE001 - backup failure must not abort import
        print(f"WARNING: pre-import backup failed: {exc}")
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true",
                    help="actually write to SQLite (default: dry run)")
    ap.add_argument("--limit", type=int, default=0,
                    help="cap inserted rows per file (0 = no cap)")
    ap.add_argument("--db", default=None,
                    help="target SQLite file (default: aura.db). Used by tests "
                         "against a disposable copy.")
    ap.add_argument("--file", default=None,
                    help="import a single CSV instead of the built-in sources.")
    ap.add_argument("--source-tag", default="external_test",
                    help="source value to store when --file is used.")
    ap.add_argument("--report", default=None,
                    help="override the import-report path (default: "
                         "data/external/import_report.json). Tests and dry "
                         "runs against a disposable --db should pass this so "
                         "they never clobber the real import audit trail.")
    args = ap.parse_args()

    db_path = Path(args.db).resolve() if args.db else DB_PATH

    stats: Counter = Counter()
    rejects: list[dict] = []
    candidates: list[dict] = []

    if not db_path.is_file():
        print(f"ABORT: {db_path} not found")
        return 2

    print("== external dataset import ==")
    print(f"mode      : {'APPLY' if args.apply else 'DRY RUN (no writes)'}")
    print(f"database  : {db_path}")

    if args.file:
        source_files = [(args.file, args.source_tag)]
    else:
        source_files = list(SOURCE_FILES)
    files_meta = []
    for filename, source_tag in source_files:
        path = Path(filename) if os.path.isabs(filename) or os.sep in filename \
            else EXTERNAL_DIR / filename
        if not path.is_file():
            print(f"SKIP  {filename} (not present)")
            continue
        digest = sha256_file(path)
        rows, rej = read_source(path, source_tag, stats)
        rejects.extend(rej)
        candidates.extend(rows)
        files_meta.append({
            "file": filename, "source_tag": source_tag, "sha256": digest,
            "valid_rows": len(rows), "rejected": len(rej),
        })
        print(f"read   {filename}: {len(rows)} valid, {len(rej)} rejected "
              f"(sha256 {digest[:12]}...)")

    # ---- dedup: in-file, then against the live database -------------------
    conn = sqlite3.connect(str(db_path), timeout=60)
    conn.row_factory = sqlite3.Row
    added_column = False
    try:
        if args.apply:
            added_column = ensure_external_id_column(conn)
            ensure_idempotency_index(conn)
        db_before = conn.execute("SELECT COUNT(*) FROM dataset_samples").fetchone()[0]
        db_comments, db_ext_ids = existing_keys(conn)
        try:
            # like-for-like with the post-run check below: rows that were NOT
            # part of this import (no external_id) must be byte-identical.
            pre_existing_sum = conn.execute(
                "SELECT COALESCE(SUM(LENGTH(comment)), 0) FROM dataset_samples "
                "WHERE external_id IS NULL"
            ).fetchone()[0]
        except sqlite3.OperationalError:
            pre_existing_sum = None
    finally:
        conn.close()

    seen_comments = set()
    seen_ext_ids = set()
    to_insert: list[dict] = []
    for row in candidates:
        key = norm_text(row["comment"])
        ext = row["external_id"]
        if ext in db_ext_ids or ext in seen_ext_ids:
            stats["skip_already_imported"] += 1
            continue
        if key in db_comments or key in seen_comments:
            stats["skip_duplicate_text"] += 1
            continue
        seen_comments.add(key)
        seen_ext_ids.add(ext)
        to_insert.append(row)

    if args.limit and args.limit > 0:
        dropped = len(to_insert) - args.limit
        if dropped > 0:
            to_insert = to_insert[:args.limit]
            stats["skipped_by_limit"] = dropped

    inserted = 0
    if args.apply and to_insert:
        backup_dir = (BACKUP_DIR if db_path == DB_PATH
                      else db_path.parent / "backups")
        backup = backup_db(db_path, backup_dir)
        if backup:
            print(f"backup  {backup.name}")
        stamp = now_iso()
        conn = sqlite3.connect(str(db_path), timeout=60)
        try:
            ensure_external_id_column(conn)
            ensure_idempotency_index(conn)
            conn.execute("BEGIN IMMEDIATE")
            insert_columns = (
                ["comment"] + list(LABELS)
                + ["source", "language", "language_name", "script", "split",
                   "external_id", "created_at", "updated_at"]
            )
            placeholders = ",".join("?" * len(insert_columns))
            payload = [
                (
                    row["comment"],
                    *[row["labels"][name] for name in LABELS],
                    row["source"],
                    row["language"], row["language_name"], row["script"],
                    "",              # split: AURA's deterministic splitter owns it
                    row["external_id"],
                    stamp, stamp,
                )
                for row in to_insert
            ]
            assert len(payload[0]) == len(insert_columns), (
                f"column/value mismatch: {len(insert_columns)} columns vs "
                f"{len(payload[0])} values"
            )
            cur = conn.executemany(
                "INSERT INTO dataset_samples (" + ", ".join(insert_columns)
                + ") VALUES (" + placeholders + ")",
                payload,
            )
            inserted = cur.rowcount if cur.rowcount and cur.rowcount > 0 else len(payload)
            conn.commit()
        except Exception as exc:  # noqa: BLE001 - roll back and report honestly
            conn.rollback()
            print(f"IMPORT FAILED, rolled back: {type(exc).__name__}: {exc}")
            raise
        finally:
            conn.close()
        stats["inserted"] = inserted
    elif to_insert:
        stats["would_insert"] = len(to_insert)

    # ---- verification: additive-only + counts -----------------------------
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=60)
    try:
        db_after = conn.execute("SELECT COUNT(*) FROM dataset_samples").fetchone()[0]
        try:
            post_sum = conn.execute(
                "SELECT COALESCE(SUM(LENGTH(comment)), 0) FROM dataset_samples "
                "WHERE external_id IS NULL"
            ).fetchone()[0]
        except sqlite3.OperationalError:
            post_sum = None
        by_source = conn.execute(
            "SELECT source, COUNT(*) FROM dataset_samples GROUP BY source "
            "ORDER BY 2 DESC LIMIT 12"
        ).fetchall()
        ext_rows = 0
        try:
            ext_rows = conn.execute(
                "SELECT COUNT(*) FROM dataset_samples WHERE external_id IS NOT NULL"
            ).fetchone()[0]
        except sqlite3.OperationalError:
            pass
    finally:
        conn.close()

    untouched = (pre_existing_sum is None or post_sum is None
                 or pre_existing_sum == post_sum)

    report = {
        "generated_at": now_iso(),
        "mode": "apply" if args.apply else "dry_run",
        "database": str(db_path),
        "files": files_meta,
        "counts": {
            "read": stats["read"],
            "valid_candidates": len(candidates),
            "inserted": inserted,
            "would_insert": stats["would_insert"],
            "skipped_total": (stats["skip_already_imported"]
                              + stats["skip_duplicate_text"]
                              + stats["skipped_by_limit"]),
            "skip_already_imported": stats["skip_already_imported"],
            "skip_duplicate_text": stats["skip_duplicate_text"],
            "skipped_by_limit": stats["skipped_by_limit"],
            "rejected_total": stats["reject_empty_text"] + stats["reject_too_long"]
                              + stats["reject_unsupported_language"]
                              + stats["reject_bad_label"],
            "reject_empty_text": stats["reject_empty_text"],
            "reject_too_long": stats["reject_too_long"],
            "reject_unsupported_language": stats["reject_unsupported_language"],
            "reject_bad_label": stats["reject_bad_label"],
        },
        "db_rows_before": db_before,
        "db_rows_after": db_after,
        "external_rows_now": ext_rows,
        "external_id_column_added": added_column,
        "pre_existing_rows_untouched": untouched,
        "supported_languages": sorted(SUPPORTED_LANGUAGES),
        "rejects_sample": rejects[:25],
    }
    report_path = Path(args.report).resolve() if args.report else REPORT_PATH
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False),
                           encoding="utf-8")

    print("\n-- counts --")
    for key, value in report["counts"].items():
        if isinstance(value, int):
            print(f"{key:<28} {value}")
    print(f"{'db_rows_before':<28} {db_before}")
    print(f"{'db_rows_after':<28} {db_after}")
    print(f"{'pre_existing_rows_untouched':<28} {untouched}")
    print("by_source:", [(r[0], r[1]) for r in by_source])
    print(f"report -> {report_path}")
    if not args.apply:
        print("\nDRY RUN: nothing was written. Re-run with --apply to import.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
