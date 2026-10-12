# AURA — Phase 4 Baseline (Workstream A)

Captured **2026-10-10 (UTC)** before any Phase 4 code change.
Purpose: establish an independently verifiable starting state so that every later
Phase 4 claim can be diffed against it.

---

## 1. Repository and version control

| Item | Finding | Evidence |
|---|---|---|
| Git repository | **NONE** — the workspace is not a git repository and never was | `git rev-parse --show-toplevel` → `fatal: not a git repository (or any of the parent directories): .git` |
| Active branch | Not applicable | same command output |
| Git status / diff | Not available | same command output |

**Consequence for acceptance gate 7** ("Git diff and changed-file list contain only
intentional changes"): a git diff cannot be produced. Phase 4 therefore uses a
**manual change inventory** instead — see §4.

### Repository root (`.venv` excluded)

| Entry | Type | Size |
|---|---|---|
| `.venv/` | directory | local virtualenv |
| `CODE/` | directory | all application code |
| `AURA_COMPLETE_WORK_REPORT.md` | report | 12.4 KB |
| `DATASET_GUIDE.md` | report | 13.5 KB |
| `PHASE2_MODEL_EVALUATION.md` | report | 12.4 KB |
| `PROJECT_AUDIT_REPORT.md` | report | 26.8 KB |
| `test.txt` | scratch file | 7.3 KB |

### Dependency manifests (project-owned only)

- `CODE/BACKEND/requirements.txt`
- `CODE/FRONTEND/requirements.txt`

No `pyproject.toml`, `Pipfile`, `package.json` or lockfile exists at project level
(the only matches found were inside `.venv/site-packages`, i.e. third-party).
There is therefore **no configured linter, formatter, static-analysis or build
step** in this repository — see §8.

### Test scripts discovered (paths confirmed, not assumed)

| File | Lines | Notes |
|---|---|---|
| `CODE/BACKEND/tests_dataset_import.py` | — | required suite |
| `CODE/BACKEND/tests_model_adapter.py` | 46.3 KB | required suite; needs model RAM |
| `CODE/BACKEND/tests_multilingual.py` | 31.8 KB | required suite |
| `CODE/BACKEND/tests_word_input.py` | — | required suite |
| `CODE/FRONTEND/tests_frontend_apptest.py` | 7.0 KB | required suite; Streamlit `AppTest` in-process |

No other `tests_*.py` exist. `pytest` is not installed; all suites are stdlib
`unittest`-style scripts run directly with the venv interpreter.

### Application layout (important correction)

`CODE/BACKEND/main.py` is a **141-byte wrapper**:

```python
from backend import app

if __name__ == '__main__':
    import uvicorn
    uvicorn.run('main:app', host='127.0.0.1', port=8000, reload=True)
```

The real FastAPI application is **`CODE/BACKEND/backend.py` (107.2 KB)**.
Largest sources: `backend.py` 107.2 KB, `ml_service.py` 62.6 KB,
`tests_model_adapter.py` 46.3 KB, `tests_multilingual.py` 31.8 KB,
`model_adapter.py` 19.0 KB, `mlexicon.py` 16.2 KB.

---

## 2. Processes and service health

Inspected **non-disruptively** (CIM process queries + HTTP GET only).

### Project services

| Port | State at inspection | Action taken |
|---|---|---|
| `:8010` FastAPI backend | **not listening** | Started by this workstream (`uvicorn main:app --host 127.0.0.1 --port 8010`, hidden window) → `healthy / aura-backend` |
| `:8000` | not listening | none |
| `:8501` / `:8502` Streamlit | not listening | none — the frontend suite uses in-process `streamlit.testing.v1.AppTest`, no server required |

### Unrelated services (identified, deliberately untouched)

| Process class | State | Handling |
|---|---|---|
| Docker (`com.docker.backend`) | **not running** | Stopped during Phase 3 with explicit user approval. **Not restarted, not touched in Phase 4.** |
| Celery / Blockchain Framework uvicorn `:8000` | **not running** | Untouched |
| Browser (`chrome`), `opencode-cli`, `OpenCode` | running | Untouched |

No unrelated service was stopped, restarted or reconfigured during Phase 4.

### Resource contention recorded before expensive tests

| Resource | Value |
|---|---|
| RAM total | 16,009 MB |
| RAM free at baseline | **6,825 MB** (first reading 7,431 MB) |
| Free disk `C:` | 211.9 GB |
| Free disk `P:` | 32.2 GB |
| Model process running at baseline | none (safe to run one model load at a time) |

---

## 3. SQLite database — read-only inspection

Opened with `file:aura.db?mode=ro` (URI read-only). No writes performed for
this section.

| Check | Result |
|---|---|
| `PRAGMA integrity_check` | **ok** |
| `PRAGMA foreign_key_check` | **clean** (empty result) |
| File size | 8,200 KB (`aura.db`) |
| SHA-256 | `292531128ec79ef67b8e…` |

### Tables and row counts (11 tables)

| Table | Rows |
|---|---|
| `audit_logs` | 828 |
| `dataset_samples` | 596 |
| `feedback` | 5 |
| `live_events` | 16 |
| `live_sessions` | 6 |
| `model_versions` | 12 |
| `moderation_results` | 808 |
| `settings` | 2 |
| `sqlite_sequence` | 7 |
| `training_runs` | 8 |
| `users` | 13 |

### Settings / production state

| Key | Value |
|---|---|
| `prediction_engine` | **`legacy`** |
| `toxicity_threshold` | `0.5` |

### Split assignments (must not change)

| split | rows |
|---|---|
| `train` | **137** |
| `validation` | **29** |
| `test` | **31** |
| `''` (unassigned, the 399 imported rows) | **399** |

Matches the Phase 3 baseline exactly (137/29/31 + 399 unassigned).

### Backups present (pre-import, genuine)

- `data/backups/aura-pre-external-import-20261009-223341.db` — 6,008 KB
- `data/backups/aura-pre-external-import-20261009-223359.db` — 6,008 KB

> **Note on row-count drift:** `users` (13) and `moderation_results` (808) are
> higher than the early-Phase-3 figures (11 / 748). This is expected: the Phase 3
> regression suites deliberately create throwaway accounts and moderation records
> against the live stack. Rows were added, never deleted or modified. Phase 4
> records counts again after the suites run (§9 of the verification report) and
> attributes any delta.

---

## 4. Configuration checksum snapshot (manual change inventory)

Because there is no git, a SHA-256 snapshot of **85 files** (`.py .json .md .txt
.bat .html .css .js .cfg .toml .yml .yaml .db`, `.venv`/`__pycache__` excluded)
was written **outside the production data directory** to:

```
C:\Users\gokul\OneDrive\Desktop\zip project\comment toxicity\PHASE4_CHECKSUMS.json
```

Key artifacts captured:

| File | SHA-256 (first 20) | Bytes |
|---|---|---|
| `CODE/BACKEND/models/tuned_threshold.json` | `f31f4975d29a151f3f87` | 2,886 |
| `CODE/BACKEND/models/phase3_benchmark.json` | `f3a5ceb488f4a9adc348` | 40,509 |
| `CODE/BACKEND/models/phase2_benchmark.json` | `5a9d94e267806ea0cae7` | 13,073 |
| `CODE/BACKEND/aura.db` | `292531128ec79ef67b8e` | 8,396,800 |
| `CODE/BACKEND/backend.py` | (see snapshot) | 107.2 KB |
| `CODE/BACKEND/main.py` | `4f62fe16138228a776a5` | 141 |
| `CODE/BACKEND/model_adapter.py` | `7de42400d1acd35d49c7` | 19,479 |
| `CODE/BACKEND/ml_service.py` | `f3317358d10d1cba7dd8` | 64,070 |
| `CODE/BACKEND/import_external_datasets.py` | `f728fb85d074fe989412` | 18,707 |
| `CODE/BACKEND/tests_dataset_import.py` | `4557202b6ca50fc6d35b` | 18,312 |
| `CODE/BACKEND/tests_model_adapter.py` | `8cabbbe11739b7f62087` | 47,375 |
| `CODE/BACKEND/benchmark_phase3.py` | `dda58f90466846c332a2` | 11,708 |
| `CODE/BACKEND/fetch_external_datasets.py` | `6b575030b84e3d1bb752` | 13,845 |
| `PHASE2_MODEL_EVALUATION.md` | `b5744dd5f0774125107c` | 12,657 |
| `DATASET_GUIDE.md` | `a66b297d94961bc38857` | 13,809 |
| `PROJECT_AUDIT_REPORT.md` | `5c16dcda447ade182916` | 27,492 |

**Phase 3 baseline cross-check:** the `tuned_threshold.json` hash prefix
`f31f4975d29a151f` matches the value recorded at the end of Phase 3 — the
threshold file is byte-identical, i.e. **unchanged across the Phase 3→4 boundary**.

### Threshold content recorded at baseline (read-only)

```
global threshold : 0.35
per_language     : en 0.55, ta 0.40, ta-Latn 0.30, hi 0.35, bn 0.30, ur 0.40
selection rule   : max toxic F1 with validation FPR <= 0.15 (tie-break higher threshold)
fpr_cap          : 0.15
val_rows         : 695 (en 120, ta 120, ta-Latn 120, hi 120, bn 95, ur 120)
tuned_at         : 2026-10-09T16:57:48        source: phase2
```

Phase 4 prohibition to enforce: **ta-Latn 0.25 and bn 0.25 must not be adopted.**

---

## 5. Model and training state (no retraining permitted)

| Item | Baseline value |
|---|---|
| Active NB model | `multinomial_nb_improved` / `improved_v10`, status `active` |
| Training date | `2026-10-09T09:22:52Z` (before Phase 4) |
| Reported metrics | accuracy 0.677, precision 0.602, recall 0.552, F1 0.539, CM `[[19,2],[8,2]]`, train 137 / val 29 / test 31 |
| `model_versions` rows | 12 |
| `training_runs` rows | 8 |
| Transformer adapter status | `not_loaded`, `weights_available=false`, `error=null` |
| `/settings` | `{toxicity_threshold: 0.5}` only |

No training endpoint was called during baseline capture.

---

## 6. Baseline API contract (live probe, read-only of production state)

Backend `healthy / aura-backend`, **42 OpenAPI operations** (matches the figure
corrected during Phase 3; the older "46" counted FastAPI's built-in doc routes).

Auth probed with the local dev admin account (credential **not** reproduced here):

| Probe | Result |
|---|---|
| `POST /auth/login` valid | HTTP 200, token length 64 |
| `POST /auth/login` invalid | HTTP 401 `{"detail": …}` |
| `GET /health` (no auth) | 200 `{"status":"healthy","service":"aura-backend"}` |
| `GET /models/engine` | `engine=legacy`, `default=legacy`, `source=settings`, `modes=[legacy,auto,hf]` |

Prediction contract, 15 synthetic inputs (empty, whitespace, ASCII, Tamil script,
Tanglish, Hindi, Bengali, Urdu, Swahili, Spanish, Chinese, SQL-injection probe,
XSS probe, emoji, zero-width/RTL, 6 KB long text):

| Observation | Result |
|---|---|
| HTTP statuses | 400 for empty/whitespace; 200 for all non-empty inputs |
| `decision_status` | **`legacy` on every 200 response** (single distinct value) |
| `model_name` | **`aura-legacy-rules-lexicon` on every 200 response** (single distinct value) |
| `toxicity_score` | **absent from every response** |
| Response key sets | **exactly 1 distinct key set across all 14 successful responses** (49 keys) — schema is uniform |
| Malformed JSON / wrong type / no body | HTTP 422 with FastAPI validation detail |
| Missing `text` field | HTTP 400 with a human-readable message |

Language handling observed at baseline:

| Input class | `language` | `language_code` | `language_confidence_kind` | `processing_mode` |
|---|---|---|---|---|
| English | English | `en` | `script_ambiguous` (`confidence=null`) | `existing_model` |
| Tamil script | Tamil | `ta` | `script_share` (`confidence=1.0`) | `language_lexicon` |
| Hindi / Bengali / Urdu | Hindi / Bengali / Urdu | `hi`/`bn`/`ur` | script-driven | `language_lexicon` |
| Swahili, Spanish (Latin, unsupported) | **English** | `en` | `script_ambiguous` (`confidence=null`) | `existing_model` |
| Chinese (unsupported) | Unknown | `und` | `no_signal` | **`fallback`** |
| Emoji-only | Unknown | `und` | `no_signal` | **`fallback`** |

**Open question handed to Workstream C:** unsupported *Latin-script* languages are
headlined as `English` and are not marked "unsupported"; the only disclosure is
`language_confidence=null` + `language_confidence_kind="script_ambiguous"`.
Unsupported *non-Latin* input does get `Unknown` + `processing_mode=fallback`.
This asymmetry is recorded as a finding to be confirmed in code, not silently
"fixed" — changing language labelling would alter the production response contract.

---

## 7. Phase 3 figures to preserve and independently re-verify

These are **claims carried over from Phase 3**; Phase 4 treats them as unverified
until Workstream E cross-checks them against `models/phase3_benchmark.json`.

| Claim | Value |
|---|---|
| Tanglish (`ta-Latn`) F1 | 0.313 |
| Bengali (`bn`) FPR | 0.178 |
| Urdu (`ur`) FPR | 0.256 |
| FPR budget | 0.15 (bn and ur exceed it) |
| Pooled validation rows | 695 |
| Reported suites | dataset import 40/40, model adapter 110/110, word input 42/42, multilingual 29/29 + 5/5, frontend 35/35 |
| Benchmark artifact | `CODE/BACKEND/models/phase3_benchmark.json` (40,509 bytes, present ✓) |
| Engine | legacy; live response `decision_status=legacy`, no `toxicity_score` ✓ re-confirmed |
| Thresholds | byte-identical to Phase 2 ✓ re-confirmed by SHA-256 |
| Splits | 137/29/31 + 399 unassigned ✓ re-confirmed |
| Naive Bayes retraining | none since `2026-10-09T09:22:52Z` ✓ re-confirmed |

---

## 8. Constraints adopted for Phase 4

Enforced throughout; violation of any item invalidates the phase:

1. FastAPI + SQLite + Streamlit preserved; production engine stays `legacy`.
2. No Naive Bayes retraining, no unapproved training pipeline.
3. No production threshold change; `tuned_threshold.json` stays byte-identical.
4. No split modification; the 399 unassigned rows stay unassigned.
5. No dataset import into production; no unnecessary user-data modification.
6. No stopping/restarting/reconfiguring of unrelated services, browsers, OpenCode
   processes, Docker or Celery workers without explicit approval.
7. No deployment, no live-model replacement, no production routing change.
8. No fabricated outputs, language support, metrics, screenshots or test results.
9. Database records, audit history, authentication and API contracts preserved.
10. No credentials, tokens, personal information or dataset-sensitive content in
    any report.
11. Adopting **ta-Latn 0.25** or **bn 0.25** in production is explicitly forbidden.

---

## 9. Baseline verdict

| Gate item | Baseline status |
|---|---|
| Services identified and healthy | ✅ backend `healthy`, 42 operations |
| Unrelated services untouched | ✅ Docker/Celery already stopped; browsers untouched |
| DB integrity | ✅ `integrity_check=ok`, `foreign_key_check` clean |
| Record counts captured | ✅ 11 tables recorded |
| Threshold file snapshotted outside production data dir | ✅ `PHASE4_CHECKSUMS.json` (85 files) |
| Model/training state captured | ✅ `improved_v10`, no retraining |
| Change-inventory mechanism established | ✅ manual SHA-256 inventory (no git exists) |
| Contention recorded before expensive tests | ✅ 6,825 MB free, 211.9 GB disk, no model process |

Everything below this line was recorded from actual command output. No figure in
this document is estimated or inferred.
