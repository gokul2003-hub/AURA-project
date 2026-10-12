# AURA Phase 4 — Workstream E: Evaluation / Reproducibility Pipeline Audit

> **Scope:** read-only audit of the evaluation & reproducibility pipeline.
> **No model was loaded, nothing was retrained, no file under `models/` was modified.**
> Auditor runs: CPU-only, stdlib Python against fixed on-disk artifacts.
> Date of audit: 2026-10-10.

---

## 0. Safety-compliance attestation

| Constraint | Status | Evidence |
|---|---|---|
| Never retrain / never call `split_dataset()` | **HELD** | No training or split call was made. All scripts read CSV/JSON only. |
| Never modify `models/*` (read-only) | **HELD** | `tuned_threshold.json` sha256 = `F31F4975D29A151F3F8737AE18875F6A5D11C2EE8719D126C587F7B339285C54`; prefix `f31f4975d29a151f` **MATCHES** the expected value (verified via `Get-FileHash`, before and after audit — file never written). |
| Never trigger a transformer load | **HELD** | No `benchmark_*.py` was executed; no HF prediction was made; only stored JSON/CSV/log were read. |
| Never write to `aura.db` | **HELD** | DB never opened for write; only CSVs/JSONs read. |
| Never start/stop/kill a process | **HELD** | No service/browser/Docker/Celery action taken. |
| Never modify splits / the 399 `split=''` rows | **HELD** | No split or DB row touched. |
| Never run the 5 coordinator-owned suites | **HELD** | `tests_dataset_import.py`, `tests_model_adapter.py`, `tests_word_input.py`, `tests_multilingual.py`, `tests_frontend_apptest.py` were **NOT run** (see test table). |

---

## 1. Reproducibility verdict — **PASS (inputs are fixed and reproducible)**

| Check | Result | Evidence |
|---|---|---|
| Eval CSVs fixed on disk | **YES** | `data/phase2_eval/{en,hi,ta,ta-Latn,bn,ur}_{val,test}.csv` present; row counts match `manifest.json` exactly (en/hi/ta/ta-Latn/ur = 120 val + 180 test; bn = 95 + 143). |
| Seed present | **YES** | `prepare_phase2_eval.py:53` `SEED = 42`; `split_val_test` uses `seed + 7` (line 281). `manifest.json:3` records `"seed": 42`, `"per_class": 150`. |
| Deterministic builder | **YES** | `stratify()` (line 264) and `split_val_test()` (line 279) use `random.Random(seed)` — local RNG, reproducible. |
| Manifest/provenance | **YES** | `data/phase2_eval/manifest.json` records dataset, url, license, label_notes and per-split counts per group. |
| Eval splits disjoint from training data | **YES** | Audited: **0** normalised-text overlaps between any eval split and the 197 training/demo texts (`data/train|validation|test` + `data/multilingual/*/split.csv`). |
| val <-> test isolation | **INTACT** | **0** exact AND **0** normalised duplicate texts between val and test for every group. |
| Cross-group reuse | **NONE** | **0** texts shared across any pair of language groups. |
| Class balance | As documented | 50/50 for en/hi/ta/ta-Latn/ur; bn 36.97% toxic (~37%, matches "bn 37%" claim in `PROJECT_AUDIT_REPORT.md:484`). |

Verdict: the evaluation inputs are fixed, seeded, provenance-tracked, and
demonstrably isolated from each other and from training data. Reproducing a run
requires only re-scoring the same CSVs; no hidden randomness in the split.

---

## 2. Threshold-selection boundaries — **CORRECT (validation-only); test used once for reporting**

| Aspect | Result | Evidence |
|---|---|---|
| Phase 3 sweep range | 0.05..0.90 step 0.05 | `benchmark_phase3.py:49-51` |
| Selection rule | max toxic F1 s.t. val FPR <= cap (tie-break higher thr) | `benchmark_phase2.py:163-175` (`select_threshold`); invoked from `benchmark_phase3.py:96-99` |
| FPR cap | 0.15 (env-overridable `AURA_TUNE_FPR_CAP`) | `benchmark_phase2.py:155-160` |
| Thresholds selected on | **VALIDATION only** | `benchmark_phase3.py:138-144`: sweep + `pick()` computed from `val` rows; comment "test never consulted". `tuned[g] = thr` (line 144) comes from `v_sweep`. |
| Pooled global threshold | **VALIDATION only** | `benchmark_phase3.py:202-223`: pooled from all groups' `val` splits. |
| Held-out test usage | Scored **once**, report-only | `benchmark_phase3.py:146-151`. |
| `--write-thresholds` payload | validation-only provenance | `benchmark_phase3.py:255-269` writes `tuned` (val-selected). **Not invoked** — `tuned_threshold.json` `tuned_at` = `2026-10-09T16:57:48` (Phase 2), unchanged. |

**No place lets test data influence a chosen threshold.** The only test-set
derived quantities are *diagnostic* and stored under `threshold_drift`
(`benchmark_phase3.py:157-168`): `test_optimal_threshold`,
`test_f1_at_own_optimum`, `test_fpr_at_val_threshold`. These are **never** fed
back into `tuned` or the persisted thresholds. See §7 for the labeling note.

Phase 2 (`benchmark_phase2.py`) is likewise validation-only
(`tune_threshold:128-145`, `tune_global:178-231`); its documented defect was the
**0.30 sweep floor** (lines 139, 199), not test leakage — the floor is what
Phase 3 fixed.

---

## 3. Metric formulas — **NO BUG FOUND (independently re-derived from confusion matrices)**

`benchmark_phase2.py` `metrics()` (lines 50-76):

| Metric | Formula in code | Verdict |
|---|---|---|
| precision | `tp/(tp+fp)` (l.56) | correct |
| recall | `tp/(tp+fn)` (l.57) | correct |
| toxic F1 | `2PR/(P+R)` (l.58) | correct |
| negative-class precision | `tn/(tn+fn)` (l.59) | correct (NPV) |
| negative-class recall | `tn/(tn+fp)` (l.60) | correct (specificity) |
| macro-F1 | `(f1+nf1)/2` (l.70) | correct (mean of both class F1s) |
| FPR | `fp/(fp+tn)` (l.63) | correct |
| accuracy | `(tp+tn)/n` (l.62) | correct |
| ROC-AUC | rank-based Mann-Whitney U, ties averaged (l.79-98) | correct |
| PR-AUC | step AP, ties grouped at block end (l.101-125) | correct (sklearn-style) |

Independent recomputation: for all 6 languages I recomputed precision, recall,
F1, macro-F1, accuracy and FPR **directly from the stored `[[tn,fp],[fn,tp]]`
matrices** in `phase3_benchmark.json` and compared to the stored values.
**0 mismatches** (see §8 command output). The formulas and the stored numbers are
internally consistent. **No formula bug, therefore no `tests_metrics_phase4.py`
was created** (the deliverable only calls for a fix+test if an unambiguous bug
exists — none does).

---

## 4. Number-by-number cross-check: reports vs `models/phase3_benchmark.json`

Legend: **P** = value printed in the report; **J** = value in
`phase3_benchmark.json`. Rounding to the printed precision is a MATCH.
"P10.3" = `PHASE2_MODEL_EVALUATION.md` §10.3; "A16.3" = `PROJECT_AUDIT_REPORT.md` §16.3.

### 4.1 Per-language table (P10.3 lines 235-242; A16.3 lines 445-452)

| Metric | en P / J | ta P / J | ta-Latn P / J | hi P / J | bn P / J | ur P / J | Verdict |
|---|---|---|---|---|---|---|---|
| n (pos/neg) | 180(90/90) / 180(90/90) | 180(90/90) / same | 180(90/90) / same | 180(90/90) / same | 143(53/90) / 143(53/90) | 180(90/90) / same | MATCH |
| val thr | 0.55 / 0.55 | 0.40 / 0.40 | 0.25 / 0.25 | 0.35 / 0.35 | 0.25 / 0.25 | 0.40 / 0.40 | MATCH |
| test P | 0.988 / 0.988 | 0.740 / 0.74 | 0.720 / 0.72 | 0.917 / 0.9167 | 0.709 / 0.7091 | 0.671 / 0.6714 | MATCH |
| test R | 0.911 / 0.9111 | 0.411 / 0.4111 | 0.200 / 0.2 | 0.489 / 0.4889 | 0.736 / 0.7358 | 0.522 / 0.5222 | MATCH |
| test F1 | 0.948 / 0.948 | 0.529 / 0.5286 | 0.313 / 0.313 | 0.638 / 0.6377 | 0.722 / 0.7222 | 0.588 / 0.5875 | MATCH |
| macro-F1 | 0.950 / 0.9499 | 0.614 / 0.6143 | 0.495 / 0.4953 | 0.706 / 0.7062 | 0.777 / 0.7768 | 0.629 / 0.6288 | MATCH |
| accuracy | 0.950 / 0.95 | 0.633 / 0.6333 | 0.561 / 0.5611 | 0.722 / 0.7222 | 0.790 / 0.7902 | 0.633 / 0.6333 | MATCH |
| test FPR | 0.011 / 0.0111 | 0.144 / 0.1444 | 0.078 / 0.0778 | 0.044 / 0.0444 | 0.178 / 0.1778 | 0.256 / 0.2556 | MATCH |
| ROC-AUC | 0.989 / 0.9888 | 0.728 / 0.7277 | 0.668 / 0.6677 | 0.861 / 0.8611 | 0.839 / 0.839 | 0.704 / 0.7044 | MATCH |
| PR-AUC | 0.990 / 0.9901 | 0.747 / 0.7465 | 0.659 / 0.6585 | 0.874 / 0.8735 | 0.743 / 0.7429 | 0.697 / 0.6967 | MATCH |
| legacy F1 | 0.540 / 0.5397 | 0.021 / 0.0215 | 0.104 / 0.1042 | 0.065 / 0.0645 | 0.000 / 0.0 | 0.000 / 0.0 | MATCH |
| vs P2 thr (delta F1) | 0.000 / 0.0 | 0.000 / 0.0 | +0.068 / 0.0677 | 0.000 / 0.0 | +0.099 / 0.0985 | 0.000 / 0.0 | MATCH |

### 4.2 Confusion matrices (P10.3 lines 246-253)

| Lang | P10.3 `[[tn,fp],[fn,tp]]` | J `confusion_matrix.matrix` | Verdict |
|---|---|---|---|
| en | `[[89,1],[8,82]]` | `[[89,1],[8,82]]` | MATCH |
| ta | `[[77,13],[53,37]]` | `[[77,13],[53,37]]` | MATCH |
| ta-Latn | `[[83,7],[72,18]]` | `[[83,7],[72,18]]` | MATCH |
| hi | `[[86,4],[46,44]]` | `[[86,4],[46,44]]` | MATCH |
| bn | `[[74,16],[14,39]]` | `[[74,16],[14,39]]` | MATCH |
| ur | `[[67,23],[43,47]]` | `[[67,23],[43,47]]` | MATCH |

### 4.3 Scalar / narrative numbers

| Claim (location) | Printed | JSON | Verdict |
|---|---|---|---|
| Pooled val rows (P10.3:255, A:342) | 695 | `global_validation.n` 695 | MATCH |
| Pooled val positives (P10.3:255) | 335 | `global_validation.positives` 335 | MATCH |
| Pooled threshold (P10.3:255) | 0.35 | `global_validation.threshold` 0.35 | MATCH |
| Pooled val F1 (P10.3:256) | 0.658 | `global_validation.toxic_f1` 0.6585 | MATCH |
| Pooled val FPR (P10.3:256) | 0.133 | `global_validation.fpr` 0.1333 | MATCH |
| Memory before (P10.3:257, A:463) | 18.0 MB | `memory_mb.before` 18.0 | MATCH |
| Memory after (P10.3:257, A:463) | 1138.3 MB | `memory_mb.after` 1138.3 | MATCH |
| FPR cap = 0.15 (task item 10) | 0.15 | `model.fpr_cap` 0.15 | MATCH |
| 695 validation rows (task item 10) | 695 | `global_validation.n` 695 | MATCH |
| ta-Latn F1 0.313 (task item 10) | 0.313 | `groups.ta-Latn.test_model.toxic_f1` 0.313 | MATCH |
| bn FPR 0.178 (task item 10) | 0.178 | `groups.bn.test_model.fpr` 0.1778 | MATCH |
| ur FPR 0.256 (task item 10) | 0.256 | `groups.ur.test_model.fpr` 0.2556 | MATCH |
| FPR cap breached on test (P10.3:262) | bn 0.178, ur 0.256 | `fpr_cap_respected_on_test` false; both drift `...exceeds_cap` true | MATCH |
| Latency this run en/ta/ta-Latn/hi/bn/ur (P10.3:258) | 147/530/191/387/952/336 | `test_model.latency_ms_per_text` 147.07/530.14/190.89/387.02/951.69/336.21 | MATCH |
| ta-Latn val @0.25 F1/FPR vs @0.30 (A:455, P10.3:272) | 0.250/0.050 vs 0.174/0.050 | `validation_sweep` "0.25"→F1 0.25,FPR 0.05; "0.3"→F1 0.1739,FPR 0.05 | MATCH |
| bn val @0.25 F1/FPR vs @0.30 (P10.3:272-273) | 0.633/0.100 vs 0.539/0.050 | "0.25"→0.6333/0.1; "0.3"→0.5385/0.05 | MATCH |
| ur test-optimal thr (P10.4:286, A:460) | 0.55 | `groups.ur.threshold_drift.test_optimal_threshold` 0.55 | MATCH |
| ur F1 at own optimum (P10.4:287, A:461) | 0.394 | `...test_f1_at_own_optimum` 0.3937 | MATCH |
| ur F1 at val thr 0.40 (P10.4:287) | 0.588 | `...test_f1_at_val_threshold` 0.5875 | MATCH |
| Phase 2 floor at `t=0.30` lines 139/199 (P10.1:191) | 139, 199 | `benchmark_phase2.py:139` and `:199` both `t = 0.30` | MATCH (source) |
| Deployed thresholds still Phase 2 (P10.5:298, A:465) | en .55/ta .40/ta-Latn .30/hi .35/bn .30/ur .40 | `tuned_threshold.json.per_language` = same; `tuned_at` 2026-10-09 unchanged | MATCH |

**Cross-check verdict: every number printed in `PHASE2_MODEL_EVALUATION.md` §10.3 and `PROJECT_AUDIT_REPORT.md` §16.3 matches `phase3_benchmark.json` (within printed rounding). 0 mismatches.**

Note: P10.3 §15.2 (Phase 2 summary, `PROJECT_AUDIT_REPORT.md:332-341`) also matches
`phase2_benchmark.json` (e.g. ta-Latn model F1 0.245↔0.2453, bn 0.624↔0.6237,
latency 39.7↔39.68 etc.).

---

## 5. Class/label definitions & provenance — **CONFIRMED (one doc typo)**

Positive class = toxic/offensive/hate (label 1); negative = non-toxic (label 0).
Confirmed against `data/phase2_eval/manifest.json`:

| Group | Source (manifest) | License | Label basis | vs documented table | Verdict |
|---|---|---|---|---|---|
| en | `textdetox/multilingual_toxicity_dataset` | OpenRAIL++ | binary `toxic` as-is | matches `PROJECT_AUDIT_REPORT.md:475`, `DATASET_GUIDE.md:170` | MATCH |
| hi | `textdetox/multilingual_toxicity_dataset` | OpenRAIL++ | binary `toxic` as-is | matches | MATCH |
| ta | `community-datasets/offenseval_dravidian` | CC-BY-4.0 | 0=Not_offensive->0; 1-4=Offensive->1; 5 excluded; Tamil script only | matches `AUDIT:476`, `GUIDE:171` | MATCH |
| ta-Latn | `community-datasets/offenseval_dravidian` | CC-BY-4.0 | same labels, rows WITHOUT Tamil script | matches intent | MATCH (manifest) — **see doc typo below** |
| bn | `Polygl0t/bengali-toxicity-qwen-annotations` | Apache-2.0 | WEAK Qwen labels: >=4 toxic, <=2 non-toxic, 3 excluded | matches `AUDIT:477`, `GUIDE:173` | MATCH |
| ur | `Adnan855570/Urdu_Hate_Speech` | MIT | expert hate-speech labels -> binary | matches `AUDIT:478`, `GUIDE:174` | MATCH |

**Doc typo (confirmed):** `DATASET_GUIDE.md:172` spells the ta-Latn source
`community-datasets/offenseval_dravilian` ("dravilian"). The manifest and
`prepare_phase2_eval.py:378` both use `offenseval_dravidian`. Cosmetic, but a
provenance-table mismatch that should read `offenseval_dravidian`.

Label mapping code agrees with the notes: `prepare_phase2_eval.py:186`
(`1 if lab in (1,2,3,4) else 0`, label 5 excluded at :184), :204-209 (bn
score>=4 / <=2 / 3 excluded), :255 (ur `label>=1 -> 1`).

---

## 6. Statistical meaningfulness & 95% CIs

No per-row predictions are stored anywhere (the JSONs keep only confusion
matrices + threshold sweeps), so an exact F1 bootstrap over stored predictions is
**not computable without re-scoring**. Below I use (a) a closed-form **Wilson 95%
CI for FPR** (binomial, n = number of negatives) and (b) a **parametric
multinomial bootstrap** for F1 that resamples only the 2x2 confusion cells
(no model, counts taken straight from `phase3_benchmark.json`). Bootstrap =
20,000 resamples, seed 12345, percentile 2.5/97.5.

| Group | n (neg) | F1 (95% boot CI) | FPR (95% Wilson CI) | Meaningful? |
|---|---|---|---|---|
| en | 180 (90) | 0.948 [0.910, 0.979] | 0.011 [0.002, 0.060] | **Yes** — tight; clearly better than legacy (0.540) |
| hi | 180 (90) | 0.638 [0.538, 0.726] | 0.044 [0.017, 0.109] | **Yes** — CI excludes legacy (0.065) |
| ur | 180 (90) | 0.588 [0.493, 0.674] | 0.256 [0.177, 0.354] | F1 meaningful vs legacy 0.0; **FPR CI [0.18,0.35] lies entirely above the 0.15 cap** — the breach is real, not noise |
| bn | 143 (90) | 0.722 [0.617, 0.811] | 0.178 [0.113, 0.269] | F1 CI wide (weak labels); **FPR CI straddles 0.15** — breach is *suggestive, not conclusive* at n=90 negatives |
| ta | 180 (90) | 0.529 [0.422, 0.624] | 0.144 [0.086, 0.232] | F1 meaningful vs legacy (0.021); FPR CI straddles cap |
| ta-Latn | 180 (90) | 0.313 [0.200, 0.419] | 0.078 [0.038, 0.152] | F1 CI wide and low; the +0.068 "fix" gain (0.245->0.313) is **inside overlapping CIs — not statistically firm** |

Explicit statements:

- **Statistically meaningful at these sizes:** en and hi (tight CIs, clear
  separation from legacy); the ur FPR-cap breach (CI entirely above 0.15); the
  broad "model >> legacy" direction for ta/ur/bn.
- **NOT statistically firm:** (1) the ta-Latn 0.245->0.313 improvement — the two
  F1 CIs overlap heavily, so the "root-cause fix" gain is directionally positive
  but not significant at n=180; (2) the bn F1-vs-FPR trade — bn FPR CI
  [0.113,0.269] straddles the 0.15 budget, so "bn breaches the cap" is not
  conclusive; (3) any per-language FPR at 0.000 (e.g. legacy hi/bn/ur) — with
  0/90 the Wilson upper bound is still ~0.040, so "0 FPR" should be read as
  "< ~4%", not "0".

These CIs are computed only from stored counts; none are invented.

---

## 7. Task incompatibility — **DOCS HANDLE IT CORRECTLY (not combined into one score)**

The reports explicitly refuse to merge the incompatible tasks into a single
headline number. `PHASE2_MODEL_EVALUATION.md:279-293` ("Why ur and bn remain
weak (task mismatch)") and `PROJECT_AUDIT_REPORT.md:469-486` (§16.4) state that
`ur` = hate-speech, `ta`/`ta-Latn` = offensiveness, `bn` = weak Qwen
annotations, and that this is "not fixable by threshold tuning alone."
`DATASET_GUIDE.md:181-186` repeats it. Per-language results are always reported
separately; there is no pooled cross-task score presented as a single quality
number. **No misleading combination found — nothing to flag.**

(If a single summary sentence is ever needed, suggested wording:
*"These six per-language figures come from four different labelling tasks
(generic toxicity, offensiveness, hate speech, and weak model annotations) and
must not be averaged into one 'toxicity accuracy'; compare each language only
against its own baseline and label basis."*)

---

## 8. Environment-dependent timing — **CLEARLY LABELED**

- `PHASE2_MODEL_EVALUATION.md:259-261`: latency "batch 8 on a loaded CPU…
  treat both as CPU-only, load-dependent numbers, not serviceable latencies."
- `PROJECT_AUDIT_REPORT.md:463-464`: "latency this run (batch 8, loaded CPU)
  147-952 ms/text vs Phase 2's 40-290 ms at batch 16."
- Memory is reported as measured working-set (18.0 -> 1138.3 MB), tied to the
  CPU-only torch build.

**Confirmed environment-dependence is disclosed. No defect.**

---

## 9. Test-set usage labeling — **ACCEPTABLE, one recommendation**

`benchmark_phase3.py` does **not** print a per-language `test_optimal_threshold`
to stdout (the per-language print at lines 194-200 omits it); it is only stored
in `threshold_drift` in the JSON (lines 160-168). The reports cite the ur
test-optimal (0.55, F1 0.394) **diagnostically** — to argue the ranking is weak
and to justify *not* changing the threshold — and `tuned_threshold.json` is
provably unchanged (sha256 verified). So no test-informed selection occurred and
the headline metrics (which use the validation-selected thresholds) remain
unbiased.

**Recommendation (wording, not a code fix):** the two `threshold_drift` fields
`test_optimal_threshold` / `test_f1_at_own_optimum` are computed on the test set;
wherever they are quoted (e.g. `PHASE2_MODEL_EVALUATION.md:286`,
`PROJECT_AUDIT_REPORT.md:460`), add the label *"exploratory diagnostic on the
test split — not an unbiased final estimate, not used for selection."* This does
not change any reported operating-point number.

---

## 10. Confirmed defects (with file:line)

| # | Defect | Location | Impact | Suggested fix |
|---|---|---|---|---|
| D1 | **Stale Phase-2 figures embedded in the Phase 3 artifact.** `MODEL_COVERAGE` strings for `ta-Latn` ("F1 0.245 … FPR 0.033") and `bn` ("F1 0.624 … FPR 0.122") are hard-coded Phase-2-at-0.30 values. They are copied verbatim into `phase3_benchmark.json` `uncertainty_and_coverage.coverage.*.status` and now contradict that same file's `test_model` metrics (ta-Latn 0.313/0.078; bn 0.722/0.178). en/hi/ta/ur strings still match only because their thresholds did not change. | source `model_adapter.py:80-81`; surfaced at `phase3_benchmark.json:1466` (bn) and `:1520` (ta-Latn) | The Phase-3 JSON is internally inconsistent; a reader trusting the coverage note gets the *old* ta-Latn/bn numbers. Reports (P10.3/A16.3) use the correct values. | Regenerate the coverage strings from the Phase-3 results, or annotate them "Phase 2, threshold 0.30". **Engine change — out of Workstream E's write scope; NOT modified here.** |
| D2 | **Doc typo in provenance table:** ta-Latn source misspelled `offenseval_dravilian`. | `DATASET_GUIDE.md:172` | Provenance mismatch vs manifest (`offenseval_dravidian`). | Correct to `offenseval_dravidian`. (Report-only; report sections not overwritten.) |
| D3 | **Stale contradictory "Outstanding" section.** §16.4 (second occurrence) says `benchmark_phase3.py` "has not produced final numbers yet" and describes OOM — directly contradicting §16.3 (same file) which already presents the completed Phase-3 results. Also a duplicate §16.4 heading (lines 469 and 498). | `PROJECT_AUDIT_REPORT.md:498-507` vs `:438-467` | Reader confusion about whether Phase 3 completed. It did (`phase3_benchmark.json` `generated_at` 2026-10-10T10:52Z). | Delete/merge the stale Outstanding paragraph; renumber. |
| D4 | **Mojibake in report body** (em-dash/en-dash/≤/→ rendered as `?`). | `PHASE2_MODEL_EVALUATION.md:196,209,211,213,298` (e.g. "0.30?0.90", "FPR ? 0.15", ".55 ? .ta") | Cosmetic readability loss. | Re-save as UTF-8 or use ASCII equivalents. |

No metric-formula bug (see §3) → no `tests_metrics_phase4.py` was created, per the
deliverable's conditional instruction.

## 11. Rejected suspicions (with reasoning)

| Suspicion | Verdict | Reasoning |
|---|---|---|
| Test set influences threshold selection | **REJECTED** | `benchmark_phase3.py:138-144` selects from `v_sweep` (validation); `tuned_threshold.json.tuned_at` (2026-10-09) predates the Phase-3 run (2026-10-10) and sha256 is unchanged — nothing was written back. |
| A metric formula bug (FPR/macro-F1) | **REJECTED** | All 6 languages' precision/recall/F1/macro-F1/acc/FPR recompute exactly from the stored 2x2 matrices (0 mismatches). |
| Eval splits leak into training data | **REJECTED** | 0 normalised overlaps against the 197 training/demo texts. |
| val/test contamination | **REJECTED** | 0 exact and 0 normalised duplicates within any group; 0 cross-group reuse. |
| Latency/memory presented as fixed | **REJECTED** | Explicitly labeled load/CPU-dependent in both reports. |
| Docs merge hate-speech/offensiveness/toxicity into one score | **REJECTED** | Reports explicitly keep them separate and flag the mismatch as the root cause. |

---

## 12. Exact commands executed & actual outputs

All commands run from the project; `$py` = the project venv Python.

**C1 — sha256 of the read-only threshold file**
```powershell
Get-FileHash -Algorithm SHA256 ".../models/tuned_threshold.json"
# Hash: F31F4975D29A151F3F8737AE18875F6A5D11C2EE8719D126C587F7B339285C54
# prefix f31f4975d29a151f -> MATCHES expected
```

**C2 — isolation + formula recompute + CIs** (`$env:PYTHONIOENCODING='utf-8'; & $py phase4_verify.py`)
Key output (full transcript reproduced from the run):
```
A. SPLIT ISOLATION
en  val=120 test=180 pos=150 neg=150 50.00% | val<->test overlap exact=0 norm=0
ta  ... overlap exact=0 norm=0
ta-Latn ... overlap exact=0 norm=0
hi  ... overlap exact=0 norm=0
bn  val=95 test=143 pos=88 neg=150 36.97% | overlap exact=0 norm=0
ur  ... overlap exact=0 norm=0
total cross-group reused texts: 0
total eval-vs-training overlaps: 0

B. RECOMPUTE METRICS FROM CONFUSION MATRICES
en/ta/ta-Latn/hi/bn/ur -> ALL MATCH (each of P,R,F1,macro,acc,FPR equal stored)
TOTAL metric mismatches from confusion matrices: 0

C. 95% CI
en  FPR=0.0111 Wilson95=[0.0020,0.0603] | F1=0.9480 boot95=[0.9101,0.9787]
ta  FPR=0.1444 Wilson95=[0.0864,0.2316] | F1=0.5286 boot95=[0.4219,0.6242]
ta-Latn FPR=0.0778 Wilson95=[0.0382,0.1519] | F1=0.3130 boot95=[0.2000,0.4186]
hi  FPR=0.0444 Wilson95=[0.0174,0.1088] | F1=0.6377 boot95=[0.5378,0.7260]
bn  FPR=0.1778 Wilson95=[0.1125,0.2694] | F1=0.7222 boot95=[0.6168,0.8108]
ur  FPR=0.2556 Wilson95=[0.1767,0.3544] | F1=0.5875 boot95=[0.4925,0.6742]
```

**C3 — read-only inspection** of `benchmark_phase2.py`, `benchmark_phase3.py`,
`prepare_phase2_eval.py`, `model_adapter.py` (grep coverage map),
`models/phase{2,3}_benchmark.json`, `tuned_threshold.json`, `benchmark_run2.log`,
`data/phase2_eval/manifest.json`, and the four reports. No writes to `models/`.

## 13. Test counts

| Suite | Passed | Failed | Skipped | Not run |
|---|---:|---:|---:|---|
| `tests_dataset_import.py` (coordinator) | — | — | — | **NOT RUN** (out of scope) |
| `tests_model_adapter.py` (coordinator) | — | — | — | **NOT RUN** (out of scope) |
| `tests_word_input.py` (coordinator) | — | — | — | **NOT RUN** (out of scope) |
| `tests_multilingual.py` (coordinator) | — | — | — | **NOT RUN** (out of scope) |
| `tests_frontend_apptest.py` (coordinator) | — | — | — | **NOT RUN** (out of scope) |
| Workstream E verification script (new, CPU-only, no model) | all checks pass (isolation 0/0/0; formula mismatches 0) | 0 | 0 | — |

Workstream E created **no** `tests_metrics_phase4.py` because no metric formula
bug exists to reproduce (see §3).

---

## 14. Bottom line

- **Cross-check:** every numeric value printed in `PHASE2_MODEL_EVALUATION.md` §10.3
  and `PROJECT_AUDIT_REPORT.md` §16.3 matches `models/phase3_benchmark.json` —
  **~124 values checked, 0 mismatches**. Phase-2 §15.2 also matches
  `phase2_benchmark.json`.
- **Reproducibility:** PASS — fixed, seeded, provenance-tracked eval splits with
  intact val/test isolation and zero leakage into training data.
- **Threshold discipline:** PASS — validation-only selection; test read once for
  reporting; `tuned_threshold.json` untouched (sha256 verified).
- **Metric formulas:** PASS — no bug; independently re-derived.
- **Confirmed defects:** D1 stale Phase-2 ta-Latn/bn figures embedded in the
  Phase-3 JSON (from `model_adapter.py:80-81`); D2 `dravilian` typo
  (`DATASET_GUIDE.md:172`); D3 stale contradictory "Outstanding" §16.4
  (`PROJECT_AUDIT_REPORT.md:498-507`); D4 mojibake in the Phase-2 report body.
- **Unverifiable without re-scoring:** exact per-row bootstrap F1 CIs (no stored
  predictions) — approximate CIs here come from the confusion-matrix counts and
  are labeled as such.
- **Not statistically firm:** the ta-Latn 0.245->0.313 gain and the bn FPR-cap
  breach (both CIs overlap the comparison at these n).
