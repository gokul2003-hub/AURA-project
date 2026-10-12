# AURA Phase 4.1 — Final Execution Report

Baseline captured **10:19:47**; final state verified **13:16:03** (wall-clock
**176 min**). **The 5-minute hard deadline was NOT met** — reported honestly
rather than restated. The overrun came from two sources: waiting on three
background agents, and integration debugging of a real regression the agents'
changes introduced (see §"Defects", C-F-2). Optional work (a full benchmark
re-run, extra documentation) was skipped; safety checks were never skipped.

---

## 1. Execution

**Agents used** — 3 parallel `general` sub-agents, launched simultaneously with
strict non-overlapping file ownership so no two could edit the same file:

| Agent | Exclusive ownership | Task |
|---|---|---|
| A | `mlexicon.py` + new `tests_langid_phase41.py` | C-F-2, C-F-4 |
| B | `model_adapter.py`, `backend.py` + new `tests_audit_threshold_phase41.py` | C-F-5, C-F-6 |
| C | `PHASE41_URDU_FPR.md` only (code files explicitly forbidden) | Urdu FPR investigation |

Integration/regression work was done by me (lead), because no agent was given
write access to the pre-existing test suites — this prevented any assertion from
being weakened to force a pass.

**Files changed (Phase 4.1)**

| File | Change |
|---|---|
| `CODE/BACKEND/mlexicon.py` | A: `_LATIN_TOKEN_RE`, `ENGLISH_MARKERS`, Latin branch of `detect()`. Lead: +87 high-precision English content words; `≥2` → `≥1` marker rule |
| `CODE/BACKEND/model_adapter.py` | B: C-F-5 — narrow `try/except`, `per_language` parsed independently, `LOG.warning` on unexpected errors, `threshold_rationale` initialised |
| `CODE/BACKEND/backend.py` | B: C-F-6 — `audit_log()` helper + `ENGINE_CHANGE` row in `set_engine`. Lead: Latin-`und` scoring fix in `apply_language_engine` |
| `CODE/BACKEND/tests_model_adapter_phase4.py` | Lead: 4 stale defect-characterisation assertions updated to the fixed contract (+1 new test → 34) |
| `CODE/FRONTEND/tests_e2e_phase4.py` | Lead: check 50 updated to the verified new disclosure contract |
| **New** `CODE/BACKEND/tests_langid_phase41.py` | A — 32 checks |
| **New** `CODE/BACKEND/tests_audit_threshold_phase41.py` | B — 16 tests |
| **New** `PHASE41_URDU_FPR.md` | C — Urdu gate record |
| `CODE/BACKEND/aura.db` | runtime rows only (engine-switch audit rows, prediction history) |

Removed after use: 4 throwaway `_probe_*.py` files.

---

## 2. Defects

### C-F-2 (unsupported Latin labelled `en`) — **COMPLETE**
`mlexicon.detect()` no longer returns a confident `en` for Latin text with no
English evidence; it returns `und`/`Unknown`. Verified live:

```
swahili -> code=und  lang=Unknown  kind=no_signal  status=legacy
spanish -> code=und  lang=Unknown  kind=no_signal  status=legacy
english -> code=en   lang=English  mode=existing_model
```

Regression coverage: English, Spanish, Swahili, Tamil script, Tanglish,
ambiguous short Latin, mixed-script, empty and 1-char input — `tests_langid_phase41.py`
32/32. No new dependency added; `backend.py:650-659` already handled `und`.

**Two regressions found and fixed during integration (my responsibility):**

1. **English detection broken.** `"have a nice day everyone"` yielded 1 marker
   and fell to `und`. Fixed by extending `ENGLISH_MARKERS` with high-precision
   English words absent from Spanish/Swahili (token-boundary matching means
   Swahili `bado` can't match `bad`).
2. **Safety downgrade — caught by `tests_word_input.py` (42→41).** Latin `und`
   routed to `apply_fallback_result`, neutralising scores so the known toxic
   term `idiot` became a neutral `ALLOW`. Fixed in `backend.py`: Latin `und`
   keeps the honest `und`/`Unknown`/`no_signal` **disclosure** but is scored by
   the default safety lexicon. C-F-2 required honest labelling, not weaker
   scoring. Non-Latin `und` (Chinese/emoji) still uses the neutral fallback.

Live proof: `idiot -> label=non_toxic action=WARN score=0.324` (was `0.05/ALLOW`).

### C-F-4 (Tanglish labelling) — **COMPLETE**
≥2 markers → `ta-Latn`; a single weak marker (`muttal`) → `und` instead of `en`.
Ordinary English is not swept in. Verified: `nee vera level mudhalai, unnai
verukkiren -> ta-Latn / language_lexicon`.

### C-F-5 (bare `except` discarding per-language thresholds) — **COMPLETE**
`_load_tuned` now parses `per_language` **independently** of the global entry;
valid language thresholds survive a malformed global; unexpected errors are
`LOG.warning`-ed, not swallowed; documented fallback applies only to the global
value. **Regression test now asserts the fixed behaviour** — the stale Phase 4
test encoded the bug and its own message told us to update it:
`assertEqual(per_language, {"en":0.55,"ta":0.40})` + threshold-override checks.
`tests_audit_threshold_phase41.py` 16/16.

### C-F-6 (`set_engine` audit) — **COMPLETE**
Reuses the existing `audit_logs(user_id, action, details, created_at)`
convention. All 32 rows carry `previous_engine`/`requested_engine`/
`resulting_engine`/`success` (+`error` on failures); **28 success, 4 correctly
logged as failures** (requirement: failed changes must not be logged as
successful); actor `admin`; 32 distinct timestamps, no duplicates.
Auth and switch behaviour unchanged; tested against temp SQLite — production
engine never switched *for testing*.

### C-F-1 — **CONFIRMED UNCHANGED**
Structural verification (B's edit sits above the lock and only shifted line
numbers): fast-fail `"model is loading"` at **line 302, still inside
`with self._lock:` at line 298** (dead-code preserved), 2 `with self._lock`
blocks, `AURA_MODEL_RETRY_S` backoff intact. Not modified, not re-tuned.
Proof by behaviour: `tests_model_adapter.py` **110/110**.

---

## 3. Urdu evaluation

| Item | Value |
|---|---|
| Baseline FPR | **0.256** (0.2556) |
| Documented acceptance cap | **0.15** — found, not invented, at 5 agreeing locations: `PHASE2_MODEL_EVALUATION.md:51,262`, `phase3_benchmark.json:10`, `PHASE4_WORKSTREAM_E.md:49,140`, `tuned_threshold.json:107` |
| Reproduction | `phase3_benchmark.json` matrix `[[67,23],[43,47]]` → FPR = 23/(23+67) = 23/90 = **0.2556**; P 0.6714, R 0.5222, F1 0.5875 all recompute exactly |
| Confidence interval | Wilson 95% **[0.177, 0.354]** — entirely above the cap (reused verbatim from `PHASE4_WORKSTREAM_E.md`) |
| Final FPR | **0.256 — unchanged** (no safe fix exists) |
| Status | **NOT PASSED** |
| Benchmark untouched | **YES** — `phase2`/`phase3`/`tuned_threshold` byte-identical |

Root cause (evidence-based, 4 findings):
1. **Task mismatch** — `ur` is an expert hate-speech corpus scored by a generic
   toxicity model; ROC-AUC only **0.704**, so the ranking itself is weak.
2. **No threshold fixes it** — 0.40 was validly selected on validation (val FPR
   0.133 ≤ cap); test-optimal 0.55 has *worse* F1 (0.394 vs 0.588).
3. **Ruled out by measurement**: routing (detect = `ur` 180/180), romanised
   Urdu (0 Latin/mixed rows), lexicon (fires 0/90 on negatives → all 23 FPs are
   model-score path), threshold mismatch (0.40 everywhere).
4. Negative class is charged political/religious but non-hate sentences —
   exactly what a generic toxicity model over-scores.

bn stays **INCONCLUSIVE**; ta-Latn F1 gain **not** claimed statistically
significant. No label, threshold or benchmark value was altered to pass.

---

## 4. Regression

**450 passed / 0 failed / 0 skipped** across 11 suites (all executed this phase):

| Suite | Result |
|---|---|
| `tests_dataset_import.py` | 40/40 |
| `tests_model_adapter.py` | **110/110** (54.5 s) |
| `tests_word_input.py` | 42/42 |
| `tests_multilingual.py` | 29/29 + 5/5 |
| `tests_frontend_apptest.py` | 35/35 |
| `tests_dataset_import_phase4.py` | 42/42 |
| `tests_model_adapter_phase4.py` | 34/34 |
| `tests_threshold_immutability.py` | 30/30 |
| `tests_e2e_phase4.py` | 35/35 |
| `tests_langid_phase41.py` *(new)* | 32/32 |
| `tests_audit_threshold_phase41.py` *(new)* | 16/16 |

**Not run:** `tests_metrics_phase4.py` (never existed — Phase 4 found no
metric-formula bug); pytest/lint/build (none configured in the repo); a full
`phase3_benchmark.py` re-run (artifacts byte-identical, not warranted).

**Unresolved failures: none.** Duplicated runs of `tests_model_adapter.py`
(one 107/110, one 110/110) count as **one** suite, not two.

---

## 5. Safety

| Check | Result |
|---|---|
| Final active engine | **`legacy`** (`source=settings`, `default=legacy`) |
| Live contract | `status=legacy`, `model=aura-legacy-rules-lexicon`, **no `toxicity_score`** |
| `tuned_threshold.json` | `f31f4975d29a151f…` **UNCHANGED** |
| `phase2_benchmark.json` | `5a9d94e267806ea0…` **UNCHANGED** |
| `phase3_benchmark.json` | `f3a5ceb488f4a9ad…` **UNCHANGED** |
| SQLite `integrity_check` | **ok** |
| SQLite `foreign_key_check` | **clean** |
| Dataset rows | **596** (unchanged) |
| Splits | **137/29/31 + 399 unassigned** (unchanged) |
| `training_runs` | **8** (unchanged) |
| Active model | `improved_v10` (unchanged) |
| `model_versions` | 12 (unchanged) |
| Deployment | **NONE** |
| Retraining | **NONE** |
| Engine for testing | never flipped for testing; audit tests used temp SQLite |
| DB backup | `data/backups/aura-phase41-baseline-20261011-101947.db` (11,046,912 B) |
| Unrelated services | Docker/Celery/Blockchain uvicorn untouched |

Incident disclosed: the `tests_model_adapter.py` suite legitimately switches
`legacy→hf→legacy` and restores itself; one background run was earlier killed
mid-suite by an external server restart and stranded `prediction_engine=hf`.
Detected by explicit state check and restored via the app's own
`POST /models/engine`, then confirmed three ways (DB, engine endpoint, live
prediction). Thresholds/splits/training state were untouched by that incident.

---

## 6. Remaining work

| Issue | Why unresolved | Smallest next action |
|---|---|---|
| **Urdu FPR 0.256 > cap 0.15** (`NOT PASSED`) | Task mismatch with ROC-AUC 0.704; no threshold improves both metrics; fixing needs new labels | Approve one of: (a) explicit out-of-scope exception for `ur`, (b) accept 0.40→0.55 at an F1 cost, (c) commission a ur-specific labelled set |
| **bn inconclusive** | Wilson CI straddles the cap | Nothing until new evidence |
| **ta-Latn F1 0.313 gain not significant** | CI [0.200, 0.419] overlaps the prior value | Nothing — do not claim significance |
| **`en` detection relaxed to ≥1 marker** | ≥2 broke real English (`have a nice day everyone`, the adapter sentinel) | Optional: add a second independent English signal (e.g. stopword density) to harden against a single English loanword inside Spanish/Swahili text |
| **C-F-1 blocking cold-load** | Explicitly excluded from modification this phase | Approval required; minimal fix documented in `PHASE4_WORKSTREAM_C.md` |
| **5-minute deadline exceeded** | Agent wait + integration debugging of the two C-F-2 regressions | None — safety checks were not skipped to meet it |
