# AURA — PROJECT AUDIT REPORT

> **Generated:** 2026-10-09 · **Scope:** full-project audit, repair, dataset
> expansion (Phase 4), word-level/text input verification (Phase 5), tests.
> Working tree: `C:\Users\gokul\OneDrive\Desktop\zip project\comment toxicity`

---

## 1. Project overview & technology stack

**Purpose:** multilingual comment-toxicity detection & moderation platform.
Text in → language detection → toxicity classification → label, per-category
scores, confidence, decision (ALLOW/WARN/QUARANTINE/RESTRICT/TEMPORARY_BLOCK/
HUMAN_REVIEW), persisted to history with analytics, dataset management, model
training, voice and live-guard pipelines.

| Layer | Technology |
|---|---|
| Backend | FastAPI + Uvicorn (`CODE/BACKEND/backend.py`, entry `main.py`) |
| Database | SQLite `aura.db` (additive migrations only) |
| ML service | `ml_service.py` — pure-Python Naive Bayes (baseline + improved), model registry, background training jobs |
| Multilingual | `mlexicon.py` — script-based language detection + per-language lexicon matcher (stdlib) |
| Frontend | Streamlit (`CODE/FRONTEND/app.py`), 16 nav pages, admin-guarded |
| Tests | stdlib test scripts (`tests_multilingual.py`, `tests_word_input.py`, `tests_frontend_apptest.py`) — pytest not installed |
| Env | `.venv` Python 3.14.3; fastapi 0.142.2, uvicorn 0.54.0, streamlit 1.65.0, pandas 3.0.6, numpy 2.5.3 |
| Ports | Backend **8010** (8000 occupied by an unrelated project), Frontend **8501** |

Architecture: `Streamlit UI → FastAPI /predict|/moderate → run_engine() →
{rule/lexicon engine (English & 11 languages)} → SQLite → history/analytics/
dataset/model endpoints → UI`.

---

## 2. Component & module inventory

**Backend — 42 routes (all registered in `backend.py`):**

| Group | Endpoints |
|---|---|
| Core | `GET /`, `/health` |
| Auth | `POST /auth/login`, `POST /auth/register` (token-based, role-guarded) |
| Prediction | `POST /moderate`, `POST /predict`, `POST /predict/batch` |
| History/Comments | `GET /history` (q,label,category,source,language,date,confidence filters), `GET /comments/me` |
| Admin | `GET /admin/overview`, `/admin/comments`, `/admin/human-review`, `POST /admin/human-review/{id}`, `GET /admin/users`, `POST /admin/block-user`, `POST /admin/verify/{id}` |
| Analytics | `GET /analytics` |
| Feedback | `POST /feedback`, `GET /feedback` |
| Settings | `GET /settings`, `PUT /settings` |
| Dataset | `GET/POST /dataset`, `PUT/DELETE /dataset/{id}`, `GET /dataset/stats` |
| Models | `GET /models`, `/models/performance`, `/models/compare`, `/models/split`, `POST /models/train`, `GET /models/train/{id}` |
| Voice | `POST /voice/transcribe`, `POST /voice/predict` |
| Live guard | `POST /live/start|chunk|stop`, `GET /live/sessions`, `GET /live/{id}` |
| Model engine (Phase 2) | `GET/POST /models/engine`, `GET /models/adapter` (admin-only) |

**Frontend — 16 pages (all render, admin-guarded):** Login, Admin Dashboard,
Human Review, All Comments, User Profiles, Text Detection, Batch, Voice, Live
Guard, Analytics, History, Dataset Mgmt, Model Performance, Model Versions,
Training, System Settings, Feedback Review.

**Data pipelines:** demo CSV (100) + multilingual curated demo (96) → SQLite
`dataset_samples` (197) → deterministic 70/15/15 split (seed 42) → Naive Bayes
training → model registry (`data/processed/*.json`) → served predictions.
New: external HF datasets → `data/external/**` (this audit).

**Functions:** `classify()`, `analyse()`, `result()`, `run_engine()`,
`apply_language_engine()`, `multilingual_decision()`, `is_ambiguous_for_review()`,
plus 66 `ml_service` functions (CRUD, split, train, evaluate, registry, jobs).

---

## 3. Feature status

| Feature | Status | Evidence |
|---|---|---|
| Backend health/root | **PASS** | `GET /health` → `healthy` |
| Auth login/register, role guard | **PASS** | login OK in all 3 suites; protected routes return 401 without token (verified) |
| `/predict` single text | **PASS** | contract fields present in all cases |
| `/predict/batch` | **PASS** | 6-item mixed-language batch returns 6 contract-complete items |
| `/moderate` legacy | **PASS** | regression sweep in `tests_multilingual.py` |
| Multilingual detection (12 languages) | **PASS** | 29/29 matrix |
| Language → lexicon scoring | **PASS** | `language_lexicon` mode, labels correct |
| Unsupported language fallback | **PASS** | `你好世界` → `und`/`fallback`, conservative |
| Empty/invalid input validation | **PASS** | HTTP 400 with meaningful messages |
| History + language filter | **PASS** | E2E check + UI test 14/16 |
| Analytics (incl. language distribution) | **PASS** | E2E check + UI test 15 |
| Dataset CRUD + stats + filters | **PASS** | E2E + UI test 12 |
| Model training (real run) | **PASS** | job `improved_v10` completed, metrics measured |
| Model performance / by-language | **PASS** | unmeasured = literal "Not evaluated" |
| Frontend 16 pages render | **PASS** | 35/35 AppTest |
| Voice / Live (API lifecycle) | **PASS** | tested via API in existing suite; camera/mic hardware not automatable |
| Word-level & text identification (Phase 5) | **PASS** | **42/42** new suite |
| External dataset integration (Phase 4) | **PARTIAL** | 2 CC0 datasets fetched (400-row smoke subset) + pipeline; import to DB is a documented manual step; larger pulls & Indic-language datasets remain |
| Multilingual transformer model | **NOT IMPLEMENTED** | documented as out of scope — non-English is honest lexicon heuristics (`confidence_kind: heuristic`) |
| pytest / lint tooling | **NOT PRESENT** | project uses standalone stdlib test scripts; pytest is not in the venv |

---

## 4. Broken functions, root causes, fixes

| # | Defect found | Root cause | Fix |
|---|---|---|---|
| 1 | Backend not running (port 8010 down) | service stopped since last session | restarted `uvicorn main:app --port 8010`; health verified |
| 2 | **wiki_toxic normalized to 0 toxic / 200 rows** — silent label corruption | dataset stores its binary label as `label`, my normalizer read `toxic` | fixed `normalize()` to read `label` (fallback `toxic`), type-safe threshold; re-run → 21/200 toxic; added a permanent "0 toxic out of ≥50 → WARN loudly" guard so this class of bug cannot pass silently again |
| 3 | My new word-input suite reported 2 batch failures | test used wrong payload key (`texts` vs API's `comments`) | corrected the test (the API contract was right; verified against `BatchIn` and `tests_multilingual.py`) |

No pre-existing production code defect was found in the prediction path this
session; the prior session's fixes (threshold default, source whitelist,
language filter) were verified still in place.

**Honesty note:** the `word_idiot` case returns `label=non_toxic,
score=0.324` with `toxic_terms=['idiot']` — this is *by design* (WARN-band
calibration for mild insults at the default 0.5 threshold), not a crash, and
the term IS surfaced. Strong toxicity (`I will hurt you` → `toxic`, 0.846) and
Tamil toxic single words (`முட்டாள்` → `toxic`, 0.9) classify correctly.

---

## 5. Files created / modified / removed

| File | Action | Reason |
|---|---|---|
| `CODE/BACKEND/tests_word_input.py` | **CREATED** | Phase 5 word-level/text/edge-case suite (42 checks) |
| `CODE/BACKEND/fetch_external_datasets.py` | **CREATED** | Phase 4 dataset expansion pipeline (HF fetch → normalize → dedup → split → manifest) |
| `CODE/BACKEND/data/external/civil_comments.csv` + `.meta.json` | **CREATED** | 200-row smoke subset, CC0-1.0 |
| `CODE/BACKEND/data/external/wiki_toxic.csv` + `.meta.json` | **CREATED** | 200-row smoke subset, CC0-1.0 |
| `CODE/BACKEND/data/external/manifest.json`, `splits/*.csv` | **CREATED** | provenance manifest + merged deterministic splits |
| `DATASET_GUIDE.md` | **CREATED** | required by Phase 9 |
| `PROJECT_AUDIT_REPORT.md` | **CREATED** | this file |
| `CODE/BACKEND/backend.py`, `ml_service.py`, `app.py` | **unchanged** | no production defect required a fix this session |
| `aura.db` | **changed only by app runtime** | a real training job + predictions appended rows; no destructive migration, no rows deleted |

Nothing was removed.

---

## 6. Integration status

- **Frontend → Backend:** live — `AURA_BACKEND_URL=http://127.0.0.1:8010`; all
  16 pages render and UI prediction/filter flows pass AppTest (35/35).
- **Backend → Engine:** single code path `run_engine()` shared by
  `/moderate`, `/predict`, batch, voice, live (verified consistent contracts).
- **Backend → DB:** SQLite CRUD verified (dataset add/edit/delete round-trip in
  regression sweep; persistence across requests confirmed by history reads).
- **Backend → ML:** train → registry → `/models/performance` verified with a
  real completed job (`improved_v10`).
- **External data → app:** files written + manifest; **DB import intentionally
  left as a manual step** (see §4 of `DATASET_GUIDE.md`) to avoid clobbering
  user data.

---

## 7. Dataset details

| Name | Source URL | License | Rows used | Language | Preprocessing |
|---|---|---|---|---|---|
| AURA demo | local | project-owned | 100 | en | existing |
| Multilingual curated demo | local | project-owned | 96 | 12 langs | existing (marked "curated_demo, not a benchmark") |
| google/civil_comments | https://huggingface.co/datasets/google/civil_comments | CC0-1.0 (verified via HF API) | 200 smoke subset | en | strip → drop empty → binary @0.5 → dedup vs 197 existing → stratified 70/15/15 (seed 42) |
| OxAISH-AL-LLM/wiki_toxic | https://huggingface.co/datasets/OxAISH-AL-LLM/wiki_toxic | CC0-1.0 (verified via HF API) | 200 smoke subset | en | `label`→binary → same pipeline |

Current DB dataset: **197 rows** (before external import) — 71 toxic /
126 non-toxic; 12 languages; 0 duplicates; 0 missing labels.

---

## 8. Model status & evaluation (measured, not claimed)

- **Architecture:** pure-Python multinomial Naive Bayes (baseline + improved
  variants), bag-of-words + bigrams, saved as JSON weights in
  `data/processed/`, versioned in a model registry. English inference for the
  production decision path is the **rule/lexicon engine**; the NB model powers
  the training/evaluation pages.
- **Training status:** a real job was executed during this audit —
  `improved_v10`, status `completed`, 137 train / 29 val / 31 test.
- **Inference status:** works after restart (weights loaded from disk).
- **Measured metrics (test n=31):** accuracy **0.677**, precision **0.602**,
  recall **0.552**, F1 **0.539**, confusion matrix `[[19,2],[8,2]]`.
- **Per-language:** en acc 0.882 (support 17), kn acc 0.667 (support 3),
  all others literally **"Not evaluated"** (support < 3). No number here is
  fabricated.
- **Caveat:** the test split is small (31 rows) — these metrics have wide
  confidence intervals; the external datasets are staged for a larger retrain.

---

## 9. Edge-case test results (Phase 5)

New suite `tests_word_input.py`: **42/42 PASS**.

| Input class | Example | Result |
|---|---|---|
| Single neutral word | `hello` | 200 · en · non_toxic · conf 0.86 |
| Single mild insult | `idiot` | 200 · score 0.324 · `toxic_terms=['idiot']` · label non_toxic (WARN-band calibration) |
| Threatening sentence | `I will hurt you` | 200 · **toxic** · score 0.846 |
| Short phrase | `good morning` | 200 · non_toxic |
| Sentence / paragraph | 2 long texts | 200 · contract complete |
| Uppercase / mixed case | `HELLO THERE`, `HeLLo wORld` | 200 · correct |
| Leading/trailing spaces | `   hello   ` | 200 · text normalized |
| Punctuation / emoji | `hello!!!`, `hello 😀` | 200 |
| Numbers only / symbols | `12345`, `!!!???...` | 200 · `und`/`fallback` |
| Empty / whitespace / null | `""`, `"   "`, `null` | **400** with clear message |
| Misspelled | `yuo are a stupiid idot` | 200 · non_toxic (no crash) |
| Unfamiliar word | `zorblatt quixen frobnicate` | 200 · non_toxic |
| Hindi/Urdu/Bengali single words | `नमस्ते`, `السلام علیکم`, `শুভ সকাল` | 200 · correct lang codes |
| Tamil toxic single word | `முட்டாள்` | 200 · **toxic** · score 0.9 |
| Mixed script | `hello உலகம` | 200 · ta · non_toxic |
| Unsupported CJK | `你好世界` | 200 · `und`/`fallback` |
| Batch (6 mixed) | words+sentences+numbers | 200 · 6/6 contract-complete · langs en/hi/ta/und |
| Batch empty item | `["hello",""]` | **400** `Comment 2 in the batch is empty.` |
| Batch >500 | 501 items | **400** |
| Duplicate rapid requests | ×5 | all 200 |
| Very large input | 140k chars | 200, no 5xx |

---

## 10. Commands executed & outcomes

| Command | Outcome |
|---|---|
| `uvicorn main:app --host 127.0.0.1 --port 8010` | started, `/health` → `healthy` |
| `python tests_multilingual.py` | **29/29 + 5/5 PASS, exit 0** |
| `python tests_frontend_apptest.py` | **35/35 PASS, exit 0** |
| `python tests_word_input.py` (run twice) | first run 40/42 (2 test-side key bugs), fixed → **42/42 PASS, exit 0** |
| `python -m compileall backend.py ml_service.py mlexicon.py main.py app.py` | **exit 0** (no syntax errors) |
| `python fetch_external_datasets.py --limit 200 --merge` | run 1: wiki_toxic 0 toxic (**bug**), fixed → run 2: 400 rows, 12+21 toxic, manifest written |
| `POST /models/train` → poll → `GET /models/performance` | job **completed**, `improved_v10`, metrics measured |
| HF API license probe | both datasets confirmed CC0-1.0 |
| secrets grep across `CODE/` | only the documented default admin password in a test file; no API keys/tokens found |

---

## 11. Exact test counts

| Suite | Passed | Failed | Skipped | Not run |
|---|---|---|---|---|
| `tests_multilingual.py` matrix | **29** | 0 | 0 | — |
| `tests_multilingual.py` E2E checks | **5** | 0 | 0 | — |
| `tests_frontend_apptest.py` | **35** | 0 | 0 | — |
| `tests_word_input.py` (new) | **42** | 0 | 0 | — |
| **TOTAL** | **111** | **0** | **0** | pytest suite: not run (pytest not installed; project uses standalone scripts) |

Not automatable here: physical camera/mic capture, browser CSV download,
production-grade lint (no linter configured in the project).

---

## 12. Known limitations & remaining work

1. **DB import of external rows not done** — deliberately manual (protects
   user data); pipeline + docs ready (see `DATASET_GUIDE.md` §4).
2. **External smoke subset is small** (200/source) and English-only — Indic
   toxicity datasets (HASOC, Jigsaw multilingual) are listed but not fetched.
3. **Non-English scoring is lexicon heuristics**, honestly labeled
   (`processing_mode=language_lexicon`, `confidence_kind=heuristic`). No
   transformer was downloaded or claimed.
4. **Small test split** (31) → wide error bars on all ML metrics.
5. `pytest`/linter not present in the venv; tests are standalone scripts.
6. Port 8000 remains occupied by an unrelated project (not touched).
7. Streamlit deprecation warnings (`components.v1.html`, `use_container_width`)
   are functional today but will need attention after 2025-12-31.
8. NB model toxic-class recall is low (0.20) — retrain after external import.

## 13. How to run

```powershell
$py = "C:\Users\gokul\OneDrive\Desktop\zip project\comment toxicity\.venv\Scripts\python.exe"
$env:PYTHONIOENCODING='utf-8'

# Backend (port 8010)
cd "C:\Users\gokul\OneDrive\Desktop\zip project\comment toxicity\CODE\BACKEND"
& $py -m uvicorn main:app --host 127.0.0.1 --port 8010

# Frontend (port 8501) — second terminal
$env:AURA_BACKEND_URL='http://127.0.0.1:8010'
cd "...\comment toxicity\CODE\FRONTEND"
& $py -m streamlit run app.py --server.port 8501

# Tests (backend must be running)
$env:AURA_BASE_URL='http://127.0.0.1:8010'
& $py ..\BACKEND\tests_multilingual.py
& $py ..\BACKEND\tests_word_input.py
$env:AURA_BACKEND_URL='http://127.0.0.1:8010'
& $py tests_frontend_apptest.py

# Dataset expansion
& $py fetch_external_datasets.py --limit 500 --merge

# Train
# POST /models/train {"config":{"variant":"improved","seed":42}}  (admin token)
```

Login: `admin` / `Admin@1234` (unchanged).

## 14. Prioritized next steps

1. **Import the external rows into `dataset_samples` and retrain** — expect
   toxic-class recall to rise well above 0.20 with 400 more labeled rows.
2. Fetch an **Indic/hasoc-style multilingual toxicity dataset** to give the 11
   lexicon languages real per-language metrics (currently "Not evaluated").
3. Increase the test split size (or k-fold) so reported metrics are stable.
4. Add `pytest` to the venv and wrap the three stdlib suites for CI.
5. Replace deprecated Streamlit APIs before 2025-12-31.
6. Consider a small pretrained multilingual model (e.g. XLM-R base distilled)
   for non-English scoring, replacing lexicon heuristics — requires download
   budget and GPU/CPU inference time.

---

## 15. Phase 2 status

**Scope:** pretrained model integration (Phase 2) — full evaluation details in
`PHASE2_MODEL_EVALUATION.md`. All numbers below are measured
(`CODE/BACKEND/models/phase2_benchmark.json`, `models/tuned_threshold.json`).

### 15.1 Model integration & engine switch

- **Model:** Horizon-Labs/multilingual-toxicity-small — 141M params,
  Apache-2.0, 7 sigmoid multi-label heads; integrated **behind a modular
  adapter** (`CODE/BACKEND/model_adapter.py`), legacy engine untouched.
- **Engine switch:** `AURA_PREDICTION_ENGINE` = `legacy` (DEFAULT) | `auto` |
  `hf`; precedence **settings table > env > default**, persisted in the
  settings table.
- **Admin endpoints:** `GET/POST /models/engine`, `GET /models/adapter`
  (42 API endpoints total per openapi.json — the 39 inventoried in §2 plus
  these 3; an earlier draft's "46" counted FastAPI's built-in doc routes).
- `auto` = languages in the coverage map **or** claimed by the model card.
- Lazy one-time load per process (thread-safe singleton), warm-up thread on
  engine switch, failure backoff `AURA_MODEL_RETRY_S` (default 60s), never
  re-downloaded per request.

### 15.2 Benchmark summary (held-out test)

| Language | n | legacy toxic F1 | model toxic F1 | model recall | model FPR | model ROC-AUC | latency ms/text |
|---|---:|---:|---:|---:|---:|---:|---:|
| en | 180 | 0.540 | 0.948 | 0.911 | 0.011 | 0.989 | 39.7 |
| ta | 180 | 0.021 | 0.529 | 0.411 | 0.144 | 0.728 | 164.2 |
| ta-Latn | 180 | 0.104 | 0.245 | 0.144 | 0.033 | 0.668 | 72.1 |
| hi | 180 | 0.065 | 0.638 | 0.489 | 0.044 | 0.861 | 112.2 |
| bn | 143 | 0.000 | 0.624 | 0.547 | 0.122 | 0.839 | 288.0 |
| ur | 180 | 0.000 | 0.588 | 0.522 | 0.256 | 0.704 | 102.9 |

Memory: 21.5 MB → 1168.9 MB (delta 1147.4 MB), CPU-only `torch 2.14.1+cpu`.
Thresholds tuned on pooled validation only (n=695, selected 0.35); test split
untouched during tuning.

### 15.3 Coverage gating

| Tier | Languages |
|---|---|
| validated | en, hi |
| experimental (measured, caveats) | ta, ta-Latn, bn, ur |
| unmeasured | everything else — marked **NOT EVALUATED**, never claimed |

`MODEL_CLAIMED_LANGUAGES` (model card) **deliberately excludes `ta`** (the card
does not claim Tamil). API responses carry `model_coverage` + `note`;
unmeasured/card-claimed-only languages get `decision_status=experimental` and a
HUMAN_REVIEW action.

### 15.4 Fallback behavior

Any adapter failure leaves the **legacy result intact**, sets
`decision_status=fallback` + a sanitized one-line `model_error` (filesystem
paths masked, **no stack traces**), HTTP 200. Unknown engine value → 400.

### 15.5 New test suite + detection fix it uncovered

`CODE/BACKEND/tests_model_adapter.py` — adapter/engine-switch suite (110 checks:
engine auth/validation, legacy contract, model contract, per-language
word+sentence across all 6 groups, unmeasured gating, batch limits, SQLite
persistence, auto gating, fallback instance, in-process backoff, engine
restore), run with `AURA_BASE_URL=http://127.0.0.1:8010` (backend must be
running).

First run exposed a **pre-existing language-detection bug**: the Indic danda
sentence terminators (U+0964 `।` / U+0965 `॥`) live in the Devanagari block
and were counted as script evidence, so any Bengali/Hindi comment ending in
"।" registered as two scripts → `Mixed` → `und` → forced legacy fallback.
Fixed in `mlexicon.py` (`SHARED_INDIC_PUNCTUATION` excluded from script
counting); genuine mixed-script text still returns `und`, Marathi marker
detection unchanged.

### 15.6 Remaining work (honest limitations)

1. ta-Latn weak (toxic F1 0.245); bn labels are **weak Qwen annotations**, not
   human gold.
2. Val/test FPR drift: ur test FPR 0.256, ta 0.144 despite the 0.15 validation cap.
3. `confidence = max(tox, 1-tox)` is a decision-margin proxy, **not a
   calibrated probability**; `language_confidence` is an uncalibrated
   script-share heuristic (Latin script → `None`, `kind=script_ambiguous`).
4. Model **overlays** the legacy action ladder (`processing_mode=
   pretrained_model` but actions still derive from the legacy risk ladder) —
   does not fully replace legacy context blending.
5. Per-category sigmoid heads ≠ a single human "toxic" judgment; CPU latency
   varies ~40–290 ms/text.
6. Phase 1 external CC0 datasets **still not imported into `aura.db`**
   (manual step, documented in `DATASET_GUIDE.md` §4) — **RESOLVED in Phase 3,
   see §16.1**.

---

## 16. Phase 3 status

**Scope:** model-accuracy root causes + safe external-dataset import. No
architecture change; the legacy Naive Bayes + lexicon engine stays active and
the transformer stays **opt-in** (`prediction_engine=legacy`).

### 16.1 External dataset import (COMPLETE — counts measured)

`CODE/BACKEND/import_external_datasets.py`, dry-run by default, `--apply` to
write. Details and caveats in `DATASET_GUIDE.md` §8.

| Outcome | Rows |
|---|---:|
| Read from source CSVs | 400 |
| **Inserted** | **399** (civil 199 / wiki 200) |
| Skipped — conflicting-label duplicate | 1 |
| Skipped — already imported (idempotency re-run) | 399 |
| Rejected | **0** |
| `dataset_samples` before → after | **197 → 596** |

- The 197 pre-existing rows are **byte-identical** afterwards (checked column by
  column against the pre-import backup); users (11) and history (658) untouched.
- Transactional: a fault injected mid-batch rolled back **0 of 4** rows.
- Idempotent: a second `--apply` inserted **0** (partial UNIQUE index on
  `external_id`).
- Two importer defects were caught and fixed before data landed: a placeholder
  count mismatch (14 values for 15 columns) and a misuse of `sqlite3.connect`
  as a context manager in the backup step.

### 16.2 Defects fixed

| Defect | Where | Impact | Fix |
|---|---|---|---|
| Threshold sweep truncated | `benchmark_phase2.py:139,199` | sweep started at `t=0.30`, so ta-Latn was pinned to the grid edge and could never trade validation FPR for recall — a root cause of the 0.245 F1 | `benchmark_phase3.py` sweeps **0.05–0.90**; selection rule unchanged |
| Split leakage in the fetch pipeline | `fetch_external_datasets.py:257` | dedup compared `text.lower()` only, so whitespace-differing copies survived; `civil_comments-82/84` (identical text, **opposite labels**) landed in two different splits | `dedup_key()`/`dedup_rows()` now use the same whitespace-collapsed key as `ml_service`, and conflicting-label duplicates are detected and reported |
| Non-binary labels | importer | a `0.37` label could be coerced | labels must parse to exactly 0/1, else rejected with a reason |
| Unsupported languages | importer | rows in languages AURA cannot detect would be silently scored as English | rejected with `unsupported_language:<code>` and tallied |

### 16.3 Model benchmark - measured (`models/phase3_benchmark.json`)

Ran to completion on the same held-out test splits. Selection on **validation
only**; test read once for reporting. Full precision/recall/F1, macro-F1,
confusion matrices, ROC-AUC, PR-AUC and latency are in the JSON and in
`PHASE2_MODEL_EVALUATION.md` §10.3.

| Lang | n (pos/neg) | val thr | test F1 (was) | test FPR | ROC-AUC | legacy F1 |
|---|---|---:|---|---:|---:|---:|
| en | 180 (90/90) | 0.55 | **0.948** (0.948) | 0.011 | 0.989 | 0.540 |
| ta | 180 (90/90) | 0.40 | **0.529** (0.529) | 0.144 | 0.728 | 0.021 |
| ta-Latn | 180 (90/90) | **0.25** (0.30) | **0.313** (0.245) | 0.078 | 0.668 | 0.104 |
| hi | 180 (90/90) | 0.35 | **0.638** (0.638) | 0.044 | 0.861 | 0.065 |
| bn | 143 (53/90) | **0.25** (0.30) | **0.722** (0.624) | **0.178** | 0.839 | 0.000 |
| ur | 180 (90/90) | 0.40 | **0.588** (0.588) | **0.256** | 0.704 | 0.000 |

- **Root cause confirmed**: with the 0.30 floor removed, ta-Latn's validation
  optimum is **0.25** (val F1 0.250 at FPR 0.050 vs 0.174 at 0.30 - strictly
  better at identical FPR). Test F1 rises 0.245 -> **0.313** (+0.068) and FPR
  stays at 0.078, well inside the cap.
- **bn** also moves to 0.25 (test F1 0.624 -> **0.722**) but its test FPR rises
  to **0.178, above the 0.15 safety budget** - so it is *not* adopted.
- **ur and bn fail the test FPR cap** (0.256 / 0.178). For ur the test-optimal
  threshold (0.55) has *worse* F1 (0.394) than 0.40, i.e. the ranking itself is
  weak for that label definition - consistent with the task mismatch below.
- Memory 18.0 -> **1138.3 MB**; latency this run (batch 8, loaded CPU) 147-952
  ms/text vs Phase 2's 40-290 ms at batch 16.
- **Nothing was deployed**: `models/tuned_threshold.json` is untouched and
  `prediction_engine=legacy`. ta-Latn 0.25 is a safe, evidence-backed candidate
  awaiting an explicit rollout decision.

### 16.4 Root cause for the weak languages: task mismatch

Verified from `data/phase2_eval/manifest.json`:

| Lang | Source | License | Label basis |
|---|---|---|---|
| en, hi | `textdetox/multilingual_toxicity_dataset` | OpenRAIL++ | generic `toxic`, used as-is |
| ta, ta-Latn | `offenseval_dravidian` | CC-BY-4.0 | **offensiveness** (not toxicity); ta-Latn = rows without Tamil script |
| bn | `Polygl0t/bengali-toxicity-qwen-annotations` | Apache-2.0 | **WEAK: Qwen annotations**, score 3 excluded |
| ur | `Adnan855570/Urdu_Hate_Speech` | MIT | **expert hate-speech** labels mapped to binary |

Three of the six groups are therefore not generic-toxicity corpora. This is the
leading explanation for ur's FPR and ta-Latn's weakness, and it is **not**
fixable by threshold tuning alone.

Data hygiene checked and clean: classes balanced (50/50 except bn 37%), **zero**
val<->test duplicates (exact and normalised), no cross-group text reuse,
ta-Latn positives are distinct genuine romanised Tamil.

### 16.5 Verification (against the live stack)

| Suite | Result |
|---|---|
| `tests_dataset_import.py` (new, 38 checks) | **38/38 PASS** |
| `tests_word_input.py` | **42/42 PASS** |
| `tests_multilingual.py` | **29/29 + 5/5 PASS** |
| `tests_frontend_apptest.py` | **35/35 PASS** |
| `tests_model_adapter.py` | **110/110 PASS** (Phase 4 re-run, 271.6s) |

### 16.6 Outstanding

- Phase 3 did **not** retrain the Naive Bayes model: the 399 new English rows
  are unassigned to splits, and `split_dataset()` would reshuffle **all** rows,
  invalidating the previously documented 197-row metrics. That needs a
  deliberate training run, not a side effect.
- `ta-Latn 0.25` is evidence-backed (test FPR 0.078, well inside the cap) but
  **not deployed**; `bn 0.25` is **not** recommended (test FPR 0.178 breaches
  the 0.15 budget). Both await an explicit rollout decision.
