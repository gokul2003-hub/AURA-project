# AURA Phase 4.7 — RUHSOLD Split Verification Plan

**Status: PLAN COMPLETE — DOWNLOAD NOT AUTHORISED, VERIFICATION NOT PERFORMED.**

No dataset file was fetched. This document specifies the verification that must
run **once authorization is granted**. Per instruction, no split's purpose is
inferred from its filename.

---

## 1. Upstream metadata — exactly as published

### 1.1 Machine-readable YAML (`dataset_info`, verbatim)

| Config | `train` | `test` | `validation` | `download_size` |
|---|---|---|---|---|
| `Coarse_Grained` | 725,715 B / **7,208** | 202,318 B / **2,002** | 79,755 B / **800** | **730,720 B** |
| `Fine_Grained` | 723,666 B / **7,208** | 203,590 B / **2,002** | **723,666 B / 7,208** | 1,199,660 B |

### 1.2 Narrative prose (*Data Splits*, verbatim)

> *"The data is split in train, test, and validation sets with **70,20,10** split
> ratio using stratification based on fine-grained labels."*
>
> `Train Valid Test` / `7209 2003 801`

### 1.3 The conflict

| Size band | Prose name | YAML name | Rows (prose / YAML) |
|---|---|---|---|
| **70 %** | Train | `train` | 7,209 / 7,208 |
| **20 %** | **Valid** | **`test`** | 2,003 / 2,002 |
| **10 %** | **Test** | **`validation`** | 801 / 800 |

**Two independent inconsistencies:**

1. **Name swap.** The 20 % split is *validation* to the authors and `test` to
   the loader. The 10 % split is *test* to the authors and `validation` to the
   loader. **Purpose cannot be inferred from the filename** — the two sources
   directly contradict.
2. **Totals exceed the stated sample.** YAML sums to **10,010**; prose sums to
   **10,013**; yet *Data Fields* states **"select 10000 tweets"**. Both totals
   exceed 10,000 by 10–13 rows. The card is internally inconsistent on all
   three points.

### 1.4 Already-detectable defect

`Fine_Grained/validation` reports **723,666 B / 7,208 rows — byte-for-byte
identical to `Fine_Grained/train`.** That split is **unusable** for selection or
evaluation, on metadata evidence alone.

---

## 2. Approval gate — NOT YET GRANTED

**No download has occurred and none will without explicit authorisation.**

Requested authorisation covers: fetching the 6 parquet files (≈ 1.93 MB total
across both configs), written to a **scratch location outside the project tree**,
never into `CODE/BACKEND/data/`.

---

## 3. Post-approval verification procedure

To be executed as a throwaway script in `%TEMP%`, printing **aggregate
statistics only — never raw rows** (see `PHASE47_PRIVACY_PLAN.md`).

| # | Check | Method | Pass condition |
|---|---|---|---|
| V1 | **Row counts** | parquet metadata per file | matches YAML §1.1 within Δ 3; discrepancy recorded |
| V2 | **Checksums** | SHA256 per parquet | recorded in the provenance manifest |
| V3 | **Schema** | column names + dtypes | exactly `tweet: string`, `label: class_label` |
| V4 | **Label set** | distinct labels per config | Coarse `{0,1}`; Fine `{0,1,2,3,4}` — no nulls |
| V5 | **Intra-split duplicates** | NFKC-normalised exact match | count reported per split |
| V6 | **Cross-split overlap** | normalised exact match, **every pair** (train↔test, train↔val, test↔val) | count reported per pair |
| V7 | **Near-duplicates** | char-trigram **Jaccard ≥ 0.80**, every cross-split pair | count reported per pair |
| V8 | **`Fine_Grained/validation` vs `train`** | direct content equality | expected **IDENTICAL** — confirms the defect |
| V9 | **Coarse vs Fine alignment** | whether the two configs label the same tweet set | determines if they are independent datasets |
| V10 | **Class distribution** | per split, per config | recorded; imbalance flagged |
| V11 | **PII scan** | regex `@\w+`, `https?://`, emails, phone patterns | **counts only**; see `PHASE47_PRIVACY_PLAN.md` |

V6/V7 are decisive: if the 2,002-row split overlaps the 7,208-row train split,
it cannot serve as any form of held-out set regardless of its name.

---

## 4. Defensible split strategy — recommendation

**Do not adopt any upstream split as our test set.** Reasons:

- The authors' genuine test split (801 rows) yields only **~200–400 negatives**,
  below the **250**-negative target in `PHASE44_EVAL_PROTOCOL.md §2`.
- The 2,002-row split is the authors' **validation** set; using it as an
  independent test set is explicitly forbidden by this phase's instructions and
  would be methodologically unsound.
- `Fine_Grained/validation` is a copy of `train`.

**Recommended strategy — rebuild the split ourselves, once:**

1. Pool the **union** of upstream `train` + the 2,002-row split (i.e. everything
   that is *not* the authors' 801-row test set and *not* the duplicated
   `Fine_Grained/validation`).
2. Keep the authors' **801-row test set quarantined and unused** — it is the only
   upstream split with a defensible claim to independence, but it is too small
   to gate on.
3. Apply **dedupe before splitting** (normalised exact + trigram Jaccard ≥ 0.80).
4. **Group-aware split** on `group_id`, ratio **40 / 20 / 40**, asserting no
   group straddles splits (routine must fail loudly).
5. Verify assertions **L1–L7** from `PHASE44_EVAL_PROTOCOL.md §4.4`.
6. Freeze the new test split with a **SHA256 manifest** before any scoring.

**Consequence, stated plainly:** if verification shows the pooled usable corpus
is ~9,200 rows (7,208 + 2,002) with ~40 % non-toxic, a 40 % test split yields
**~1,470 test negatives** — comfortably above the 250 target. **This is a
projection, not a measurement**; it depends entirely on V5/V6/V7 outcomes and on
the label-mapping decision in `PHASE47_LABEL_MAPPING.md`.

---

## 5. Explicit prohibitions observed

- The 2,002-row authors' validation split will **not** be used as an independent
  test set.
- No split's purpose is taken from its filename.
- No download, import or persistence in the project tree without authorisation.
- No performance metrics are reported this phase — mapping and split integrity
  are unapproved.

## 6. Approvals required

| # | Approval | Status |
|---|---|---|
| A1 | **Download the 6 parquet files to scratch** (≈ 1.93 MB) | **PENDING — blocks V1–V11** |
| A2 | Split-strategy recommendation in §4 | pending |
| A3 | Label mapping (`PHASE47_LABEL_MAPPING.md`) | pending |
| A4 | Privacy controls (`PHASE47_PRIVACY_PLAN.md`) | pending |
