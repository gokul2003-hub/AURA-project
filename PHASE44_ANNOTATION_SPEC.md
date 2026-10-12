# AURA Phase 4.4 — Task-Matched Urdu Toxicity Dataset: Annotation Specification & Licensing Checklist

**Status: SPECIFICATION COMPLETE — NO HUMAN-LABELLED DATA OBTAINED.**

> This is the Option (c) planning milestone. **No dataset was collected,
> purchased, downloaded or labelled.** No item in this document is
> human-labelled data, and none is presented as such. Any example text is an
> explicitly marked **synthetic illustrative placeholder**.

## Why this specification exists

`PHASE43_URDU_AUDIT.md §2` proved the current Urdu corpus is **hate-speech
labelled**, not toxicity labelled — its own per-row annotation reads
`'expert-generated hate-speech labels mapped to binary; unmappable values excluded'`.
It is the only group in `manifest.json` sourced from a hate-speech corpus; every
other language uses a genuine toxicity/offence corpus with labels used as-is.
That definitional mismatch is the root cause of the FPR breach and **cannot be
fixed by any threshold change.**

---

## 1. Annotation specification

### 1.1 Task definition (must match AURA exactly)

AURA's task is **multi-dimension comment toxicity** (`DATASET_GUIDE.md:35,38`):

```
toxic, severe_toxic, obscene, threat, insult, identity_hate
- `toxic` is the binary headline label; the other five columns are categories.
```

The **headline label** this dataset must provide is binary `toxic`. The five
categories are strongly recommended as secondary annotation, because AURA's
production head emits them.

### 1.2 Operational label definitions

| Label | Definition |
|---|---|
| `toxic = 1` | Rude, disrespectful or unreasonable in a way likely to make a person leave the conversation, **or** an attack on a person/group on an identity basis. |
| `toxic = 0` | Does not meet that bar — **even if** negative, blunt, profane without a target, political, religious, or discussing a sensitive topic. |

### 1.3 Category decision table

| Category | `toxic` | Notes |
|---|---|---|
| Targeted identity attack | **1** | Attack by identity attribute |
| Direct insult aimed at a reader | **1** | Likely to make them leave |
| Severe profanity directed at a person | **1** | Targeted, not ambient |
| Profanity with **no target** | **0** | Ambient profanity ≠ toxicity |
| **Quoted** toxicity (news, reporting, screenshot) | **0** | Quoting ≠ endorsing |
| **Negated** toxicity ("this is not abusive") | **0** | Negation flips polarity |
| Friendly banter containing a swear | **0** | Conversational, non-harming |
| Medical / clinical / educational mention | **0** | Context-dependent |
| Political or religious disagreement, no attack | **0** | Charged ≠ hateful |
| Anger with no person/group target | **0** | Venting, not attacking |
| Reclaimed / in-group slur | **0** default | **Always adjudicate** |

### 1.4 Required item categories and target shares

| # | Category | Share | FPR rationale |
|---|---|---|---|
| 1 | Plain non-toxic | 25 % | True-negative backbone |
| 2 | Plain toxic | 20 % | Keeps recall measurable |
| 3 | **Borderline** (mild profanity, reclaimed slurs) | 12 % | Primary false-positive zone |
| 4 | **Quoted** toxicity | 10 % | Reporting vs attacking |
| 5 | **Negated** toxicity | 8 % | Polarity inversion |
| 6 | **Conversational** banter with profanity | 10 % | Toxic tokens, friendly tone |
| 7 | **Context-dependent** (medical, news, politics, religion) | 15 % | Charged vocabulary, no attack |
| 8 | Identity reference without attack | 10 % | Targets `identity_attack` FP |

Categories 3–8 are where a generic toxicity model over-fires; they carry the
highest information value for this gate.

### 1.5 Script strata — reported separately, never pooled

| Stratum | Code | Requirement |
|---|---|---|
| Urdu script | `ur-Arab` | Full coverage of categories 1–8 |
| **Roman Urdu** | `ur-Latn` | **Full parallel coverage of categories 1–8** |
| Code-mixed | `mixed` | Labelled, counted, reported separately |

Roman Urdu is a **parallel stratum**, not a sub-slice. A single pooled "Urdu"
number would let the currently-unevaluated stratum hide behind Urdu-script
performance. **Separate FPR + CI per stratum is mandatory.**

### 1.6 Roman Urdu guidelines

- **Transliteration:** accept UMP/roman, scientific IAST-style and everyday
  chatroman; record the scheme per item. Do not force one scheme.
- **Spelling variation:** `kia/kya/kiya`, `nahi/nahiN/naheen`, `hai/hain/he` are
  one concept — collapse to one `group_id` so variants never straddle a split.
- **Code-mixed Urdu-English** ("ye bilkul boring hai") is labelled as a whole
  utterance with `script = mixed`.
- **Roman Urdu must be annotated by humans who read Roman Urdu.** Machine
  transliteration from Urdu script followed by re-labelling is **not**
  human-labelled Roman Urdu and must be tagged `synthetic_transliterated`.

### 1.7 Annotation workflow

1. **Pilot:** 50 items spanning both strata and all 8 categories.
2. **Two independent annotators** per item; neither sees split membership.
3. **Third-reviewer adjudication** of every disagreement.
4. **Cohen's κ per stratum and per category.** **Accept threshold κ ≥ 0.70.**
   Below that: revise the guidelines and re-run the pilot — items are never
   silently force-labelled.
5. Guidelines must include worked examples for **quoting, negation and reclaimed
   slurs**, since those three decide this gate.

### 1.8 Schema

```jsonc
{
  "id": "ur-000123",                 // required, unique
  "text": "...",                     // required
  "label": 0,                        // required 0|1  (toxic headline)
  "categories": ["insult"],          // subset of the 5 secondary dims
  "script": "ur-Arab",               // ur-Arab | ur-Latn | mixed   (required)
  "transliteration_scheme": null,    // required when script != ur-Arab
  "source": "...",                   // required
  "source_url": "...",               // required when applicable
  "licence": "MIT",                  // required
  "provenance": "human_annotated",   // human_annotated | human_existing |
                                     // synthetic_illustrative | synthetic_transliterated
  "group_id": "fam-0042",            // required, drives group-aware split
  "domain_tag": "news",              // news|medical|political|religious|sport|
                                     // entertainment|chat|other
  "quoted": false, "negated": false, "context_dependent": false,  // required
  "annotator_id": "A1",              // required
  "annotator_confidence": 0.9,       // required
  "adjudication_status": "adjudicated",  // auto|agree|adjudicated
  "final_label": 0,                  // required post-adjudication
  "created_at": "...", "notes": ""
}
```

**Any row whose `provenance` is not `human_annotated` or `human_existing` is
excluded from all gate metrics.** Synthetic rows exist only to exercise the
pipeline.

---

## 2. Licensing & provenance checklist

Complete **before** any purchase, download or annotation spend. A single
unanswered row blocks acquisition.

| # | Check | Required answer | Status |
|---|---|---|---|
| 1 | Licence name + version | e.g. MIT, CC-BY-4.0, CC0-1.0 | ☐ |
| 2 | Commercial use permitted | explicit yes | ☐ |
| 3 | Redistribution permitted | explicit yes | ☐ |
| 4 | Modification / derivative labels permitted | explicit yes | ☐ |
| 5 | **Human vs machine-generated labels** | must be **human** | ☐ |
| 6 | Annotator count & qualification | ≥ 2, documented | ☐ |
| 7 | Annotator compensation | fair, documented | ☐ |
| 8 | Consent / PII status | no unconsented personal data | ☐ |
| 9 | Collection methodology documented | required | ☐ |
| 10 | Label definitions published | must be **toxicity**, not hate speech | ☐ |
| 11 | Roman Urdu coverage | real, not transliterated | ☐ |
| 12 | Upstream source URL + retrieval date | recorded per row | ☐ |
| 13 | Stable snapshot hash | SHA256 recorded at acquisition | ☐ |

**Project precedent for check 5:** `PHASE2_MODEL_EVALUATION.md:42` warns that
the bn labels are *Qwen-generated weak annotations, not human gold labels*. That
failure mode must not be repeated for Urdu.

**Provenance normalisation:** the existing `ur_test.csv` leaves the per-row
`license` and `source_url` columns **empty for all 180 rows**, retaining licence
only inside an embedded JSON blob. This specification requires both columns
populated on every row.

---

## 3. Acquisition options (identified, NOT obtained)

> **No external dataset could be verified.** The environment has **no network
> access** — three web-research queries returned no results, and sub-agents
> failed with `getaddrinfo ENOTFOUND opencode.ai`. Consequently **no external
> dataset's licence, size or label quality could be confirmed**, and no candidate
> is named here as available. Naming one would be fabrication.

Ordered preference once network access exists:

1. **Existing public Urdu *toxicity/abuse* corpus** with a clear licence and
   human labels — cheapest, fastest.
2. **Commissioned annotation** using §1 — most defensible, highest cost.
3. **Last resort only:** expansion of the existing MIT hate-speech corpus,
   with the task mismatch permanently documented in the benchmark metadata.

---

## 4. Blocker

**Human-labelled, task-matched Urdu toxicity data — in either script stratum —
does not exist in this environment and cannot be obtained from it.** Work stops
here at the planning milestone. No dataset is claimed complete, and the quality
gate remains **`NOT PASSED`**.

**No production file, threshold, benchmark artifact, frozen split or model was
created, modified or deleted by this specification.**
