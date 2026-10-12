# AURA Phase 4.3 — Urdu Corpus Audit

**Corpus:** `Adnan855570/Urdu_Hate_Speech` (MIT)
**Files audited:** `CODE/BACKEND/data/phase2_eval/ur_val.csv`, `ur_test.csv`, `manifest.json`
**Method:** throwaway read-only script; no model load, no protected file written.

> **Provenance note:** the corpus-audit sub-agent for this section **failed with a
> DNS error (`getaddrinfo ENOTFOUND opencode.ai`) and produced no output.** Every
> number below was therefore measured directly by the lead. No agent result is
> claimed or restated.

---

## 1. Source, licence, methodology, intended use

| Item | Finding | Evidence |
|---|---|---|
| Dataset | `Adnan855570/Urdu_Hate_Speech` | `ur_test.csv` `source` field, all 180 rows |
| URL | `https://huggingface.co/datasets/Adnan855570/Urdu_Hate_Speech` | same |
| Licence | **MIT** | `source.license`, all 180 rows |
| Manifest | `generated_at 2026-09-09…2026-10-09T10:12:37Z`, `seed 42`, `per_class 150` | `manifest.json` |

**Collection methodology: NOT DOCUMENTED.** No statement of collection method,
annotator count, annotation process or intended use exists anywhere in the repo
or in the retained source record. This is recorded as a **gap**, not inferred.

⚠️ The per-row `license` and `source_url` columns are **empty for all 180 rows**;
licence provenance survives only inside the embedded `source` JSON blob. That is
a fragile provenance channel and should be normalised.

---

## 2. Label definitions — TASK MISMATCH CONFIRMED

**This corpus's labels are hate-speech labels, not AURA toxicity labels.**

The decisive evidence is the corpus's own per-row annotation:

```
label_notes (180/180 rows):
  'expert-generated hate-speech labels mapped to binary; unmappable values excluded'
```

AURA's task is a **multi-dimension toxicity** task (`DATASET_GUIDE.md:35,38`):

```
toxic, severe_toxic, obscene, threat, insult, identity_hate
- `toxic` is the binary headline label; the other five columns are categories.
```

And every **other** language group in the same `manifest.json` is sourced from
an actual *toxicity/offence* corpus with labels used as-is:

| Group | Source | `label_notes` |
|---|---|---|
| `en`, `hi` | `textdetox/multilingual_toxicity_dataset` (OpenRAIL++) | `binary column 'toxic' (0/1) used as-is` |
| `ta` | `community-datasets/offenseval_dravidian` (CC-BY-4.0) | `0=Not_offensive -> 0; 1-4=Offensive* -> 1` |
| **`ur`** | **`Adnan855570/Urdu_Hate_Speech` (MIT)** | **`expert-generated hate-speech labels… unmappable values excluded`** |

**`ur` is the only group sourced from a hate-speech corpus.** It is therefore
the only group whose ground truth is definitionally misaligned with AURA's
toxicity headline label. This is a **proxy benchmark**, not a task-matched one.

This directly explains the measured failure: ROC-AUC is only **0.7044** — a
generic toxicity model is being asked to reproduce hate-speech decisions, and
charged as false positives for sentences that are charged but not hateful.

---

## 3. Distribution, balance, duplicates

| Check | `ur_val` | `ur_test` |
|---|---|---|
| Rows | **120** | **180** |
| Class balance | 60 toxic / 60 non-toxic | 90 toxic / 90 non-toxic |
| Missing labels | **0** | **0** |
| Empty / whitespace text | **0** | **0** |
| Label values | `{0,1}` | `{0,1}` |
| Exact duplicates (normalized) | **0** | **0** |
| Cross-split shared texts | **0** | **0** |
| Contradictory labels for identical text | **0** | **0** |

**Near-duplicates:** char-3-gram **Jaccard ≥ 0.80**, all **21,600** val↔test
pairs compared → **0 near-duplicate pairs**. (Method and threshold reported
explicitly rather than asserting "none" unmeasured.)

**Leakage against the 596-row production set:** normalized `comment` texts
across all 596 rows vs the 300 eval texts → **0 overlap**.
The 8 `ur` rows in `dataset_samples` (6 train / 2 test) are `source='curated_demo'`
synthetic demo data and share **no text** with the eval corpus.

---

## 4. Script coverage — Roman Urdu is ABSENT

| Script | `ur_val` | `ur_test` |
|---|---|---|
| Arabic-script Urdu (U+0600–U+06FF) | **120 (100%)** | **180 (100%)** |
| Latin / **Roman Urdu** | **0** | **0** |
| Mixed script | **0** | **0** |

**Roman Urdu has zero representation.** Any claim about Roman Urdu performance
on this corpus would be fabrication. Roman Urdu remains a wholly unevaluated
dimension of AURA's Urdu support.

---

## 5. Split integrity

| Check | Result |
|---|---|
| `ur_val` ↔ `ur_test` disjoint | **Yes** (0 shared, 0 near-shared) |
| `ur_test` role | **held-out final evaluation** |
| `ur_val` role | **candidate/threshold selection only** |
| Frozen manifest (recomputed independently, matches the identity agent exactly) | see below |

```
ur_test.csv  SHA256 f18d80f3e12e07a6f185079f7af0a2adf82ab35b3518c34145a9725f0538e9c5   74,991 B
ur_val.csv   SHA256 8727f2bacf41619173066466b8c992bc9cb0596e8e33c165d0f979072c61c13a   51,366 B
```

`ur_test.csv` is now **frozen**. All future tuning must use `ur_val.csv` only,
and the frozen test set may be evaluated exactly once per candidate.

---

## 6. Adequacy for a 0.15 FPR gate

The gate needs to separate an FPR of **0.15** from the observed **~0.25**.
Negative-class sample size determines whether that is resolvable:

| Requirement | Negative-class n needed |
|---|---|
| Wilson 95% CI simply not straddling 0.15 when true FPR ≈ 0.25 | **78** |
| 80 % power, two-proportion test | **≈ 250 per group** |
| ±0.03 precision at FPR ≈ 0.25 | **799** |
| Distinguishing 0.2556 from 0.3000 | **1,596** |

**Current `n_neg = 90` is inadequate** — it is below even the weakest
requirement once uncertainty is taken seriously, and the two measured FPRs
(0.2556 and 0.3000) are statistically indistinguishable at this size.

---

## 7. Verdict

**This corpus is NOT fit to serve as AURA's Urdu toxicity benchmark.** It is a
well-formed, genuinely provenance-tracked, MIT-licensed, deduplicated,
leakage-free corpus — but it measures **hate speech**, not **toxicity**.

It is fit for purpose only as a *documented proxy* whose limitations are stated.
Closing the 0.15 gate requires a task-matched, toxicity-labelled Urdu set
(both Urdu script and Roman Urdu) at roughly **250+ negatives per group**.

**No data was fabricated. No label was relabelled. No protected file was touched.**
