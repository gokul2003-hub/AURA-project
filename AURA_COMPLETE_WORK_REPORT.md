# AURA Comment Toxicity — Complete Work Report

> **Generated:** 2026-10-06
> **Scope:** Phase 1–7 feature upgrade + Multilingual (Input/Output) implementation
> **Status:** All work implemented, integrated, and tested. Both services RUNNING.

---

## 1. Project & Environment

| Item | Value |
|---|---|
| Project root | `C:\Users\gokul\OneDrive\Desktop\zip project\comment toxicity` |
| Backend | `CODE/BACKEND/backend.py` (FastAPI) + `ml_service.py` + SQLite `aura.db` |
| Frontend | `CODE/FRONTEND/app.py` (Streamlit) |
| Python | System Python 3.14.3, project venv at `comment toxicity\.venv` |
| Backend URL | `http://127.0.0.1:8010` (port 8000 occupied by an unrelated project's server — PID from another project; AURA does not kill it) |
| Frontend URL | `http://localhost:8501` (started with `AURA_BACKEND_URL=http://127.0.0.1:8010`) |
| Login (user) | `admin` / `Admin@1234` (unchanged credentials) |

### How to run (PowerShell, two terminals)

```powershell
# Terminal 1 — Backend (port 8010)
cd "C:\Users\gokul\OneDrive\Desktop\zip project\comment toxicity\CODE\BACKEND"
& "C:\Users\gokul\OneDrive\Desktop\zip project\comment toxicity\.venv\Scripts\python.exe" -m uvicorn main:app --host 127.0.0.1 --port 8010

# Terminal 2 — Frontend (port 8501)
$env:AURA_BACKEND_URL='http://127.0.0.1:8010'
cd "C:\Users\gokul\OneDrive\Desktop\zip project\comment toxicity\CODE\FRONTEND"
& "C:\Users\gokul\OneDrive\Desktop\zip project\comment toxicity\.venv\Scripts\python.exe" -m streamlit run app.py --server.port 8501
```

> If the unrelated server on port 8000 is stopped, the backend may instead run on
> `--port 8000` and the frontend with `AURA_BACKEND_URL='http://127.0.0.1:8000'` (app default).

---

## 2. Work Completed

### Phase 1–7 (feature upgrade, all COMPLETE)

- **27 new backend endpoints:** `/predict`, `/predict/batch`, `/history` (filters: q, label, category, source, language, date range, confidence), `/analytics`, `/dataset` (CRUD + stats + filters), `/feedback`, `/admin/verify/{id}`, `/settings`, `/models`, `/models/performance`, `/models/compare`, `/models/split`, `/models/train/{id}`, `/voice/predict`, `/voice/transcribe`, `/live/start|chunk|stop|sessions`, etc.
- **Safe additive SQLite migrations** — new tables: `settings`, `feedback`, `live_sessions`, `live_events`, `training_runs`; new columns on `moderation_results`: `source, overall_label, confidence, categories_json, verified, language, language_name, processing_mode`; new columns on `dataset_samples`: `language, language_name, script, split`. Nothing dropped, no pre-existing records deleted.
- **ML workflow (`ml_service.py`):** dataset CRUD, deterministic 70/15/15 split (seed 42), pure-Python baseline/improved Naive Bayes, model registry & versions, background training jobs, real evaluation metrics (no fabricated numbers — unevaluated = "Not evaluated").
- **Frontend pages (all in nav, admin-guarded):** Admin Dashboard, Human Review, All Comments, User Profiles, Text Detection, Batch, Voice, Live Guard (iframe), Analytics, History (filters), Dataset Mgmt, Model Performance, Model Versions, Training, System Settings, Feedback Review.
- **Voice:** speech-to-text with language hint (en/ta/hi) + manual-transcript fallback → multilingual engine.
- **Live Guard:** camera + microphone iframe → speech chunks → `/live/chunk` → timeline events with language/toxicity/confidence/timestamp. Spoken language is the toxicity signal (no facial-expression classification).

### Multilingual implementation (all 5 goals COMPLETE)

1. **Real input → real output verified** end-to-end (UI → API → preprocessing → engine → result UI).
2. **Input/backend/model/output failures fixed** (see §4 root-cause fixes).
3. **Multilingual dataset structure created:**
   ```
   data/multilingual/
   ├── raw/multilingual_demo.csv     (96 rows, exact required schema)
   ├── processed/
   ├── train/  validation/  test/    (split mirrors, seed 42)
   └── README_DEMO.txt               (states: curated_demo, NOT a benchmark)
   ```
   Schema: `id,text,language,language_name,script,toxic,severe_toxic,obscene,threat,insult,identity_hate,source,split`
   Coverage: 12 languages × 8 complete-sentence rows (4 non-toxic + 4 toxic), `source=curated_demo`.
4. **Multilingual detection without breaking English** — new module `CODE/BACKEND/mlexicon.py`:
   - Script-based detection: `en, ta, ta-Latn (Tanglish), hi, te, ml, kn, bn, mr, gu, pa, ur, und`
   - Marathi vs Hindi: ≥2 distinct Marathi marker tokens (boundary-matched)
   - Tanglish: Latin script + ≥2 Tamil-roman markers with word boundaries (never substring-matches ordinary English)
   - English continues through the **original engine** unchanged (`processing_mode: existing_model`)
5. **Complete multilingual testing** — see §3.

---

## 3. Test Results (all executed against the running app)

### A. Multilingual API test matrix — `CODE/BACKEND/tests_multilingual.py`
**29/29 PASS + 5/5 END-TO-END checks PASS (exit 0)**

- 12 languages × {non-toxic, toxic} = 24 cases
- 5 English extras: threat, threat, obscene, 2 false-positive guards ("The class was held in the basement.", "Hello friends, have a great day." → non-toxic)
- Pass rules per case: `lang_ok` AND `label_ok` AND `mode_ok` (no `fallback` for supported languages)
- E2E: `/health`, `/predict/batch` (3 mixed languages, contract fields), `/history?language=ta`, `/dataset/stats` (`by_language`,`languages`), `/analytics` (`language_distribution`)

### B. Frontend in-process test (Streamlit AppTest) — **35/35 PASS**
- Admin login, 9 multilingual UI predictions (Tamil, English, Tanglish, Hindi, Urdu toxic/non-toxic + FP guard) with rendered `Language / Processing / Score / Confidence` lines
- All **16 nav pages render with zero exceptions**
- Dataset language filters + "SAMPLES BY LANGUAGE"/"BY SPLIT" sections, Model Performance "PERFORMANCE BY LANGUAGE" table, History language filter (select + query), Analytics "LANGUAGE DISTRIBUTION", Batch/Voice/Training pages

### C. Regression sweep — all PASS
`/moderate` (legacy), batch, history filters (incl. invalid-language → 400), dataset add/edit/delete round-trip, feedback, `/models/performance`, compare, split, training job (completed), voice predict, live start→chunk→stop lifecycle.

### D. Language matrix (API, final)

| Language | Code | Non-toxic | Toxic | Mode |
|---|---|---|---|---|
| English | en | PASS | PASS | existing_model |
| Tamil | ta | PASS | PASS | language_lexicon |
| Tanglish | ta-Latn | PASS | PASS | language_lexicon |
| Hindi | hi | PASS | PASS | language_lexicon |
| Telugu | te | PASS | PASS | language_lexicon |
| Malayalam | ml | PASS | PASS | language_lexicon |
| Kannada | kn | PASS | PASS | language_lexicon |
| Bengali | bn | PASS | PASS | language_lexicon |
| Marathi | mr | PASS | PASS | language_lexicon |
| Gujarati | gu | PASS | PASS | language_lexicon |
| Punjabi | pa | PASS | PASS | language_lexicon |
| Urdu | ur | PASS | PASS | language_lexicon |

Fallback check: Chinese/Japanese input → `language=und`, `processing_mode=fallback`, conservative non-toxic (no fabricated toxicity).

### E. Dataset final state
```
Total: 197 | duplicates: 0 | missing labels: 0
by_language: en 109, ta 8, ta-Latn 8, hi 8, te 8, ml 8, kn 8, bn 8, mr 8, gu 8, pa 8, ur 8
by_split:   train 137, validation 29, test 31
by_source:  demo 100, text 1, curated_demo 96
```

---

## 4. Root-Cause Fixes (debug → fix → retest, not test-gaming)

1. **Dataset `source` whitelist rejected `demo`/`manual`** → added `DATASET_SOURCE_RE` regex validation in `backend.py`.
2. **4 English toxic matrix cases initially failed** → engine scores were correct (risk 57.6 / 59.0) but an earlier UI slider test had persisted `toxicity_threshold = 0.69`; code default is **0.5**. Restored default → all 29 cases pass. (Threshold is a user setting; UI slider still works.)
3. **`/history` lacked the `language` filter** the frontend sends (would be a dead control) → added validated filter (`VALID_LANG_CODES`, invalid → 400).
4. **Frontend `lang_info` ignored `language_code`** (backend carries display name in `language` for backward compat) → prefer `language_code`, fall back safely; flags/filters now resolve correctly.
5. **False-positive protection:** lexicon matching is Unicode-NFC-normalized, casefolded, repeated-char collapsed, and strictly token/phrase-boundary matched — `"ass"` never matches `"class"`, `"hell"` never matches `"hello"`; punctuation/obfuscation handled without over-classifying.

---

## 5. Files Changed / Created

| File | Change |
|---|---|
| `CODE/BACKEND/mlexicon.py` | **NEW** — language detection + lexicon loader/matcher (pure stdlib) |
| `CODE/BACKEND/backend.py` | language/script/processing_mode/score/confidence_kind on all prediction paths; history language filter + columns; voice language hint; `analytics.language_distribution`; additive migrations; `DATASET_SOURCE_RE` |
| `CODE/BACKEND/ml_service.py` | language columns (PRAGMA-guarded), filters (language/label/source/split), `by_language`/`by_split`/`by_source` stats, multilingual seeding (idempotent), split mirroring to `data/multilingual/*`, `evaluate_report().by_language` |
| `CODE/FRONTEND/app.py` | language/mode/score block in every result, batch CSV columns, history language filter, dataset filters + language forms + by-language/by-split charts, per-language performance table, analytics language chart, voice language hint, live-iframe language display + speech-language selector |
| `CODE/BACKEND/data/lexicons/*.json` | **NEW** — 12 files: `en, ta, tanglish, hi, te, ml, kn, bn, mr, gu, pa, ur` (categorized terms; offensive words live only in data files, never in UI source) |
| `CODE/BACKEND/data/multilingual/**` | **NEW** — raw/processed/train/validation/test + `multilingual_demo.csv` + `README_DEMO.txt` |
| `CODE/BACKEND/tests_multilingual.py` | **NEW** — 29-case automated smoke matrix (stdlib only, `AURA_BASE_URL`, exit code 0/1/2) |
| `CODE/BACKEND/aura.db` | additive migrations only; pre-existing records preserved |

**Response contract (every prediction: `/moderate`, `/predict`, batch items, `/voice/predict`, `/live/chunk`):**
```json
{
  "text": "...", "language": "Tamil", "language_code": "ta", "language_name": "Tamil",
  "script": "Tamil", "processing_mode": "language_lexicon",
  "confidence_kind": "heuristic", "score": 0.9,
  "overall_label": "toxic", "confidence": 0.93,
  "categories": {"toxic": 0.9, "severe_toxic": 0, "obscene": 0, "threat": 0, "insult": 0.85, "identity_hate": 0, "non_toxic": 0.1},
  "toxic_terms": ["..."], "risk_score": 85.0
}
```
- `processing_mode`: `existing_model` (English) | `language_lexicon` (11 languages) | `fallback` (unsupported/undetectable)
- No multilingual transformer was downloaded or claimed; scores are heuristic and labeled as such.

---

## 6. Honest Limitations

1. Non-English scoring = **language-specific lexicon heuristics**, exposed via `processing_mode`/`confidence_kind` — not a calibrated multilingual model. No large model was trained/downloaded (per constraints).
2. **Per-language ML metrics** exist only where test support ≥ 3: English (acc 88.2%, support 17), Kannada (acc 66.7%, support 3). All others display literal **"Not evaluated"** — never fabricated.
3. The multilingual dataset is a **small curated_demo (96 rows)** — explicitly *not* a real-world benchmark and not sourced from a public corpus.
4. Speech-to-text uses network Google recognition (en/ta/hi hints) with a manual-transcript fallback; offline STT is not included.
5. Physical camera/mic capture and the browser CSV file download were not automatable in this environment — their API contracts and page rendering were verified instead (voice/live lifecycles tested via API).
6. Port 8000 remains occupied by an unrelated project's server; AURA uses 8010 until that process is stopped by the user.
7. `st.components.v1.html` and `use_container_width` emit Streamlit deprecation warnings (functional today).

---

## 7. Verification Commands

```powershell
$py = "C:\Users\gokul\OneDrive\Desktop\zip project\comment toxicity\.venv\Scripts\python.exe"
$env:PYTHONIOENCODING='utf-8'
$env:AURA_BASE_URL='http://127.0.0.1:8010'

# Multilingual matrix (29 cases + 5 E2E checks; exit 0 = all pass)
& $py "C:\Users\gokul\OneDrive\Desktop\zip project\comment toxicity\CODE\BACKEND\tests_multilingual.py"

# Health
Invoke-RestMethod 'http://127.0.0.1:8010/health'
```

**Final status:** Application RUNNING · Real input→output PASS · Languages 12/12 PASS · Tests 29/29 + 5/5 + 35/35 PASS · Voice WORKING · Live WORKING (API/UI) · Batch WORKING (API/UI) · Dataset 197 samples / 12 languages.
