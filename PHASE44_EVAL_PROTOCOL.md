# AURA Phase 4.4 — Sample-Size Plan & Leakage-Safe Evaluation Protocol

Companion to `PHASE44_ANNOTATION_SPEC.md`. All numbers below were **computed in
this environment** (Wilson score intervals and a pooled two-proportion power
calculation, α = 0.05 two-sided, power = 80 %), not asserted.

---

## 1. Correction to the Phase 4.3 sample-size claim

Phase 4.3 stated that `n_neg = 90` is "inadequate". Re-computation shows that
was **imprecise**, and the correction matters for planning:

| | Verdict at n_neg = 90 |
|---|---|
| **Detecting a FAIL** (true FPR ≈ 0.25) | **Adequate.** CI `[0.177, 0.354]` lies **entirely above** the 0.15 cap → failure is already statistically established. |
| **Confirming a PASS** (true FPR ≈ 0.10) | **Inadequate.** CI `[0.054, 0.179]` **straddles** 0.15 → a genuinely passing model *could not* be proven to pass. |

So the current corpus can already **condemn** the baseline, but could never
**acquit** a good candidate. The sample-size requirement is therefore driven by
the **pass-confirmation** side.

## 2. Where the requirement actually applies

**The count that matters is negatives in the *frozen test split*, per script
stratum** — not the whole corpus, and not a pooled Urdu total.

Verified minimum test-negative counts (Wilson 95 %):

| Test negatives | True FPR 0.10 → CI | True FPR 0.25 → CI | Outcome |
|---|---|---|---|
| 200 | [0.066, **0.149**] | [**0.195**, 0.314] | confirms PASS **and** FAIL |
| **250** | [0.069, **0.143**] | [**0.199**, 0.305] | confirms PASS **and** FAIL |
| 300 | [0.071, **0.139**] | [**0.204**, 0.302] | confirms PASS **and** FAIL |

**Minimum: 200 test negatives per stratum. Recommended: 250** (also satisfies the
80 % power requirement for 0.25 vs 0.15, which needs **n = 250 per group**).

## 3. Corpus sizing derived from it

| Parameter | Value |
|---|---|
| Required **test** negatives per stratum | **250** |
| Test split fraction | **40 %** |
| → corpus negatives per stratum | `250 / 0.4 =` **625** |
| → items per stratum at 1:1 balance | **1,250** |
| **Total corpus (ur-Arab + ur-Latn)** | **≈ 2,500 items** |

A cheaper 50 % test split yields ≈ 2,000 items, at the cost of less training
material. 40/20/40 is recommended.

Power reference (80 %, α = 0.05): 0.30 vs 0.15 → **121**/group;
0.25 vs 0.15 → **250**/group; 0.20 vs 0.15 → **906**/group. Tightening the
observed FPR toward the cap is disproportionately expensive — a further argument
for measuring rather than threshold-tuning.

---

## 4. Leakage-safe evaluation protocol

### 4.1 Deduplication — before any split exists

1. **Exact:** NFKC-normalise → lowercase → strip punctuation → collapse
   whitespace → exact-match dedupe.
2. **Fuzzy:** char-trigram **Jaccard ≥ 0.80** → candidate near-duplicate →
   human review. *(Same method and threshold that found 0 near-duplicates in the
   existing corpus, keeping the two corpora comparable.)*
3. **Transliteration families:** Roman Urdu variants of one utterance collapse
   into a single `group_id`.

### 4.2 Group-aware splitting

- **Group key `group_id`** = normalized-text family (near-duplicates,
  transliteration variants, same-thread utterances).
- **Invariant, asserted programmatically:** every member of a `group_id` lands
  in **exactly one** split. The split routine must **fail loudly** if any group
  is observed in two splits.
- **Stratification:** every category and **both script strata** appear in every
  split, preserving the 1:1 class balance.
- **Ratio:** 40 % train / 20 % validation / **40 % frozen test**.

### 4.3 Freeze-before-tuning

1. Emit a **hash manifest** over the test split (file SHA256 + per-stratum
   counts) *before* any candidate is scored.
2. **All** candidate selection and threshold selection uses **validation only**.
3. The frozen test set is scored **exactly once** per candidate.
4. The frozen manifest is committed to the benchmark record alongside the result.

Existing splits stay frozen and untouched:

```
ur_test.csv  f18d80f3e12e07a6f185079f7af0a2adf82ab35b3518c34145a9725f0538e9c5   74,991 B
ur_val.csv   8727f2bacf41619173066466b8c992bc9cb0596e8e33c165d0f979072c61c13a   51,366 B
```

### 4.4 Leakage assertions (must all pass before any metric is reported)

| # | Assertion |
|---|---|
| L1 | 0 exact-duplicate texts **within** any split |
| L2 | 0 shared normalized texts **between** any two splits |
| L3 | 0 fuzzy near-duplicate pairs (Jaccard ≥ 0.80) **across** split boundaries |
| L4 | 0 `group_id` spanning more than one split |
| L5 | 0 overlap with `dataset_samples` production text (all 596 rows) |
| L6 | 0 contradictory `final_label` for an identical normalized text |
| L7 | Test-split hashes match the frozen manifest |

### 4.5 Metric reporting (per script stratum — never pooled)

Report for `ur-Arab` and `ur-Latn` **separately**: sample counts and class
distribution; confusion matrix `[[TN,FP],[FN,TP]]`; **FPR with Wilson 95 % CI**;
precision, recall, F1, ROC-AUC where valid; runtime and peak resources.

**Gate rule:** the gate passes only if **each** script stratum independently
demonstrates **FPR ≤ 0.15 with its CI entirely at or below the cap**, on the
frozen test set, under the documented protocol.

### 4.6 Integrity guardrails

- Production engine remains **`legacy`**; protected hashes
  `f31f4975…` / `5a9d94e2…` / `f3a5ceb4…` unchanged.
- Candidate evaluation runs **isolated** — no production import, no backend
  start, no engine switch, no retrain, no deploy.
- Existing 596-row database, its splits, the 8 `training_runs` and
  `improved_v10` untouched.
- Existing frozen Urdu splits never rewritten.
- No threshold is tuned on test; the 0.15 cap is never relaxed.

---

## 5. Status

| Item | State |
|---|---|
| Annotation specification | **COMPLETE** |
| Licensing/provenance checklist | **COMPLETE** |
| Sample-size plan | **COMPLETE** (computed, verified) |
| Leakage-safe evaluation protocol | **COMPLETE** |
| Human-labelled Urdu toxicity data | **NOT AVAILABLE — BLOCKED** |
| Quality gate | **`NOT PASSED`** |

No dataset was fabricated, no label was invented, no metric was computed on data
that does not exist, and no production artifact was modified.
