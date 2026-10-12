"""
ml_service — dataset management + pure-Python ML for AURA comment toxicity.

Imported by ``CODE/BACKEND/backend.py`` as ``import ml_service``.  Standard
library only (csv, json, math, random, re, sqlite3, threading, hashlib,
datetime, pathlib) — no scikit-learn, no torch.

Public API
----------
DATA_DIR / ensure_dirs()
Dataset CRUD .... list_samples, add_sample, update_sample, delete_sample
Stats ........... dataset_stats, class_distribution
Split ........... split_dataset, split_counts        (writes REAL CSVs)
Multilingual ..... ensure_multilingual_seeded        (idempotent, additive)
Training ........ train_model(variant, seed)         (Multinomial Naive Bayes)
Registry ........ register_model_version, list_model_versions
Reporting ....... evaluate_report, compare_models
Jobs ............ start_training, get_job            (daemon thread, non-blocking)

Safety rules honoured by this module
------------------------------------
* Only ``CREATE TABLE IF NOT EXISTS`` is ever issued, plus guarded additive
  ``ALTER TABLE ... ADD COLUMN`` migrations for the language metadata columns;
  existing tables in ``aura.db`` are never dropped, and rows owned by other
  modules are never deleted.
* If the database is locked/busy a clear ``RuntimeError`` is raised; the DB
  is never corrupted.
* Nothing heavy happens at import time — no threads are started, no files are
  written, no DB is touched until a public function is called.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import random
import re
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

__all__ = [
    "DATA_DIR",
    "ensure_dirs",
    "list_samples",
    "add_sample",
    "update_sample",
    "delete_sample",
    "dataset_stats",
    "class_distribution",
    "split_dataset",
    "split_counts",
    "train_model",
    "register_model_version",
    "list_model_versions",
    "evaluate_report",
    "compare_models",
    "start_training",
    "get_job",
    "ensure_multilingual_seeded",
]

# --------------------------------------------------------------------------
# paths / constants (resolved relative to this file)
# --------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
TRAIN_DIR = DATA_DIR / "train"
VALIDATION_DIR = DATA_DIR / "validation"
TEST_DIR = DATA_DIR / "test"

DEMO_CSV = RAW_DIR / "demo_dataset.csv"
SPLIT_META_PATH = PROCESSED_DIR / "split_meta.json"
SEED_MARKER_PATH = PROCESSED_DIR / ".demo_seeded"
TRAIN_CSV = TRAIN_DIR / "train.csv"
VALIDATION_CSV = VALIDATION_DIR / "validation.csv"
TEST_CSV = TEST_DIR / "test.csv"

# multilingual demo data (written by the dataset pipeline; may not exist yet)
MULTILINGUAL_DIR = DATA_DIR / "multilingual"
MULTILINGUAL_CSV = MULTILINGUAL_DIR / "raw" / "multilingual_demo.csv"

DB_PATH = BASE_DIR / "aura.db"

LABELS: Tuple[str, ...] = (
    "toxic",
    "severe_toxic",
    "obscene",
    "threat",
    "insult",
    "identity_hate",
)
CSV_COLUMNS: Tuple[str, ...] = ("comment",) + LABELS + ("source",)
# language metadata columns added to the dataset (additive migration above)
LANG_COLUMNS: Tuple[str, ...] = ("language", "language_name", "script", "split")
# columns written to data/train|validation|test/*.csv (superset of CSV_COLUMNS —
# readers only require CSV_COLUMNS, extra columns are ignored by DictReader)
SPLIT_CSV_COLUMNS: Tuple[str, ...] = ("comment",) + LABELS + (
    "source",
    "language",
    "language_name",
    "script",
    "split",
)
# header of data/multilingual/{train,validation,test}/split.csv
MULTILINGUAL_SPLIT_COLUMNS: Tuple[str, ...] = (
    "id",
    "text",
    "language",
    "language_name",
    "script",
) + LABELS + ("source", "split")
ITEM_COLUMNS: Tuple[str, ...] = ("id", "comment") + LABELS + (
    "source",
    "language",
    "language_name",
    "script",
    "split",
    "created_at",
    "updated_at",
)
UPDATABLE = frozenset(("comment", "source") + LABELS + LANG_COLUMNS)
VARIANTS: Tuple[str, ...] = ("baseline", "improved")

_SPLIT_VALUES: Tuple[str, ...] = ("", "train", "validation", "test")
_LANGUAGE_RE = re.compile(r"^[a-z]{2,3}(-[A-Za-z]{2,4})?$")
_LABEL_FILTERS: Dict[str, int] = {"toxic": 1, "non_toxic": 0}
UNASSIGNED_SPLIT = "unassigned"
DEFAULT_LANGUAGE = "en"
DEFAULT_LANGUAGE_NAME = "English"
DEFAULT_SCRIPT = "Latin"
_MIN_LANGUAGE_EVAL_SAMPLES = 3

_SPLIT_RATIOS = (0.70, 0.15, 0.15)  # train / validation / test
_DB_TIMEOUT_S = 15.0
_TRUE_TOKENS = frozenset(("1", "true"))
_FALSE_TOKENS = frozenset(("0", "false"))
_WORD_RE = re.compile(r"[a-z0-9']+")
_NOT_EVALUATED = "Not evaluated"
_METRIC_KEYS = ("accuracy", "precision", "recall", "f1")
_NOTES = (
    "Metrics measured on the held-out test split; "
    "unmeasured values show Not evaluated."
)

CREATE_SAMPLES_SQL = """
CREATE TABLE IF NOT EXISTS dataset_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    comment TEXT,
    toxic INT,
    severe_toxic INT,
    obscene INT,
    threat INT,
    insult INT,
    identity_hate INT,
    source TEXT DEFAULT 'demo',
    created_at TEXT,
    updated_at TEXT
)
"""
CREATE_MODELS_SQL = """
CREATE TABLE IF NOT EXISTS model_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL,
    dataset_version TEXT,
    training_date TEXT,
    metrics_json TEXT,
    status TEXT,
    path TEXT,
    created_at TEXT
)
"""
_REQUIRED_SAMPLE_COLS = ("id", "comment") + LABELS + (
    "source",
    "created_at",
    "updated_at",
)

# in-memory background-job store
_JOBS: Dict[str, Dict[str, Any]] = {}
_JOBS_LOCK = threading.Lock()

# multilingual seeding state (cheap + idempotent, guarded by flag + quick check)
_MULTILINGUAL_SEEDED = False
_MULTILINGUAL_LOCK = threading.Lock()


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------
def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_dirs() -> None:
    """Create ``data/`` and its raw/processed/train/validation/test subdirs."""
    for path in (DATA_DIR, RAW_DIR, PROCESSED_DIR, TRAIN_DIR, VALIDATION_DIR, TEST_DIR):
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:  # pragma: no cover - defensive
            raise RuntimeError(f"cannot create data directory {path}: {exc}") from exc


def _check_int(value: Any, name: str, minimum: Optional[int] = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer, got {value!r}")
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be >= {minimum}, got {value}")
    return int(value)


def _check_id(value: Any, name: str = "sample_id") -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be an integer id, got {value!r}")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    raise ValueError(f"{name} must be an integer id, got {value!r}")


def _coerce_label(value: Any, name: str) -> int:
    """Accept only 0 / 1 / true / false (bool, int, or their string forms)."""
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, int):
        if value in (0, 1):
            return value
        raise ValueError(f"label '{name}' must be 0 or 1, got {value!r}")
    if isinstance(value, str):
        token = value.strip().lower()
        if token in _TRUE_TOKENS:
            return 1
        if token in _FALSE_TOKENS:
            return 0
        raise ValueError(
            f"label '{name}' must be one of 0, 1, true, false — got {value!r}"
        )
    raise ValueError(
        f"label '{name}' must be one of 0, 1, true, false — got {value!r}"
    )


def _to_int(value: Any) -> int:
    """Best-effort int conversion used on already-validated CSV cells."""
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, int):
        return 1 if value else 0
    if isinstance(value, str):
        return 1 if value.strip().lower() in _TRUE_TOKENS else 0
    return 1 if value else 0


# --------------------------------------------------------------------------
# multilingual metadata validation (optional keyword args only)
# --------------------------------------------------------------------------
def _validate_language(value: Any, name: str = "language") -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string, got {type(value).__name__}")
    code = value.strip()
    if not _LANGUAGE_RE.match(code):
        raise ValueError(
            f"{name} must look like 'en' or 'ta-Latn' "
            f"(^[a-z]{{2,3}}(-[A-Za-z]{{2,4}})?$), got {value!r}"
        )
    return code


def _validate_split(value: Any, name: str = "split") -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string, got {type(value).__name__}")
    split = value.strip()
    if split not in _SPLIT_VALUES:
        raise ValueError(
            f"{name} must be one of {list(_SPLIT_VALUES)}, got {value!r}"
        )
    return split


def _validate_text(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string, got {type(value).__name__}")
    return value.strip()


def _collect_lang_fields(payload: Dict[str, Any]) -> Dict[str, str]:
    """Validated subset of {language, language_name, script, split} in *payload*.

    Keys that are absent, ``None`` or empty strings mean "not provided" (the
    column default applies / the row keeps its current value).
    """
    out: Dict[str, str] = {}
    for key in LANG_COLUMNS:
        if key not in payload:
            continue
        value = payload[key]
        if value is None:
            continue
        if key == "language":
            code = _validate_language(value)
            if code:
                out[key] = code
        elif key == "split":
            out[key] = _validate_split(value)  # '' is a valid, explicit value
        else:
            text = _validate_text(value, key)
            if text:
                out[key] = text
    return out


def _row_language(row: Any) -> str:
    try:
        value = row["language"]
    except (KeyError, IndexError, TypeError):
        return DEFAULT_LANGUAGE
    code = str(value).strip() if value is not None else ""
    return code or DEFAULT_LANGUAGE


def _row_split(row: Any) -> str:
    try:
        value = row["split"]
    except (KeyError, IndexError, TypeError):
        return ""
    return str(value).strip() if value is not None else ""


def _db_error(exc: Exception) -> RuntimeError:
    return RuntimeError(
        "aura.db is locked or unavailable (another process/connection is "
        f"holding it, or the file is read-only): {exc}. "
        "Close the other connection and retry — the database was not modified."
    )


def _connect() -> sqlite3.Connection:
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=_DB_TIMEOUT_S)
    except sqlite3.Error as exc:
        raise _db_error(exc) from exc
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    """CREATE TABLE IF NOT EXISTS for the two tables owned by this module."""
    try:
        conn.execute(CREATE_SAMPLES_SQL)
        conn.execute(CREATE_MODELS_SQL)
        conn.commit()
        cols = [row[1] for row in conn.execute("PRAGMA table_info(dataset_samples)")]
        if cols:
            _migrate_samples_columns(conn, cols)
            cols = [row[1] for row in conn.execute("PRAGMA table_info(dataset_samples)")]
    except sqlite3.OperationalError as exc:
        raise _db_error(exc) from exc
    except sqlite3.DatabaseError as exc:
        raise RuntimeError(f"aura.db appears to be corrupt: {exc}") from exc
    if cols:
        missing = [c for c in _REQUIRED_SAMPLE_COLS if c not in cols]
        if missing:
            raise RuntimeError(
                f"table dataset_samples already exists in {DB_PATH.name} but is "
                f"missing columns {missing}; refusing to modify an unknown schema"
            )


# Additive-only migration: new multilingual metadata columns.  Existing rows
# simply receive the DEFAULT value (SQLite backfill) — no row data is ever
# rewritten, and columns are only added when they are missing.
_SAMPLE_MIGRATIONS: Tuple[Tuple[str, str], ...] = (
    ("language", "TEXT DEFAULT 'en'"),
    ("language_name", "TEXT DEFAULT 'English'"),
    ("script", "TEXT DEFAULT 'Latin'"),
    ("split", "TEXT DEFAULT ''"),
)


def _migrate_samples_columns(conn: sqlite3.Connection, cols: List[str]) -> None:
    existing = set(cols)
    for name, declaration in _SAMPLE_MIGRATIONS:
        if name in existing:
            continue
        conn.execute(f"ALTER TABLE dataset_samples ADD COLUMN {name} {declaration}")
        existing.add(name)
    conn.commit()


def _row_to_item(row: sqlite3.Row) -> Dict[str, Any]:
    return {key: row[key] for key in ITEM_COLUMNS if key in row.keys()}


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _safe_metrics(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except ValueError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


# --------------------------------------------------------------------------
# demo seeding
# --------------------------------------------------------------------------
def _demo_rows() -> List[Dict[str, str]]:
    if not DEMO_CSV.exists():
        return []
    try:
        with DEMO_CSV.open("r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            if not reader.fieldnames:
                return []
            missing = [c for c in CSV_COLUMNS if c not in reader.fieldnames]
            if missing:
                raise ValueError(
                    f"{DEMO_CSV.name} is missing required columns: {missing}"
                )
            return list(reader)
    except csv.Error as exc:
        raise ValueError(f"cannot parse {DEMO_CSV.name}: {exc}") from exc


def _ensure_seeded(conn: sqlite3.Connection) -> int:
    """Seed dataset_samples from the demo CSV the first time it is empty."""
    try:
        count = conn.execute("SELECT COUNT(*) FROM dataset_samples").fetchone()[0]
    except sqlite3.OperationalError as exc:
        raise _db_error(exc) from exc
    if count or SEED_MARKER_PATH.exists():
        return 0
    raw_rows = _demo_rows()
    if not raw_rows:
        return 0
    stamp = _now()
    payload: List[Tuple[Any, ...]] = []
    for raw in raw_rows:
        comment = (raw.get("comment") or "").strip()
        if not comment:
            continue
        labels = [_coerce_label(raw.get(label), label) for label in LABELS]
        source = (raw.get("source") or "").strip() or "demo"
        payload.append((comment, *labels, source, stamp, stamp))
    if not payload:
        return 0
    try:
        conn.executemany(
            "INSERT INTO dataset_samples (comment, "
            + ", ".join(LABELS)
            + ", source, created_at, updated_at) VALUES ("
            + ", ".join("?" for _ in range(len(LABELS) + 4))
            + ")",
            payload,
        )
        conn.commit()
    except sqlite3.OperationalError as exc:
        raise _db_error(exc) from exc
    try:
        ensure_dirs()
        SEED_MARKER_PATH.write_text(
            f"seeded {len(payload)} demo rows at {stamp}\n", encoding="utf-8"
        )
    except OSError:  # pragma: no cover - marker is best effort
        pass
    return len(payload)


def _open() -> sqlite3.Connection:
    conn = _connect()
    _ensure_schema(conn)
    _ensure_seeded(conn)
    return conn


# --------------------------------------------------------------------------
# multilingual seeding (defensive: file may not exist yet, never destructive)
# --------------------------------------------------------------------------
def _read_multilingual_rows() -> Optional[List[Dict[str, str]]]:
    """Rows of data/multilingual/raw/multilingual_demo.csv, or None when the
    file is missing / still being written / not in the documented shape."""
    if not MULTILINGUAL_CSV.is_file():
        return None
    try:
        with MULTILINGUAL_CSV.open("r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            if not reader.fieldnames:
                return None
            fields = {(name or "").strip() for name in reader.fieldnames}
            if "text" not in fields or "language" not in fields:
                return None  # not the documented shape — leave it alone
            return [dict(row) for row in reader]
    except (OSError, UnicodeDecodeError, csv.Error):
        return None


def _insert_multilingual_rows(
    conn: sqlite3.Connection, raw_rows: List[Dict[str, str]]
) -> int:
    existing = {
        re.sub(r"\s+", " ", (row[0] or "").strip()).lower()
        for row in conn.execute(
            "SELECT comment FROM dataset_samples WHERE comment IS NOT NULL"
        )
    }
    stamp = _now()
    payload: List[Tuple[Any, ...]] = []
    for raw in raw_rows:
        text = (raw.get("text") or raw.get("comment") or "").strip()
        if not text:
            continue
        key = re.sub(r"\s+", " ", text).lower()
        if key in existing:
            continue  # never duplicate / overwrite an existing row
        existing.add(key)
        language = (raw.get("language") or "").strip()
        if not _LANGUAGE_RE.match(language):
            language = DEFAULT_LANGUAGE
        language_name = (raw.get("language_name") or "").strip() or language
        script = (raw.get("script") or "").strip() or (
            DEFAULT_SCRIPT if text.isascii() else ""
        )
        split = (raw.get("split") or "").strip()
        if split not in _SPLIT_VALUES:
            split = ""
        source = (raw.get("source") or "").strip() or "multilingual"
        labels = [_to_int(raw.get(label)) for label in LABELS]
        payload.append(
            (text, *labels, source, language, language_name, script, split, stamp, stamp)
        )
    if not payload:
        return 0
    fields = ("comment",) + LABELS + ("source",) + LANG_COLUMNS + (
        "created_at",
        "updated_at",
    )
    conn.executemany(
        "INSERT INTO dataset_samples ("
        + ", ".join(fields)
        + ") VALUES ("
        + ", ".join("?" for _ in fields)
        + ")",
        payload,
    )
    conn.commit()
    return len(payload)


def ensure_multilingual_seeded(conn: Optional[sqlite3.Connection] = None) -> int:
    """Idempotently seed ``dataset_samples`` from the multilingual demo CSV.

    * No file (or a partially-written / foreign-shaped file) -> do nothing.
    * Rows whose text already exists in the table are skipped.
    * Existing rows are never deleted or overwritten.
    * Cheap: guarded by a module flag plus a one-query "already seeded" check.
    """
    global _MULTILINGUAL_SEEDED
    if _MULTILINGUAL_SEEDED:
        return 0
    if not MULTILINGUAL_CSV.is_file():
        return 0  # absent today, re-checked cheaply on the next call
    with _MULTILINGUAL_LOCK:
        if _MULTILINGUAL_SEEDED:
            return 0
        own_connection = conn is None
        if own_connection:
            conn = _connect()
            _ensure_schema(conn)
            _ensure_seeded(conn)
        try:
            cols = [
                row[1] for row in conn.execute("PRAGMA table_info(dataset_samples)")
            ]
            if cols and "language" not in cols:
                _migrate_samples_columns(conn, cols)
            seeded = conn.execute(
                "SELECT 1 FROM dataset_samples "
                "WHERE language IS NOT NULL AND language NOT IN ('en', '') "
                "LIMIT 1"
            ).fetchone()
            if seeded is not None:
                _MULTILINGUAL_SEEDED = True
                return 0
            raw_rows = _read_multilingual_rows()
            if not raw_rows:
                return 0  # file missing/incomplete — retry later, no error
            inserted = _insert_multilingual_rows(conn, raw_rows)
            _MULTILINGUAL_SEEDED = True
            return inserted
        except sqlite3.OperationalError as exc:
            raise _db_error(exc) from exc
        finally:
            if own_connection:
                conn.close()


# --------------------------------------------------------------------------
# dataset CRUD
# --------------------------------------------------------------------------
def _filter_clauses(
    language: Any, label: Any, source: Any, split: Any, params: List[Any]
) -> List[str]:
    """Build the extra WHERE clauses for the multilingual/faceted filters."""
    clauses: List[str] = []

    def _text_filter(value: Any, name: str, column: str) -> None:
        if value is None:
            return
        if not isinstance(value, str):
            raise ValueError(f"{name} must be a string, got {type(value).__name__}")
        term = value.strip()
        if not term:  # empty string == no filter (same convention as q="")
            return
        clauses.append(f"{column} = ?")
        params.append(term)

    _text_filter(language, "language", "language")
    _text_filter(source, "source", "source")

    if label is not None and str(label).strip() != "":
        if not isinstance(label, str):
            raise ValueError(f"label must be a string, got {type(label).__name__}")
        key = label.strip().lower()
        if key not in _LABEL_FILTERS:
            raise ValueError(
                "label must be 'toxic' or 'non_toxic', got {!r}".format(label)
            )
        clauses.append("toxic = ?")
        params.append(_LABEL_FILTERS[key])

    if split is not None:
        if not isinstance(split, str):
            raise ValueError(f"split must be a string, got {type(split).__name__}")
        value = split.strip()
        if value:
            if value.lower() == UNASSIGNED_SPLIT:
                clauses.append("(split IS NULL OR split = '')")
            else:
                clauses.append("split = ?")
                params.append(value)

    return clauses


def list_samples(
    limit: int = 100,
    offset: int = 0,
    q: str = "",
    language: Optional[str] = None,
    label: Optional[str] = None,
    source: Optional[str] = None,
    split: Optional[str] = None,
) -> Dict[str, Any]:
    limit = _check_int(limit, "limit", minimum=0)
    offset = _check_int(offset, "offset", minimum=0)
    if not isinstance(q, str):
        raise ValueError(f"q must be a string, got {type(q).__name__}")

    where_parts: List[str] = []
    params: List[Any] = []
    term = q.strip()
    if term:
        escaped = (
            term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        )
        where_parts.append("comment LIKE ? ESCAPE '\\'")
        params.append(f"%{escaped}%")
    where_parts.extend(_filter_clauses(language, label, source, split, params))

    where = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""

    conn = _open()
    try:
        ensure_multilingual_seeded(conn)
        total = conn.execute(
            f"SELECT COUNT(*) FROM dataset_samples{where}", params
        ).fetchone()[0]
        rows = conn.execute(
            f"SELECT * FROM dataset_samples{where} ORDER BY id ASC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
        return {"items": [_row_to_item(r) for r in rows], "total": int(total)}
    finally:
        conn.close()


def add_sample(d: Any) -> Dict[str, Any]:
    if not isinstance(d, dict):
        raise ValueError(f"add_sample expects a dict, got {type(d).__name__}")
    comment = d.get("comment")
    if not isinstance(comment, str) or not comment.strip():
        raise ValueError("comment must be a non-empty string")
    comment = comment.strip()
    labels = {label: _coerce_label(d.get(label, 0), label) for label in LABELS}
    source = d.get("source", "demo")
    if source is None:
        source = "demo"
    if not isinstance(source, str) or not source.strip():
        raise ValueError(f"source must be a non-empty string, got {source!r}")
    source = source.strip()
    lang_fields = _collect_lang_fields(d)

    stamp = _now()
    conn = _open()
    try:
        fields = ["comment"] + list(LABELS) + ["source"] + list(lang_fields)
        values: List[Any] = [comment] + [labels[label] for label in LABELS] + [source]
        values.extend(lang_fields[key] for key in lang_fields)
        fields += ["created_at", "updated_at"]
        values += [stamp, stamp]
        cur = conn.execute(
            "INSERT INTO dataset_samples ("
            + ", ".join(fields)
            + ") VALUES ("
            + ", ".join("?" for _ in fields)
            + ")",
            values,
        )
        conn.commit()
        new_id = int(cur.lastrowid or 0)
        row = conn.execute(
            "SELECT * FROM dataset_samples WHERE id = ?", (new_id,)
        ).fetchone()
        if row is None:  # pragma: no cover - defensive
            raise RuntimeError("insert succeeded but the row could not be read back")
        return _row_to_item(row)
    except sqlite3.OperationalError as exc:
        raise _db_error(exc) from exc
    finally:
        conn.close()


def update_sample(sample_id: Any, d: Any) -> Dict[str, Any]:
    sample_id = _check_id(sample_id)
    if not isinstance(d, dict):
        raise ValueError(f"update_sample expects a dict, got {type(d).__name__}")
    updates: Dict[str, Any] = {}
    for key, value in d.items():
        if key in UPDATABLE and key not in LANG_COLUMNS:
            updates[key] = value
    if "comment" in updates:
        comment = updates["comment"]
        if not isinstance(comment, str) or not comment.strip():
            raise ValueError("comment must be a non-empty string")
        updates["comment"] = comment.strip()
    if "source" in updates:
        source = updates["source"]
        if not isinstance(source, str) or not source.strip():
            raise ValueError(f"source must be a non-empty string, got {source!r}")
        updates["source"] = source.strip()
    for label in LABELS:
        if label in updates:
            updates[label] = _coerce_label(updates[label], label)
    # optional multilingual metadata — only the keys actually provided
    updates.update(_collect_lang_fields(d))
    if not updates:
        raise ValueError(
            "nothing to update: provide at least one of "
            + ", ".join(sorted(UPDATABLE))
        )

    conn = _open()
    try:
        row = conn.execute(
            "SELECT id FROM dataset_samples WHERE id = ?", (sample_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"sample {sample_id} not found")
        updates["updated_at"] = _now()
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        conn.execute(
            f"UPDATE dataset_samples SET {set_clause} WHERE id = ?",
            list(updates.values()) + [sample_id],
        )
        conn.commit()
        fresh = conn.execute(
            "SELECT * FROM dataset_samples WHERE id = ?", (sample_id,)
        ).fetchone()
        if fresh is None:  # pragma: no cover - defensive
            raise KeyError(f"sample {sample_id} not found")
        return _row_to_item(fresh)
    except sqlite3.OperationalError as exc:
        raise _db_error(exc) from exc
    finally:
        conn.close()


def delete_sample(sample_id: Any) -> bool:
    sample_id = _check_id(sample_id)
    conn = _open()
    try:
        cur = conn.execute("DELETE FROM dataset_samples WHERE id = ?", (sample_id,))
        conn.commit()
        return cur.rowcount > 0
    except sqlite3.OperationalError as exc:
        raise _db_error(exc) from exc
    finally:
        conn.close()


# --------------------------------------------------------------------------
# statistics
# --------------------------------------------------------------------------
def dataset_stats() -> Dict[str, Any]:
    conn = _open()
    try:
        ensure_multilingual_seeded(conn)
        summary = conn.execute(
            "SELECT COUNT(*) AS n, "
            + ", ".join(f"COALESCE(SUM({label}), 0) AS s_{label}" for label in LABELS)
            + " FROM dataset_samples"
        ).fetchone()
        total = int(summary["n"] or 0)
        category_counts = {label: int(summary[f"s_{label}"] or 0) for label in LABELS}
        missing = int(
            conn.execute(
                "SELECT COUNT(*) FROM dataset_samples WHERE comment IS NULL "
                "OR TRIM(comment) = '' OR "
                + " OR ".join(f"{label} IS NULL" for label in LABELS)
            ).fetchone()[0]
        )
        comments = [
            (row[0] or "")
            for row in conn.execute(
                "SELECT comment FROM dataset_samples WHERE comment IS NOT NULL"
            )
        ]
        by_language: Dict[str, int] = {}
        by_split: Dict[str, int] = {}
        by_source: Dict[str, int] = {}
        for row in conn.execute(
            "SELECT language, split, source FROM dataset_samples"
        ).fetchall():
            code = _row_language(row)
            by_language[code] = by_language.get(code, 0) + 1
            split_key = _row_split(row) or UNASSIGNED_SPLIT
            by_split[split_key] = by_split.get(split_key, 0) + 1
            try:
                src = row["source"]
            except (KeyError, IndexError, TypeError):
                src = None
            src = str(src).strip() if src is not None else ""
            src = src or "demo"
            by_source[src] = by_source.get(src, 0) + 1
    except sqlite3.OperationalError as exc:
        raise _db_error(exc) from exc
    finally:
        conn.close()

    seen: Dict[str, int] = {}
    for comment in comments:
        key = re.sub(r"\s+", " ", comment.strip()).lower()
        seen[key] = seen.get(key, 0) + 1
    duplicates = sum(count - 1 for count in seen.values() if count > 1)

    toxic = category_counts.get("toxic", 0)
    return {
        "total": total,
        "toxic": toxic,
        "non_toxic": total - toxic,
        "category_counts": category_counts,
        "missing_labels": missing,
        "duplicates": duplicates,
        "by_language": by_language,
        "by_split": by_split,
        "by_source": by_source,
        "languages": sorted(by_language),
    }


def class_distribution() -> Dict[str, int]:
    stats = dataset_stats()
    counts = dict(stats["category_counts"])
    return {
        **{label: int(counts.get(label, 0)) for label in LABELS},
        "non_toxic": int(stats["non_toxic"]),
    }


# --------------------------------------------------------------------------
# deterministic train / validation / test split
# --------------------------------------------------------------------------
def _write_split_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(SPLIT_CSV_COLUMNS)
        for row in rows:
            writer.writerow(
                [
                    row.get("comment", ""),
                    *[_to_int(row.get(label)) for label in LABELS],
                    row.get("source") or "demo",
                    row.get("language") or DEFAULT_LANGUAGE,
                    row.get("language_name") or DEFAULT_LANGUAGE_NAME,
                    row.get("script") or DEFAULT_SCRIPT,
                    row.get("split") or "",
                ]
            )


def _write_multilingual_split_csvs(
    buckets: Dict[str, List[Dict[str, Any]]]
) -> None:
    """data/multilingual/{train,validation,test}/split.csv — best effort."""
    for name, rows in buckets.items():
        directory = MULTILINGUAL_DIR / name
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError:
            continue  # directory unavailable -> nothing to write
        try:
            with (directory / "split.csv").open(
                "w", encoding="utf-8", newline=""
            ) as fh:
                writer = csv.writer(fh)
                writer.writerow(MULTILINGUAL_SPLIT_COLUMNS)
                for row in rows:
                    writer.writerow(
                        [
                            row.get("id", ""),
                            row.get("comment", ""),
                            row.get("language") or DEFAULT_LANGUAGE,
                            row.get("language_name") or DEFAULT_LANGUAGE_NAME,
                            row.get("script") or DEFAULT_SCRIPT,
                            *[_to_int(row.get(label)) for label in LABELS],
                            row.get("source") or "demo",
                            row.get("split") or name,
                        ]
                    )
        except OSError:
            continue


def _sync_split_column(conn: sqlite3.Connection, rows: List[Dict[str, Any]]) -> None:
    """Persist the freshly computed split as row metadata (split column only)."""
    updates: List[Tuple[str, int, str]] = []
    for row in rows:
        row_id = row.get("id")
        if row_id is None:
            continue
        split = _row_split(row)
        updates.append((split, int(row_id), split))
    if not updates:
        return
    conn.executemany(
        "UPDATE dataset_samples SET split = ? "
        "WHERE id = ? AND IFNULL(split, '') <> ?",
        updates,
    )
    conn.commit()


def split_dataset(seed: int = 42) -> Dict[str, int]:
    seed = _check_int(seed, "seed")
    ensure_dirs()
    conn = _open()
    try:
        ensure_multilingual_seeded(conn)  # (a) multilingual rows join the split
        rows = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM dataset_samples ORDER BY id ASC"
            ).fetchall()
        ]

        # dedupe first (keep the first occurrence of each normalised comment)
        unique: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            comment = (row.get("comment") or "").strip()
            if not comment:
                continue
            key = re.sub(r"\s+", " ", comment).lower()
            if key not in unique:
                row["comment"] = comment
                unique[key] = row
        deduped = list(unique.values())

        rng = random.Random(seed)
        rng.shuffle(deduped)

        n = len(deduped)
        n_train = int(n * _SPLIT_RATIOS[0])
        n_val = int(n * _SPLIT_RATIOS[1])
        n_test = n - n_train - n_val

        train_rows = deduped[:n_train]
        val_rows = deduped[n_train : n_train + n_val]
        test_rows = deduped[n_train + n_val :]
        for bucket, bucket_rows in (
            ("train", train_rows),
            ("validation", val_rows),
            ("test", test_rows),
        ):
            for row in bucket_rows:
                row["split"] = bucket
        _sync_split_column(conn, deduped)
    except sqlite3.OperationalError as exc:
        raise _db_error(exc) from exc
    finally:
        conn.close()

    _write_split_csv(TRAIN_CSV, train_rows)
    _write_split_csv(VALIDATION_CSV, val_rows)
    _write_split_csv(TEST_CSV, test_rows)
    _write_multilingual_split_csvs(
        {"train": train_rows, "validation": val_rows, "test": test_rows}
    )
    _write_json(
        SPLIT_META_PATH,
        {
            "seed": seed,
            "train": n_train,
            "validation": n_val,
            "test": n_test,
            "total_rows": n,
            "created_at": _now(),
        },
    )
    return {"seed": seed, "train": n_train, "validation": n_val, "test": n_test}


def _split_ready() -> bool:
    try:
        return all(
            path.is_file() and path.stat().st_size > 0
            for path in (TRAIN_CSV, VALIDATION_CSV, TEST_CSV)
        )
    except OSError:  # pragma: no cover - defensive
        return False


def _count_csv(path: Path) -> int:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.reader(fh)
            rows = sum(1 for _ in reader)
    except (OSError, csv.Error):
        return 0
    return max(0, rows - 1)  # minus the header


def split_counts() -> Dict[str, int]:
    ensure_dirs()
    if not _split_ready():
        return split_dataset(42)
    meta = _read_json(SPLIT_META_PATH)
    seed = meta.get("seed", 42) if isinstance(meta, dict) else 42
    if isinstance(seed, bool) or not isinstance(seed, int):
        seed = 42
    return {
        "seed": seed,
        "train": _count_csv(TRAIN_CSV),
        "validation": _count_csv(VALIDATION_CSV),
        "test": _count_csv(TEST_CSV),
    }


def _load_split_rows(path: Path) -> List[Dict[str, str]]:
    if not path.is_file():
        raise ValueError(f"missing dataset split file: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            raise ValueError(f"empty dataset split file: {path}")
        missing = [c for c in CSV_COLUMNS if c not in reader.fieldnames]
        if missing:
            raise ValueError(f"{path.name} is missing columns: {missing}")
        return [r for r in reader if (r.get("comment") or "").strip()]


# --------------------------------------------------------------------------
# Multinomial Naive Bayes (pure python)
# --------------------------------------------------------------------------
def _tokenize(text: str, bigrams: bool) -> List[str]:
    words = _WORD_RE.findall(text.lower())
    if not bigrams:
        return words
    tokens = list(words)
    tokens.extend(
        f"{words[i]}_{words[i + 1]}" for i in range(len(words) - 1)
    )
    return tokens


def _predict_one(
    feature_log_prob: Dict[str, List[float]],
    class_log_prior: List[float],
    comment: str,
    bigrams: bool,
) -> int:
    tokens = _tokenize(comment, bigrams)
    best_class = 0
    best_score = float("-inf")
    for cls in (0, 1):
        score = class_log_prior[cls]
        for token in tokens:
            log_prob = feature_log_prob.get(token)
            if log_prob is not None:
                score += log_prob[cls]
        if score > best_score:
            best_class = cls
            best_score = score
    return best_class


def _class_prf(num: int, denom_p: int, denom_r: int, support: int) -> Dict[str, float]:
    precision = num / denom_p if denom_p else 0.0
    recall = num / denom_r if denom_r else 0.0
    f1 = (2.0 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "support": support,
    }


def _binary_metrics(y_true: List[int], y_pred: List[int]) -> Dict[str, Any]:
    tn = fp = fn = tp = 0
    for actual, pred in zip(y_true, y_pred):
        if actual == 1 and pred == 1:
            tp += 1
        elif actual == 1 and pred == 0:
            fn += 1
        elif actual == 0 and pred == 1:
            fp += 1
        else:
            tn += 1
    total = tn + fp + fn + tp
    accuracy = (tn + tp) / total if total else 0.0
    per_label = {
        "non_toxic": _class_prf(tn, tn + fn, tn + fp, tn + fp),
        "toxic": _class_prf(tp, tp + fp, tp + fn, tp + fn),
    }
    macro = {
        key: (per_label["non_toxic"][key] + per_label["toxic"][key]) / 2.0
        for key in ("precision", "recall", "f1")
    }
    return {
        "accuracy": accuracy,
        "precision": macro["precision"],
        "recall": macro["recall"],
        "f1": macro["f1"],
        "confusion_matrix": {
            "labels": ["non_toxic", "toxic"],
            "matrix": [[tn, fp], [fn, tp]],
        },
        "per_label": per_label,
    }


def _next_version(variant: str) -> int:
    max_seen = 0
    try:
        for path in PROCESSED_DIR.glob(f"{variant}_v*.json"):
            match = re.match(rf"^{re.escape(variant)}_v(\d+)\.json$", path.name)
            if match:
                max_seen = max(max_seen, int(match.group(1)))
    except OSError:  # pragma: no cover - defensive
        pass
    return max_seen + 1


def _dataset_version(path: Path, seed: int) -> str:
    try:
        digest = hashlib.sha1(path.read_bytes()).hexdigest()[:10]
    except OSError:  # pragma: no cover - defensive
        digest = "unknown"
    return f"seed{seed}-{digest}"


def _full_from_stored(metrics: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not metrics or any(key not in metrics for key in _METRIC_KEYS):
        return None
    return {
        "accuracy": float(metrics["accuracy"]),
        "precision": float(metrics["precision"]),
        "recall": float(metrics["recall"]),
        "f1": float(metrics["f1"]),
        "confusion_matrix": metrics.get("confusion_matrix"),
        "per_label": metrics.get("per_label"),
    }


def _load_weights(path: Any) -> Optional[Dict[str, Any]]:
    if not path:
        return None
    file_path = Path(str(path))
    if not file_path.is_file():
        return None
    data = _read_json(file_path)
    if not isinstance(data, dict) or "feature_counts" not in data:
        return None
    counts = data.get("feature_counts") or {}
    if not isinstance(counts, dict):
        return None
    vocab_size = max(1, int(data.get("vocab_size") or len(counts)))
    totals = data.get("class_totals") or [0, 0]
    denom = [
        max(1.0, float(totals[0]) + vocab_size),
        max(1.0, float(totals[1]) + vocab_size),
    ]
    feature_log_prob: Dict[str, List[float]] = {}
    for token, pair in counts.items():
        pair = pair if isinstance(pair, (list, tuple)) else [0, 0]
        feature_log_prob[token] = [
            math.log((float(pair[0]) + 1.0) / denom[0]),
            math.log((float(pair[1]) + 1.0) / denom[1]),
        ]
    data["_feature_log_prob"] = feature_log_prob
    data["_bigrams"] = bool(data.get("bigrams"))
    return data


def _evaluate_weights(weights: Dict[str, Any], rows: List[Dict[str, str]]) -> Dict[str, Any]:
    feature_log_prob = weights["_feature_log_prob"]
    class_log_prior = list(weights.get("class_log_prior") or [0.0, 0.0])
    bigrams = weights["_bigrams"]
    y_true: List[int] = []
    y_pred: List[int] = []
    for row in rows:
        y_true.append(_to_int(row.get("toxic")))
        y_pred.append(
            _predict_one(feature_log_prob, class_log_prior, row.get("comment", ""), bigrams)
        )
    return _binary_metrics(y_true, y_pred)


def _evaluate_by_language(
    weights: Dict[str, Any], rows: List[Dict[str, str]]
) -> Optional[Dict[str, Any]]:
    """Binary metrics per language, from the *same* predictions as the overall
    report.  Only languages with >= ``_MIN_LANGUAGE_EVAL_SAMPLES`` test rows get
    real metrics; every other language is reported as ``None`` (never faked)."""
    if not weights or "_feature_log_prob" not in weights:
        return None
    feature_log_prob = weights["_feature_log_prob"]
    class_log_prior = list(weights.get("class_log_prior") or [0.0, 0.0])
    bigrams = bool(weights.get("_bigrams"))
    if not isinstance(feature_log_prob, dict):
        return None

    groups: Dict[str, List[Dict[str, str]]] = {}
    for row in rows:
        code = str(row.get("language") or "").strip() or DEFAULT_LANGUAGE
        groups.setdefault(code, []).append(row)

    report: Dict[str, Any] = {}
    for code in sorted(groups):
        subset = groups[code]
        if len(subset) < _MIN_LANGUAGE_EVAL_SAMPLES:
            report[code] = None
            continue
        try:
            metrics = _evaluate_weights(
                {
                    "_feature_log_prob": feature_log_prob,
                    "_bigrams": bigrams,
                    "class_log_prior": class_log_prior,
                },
                subset,
            )
        except Exception:  # pragma: no cover - defensive, never fabricate
            report[code] = None
            continue
        report[code] = {
            "accuracy": float(metrics["accuracy"]),
            "precision": float(metrics["precision"]),
            "recall": float(metrics["recall"]),
            "f1": float(metrics["f1"]),
            "support": len(subset),
        }
    return report


def train_model(
    variant: str, seed: int = 42, *, _on_progress: Optional[Callable[[int, str], None]] = None
) -> Dict[str, Any]:
    """Train the pure-python Multinomial NB and evaluate it on the test split."""
    if variant not in VARIANTS:
        raise ValueError(
            f"variant must be one of {list(VARIANTS)}, got {variant!r}"
        )
    seed = _check_int(seed, "seed")

    def progress(pct: int, message: str) -> None:
        if _on_progress is not None:
            try:
                _on_progress(pct, message)
            except Exception:  # pragma: no cover - progress must never fail training
                pass

    ensure_dirs()
    progress(5, "Preparing dataset split")
    split = split_dataset(seed) if not _split_ready() else split_counts()

    train_rows = _load_split_rows(TRAIN_CSV)
    val_rows = _load_split_rows(VALIDATION_CSV)
    test_rows = _load_split_rows(TEST_CSV)
    train_n = len(train_rows)
    val_n = len(val_rows)
    test_n = len(test_rows)
    if train_n == 0:
        raise ValueError(
            "the training split is empty — add samples and call split_dataset() first"
        )
    progress(20, f"Loaded {train_n} training samples")

    bigrams = variant == "improved"
    feature: Dict[str, List[int]] = {}
    class_totals = [0, 0]
    class_doc_counts = [0, 0]
    for row in train_rows:
        target = 1 if _to_int(row.get("toxic")) else 0
        class_doc_counts[target] += 1
        for token in _tokenize(row["comment"], bigrams):
            pair = feature.get(token)
            if pair is None:
                pair = [0, 0]
                feature[token] = pair
            pair[target] += 1
            class_totals[target] += 1

    vocab_size = len(feature)
    denom = [
        max(1.0, float(class_totals[0]) + vocab_size),
        max(1.0, float(class_totals[1]) + vocab_size),
    ]
    class_log_prior = [
        math.log((class_doc_counts[cls] + 1.0) / (train_n + 2.0)) for cls in (0, 1)
    ]
    feature_log_prob = {
        token: [
            math.log((pair[0] + 1.0) / denom[0]),
            math.log((pair[1] + 1.0) / denom[1]),
        ]
        for token, pair in feature.items()
    }
    progress(
        55,
        f"Trained on {train_n} samples with {vocab_size} features ({variant})",
    )

    y_true = [1 if _to_int(r.get("toxic")) else 0 for r in test_rows]
    y_pred = [
        _predict_one(feature_log_prob, class_log_prior, r["comment"], bigrams)
        for r in test_rows
    ]
    full = _binary_metrics(y_true, y_pred)
    progress(80, f"Evaluated on {test_n} held-out test samples")

    metrics = {key: float(full[key]) for key in _METRIC_KEYS}
    training_date = _now()
    model_name = f"multinomial_nb_{variant}"
    version_num = _next_version(variant)
    model_version = f"{variant}_v{version_num}"
    out_path = PROCESSED_DIR / f"{model_version}.json"
    dataset_version = _dataset_version(TRAIN_CSV, seed)

    payload = {
        "model_name": model_name,
        "model_version": model_version,
        "variant": variant,
        "seed": seed,
        "bigrams": bigrams,
        "tokenizer": "word_unigram_bigram" if bigrams else "word_unigram",
        "smoothing": 1.0,
        "classes": ["non_toxic", "toxic"],
        "vocab_size": vocab_size,
        "class_totals": class_totals,
        "class_doc_counts": class_doc_counts,
        "class_log_prior": class_log_prior,
        "feature_counts": feature,
        "dataset_version": dataset_version,
        "split": {
            "seed": split.get("seed", seed),
            "train": train_n,
            "validation": val_n,
            "test": test_n,
        },
        "metrics": metrics,
        "confusion_matrix": full["confusion_matrix"],
        "per_label": full["per_label"],
        "training_date": training_date,
    }
    _write_json(out_path, payload)
    progress(92, f"Saved weights to data/processed/{out_path.name}")

    registry_metrics = {
        **metrics,
        "variant": variant,
        "train_n": train_n,
        "val_n": val_n,
        "test_n": test_n,
        "confusion_matrix": full["confusion_matrix"],
        "per_label": full["per_label"],
    }
    register_model_version(
        {
            "model_name": model_name,
            "model_version": model_version,
            "dataset_version": dataset_version,
            "training_date": training_date,
            "metrics": registry_metrics,
            "status": "active",
            "path": str(out_path),
        }
    )
    progress(100, "Training completed")

    return {
        "model_name": model_name,
        "model_version": model_version,
        "metrics": metrics,
        "train_n": train_n,
        "val_n": val_n,
        "test_n": test_n,
        "confusion_matrix": full["confusion_matrix"],
        "per_label": full["per_label"],
        "training_date": training_date,
    }


# --------------------------------------------------------------------------
# model registry
# --------------------------------------------------------------------------
def register_model_version(entry: Any) -> Dict[str, Any]:
    if not isinstance(entry, dict):
        raise ValueError(
            f"register_model_version expects a dict, got {type(entry).__name__}"
        )
    model_name = entry.get("model_name")
    model_version = entry.get("model_version")
    if not isinstance(model_name, str) or not model_name.strip():
        raise ValueError("model_name must be a non-empty string")
    if not isinstance(model_version, str) or not model_version.strip():
        raise ValueError("model_version must be a non-empty string")

    dataset_version = entry.get("dataset_version")
    dataset_version = (
        dataset_version if isinstance(dataset_version, str) else "unknown"
    )
    training_date = entry.get("training_date") or _now()
    if not isinstance(training_date, str):
        raise ValueError("training_date must be an ISO-8601 string")

    metrics = entry.get("metrics")
    if metrics is None:
        metrics_json = "{}"
    elif isinstance(metrics, dict):
        metrics_json = json.dumps(metrics, ensure_ascii=False)
    elif isinstance(metrics, str):
        try:
            json.loads(metrics)
        except ValueError as exc:
            raise ValueError("metrics_json must be valid JSON") from exc
        metrics_json = metrics
    else:
        raise ValueError("metrics must be a dict or a JSON string")

    status = entry.get("status") or "trained"
    if not isinstance(status, str):
        raise ValueError("status must be a string")
    path = entry.get("path") or ""
    if not isinstance(path, str):
        raise ValueError("path must be a string")

    created_at = _now()
    conn = _open()
    try:
        cur = conn.execute(
            "INSERT INTO model_versions (model_name, model_version, dataset_version, "
            "training_date, metrics_json, status, path, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                model_name.strip(),
                model_version.strip(),
                dataset_version,
                training_date,
                metrics_json,
                status,
                path,
                created_at,
            ),
        )
        conn.commit()
        new_id = int(cur.lastrowid or 0)
        row = conn.execute(
            "SELECT * FROM model_versions WHERE id = ?", (new_id,)
        ).fetchone()
        if row is None:  # pragma: no cover - defensive
            raise RuntimeError("registration succeeded but the row could not be read")
        item = dict(row)
        item["metrics"] = _safe_metrics(item.get("metrics_json"))
        return item
    except sqlite3.OperationalError as exc:
        raise _db_error(exc) from exc
    finally:
        conn.close()


def list_model_versions() -> List[Dict[str, Any]]:
    conn = _open()
    try:
        rows = conn.execute(
            "SELECT * FROM model_versions ORDER BY created_at DESC, id DESC"
        ).fetchall()
    except sqlite3.OperationalError as exc:
        raise _db_error(exc) from exc
    finally:
        conn.close()
    versions: List[Dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["metrics"] = _safe_metrics(item.get("metrics_json"))
        versions.append(item)
    return versions


def _latest_model(variant: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Newest registry row (optionally per variant), falling back to disk."""
    conn = _open()
    try:
        if variant:
            rows = conn.execute(
                "SELECT * FROM model_versions WHERE model_name = ? "
                "ORDER BY created_at DESC, id DESC",
                (f"multinomial_nb_{variant}",),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM model_versions ORDER BY created_at DESC, id DESC"
            ).fetchall()
    except sqlite3.OperationalError as exc:
        raise _db_error(exc) from exc
    finally:
        conn.close()

    for row in rows:
        item = dict(row)
        metrics = _safe_metrics(item.get("metrics_json"))
        has_weights = bool(item.get("path")) and Path(str(item["path"])).is_file()
        if has_weights or metrics:
            item["metrics"] = metrics
            return item

    # fall back to weights on disk (e.g. registry rows removed elsewhere)
    try:
        candidates: List[Tuple[float, int, Path]] = []
        for path in PROCESSED_DIR.glob("*_v*.json"):
            match = re.match(r"^([A-Za-z0-9]+)_v(\d+)\.json$", path.name)
            if not match:
                continue
            if variant and match.group(1) != variant:
                continue
            try:
                mtime = path.stat().st_mtime
            except OSError:
                mtime = 0.0
            candidates.append((mtime, int(match.group(2)), path))
    except OSError:  # pragma: no cover - defensive
        candidates = []
    if not candidates:
        return None
    candidates.sort(reverse=True)
    data = _read_json(candidates[0][2])
    if not isinstance(data, dict):
        return None
    metrics = data.get("metrics") if isinstance(data.get("metrics"), dict) else {}
    return {
        "model_name": data.get("model_name"),
        "model_version": data.get("model_version"),
        "dataset_version": data.get("dataset_version"),
        "training_date": data.get("training_date"),
        "metrics_json": json.dumps(metrics, ensure_ascii=False),
        "metrics": metrics,
        "status": "active",
        "path": str(candidates[0][2]),
        "created_at": None,
    }


def _not_evaluated(split: Dict[str, int]) -> Dict[str, Any]:
    return {
        "status": "not_evaluated",
        "accuracy": _NOT_EVALUATED,
        "precision": _NOT_EVALUATED,
        "recall": _NOT_EVALUATED,
        "f1": _NOT_EVALUATED,
        "training_samples": int(split.get("train", 0)),
        "validation_samples": int(split.get("validation", 0)),
        "test_samples": int(split.get("test", 0)),
        "model_version": None,
        "evaluated_at": None,
        "confusion_matrix": None,
        "per_label": None,
    }


def evaluate_report() -> Dict[str, Any]:
    split = split_counts()
    model = _latest_model()
    if model is None:
        report = _not_evaluated(split)
        report["by_language"] = None
        return report

    weights = _load_weights(model.get("path"))
    by_language: Optional[Dict[str, Any]] = None
    if weights is not None:
        test_rows = _load_split_rows(TEST_CSV)
        full = _evaluate_weights(weights, test_rows)
        model_version = weights.get("model_version") or model.get("model_version")
        if full is not None:
            by_language = _evaluate_by_language(weights, test_rows)
    else:
        full = _full_from_stored(model.get("metrics") or {})
        model_version = model.get("model_version")
    if full is None:
        report = _not_evaluated(split)
        report["by_language"] = None
        return report

    return {
        "status": "evaluated",
        "accuracy": float(full["accuracy"]),
        "precision": float(full["precision"]),
        "recall": float(full["recall"]),
        "f1": float(full["f1"]),
        "training_samples": int(split.get("train", 0)),
        "validation_samples": int(split.get("validation", 0)),
        "test_samples": int(split.get("test", 0)),
        "model_version": model_version,
        "evaluated_at": _now(),
        "confusion_matrix": full["confusion_matrix"],
        "per_label": full["per_label"],
        "by_language": by_language,
    }


def _variant_report(variant: str) -> Optional[Dict[str, Any]]:
    model = _latest_model(variant)
    if model is None:
        return None
    weights = _load_weights(model.get("path"))
    if weights is not None:
        full = _evaluate_weights(weights, _load_split_rows(TEST_CSV))
    else:
        full = _full_from_stored(model.get("metrics") or {})
    if full is None:
        return None
    stored = model.get("metrics") if isinstance(model.get("metrics"), dict) else {}
    split = split_counts()
    return {
        "metrics": {key: float(full[key]) for key in _METRIC_KEYS},
        "confusion_matrix": full["confusion_matrix"],
        "per_label": full["per_label"],
        "training": {
            "model_name": model.get("model_name"),
            "model_version": model.get("model_version"),
            "dataset_version": model.get("dataset_version"),
            "training_date": model.get("training_date"),
            "train_n": int(stored.get("train_n", split.get("train", 0))),
            "val_n": int(stored.get("val_n", split.get("validation", 0))),
            "test_n": int(stored.get("test_n", split.get("test", 0))),
            "metrics": {
                key: float(full[key]) for key in _METRIC_KEYS
            },
        },
    }


def compare_models() -> Dict[str, Any]:
    split_counts()  # make sure the held-out split exists before comparing
    baseline = _variant_report("baseline")
    improved = _variant_report("improved")

    def value(report: Optional[Dict[str, Any]], key: str) -> Any:
        if not report:
            return _NOT_EVALUATED
        metrics = report["metrics"]
        return metrics.get(key, _NOT_EVALUATED)

    metrics = [
        {"name": "Accuracy", "baseline": value(baseline, "accuracy"), "improved": value(improved, "accuracy")},
        {"name": "Precision", "baseline": value(baseline, "precision"), "improved": value(improved, "precision")},
        {"name": "Recall", "baseline": value(baseline, "recall"), "improved": value(improved, "recall")},
        {"name": "F1", "baseline": value(baseline, "f1"), "improved": value(improved, "f1")},
    ]
    return {
        "metrics": metrics,
        "training": {
            "baseline": baseline["training"] if baseline else _NOT_EVALUATED,
            "improved": improved["training"] if improved else _NOT_EVALUATED,
        },
        "notes": _NOTES,
    }


# --------------------------------------------------------------------------
# background training jobs (daemon thread — never blocks the caller)
# --------------------------------------------------------------------------
def _set_job(job_id: str, **fields: Any) -> None:
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            return
        job.update(fields)


def _training_worker(job_id: str, variant: str, seed: int) -> None:
    _set_job(job_id, status="running", progress=5, message="Training started")
    try:
        result = train_model(
            variant,
            seed,
            _on_progress=lambda pct, msg: _set_job(
                job_id, progress=pct, message=msg, status="running"
            ),
        )
        _set_job(
            job_id,
            status="completed",
            progress=100,
            message=f"Training completed ({variant})",
            metrics=result,
            error=None,
            finished_at=_now(),
        )
    except Exception as exc:  # noqa: BLE001 - a job must capture every failure
        _set_job(
            job_id,
            status="failed",
            progress=100,
            message="Training failed",
            error=f"{type(exc).__name__}: {exc}",
            finished_at=_now(),
        )


def start_training(job_id: Any, config: Any = None) -> None:
    if not isinstance(job_id, str) or not job_id.strip():
        raise ValueError(f"job_id must be a non-empty string, got {job_id!r}")
    job_id = job_id.strip()

    if config is None:
        cfg: Dict[str, Any] = {}
    elif isinstance(config, dict):
        cfg = dict(config)
    else:
        raise ValueError(f"config must be a dict or None, got {type(config).__name__}")

    variant = cfg.get("variant", "improved")
    if variant not in VARIANTS:
        raise ValueError(
            f"config['variant'] must be one of {list(VARIANTS)}, got {variant!r}"
        )
    seed = cfg.get("seed", 42)
    seed = _check_int(seed, "config['seed']")

    with _JOBS_LOCK:
        existing = _JOBS.get(job_id)
        if existing is not None and existing["status"] in ("queued", "running"):
            raise ValueError(
                f"job {job_id!r} is already {existing['status']}"
            )
        _JOBS[job_id] = {
            "job_id": job_id,
            "status": "queued",
            "progress": 0,
            "message": "Queued",
            "metrics": None,
            "error": None,
            "started_at": _now(),
            "finished_at": None,
        }

    thread = threading.Thread(
        target=_training_worker,
        args=(job_id, variant, seed),
        name=f"aura-training-{job_id}",
        daemon=True,
    )
    thread.start()  # returns immediately — the caller is never blocked


def get_job(job_id: Any) -> Dict[str, Any]:
    if not isinstance(job_id, str) or not job_id.strip():
        raise ValueError(f"job_id must be a non-empty string, got {job_id!r}")
    job_id = job_id.strip()
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            raise KeyError(f"job {job_id!r} not found")
        return {
            "job_id": job["job_id"],
            "status": job["status"],
            "progress": job["progress"],
            "message": job["message"],
            "metrics": job["metrics"],
            "error": job["error"],
            "started_at": job["started_at"],
            "finished_at": job["finished_at"],
        }


if __name__ == "__main__":  # pragma: no cover - manual smoke test only
    ensure_dirs()
    print(json.dumps(list_samples(limit=3), indent=2))
    print(json.dumps(dataset_stats(), indent=2))
    print(json.dumps(split_counts(), indent=2))
    print(json.dumps(evaluate_report(), indent=2))
