# AURA Phase 4.7 — RUHSOLD Label Mapping to AURA Toxicity Taxonomy

**Status: PROPOSAL — NOT APPROVED. No labels have been remapped, imported or
applied. No performance metric is reported this phase.**

---

## 1. AURA's actual taxonomy (target)

From `DATASET_GUIDE.md:35,38`:

```
toxic, severe_toxic, obscene, threat, insult, identity_hate
- `toxic` is the binary headline label; the other five columns are categories.
```

Production emits the **binary headline `toxic`** plus five secondary categories.
The `pretrained` head additionally exposes
`toxicity, severe_toxicity, obscene, threat, insult, identity_attack, sexual_explicit`
(`PHASE2_MODEL_EVALUATION.md:17`).

**RUHSOLD supplies only a single label column.** Only the **binary headline**
can be mapped with integrity. The five AURA categories **cannot be recovered**
from RUHSOLD's single label — any such assignment would be fabricated.

## 2. RUHSOLD's taxonomy (source)

| Config | Classes |
|---|---|
| `Coarse_Grained` | `0: Abusive/Offensive`, `1: Normal` |
| `Fine_Grained` | `0: Abusive/Offensive`, `1: Normal`, `2: Religious Hate`, `3: Sexism`, `4: Profane/Untargeted` |

Annotation provenance: **three independent expert annotators, majority vote**
(README *Data Fields*) — verified in `PHASE46_RUHSOLD_LABEL_AUDIT.md §1`.

---

## 3. Proposed mapping

| RUHSOLD class | → AURA `toxic` | Secondary category | Confidence | Rationale |
|---|---|---|---|---|
| `1: Normal` | **0** (`non_toxic`) | — | **High** | "Normal / inoffensive" aligns with AURA's non-toxic definition |
| `0: Abusive/Offensive` | **1** (`toxic`) | *none assignable* | **Medium-High** | "Abusive/offensive" ≈ AURA's "rude, disrespectful or unreasonable". Wording is close but not identical |
| `2: Religious Hate` | **1** (`toxic`) | **`identity_hate`** | **High** | Attack on a group by religious identity — squarely AURA `identity_hate` |
| `3: Sexism` | **1** (`toxic`) | **`identity_hate`** | **High** | Attack by gender — squarely AURA `identity_hate` |
| **`4: Profane/Untargeted`** | **EXCLUDED** | — | **Unresolved** | See §4 |

### 3.1 What CANNOT be mapped

RUHSOLD's single label **cannot** yield `severe_toxic`, `obscene`, `threat` or
`insult`. Only `identity_hate` is recoverable, and only for classes 2 and 3.

**Consequence:** any evaluation on RUHSOLD is valid **only for the binary
headline `toxic`**. Category-level metrics must not be reported from this source.

---

## 4. `Profane/Untargeted` — EXCLUDED by default

Per this phase's instruction and `PHASE46_RUHSOLD_LABEL_AUDIT.md §7`:

**AURA's definition** — *"rude, disrespectful or unreasonable in a way likely to
make a person leave the conversation"* — **does not require a target.** Untargeted
profanity therefore straddles the boundary:

| Case | Would map to |
|---|---|
| *"what a f***ing mess"* — ambient venting | plausibly `non_toxic` |
| sustained heavy profanity, exclusionary tone, no named target | plausibly `toxic` |

**A blanket rule in either direction introduces semantic distortion.** Per
instruction, this class is **excluded by default unless reviewed and reliably
adjudicated**.

### Exclusion policy (proposed)

1. Class `4` rows are **removed from the labelled evaluation pool** — they are
   neither counted as toxic nor as non-toxic.
2. **They are NOT counted as verified negatives.** This is explicit: an excluded
   item is *unknown*, not *negative*. Treating exclusions as negatives would
   artificially deflate the measured FPR and could manufacture a gate pass.
3. Excluded rows are retained separately with `mapping_status = excluded_pending_adjudication`,
   preserving the ability to re-adjudicate later without re-acquiring data.
4. If adjudication is approved, **3 annotators apply AURA's definition verbatim**,
   with `mapping_confidence`; items below the confidence threshold **stay excluded**.
5. The exclusion/adjudication decision is **frozen before any scoring** and
   reported alongside results.

### Quantified impact (to be filled after V10)

| Class | Rows | Share |
|---|---|---|
| 0,1,2,3 | *pending V10* | *pending* |
| **4 (excluded)** | **pending V10** | **pending** |

Excluding class 4 **shrinks the usable pool and changes the class balance**.
The sample-size projection in `PHASE47_SPLIT_VERIFICATION_PLAN.md §4` must be
recomputed after V10 — the 250-negative target may no longer be met.

---

## 5. Label uncertainty register

| Source of uncertainty | Handling |
|---|---|
| `Abusive/Offensive` vs AURA `toxicity` — not identical constructs | Documented; medium-high confidence; **requires approval** |
| `Profane/Untargeted` ambiguity | **Excluded** by default (§4) |
| Card-internal inconsistencies (totals 10,010 vs 10,013 vs "10000") | Row authority deferred to parquet (V1) |
| Possible cross-split duplicates/overlap | Unresolved until V5–V7 |
| `Fine_Grained/validation` == `train` | That split unusable; excluded from any pool |
| Single-label schema | Secondary AURA categories **unrecoverable** — not fabricated |

---

## 6. Exclusions summary — nothing counted as verified

| Excluded from evaluation pool | Reason |
|---|---|
| All `4: Profane/Untargeted` | ambiguity; not adjudicated |
| All `Fine_Grained/validation` rows | duplicate of `train` |
| Any row implicated in cross-split overlap (pending V5–V7) | leakage |
| Any row with unresolved PII (pending `PHASE47_PRIVACY_PLAN.md`) | privacy |

**None of the above is counted as a verified negative.**

## 7. Approvals required

| # | Decision | Status |
|---|---|---|
| M1 | Approve `Normal → non_toxic`, `Abusive/Offensive → toxic` | **PENDING** |
| M2 | Approve `Religious Hate`/`Sexism` → `toxic` + `identity_hate` | **PENDING** |
| M3 | Confirm **exclusion** of `Profane/Untargeted` (recommended), *or* approve adjudication | **PENDING** |
| M4 | Accept that only the **binary headline** is evaluable from RUHSOLD | **PENDING** |

**No label was fabricated. No excluded item is counted as a verified negative.
No performance metric is reported.**
