# AURA — Phase 4 Verification Report

Verification of the Phase 4 audit and its fixes. Every figure below comes from
captured command output; nothing is estimated, rounded up, or inferred.

Companion documents: `PHASE4_BASELINE.md`, `PHASE4_IMPLEMENTATION_REPORT.md`,
`PHASE4_WORKSTREAM_B.md` / `_C.md` / `_E.md`, `PHASE4_CHECKSUMS.json`,
`PHASE4_CHANGED_FILES.json`.

---

## 1. Test results

### Required suites (all five, paths discovered — not assumed)

| Suite | Path | Passed | Failed | Result |
|---|---|---:|---:|---|
| `tests_dataset_import.py` | `CODE/BACKEND/` | 40 | 0 | PASS (exit 0) |
| `tests_model_adapter.py` | `CODE/BACKEND/` | 110 | 0 | PASS (exit 0) — run twice |
| `tests_word_input.py` | `CODE/BACKEND/` | 42 | 0 | PASS (exit 0) |
| `tests_multilingual.py` | `CODE/BACKEND/` | 29 + 5 | 0 | PASS (exit 0) |
| `tests_frontend_apptest.py` | `CODE/FRONTEND/` | 35 | 0 | PASS (exit 0) |

### New suites written in Phase 4

| Suite | Covers | Passed | Failed | Result |
|---|---|---:|---:|---|
| `tests_dataset_import_phase4.py` (WS-B) | importer rollback, split/threshold immutability, static guards that the suite cannot write `aura.db` | 42 | 0 | PASS |
| `tests_model_adapter_phase4.py` (WS-C) | adapter contract/fallback/backoff with a **stubbed** adapter, `:memory:` SQLite — no model load | 33 | 0 | PASS |
| `tests_threshold_immutability.py` | gates 1/2/8/9: threshold checksum vs baseline, engine, splits, active model, live legacy contract | 30 | 0 | PASS |
| `tests_e2e_phase4.py` (WS-D) | input → validation → LID → legacy prediction → API → Streamlit | 35 | 0 | PASS |

### Totals

```
PASSED 401   FAILED 0   SKIPPED 0   NOT RUN (see below)
```

### Not run, and why

| Item | Reason |
|---|---|
| `tests_metrics_phase4.py` | **Not created.** Workstream E was instructed to create it only if a metric-formula bug were found. It re-derived P/R/F1/macro-F1/accuracy/FPR for all 6 languages from the stored confusion matrices and found **0 mismatches** |
| pytest / linter / static analysis / build | **None configured.** No `pyproject.toml`, `Pipfile`, lockfile, CI config or lint config exists at project level; `pytest` is not installed. All suites are stdlib scripts |
| Real-model inference inside WS-C's tests | Forbidden (RAM-constrained box); C used a stubbed adapter and asserted the contract instead |
| HF re-fetch of meta/manifest provenance (WS-B) | Out of scope; would require a network re-fetch |
| Concurrent multi-operator import stress test (WS-B) | Reasoned about, not stress-tested — reported as unverified |
| Exact per-row bootstrap F1 CIs (WS-E) | **Not computable** without re-scoring; the artifact stores aggregate counts, not per-row scores. Approximate CIs are labelled as such |
| Re-running `benchmark_phase3.py` | Not needed — `phase3_benchmark.json` is unchanged and byte-verified |

### Timings and contention

| Suite | Elapsed |
|---|---|
| `tests_dataset_import.py` | 1.9–2.0 s |
| `tests_word_input.py` | 1.6 s |
| `tests_multilingual.py` | 1.4 s |
| `tests_frontend_apptest.py` | 14.8 s |
| `tests_model_adapter.py` | 271.6 s first run / 84.8 s re-run |
| `tests_model_adapter_phase4.py` | 2.3 s |
| `tests_e2e_phase4.py` | 4.5 s |
| `tests_threshold_immutability.py` | 0.5 s |

Model-load suites were run **one at a time** (RAM-bound machine, 16 GB). Free
RAM 7,171 MB before / 6,231 MB after the heaviest run; no OOM event.

---

## 2. Acceptance gates

### Gate 1 — No unauthorized changes to production engine, threshold file, splits or live database — **PASS**

| Item | Baseline | Final | Verdict |
|---|---|---|---|
| `tuned_threshold.json` SHA-256 | `f31f4975d29a151f3f87…` | `f31f4975d29a151f3f8737ae18875f6a5d11c2ee8719d126c587f7b339285c54` | **byte-identical** |
| `phase2_benchmark.json` | `5a9d94e267806ea0cae7…` | `5a9d94e267806ea0cae7fa83…` | byte-identical |
| `phase3_benchmark.json` | `f3a5ceb488f4a9adc348…` | `f3a5ceb488f4a9adc3488694…` | byte-identical |
| `prediction_engine` | `legacy` | `legacy` | unchanged |
| `toxicity_threshold` | `0.5` | `0.5` | unchanged |
| splits | 137/29/31 + 399 unassigned | 137/29/31 + 399 unassigned | unchanged |
| `dataset_samples` | 596 | 596 | unchanged |
| `training_runs` | 8 | 8 | unchanged |
| active model | `improved_v10` | `improved_v10` | unchanged |
| `model_versions` | 12 | 12 | unchanged |

Enforced by `tests_threshold_immutability.py` (30/30), which reads expected
values from the Phase 4 baseline snapshot rather than from hardcoded magic
numbers. `ta-Latn 0.25` / `bn 0.25` appear **only** in the evaluation artifact,
never in production config (asserted).

**One incident, disclosed:** an external server restart killed
`tests_model_adapter.py` **before its §12 restore**, leaving
`prediction_engine=hf` in the live database. Detected by an explicit state
check, restored to `legacy` through the app's own `POST /models/engine`, then
re-confirmed three ways: DB read, `/models/engine`, and a live prediction
returning `decision_status=legacy` with no `toxicity_score`. Thresholds, splits
and training state were untouched by the incident.

### Gate 2 — Existing legacy prediction behaviour preserved — **PASS**

Live response, verified after every suite run:

```
decision_status = legacy
model_name      = aura-legacy-rules-lexicon
processing_mode = existing_model
toxicity_score  = ABSENT
```

Response schema is a **single uniform 49-key set** across all 14 successful
input classes (empty, whitespace, ASCII, Tamil, Tanglish, Hindi, Bengali,
Urdu, Swahili, Spanish, Chinese, SQL probe, XSS probe, emoji, zero-width/RTL,
6 KB text). WS-C additionally proved the legacy path never invokes the adapter
(stub never called) and that no code path can surface a candidate-model result
as a production prediction — model scores always travel with `decision_status`
+ `model_name` + `model_coverage`.

### Gate 3 — All relevant regression suites pass — **PASS**

401/401 across 9 suites, 0 failures, 0 skips. Two first-run failures were in
**new test code** (WS-B: 39→42; WS-C: 5 failures including two wrong
`decision_status` expectations the run itself disproved), and three were in
**my** first E2E draft (missing auth token; asserting a UI string the UI does
not and should not use). All corrected in test code; **no assertion was weakened
and no timeout expanded to manufacture a pass.**

### Gate 4 — API and frontend integration verified with real execution — **PASS**

Evidence from `tests_e2e_phase4.py` (35/35) and the live probe:

- **Input validation:** empty → 400 with a human-readable message; missing
  `text` → 400; wrong type / invalid JSON / no body → 422 with FastAPI detail.
- **Language handling:** Tamil/Hindi/Bengali/Urdu detected via script and routed
  to `language_lexicon`; Chinese and emoji-only → `language_code=und`,
  `language_confidence_kind=no_signal`, `processing_mode=fallback`.
- **Honesty:** Latin-script unsupported input is disclosed as
  `language_confidence=null` + `language_confidence_kind=script_ambiguous`;
  the UI renders *"Language confidence: not confirmable from script"* rather
  than a fabricated percentage, and flags results `heuristic, uncalibrated`.
- **No fabrication:** `toxicity_score` absent from every response; the UI never
  displays a toxicity score for legacy results and never claims the pretrained
  model (`PRETRAINED` / `MULTILINGUAL-TOXICITY-SMALL` absent).
- **Fallback:** non-Latin unsupported input presents as `Fallback · Limited`.
- **Resilience:** UI survives an unreachable backend without an exception.
- **Auth:** valid login 200 (token length 64), invalid 401, `GET /models/engine`
  without a token 401.
- **Frontend:** all 16 nav pages render without exception; 8 multilingual UI
  predictions and 5 page-specific marker checks pass (35/35).

### Gate 5 — New tests reproduce and prevent every confirmed defect fixed — **PASS**

| Fixed defect | Prevention test |
|---|---|
| B-D1 leakage-guard key mismatch | WS-B: `fetch_guard_key_collapsed_casefold`, `fetch_guard_drops_whitespace_variant`; live reproduction before (exit 1) / after (exit 0) |
| B-D2 importer report path | WS-B: `report_flag_default_untouched`, `custom_report_content_valid` |
| D-3 suite clobbering the audit trail | `tests_threshold_immutability.py` 22/23/24 (static: `run_importer` must pass `--report` and `--db`; the production-path expression must be absent) + **dynamic proof**: full suite run leaves `import_report.json` byte-identical |
| C-F-3 coverage notes unnamed threshold | WS-C regression test (numbers asserted unchanged) |
| E-D2/D3/D4/D5 documentation | Verified by direct inspection — not code defects, so no runtime test applies |

### Gate 6 — Benchmark artifacts and documentation accurately reflect what was measured — **PASS**

Workstream E cross-checked **~124 values** printed in
`PHASE2_MODEL_EVALUATION.md` §10.3 and `PROJECT_AUDIT_REPORT.md` §16.3 against
`models/phase3_benchmark.json`: **0 mismatches**. It independently re-derived
every metric formula from the confusion matrices (0 mismatches), confirmed
seeded reproducibility (seed 42, fixed CSVs, intact val/test isolation,
provenance manifest), and confirmed all five carried-over Phase 3 figures
(ta-Latn F1 0.313, bn FPR 0.178, ur FPR 0.256, cap 0.15, 695 val rows).

Two documentation accuracy corrections were applied: the Phase 3 report's
confidence-interval table (I had written 6 of 12 intervals myself — corrected to
E's measured values) and the `ta-Latn` gain, which is now explicitly labelled as
**not statistically firm** (CI [0.200, 0.419] overlaps the previous value).

### Gate 7 — Changed-file list contains only intentional changes — **PASS (manual inventory; no git exists)**

`git rev-parse --show-toplevel` → `fatal: not a git repository`. Gate satisfied
by a SHA-256 inventory of 85 files taken **before any Phase 4 change**, compared
afterwards (`PHASE4_CHANGED_FILES.json`):

```
unchanged: 75   changed: 10   added: 10  removed: 0
```

Every changed file is accounted for in `PHASE4_IMPLEMENTATION_REPORT.md` §3:
4 source/test files (2 defect fixes, 1 wording fix, 1 audit-trail fix), 1
restored audit file, 3 reports, `aura.db` (runtime rows only), and the snapshot
file itself. No file was removed. Protected artifacts byte-identical.

### Gate 8 — No unrelated services interrupted — **PASS**

Docker (stopped during Phase 3 with user approval), Celery, the Blockchain
Framework uvicorn, browser windows, `opencode-cli` and `OpenCode` were
identified and **never touched** in Phase 4. Only the project's own backend was
started, and once restarted by me after an external interruption.

### Gate 9 — No deployment or retraining — **PASS**

No training endpoint was called; `training_runs` 8 → 8; active model unchanged;
thresholds byte-identical; engine `legacy`; no `--write-thresholds` invocation;
no dataset import into production (`dataset_samples` 596 → 596).

### Gate 10 — Final report contains actual results and blockers — **PASS**

This document and `PHASE4_IMPLEMENTATION_REPORT.md`. Blockers and unfinished
work are in §4 below.

---

## 3. Database integrity and record-count comparison

`PRAGMA integrity_check` = **ok**; `PRAGMA foreign_key_check` = **clean**.

| Table | Baseline | Final | Δ | Assessment |
|---|---:|---:|---:|---|
| `dataset_samples` | 596 | 596 | **0** | unchanged — protected |
| `feedback` | 5 | 5 | **0** | unchanged |
| `live_events` | 16 | 16 | **0** | unchanged |
| `live_sessions` | 6 | 6 | **0** | unchanged |
| `model_versions` | 12 | 12 | **0** | unchanged |
| `settings` | 2 | 2 | **0** | unchanged |
| `training_runs` | 8 | 8 | **0** | no retraining |
| `users` | 13 | 16 | +3 | test-suite throwaway accounts (no delete-user endpoint) |
| `moderation_results` | 808 | 1041 | +233 | prediction/history rows written by the suites |
| `audit_logs` | 828 | 1061 | +233 | matching audit rows |

**No rows were deleted or modified in any table** — every delta is an append
from executing the suites. Preservation spot-checks: original 197 rows still
present, all 399 imported rows still `split=''` (0 assigned), sources intact
(`demo` 100, `curated_demo` 96, `text` 1, `external_civil` 199,
`external_wiki` 200).

The database file grew 8.4 → 10.5 MB purely from those appended rows.

---

## 4. Remaining multilingual quality limitations

Independently re-measured and cross-checked (Workstream E). These are **not**
fixable by threshold tuning:

| Lang | Held-out F1 | Test FPR | Limitation |
|---|---|---|---|
| en | 0.948 [0.910, 0.979] | 0.011 [0.002, 0.060] | Sound; only group clearly separated from legacy at this n |
| hi | 0.638 [0.538, 0.726] | 0.044 [0.017, 0.109] | Acceptable; recall 0.489 |
| ta | 0.529 [0.422, 0.624] | 0.144 [0.086, 0.232] | Labels are **offensiveness**, not toxicity |
| ta-Latn | 0.313 [0.200, 0.419] | 0.078 [0.038, 0.152] | Weakest group; Latin-script romanised Tamil, model card does not claim Tamil. The 0.245→0.313 gain is **inside overlapping CIs — not statistically firm** |
| bn | 0.722 [0.617, 0.811] | 0.178 [0.113, 0.269] | **Weak Qwen annotations**, not human gold; FPR cap breach is *suggestive, not conclusive* |
| ur | 0.588 [0.493, 0.674] | **0.256 [0.177, 0.354]** | **Expert hate-speech** corpus scored by a toxicity model; cap breach is **real** (CI entirely above 0.15). No threshold does well — test-optimal 0.55 has *worse* F1 |

Additional structural limitation (WS-C, confirmed in code):

- **Latin-script language identification is systemic.** Unsupported Latin-script
  input (Swahili, Spanish, and single-marker Hinglish/Banglish/Tanglish) is
  returned as `en`. There is **no "unsupported language" field** — the only
  disclosure is `language_confidence=null` + `script_ambiguous`. Non-Latin
  unsupported input *is* properly marked as `fallback`. Reported, **not**
  changed: fixing it alters the production response contract.

---

## 5. Blocked, unfinished, or requiring approval

| Item | Status |
|---|---|
| **C-F-1 adapter concurrency** (MEDIUM) | **Needs your approval.** The `"model is loading"` fast-fail is dead code inside the lock, so concurrent cold-load requests block a worker ~20-24 s, and the load has no timeout (unbounded `from_pretrained`). Single-flight itself is clean, so no uncontrolled memory/CPU. Fixing it changes hot-path semantics and **breaks `tests_model_adapter.py:415-424`**, which requires the first warm-up predict to return a model result. Minimal fix documented by WS-C |
| **C-F-2 unsupported Latin-script languages** (MEDIUM) | Reported only — schema/labelling change needs approval |
| **C-F-4 single-marker Tanglish → `en`** (LOW) | Reported only — language-labelling change |
| **C-F-5 bare `except` discards all per-language thresholds** (LOW latent) | Reproduced; file valid today. Threshold-loading semantics deliberately untouched |
| **C-F-6 `set_engine` writes no audit row** (LOW) | Reported only |
| `tests_dataset_import.py:367-368` | **Pre-existing vacuous assertion** — `... or True` makes `api_dataset_external_id_exposed` always pass. Behaviour itself verified correct via the API probe. Left untouched (weakening/altering existing assertions is out of scope) |
| `phase3_benchmark.json` coverage text | Still carries pre-F-3 note text; only refreshed by re-running the benchmark, which was not warranted |
| External datasets remain English-only | Cannot move any Indic-language metric |
| 399 imported rows unassigned | Would require a deliberate retraining run, which would reshuffle **all** splits and invalidate documented 197-row metrics |

---

## 6. Explicit final statement

- **Deployed: NO.** `tuned_threshold.json` is byte-identical
  (`f31f4975d29a151f…`, `tuned_at 2026-10-09T16:57:48`); `ta-Latn 0.25` and
  `bn 0.25` were evaluated but **not** adopted; the engine is `legacy`.
- **Retrained: NO.** `training_runs` unchanged at 8; active model `improved_v10`
  unchanged; splits unchanged.
- **Phase 4 status: COMPLETE** for all 10 acceptance gates, with the two
  MEDIUM findings (C-F-1, C-F-2) and four LOW findings **reported rather than
  silently changed**, because each requires a production-behaviour or contract
  decision.
