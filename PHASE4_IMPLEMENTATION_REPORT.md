# AURA — Phase 4 Implementation Report

Phase 4 workstream: audit → confirm defects → apply only safe, evidence-backed
fixes. Companion documents: `PHASE4_BASELINE.md` (starting state),
`PHASE4_VERIFICATION_REPORT.md` (gate-by-gate evidence),
`PHASE4_WORKSTREAM_B/C/E.md` (per-workstream raw findings),
`PHASE4_CHECKSUMS.json` (before-state inventory), `PHASE4_CHANGED_FILES.json`
(change inventory).

---

## 1. Baseline findings (summary)

Full detail in `PHASE4_BASELINE.md`. Material points:

| Finding | Consequence for Phase 4 |
|---|---|
| **No git repository anywhere in the workspace** | Acceptance gate 7 cannot use `git diff`; replaced by a SHA-256 inventory of 85 files written *outside* the production data directory (`PHASE4_CHECKSUMS.json`) |
| `main.py` is a 141-byte wrapper (`from backend import app`) | The real application is `backend.py` (107 KB). Audit scope was corrected mid-phase before the adapter workstream audited the wrong file |
| `:8010` not listening at inspection | Started by this workstream; healthy, 42 OpenAPI operations |
| Docker / Celery / browsers running | Identified, **never touched** (Docker was already stopped during Phase 3 with user approval) |
| DB integrity `ok`, FK clean, splits 137/29/31 + 399 unassigned | Verified read-only; re-verified at the end |
| RAM 6,825 MB free, 211.9 GB disk | Recorded before any expensive test |

---

## 2. Confirmed defects and root causes

### Fixed in Phase 4

| ID | Sev | Location | Root cause | Before → After |
|---|---|---|---|---|
| **B-D1** | MEDIUM | `fetch_external_datasets.py:174` | The leakage guard built its "existing texts" set with `.strip().lower()` while the candidate check uses `dedup_key()` (whitespace-collapsed + `casefold`). Whitespace variants of already-present rows passed the guard — the same bug class Phase 3 fixed in `dedup_rows()`, missed in the set builder | Reproduced live: **pre-fix `LEAKED`, exit 1** → **post-fix `GUARDED`, exit 0**. Impact bounded (the importer re-dedups against the DB; a read-only scan found 0 duplicate-text groups) |
| **B-D2** | LOW→realised | `import_external_datasets.py:59,447-449` | Hard-coded report path meant any importer run overwrote `data/external/import_report.json`, the production audit trail | Added an **additive `--report` flag**; default behaviour byte-identical (the existing suite's assertion depends on the default) |
| **D-3** | MEDIUM | `tests_dataset_import.py:72,121` | **Extension of B-D2 that B deliberately left open:** the *suite* had no `--report`, so every run of `tests_dataset_import.py` still destroyed the production import report. I was the one who caused the observed damage — my concurrent suite run during this phase overwrote the genuine Phase 3 report with a test artifact pointing at `…\Temp\aura_p3__zbbje2a\copy.db` | `run_importer` now passes `--report` to a path beside the **disposable** temp DB, and the assertion reads that path. Proven: suite **still 40/40**, and `import_report.json` is **byte-identical before and after** the run (previously rewritten every run) |
| **C-F-3** | LOW | `model_adapter.py:77-82` | Coverage notes were *numerically correct for the deployed thresholds* (all 6 verified against `phase2_benchmark.json`, Δ≤0.0005) but named no threshold, so they appeared to contradict `phase3_benchmark.json`'s swept-0.25 figures | **Wording only**: "at the deployed threshold X" added to en/hi/ta-Latn/bn. **Every number byte-identical**; ta/ur untouched (already named theirs). Regression test added |
| **E-D2** | LOW | `DATASET_GUIDE.md:172` | Provenance typo `offenseval_dravilian` vs manifest `offenseval_dravidian` | Corrected |
| **E-D3** | LOW | `PROJECT_AUDIT_REPORT.md:498-507` | Duplicate `§16.4` heading and a stale "benchmark has not produced final numbers yet" contradicting `§16.3` | Renumbered `§16.6`; replaced with measured results, including the `tests_model_adapter.py` figure still marked "in progress" |
| **E-D4** | LOW | `PHASE2_MODEL_EVALUATION.md` ×9 lines | Mojibake — `?` substituted for —/≤/·/§ | Restored |
| **E-D5** | LOW | `PHASE2_MODEL_EVALUATION.md` | Two `§10.4` headings, out of sequence | Renumbered the import section to `§10.6` |

### Confirmed but **not** fixed — requires approval or is out of scope

| ID | Sev | Location | Finding | Why not fixed |
|---|---|---|---|---|
| **C-F-1** | **MEDIUM** | `model_adapter.py:237-241` vs `248-286` | The `"model is loading"` fast-fail is **dead code**: it sits inside `with self._lock:` while the loading thread holds that lock for the whole load, so a concurrent cold-load request **blocks a shared thread-pool worker** (~20-24 s observed) instead of falling back to legacy. The load itself has **no timeout** — an unbounded `from_pretrained` would block workers indefinitely | Single-flight is **clean** (N requests can never spawn N loads), so the mission's "no uncontrolled memory/CPU pressure" requirement is met. Fixing it changes production hot-path semantics and **breaks `tests_model_adapter.py:415-424`**, which requires the first warm-up predict to return a *model* result. Minimal fix is documented by Workstream C (lock-free status check above the `with`); **not applied without approval** |
| **C-F-2** | MEDIUM | `mlexicon.py:253-256` → `backend.py:766,859` | Unsupported **Latin-script** input (Swahili/Spanish) → `code="en"` → an English prediction with `processing_mode=existing_model`. `language_confidence_kind='script_ambiguous'` applies to *all* Latin input including genuine English, so **no field marks "unsupported"**. Non-Latin input *is* marked (`processing_mode='fallback'`) | Changing language labelling alters the production response contract. Reported, characterized by a test, **not silently changed** |
| **C-F-4** | LOW | `mlexicon.py:254` | Single-marker Tanglish → `en` → wrong threshold (0.55 vs 0.30) under the model engine; mitigated in legacy by inline romanised-Tamil LEX terms | Language-labelling change |
| **C-F-5** | LOW latent | `model_adapter.py:126-157` | One bad/missing global threshold silently discards **all** per-language thresholds (bare `except` + `threshold_rationale` AttributeError). Reproduced; the file is valid today | Threshold-loading semantics left alone per the "do not touch thresholds" constraint |
| **C-F-6** | LOW | `backend.py:818-832` | `set_engine` writes no `audit_logs` row, unlike every other admin action | Small behaviour change to an admin path; reported |

### Suspected and **rejected** with written reasoning

12 items were examined and rejected by Workstream B (TOCTOU, DDL-survives-rollback,
`casefold` vs `lower`, positional fetch ids, backup retention, whether the existing
suite can write `aura.db` — it cannot). Workstream E rejected: test-influenced
threshold selection (proven by checksum), metric-formula bugs (independently
re-derived), split leakage (0 duplicates / 0 reuse / 0 train overlap), timing
presented as fixed (it is labelled), and incompatible-task score combining.
Workstream C rejected a draft misreading of its own (the `experimental` status
applies only to unmeasured coverage).

---

## 3. Files changed and reasons

Source inventory: `PHASE4_CHANGED_FILES.json` — **75 unchanged, 10 changed, 10 added, 0 removed**
(scope: the same `.json .py .md .txt .db .bat` set the baseline snapshot covered;
the inventory file excludes itself).

### Changed

| File | Change | Reason |
|---|---|---|
| `CODE/BACKEND/fetch_external_datasets.py` | +353 B | B-D1 leakage-guard key fix |
| `CODE/BACKEND/import_external_datasets.py` | +466 B | B-D2 additive `--report` flag |
| `CODE/BACKEND/model_adapter.py` | +124 B | C-F-3 wording (threshold attribution); **no number changed** |
| `CODE/BACKEND/tests_dataset_import.py` | +317 B | D-3 stop the suite clobbering the audit trail |
| `CODE/BACKEND/data/external/import_report.json` | 1,344 → 2,163 B | Restored after being clobbered — see §4 |
| `PHASE2_MODEL_EVALUATION.md` | 12,657 → 14,697 B | E-D4 mojibake, E-D5 numbering, + statistical-confidence section |
| `DATASET_GUIDE.md` | 13,809 B (hash changed) | E-D2 typo (same byte length, hence identical size) |
| `PROJECT_AUDIT_REPORT.md` | 27,492 → 27,398 B | E-D3 stale/duplicate section |
| `CODE/BACKEND/aura.db` | 8.4 → 10.5 MB | Runtime rows only (§9); no schema or split change |
| `PHASE4_CHECKSUMS.json` | self | Re-written by the inventory pass |

### Added

| File | Purpose |
|---|---|
| `CODE/BACKEND/tests_dataset_import_phase4.py` | 42 assertions; temp DBs only; hard guard refusing the live DB path |
| `CODE/BACKEND/tests_model_adapter_phase4.py` | 33 weight-free tests (stubbed adapter, `:memory:` SQLite) |
| `CODE/BACKEND/tests_threshold_immutability.py` | 26 assertions; gates 1/2/8/9 |
| `CODE/FRONTEND/tests_e2e_phase4.py` | 35 end-to-end API→Streamlit checks |
| `PHASE4_BASELINE.md`, `PHASE4_WORKSTREAM_B.md`, `PHASE4_WORKSTREAM_C.md`, `PHASE4_WORKSTREAM_E.md`, `PHASE4_IMPLEMENTATION_REPORT.md`, `PHASE4_VERIFICATION_REPORT.md` | Deliverables |

**Protected artifacts, byte-identical to baseline:**

```
models/tuned_threshold.json  f31f4975d29a151f3f8737ae18875f6a5d11c2ee8719d126c587f7b339285c54
models/phase2_benchmark.json 5a9d94e267806ea0cae7fa83…
models/phase3_benchmark.json f3a5ceb488f4a9adc3488694…
```

---

## 4. The audit-trail damage I caused, and the repair

`data/external/import_report.json` recorded the real Phase 3 import (400 read,
399 inserted, 1 skipped, 0 rejected). My concurrent run of
`tests_dataset_import.py` during this phase **overwrote it** with a report for a
run against a disposable temp DB.

Repair, in two parts:

1. **Prevent recurrence** (D-3 above) — the suite now writes its report beside
   the temp DB. Verified by hash comparison across a full suite run.
2. **Restore the record honestly.** The file is now a **labelled
   reconstruction**, not raw importer output. It carries a `reconstruction`
   block stating exactly what happened, marks its `counts` as *transcribed* from
   the documented Phase 3 record (`DATASET_GUIDE.md` §8,
   `PROJECT_AUDIT_REPORT.md` §16.1) rather than re-executed, and includes a
   `verification_from_live_db` block read `mode=ro` at reconstruction time:
   399 external rows, `external_civil` 199 / `external_wiki` 200, all
   `split=''`, labels 367 non-toxic / 32 toxic.

Idempotency was re-proved afterwards: a dry-run reports `db_rows_before 596 →
db_rows_after 596`, `pre_existing_rows_untouched True`, nothing written.

---

## 5. Exact commands executed

All Python run as `C:\Users\gokul\OneDrive\Desktop\zip project\comment toxicity\.venv\Scripts\python.exe`
with `$env:PYTHONIOENCODING='utf-8'`; API suites with `$env:AURA_BASE_URL='http://127.0.0.1:8010'`.

**Workstream A (baseline)**
```powershell
git rev-parse --show-toplevel; git status --porcelain=v1      # fatal: not a git repository
python -  # snapshot script -> PHASE4_CHECKSUMS.json (85 files, sha256)
python -  # read-only PRAGMA integrity_check / foreign_key_check / table counts
Start-Process ... uvicorn main:app --host 127.0.0.1 --port 8010   # backend
```

**Workstream D (integration)**
```powershell
python -            # API contract probe, 15 input classes -> Temp\phase4_d\api_probe.json
python tests_e2e_phase4.py                                    # 35/35
```

**Required + new suites**
```powershell
python tests_dataset_import.py               # 40/40  (re-run after B's changes: 40/40)
python tests_word_input.py                   # 42/42
python tests_multilingual.py                 # 29/29 + 5/5
python ..\FRONTEND\tests_frontend_apptest.py # 35/35
python tests_model_adapter.py                # 110/110 (271.6s), re-run 110/110 (84.8s)
python tests_dataset_import_phase4.py        # 42/42
python tests_model_adapter_phase4.py         # 33/33
python tests_threshold_immutability.py       # 26/26
python ..\FRONTEND\tests_e2e_phase4.py       # 35/35
```

**Recovery after an external interruption**
```powershell
Get-NetTCPConnection -LocalPort 8010            # no listener
python -   # read settings: prediction_engine = hf   <-- interrupted test strand
Invoke-RestMethod POST /models/engine {"engine":"legacy"}   # restore mandated state
```

---

## 6. Before/after behaviour per fix

| Fix | Before | After |
|---|---|---|
| B-D1 | whitespace variant of an existing row **passes** the fetch leakage guard | same input **rejected** (exit 0 guard), key is whitespace-collapsed + casefolded |
| B-D2 | importer could only write one hard-coded report path | `--report PATH` honoured; default byte-identical |
| D-3 | every `tests_dataset_import.py` run overwrote `import_report.json` | suite run leaves the production report **byte-identical** (hash-compared) |
| C-F-3 | note read "held-out n=180: F1 0.245…" with no threshold stated | note reads "… at the deployed threshold 0.30"; **all numbers unchanged** |
| E-D2/D3/D4/D5 | typo, duplicate heading, stale claim, `?` glyphs | corrected; stale claim replaced with measured results |
| Interrupted-test strand | `prediction_engine=hf` in the live DB | restored to `legacy` via the API, confirmed by DB read **and** a live prediction returning `decision_status=legacy` |

---

## 7. Disclosed errors of my own (this phase)

Recorded because they bear on trust in the numbers:

1. **Killed the backend's parent process.** Stopping what looked like a redundant
   uvicorn instance killed its child too (both were one tree). Restarted
   immediately; data verified intact.
2. **Clobbered the production import report** by running the suite concurrently
   — see §4. Root cause fixed; record restored as a labelled reconstruction.
3. **Wrote 6 of 12 confidence intervals myself** instead of copying Workstream E's
   measured values when editing the Phase 3 report. Caught by re-reading
   `PHASE4_WORKSTREAM_E.md` §6 and replaced with E's exact figures:
   ta F1 [0.422,0.624], ta FPR [0.086,0.232], ta-Latn FPR [0.038,0.152],
   hi FPR [0.017,0.109], bn F1 [0.617,0.811], ur F1 [0.493,0.674].
4. **First `tests_e2e_phase4.py` run reported 3 failures that were my test's
   bugs**, not the product's: a missing auth token, and asserting the word
   "LEGACY" appears in a UI that correctly says `Processing: Existing Model`.
   Corrected the assertions rather than the product.
5. **Agent B and the evaluator both reported first-run failures in their own new
   test code** (B: 39→42; C: 5 failures with two wrong `decision_status`
   expectations the run itself disproved). Both corrected test code only; no
   assertion was weakened.

---

## 8. Not deployed / not retrained (explicit)

- **NOT deployed.** `models/tuned_threshold.json` is byte-identical
  (`f31f4975d29a151f…`, `tuned_at 2026-10-09T16:57:48`). `ta-Latn 0.25` and
  `bn 0.25` appear **only** inside the `phase3_benchmark.json` evaluation
  artifact, never in production config. Engine is `legacy`.
- **NOT retrained.** `training_runs` = 8 (baseline 8), active model
  `improved_v10` dated 2026-10-09, `model_versions` = 12, splits untouched at
  137/29/31 with all 399 imported rows still `split=''`.
- **No dataset import into production** occurred in Phase 4; `dataset_samples`
  = 596 (unchanged).
- **No unrelated service** was stopped, restarted or reconfigured.
