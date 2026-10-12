# AURA Phase 4.11 — P1/P2 Legal & Privacy Reviewer Checklist

**Status: PENDING and BLOCKING.**
**This document makes NO legal determination, offers NO legal advice, and claims
NO legal approval.** It exists only to hand a **qualified reviewer** the exact
questions and the evidence position. **Only a qualified legal/privacy reviewer
can close P1 and P2.**

Evidence base: `PHASE46_RUHSOLD_LABEL_AUDIT.md`, `PHASE47_PRIVACY_PLAN.md`,
`PHASE49_PRIVACY_REVIEW_CHECKLIST.md`, and measured facts from
`PHASE48_SCRATCH_VERIFICATION.md`.

---

## A. Dataset rights and provenance — P1

| # | Question for the reviewer | Evidence in hand | Missing |
|---|---|---|---|
| P1.1 | Does the MIT licence cover the **curators' artefact** (code, curation, format)? | **Yes** — HF API `license:mit`; README; curated at LUMS; peer-reviewed EMNLP 2020 (Rizwan, Shakeel, Karim) | — |
| P1.2 | Does MIT reach the **underlying tweets**? | **No evidence.** MIT was granted by curators who likely cannot re-license third-party platform content | **Chain of title for tweet text** |
| P1.3 | What is the source of the original data? | README *Source Data* = **"[More Information Needed]"** | **Provenance statement from authors** |
| P1.4 | Who are the authors/contact for a rights confirmation? | M. Haroon Shakeel (LUMS); `aclanthology.org/2020.emnlp-main.197/` | **Written reply** |
| P1.5 | Are the 3 cited papers' redistribution terms compatible with MIT? | Papers identified | **Licence review of each** |
| P1.6 | Is commercial/production use of the combined artefact permitted? | Not stated | **Explicit determination** |
| P1.7 | Annotator rights: 3 expert annotators contributed labels — are their contributions covered? | Annotators identified, majority vote | **Confirmation** |

**Reviewer deliverable:** a written opinion stating whether P1.2–P1.6 permit
import. **Until then P1 stays BLOCKED.**

## B. Lawful basis — P2

| # | Question for the reviewer | Evidence in hand | Missing |
|---|---|---|---|
| P2.1 | What is the **lawful basis** for processing this personal data? | **None identified** | **Documented basis** |
| P2.2 | Is consent obtained or required? | No consent mechanism exists upstream | **Determination** |
| P2.3 | Does legitimate-interests assessment apply? | Not performed | **LIA or equivalent** |
| P2.4 | Is the processing compatible with the original collection purpose? | Unknown — no provenance | **Determination** |

## C. Platform terms

| # | Question | Evidence | Missing |
|---|---|---|---|
| P2.5 | Which platform(s) did the tweets originate from? | Described as tweets; not confirmed | **Identification** |
| P2.6 | Do those platforms' ToS permit this secondary research use? | Not assessed | **ToS review** |
| P2.7 | Do ToS restrictions survive the curators' MIT grant? | Not assessed | **Determination** |

## D. PII and sensitive-data risk

| # | Question | Evidence in hand | Missing |
|---|---|---|---|
| P2.8 | Direct identifiers: are `@handles`/URLs/emails present? | **MEASURED: 0 handles, 4 URLs, 0 emails** across 10,010 rows | Confirmation the stripping was intentional & complete |
| P2.9 | Residual re-identification risk from free text? | Not assessed by a human | **Assessment** |
| P2.10 | **Special-category inference** — classes `2: Religious Hate` (563) and `3: Sexism` (603) = **1,166 rows** assert a protected characteristic about a person. Does this constitute special-category data? | **Structural fact established**; handle-stripping does **not** resolve it | **Determination** |
| P2.11 | Romanised/obfuscated identifiers not caught by regex? | Regex-only scan performed | **Human spot-check** |

## E. Retention and deletion

| # | Question | Evidence | Missing |
|---|---|---|---|
| P2.12 | Retention period and approved end date? | **None set** (see P5 gap in the matrix) | **Approved end date** |
| P2.13 | Can data-subject **erasure** be honoured? | **No deletion capability exists** in the codebase (P5 gap) | **Procedure + capability** |
| P2.14 | Does erasure cascade to splits, manifests, cached features, scratch copies? | Not implemented | **Procedure** |
| P2.15 | Backup deletion schedule? | Not defined | **Definition** |

## F. Cross-border and DPIA

| # | Question | Evidence | Missing |
|---|---|---|---|
| P2.16 | Are cross-border transfer obligations triggered? | Curators in Pakistan; hosting location unknown | **Location + determination** |
| P2.17 | Is a DPIA required? | Not assessed | **Assessor's determination** |
| P2.18 | Where will the data be stored if imported? | Would be local project storage | **Confirmation** |

---

## Reviewer decision block — to be completed by the reviewer, not by this project

```
Reviewer name:        ______________________________
Qualification:        ______________________________
Date:                 ______________________________

P1 — rights/provenance:   APPROVED  /  REJECTED  /  NEEDS MORE EVIDENCE
P2 — lawful basis/ToS:    APPROVED  /  REJECTED  /  NEEDS MORE EVIDENCE

Conditions or required actions:
_________________________________________________________________
_________________________________________________________________

Signature:             ______________________________
```

> **No box above may be completed by an automated process or by this project.**
> Until a signed reviewer entry exists, **P1 and P2 remain PENDING and BLOCKING**,
> and dataset import remains **NO-GO**.
