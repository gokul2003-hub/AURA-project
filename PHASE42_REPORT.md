# AURA Phase 4.2 — Final Report

**Objective:** improve Urdu toxicity detection using a properly labelled Urdu
dataset and an isolated model evaluation, **without** changing the live
production engine or any protected threshold.

**Overall verdict: `NOT PASSED` (gate) — dataset work and isolated evaluation
both completed with measured evidence.** The production system is unchanged.

Baseline captured and final state verified 2026-10-11.

---

## 1. Dataset availability and provenance

**Verdict: a suitable dataset already exists — no import pipeline was needed.**

| Item | Finding |
|---|---|
| Source | `Adnan855570/Urdu_Hate_Speech` — verified in `data/phase2_eval/manifest.json:109` and corroborated by 4 project documents |
| Licence | **MIT** (explicitly stated; not inferred) |
| Row provenance | `source_row_id` + `source_url` present per row |
| Fetch size | 26,174 rows fetched upstream → balanced 150/150 subset retained |
| `ur_val.csv` | **120** rows — 60 toxic / 60 non-toxic (tuning only) |
| `ur_test.csv` | **180** rows — 90 toxic / 90 non-toxic (held out) |
| Label column | `label`, values `{0,1}` |
| Missing labels | **0** |
| Empty texts | **0** |

**Quality checks (all measured):**

| Check | Result |
|---|---|
| Exact-duplicate texts within `ur_val.csv` | **0** |
| Exact-duplicate texts within `ur_test.csv` | **0** |
| Val ↔ test shared texts (leakage) | **0** |
| Contradictory labels for identical text | **0** |
| Train ↔ eval overlap in `aura.db` | **0** — read-only check |
| Splits unchanged | 137 / 29 / 31 + 399 unassigned |

**Synthetic vs real — separated explicitly:**
- The **eval CSVs are a real, expert-labelled corpus** (source-tracked). These
  are the benchmark.
- The **8 `ur` rows inside `aura.db` are `source='curated_demo'` synthetic demo
  data** (6 train / 2 test) with **zero text overlap** against the 300 eval rows.
- `data/lexicons/ur.json` self-declares *"demo/dev quality. Not benchmark data."*
  (`ur.json:5`) — **it was not treated as benchmark data.**

No dataset was fabricated and no training was claimed.

---

## 2. Urdu script and Roman Urdu coverage

| Script | `ur_val` | `ur_test` |
|---|---|---|
| Arabic-script Urdu (U+0600–U+06FF) | **120 / 120 (100%)** | **180 / 180 (100%)** |
| Latin / Roman Urdu | **0** | **0** |
| Mixed script | **0** | **0** |

**Roman Urdu is entirely absent from the held-out evaluation data.** This is
recorded as a measured gap, not assumed coverage. Any claim about Roman Urdu
performance would be unsupported by this dataset.

---

## 3. Baseline and candidate metrics

### Baseline (unchanged, reproduced from `phase3_benchmark.json`)

| Metric | Value |
|---|---|
| Threshold used | **0.40** |
| n | **180** (90 toxic / 90 non-toxic) |
| Confusion matrix `[[TN,FP],[FN,TP]]` | **`[[67,23],[43,47]]`** |
| **FPR** | **0.2556** (23 / 90) |
| Precision / Recall / F1 | 0.6714 / 0.5222 / **0.5875** |
| ROC-AUC | 0.7044 |
| Documented acceptance cap | **0.15** — found at 5 agreeing locations, **not invented** |

### Candidate (isolated evaluation)

**Key finding: the only compatible multilingual toxicity model available
locally is the same checkpoint the Phase 3 baseline already used.** This was
therefore an isolated **re-measure**, not a genuinely new candidate.

| Item | Value |
|---|---|
| Model | `Horizon-Labs/multilingual-toxicity-small` |
| Snapshot | `3baf7739…`, 536.53 MB, fp32 ModernBert 141 M |
| Licence | **Apache-2.0** (upstream model card; no licence field in local config) |
| Provenance | already on disk in `models/hf_cache/` — **nothing downloaded** (`HF_HUB_OFFLINE=1`) |
| Head | 7-label sigmoid, toxicity = index 0 |
| Threshold selection | **0.38**, chosen on **`ur_val.csv` only** (max F1 subject to val FPR ≤ 0.15; val FPR exactly 0.1500, val AUC 0.7883) |

**Test metrics (`ur_test.csv`, n = 180):**

| Metric | Candidate @ 0.38 | Baseline @ 0.40 |
|---|---|---|
| **FPR** | **0.3000** | **0.2556** |
| FPR Wilson 95% CI | [0.215, 0.401] | [0.177, 0.354] |
| Precision | 0.6494 | 0.6714 |
| Recall | 0.5556 | 0.5222 |
| F1 | 0.5988 | 0.5875 |
| ROC-AUC | 0.7006 | 0.7044 |
| Confusion matrix | `[[63,27],[40,50]]` | `[[67,23],[43,47]]` |

The FPR confidence intervals overlap and the F1 difference is within noise —
consistent with both runs measuring the **same checkpoint**. The Urdu
false-positive problem is the model's Urdu discrimination, **not** the adapter,
the routing or the threshold plumbing.

**Coverage measured:** 180/180 test rows are Arabic-script with **0 unknown
tokens**, but heavy fragmentation at **4.48 subwords/word**. Roman Urdu is
**unmeasured** (0 rows exist to measure it on); tokenizer probes show it is
*representable*, which is not the same as *supported*.

**Runtime and resources measured:** model load 35.5 s, inference 206.3 s
(~688 ms/text, 4 threads), total **241.9 s**. Free RAM 6.02 GB → 4.50 GB of
15.63 GB. Peak RSS unmeasured (`psutil` absent).

**Limitations:** max sequence length was reduced to 96 tokens after a 256-token
run exceeded the 150 s harness budget; truncation affects 5.6% of rows, judged
negligible versus the AUC delta of 0.004. No second candidate exists locally.

---

## 4. Acceptance gate — **`NOT PASSED`**

Documented cap **0.15**. Baseline FPR **0.2556**, candidate FPR **0.3000**.
Both Wilson intervals lie entirely above the cap. **No candidate passes.**

Nothing was tuned on the held-out test set — the candidate threshold (0.38) was
selected on `ur_val.csv` alone. No candidate was deployed. No production
threshold was changed to force the gate.

**Next evidence-backed step:** the metric is a *hate-speech* corpus being
scored by a *generic* toxicity model (baseline ROC-AUC only 0.704), so no
threshold improves both FPR and F1. The gate cannot be closed by threshold work.
The realistic options remain those identified in Phase 4.1: (a) an explicit
out-of-scope exception for `ur`, (b) accepting an F1 cost, or (c) commissioning
a ur-specific labelled set that matches the toxicity task — which the MIT
licence and clean provenance of this dataset make a practical basis.

---

## 5. Tests actually executed

| Suite | Result |
|---|---|
| Urdu dataset analysis (throwaway script, `%TEMP%`) | 120 val / 180 test, 0 dupes, 0 leakage — exit 0 |
| Isolated candidate eval (`%TEMP%\p42_cand_eval.py`) | **exit 0**, 241.9 s |
| Protected-artifact + DB integrity verification | integrity **ok**, FK **clean** — exit 0 |
| Truncation impact check (`p42_trunc_check.py`) | 5.6% of rows — exit 0 |

**Not run / not needed:** no `tests_*.py` production suite was executed this
phase, because **no production file was modified** — there was nothing to
regress. Model-adapter compatibility was unaffected by construction (the
adapter was never imported by the isolated evaluation).

---

## 6. Files changed

**Production code: NONE.**

| File | Change |
|---|---|
| `PHASE42_URDU_DATASET.md` | **New** — dataset provenance, quality, coverage |
| `PHASE42_CANDIDATE_EVAL.md` | **New** — isolated candidate evaluation |
| `PHASE42_REPORT.md` | **New** — this report |
| `%TEMP%\p42_cand_eval.py`, `p42_trunc_check.py`, `p42_run.log`, `p42_partial.json`, `urdu_analyze.py` | Throwaway analysis scripts, **outside** the project |

Untouched by design: `mlexicon.py`, `backend.py`, `model_adapter.py`, `app.py`,
all `tests_*.py`, `tuned_threshold.json`, `phase2_benchmark.json`,
`phase3_benchmark.json`, `aura.db`, and every `data/*.csv`.

---

## 7. Final engine and database state

| Check | Value |
|---|---|
| **Active engine** | **`legacy`** |
| `tuned_threshold.json` | `f31f4975d29a151f…` **UNCHANGED** |
| `phase2_benchmark.json` | `5a9d94e267806ea0…` **UNCHANGED** |
| `phase3_benchmark.json` | `f3a5ceb488f4a9ad…` **UNCHANGED** |
| SQLite `integrity_check` | **ok** |
| SQLite `foreign_key_check` | **clean** |
| Dataset rows | **596** (unchanged) |
| Splits | **137 / 29 / 31 + 399 unassigned** (unchanged) |
| `training_runs` | **8** (unchanged) |
| `model_versions` | **12** (unchanged) |
| Active model | `improved_v10` (unchanged) |
| Deployment | **NONE** |
| Retraining | **NONE** |
| Model downloads | **NONE** — evaluation ran with `HF_HUB_OFFLINE=1` against the existing local snapshot |
| HF cache | 1 model, unchanged |

C-F-1 locking behaviour was not touched this phase and remains as fixed in
Phase 4.1.

---

## 8. Remaining blockers

| Blocker | Detail |
|---|---|
| **Urdu FPR gate `NOT PASSED`** | 0.2556 (baseline) / 0.3000 (candidate) vs cap 0.15; ROC-AUC 0.704 means no threshold fixes it. Needs a decision from the three options in §4. |
| **Roman Urdu unevaluated** | 0 Roman-Urdu rows exist in the held-out set; any Roman-Urdu claim would be fabricated. Needs a romanised labelled subset. |
| **No second candidate available locally** | Only one compatible model exists on disk; finding a genuinely better multilingual toxicity model requires evaluation of models not yet downloaded. |
| **Task mismatch unresolved** | Expert hate-speech corpus scored by a generic toxicity model — the core cause of the FPR breach. |
| **Max sequence length 96** | A full 256-token run was time/RAM limited; impact measured at 5.6% of rows. Re-running at 256 would confirm. |
| **Peak RSS unmeasured** | `psutil` absent from the venv. |

**Production remains unchanged and requires separate deployment approval.**
