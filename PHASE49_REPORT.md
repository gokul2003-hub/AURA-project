# AURA Phase 4.9 — Final Report

**Outcome: all remaining decisions prepared for explicit approval. NOTHING
approved, imported, computed or changed.**

16:25:20 → documentation pass. Deliverables:
`PHASE49_LABEL_MAPPING_DECISIONS.md`, `PHASE49_PRIVACY_REVIEW_CHECKLIST.md`, this report.

---

## 1. M1–M4 mapping decision table (Fine-grained)

Counts are **measured** from Phase 4.8 (`Fine/train`, n = 7,208), not projected.

| ID | Class | Rows | → `toxic` | Dimension | Confidence | Status |
|---|---|---|---|---|---|---|
| **M1a** | `1: Normal` | 3,851 | **0** | — | High | **PENDING** |
| **M1b** | `0: Abusive/Offensive` | 1,729 | **1** | *none* | Medium-High | **PENDING** |
| **M2a** | `2: Religious Hate` | 563 | **1** | `identity_hate` | High | **PENDING** |
| **M2b** | `3: Sexism` | 603 | **1** | `identity_hate` | High | **PENDING** |
| **M3** | **`4: Profane/Untargeted`** | **462** | **EXCLUDED → unknown** | — | ambiguous | **PENDING (recommend confirm exclusion)** |
| **M4** | — | — | binary headline only | — | structural | **PENDING** |

Pool if approved as recommended: toxic **2,895** / non-toxic **3,851** /
excluded **462** / **USABLE 6,746**.

**M3 unchanged from default:** `Profane/Untargeted` stays **excluded/unknown**
and is **never counted as verified non-toxic** — doing so would deflate the
measured FPR and could manufacture a gate pass.

## 2. What is and is not evaluable (M4)

**Binary headline `toxic` only.** RUHSOLD has a **single label column**, so
`severe_toxic`, `obscene`, `threat` and `insult` are **structurally
unrecoverable**; `identity_hate` is recoverable *only* as a co-occurring flag
for classes 2/3. **Any category-level metric from RUHSOLD would be fabricated.**

Caveat surfaced for the approver: the two label layers disagree on **one row**
(Coarse abusive 3,358 vs Fine 3,357), so they are not perfectly consistent.

## 3. P1–P2 — legal review, BLOCKING, no conclusion offered

**This report makes no legal determination.** Documented for a qualified
reviewer: whether MIT covers the **underlying tweets** (vs the curators'
artefact, which it verifiably does); chain of title (upstream *Source Data* is
"[More Information Needed]"); **lawful basis**; platform ToS; **erasure and
objection rights**; cross-border transfer; DPIA applicability.

⚠️ **Special-category concern remains live:** classes `2`/`3` total **1,166
rows** and **class membership itself asserts a protected characteristic**, which
handle-stripping does not resolve.

**Mitigating measured evidence:** the Phase 4.8 scan found **0 handles, 4 URLs,
0 emails** across 10,010 rows — direct-identifier exposure is far lower than the
structural estimate. This **lowers but does not eliminate** the risk.

## 4. P3–P5 controls — specified, implementation pending

- **P3 redaction before dedup** — and explicitly **before** dedup, or Phase 4.8's
  V5–V7 figures will not reproduce (normalisation changes the trigram sets).
- **P3b versioned reproducible preprocessing** — `preprocess_version`, pinned
  regex, NFKC, golden fixture test; V5–V7 must re-derive exactly.
- **P3c salted text hashes** — join key enabling dedup **without** retaining raw
  text; salt held separately, never committed. Hashing is **not** anonymisation.
- **P4** role-restricted access, logged, **counts-only reporting**, encrypted at rest.
- **P5** time-bounded retention with an **approved end date**, and **cascade
  deletion** reaching splits, manifests, cached features and scratch copies.

## 5. C1 — `ur-Arab` commissioning reconfirmation

≈ **1,250 items**, 1:1, with the **625 non-toxic** items as the critical path
(the gate is FPR-driven). **3 independent native Urdu-*script* annotators** +
senior adjudicator, **κ ≥ 0.70**, calibration quiz, wellbeing provisions.
**Compensation requires explicit approval** — fair hourly, not per-label.
Commissioned text preferred over scraped text to eliminate third-party PII.

**No Urdu-script data exists. None is claimed.**

## 6. Safety

| Check | Result |
|---|---|
| **Production engine** | **`legacy`** |
| `tuned_threshold.json` | `f31f4975d29a151f…` **UNCHANGED** |
| `phase2_benchmark.json` | `5a9d94e267806ea0…` **UNCHANGED** |
| `phase3_benchmark.json` | `f3a5ceb488f4a9ad…` **UNCHANGED** |
| Frozen `ur_test` / `ur_val` | **UNCHANGED** |
| SQLite integrity / FK | **ok** / **clean** |
| Rows / splits | **596**; **137 / 29 / 31 + 399 unassigned** |
| `training_runs` / `model_versions` | **8 / 12** |
| Active model | `improved_v10` |
| Downloaded / imported / purchased / annotated | **NONE** |
| Benchmark metrics run | **NONE** |
| Thresholds tuned | **NONE** |
| Frozen splits changed | **NONE** |
| Project `data/` written | **NONE** (mtime sweep clean) |
| User changes preserved | **yes** |

## 7. Decision register — nothing approved

| ID | Item | Status | Who decides |
|---|---|---|---|
| **M1** | `Normal → non_toxic`, `Abusive/Offensive → toxic` | **PENDING** | approver |
| **M2** | `Religious Hate`/`Sexism` → `toxic` + `identity_hate` | **PENDING** | approver |
| **M3** | Confirm **exclusion** of `Profane/Untargeted` | **PENDING** | approver |
| **M4** | Accept **binary-only** evaluation | **PENDING** | approver |
| **P1** | Licence scope vs underlying tweet rights | **BLOCKED** | **legal reviewer** |
| **P2** | Lawful basis / ToS / erasure | **BLOCKED** | **legal reviewer** |
| **P3–P5** | Redaction, preprocessing, hashing, access, retention | **PENDING** | approver |
| **C1** | `ur-Arab` commissioning + **compensation** | **PENDING — blocking** | approver |

## 8. Blocking path to any evaluation

```
P1 ─┐
P2 ─┼─► lawful import ─► M1–M4 mapping freeze ─► re-split (dedup + group-aware)
C1 ─┘                                          ─► freeze test + hash manifest
                                                ─► single per-stratum evaluation
```

**Both quality gates remain `NOT PASSED`.** Roman Urdu has a verified,
sufficiently-sized labelled pool (6,746 usable; 1,540 test negatives at 40 %) but
**no evaluation may run until P1–P2 and M1–M4 close**. Urdu-script remains
unmeasured and uncommissioned.

**Documentation is not approval. No item above is approved.**
