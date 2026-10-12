# AURA Phase 4 — Workstream C: Model Adapter, Fallback, Lifecycle, Timeout & Per-Language Preprocessing Audit

**Scope:** `CODE\BACKEND\model_adapter.py`, `CODE\BACKEND\backend.py` (the real FastAPI app — `main.py` is a 5-line shim: `from backend import app`, main.py:1), `CODE\BACKEND\ml_service.py` (legacy NB/lexicon storage path), `CODE\BACKEND\mlexicon.py` (language detection + lexicon matching), `CODE\BACKEND\models\tuned_threshold.json` (read-only).
**Date:** 2026-10-10. **Mode:** read-only code audit + weight-free tests; 1 wording-only fix implemented.

**Safety statements (all verified):** no model weights were loaded (the adapter singleton is stubbed in every test; the only adapter-object tests manipulate `_status`/`_lock` and hit the raise *before* the `import torch` at model_adapter.py:254); `aura.db` was never opened for writing (tests patch `backend.db` with `:memory:` and stub `store_moderation`); `models/tuned_threshold.json` unmodified (sha256 identical before/after, see §7); no service/process started or stopped; **zero** HTTP requests were made to the running backend (the coordinator's live probe is folded in as context, per instruction); the five coordinator-run suites were not executed; `ml_service` never retrained; production routing untouched.

---

## 1. Confirmed defects

### F-1 — MEDIUM — Concurrent cold-load requests block instead of the documented fast-fail (dead branch)
**Where:** model_adapter.py:237-241 vs 248-286 (load holds the lock); callers: backend.py:1059-1063 (startup warm-up), backend.py:1494-1498 (engine-switch warm-up), backend.py:909 (`apply_model_result` → `ADAPTER.predict`).

**Mechanism:** `_ensure_loaded` puts the *entire* load inside `with self._lock:` — it sets `_status="loading"` at line 248 under the lock and only flips it to `ready`/`unavailable` (lines 274/277) before releasing. The intended fast-fail
```python
if self._status == "loading":
    raise AdapterUnavailable("model is loading")     # model_adapter.py:240-241
```
sits *inside* the same lock, so under real contention no second caller can ever hold the lock while status is `loading` — **the branch is unreachable in the live flow** (it only fires in artificial setups where `loading` is set without a holder, which my test reproduces). Consequence: N simultaneous requests during a cold load each block a FastAPI/anyio threadpool worker for the whole load (cold ≈ 20–24 s per tests_model_adapter.py:415's own comment), and because the load has **no timeout** (`AutoTokenizer/AutoModelForSequenceClassification.from_pretrained` at model_adapter.py:259-262 is unbounded), a hung load blocks those workers indefinitely — all sync endpoints share the same ~40-worker pool, so unrelated legacy endpoints can stall too.

**Memory/CPU angle (asked in the brief):** single-flight is **guaranteed** — the lock is held across the whole load, so N requests can never spawn N loads; no uncontrolled memory growth from duplicate loads. The defect is thread-pool starvation / unbounded wait, not duplicate loading.

**Why not fixed here (blocked, needs coordinator approval):** the coordinator's suite explicitly *depends* on the blocking behavior — tests_model_adapter.py:415-424 sends the first `/predict` during warm-up and `model_contract()` (tests_model_adapter.py:308-338) requires `decision_status ∈ {predicted, uncertain}` + `processing_mode == "pretrained_model"`. A fast-fail fix would return `decision_status='fallback'` there and break that suite (and changing it is a behavior-contract change, not a wording fix).

**Proposed minimal fix:** hoist a lock-free check above `with self._lock:` — `if self._status == "loading": raise AdapterUnavailable("model is loading")` (attribute reads are GIL-atomic and `_status` is only mutated under the lock), so waiting requests take the already-tested legacy fallback path (backend.py:919-922) immediately; optionally bound the lock acquire. My test `TestAdapterConcurrency.test_status_loading_blocks_instead_of_fast_fail` characterizes today's behavior so the fix flips it consciously.

### F-2 — MEDIUM (honesty/provenance) — Unsupported Latin-script languages collapse into an English prediction with no "unsupported" marker
**Where:** mlexicon.py:253-256 → backend.py:642-659 → backend.py:765-767 → backend.py:850-864 (esp. 859).

**Mechanism (explains the coordinator's live probe exactly):**
1. `mlexicon.detect` has only two Latin-script outcomes: `ta-Latn` (≥2 distinct Tanglish markers, mlexicon.py:179-189/254) or `en` (mlexicon.py:256). Swahili/Spanish/any other Latin language therefore returns `code="en"`.
2. `backend.detect_language` passes it through → `language_code="en"`, `language="English"`.
3. `apply_language_engine` special-cases English: `if code=='en': mode='existing_model'` (backend.py:766) → the English rule engine produces a normal English result.
4. The only hint that anything is unconfirmed is `language_confidence_for` returning `(None, 'script_ambiguous')` for **all** Latin-script input (backend.py:859) — including genuine English — so it cannot distinguish "unsupported language interpreted as English" from a real English comment.
5. No field in the response names the state: `processing_mode="existing_model"`, `language_code="en"`, `language="English"`, `language_confidence=null`, `language_confidence_kind="script_ambiguous"`.

**Contrast (the state *is* marked for non-Latin):** Chinese/emoji-only → `und` (mlexicon.py:236/257) → `processing_mode="fallback"` with the explicit reason "…no safety lexicon is available for it, so AURA used a conservative fallback…" (backend.py:720-741, verified by test `test_non_latin_unsupported_is_marked`). **Only the Latin-script case collapses**, and it collapses into (c) a genuine supported-language negative — the exact three-way collapse flagged in the audit brief.

**Severity:** MEDIUM. The decision itself is not fabricated (the English rules/lexicon genuinely ran, and their terms may catch loanwords), but the *language provenance* claim ("English") is wrong for non-English Latin input and indistinguishable from a supported-language result at the top level of the response.

**Proposed minimal fix (NOT implemented — production-contract change per coordinator instruction):** add one additive field, no existing field changes — e.g. in `apply_language_engine`, when `code=='en' and script=='Latin'`, set `r['language_confidence_kind']='script_ambiguous'` (already true) **plus** an explicit `r['language_detection_method']='script_only'` / `r['language_supported']=False`, or widen `detect` with a lexical LID for Latin. Characterized by test `test_unsupported_latin_collapses_into_english` (asserts today's contract so any fix must consciously update it).

### F-3 — LOW (fixed) — Coverage notes did not name the threshold their figures belong to
**Where:** model_adapter.py:77-82 (`MODEL_COVERAGE`), previously lines 80-81 for the two ambiguous entries.

**Assessment of the coordinator/Workstream-E report:** the figures are **factually correct FOR THE DEPLOYED thresholds** — I verified every note against `models/phase2_benchmark.json` (which was generated *at* the deployed thresholds; its `model.threshold_used` equals the deployed value for all six groups):

| lang | note F1 | artifact F1 | Δ | note FPR | artifact FPR | Δ | artifact thr = deployed thr |
|---|---|---|---|---|---|---|---|
| en | 0.948 | 0.9480 | 0.0000 | 0.011 | 0.0111 | 0.0001 | 0.55 = 0.55 ✓ |
| ta | 0.529 | 0.5286 | 0.0004 | 0.144 | 0.1444 | 0.0004 | 0.40 = 0.40 ✓ |
| ta-Latn | 0.245 | 0.2453 | 0.0003 | 0.033 | 0.0333 | 0.0003 | 0.30 = 0.30 ✓ |
| hi | 0.638 | 0.6377 | 0.0003 | 0.044 | 0.0444 | 0.0004 | 0.35 = 0.35 ✓ |
| bn | 0.624 | 0.6237 | 0.0003 | 0.122 | 0.1222 | 0.0002 | 0.30 = 0.30 ✓ |
| ur | 0.588 | 0.5875 | 0.0005 | 0.256 | 0.2556 | 0.0004 | 0.40 = 0.40 ✓ |

(ROC-AUC claims also verified: en 0.9888≈0.989, hi 0.8611≈0.861.) All deltas are pure display rounding. **So the strings were NOT stale and no number was wrong.** The genuine defect was the missing qualifier: `ta` and `ur` notes named "(FPR-capped threshold 0.40)", but `en`, `hi`, `ta-Latn`, `bn` named none — while `models/phase3_benchmark.json` (generated 2026-10-10T10:52:50) reports *different* figures at the **swept-but-not-adopted** 0.25 (`groups.ta-Latn.test_model`: F1 0.313/FPR 0.0778 at `threshold_used=0.25`; `groups.bn.test_model`: F1 0.7222/FPR 0.1778 at 0.25). A reader comparing the two artifacts saw an apparent contradiction. **Does phase3_benchmark.json store the deployed-threshold values?** Only partially and obliquely: it stores `delta_toxic_f1_vs_phase2_threshold` (+0.0677 ta-Latn, +0.0985 bn), from which deployed F1 is recoverable (0.313−0.0677=0.2453 ✓; 0.7222−0.0985=0.6237 ✓), but it stores **no FPR-at-deployed-threshold at all**. That ambiguity is what the fix removes.

**Fix implemented (wording only, every number byte-identical):** each of the four notes now reads "held-out n=… **at the deployed threshold X**: F1 …". `ta`/`ur` already named their threshold and were left untouched. Where the notes surface (unchanged by the fix): every model-engine `/predict` response via `r['model_coverage_note']` (backend.py:918, 982), `GET /models/engine` (backend.py:1484), `GET /models/adapter` (backend.py:1509), and `models/phase3_benchmark.json → uncertainty_and_coverage.coverage` (benchmark_phase3.py:227 — the JSON file is a stale-run artifact and keeps the old wording until the benchmark is next run; regenerating it was out of scope and forbidden). No coordinator suite or frontend asserts the note text (grep evidence: tests_model_adapter.py:359-360/512-513 check only non-empty; FRONTEND/app.py:520/588 only displays it), so the change cannot break them. Regression test added: `test_coverage_notes_match_deployed_threshold_artifact`.

### F-4 — LOW (report-only) — Single-marker Tanglish is detected as English
**Where:** mlexicon.py:179-189 (marker table), 254 (`>= 2` distinct markers required).

**Mechanism:** a Tanglish comment containing only one marker (e.g. "muttal") is `en`, not `ta-Latn`. Under the model engine this swaps the per-language threshold (0.55 instead of ta-Latn's 0.30) and the honesty label (`validated` instead of `experimental`) for Tanglish text. Mitigation under the production legacy path: the backend's inline English lexicon contains the romanized Tamil terms (backend.py:53, 81, 106), so such text is still scored, not dropped. Verified by test `test_single_marker_tanglish_detected_as_english`. **Fix requires coordinator approval** (it is a language-labeling behavior change: lowering the marker threshold to 1 would reclassify English comments containing "nee"/"illa"/"enna" as Tanglish).

### F-5 — LOW, latent (report-only) — One bad global threshold silently disables all per-language thresholds
**Where:** model_adapter.py:126-157 (`ModelConfig._load_tuned`).

**Mechanism:** if `payload["threshold"]` is missing/non-numeric, `float(payload.get("threshold"))` raises `TypeError`, caught by the bare `except Exception: pass` at line 154 — which also discards the otherwise-valid `per_language` map and the rationale; a global value outside (0,1) is equally fatal because line 152 (`self.threshold_rationale += …`) raises `AttributeError` on the not-yet-set attribute, again swallowed. Either way the config silently falls back to `0.5` with **no** per-language thresholds. Reproducible: test `test_malformed_tuned_file_keeps_per_language` asserts today's (bad) behavior as a characterization. **Not fixed** because it is latent (the deployed file is valid), and threshold-loading semantics are currently the subject of active Phase 4 work by other streams — flipping them silently here would be worse than reporting. **Proposed minimal fix:** initialize `self.threshold_source`/`self.threshold_rationale` before the `try`, and load `per_language` independently of global-threshold validity.

### F-6 — LOW (auditability, report-only) — The engine switch writes no audit log
**Where:** backend.py:818-832 (`set_engine`) vs backend.py:1173/1184/1352 (every other consequential admin action inserts into `audit_logs`).

Flipping `prediction_engine` (legacy→hf/auto) — the single most consequential production switch — persists a settings row and mirrors the env (backend.py:831) but records **no** `audit_logs` entry. **Proposed minimal fix:** one `INSERT INTO audit_logs(..., 'SET_PREDICTION_ENGINE', ...)` inside `set_engine`. Not implemented during Phase 4 because it adds a DB write while the coordinator's suite runs against the live DB and the severity is low.

---

## 2. Areas audited and found CLEAN (explicitly)

1. **Legacy path preservation (item 1 of the brief).** Default engine is `legacy` (backend.py:42 `ENGINE_DEFAULT='legacy'`). `run_engine` stamps every production response `model_name='aura-legacy-rules-lexicon'`, `model_version=app.version`, `decision_status='legacy'` via `setdefault` (backend.py:1035-1037). No legacy code path (`analyse` backend.py:464-509, `apply_lexicon_result` 669-718, `apply_fallback_result` 720-741) ever sets `toxicity_score` — verified: `/predict` legacy responses contain **no** `toxicity_score` key (test `test_legacy_contract_no_toxicity_score`). The adapter can only run when `model_selected(code)` is true (backend.py:758, 834-846), which is False for `legacy` — proven by test `test_legacy_engine_never_calls_adapter` (stub adapter call count = 0). **No code path can silently return a candidate-model result as a production prediction:** every model-produced result carries `decision_status ∈ {predicted, uncertain, experimental}`, `model_name=<model id>`, `toxicity_score`, `model_coverage(+note)` — provenance travels with the score.
2. **Candidate-model isolation / opt-in (item 2).** Model runs only when an admin settings row or `AURA_PREDICTION_ENGINE` explicitly selects `auto`/`hf` (backend.py:792-816); startup warm-up only when engine≠legacy or `AURA_MODEL_EAGER_LOAD=1` (backend.py:1059); `should_try_model` returns False for everything under `legacy`, True only for measured/claimed languages under `auto` (model_adapter.py:374-392, test `test_engine_gating`). `ta` is deliberately absent from `MODEL_CLAIMED_LANGUAGES` (model_adapter.py:65-67, test `test_ta_not_claimed_by_model_card`).
3. **Failure truthfulness (item 3).** Any adapter failure (load failure, timeout, inference error, module not loaded) → `decision_status='fallback'` + single-line, path-masked `model_error` + legacy `model_name` + **no** `toxicity_score` (backend.py:900-903, 919-922, `_safe_model_error` 875-889). `decision_status='predicted'` is never set unless the model actually produced the prediction (`categorise` only runs after a successful `predict`, model_adapter.py:401-415; backend.py:946-948). Tests: `test_hf_timeout_falls_back_truthfully`, `test_hf_load_failure_falls_back_truthfully` (timeout text survives into `model_error`; no traceback/newline/path).
4. **Concurrency guard (item 4) — the loading part is clean.** Single-flight is structurally guaranteed (load entirely under `self._lock`, model_adapter.py:237-286); N concurrent cold requests can never trigger N loads. The wait-instead-of-fast-fail issue is F-1.
5. **Timeout handling (item 5).** `AURA_MODEL_TIMEOUT_S` is a **per-chunk** deadline (`chunk_t0` reset each chunk, model_adapter.py:316-334; `_check_deadline` 361-63); defaults are 10 s / batch 16 (model_adapter.py:116-117, test `test_default_timeout_and_batch`). `benchmark_phase3.py:46-47` relaxes them via `os.environ.setdefault` **at its own import time only** — it never mutates model_adapter's source defaults, and backend.py never imports benchmark_phase3 (grep over the whole backend: the only `benchmark_phase3` hits are in that file). A timeout is surfaced honestly (F-3 mechanism above) and falls back to legacy rather than erroring or guessing. Caveat (not a defect): the check is *post-hoc* — a slow chunk is not interrupted, only reported after it completes (design note, R-2).
6. **State distinction (item 6).** `predicted` (genuine model decision, `toxicity_score` present) vs `fallback` (adapter failed, `model_error` present, no `toxicity_score`) vs `experimental` (unmeasured/model-card-claimed language, forced `HUMAN_REVIEW`, backend.py:948-950) are three **distinct** response shapes — test `test_three_states_are_distinct`. Unsupported non-Latin language is explicitly marked (`processing_mode='fallback'` + reason). The **one** collapse is unsupported-Latin → English = F-2. Note (correcting a common misreading, R-4): `decision_status='experimental'` is *only* set for `unmeasured`/`model_card_claimed` coverage (backend.py:948); the measured-experimental languages (ta, ta-Latn, bn, ur) keep `decision_status='predicted'/'uncertain'` and carry the caveat in `model_coverage='experimental'` + note — this matches the coordinator's own contract assertions (tests_model_adapter.py:310, 357-366).
7. **Provenance (item 8).** `/predict`, `/moderate`, `/voice/predict` return `language`, `language_code`, `language_name`, `script`, `processing_mode`, `language_confidence(+kind)`, `model_name`, `model_version`, `model_coverage(+note)`, `decision_status`, `confidence_kind`; `/predict/batch` carries the same per row (backend.py:1236); persistence stores `language`, `language_name`, `processing_mode` columns plus the full `result_json` (backend.py:610-624, migration 176-178). Minor gap (observation R-12): `/live/chunk` returns language/script/processing_mode but **not** `decision_status`/`model_error`/`model_name` (backend.py:1761), so a live-surface consumer cannot see that a model fallback occurred.
8. **`tuned_threshold.json` (item 9)** — see §7. Byte-identical Phase 2 values; the rejected 0.25s appear **only** inside `models/phase3_benchmark.json` as an evaluation artifact (`tuned_per_language`/`threshold_used=0.25`), never in production config; no production code path reads phase3_benchmark.json (backend reads phase2_benchmark.json only, backend.py:1515). Test `test_phase2_values_exactly` also asserts no deployed threshold equals 0.25.
9. **`ml_service.py` / `mlexicon.py` legacy-path hygiene.** AST scan: both import only stdlib and execute **no** module-level I/O (no DB/file writes, no downloads) — safe to import; `mlexicon` docstring contract ("never raises on missing/malformed lexicon") is implemented (mlexicon.py:325-365).

---

## 3. Rejected / non-defects (with reasoning)

| # | Claim | Verdict | Evidence |
|---|---|---|---|
| R-1 | "Coverage notes are stale Phase-2 numbers" | **Rejected** — correct for deployed thresholds (table in F-3); only the missing threshold qualifier was defective | phase2_benchmark.json `model.threshold_used` == deployed for all 6; Δ≤0.0005 |
| R-2 | Timeout doesn't preempt a slow chunk | Design note, not a defect | Post-hoc check model_adapter.py:334/361-363; result is discarded on timeout, honest fallback — never a partial/guessed answer |
| R-3 | Batch returns `toxicity_score: null` under legacy | Observation only | backend.py:1236 uses `r.get(...)`; the single-prediction contract has no key at all (test) — JSON null ≈ absent |
| R-4 | "Measured-experimental languages (ta…) get decision_status='experimental'" | Rejected — verified false | backend.py:948 limits it to unmeasured/claimed; ta under hf keeps `predicted`/`uncertain` + `model_coverage='experimental'` (test `test_hf_tamil_gets_ta_threshold_and_experimental_coverage`) |
| R-5 | Settings-row engine beats env (backend.py:795-811) | Documented design, admin-authenticated; default remains legacy | backend.py:42, 803-812; audit gap noted as F-6 |
| R-6 | Batch pre-computes model scores for gated-out languages | Wasted compute only; `apply_model_result` is still gated per comment | backend.py:1220-1227 vs 758 |
| R-7 | Batch retries per-comment after a failed batch predict | Bounded (retry-backoff makes load failures cheap; timeout retries are per-chunk bounded); latency-only | backend.py:1228-1229, model_adapter.py:245-247 |
| R-8 | `ModelConfig()` built per predict (reads tuned file each call); `self._config` assigned pre-lock | Benign (small file read; scalars only) | model_adapter.py:233-234 |
| R-9 | `language_gate()` unused by backend | Dead code, harmless | model_adapter.py:426-432; grep: no caller |
| R-10 | `confidence` 0..1 vs `uncertainty` 0..100 in one response | Pre-existing across both engines; frontend consumes as-is; contract change to fix | backend.py:958-960, 1208, 1024-1025 |
| R-11 | ta-Latn 0.25 / bn 0.25 "in production" | **Not in production config** — only in `models/phase3_benchmark.json` (benchmark artifact) | tuned_threshold.json = 0.30/0.30, sha256 §7 |
| R-12 | `/live/chunk` omits decision_status/model_error/model_name | Minor provenance gap on the live surface; reported, not changed (schema change) | backend.py:1761 |

---

## 4. Files changed

| File | Change | Why |
|---|---|---|
| `CODE\BACKEND\model_adapter.py` | Lines 77-82: added "at the deployed threshold X" to the en/hi/ta-Latn/bn coverage notes. **No number, threshold, status or behavior changed**; `ta`/`ur` notes untouched (already named their threshold) | F-3 (coordinator-requested); wording-only, verified no suite/frontend asserts the text |
| `CODE\BACKEND\tests_model_adapter_phase4.py` | **New** — 33 weight-free tests (§5) | Deliverable 1 |
| `PHASE4_WORKSTREAM_C.md` | **New** — this document | Deliverable 2 |

Before/after behavior of the fix: `MODEL_COVERAGE['ta-Latn'][1]` was `"held-out n=180: F1 0.245 vs legacy 0.104, FPR 0.033 — …"` and is now `"held-out n=180 at the deployed threshold 0.30: F1 0.245 vs legacy 0.104, FPR 0.033 — …"` (same for en/hi/bn with 0.55/0.35/0.30). API clients see the identical figures with the threshold now attributed; `GET /models/engine`, `GET /models/adapter` and every model-engine `/predict` (`model_coverage_note`) pick this up automatically. No other observable change. (Two scratch debug scripts `_ws_c_check.py`/`_ws_c_dbg.py` were created and deleted during the audit; nothing else in the tree was touched.)

---

## 5. Tests executed — exact command and output counts

Command (bounded, 120 s timeout, run from any cwd):

```
$env:PYTHONIOENCODING='utf-8'
& "…\comment toxicity\.venv\Scripts\python.exe" -W ignore::DeprecationWarning `
  "…\CODE\BACKEND\tests_model_adapter_phase4.py"          # exit code captured separately
```

Actual output (tail):

```
----------------------------------------------------------------------
Ran 33 tests in 1.410s

OK
EXITCODE=0
```

**Counts: 33 run, 33 passed, 0 failed, 0 errors, 0 skipped (0 not-run).** Suite is self-contained: no network, no server, no model weights, `:memory:` SQLite + stubbed `store_moderation` (aura.db untouched), adapter singleton stubbed. Coverage: §1 F-3 regression (note↔artifact↔deployed-threshold tie-out), F-4 characterization, F-5 characterization, F-1 characterization; §2 items 1-6 as listed. First run had 4 failures + 1 error — all five were bugs in *my* test code (wrong model label key `severe_toxic`→`severe_toxicity`; a Bengali constant that accidentally mixed Devanagari `\u0939` making `und` correct behavior; a wrong reason substring; and two wrong expectations about `decision_status='experimental'` which the run itself proved false — R-4). Test expectations were corrected to the verified contract; no product assertion was weakened to pass. The five coordinator-run suites were **not executed** (not-run by design).

## 6. Per-language audit (6 languages) — verified vs merely claimed

| lang | Detection (VERIFIED by test) | Legacy production path (VERIFIED) | Model path (code-verified, weights NOT run) | Deployed threshold (VERIFIED vs file+artifacts) | Open caveat |
|---|---|---|---|---|---|
| **en** | Latin, <2 Tanglish markers → `en` (mlexicon.py:253-256) | `existing_model`, inline rules/lexicon (backend.py:766) | `validated`; `predicted`/`uncertain`; note F1 0.948/ROC-AUC 0.989 ties to artifact | **0.55** | unsupported Latin input collapses here (F-2) |
| **ta** | Tamil script → `ta` (mlexicon.py:241-247); script_share confidence 1.0 for pure Tamil | `language_lexicon` (ta.json present) | `experimental` + note; NOT model-card claimed; threshold 0.40 applied (test) | **0.40** | quality figures "claimed" from phase2 artifact, not recomputed by me |
| **ta-Latn** | ≥2 distinct markers → `ta-Latn` (mlexicon.py:254-255) | `language_lexicon` (tanglish.json → alias, mlexicon.py:264) | `experimental`; 0.30 | **0.30** | single-marker Tanglish → `en` (F-4); note F1 0.245 = weakest measured group |
| **hi** | Devanagari, <2 Marathi markers → `hi` (mlexicon.py:243-244) | `language_lexicon` (hi.json) | `validated`; 0.35; note F1 0.638/ROC-AUC 0.861 ties to artifact | **0.35** | Hinglish (Latin Hindi) has no marker table → `en` (same family as F-2/F-4, Latin limitation) |
| **bn** | Bengali script → `bn` (mlexicon.py:246) | `language_lexicon` (bn.json) | `experimental` ("weak LLM annotations" caveat in note); 0.30 | **0.30** | Banglish (Latin Bengali) undetected → `en`; note F1 0.624 ties to artifact |
| **ur** | Arabic script ≥ Latin → `ur` (mlexicon.py:249-252) | `language_lexicon` (ur.json) | `experimental`; 0.40; note carries FPR 0.256 warning | **0.40** | any Arabic-script text (incl. Arabic itself) → `ur`; no Arabic/Urdu disambiguation; highest measured FPR |

**Verified** = asserted by a test that ran in this workstream (detection codes, processing modes, thresholds, provenance fields, contract shapes) or cross-checked byte-level against `models/phase2_benchmark.json` / `models/tuned_threshold.json`. **Merely claimed** = the F1/FPR/ROC-AUC values themselves (trusted from Phase 2 artifacts — I verified the artifacts are internally consistent and match the deployed thresholds, but recomputing them would require running the model, which was forbidden), and all real-model inference behavior (audited by code reading + stubbed-adapter contract tests only).

## 7. `models/tuned_threshold.json` (READ ONLY — verified)

- **sha256:** `f31f4975d29a151f3f8737ae18875f6a5d11c2ee8719d126c587f7b339285c54` (2886 bytes) — identical before and after this workstream.
- **Values (exact):** global `0.35`; `en 0.55, ta 0.40, ta-Latn 0.30, hi 0.35, bn 0.30, ur 0.40`; **`tuned_at: "2026-10-09T16:57:48"`** — byte-for-byte the Phase 2 deployed set specified in the brief. No 0.25 anywhere in this file; `ModelConfig` loads and serves them per language (tests `test_phase2_values_exactly`, `test_model_config_reads_deployed_thresholds`).

## 8. What I could not verify

1. Real-model inference end-to-end (weights load forbidden — RAM constraint). Model-path behavior is verified via code reading + stubbed payloads only; the coordinator's `tests_model_adapter.py` remains the live-model authority.
2. Live API responses at the time of writing (no HTTP calls made by me, per scope; coordinator probe folded in and matched to code paths in F-2).
3. F1/FPR/ROC-AUC figures — verified as *consistent with the artifacts and the deployed thresholds*, not recomputed.
4. `models/phase3_benchmark.json` regeneration after the F-3 wording fix (benchmark runs are forbidden); the JSON artifact retains the old note text until someone reruns `benchmark_phase3.py` — flagged so the coordinator is not surprised by the mismatch between the live note and that file's `coverage` section.
5. Whether F-1's fast-fail fix is desired — blocked by tests_model_adapter.py:415-424's blocking-behavior dependency; needs coordinator decision.
