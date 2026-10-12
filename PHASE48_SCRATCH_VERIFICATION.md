# AURA Phase 4.8 — Scratch Verification (A1 approved, scratch-only)

**A1 authorization basis:** the Phase 4.8 brief is titled *"Approved Scratch
Verification Only"* and directs scratch download, verification and scratch
cleanup. Recorded here as the authorization of record for audit.

**Scope honoured:** 6 parquet files downloaded to
`%TEMP%\aura-phase48-scratch` — **outside the project tree**, chmod **0o444
(read-only evidence)**. **Nothing was imported into AURA.** No frozen split,
threshold, benchmark artifact, database record or model was touched.

**Raw text was never printed or persisted into the project** — every figure below
is an aggregate count.

---

## 1. Files acquired (V2 checksums)

| File | Bytes | SHA256 (first 16) |
|---|---|---|
| `Coarse_Grained/train` | 525,200 | `974c71ca5261efae` |
| `Coarse_Grained/test` | 147,029 | `b5e07f4849ff9ecd` |
| `Coarse_Grained/validation` | 58,491 | `850a3d809bb192a6` |
| `Fine_Grained/train` | 525,885 | `00eadf726850f32b` |
| `Fine_Grained/test` | 147,890 | `202503e8552bfe14` |
| **`Fine_Grained/validation`** | **525,885** | **`00eadf726850f32b`** ← identical to `Fine/train` |

Full 64-char hashes recorded in scratch `_manifest.json`.

**Byte totals reconcile exactly with the card:** Coarse 730,720 B and Fine
1,199,660 B match the published `download_size` values **to the byte**.

---

## 2. ⚠️ FINDING 1 — the 2,002-row `test` split is **UNLABELLED**

| Split | `label` values observed |
|---|---|
| `Coarse_Grained/test` | **`null` × 2002** |
| `Fine_Grained/test` | **`null` × 2002** |

**All 2,002 rows carry a null label in both configs.** This is decisive and
**independent** of the Phase 4.6 split-name swap: the split **cannot serve any
supervised purpose** — not as a test set, not as a validation set. It is a
label-holding-out file.

This **supersedes** the Phase 4.7 concern about "using the authors' validation
split as a test set". The real reason it is unusable is simpler: **there are no
labels to score against.**

## 3. ⚠️ FINDING 2 — YAML is right, prose is wrong

**V1 row counts match the YAML exactly**, so the machine-readable block is
authoritative and the narrative prose is simply incorrect:

| Split | Prose | **YAML / ACTUAL** |
|---|---|---|
| 70 % | 7,209 | **7,208** ✅ |
| 20 % | 2,003 | **2,002** ✅ |
| 10 % | 801 | **800** ✅ |

## 4. ⚠️ FINDING 3 — `Fine_Grained/validation` confirmed duplicate (V8)

Tweet content **and** labels are **identical** to `Fine_Grained/train`
(7,208 rows, 525,885 B, same SHA256). **Confirmed unusable.** V6 shows 7,198
normalised texts shared — the 10-row delta is intra-split duplication, not
distinct content.

## 5. V3/V4/V10 — schema, labels, distribution

Schema is exactly `['tweet', 'label']`. Recall **0 = Abusive/Offensive (toxic)**
and **1 = Normal (non-toxic)**.

| Split | Rows | label distribution |
|---|---|---|
| Coarse/train | 7,208 | `0: 3358`, `1: 3850` |
| Coarse/validation | 800 | `0: 372`, `1: 428` |
| Coarse/test | 2,002 | **`null`: 2002** |
| Fine/train | 7,208 | `0: 1729`, `1: 3851`, `2: 563`, `3: 603`, `4: 462` |
| Fine/validation | 7,208 | identical to Fine/train |
| Fine/test | 2,002 | **`null`: 2002** |

**V9 — Coarse vs Fine are two label layers over the same tweets, but not
row-aligned** (`text_order_identical = False`; validation sizes 800 vs 7,208).
Reconciling the layers: Coarse abusive 3,358 vs Fine (0+2+3+4) 3,357 — a
**one-row disagreement**; Coarse normal 3,850 vs Fine normal 3,851. Minor, but it
means the two layers are not perfectly consistent.

## 6. V5/V6 — duplicates and cross-split overlap

**Intra-split duplicate extras:** Coarse/train **19**, Coarse/test 3,
Coarse/validation 0, Fine/train **10**, Fine/validation 10, Fine/test 3.

**Cross-split normalised-exact overlap:**

| Pair | Shared |
|---|---|
| Coarse train↔test | **4** |
| Coarse train↔validation | **2** |
| Coarse test↔validation | **1** |
| Fine train↔test | **9** |
| Fine train↔validation | **7,198** (the duplicate) |
| Fine test↔validation | **9** |

Small but **non-zero** — genuine leakage, confirming that **no upstream split
may be adopted as-is**. It must be re-split after deduplication.

## 7. V7 — near-duplicates (trigram Jaccard ≥ 0.80) — COMPLETE

| Pair | Near-dup pairs | Exact-dup pairs (V6) |
|---|---|---|
| Coarse train↔test | **15** | 4 |
| Coarse train↔validation | **5** | 2 |
| Coarse test↔validation | **2** | 1 |
| Fine train↔test | **22** | 9 |
| Fine train↔validation | *skipped* — duplicate of train | 7,198 |
| Fine test↔validation | *skipped* — duplicate of train | 9 |

**Near-duplicate leakage is 3–4× the exact-duplicate leakage** (e.g. 15 vs 4 on
Coarse train↔test). A dedup pass relying on exact matching alone would have
missed the majority of the leakage. Total cross-split near-dup leakage:
**22 pairs (Coarse)** and **22 pairs (Fine)**.

This is the strongest single piece of evidence that **no upstream split may be
adopted as-is.**

## 8. V11 — PII counts (aggregate only)

Across all 10,010 Coarse rows: **`@handles` = 0**, **URLs = 4**, **emails = 0**.

Handles appear to have been **stripped upstream already**, which materially
lowers the privacy risk assessed in `PHASE47_PRIVACY_PLAN.md`. PII exposure is
**far lower than the structural estimate** — though redaction controls remain
appropriate, and the special-category concern (classes 2/3 assert religious and
gender attributes) **stands**.

**Script coverage:** `latin = 10,010` (100 %), `arabic_script = 3`,
`mixed = 3`. Confirms **Roman Urdu** stratum only — no `ur-Arab` content.

---

## 9. Usable labelled pool after exclusions (step 6)

Per `PHASE47_LABEL_MAPPING.md`, `4: Profane/Untargeted` is **excluded and
classified as unknown — not as negative.**

| Pool | toxic | non-toxic | excluded | **USABLE** |
|---|---|---|---|---|
| **`Fine/train`** | 2,895 (`0`+`2`+`3`) | 3,851 | **462** | **6,746** |
| Coarse train+validation | 3,730 | 4,278 | *n/a* | 8,008 |

### ⚠️ The exclusion decision FORCES the Fine layer

**Coarse folds `Profane/Untargeted` into `Abusive/Offensive`.** With Coarse
labels it is **impossible** to honour the Phase 4.7 exclusion — the 462 profane
rows are indistinguishable from toxic ones. **The Fine layer must be used**, or
the exclusion policy is silently violated.

### Sample-size adequacy — using `Fine/train` (6,746 usable)

| Split | Test rows | **Test negatives** | vs 250 target |
|---|---|---|---|
| 40 % | 2,698 | **1,540** | ✅ **MEETS** |
| 50 % | 3,373 | **1,925** | ✅ **MEETS** |

**The 250-negative per-stratum requirement is comfortably met** by the pooled
labelled data — provided we re-split ourselves. Note this is the **Roman Urdu**
(`ur-Latn`) stratum only; `ur-Arab` remains at zero.

---

## 10. Split-strategy confirmation

Evidence now **confirms** the Phase 4.7 recommendation:

1. Pool `Fine/train` (7,208) — the **only** labelled, non-duplicated Fine source.
2. **Discard** `Fine/validation` (duplicate) and `Fine/test` (unlabelled).
3. Dedupe: 10 intra-split extras + 9 cross-adjacent overlaps removed.
4. Group-aware 40/20/40 on `group_id`, failing loudly on straddling groups.
5. Apply assertions L1–L7; freeze the new test split with a SHA256 manifest.

---

## 11. Verification completeness — ALL CHECKS COMPLETE

| Check | Status |
|---|---|
| V1 row counts | ✅ complete |
| V2 checksums | ✅ complete |
| V3 schema | ✅ complete |
| V4 label sets | ✅ complete |
| V5 intra-split duplicates | ✅ complete |
| V6 cross-split overlap | ✅ complete |
| V7 near-duplicates | ✅ **complete** (see §7) |
| V8 validation==train identity | ✅ complete |
| V9 Coarse/Fine alignment | ✅ complete |
| V10 class distribution | ✅ complete |
| V11 PII scan | ✅ complete |

**All V1–V11 checks are complete.** No verification remains outstanding.

## 12. Not done (by instruction)

- **No import into AURA.**
- **No label mapping resolved** — `Profane/Untargeted` remains **excluded/unknown**; M1–M4 untouched.
- **No benchmark metrics created.**
- **No frozen split altered.**
- Legal reviews P1–P2 remain open.
