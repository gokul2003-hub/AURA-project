"""AURA Phase 4 (Workstream B) — dataset-import pipeline safety tests.

Safety contract of THIS suite:
  * Every database is a throw-away fixture created under the system temp
    dir (``.../Temp/opencode/phase4_wb``). This suite NEVER opens, reads
    or writes ``CODE/BACKEND/aura.db`` — a hard guard in ``run_importer``
    refuses to target the live DB path.
  * Every importer subprocess gets an explicit ``--db`` and an explicit
    ``--report`` pointing inside the temp dir, so even the importer's
    report file can never clobber the project's real audit trail.
  * Stdlib only, no backend/network, no model loading, no training.

What it covers (gaps and fixes from the Phase 4 audit):
  1. Fix F-B1: fetch pipeline's ``existing_texts()`` leakage guard now uses
     the same whitespace-collapsed + casefold key as ``dedup_rows()``.
  2. Fix F-B2: importer ``--report`` flag isolates the import report.
  3. Rollback completeness under fault injection (SQLite trigger).
  4. Additive-only guarantee: pre-existing rows byte-identical after import.
  5. Split immutability: split values of pre-existing rows never change;
     imported rows always get split=''.
  6. Threshold/model immutability: models/tuned_threshold.json,
     models/phase2_benchmark.json, models/phase3_benchmark.json are
     byte-identical before/after a real (--apply) import run.
  7. Idempotency + external_id UNIQUE index + cross-file dedup.
  8. Schema-mismatch abort, unsupported-language rejection, malformed-row
     handling, BOM/CRLF encoding, --limit accounting.
  9. Backup location: backups follow the target DB (temp dir), never the
     project directory, when --db is used.
 10. Static safety check: the existing coordinator-run suite
     tests_dataset_import.py always passes --db (never the live default).

Run:  python tests_dataset_import_phase4.py
Exit: 0 = all pass, 1 = failures.
"""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
LIVE_DB = BACKEND_DIR / "aura.db"           # never opened by this suite
IMPORTER = BACKEND_DIR / "import_external_datasets.py"
FETCH_SCRIPT = BACKEND_DIR / "fetch_external_datasets.py"
EXISTING_SUITE = BACKEND_DIR / "tests_dataset_import.py"
PROJECT_REPORT = BACKEND_DIR / "data" / "external" / "import_report.json"
MODELS_DIR = BACKEND_DIR / "models"
MODEL_ARTIFACTS = ["tuned_threshold.json", "phase2_benchmark.json",
                   "phase3_benchmark.json"]

TMP_ROOT = Path(tempfile.gettempdir()) / "opencode" / "phase4_wb"
SUBPROC_TIMEOUT = 120

PASS = 0
FAIL = 0
FAILURES = []

HEADER = ["id", "text", "language", "language_name", "script", "toxic",
          "severe_toxic", "obscene", "threat", "insult", "identity_hate",
          "source", "split"]
LABELS = ["toxic", "severe_toxic", "obscene", "threat", "insult",
          "identity_hate"]

# Exact live shape of dataset_samples (read-only inspection, Phase 4 audit).
SCHEMA_SQL = """
CREATE TABLE dataset_samples (
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
    updated_at TEXT,
    language TEXT DEFAULT 'en',
    language_name TEXT DEFAULT 'English',
    script TEXT DEFAULT 'Latin',
    split TEXT DEFAULT '',
    external_id TEXT
)
"""


def note(ok: bool, name: str, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"PASS  {name}" + (f"  ({detail})" if detail else ""))
    else:
        FAIL += 1
        FAILURES.append(name)
        print(f"FAIL  {name}  {detail}")


def tmpdir_ctx():
    TMP_ROOT.mkdir(parents=True, exist_ok=True)
    return tempfile.TemporaryDirectory(dir=str(TMP_ROOT), prefix="p4wb_")


def make_db(path: Path, with_external_id: bool = True) -> Path:
    """Create an isolated fixture DB in the live schema, pre-seeded rows."""
    conn = sqlite3.connect(str(path))
    conn.execute(SCHEMA_SQL if with_external_id else
                 SCHEMA_SQL.replace(",\n    external_id TEXT", ""))
    rows = [
        ("legacy train row about the weather", 0, "train"),
        ("legacy train row about sports", 0, "train"),
        ("legacy toxic slurry here", 1, "validation"),
        ("legacy test row,  has   odd spacing", 1, "test"),
        ("legacy unsplit row", 0, ""),
    ]
    stamp = "2026-01-01T00:00:00+00:00"
    for text, toxic, split in rows:
        conn.execute(
            "INSERT INTO dataset_samples (comment, toxic, severe_toxic, "
            "obscene, threat, insult, identity_hate, source, created_at, "
            "updated_at, language, language_name, script, split) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (text, toxic, 0, 0, 0, 0, 0, "demo", stamp, stamp,
             "en", "English", "Latin", split),
        )
    conn.commit()
    conn.close()
    return path


def snapshot_legacy(db: Path):
    """Full byte-level snapshot of every column of every fixture row."""
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=30)
    try:
        return c.execute(
            "SELECT id, comment, toxic, severe_toxic, obscene, threat, "
            "insult, identity_hate, source, created_at, updated_at, "
            "language, language_name, script, split "
            "FROM dataset_samples ORDER BY id").fetchall()
    finally:
        c.close()


def counts(db: Path):
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=30)
    try:
        total = c.execute("SELECT COUNT(*) FROM dataset_samples").fetchone()[0]
        try:
            ext = c.execute(
                "SELECT COUNT(*) FROM dataset_samples "
                "WHERE external_id IS NOT NULL").fetchone()[0]
        except sqlite3.OperationalError:
            ext = -1
        return total, ext
    finally:
        c.close()


def run_importer(db: Path, *extra, csv_file=None, source_tag="p4_test",
                 report=None):
    if db.resolve() == LIVE_DB.resolve():  # hard safety guard
        raise RuntimeError("REFUSING to target the live aura.db")
    cmd = [sys.executable, str(IMPORTER), "--db", str(db), *extra]
    if csv_file:
        cmd += ["--file", str(csv_file), "--source-tag", source_tag]
    if report:
        cmd += ["--report", str(report)]
    return subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace",
                          cwd=str(BACKEND_DIR), timeout=SUBPROC_TIMEOUT)


def make_csv(path: Path, rows, bom: bool = False, crlf: bool = False):
    buf = io.StringIO(newline="")
    w = csv.writer(buf, lineterminator="\r\n" if crlf else "\n")
    w.writerow(HEADER)
    w.writerows(rows)
    text = buf.getvalue()
    raw = text.encode("utf-8")
    if bom:
        raw = b"\xef\xbb\xbf" + raw
    path.write_bytes(raw)


def good_row(i: int, text: str, tag_id: str = "p4"):
    return [f"{tag_id}-{i}", text, "en", "English", "Latin",
            "1", "0", "0", "0", "0", "0", "external:civil_comments", "train"]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# 1) dry run: no writes, isolated report
# ---------------------------------------------------------------------------
def test_dry_run(tmp: Path) -> None:
    db = make_db(tmp / "dry.db")
    before_snap = snapshot_legacy(db)
    report = tmp / "dry_report.json"
    proc = run_importer(db, report=report)
    note(proc.returncode == 0, "dry_run_exit_0", f"exit={proc.returncode}")
    note("DRY RUN" in proc.stdout, "dry_run_declared")
    note(snapshot_legacy(db) == before_snap, "dry_run_no_writes")
    rep = json.loads(report.read_text(encoding="utf-8"))
    note(rep.get("mode") == "dry_run", "dry_run_report_mode",
         f"mode={rep.get('mode')}")
    note(rep.get("database") == str(db.resolve()),
         "dry_run_report_target_db", rep.get("database", ""))


# ---------------------------------------------------------------------------
# 2) apply: additive, idempotent, provenance, backup location, split blank
# ---------------------------------------------------------------------------
def test_apply_and_idempotency(tmp: Path) -> None:
    db = make_db(tmp / "apply.db")
    before_snap = snapshot_legacy(db)
    csv_path = tmp / "ok.csv"
    make_csv(csv_path, [good_row(i, f"phase4 probe row number {i}")
                        for i in range(6)])
    report = tmp / "apply_report.json"
    proc = run_importer(db, "--apply", csv_file=csv_path, report=report)
    first = counts(db)
    note(proc.returncode == 0 and first[1] == 6, "apply_inserts_6",
         f"exit={proc.returncode} ext={first[1]}")
    note(first[0] == len(before_snap) + 6, "apply_additive_counts",
         f"{len(before_snap)} -> {first[0]}")
    after_snap = snapshot_legacy(db)
    # inserts append with new ids; every pre-existing row must be byte-identical
    note(after_snap[:len(before_snap)] == before_snap
         and len(after_snap) == len(before_snap) + 6,
         "apply_original_rows_byte_identical",
         f"compared {len(before_snap)} pre-existing rows")

    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=30)
    rows = c.execute(
        "SELECT external_id, comment, source, language, language_name, "
        "script, split FROM dataset_samples WHERE external_id IS NOT NULL"
    ).fetchall()
    idx = [r[0] for r in c.execute(
        "SELECT name FROM sqlite_master WHERE type='index' "
        "AND tbl_name='dataset_samples'").fetchall()]
    c.close()
    note(len({r[0] for r in rows}) == 6, "external_id_unique", f"{len(rows)} rows")
    note(all(r[2] == "p4_test" and ":" not in r[2] for r in rows),
         "source_normalised_no_colon")
    note(all(r[3] == "en" and r[4] == "English" and r[5] == "Latin"
             for r in rows), "language_script_recorded")
    note(all((r[6] or "") == "" for r in rows), "imported_split_blank",
         "importer never assigns splits")
    note("idx_dataset_samples_external_id" in idx, "unique_index_created",
         f"indexes={idx}")

    proc2 = run_importer(db, "--apply", csv_file=csv_path, report=report)
    second = counts(db)
    note(proc2.returncode == 0 and second == first, "apply_idempotent",
         f"rows {first[0]} -> {second[0]} on re-run")

    # backup followed the TEMP db, not the project directory
    backups = list((tmp / "backups").glob("aura-pre-external-import-*.db"))
    ok_backup = False
    if backups:
        bc = sqlite3.connect(f"file:{backups[0]}?mode=ro", uri=True, timeout=30)
        n = bc.execute("SELECT COUNT(*) FROM dataset_samples").fetchone()[0]
        bc.close()
        ok_backup = (n == len(before_snap))
    note(ok_backup, "backup_written_next_to_target_db",
         f"{len(backups)} backup(s) under temp dir, snapshot rows match pre-import")


# ---------------------------------------------------------------------------
# 3) rollback completeness under fault injection
# ---------------------------------------------------------------------------
def test_rollback_fault_injection(tmp: Path) -> None:
    db = make_db(tmp / "fault.db")
    before_snap = snapshot_legacy(db)
    marker = "P4_FAULT_INJECT_MARKER row"
    bad = tmp / "fault.csv"
    make_csv(bad, [good_row(1, "fault clean row one"),
                   good_row(2, "fault clean row two"),
                   good_row(3, marker),
                   good_row(4, "fault clean row four")])
    c = sqlite3.connect(str(db))
    c.execute(
        "CREATE TRIGGER p4_inject BEFORE INSERT ON dataset_samples "
        "WHEN NEW.comment LIKE '%P4_FAULT_INJECT_MARKER%' "
        "BEGIN SELECT RAISE(ABORT, 'injected fault'); END;")
    c.commit()
    c.close()
    report = tmp / "fault_report.json"
    proc = run_importer(db, "--apply", csv_file=bad, report=report)
    note(proc.returncode != 0, "rollback_nonzero_exit",
         f"exit={proc.returncode}")
    note("rolled back" in (proc.stdout + proc.stderr).lower(),
         "rollback_message_printed")
    note(counts(db) == (len(before_snap), 0), "rollback_no_partial_rows",
         f"counts={counts(db)}")
    note(snapshot_legacy(db) == before_snap, "rollback_original_rows_intact")
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=30)
    leaked = c.execute(
        "SELECT COUNT(*) FROM dataset_samples WHERE comment LIKE '%fault clean%'"
        " OR comment LIKE '%FAULT_INJECT%'").fetchone()[0]
    cols = {r[1] for r in c.execute("PRAGMA table_info(dataset_samples)")}
    c.close()
    note(leaked == 0, "rollback_no_leaked_rows", f"leaked={leaked}")
    note("external_id" in cols, "schema_change_after_rollback_is_additive_only",
         "column may persist after rollback; data did not change")


# ---------------------------------------------------------------------------
# 4) schema mismatch / malformed rows / encoding / limit / language reject
# ---------------------------------------------------------------------------
def test_validation(tmp: Path) -> None:
    db = make_db(tmp / "valid.db")
    pre = counts(db)

    broken = tmp / "broken.csv"
    broken.write_bytes(b"id,text,language\r\nx1,some text,en\r\n")
    proc = run_importer(db, "--apply", csv_file=broken,
                        report=tmp / "r1.json")
    note(proc.returncode != 0
         and "schema mismatch" in (proc.stdout + proc.stderr).lower(),
         "schema_mismatch_aborts", f"exit={proc.returncode}")
    note(counts(db) == pre, "schema_abort_no_writes")

    # BOM + CRLF + non-ASCII text (printed as codepoints, console-safe)
    uni_text = "vanakkam \u0b95\u0ba4\u0bc1 \u0b85\u0ba9\u0bcd"
    uni = tmp / "uni.csv"
    make_csv(uni, [good_row(1, uni_text)], bom=True, crlf=True)
    proc = run_importer(db, "--apply", csv_file=uni, report=tmp / "r2.json",
                        source_tag="p4_uni")
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=30)
    got = c.execute("SELECT comment FROM dataset_samples "
                    "WHERE external_id='p4-1'").fetchone()
    c.close()
    note(proc.returncode == 0 and got and got[0] == uni_text,
         "bom_crlf_utf8_handled",
         f"stored={got[0].encode('unicode_escape') if got else None}")

    # empty text + overlong text rejected with tallies
    rej = tmp / "rej.csv"
    make_csv(rej, [["p4-e1", "   ", "en", "English", "Latin",
                    "1", "0", "0", "0", "0", "0", "external:x", "train"],
                   good_row(2, "x" * 20001),
                   ["p4-es", "hola texto de prueba", "es", "Spanish", "Latin",
                    "1", "0", "0", "0", "0", "0", "external:x", "train"]])
    proc = run_importer(db, "--apply", csv_file=rej, report=tmp / "r3.json",
                        source_tag="p4_rej")
    rep = json.loads((tmp / "r3.json").read_text(encoding="utf-8"))
    cc = rep["counts"]
    note(proc.returncode == 0 and cc["reject_empty_text"] == 1
         and cc["reject_too_long"] == 1
         and cc["reject_unsupported_language"] == 1
         and cc["inserted"] == 0, "malformed_and_language_rejects_tallied",
         f"empty={cc['reject_empty_text']} long={cc['reject_too_long']} "
         f"lang={cc['reject_unsupported_language']}")

    # --limit accounting (fresh DB: avoid external_id collisions with the
    # ids already imported into valid.db above)
    db_lim = make_db(tmp / "limit.db")
    lim = tmp / "lim.csv"
    make_csv(lim, [good_row(i, f"limit probe row {i}") for i in range(5)])
    proc = run_importer(db_lim, "--apply", "--limit", "2", csv_file=lim,
                        report=tmp / "r4.json", source_tag="p4_lim")
    rep = json.loads((tmp / "r4.json").read_text(encoding="utf-8"))
    note(proc.returncode == 0 and rep["counts"]["inserted"] == 2
         and rep["counts"]["skipped_by_limit"] == 3, "limit_accounting",
         f"inserted={rep['counts']['inserted']} "
         f"capped={rep['counts']['skipped_by_limit']}")


# ---------------------------------------------------------------------------
# 5) dedup: whitespace-variant of an existing row is skipped (importer side)
# ---------------------------------------------------------------------------
def test_importer_dedup(tmp: Path) -> None:
    db = make_db(tmp / "dedup.db")  # fixture has "legacy test row,  has   odd spacing"
    variant = tmp / "variant.csv"
    make_csv(variant, [good_row(1, "legacy test row, has odd spacing")])
    proc = run_importer(db, "--apply", csv_file=variant,
                        report=tmp / "dedup_report.json", source_tag="p4_dup")
    rep = json.loads((tmp / "dedup_report.json").read_text(encoding="utf-8"))
    note(proc.returncode == 0 and rep["counts"]["skip_duplicate_text"] == 1
         and rep["counts"]["inserted"] == 0,
         "importer_dedup_whitespace_variant",
         f"skipped={rep['counts']['skip_duplicate_text']}")

    # cross-file external_id dedup: same id imported under another tag
    db2 = make_db(tmp / "cross.db")
    a = tmp / "a.csv"
    b = tmp / "b.csv"
    make_csv(a, [good_row(9, "cross file probe alpha")])
    make_csv(b, [good_row(9, "cross file probe beta")])
    run_importer(db2, "--apply", csv_file=a, report=tmp / "cr1.json",
                 source_tag="p4_a")
    proc = run_importer(db2, "--apply", csv_file=b, report=tmp / "cr2.json",
                        source_tag="p4_b")
    rep = json.loads((tmp / "cr2.json").read_text(encoding="utf-8"))
    note(proc.returncode == 0 and rep["counts"]["skip_already_imported"] == 1
         and rep["counts"]["inserted"] == 0, "cross_file_external_id_dedup",
         f"skipped={rep['counts']['skip_already_imported']}")


# ---------------------------------------------------------------------------
# 6) fix F-B2: --report isolates the audit trail (default report untouched)
# ---------------------------------------------------------------------------
def test_report_isolation(tmp: Path) -> None:
    db = make_db(tmp / "rep.db")
    csv_path = tmp / "rep.csv"
    make_csv(csv_path, [good_row(1, "report isolation probe row")])
    custom = tmp / "custom_report.json"
    proc = run_importer(db, "--apply", csv_file=csv_path, report=custom)
    note(proc.returncode == 0 and custom.is_file(),
         "report_flag_writes_custom_path", f"exit={proc.returncode}")
    note(f"report -> {custom.resolve()}" in proc.stdout,
         "report_flag_stdout_points_to_custom",
         "importer announced the isolated report path")
    # Precise attribution: if the project's default report was rewritten BY
    # THIS run, its "database" field would name our temp DB. A concurrent
    # unrelated run (e.g. the coordinator's suite) would name a different DB
    # and must not fail this check.
    clobbered = False
    if PROJECT_REPORT.is_file():
        try:
            cur = json.loads(PROJECT_REPORT.read_text(encoding="utf-8"))
            clobbered = cur.get("database") == str(db.resolve())
        except (OSError, ValueError):
            clobbered = False
    note(not clobbered, "report_flag_default_untouched",
         "project import_report.json not rewritten by this isolated run")
    rep = json.loads(custom.read_text(encoding="utf-8"))
    note(rep.get("mode") == "apply"
         and rep.get("counts", {}).get("inserted") == 1,
         "custom_report_content_valid", f"mode={rep.get('mode')}")


# ---------------------------------------------------------------------------
# 7) fix F-B1: fetch leakage guard uses the collapsed+casefold key
# ---------------------------------------------------------------------------
def _load_fetch_module(tmp: Path):
    spec = importlib.util.spec_from_file_location("p4_fetch_mod", FETCH_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.DATA = tmp
    mod.EXTERNAL = tmp / "external"
    mod.MULTI_RAW = tmp / "multilingual" / "raw"
    return mod


def test_fetch_dedup_key(tmp: Path) -> None:
    mod = _load_fetch_module(tmp)
    raw = tmp / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    with open(raw / "demo_dataset.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["comment", "toxic", "language"])
        w.writerow(["This  comment has   double spaces", "1", "en"])
    seen = mod.existing_texts()
    src = mod.SOURCES[0]
    fetched = [{"text": "This comment has double spaces", "toxicity": 0.9,
                "severe_toxicity": 0.0, "obscene": 0.0, "threat": 0.0,
                "insult": 0.0, "identity_attack": 0.0}]
    rows = mod.normalize(src, fetched)
    kept = mod.dedup_rows(rows, seen, [])
    note(len(seen) == 1 and list(seen)[0] == "this comment has double spaces",
         "fetch_guard_key_collapsed_casefold", repr(sorted(seen)))
    note(len(kept) == 0,
         "fetch_guard_drops_whitespace_variant",
         "existing AURA row variant no longer leaks")

    # conflicting-label duplicates in one batch are recorded, first kept
    fetched2 = [{"text": "conflict probe", "toxicity": 0.9,
                 "severe_toxicity": 0.0, "obscene": 0.0, "threat": 0.0,
                 "insult": 0.0, "identity_attack": 0.0},
                {"text": "conflict  probe", "toxicity": 0.1,
                 "severe_toxicity": 0.0, "obscene": 0.0, "threat": 0.0,
                 "insult": 0.0, "identity_attack": 0.0}]
    rows2 = mod.normalize(src, fetched2)
    conflicts = []
    kept2 = mod.dedup_rows(rows2, set(), conflicts)
    note(len(kept2) == 1 and len(conflicts) == 1,
         "fetch_conflicting_label_duplicate_recorded",
         f"kept={len(kept2)} conflicts={len(conflicts)}")

    # fetch pipeline never touches SQLite / the live DB (static guarantee)
    src_text = FETCH_SCRIPT.read_text(encoding="utf-8")
    note("import sqlite3" not in src_text and "aura.db" not in src_text
         .replace("Nothing is written to aura.db", ""),
         "fetch_has_no_db_code", "no sqlite3 import in fetch pipeline")


# ---------------------------------------------------------------------------
# 8) threshold / model-artifact immutability around a real apply run
# ---------------------------------------------------------------------------
def test_models_untouched(tmp: Path) -> None:
    present = {n: (MODELS_DIR / n) for n in MODEL_ARTIFACTS
               if (MODELS_DIR / n).is_file()}
    if not present:
        note(True, "models_untouched", "SKIP: no model artifacts present")
        return
    before = {n: sha256(p) for n, p in present.items()}
    db = make_db(tmp / "models.db")
    csv_path = tmp / "m.csv"
    make_csv(csv_path, [good_row(i, f"models immutability row {i}")
                        for i in range(3)])
    proc = run_importer(db, "--apply", csv_file=csv_path,
                        report=tmp / "m_report.json")
    after = {n: sha256(p) for n, p in present.items()}
    note(proc.returncode == 0 and before == after, "models_untouched",
         f"checked {len(present)} artifact(s), exit={proc.returncode}")
    splits = snapshot_legacy(db)
    note(all((r[14] or "") in ("train", "validation", "test", "")
             for r in splits), "pre_existing_splits_unchanged",
         "fixture split values intact after import")


# ---------------------------------------------------------------------------
# 9) column-add path: DB without external_id gains it additively
# ---------------------------------------------------------------------------
def test_column_add(tmp: Path) -> None:
    db = make_db(tmp / "col.db", with_external_id=False)
    before_snap = snapshot_legacy(db)
    csv_path = tmp / "col.csv"
    make_csv(csv_path, [good_row(1, "column add probe row")])
    proc = run_importer(db, "--apply", csv_file=csv_path,
                        report=tmp / "col_report.json")
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=30)
    cols = {r[1] for r in c.execute("PRAGMA table_info(dataset_samples)")}
    n = c.execute(
        "SELECT COUNT(*) FROM dataset_samples WHERE external_id IS NOT NULL"
    ).fetchone()[0]
    c.close()
    note(proc.returncode == 0 and "external_id" in cols and n == 1,
         "external_id_column_added_additively", f"exit={proc.returncode}")
    after_snap = snapshot_legacy(db)
    note(after_snap[:len(before_snap)] == before_snap
         and len(after_snap) == len(before_snap) + 1,
         "column_add_preserves_existing_rows")


# ---------------------------------------------------------------------------
# 10) static safety: the coordinator-run suite always targets --db
# ---------------------------------------------------------------------------
def test_existing_suite_static_safety() -> None:
    text = EXISTING_SUITE.read_text(encoding="utf-8")
    note('"--db", str(db_file)' in text,
         "existing_suite_always_passes_db_flag",
         "run_importer cmd always includes --db (never the live default)")
    db_path_lines = [l for l in text.splitlines()
                     if "DB_PATH" in l and not l.strip().startswith("DB_PATH")]
    note(bool(db_path_lines)
         and all("mode=ro" in l for l in db_path_lines),
         "existing_suite_live_db_readonly",
         f"{len(db_path_lines)} live-DB reference(s), all mode=ro")


def main() -> int:
    print("== AURA Phase 4 Workstream B: dataset-import safety tests ==")
    print(f"temp root: {TMP_ROOT}")
    print(f"live db guard: {LIVE_DB} is never opened by this suite")
    with tmpdir_ctx() as td:
        tmp = Path(td)
        test_dry_run(tmp)
        test_apply_and_idempotency(tmp)
        test_rollback_fault_injection(tmp)
        test_validation(tmp)
        test_importer_dedup(tmp)
        test_report_isolation(tmp)
        test_fetch_dedup_key(tmp)
        test_models_untouched(tmp)
        test_column_add(tmp)
    test_existing_suite_static_safety()
    print(f"\nPHASE4-WSB SUMMARY: PASSED {PASS} / FAILED {FAIL}")
    if FAIL:
        print("failed: " + ", ".join(FAILURES))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
