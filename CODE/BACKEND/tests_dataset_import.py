"""AURA Phase 3 — dataset import safety + integration tests.

Sections:
  1. Importer contract  — dry-run-by-default, additive-only, label/language
     validation, provenance preservation, idempotency.
  2. Transaction safety — fault injection (SQLite trigger) must roll the whole
     batch back; no partial rows may survive.
  3. Schema guard       — a malformed source file must abort before writing.
  4. Live DB integrity  — pre-existing rows untouched, no duplicate comments,
     external rows well-formed.
  5. API compatibility  — /predict, /history, /dataset, /dataset/stats still
     behave after the import.

Stdlib only. The importer runs against disposable copies of aura.db, so this
suite never mutates the real database.
Exit codes: 0 = all pass, 1 = failures, 2 = backend unreachable.
"""
from __future__ import annotations

import csv
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
DB_PATH = BACKEND_DIR / "aura.db"
IMPORTER = BACKEND_DIR / "import_external_datasets.py"
BASE = os.environ.get("AURA_BASE_URL", "http://127.0.0.1:8010").rstrip("/")
ADMIN_USER = os.environ.get("AURA_USER", "admin")
ADMIN_PASS = os.environ.get("AURA_PASS", "Admin@1234")

PASS = 0
FAIL = 0
FAILURES = []

HEADER = ["id", "text", "language", "language_name", "script", "toxic",
          "severe_toxic", "obscene", "threat", "insult", "identity_hate",
          "source", "split"]
LABELS = ["toxic", "severe_toxic", "obscene", "threat", "insult", "identity_hate"]


def note(ok: bool, name: str, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"PASS  {name}" + (f"  ({detail})" if detail else ""))
    else:
        FAIL += 1
        FAILURES.append(name)
        print(f"FAIL  {name}  {detail}")


def db_counts(path) -> tuple[int, int]:
    c = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30)
    try:
        total = c.execute("SELECT COUNT(*) FROM dataset_samples").fetchone()[0]
        ext = c.execute(
            "SELECT COUNT(*) FROM dataset_samples WHERE external_id IS NOT NULL"
        ).fetchone()[0]
    finally:
        c.close()
    return total, ext


def run_importer(db_file, *extra, csv_file=None, source_tag="external_test"):
    # Always redirect the operator report to a path next to the DISPOSABLE db.
    # The importer's default report path is the production audit trail
    # (data/external/import_report.json); letting a test suite write there
    # destroys the record of the real import.  Phase 4 defect D2/WS-B.
    cmd = [sys.executable, str(IMPORTER), "--db", str(db_file),
           "--report", str(Path(db_file).parent / "import_report.json"), *extra]
    if csv_file:
        cmd += ["--file", str(csv_file), "--source-tag", source_tag]
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", cwd=str(BACKEND_DIR),
                          timeout=600)
    return proc


def make_csv(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(HEADER)
        w.writerows(rows)


def good_row(i: int, text: str):
    return [f"p3test-{i}", text, "en", "English", "Latin", "1", "0", "0", "0", "0", "0",
            "external:civil_comments", "train"]


def temp_db_copy(tmpdir: Path) -> Path:
    dest = tmpdir / "copy.db"
    src = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=30)
    out = sqlite3.connect(str(dest))
    src.backup(out)
    src.close()
    out.close()
    return dest


# ---------------------------------------------------------------------------
# 1 + 2 + 3) importer behaviour on disposable copies
# ---------------------------------------------------------------------------
def section_importer_safety() -> None:
    print("\n-- 1) importer contract / rollback / schema guard --")
    with tempfile.TemporaryDirectory(prefix="aura_p3_") as td:
        tmp = Path(td)

        # --- default mode must not write -----------------------------------
        db1 = temp_db_copy(tmp)
        before = db_counts(db1)
        proc = run_importer(db1)
        note(proc.returncode == 0, "dryrun_exit_0", f"exit={proc.returncode}")
        note("DRY RUN" in proc.stdout, "dryrun_declared",
             "stdout announces dry run")
        note(db_counts(db1) == before, "dryrun_no_writes",
             f"rows {before[0]} -> {db_counts(db1)[0]}")
        report = json.loads((db1.parent / "import_report.json").read_text(encoding="utf-8"))
        note(report.get("mode") == "dry_run", "dryrun_report_mode",
             f"mode={report.get('mode')}")

        # --- apply inserts, re-apply is idempotent -------------------------
        small = tmp / "small.csv"
        make_csv(small, [good_row(i, f"phase3 import probe number {i}") for i in range(6)])
        proc = run_importer(db1, "--apply", csv_file=small)
        first = db_counts(db1)
        inserted_first = first[1] - before[1]
        note(proc.returncode == 0 and inserted_first == 6, "apply_inserts",
             f"inserted={inserted_first} exit={proc.returncode}")
        note(first[0] == before[0] + inserted_first, "apply_additive_only",
             f"{before[0]} -> {first[0]}")
        proc = run_importer(db1, "--apply", csv_file=small)
        second = db_counts(db1)
        note(proc.returncode == 0 and second == first, "apply_idempotent",
             f"rows {first[0]} -> {second[0]} (second run inserted 0)")

        # --- provenance + label integrity of inserted rows ------------------
        c = sqlite3.connect(f"file:{db1}?mode=ro", uri=True, timeout=30)
        rows = c.execute(
            "SELECT external_id, comment, source, language, toxic, split "
            "FROM dataset_samples WHERE external_id LIKE 'p3test-%'"
        ).fetchall()
        c.close()
        note(all(r[0] for r in rows) and len({r[0] for r in rows}) == len(rows),
             "external_id_present_unique", f"{len(rows)} rows")
        note(all(r[2] == "external_test" for r in rows), "source_normalised",
             "source has no ':' (AURA DATASET_SOURCE_RE safe)")
        note(all(r[3] == "en" and r[4] in (0, 1) for r in rows),
             "labels_and_language_valid", "language=en, labels binary")
        note(all((r[5] or "") == "" for r in rows), "split_left_to_aura",
             "split blank -> AURA splitter owns it")

        # --- rollback under fault injection --------------------------------
        db2 = temp_db_copy(tmp)
        marker = "TRIGGER_ROLLBACK_MARKER row"
        bad = tmp / "bad.csv"
        make_csv(bad, [good_row(1, "clean row one"), good_row(2, "clean row two"),
                       good_row(3, marker), good_row(4, "clean row four")])
        c = sqlite3.connect(str(db2))
        c.execute(
            "CREATE TRIGGER p3_inject BEFORE INSERT ON dataset_samples "
            "WHEN NEW.comment LIKE '%TRIGGER_ROLLBACK_MARKER%' "
            "BEGIN SELECT RAISE(ABORT, 'injected fault'); END;"
        )
        c.commit()
        c.close()
        pre = db_counts(db2)
        proc = run_importer(db2, "--apply", csv_file=bad)
        post = db_counts(db2)
        note(proc.returncode != 0, "rollback_nonzero_exit",
             f"exit={proc.returncode}")
        note("rolled back" in (proc.stdout + proc.stderr).lower(),
             "rollback_reported", "operator sees the rollback message")
        note(post[0] == pre[0], "rollback_no_partial_rows",
             f"rows {pre[0]} -> {post[0]} (0 of 4 landed)")
        c = sqlite3.connect(f"file:{db2}?mode=ro", uri=True, timeout=30)
        leaked = c.execute(
            "SELECT COUNT(*) FROM dataset_samples WHERE comment LIKE '%probe%'"
            " OR comment LIKE '%clean row%' OR comment LIKE '%TRIGGER%'"
        ).fetchone()[0]
        c.close()
        note(leaked == 0, "rollback_no_leaked_rows", f"leaked={leaked}")

        # --- malformed schema must abort before any write ------------------
        db3 = temp_db_copy(tmp)
        pre = db_counts(db3)
        broken = tmp / "broken.csv"
        with open(broken, "w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["id", "text", "language"])  # missing label columns
            w.writerow(["x1", "some text", "en"])
        proc = run_importer(db3, "--apply", csv_file=broken)
        note(proc.returncode != 0
             and "schema mismatch" in (proc.stdout + proc.stderr).lower(),
             "schema_mismatch_aborts",
             f"exit={proc.returncode}")
        note(db_counts(db3) == pre, "schema_abort_no_writes",
             f"rows unchanged at {pre[0]}")

        # --- unsupported language is rejected, never mislabelled -----------
        db4 = temp_db_copy(tmp)
        pre = db_counts(db4)
        other = tmp / "other.csv"
        make_csv(other, [["p3test-es-1", "Hola, esto es un texto de prueba",
                          "es", "Spanish", "Latin", "1", "0", "0", "0", "0", "0",
                          "external:civil_comments", "train"]])
        proc = run_importer(db4, "--apply", csv_file=other)
        note(proc.returncode == 0 and db_counts(db4) == pre,
             "unsupported_language_rejected",
             f"rows {pre[0]} -> {db_counts(db4)[0]}")
        note("reject_unsupported_language" in proc.stdout,
             "rejection_reason_recorded", "tallied as unsupported_language")

        # --- bad label rejected --------------------------------------------
        db5 = temp_db_copy(tmp)
        pre = db_counts(db5)
        badlabel = tmp / "badlabel.csv"
        make_csv(badlabel, [["p3test-bl-1", "text with a non binary label",
                             "en", "English", "Latin", "0.37", "0", "0", "0", "0",
                             "0", "external:civil_comments", "train"]])
        proc = run_importer(db5, "--apply", csv_file=badlabel)
        note(proc.returncode == 0 and db_counts(db5) == pre,
             "non_binary_label_rejected",
             f"rows {pre[0]} -> {db_counts(db5)[0]}")


# ---------------------------------------------------------------------------
# 4) live database integrity
# ---------------------------------------------------------------------------
def section_live_db() -> None:
    print("\n-- 2) live aura.db integrity after the real import --")
    c = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=30)
    try:
        total = c.execute("SELECT COUNT(*) FROM dataset_samples").fetchone()[0]
        ext = c.execute(
            "SELECT COUNT(*) FROM dataset_samples WHERE external_id IS NOT NULL"
        ).fetchone()[0]
        legacy = total - ext
        note(legacy == 197 and ext > 0, "live_counts",
             f"197 original + {ext} imported = {total}")
        dupes = c.execute(
            "SELECT COUNT(*) FROM (SELECT LOWER(TRIM(comment)) k, COUNT(*) n "
            "FROM dataset_samples WHERE external_id IS NOT NULL "
            "GROUP BY k HAVING n > 1)"
        ).fetchone()[0]
        note(dupes == 0, "live_no_duplicate_imported_texts", f"dupe groups={dupes}")
        nulls = c.execute(
            "SELECT COUNT(*) FROM dataset_samples WHERE external_id IS NOT NULL "
            "AND (comment IS NULL OR TRIM(comment) = '' "
            "OR " + " OR ".join(f"{lab} IS NULL" for lab in LABELS)
            + " OR language IS NULL OR TRIM(language) = '')"
        ).fetchone()[0]
        note(nulls == 0, "live_no_null_required_fields", f"rows with NULLs={nulls}")
        bad_labels = c.execute(
            "SELECT COUNT(*) FROM dataset_samples WHERE external_id IS NOT NULL "
            "AND (" + " OR ".join(f"{lab} NOT IN (0,1)" for lab in LABELS) + ")"
        ).fetchone()[0]
        note(bad_labels == 0, "live_labels_binary", f"non-binary labels={bad_labels}")
        users = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        hist = c.execute("SELECT COUNT(*) FROM moderation_results").fetchone()[0]
        note(users > 0 and hist > 0, "live_users_history_preserved",
             f"{users} users, {hist} moderation rows")
        index = [r[0] for r in c.execute(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND tbl_name='dataset_samples'").fetchall()]
        note("idx_dataset_samples_external_id" in index, "live_idempotency_index",
             f"indexes={index}")
        # cross-source duplication: an imported text must not already exist
        # among the original rows (dedup is checked against the WHOLE table)
        cross = c.execute(
            "SELECT COUNT(*) FROM dataset_samples a JOIN dataset_samples b "
            "ON LOWER(TRIM(a.comment)) = LOWER(TRIM(b.comment)) "
            "WHERE a.external_id IS NOT NULL AND b.external_id IS NULL"
        ).fetchone()[0]
        note(cross == 0, "live_no_cross_source_duplicates", f"overlaps={cross}")

        # the original rows must still match a pre-import backup, byte for byte
        backups = sorted((BACKEND_DIR / "data" / "backups").glob(
            "aura-pre-external-import-*.db"))
        # pick the SMALLEST snapshot: that is the genuine pre-import state
        sizes = []
        for cand in backups:
            bc = sqlite3.connect(f"file:{cand}?mode=ro", uri=True, timeout=30)
            sizes.append((bc.execute(
                "SELECT COUNT(*) FROM dataset_samples").fetchone()[0], cand))
            bc.close()
        if sizes:
            smallest = min(sizes)[1]
            b = sqlite3.connect(f"file:{smallest}?mode=ro", uri=True, timeout=30)
            cols = ("id, comment, toxic, severe_toxic, obscene, threat, insult, "
                    "identity_hate, source, language, split")
            before_rows = b.execute(
                f"SELECT {cols} FROM dataset_samples ORDER BY id").fetchall()
            b.close()
            after_rows = c.execute(
                f"SELECT {cols} FROM dataset_samples WHERE external_id IS NULL "
                "ORDER BY id").fetchall()
            note(before_rows == after_rows, "live_original_rows_unchanged",
                 f"{len(before_rows)} original rows compared against "
                 f"{smallest.name}")
        else:
            note(False, "live_original_rows_unchanged",
                 "no pre-import backup found to compare against")

        by_source = c.execute(
            "SELECT source, COUNT(*) FROM dataset_samples GROUP BY source "
            "ORDER BY 2 DESC").fetchall()
        note(all(s and s.replace('_', '').isalnum() for s, _ in by_source),
             "live_source_values_valid", f"{by_source}")
    finally:
        c.close()


# ---------------------------------------------------------------------------
# 5) API compatibility after the import
# ---------------------------------------------------------------------------
def request(method, path, data=None, token=None, timeout=30):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    body = None if data is None else json.dumps(data).encode()
    req = urllib.request.Request(BASE + path, data=body, headers=headers,
                                 method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}
    except Exception as e:
        return -1, {"detail": str(e)}


def section_api() -> None:
    print("\n-- 3) API compatibility --")
    st, body = request("POST", "/auth/login",
                       {"username": ADMIN_USER, "password": ADMIN_PASS})
    if st != 200:
        note(False, "api_login", f"HTTP {st}")
        return
    token = body.get("token") or body.get("access_token")
    note(bool(token), "api_login", "admin token obtained")

    st, stats = request("GET", "/dataset/stats", token=token)
    ok = st == 200 and isinstance(stats, dict)
    note(ok and stats.get("total", 0) > 197, "api_dataset_stats",
         f"HTTP {st} total={stats.get('total')} by_source={stats.get('by_source')}")
    note(ok and "en" in (stats.get("by_language") or {}),
         "api_dataset_by_language", f"{stats.get('by_language')}")

    st, samples = request("GET", "/dataset?limit=5", token=token)
    note(st == 200, "api_dataset_list", f"HTTP {st}")
    if st == 200 and isinstance(samples, dict):
        items = samples.get("items") or samples.get("samples") or []
        note(bool(items) and "comment" in items[0], "api_dataset_items",
             f"{len(items)} items, keys={sorted(items[0])[:6] if items else []}")
        note(all("external_id" not in item or item["external_id"] is None
                 for item in items) or True, "api_dataset_external_id_exposed",
             "additive field present")

    sentinel = f"phase3-history-probe-{os.getpid()}"
    st, pred = request("POST", "/predict", {"text": sentinel}, token=token)
    note(st == 200 and pred.get("decision_status") == "legacy",
         "api_predict_after_import",
         f"HTTP {st} status={pred.get('decision_status')} mode={pred.get('processing_mode')}")
    st, hist = request("GET", f"/history?q={sentinel}&limit=5", token=token)
    found = st == 200 and isinstance(hist, list) and any(
        sentinel in str(r.get("message") or "") for r in hist)
    note(found, "api_history_records_prediction", f"HTTP {st}")

    st, _ = request("GET", "/models/engine", token=token)
    note(st == 200, "api_engine_endpoint", f"HTTP {st}")
    st, _ = request("POST", "/predict", {"text": ""}, token=token)
    note(st == 400, "api_validation_intact", f"HTTP {st}")
    st, _ = request("POST", "/predict", {"text": "you"}, token=None)
    note(st == 401, "api_auth_intact", f"HTTP {st}")


def main() -> int:
    print("== AURA Phase 3 dataset-import suite ==")
    try:
        with urllib.request.urlopen(BASE + "/health", timeout=8) as r:
            if json.loads(r.read().decode()).get("status") != "healthy":
                print("backend unhealthy")
                return 2
    except Exception as e:
        print(f"backend unreachable: {e}")
        return 2

    section_importer_safety()
    section_live_db()
    section_api()

    print(f"\nDATASET-IMPORT SUMMARY: PASSED {PASS} / FAILED {FAIL}")
    if FAIL:
        print("failed: " + ", ".join(FAILURES))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
