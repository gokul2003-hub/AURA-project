# AURA Phase 4 — Workstream B: Dataset-Import Pipeline Audit

Date: 2026-10-10
Scope: `CODE\BACKEND\import_external_datasets.py`, `CODE\BACKEND\fetch_external_datasets.py`,
`CODE\BACKEND\tests_dataset_import.py` (read-only), `CODE\BACKEND\data\external\*` meta/manifest files.
Mode: read-first audit; only CONFIRMED defects implemented.

---

## 1. Confirmed defects (fixed)

### D1 — MEDIUM — Fetch-stage leakage guard uses a weaker key than the dedup that consumes it
- **File:line (before):** `CODE\BACKEND\fetch_external_datasets.py:174`
  (`existing_texts()` added texts with `(row.get("text") or row.get("comment") or "").strip().lower()`)
  while the guard's consumer `dedup_rows()` (lines 207-227) checks candidates with
  `dedup_key()` = whitespace-collapsed + `casefold()` (line 196).
- **Root cause:** the Phase 3 fix that introduced `dedup_key()` (see its docstring,
  `fetch_external_datasets.py:189-196`) updated the in-batch comparison but missed the
  `existing_texts()` set builder. A fetched row that is a *whitespace variant* of an
  existing AURA training row (e.g. existing `"This  comment has   double spaces"` vs fetched
  `"This comment has double spaces"`) was not recognized as a duplicate and passed the
  "no data leakage" guard (`fetch_external_datasets.py:14`, `:207`).
- **Live reproduction (before fix):** demo script under
  `C:\Users\gokul\AppData\Local\Temp\opencode\phase4_wb\demo_fetch_dedup.py` →
  `existing_texts() set: ['this  comment has   double spaces']` →
  `rows kept by dedup_rows: 1` → `RESULT: LEAKED` (exit 1).
- **Fix:** line 174 now uses `dedup_key(...)` (same key as `dedup_rows`, the importer's
  `norm_text`, and effectively `ml_service.split_dataset`).
- **After fix:** same demo → `existing_texts() set: ['this comment has double spaces']` →
  `rows kept by dedup_rows: 0` → `RESULT: GUARDED` (exit 0). Regression-guarded by
  `tests_dataset_import_phase4.py` tests `fetch_guard_key_collapsed_casefold` /
  `fetch_guard_drops_whitespace_variant`.
- **Impact bounded, verified:** the importer re-dedups every row against the whole DB with the
  correct collapsed key (`import_external_datasets.py:87-89, 198-214, 316-327`), so nothing
  leaked into the live DB: read-only duplicate scan of `aura.db` found `dup_groups 0`
  (596 rows, command in §5). The residual harm was confined to the fetch-stage artifacts:
  `data/external/*.csv`, `*.meta.json` `duplicates_removed` counts, and especially the
  `--merge` splits (`data/external/splits/*.csv`, `fetch_external_datasets.py:336-340`), which
  bypass the importer entirely — hence MEDIUM, not LOW.

### D2 — LOW — Importer report path is hard-coded; every run (incl. test runs against temp DBs) clobbers the project's audit trail
- **File:line (before):** `import_external_datasets.py:59` (`REPORT_PATH`) used unconditionally
  at `:447-449`.
- **Evidence of harm (observed, not hypothetical):** the live artifact
  `data/external/import_report.json` does not describe the real import at all — it described a
  Phase 3 test-suite run against a temp DB (`"database": "...\\Temp\\aura_p3_0e7x3khm\\copy.db"`,
  file source `badlabel.csv`), and during this audit it was clobbered a second time by a
  concurrent coordinator run (`"...\\Temp\\aura_p3__zbbje2a\\copy.db"`, generated 2026-10-10T16:22Z).
  The genuine import audit trail is unrecoverable from that file.
- **Root cause:** the report destination ignores the `--db` target, so runs against disposable
  DBs overwrite the real DB's report.
- **Fix:** added an additive `--report PATH` CLI flag (`import_external_datasets.py:253-257`,
  `:450-452`, `:466`; docstring `:23-26`). **Default path is deliberately unchanged** because
  the coordinator-run suite depends on it (`tests_dataset_import.py:121-124` asserts the
  project report shows the last run's mode); redirecting the default would have broken a
  required suite, which I am forbidden to modify. My new suite passes `--report` on every
  invocation (`tests_dataset_import_phase4.py`, `run_importer()`).
- **Before/after:** before — any `--db /tmp/copy.db` run rewrote the project report; after —
  operators/tests can isolate it; without `--report`, behavior is byte-identical to before.
  Guarded by `report_flag_writes_custom_path`, `report_flag_stdout_points_to_custom`,
  `report_flag_default_untouched`, `custom_report_content_valid`.
- **Note for coordinator:** the existing suite still clobbers the default report by design of
  its own assertion (lines 121-124). Restoring a truthful live audit trail requires one
  operator-run `--apply` against the live DB (out of my scope/writes-prohibited).

---

## 2. Defects considered and REJECTED (with reasoning)

- **R1 (the critical safety check) — "existing tests can write to aura.db": REJECTED, NOT a defect.**
  Every importer invocation in `tests_dataset_import.py` passes an explicit temp-DB path:
  `run_importer` builds `cmd = [sys.executable, str(IMPORTER), "--db", str(db_file), *extra]`
  (`tests_dataset_import.py:72-79`); all call sites pass temp copies made via
  `src.backup(out)` with the source opened `file:{DB_PATH}?mode=ro` (`:94-101`).
  The live DB is otherwise opened read-only (`:61`, `:236`, both `mode=ro`).
  Static regression guards added: `existing_suite_always_passes_db_flag`,
  `existing_suite_live_db_readonly` (asserts every non-definition `DB_PATH` line contains
  `mode=ro`). The suite's API section (`:340-382`) does write `moderation_results` rows *via
  the backend's own /predict endpoint*, but that is the suite's intended live-integrity design
  run by the coordinator, not an importer path, and not something my changes affect.
- **R2 — `norm_text`/`dedup_key` use `casefold()` while `ml_service` uses `.lower()`**
  (`ml_service.py:525,536,997` vs `import_external_datasets.py:89`): non-defect. `casefold`
  is the strictly more aggressive key (superset for ASCII; differs only on a few Unicode
  cases like ß), so the importer can only over-skip, never under-dedup. Docstring says
  "mirrors ml_service" — imprecise wording, conservative direction, no fix applied.
- **R3 — TOCTOU: dedup decision reads one connection (`import_external_datasets.py:292-311`),
  insert uses a second (`:343-382`)**: rejected for a single-operator CLI. The partial UNIQUE
  index on `external_id` (`:188-195`) plus full rollback still guarantee no constraint
  violation survives; a concurrent run could only duplicate *text* (no DB constraint exists
  on comment text anywhere in AURA — `ml_service` dedup is application-level too). Documented
  here; not worth restructuring transaction boundaries for.
- **R4 — DDL (external_id column, UNIQUE index) survives a failed import**: non-defect by
  design (`ensure_external_id_column`/`ensure_idempotency_index`, `:174-195`, committed at
  `:297-298`/`:345-346` *before* `BEGIN IMMEDIATE` at `:347`). Additive-only, documented,
  verified by test `schema_change_after_rollback_is_additive_only`.
- **R5 — fetch `normalize()` uses positional ids `f"{name}-{i}"`** (`fetch_external_datasets.py:153`)
  instead of the upstream row id: rejected. HF rows-API pagination from offset 0 is stable, so
  ids are prefix-stable across `--limit` changes; even on upstream reorder, idempotency
  degrades safely to the importer's text-dedup (no duplicates possible). Changing the scheme
  now would churn the 399 provenance ids already stored.
- **R6 — live-import backups accumulate in `CODE\BACKEND\data\backups\` with no retention**:
  non-defect (intended location, `import_external_datasets.py:60,337-339`); temp-DB imports
  write backups next to the temp DB, verified by test `backup_written_next_to_target_db`.
  Retention/pruning is an operator-policy choice, not a correctness defect.
- **R7 — backup filename has second-granularity timestamp** (`:224-225`): two same-second
  imports would reuse the filename. Rejected: single-operator tool, ~seconds per run.
- **R8 — language matching is case-sensitive exact** (`:135-141`): non-defect; the failure
  direction is rejection-with-reason, never mislabelling — exactly what the module docstring
  promises (`:13-15`).
- **R9 — dead no-op** `if sum(labels.values()) == 0 and not any(...)` (`:155-156`): cosmetic.
- **R10 — dry run opens a read-write connection** (`:292`): non-defect; SELECT-only in
  default journal mode, creates no journal/WAL files, and `dry_run_no_writes` verifies a
  byte-identical table after a dry run.
- **R11 — `origin_source`/`origin_split` are parsed (`:166-167`) but never stored**: intentional
  per column-mapping docstring (`:35`: split is owned by AURA's splitter; the fetch source is
  normalized into `source`). Unused dict keys only; left alone.
- **R12 — on-disk `manifest.json` preprocessing strings are from an older code version** and
  `"sources": []` is vestigial: stale artifact, not a code defect; regenerated on next fetch.
  (Now partially moot: the current code's claimed "whitespace-collapsed casefolded key" dedup
  text is *true* after fix D1.)

---

## 3. Verification against the 8 audit questions (evidence)

1. **Input format/encoding/schema/language/malformed rows** — `read_source`
   (`import_external_datasets.py:110-171`): `utf-8-sig` (BOM-safe, `:113`), full-header
   schema check aborts before any DB write (`:116-121`), binary-label validation with
   per-reason tallies (`:100-107,142-154`), language whitelist with rejection reason
   (`:72-74,135-141`), empty/overlong text rejects (`:124-134`). Tests: `schema_mismatch_aborts`,
   `schema_abort_no_writes`, `bom_crlf_utf8_handled`, `malformed_and_language_rejects_tallied`.
2. **Duplicates/idempotency** — normalized key `norm_text` (`:87-89`); dedup vs DB + in-file +
   cross-file (`:313-327`); `external_id` preserved per original row with line-number fallback
   (`:157-159`); partial UNIQUE index `... WHERE external_id IS NOT NULL` (`:188-195`),
   confirmed present in live DB (`idx_sql` from read-only inspection). Tests:
   `apply_idempotent`, `external_id_unique`, `cross_file_external_id_dedup`,
   `importer_dedup_whitespace_variant`, `unique_index_created`.
3. **Transaction boundaries** — `BEGIN IMMEDIATE` (`:347`), single commit (`:376`), rollback +
   re-raise on any exception (`:377-380`); no DELETE/UPDATE/REPLACE anywhere in the importer
   (static read of full file); post-run additive verification via
   `SUM(LENGTH(comment)) WHERE external_id IS NULL` before/after (`:301-309, 391-397, 412-413`).
   Fault injection (SQLite `RAISE(ABORT)` trigger) on a self-built temp DB: exit 1,
   "rolled back" printed, counts (5,0), zero leaked rows, original rows byte-identical —
   tests `rollback_*` (6 assertions).
4. **Language/script/provenance** — stored per row: `language`, `language_name` (defaults to
   language), `script` (defaults "Unknown"), normalized `source` (colon-free,
   DATASET_SOURCE_RE-safe, `backend.py:18`), `external_id`, timestamps
   (`import_external_datasets.py:354-365`). Live DB read-only check: 399 external rows all
   `en`/`Latin`, 0 duplicate external_ids, 0 FK violations. Dataset URL/license provenance
   lives in `data/external/*.meta.json` + `manifest.json` (written by
   `fetch_external_datasets.py:308-331, 343-344`). Tests: `language_script_recorded`,
   `source_normalised_no_colon`.
5. **FAILED import rolls back completely** — YES, verified by code reasoning + fault
   injection (see §3.3). Only additive DDL may persist (by design, R4).
6. **Import cannot change splits/thresholds/production predictions** — importer inserts
   `split=''` (`:360`) and contains no UPDATE/DELETE; no reference to `tuned_threshold.json`,
   `phase2_benchmark.json`, `phase3_benchmark.json` in either pipeline file (grep evidence);
   `fetch_external_datasets.py` has **zero** DB code (`import sqlite3` absent; only the
   docstring mentions aura.db). Tests: `models_untouched` (SHA-256 of all 3 artifacts before/after
   a real `--apply` run), `imported_split_blank`, `pre_existing_splits_unchanged`.
   (Split *assignment* of the 399 `split=''` rows is done by `ml_service.split_dataset`
   (`ml_service.py:978-1021`) — untouched by me, as instructed.)
7. **Existing tests vs live DB** — NOT a defect; see R1. All importer invocations pin `--db`;
   live reads are `mode=ro`; my suite adds static regression guards.
8. **Backup handling** — live imports: `CODE\BACKEND\data\backups\aura-pre-external-import-<ts>.db`
   (intended, in-project); any `--db` elsewhere: `<db dir>/backups/` (`:337-339`) — verified by
   `backup_written_next_to_target_db`; dry runs create no backup (`:336` gate). Only the report
   file (D2) could pollute the project dir from temp-DB runs — fixed via `--report`.

---

## 4. Files changed

| File | Change | Why |
|---|---|---|
| `CODE\BACKEND\fetch_external_datasets.py` | `existing_texts()` now builds keys with `dedup_key()` (1 line + comment) | Confirmed defect D1 |
| `CODE\BACKEND\import_external_datasets.py` | Added `--report` flag (+ docstring note); report written to resolved path | Confirmed defect D2 (default behavior unchanged) |
| `CODE\BACKEND\tests_dataset_import_phase4.py` | NEW — 42-assertion suite, isolated temp DBs only, hard guard refusing the live DB path | Deliverable 1 |
| `PHASE4_WORKSTREAM_B.md` | This document | Deliverable 2 |

**Not touched:** the 5 coordinator-run suites, `aura.db` (read-only `mode=ro` URI inspection
only), `models/*` artifacts, `prediction_engine`/`model_adapter`/`backend.py`/`ml_service.py`,
all split assignments, production thresholds/routing.

## 5. Exact commands executed

```powershell
$env:PYTHONIOENCODING='utf-8'
# read-only live inspections
python C:\Users\gokul\AppData\Local\Temp\opencode\phase4_wb\inspect_live_ro.py
python C:\Users\gokul\AppData\Local\Temp\opencode\phase4_wb\schema_ro.py
python C:\Users\gokul\AppData\Local\Temp\opencode\phase4_wb\live_dupcheck_ro.py
# D1 before/after reproduction (before: exit 1 LEAKED; after: exit 0 GUARDED)
python C:\Users\gokul\AppData\Local\Temp\opencode\phase4_wb\demo_fetch_dedup.py
# new Phase 4 suite (final run)
python "...\CODE\BACKEND\tests_dataset_import_phase4.py"
# compile check
python -m py_compile import_external_datasets.py fetch_external_datasets.py tests_dataset_import_phase4.py
```
(Python = `C:\Users\gokul\OneDrive\Desktop\zip project\comment toxicity\.venv\Scripts\python.exe`;
every subprocess in the suite has a 120 s timeout; suite wall time ~30 s.)

## 6. Test counts

- **This workstream (`tests_dataset_import_phase4.py`): PASSED 42 / FAILED 0 / SKIPPED 0**
  (first run had 3 failures — all bugs in my own new test code: full-table snapshot compared
  across an import, and an external_id collision between two tests sharing a DB; fixed by
  prefix-snapshot comparison and a fresh fixture DB; no production code was weakened to pass).
- **D1 demo script:** before fix 1 leak reproduced (exit 1); after fix 0 leaks (exit 0).
- **NOT RUN by me (coordinator-owned, per instructions):** `tests_dataset_import.py`,
  `tests_model_adapter.py`, `tests_word_input.py`, `tests_multilingual.py`,
  `tests_frontend_apptest.py` — 5 suites, not run by me. (During this audit a concurrent
  coordinator run of `tests_dataset_import.py` was observed clobbering the project
  `import_report.json` and writing `aura.db` via the backend's /predict history — neither
  caused by, nor affecting, this workstream.)

## 7. Could not verify

- End-to-end truth of the on-disk `civil_comments.meta.json`/`manifest.json` numbers
  (would require re-fetching from the HF API; network fetch out of scope, and `fetched_rows`
  provenance is recorded at fetch time).
- Behavior of the 5 coordinator-run suites (deliberately not run); my static checks assert
  their live-DB access pattern is `mode=ro` + explicit `--db`, but only the coordinator's
  actual runs can produce their pass/fail counts.
- Concurrent multi-operator imports (R3) — reasoned about, not stress-tested.
