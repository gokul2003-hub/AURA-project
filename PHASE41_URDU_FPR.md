# PHASE 41 — Urdu (ur) FALSE POSITIVE RATE investigation

Status: **NOT PASSED** (cap breach is real; no safe fix inside this workstream's write scope)
Investigation only — no benchmark, threshold, label or model artifact was modified.

---

## 1. Documented acceptance cap (found, not invented)

| # | Cap | Exact source |
|---|-----|--------------|
| 1 | **0.15** (validation FPR cap, selection rule) | `PHASE2_MODEL_EVALUATION.md:51-52` — "**Selection rule:** maximize toxic F1 subject to validation FPR ≤ 0.15 (`AURA_TUNE_FPR_CAP`); tie-break → higher threshold." |
| 2 | **0.15** (applied to test as the acceptance gate) | `PHASE2_MODEL_EVALUATION.md:262` — "**FPR cap on test: NOT met for bn (0.178) and ur (0.256)** against the 0.15" |
| 3 | **0.15** (machine-readable) | `CODE\BACKEND\models\phase3_benchmark.json:10` — `"fpr_cap": 0.15`; also `selection_rule` at line 11 |
| 4 | **0.15** (verified independently) | `PHASE4_WORKSTREAM_E.md:49` — "FPR cap \| 0.15 (env-overridable `AURA_TUNE_FPR_CAP`) \| `benchmark_phase2.py:155-160`"; and `:140` "FPR cap = 0.15 … `model.fpr_cap` 0.15 \| MATCH" |
| 5 | **0.15** (deployed rule string) | `CODE\BACKEND\models\tuned_threshold.json:107` — `"ur": "max toxic F1 with val FPR <= 0.15"` |

All five agree: **the cap is 0.15**. No competing cap found.

## 2. Reproduction from stored artifacts (arithmetic shown)

Source: `CODE\BACKEND\models\phase3_benchmark.json`, group `ur`, `test_model` (threshold_used = **0.40**, from `tuned_threshold.json:9,99` — ur per_language threshold = 0.4, unchanged).

Confusion matrix (labels `["non_toxic","toxic"]`, `matrix = [[67,23],[43,47]]`):

```
            pred non_toxic   pred toxic
true non_toxic     TN=67        FP=23     -> negatives = 67+23 = 90
true toxic         FN=43        TP=47     -> positives = 43+47 = 90

FPR = FP / (FP + TN) = 23 / (23 + 67) = 23 / 90 = 0.255555... = 0.2556 -> reported 0.256
Precision = TP/(TP+FP)   = 47/70 = 0.671428 -> 0.671
Recall    = TP/(TP+FN)   = 47/90 = 0.522222 -> 0.522
F1        = 2TP/(2TP+FP+FN) = 94/(94+23+43) = 94/160 = 0.5875 -> 0.588
Accuracy  = (67+47)/180  = 114/180 = 0.633333 -> 0.633
```

Recomputed values match every stored metric exactly → **reproduced FPR = 0.2556 ≈ 0.256**.

Cross-checks:
- `phase2_benchmark.json` group `ur` → identical `[[67,23],[43,47]]`, `fpr 0.2556`, `threshold_used 0.4` → the breach predates Phase 3; it is not a regression introduced by the Phase-3 sweep fix.
- `PHASE4_WORKSTREAM_E.md:112` — "ur … 0.256 / 0.2556 … MATCH"; `:144` "ur FPR 0.256 … `groups.ur.test_model.fpr` 0.2556 \| MATCH".
- Stored `roc_auc 0.7044`, `pr_auc 0.6967`, `macro_f1 0.6288`.
- Val side: `validation.fpr = 0.1333` (60 negatives, ≤ 0.15 cap) → threshold 0.40 was legitimately selected on validation; the breach is **val→test drift**, not a rule violation. `threshold_drift` block: `test_optimal_threshold 0.55`, `test_fpr_at_val_threshold 0.2556`, `test_f1_at_val_threshold 0.5875` vs `test_f1_at_own_optimum 0.3937`.

### Sample size + CI (reused from Workstream E — NOT re-invented)
- **n = 180 test rows (90 positive / 90 negative)** — `phase3_benchmark.json` ur `test_model`; `PHASE4_WORKSTREAM_E.md:202` "ur | 180 (90)".
- **Wilson 95% CI for ur FPR = [0.1767, 0.3544]** — `PHASE4_WORKSTREAM_E.md:335` ("ur FPR=0.2556 Wilson95=[0.1767,0.3544]"); same value at `:202` as "[0.177, 0.354]".
- Interpretation per E (`:202`) and `PHASE2_MODEL_EVALUATION.md:278,285`: **the CI lies entirely above the 0.15 cap — the breach is real, not sampling noise.**

## 3. Diagnosis — why ur FPR is high

Evidence inspected (read-only, no model weights loaded):

1. **Label provenance / task mismatch (primary root cause).**
   `data\phase2_eval\manifest.json` → group `ur`: source `Adnan855570/Urdu_Hate_Speech` (MIT), `label_notes`: *"expert-generated hate-speech labels mapped to binary; unmappable values excluded"*, fetched 26,174 rows → balanced to 150/150. The labels are **expert hate-speech** annotations, but the scorer is a **generic toxicity model** (`Horizon-Labs/multilingual-toxicity-small`). Documented at `PHASE2_MODEL_EVALUATION.md:310-314` ("`ur` is an **expert hate-speech** dataset scored by a toxicity model") and `:317-320`.

2. **The ranking itself is weak for this label definition, so no threshold fixes it.**
   ur ROC-AUC = **0.704** — lowest of the Indic set (`PHASE2_MODEL_EVALUATION.md:217-220`). At the test-optimal threshold 0.55 the FPR drops but F1 collapses to **0.3937 < 0.5875** at 0.40 (`threshold_drift` block; `PHASE2_MODEL_EVALUATION.md:317-320`). So FPR 0.256 is not a mis-tuned operating point; it is score overlap between "non-hate" and "toxic" for this model.

3. **What the negative class actually contains (sampled from `ur_test.csv`, escaped):**
   - `NEG_EX '\u0645\u0631\u06cc\u062f\u06a9\u06d2 \u0633\u06d2 \u0644\u0628\u06cc\u06a9 \u0648\u0627\u0644\u0648\u06ba ...'` (Labbaik long-march political rally)
   - `NEG_EX '\u06cc\u0648\u062a\u06be\u06cc\u0648\u06ba \u06a9\u06cc \u0628\u0647\u0646 \u06a9\u06d2 \u0644\u0626\u06d2 ...'` (anti-YouTube-ban protest)
   - `NEG_EX '\u0644\u06cc\u062f\u0631 \u0633\u06d2 \u0688\u0627\u06a9\u062a\u0631 \u0631\u0635\u0648\u0627\u0646 \u0634\u0647\u06cc\u062f \u06a9\u06d2 \u0641\u06cc\u0645\u0644\u06cc \u06a9\u06cc \u0645\u0644\u0627\u0642\u0627\u062a'` (film-ban demands)
   - `NEG_EX '\u062f\u0648\u0633\u0631\u0648\u06ba \u06a9\u0648 \u0646\u0635\u06cc\u062d\u062a \u0641\u0631\u0645\u0627\u0646\u06d2 \u0648\u0627\u0644\u06d2 ...'` (religious-criticism status)
   These are **politically/religiously charged but expert-labelled non-hate** sentences — exactly the content a generic toxicity model over-scores. (The 23 exact FP rows cannot be listed: per-row scores are not stored in either benchmark JSON, and loading the 16 GB model to regenerate them is forbidden in this session.)

4. **Routing / preprocessing / lexicon are NOT the cause (ruled out):**
   - `mlexicon.detect()` on all 180 ur test rows → `{'code':'ur'}` for **180/180**; no mis-routing, no `und`.
   - Script check: **0/90** negatives are Latin-only and **0/90** mixed Latin+Arabic → **no romanised-Urdu rows** in the ur split; script normalization is not a factor here.
   - Legacy lexicon path on the 90 negatives: **0 rows with any ur lexicon score > 0** (`lexicon_available('ur') = True`, but zero term matches) → legacy `[[90,0],[90,0]]`, FPR 0.000, F1 0.000 (`test_legacy`). So **every one of the 23 FPs is produced by the transformer score path**, not by the rule/lexicon engine and not by a threshold string bug.
   - `tuned_threshold.json:9,99` ur = **0.40**, matching `threshold_used` 0.40 in both benchmark JSONs → deployed value is the validated value; no drift/mismatch.

5. **Sample size:** 90 negatives → 23 FPs is far beyond binomial noise around 0.15 (Wilson CI above), so this is not a small-n artifact (unlike bn, whose CI straddles the cap).

## 4. Decision — is a safe fix available?

**No safe fix exists within this workstream's write scope.** Options examined and rejected:

| Option | Why rejected |
|---|---|
| Move ur threshold 0.40 → 0.55 | **Prohibited without explicit approval** (and would *lose* F1: 0.588 → 0.394 while only partially cutting FPR; `PHASE2_MODEL_EVALUATION.md:317-320`). Proposed in §5 for the integration lead, NOT applied. |
| Tune anything on the test set | Prohibited (would be test-set tuning to make the number pass). |
| Change ur test labels / re-balance | Prohibited (held-out labels). |
| Patch `mlexicon.py` / `backend.py` to add Urdu FP-suppressing rules | (a) files not owned here; (b) lexicon fires 0/90 on negatives, so there is no lexicon-driven FP to suppress — such a patch would have to be built on test examples → leak risk. |
| Drop ur from the safety gate / relabel as out-of-scope | Policy decision requiring explicit sign-off; cannot be done in a report file. |
| Retrain / deploy | Prohibited. |

Bengali (bn) remains **INCONCLUSIVE** as documented (`PHASE4_WORKSTREAM_E.md:203` — CI straddles 0.15); untouched here. The ta-Latn F1 gain remains **not statistically firm** (`PHASE4_WORKSTREAM_E.md:377`, `PHASE2_MODEL_EVALUATION.md:275,281`); not claimed significant here.

## 5. Status

# NOT PASSED

ur test FPR = **0.256** vs documented cap **0.15**; Wilson 95% CI **[0.177, 0.354]** lies entirely above the cap → genuine breach, reproducible from `phase3_benchmark.json` and identical in `phase2_benchmark.json`. Benchmark artifacts left untouched.

**Smallest next action (blocked pending integration lead):** a one-line policy decision on ur — either
(a) accept `ur` as *out-of-scope for the 0.15 FPR gate* (task mismatch: expert hate-speech labels vs generic toxicity model, AUC 0.704 — documented at `PHASE2_MODEL_EVALUATION.md:310-320`) and record the exception explicitly in the gate definition, **or**
(b) approve raising the ur threshold 0.40 → 0.55 (test FPR falls, F1 falls 0.588 → 0.394; must be approved *before* any run, never selected on test), **or**
(c) commission an ur-specific labelled toxicity set so threshold selection uses in-task data.
No file outside `PHASE41_URDU_FPR.md` was created or edited.
