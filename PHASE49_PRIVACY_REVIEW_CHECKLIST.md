# AURA Phase 4.9 — P1–P5 Privacy & Legal Review Checklist

**Status: PREPARED FOR REVIEW — NOT APPROVED.**
**This document makes no legal determination and grants no approval.** Only the
user or a qualified legal/privacy reviewer may close P1–P2. Nothing below should
be read as legal advice or as a conclusion that the use is lawful.

Evidence base: `PHASE46_RUHSOLD_LABEL_AUDIT.md §8`, `PHASE47_PRIVACY_PLAN.md`,
and **measured** PII counts from `PHASE48_SCRATCH_VERIFICATION.md §8`.

---

## PART A — P1/P2: legal review (BLOCKING, human review required)

### P1 — Licence scope vs underlying tweet rights

| # | Question for the reviewer | Evidence available | Status |
|---|---|---|---|
| P1.1 | Does MIT cover the **curators' artefact**? | **Yes** — API `license:mit`; README; curated at LUMS; peer-reviewed EMNLP 2020 | **Verified fact** |
| P1.2 | Does MIT cover the **underlying tweets**? | **Unknown.** MIT was granted by curators, who likely cannot re licence third-party platform content | **BLOCKED — legal** |
| P1.3 | Is there a documented chain of title for the tweets? | **No** — README *Source Data* reads "[More Information Needed]" | **BLOCKED** |
| P1.4 | Does the repo's MIT grant extend to commercial redistribution of the combined artefact? | Requires review | **PENDING** |
| P1.5 | Are the 3 cited papers' redistribution terms compatible? | Requires review | **PENDING** |

### P2 — Lawful basis and platform terms

| # | Question for the reviewer | Evidence available | Status |
|---|---|---|---|
| P2.1 | What is the **lawful basis** for processing this personal data? | None identified | **BLOCKED — legal** |
| P2.2 | Do the platform's ToS permit this secondary research use? | Not assessed upstream | **BLOCKED** |
| P2.3 | Do data-subject rights (access, objection, **erasure**) apply, and can they be honoured? | No upstream procedure exists | **BLOCKED** |
| P2.4 | Are cross-border transfer obligations triggered? | Curators in Pakistan; hosting unknown | **PENDING** |
| P2.5 | Is a DPIA required? | Assessor to determine | **PENDING** |

> **Note the evidence that lowers — but does not eliminate — the risk:** the
> Phase 4.8 PII scan measured **`@handles` = 0**, **URLs = 4**, **emails = 0**
> across 10,010 rows. Handles appear to have been **stripped upstream**. This
> materially reduces direct-identifier exposure relative to the structural
> estimate in `PHASE47_PRIVACY_PLAN.md §2`.

### Special-category concern — remains live ⚠️

Measured class distribution: `2: Religious Hate` **563**, `3: Sexism` **603**.
**Class membership itself asserts a protected characteristic about a person**,
even where direct identifiers are absent. Pseudonymised text carrying such
inferences can still constitute special-category data. **This is not resolved by
the handle-stripping finding.**

---

## PART B — P3–P5 controls (specification ready; implementation pending approval)

### P3 — Redaction, applied BEFORE deduplication

| Control | Specification |
|---|---|
| Patterns | `@\w+` → `[USER]`; `https?://\S+`, `t.co/\S+` → `[URL]`; emails → `[EMAIL]`; phone patterns → `[PHONE]`; numeric IDs ≥ 6 digits → human review |
| Method | regex **plus human spot-check** (regex alone misses romanised/obfuscated forms) |
| **Ordering** | **Redaction must run before dedup and near-duplicate detection** — otherwise V5–V7 counts from Phase 4.8 will not reproduce, because normalization changes the trigram sets |
| Verified risk level | **Low** — measured 0 handles, 4 URLs, 0 emails |

### P3b — Reproducible versioned preprocessing

| Control | Specification |
|---|---|
| Versioned pipeline | `preprocess_version` recorded per artifact; changes bump the version |
| Determinism | pinned regex set; NFKC normalisation; documented case-folding |
| Reproducibility gate | Phase 4.8 V5–V7 figures must re-derive exactly under the pinned version |
| Golden test | a fixed fixture asserting normaliser output, so drift is caught |

### P3c — Salted text hashes

| Control | Specification |
|---|---|
| Join key | `text_hash = SHA256(salt || normalised_text)` |
| Salt | generated once, stored **separately** with restricted access; never committed |
| Purpose | enables dedup and cross-split overlap detection **without** retaining raw text |
| Note | hashing is **not** anonymisation; the text itself remains personal data |

### P4 — Restricted access and counts-only reporting

| Control | Specification |
|---|---|
| Access | role-based, least privilege, access logged |
| Raw text | **never** in application logs, error traces, tickets or reports |
| Reporting | **aggregate counts only** — this and all prior phase reports already obey this |
| Storage | encrypted at rest |

### P5 — Retention limits and cascade deletion

| Control | Specification |
|---|---|
| Retention | time-bounded, with an explicit end date **approved up front** |
| Erasure procedure | remove an individual row **and cascade** to derived artifacts: splits, hash manifests, cached features, any scratch copies |
| Backups | included in the deletion schedule |
| Evidence tension | Phase 4.8 scratch files were **already deleted** after their findings were transcribed into the project reports — evidence is preserved as **statistics**, not as retained personal data |

---

## PART C — C1: `ur-Arab` commissioning (reconfirmation required)

| Item | Specification | Status |
|---|---|---|
| Volume | ≈ **1,250 items**, `ur-Arab`, 1:1 balance (250 test negatives ÷ 40 % split) | **PENDING C1** |
| Critical path | the **625 non-toxic** items (the gate is FPR-driven) | PENDING |
| Annotators | **3 independent native Urdu *script* readers** + senior adjudicator | PENDING |
| Agreement | **Cohen's κ ≥ 0.70** per category; calibration quiz; re-pilot if below | PENDING |
| Wellbeing | content warnings, opt-out, rotation, support (slur-heavy material by design) | PENDING |
| **Compensation** | **fair hourly rate, not per-label — requires explicit approval** | **PENDING — blocking** |
| Source preference | **commissioned text over scraped text** — eliminates third-party PII entirely | PENDING |

---

## PART D — decision register

| ID | Item | Status |
|---|---|---|
| **P1** | Licence scope vs underlying tweet rights | **BLOCKED — legal review required** |
| **P2** | Lawful basis / platform ToS / erasure rights | **BLOCKED — legal review required** |
| **P3** | Redaction before dedup | **PENDING** (spec ready) |
| **P3b** | Versioned reproducible preprocessing | **PENDING** (spec ready) |
| **P3c** | Salted text hashes | **PENDING** (spec ready) |
| **P4** | Restricted access, counts-only reports | **PENDING** (spec ready) |
| **P5** | Retention + cascade deletion | **PENDING** (spec ready) |
| **C1** | `ur-Arab` commissioning + **annotator compensation** | **PENDING — blocking** |

**No legal approval is claimed. No legal conclusion is offered. Documentation is
not approval.**
