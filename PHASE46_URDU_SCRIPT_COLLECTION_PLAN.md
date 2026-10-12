# AURA Phase 4.6 — Urdu-Script (`ur-Arab`) Human-Annotation Collection Plan

**Status: PLAN COMPLETE — NO DATA EXISTS.** No Urdu-script toxicity corpus was
located (`PHASE45_ACQUISITION_READINESS.md §2`: every candidate was Roman Urdu or
hate-speech labelled). **This stratum must be commissioned.** Nothing below is
claimed to exist.

Builds on `PHASE44_ANNOTATION_SPEC.md` and `PHASE44_EVAL_PROTOCOL.md`.

---

## 1. Why commissioning is unavoidable

| Search result | Outcome |
|---|---|
| Urdu-script toxicity corpus on HF | **none found** across 7 queries / 75 datasets |
| Urdu-script corpus found | `Adnan855570/Urdu_Hate_Speech` — **hate-speech labels, task-mismatched** (`PHASE43_URDU_AUDIT.md §2`) |
| Roman Urdu candidates | RUHSOLD etc. — **wrong script stratum** |

`ur-Arab` therefore has **no acquisition path** and requires annotation from
scratch. Roman Urdu results will be reported **separately and never pooled**
(`PHASE44_ANNOTATION_SPEC.md §1.5`).

## 2. Sizing for the FPR ≤ 0.15 gate

Derived and verified in `PHASE44_EVAL_PROTOCOL.md §2` (Wilson 95 %):

| Test negatives | True FPR 0.10 → CI | True FPR 0.25 → CI |
|---|---|---|
| 200 | [0.066, **0.149**] | [**0.195**, 0.314] |
| **250 (target)** | [0.069, **0.143**] | [**0.199**, 0.305] |

Requirement applies to **negatives in the frozen test split, `ur-Arab` only**.

| Parameter | Value |
|---|---|
| Test negatives required | **250** (min 200) |
| Test split fraction | **40 %** |
| Corpus negatives | `250 / 0.4` = **625** |
| Items at 1:1 balance | **1,250** |
| **Total `ur-Arab` corpus** | **≈ 1,250 items** |

Category shares per `PHASE44_ANNOTATION_SPEC.md §1.4`: 25 % plain non-toxic,
20 % plain toxic, 12 % borderline, 10 % quoted, 8 % negated, 10 % conversational,
15 % context-dependent, 10 % identity-reference-without-attack.

**Independently reviewed non-toxic examples are the critical path** — the gate is
FPR-driven, so the **625 non-toxic** items carry the decision and receive the
strictest review. Borderline/quoted/negated/context-dependent rows are
deliberately **over-sampled within the non-toxic half**, since these are where a
generic toxicity model over-fires.

## 3. Source of raw text

Ordered preference; each requires licence clearance before use:

1. Publicly licensed Urdu text (news comments, forums) with redistribution rights.
2. Commissioned **Urdu-native writers** producing natural utterances across the
   8 categories — most defensible, avoids third-party PII entirely.
3. Existing Urdu corpora **only** if toxicity labels are added by our annotators
   (labels then have clean provenance as `human_annotated`).

**Do not machine-translate** English toxicity data and label it human — that
would repeat the bn weakness (`PHASE2_MODEL_EVALUATION.md:42`: bn labels are
Qwen-generated, not human gold).

## 4. Annotator workforce

| Item | Specification |
|---|---|
| Annotators per item | **3 independent** (aligned with RUHSOLD's expert 3-way design, `PHASE46_RUHSOLD_LABEL_AUDIT.md §1`) |
| Qualification | native/near-native Urdu **readers of Arabic script**; must **not** rely on Roman transliteration; pass a calibration quiz (κ ≥ 0.70 on a 50-item gold set) |
| Adjudication | 3rd-party senior adjudicator for disagreements; adjudicator does not annotate the same item |
| Agreement | **Cohen's κ per category and per domain**, reported; **accept κ ≥ 0.70**, else revise guidelines and re-pilot |
| **Compensation** | **requires explicit approval before recruitment** — fair hourly rate, not per-label (per-label pay incentivises speed over accuracy) |
| Wellbeing | slurs and identity attacks are present by design; provide content warnings, opt-out, and rotation |

## 5. Annotation workflow

1. **Guidelines** from `PHASE44_ANNOTATION_SPEC.md §1`, translated to Urdu with
   worked examples for **quoting, negation, reclaimed slurs, and untargeted
   profanity** (the last being the live ambiguity flagged in the RUHSOLD audit).
2. **Pilot 50 items**, both classes, all 8 categories → measure κ → revise if < 0.70.
3. **Main pass**, 3 annotators, no visibility of split membership.
4. **Adjudication** of all disagreements.
5. **Freeze**: hash manifest over the test split *before* any scoring.

## 6. Split, dedup and leakage controls

Per `PHASE44_EVAL_PROTOCOL.md §4`, unchanged:

- Dedupe **before** splitting: NFKC-normalised exact match + **char-trigram
  Jaccard ≥ 0.80** + human review of fuzzy candidates.
- **Group-aware split** keyed on `group_id`; the routine **fails loudly** if any
  group straddles two splits.
- Ratio **40 / 20 / 40**, stratified so every category appears in every split.
- Assertions **L1–L7** must pass before any metric is reported — including
  **L5: zero overlap with the 596-row production `dataset_samples`**.
- Test evaluated **exactly once**; all selection on validation only.

## 7. Provenance and privacy

Every row records: `source`, `source_url`, `licence`, `provenance =
human_annotated`, `annotator_id` ×3, `annotator_confidence`,
`adjudication_status`, `final_label`, `created_at`, `group_id`, `script =
ur-Arab`, `transliteration_scheme = null`.

- **Prefer commissioned text over scraped text** — eliminates third-party PII
  exposure entirely and is the recommended path.
- If any third-party source is used, apply the §8 controls from
  `PHASE46_RUHSOLD_LABEL_AUDIT.md` (handle/URL stripping, retention limits,
  role-restricted access, counts-only reporting).
- Store raw text encrypted at rest; never emit raw rows to logs.

## 8. Acceptance status

| Item | State |
|---|---|
| Urdu-script corpus | **DOES NOT EXIST** |
| Annotation plan | **COMPLETE** |
| Compensation approval | **PENDING** |
| Source licence clearance | **PENDING** |
| Gate `ur-Arab` FPR ≤ 0.15 | **`NOT PASSED`** (unmeasured) |

**No Urdu-script data exists, and none is claimed. No label, provenance, sample
count or performance figure has been fabricated.**
