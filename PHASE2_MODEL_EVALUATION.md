# AURA — Phase 2 Model Evaluation Report

> **Scope:** pretrained model integration · **Model:** Horizon-Labs/multilingual-toxicity-small
> **Status:** measured on held-out per-language data — no number below is estimated.

---

## 1. Objective

Evaluate **Horizon-Labs/multilingual-toxicity-small** against AURA's legacy
rules+lexicon engine on held-out per-language data **before any rollout**.

| Property | Value |
|---|---|
| Parameters | 141M |
| License | Apache-2.0 |
| Heads | 7 sigmoid multi-label: `toxicity`, `severe_toxicity`, `obscene`, `threat`, `insult`, `identity_attack`, `sexual_explicit` |
| Integration | modular adapter — `CODE\BACKEND\model_adapter.py` with an explicit engine switch |
| Baseline | legacy rules+lexicon engine (unchanged, remains the default) |

The model is integrated **behind the adapter**, never in-place: the legacy path
stays byte-for-byte intact and remains the default engine.

---

## 2. Data

Prepared by `CODE\BACKEND\prepare_phase2_eval.py` into
`CODE\BACKEND\data\phase2_eval\` with a `manifest.json` (provenance).

| Language | Validation | Test |
|---|---:|---:|
| en | 120 | 180 |
| hi | 120 | 180 |
| ta | 120 | 180 |
| ta-Latn | 120 | 180 |
| ur | 120 | 180 |
| bn | 95 | 143 |

**Caveats:**

- **bn labels are weak annotations produced by a Qwen model — not human gold labels.**
- The **test split was never touched** during threshold tuning.

---

## 3. Threshold tuning

- **Sweep:** 0.30 → 0.80, step 0.05, on the **pooled validation splits (n = 695)**
  plus per-language validation sweeps.
- **Selection rule:** maximize toxic F1 subject to validation FPR ≤ 0.15
  (`AURA_TUNE_FPR_CAP`); tie-break → higher threshold.
- Rule + rationale persisted to `models\tuned_threshold.json`.

**Pooled selected point — threshold 0.35:**

| Metric | Value |
|---|---:|
| Toxic F1 | 0.6585 |
| Recall | 0.5612 |
| Precision | 0.7966 |
| FPR | 0.1333 |

**Final thresholds:**

| Scope | Threshold |
|---|---:|
| Global | 0.35 |
| en | 0.55 |
| ta | 0.40 |
| ta-Latn | 0.30 |
| hi | 0.35 |
| bn | 0.30 |
| ur | 0.40 |

---

## 4. Held-out test results

| Language | n | legacy toxic F1 | model toxic F1 | model recall | model FPR | model ROC-AUC | latency ms/text |
|---|---:|---:|---:|---:|---:|---:|---:|
| en | 180 | 0.540 | **0.948** | 0.911 | 0.011 | 0.989 | 39.7 |
| ta | 180 | 0.021 | 0.529 | 0.411 | 0.144 | 0.728 | 164.2 |
| ta-Latn | 180 | 0.104 | 0.245 | 0.144 | 0.033 | 0.668 | 72.1 |
| hi | 180 | 0.065 | 0.638 | 0.489 | 0.044 | 0.861 | 112.2 |
| bn | 143 | 0.000 | 0.624 | 0.547 | 0.122 | 0.839 | 288.0 |
| ur | 180 | 0.000 | 0.588 | 0.522 | 0.256 | 0.704 | 102.9 |

**Memory:** before 21.5 MB → after 1168.9 MB (delta **1147.4 MB**),
CPU-only `torch 2.14.1+cpu`.

Full metric sets (accuracy, precision, recall, macro-F1, confusion matrix,
PR-AUC per group) live in `models\phase2_benchmark.json`; run log:
`models\benchmark_run2.log`.

Reference command (do not re-run blindly): `python benchmark_phase2.py --tune`.

---

## 5. Coverage gating

`MODEL_COVERAGE` in `model_adapter.py`:

| Tier | Languages |
|---|---|
| **validated** | en, hi |
| **experimental** (measured here, caveats apply) | ta, ta-Latn, bn, ur |
| **unmeasured** | everything else |

- `MODEL_CLAIMED_LANGUAGES` (from the model card) **deliberately excludes `ta`** —
  the model card does not claim Tamil.
- API responses carry `model_coverage` + `note`; unmeasured / card-claimed-only
  languages get `decision_status=experimental` and a **HUMAN_REVIEW** action.
- Unevaluated languages are marked **NOT EVALUATED** — never silently claimed.

---

## 6. Rollout control

`AURA_PREDICTION_ENGINE` = `legacy` (DEFAULT) | `auto` | `hf`.
Precedence: **settings table > env > default**.

| Control | Value |
|---|---|
| Admin read | `GET /models/engine` |
| Admin write | `POST /models/engine` |
| Adapter status | `GET /models/adapter` |
| Total API endpoints (openapi.json) | 42 |

- `auto` = languages in the coverage map **or** claimed by the model card.
- Model loads **lazily, once per process** (thread-safe singleton), with a
  warm-up thread on engine switch.
- Failure backoff: `AURA_MODEL_RETRY_S` (default **60s**).
- Weights are **never re-downloaded per request**.

---

## 7. Failure handling

- Any adapter failure leaves the **legacy result intact**, sets
  `decision_status=fallback` and a **sanitized one-line `model_error`**
  (filesystem paths masked, **no stack traces**) — HTTP **200**.
- Unknown engine value → **400**.

---

## 8. Honest limitations / unfinished work

1. **ta-Latn is weak** — toxic F1 0.245 on held-out test.
2. **bn labels are weak** (Qwen-generated), not human gold.
3. **Val/test FPR drift** — ur test FPR 0.256 and ta 0.144 despite the 0.15
   validation cap.
4. `confidence = max(tox, 1-tox)` is a **decision-margin proxy, NOT a
   calibrated probability**.
5. `language_confidence` is an **uncalibrated script-share heuristic**
   (Latin script → `None` with `kind=script_ambiguous`).
6. The model **overlays** the legacy action ladder rather than fully replacing
   legacy context blending (`processing_mode=pretrained_model`, but actions
   still derive from the legacy risk ladder).
7. Per-category sigmoid heads are **not** a single human "toxic" judgment.
8. CPU latency varies widely: **~40–290 ms/text**.
9. External CC0 datasets from Phase 1 are **still not imported into `aura.db`**
   (manual step, documented).

---

## 9. Reproduction

```powershell
$py = "C:\Users\gokul\OneDrive\Desktop\zip project\comment toxicity\.venv\Scripts\python.exe"
cd "C:\Users\gokul\OneDrive\Desktop\zip project\comment toxicity\CODE\BACKEND"

& $py prepare_phase2_eval.py          # rebuild eval splits + manifest
& $py benchmark_phase2.py --tune      # sweep + held-out benchmark

# start backend (port 8010), then:
# POST /auth/login        {"username":"admin","password":"Admin@1234"}
# POST /models/engine     {"engine":"hf"}

$env:AURA_BASE_URL = 'http://127.0.0.1:8010'
& $py tests_model_adapter.py
```

---

## 10. Phase 3 addendum

### 10.1 Root cause found for the ta-Latn (0.245) result

The Phase 2 threshold sweep started at **`t = 0.30`** (`benchmark_phase2.py`
lines 139 and 199: `t = 0.30`, stepping up by 0.05). Two consequences:

1. **The grid was truncated.** Any language whose validation optimum lies below
   0.30 could not be selected there.
2. **ta-Latn was pinned to the grid edge.** Its Phase 2 threshold is exactly
   **0.30** — the floor, not an optimum. The rule (`select_threshold`) then
   optimises F1 only inside that reachable range, which for a low-scoring,
   low-recall language costs recall.

Synthetic control (scores constructed to have a sub-0.30 optimum, **not** real
language data):

| Sweep floor | Selected threshold | Val F1 | Recall | FPR (cap 0.15) |
|---|---:|---:|---:|---:|
| 0.30 (Phase 2) | 0.80 | **0.000** | 0.000 | 0.000 |
| 0.05 (Phase 3) | 0.05 | **0.919** | 1.000 | 0.058 |

A second control confirms the **safety budget is unchanged**: a high-overlap
language still selects the FPR-minimising threshold (FPR 0.000 ≤ cap).

Fix: `CODE/BACKEND/benchmark_phase3.py` sweeps **0.05–0.90**. The selection
rule is untouched — *max toxic F1 subject to validation FPR ≤ 0.15, tie-break
higher threshold* — and selection still uses **validation splits only**.

### 10.2 Other root causes under investigation

- **Urdu FPR drift** (test FPR 0.256 vs the 0.15 validation cap): the language
  has the lowest ROC-AUC of the Indic set (0.704), so a single global operating
  point does not transfer. Whether this is score-distribution shift or noisy
  labels is being measured per row before any threshold change.
- **Bengali weak labels**: the bn corpus was annotated by a Qwen model, not
  humans. bn metrics are reported with that caveat attached and must not be
  read as gold-label performance.
- **Duplicate-content label conflict found in the Phase 1 pipeline**:
  `fetch_external_datasets.py` deduplicated on `text.lower()` only, so a
  whitespace-differing copy survived and the pair `civil_comments-82/84` —
  identical text, **opposite labels** — was assigned to two different splits.
  Fixed (shared whitespace-collapsed key + explicit conflicting-label detection).

### 10.3 Measured result of the fix (`models/phase3_benchmark.json`)

`benchmark_phase3.py` ran to completion on the same held-out test splits.
Selection stayed on **validation only**; test was read once, for reporting.

| Lang | n (pos/neg) | val thr | test P | test R | **test F1** | macro-F1 | acc | **test FPR** | ROC-AUC | PR-AUC | legacy F1 | vs Phase 2 thr |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| en | 180 (90/90) | 0.55 | 0.988 | 0.911 | **0.948** | 0.950 | 0.950 | 0.011 | 0.989 | 0.990 | 0.540 | 0.000 |
| ta | 180 (90/90) | 0.40 | 0.740 | 0.411 | **0.529** | 0.614 | 0.633 | 0.144 | 0.728 | 0.747 | 0.021 | 0.000 |
| ta-Latn | 180 (90/90) | **0.25** | 0.720 | 0.200 | **0.313** | 0.495 | 0.561 | 0.078 | 0.668 | 0.659 | 0.104 | **+0.068** |
| hi | 180 (90/90) | 0.35 | 0.917 | 0.489 | **0.638** | 0.706 | 0.722 | 0.044 | 0.861 | 0.874 | 0.065 | 0.000 |
| bn | 143 (53/90) | **0.25** | 0.709 | 0.736 | **0.722** | 0.777 | 0.790 | **0.178** | 0.839 | 0.743 | 0.000 | **+0.099** |
| ur | 180 (90/90) | 0.40 | 0.671 | 0.522 | **0.588** | 0.629 | 0.633 | **0.256** | 0.704 | 0.697 | 0.000 | 0.000 |

Confusion matrices (`[[tn,fp],[fn,tp]]`), held-out test:

| Lang | Model | Legacy |
|---|---|---|
| en | `[[89,1],[8,82]]` | F1 0.540 |
| ta | `[[77,13],[53,37]]` | F1 0.021 |
| ta-Latn | `[[83,7],[72,18]]` | F1 0.104 |
| hi | `[[86,4],[46,44]]` | F1 0.065 |
| bn | `[[74,16],[14,39]]` | F1 0.000 |
| ur | `[[67,23],[43,47]]` | F1 0.000 |

- **Pooled validation**: n=695 (335 positive), threshold **0.35** unchanged,
  F1 0.658, FPR 0.133.
- **Memory**: 18.0 MB -> 1138.3 MB working set (delta ~1120 MB), CPU-only.
- **Latency** (this run, batch 8 on a loaded CPU): en 147, ta 530, ta-Latn 191,
  hi 387, bn 952, ur 336 ms/text. Higher than the Phase 2 figures (40-290 ms),
  which were measured with batch 16 and less contention - treat both as
  CPU-only, load-dependent numbers, not serviceable latencies.
- **FPR cap on test: NOT met for bn (0.178) and ur (0.256)** against the 0.15
  validation cap. Both are reported, not tuned away.

#### Statistical confidence on these figures (Phase 4, Workstream E)

CIs are approximate, computed from the stored confusion-matrix counts (Wilson
95% for FPR; 20k parametric bootstrap for F1). Per-row bootstrap was **not**
possible because the artifact stores aggregate counts, not per-row scores.

| Lang | test F1 [95% CI] | test FPR [95% CI] | Reading |
|---|---|---|---|
| en | 0.948 [0.910, 0.979] | 0.011 [0.002, 0.060] | meaningful — tight; clearly better than legacy (0.540) |
| ta | 0.529 [0.422, 0.624] | 0.144 [0.086, 0.232] | F1 meaningful vs legacy (0.021); FPR CI straddles cap |
| ta-Latn | 0.313 [0.200, 0.419] | 0.078 [0.038, 0.152] | gain **not statistically firm** |
| hi | 0.638 [0.538, 0.726] | 0.044 [0.017, 0.109] | meaningful — CI excludes legacy (0.065) |
| bn | 0.722 [0.617, 0.811] | 0.178 [0.113, 0.269] | breach **not conclusive** |
| ur | 0.588 [0.493, 0.674] | **0.256 [0.177, 0.354]** | breach **is real** |

- **ta-Latn**: the 0.245 → 0.313 improvement sits **inside overlapping
  confidence intervals** ([0.200, 0.419]), so it is a *directional indication*,
  not a proven gain. This is why it was left unadopted rather than rolled out.
- **bn**: the FPR CI straddles the 0.15 cap, so the breach is *suggestive, not
  conclusive* at n=90 negatives; bn additionally uses weak Qwen labels.
- **ur**: the CI lies entirely above 0.15 — the cap breach is genuine, which is
  consistent with the task-mismatch root cause (§10.4), not with threshold drift.
- **en and hi** are the only two groups whose F1 is clearly separated from the
  legacy baseline at these sample sizes.

Method (Workstream E): closed-form **Wilson 95% CI for FPR** (binomial, n =
negatives) and a **parametric multinomial bootstrap for F1** resampling only the
2×2 confusion cells, 20k draws. An exact per-row bootstrap is **not computable
without re-scoring**, because the artifact stores aggregate counts rather than
per-row scores — so these intervals are approximate and are labelled as such.

#### Evidence for the ta-Latn fix

Validation sweep (the part the 0.30 floor used to hide):

| val thr | ta-Latn F1 / FPR | bn F1 / FPR |
|---|---|---|
| 0.20 | 0.293 / 0.167 (over cap) | 0.686 / 0.183 (over cap) |
| **0.25** | **0.250 / 0.050 (selected)** | **0.633 / 0.100 (selected)** |
| 0.30 (old floor) | 0.174 / 0.050 | 0.539 / 0.050 |
| 0.35 | 0.119 / 0.050 | 0.480 / 0.050 |

Lowering the floor is **strictly better on validation** for both languages, with
identical validation FPR at 0.25 vs 0.30.

### 10.4 Why ur and bn remain weak (task mismatch)

The manifest (verified in Phase 3) shows these are not generic-toxicity corpora:
`ur` is an **expert hate-speech** dataset scored by a toxicity model, `ta` /
`ta-Latn` use **offensiveness** labels, `bn` uses **weak Qwen annotations**.
This is consistent with what the numbers show:

- **ur**: no threshold does well. The test-optimal threshold is **0.55** with a
  *worse* F1 (0.394) than at 0.40 (0.588) - the ROC-AUC of 0.704 means the
  ranking itself is weak for this label definition, not merely mis-thresholded.
  Raising the threshold would cut the FPR by silencing genuine detections.
- **bn**: the F1 gain (+0.099) comes with test FPR 0.178, above the 0.15 safety
  budget, so it is **not** recommended without an explicit policy decision.
- **ta-Latn** remains the weakest group in absolute terms (F1 0.313): its rows
  are Latin-script text and the model card does not claim Tamil.

### 10.5 What has NOT changed

The tuned thresholds actually deployed are **still the Phase 2 values**
(`.en 0.55 · .ta 0.40 · .ta-Latn 0.30 · .hi 0.35 · .bn 0.30 · .ur 0.40`) —
`models/tuned_threshold.json` is untouched (`tuned_at` unchanged). The new
values were **not** written with `--write-thresholds`, because:

- `ta-Latn 0.25` is evidence-backed and safe (test FPR 0.078 ≪ cap) — a clear
  candidate, left for an explicit rollout decision.
- `bn 0.25` trades a safety-budget breach (test FPR 0.178 > 0.15) for F1.

The transformer remains opt-in and the legacy engine remains the default.

### 10.6 External dataset import

399 CC0 rows (Civil Comments 199, Wiki Toxic 200) were imported
transactionally and idempotently; counts, provenance and caveats are in
`DATASET_GUIDE.md` §8. Neither dataset contains non-English rows, so this does
**not** change any per-language result above.
