# AURA Phase 4.3 — Dedicated Urdu Evaluation Set: Specification & Approval-Ready Plan

**Status: DESIGN COMPLETE — DATA NOT OBTAINED.**

> **Provenance note:** the sub-agent assigned to this section **failed with a DNS
> error (`getaddrinfo ENOTFOUND opencode.ai`) and produced no output.** This
> specification was written by the lead from measured project evidence.
>
> **No dataset has been collected, purchased or downloaded.** No human-labelled
> data exists yet for this specification. Any example text below is an explicitly
> marked **synthetic illustrative placeholder** and is NOT presented as
> human-labelled or as benchmark data.

---

## 1. Annotation policy and label definitions

AURA's task is **multi-dimension comment toxicity** (`DATASET_GUIDE.md:35,38`):
`toxic` is the binary headline, with categories
`severe_toxic, obscene, threat, insult, identity_hate`.

**This set must be labelled to THAT definition — not to a hate-speech
definition.** The audit (`PHASE43_URDU_AUDIT.md §2`) proved the existing Urdu
corpus is hate-speech labelled, which is the root cause of the FPR breach.

### Operational label definitions

| Label | Definition |
|---|---|
| `toxic = 1` | The comment is **rude, disrespectful or unreasonable in a way likely to make a person leave the conversation**, OR attacks a person/group on an identity basis. |
| `toxic = 0` | The comment does not meet that bar, **even if it is negative, blunt, political, profane in a non-targeted way, or mentions sensitive topics.** |

### Category guidance (mutually non-exclusive; annotate all that apply)

| Category | Label | Rationale |
|---|---|---|
| Targeted identity attack | **1** | Attack on a group/person by identity |
| Direct insult aimed at a reader | **1** | Likely to make them leave |
| Severe profanity directed at someone | **1** | Targeted, not ambient |
| Profanity with **no target** ("what a mess") | **0** | Ambient profanity is not toxicity |
| Reclaimed / in-group slur | **0** (default) | Context-dependent; adjudicate |
| **Quoted** toxicity (reporting, news, screenshot) | **0** | Quoting is not endorsing |
| **Negated** toxicity ("this is not abusive") | **0** | Negation flips the target |
| Friendly banter containing a swear | **0** | Conversational, non-harming |
| Medical / clinical / educational mention | **0** | Context-dependent, non-attack |
| Political / religious disagreement, no attack | **0** | Charged ≠ hateful |
| Anger without a person/group target | **0** | Venting, not attacking |

**Borderline items must be annotated, not excluded.** They are precisely where a
generic toxicity model over-fires, so they are the highest-value rows in the set.

---

## 2. Required example categories and target proportions

| # | Category | Target share | Why it matters for FPR |
|---|---|---|---|
| 1 | Plain non-toxic Urdu | 25 % | True-negative backbone |
| 2 | Plain toxic Urdu | 20 % | Keeps recall measurable |
| 3 | **Borderline** (mild profanity, reclaimed slurs) | 12 % | Classic false-positive zone |
| 4 | **Quoted** toxicity | 10 % | Reporting ≠ attacking |
| 5 | **Negated** toxicity | 8 % | Negation flips polarity |
| 6 | **Conversational** banter w/ profanity | 10 % | Friendly tone, toxic tokens |
| 7 | **Context-dependent** (medical, news, politics, religion) | 15 % | Charged vocabulary, no attack |
| 8 | Identity reference without attack | 10 % | Directly targets identity_attack FP |
| 9 | **Roman Urdu** (all of the above, transliterated) | *separate stratum* | Currently **0 coverage** |

Roman Urdu is a **parallel stratum**, not a sub-slice: the same categories 1–8
must be represented in transliterated form, reported **separately**.

---

## 3. Roman Urdu annotation guidelines

- **Transliteration:** accept common schemes (UMP/roman, scientific IAST-style,
  and everyday chatroman); do not force one. Record the scheme per item.
- **Spelling variation:** `kia/kya/kiya`, `nahi/nahiN/naheen`, `hai/hain/he`
  are ONE concept — group them under one `group_id` so variants never split
  across train/test.
- **Code-mixed Urdu-English:** extremely common ("ye bilkul boring hai").
  Label the whole utterance; mark `script = mixed`.
- **Roman Urdu must be labelled by annotators who actually read Roman Urdu** —
  not machine-transliterated from Urdu script and re-labelled as human.

---

## 4. Schema

```jsonc
{
  "id":                    "ur-000123",          // required, unique
  "text":                  "...",                // required
  "label":                 0,                    // required, 0|1 (toxic headline)
  "categories":            ["insult"],           // optional, subset of the 6 dims
  "script":                "ur-Arab",            // required: ur-Arab | ur-Latn | mixed
  "transliteration_scheme": null,                // required when script != ur-Arab
  "source":                "...",                // required
  "source_url":            "...",                // required when applicable
  "licence":               "MIT",                // required
  "group_id":              "fam-0042",           // required, drives group-aware split
  "domain_tag":            "news",               // required: news|medical|political|
                                                 //   religious|sport|entertainment|chat|other
  "quoted":                false,                // required
  "negated":               false,                // required
  "context_dependent":     false,                // required
  "annotator_id":          "A1",                 // required
  "annotator_confidence":  0.9,                  // required, 0..1
  "adjudication_status":   "adjudicated",        // required: auto|agree|adjudicated
  "final_label":           0,                    // required post-adjudication
  "created_at":            "2026-10-11T00:00Z",  // required
  "notes":                 ""
}
```

Any `source` value of `synthetic_illustrative` **must** be excluded from all
metrics — synthetic rows are for pipeline testing only, never benchmarking.

---

## 5. Annotation workflow and quality control

1. **Pilot round:** 50 items, both scripts, both annotators — surfaces
   definition gaps *before* the main pass.
2. **Two independent annotators per item.** Neither sees split membership.
3. **Adjudication** by a third reviewer for every disagreement.
4. **Inter-annotator agreement:** **Cohen's κ**, reported per script and per
   category. **Accept threshold κ ≥ 0.70**; below that, the guidelines are
   revised and the pilot re-run — items are not silently force-labelled.
5. Annotator instructions must contain worked examples for quoting, negation
   and reclaimed slurs, since those decide the FPR.

---

## 6. Duplicate and near-duplicate detection (run BEFORE splitting)

- **Exact:** NFKC-normalise, lowercase, strip punctuation, collapse whitespace →
  exact-match dedupe.
- **Fuzzy:** char-trigram **Jaccard ≥ 0.80** → candidate near-duplicate, then
  human review. (Same method and threshold that found 0 near-duplicates in the
  existing corpus, so the two corpora stay comparable.)
- **Transliteration families:** Roman Urdu variants of one utterance collapse
  to a single `group_id`.

---

## 7. Group-aware splitting

- **Group key:** `group_id` = normalized-text family (covers transliteration
  variants, near-duplicates, and same-thread utterances). **All members of a
  group land in exactly one split** — no related example may straddle a boundary.
- **Ratio:** 40 % train / 20 % validation / 40 % **frozen test**, stratified so
  every category and both scripts appear in each split.
- **Required size for the gate** (from `PHASE43_URDU_AUDIT.md §6`): the current
  90 negatives are inadequate. Target **≥ 250 negatives per script stratum** for
  80 % power to separate FPR 0.15 from 0.25.
- Separate reporting for `ur-Arab` and `ur-Latn` — **never a single pooled Urdu
  number**, which would let the unevaluated Roman Urdu stratum hide.

---

## 8. Frozen-test protocol

1. Assemble and adjudicate the full set.
2. Record the **SHA256 of the test split** in a manifest before any tuning.
3. All candidate/threshold selection uses **validation only**.
4. The frozen test set is evaluated **exactly once** per candidate.
5. Existing frozen files remain frozen:
   `ur_test.csv f18d80f3…e9c5`, `ur_val.csv 8727f2ba…c13a`.

---

## 9. Sourcing — preference for legitimately licensed human-labelled data

Prefer, in order: (a) an existing public Urdu **toxicity/abuse** corpus with a
clear licence; (b) commissioned annotation using this specification; (c) only
as a last resort, expansion of the existing MIT hate-speech corpus **with the
task mismatch explicitly documented**.

**Licence questions that must be answered BEFORE any purchase or download:**
licence name and version; commercial-use permitted; redistribution permitted;
annotator labour provenance and compensation; whether labels are human or
model-generated (project precedent: `PHASE2_MODEL_EVALUATION.md:42` warns that
bn labels are Qwen-generated weak annotations, **not** human gold labels).

> **No new data has been obtained.** This section is a plan, not a dataset.

---

## 10. Approval-ready plan

| # | Step | Owner (role) | Est. effort |
|---|---|---|---|
| 1 | **Approve** label definitions in §1 against AURA's toxicity task | Product/ML lead | decision |
| 2 | Shortlist candidate Urdu **toxicity** corpora and clear licences | Data lead | 1–2 d |
| 3 | Write bilingual annotator guidelines from §2–§3 | ML lead | 1 d |
| 4 | Build labelling schema + tooling from §4 | Engineer | 1–2 d |
| 5 | Pilot 50 items, measure κ, revise if κ < 0.70 | Annotators | 1 d |
| 6 | Full annotation, 2 annotators + adjudication, ≥250 negatives/stratum | Annotators | 1–2 wk |
| 7 | Dedupe + group-aware split + freeze + hash manifest | Engineer | 0.5 d |
| 8 | Single frozen-test evaluation of baseline | ML lead | 0.5 d |

### The decision required

**Approve acquisition + annotation of a task-matched Urdu toxicity set at
≥ 250 negatives per script stratum (Urdu script and Roman Urdu), using the
definitions in §1.** Until that exists, the 0.15 FPR gate cannot be validly
satisfied — the present corpus measures a different task, and no threshold
change can fix a definitional mismatch.

---

**Nothing here was fabricated as human-labelled. No dataset is claimed complete.
No production file, threshold, benchmark artifact or model was modified.**
