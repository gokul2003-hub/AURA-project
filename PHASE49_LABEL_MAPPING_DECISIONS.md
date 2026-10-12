# AURA Phase 4.9 — M1–M4 Label Mapping Decision Table (RUHSOLD Fine-grained)

**Status: PREPARED FOR APPROVAL — nothing here is approved.**
Only the user or an authorised reviewer can approve. **No data was imported, no
metric computed, no threshold tuned, no frozen split changed.**

Source of counts: `PHASE48_SCRATCH_VERIFICATION.md §5` (`Fine/train`, n = 7,208,
measured — not projected).

---

## 1. AURA's actual taxonomy (target)

`DATASET_GUIDE.md:35,38` — `toxic` is the **binary headline**; five secondary
dimensions: `severe_toxic, obscene, threat, insult, identity_hate`.

## 2. RUHSOLD's schema (source)

**Single label column** `['tweet', 'label']`. One integer per row — no
multi-label head. This is the binding constraint on everything below.

---

## 3. M1–M4 decision table

| ID | RUHSOLD class | Rows | → AURA `toxic` | Secondary dimension | Semantic fit | Confidence | Status |
|---|---|---|---|---|---|---|---|
| **M1a** | `1: Normal` | **3,851** | **0** (`non_toxic`) | — | **High** — "Normal / inoffensive" aligns directly | High | **PENDING** |
| **M1b** | `0: Abusive/Offensive` | **1,729** | **1** (`toxic`) | *none assignable* | **Medium-High** — "abusive/offensive" ≈ AURA "rude, disrespectful or unreasonable", but is not the same construct | Medium-High | **PENDING** |
| **M2a** | `2: Religious Hate` | **563** | **1** (`toxic`) | **`identity_hate`** | **High** — attack by religious identity | High | **PENDING** |
| **M2b** | `3: Sexism` | **603** | **1** (`toxic`) | **`identity_hate`** | **High** — attack by gender | High | **PENDING** |
| **M3** | **`4: Profane/Untargeted`** | **462** | **EXCLUDED → `unknown`** | — | **Ambiguous** — see §4 | n/a | **PENDING (recommend: confirm exclusion)** |
| **M4** | — | — | Accept that **only the binary headline** is evaluable | — | Structural | n/a | **PENDING** |

### Resulting pool if all of M1–M3 are approved as recommended

| Class | Rows | Treatment |
|---|---|---|
| toxic (`0`+`2`+`3`) | **2,895** | verified positive |
| non-toxic (`1`) | **3,851** | verified negative |
| **excluded (`4`)** | **462** | **unknown — not counted** |
| **USABLE** | **6,746** | of 7,208 |

---

## 4. M3 — `Profane/Untargeted` remains EXCLUDED (default, unchanged)

Per instruction it stays **unknown/excluded**. AURA's definition — *"rude,
disrespectful or unreasonable in a way likely to make a person leave the
conversation"* — **does not require a target**, so untargeted profanity
straddles the boundary and a blanket rule either way would distort semantics.

**Hard rule, restated:** excluded items are **never** counted as verified
non-toxic. Counting them as negatives would deflate the measured FPR and could
manufacture a gate pass. The 462 rows are held with
`mapping_status = excluded_pending_adjudication`.

**Consequence already established (Phase 4.8 §9):** Coarse labels fold class 4
into `Abusive/Offensive`, so **the Fine layer must be used** or the exclusion is
silently violated.

---

## 5. What CAN and CANNOT be evaluated (M4)

### Can support binary toxicity evaluation ✅
- **Headline `toxic` only**, on the 6,746 usable rows.
- `identity_hate` is recoverable **only** for classes 2 and 3 — and **only as a
  co-occurring flag**, not as an independently annotated dimension.

### Cannot be recovered from RUHSOLD ❌

| AURA dimension | Recoverable? | Why |
|---|---|---|
| `severe_toxic` | **NO** | no severity axis in a single label |
| `obscene` | **NO** | not annotated |
| `threat` | **NO** | not annotated |
| `insult` | **NO** | not annotated |
| `identity_hate` (classes 0, 1, 4) | **NO** | only implied for 2/3 |

**Any category-level metric derived from RUHSOLD would be fabricated.** Only the
binary headline is valid. This is a structural limit, not a processing choice.

---

## 6. Label-quality caveats the approver should see

| Caveat | Detail |
|---|---|
| **1-row layer disagreement** | Coarse abusive 3,358 vs Fine (0+2+3+4) 3,357; Coarse normal 3,850 vs Fine normal 3,851. The two label layers are **not perfectly consistent**. |
| **Single-label granularity** | `Abusive/Offensive` bundles a wide severity range into one class. |
| **Upstream splits unusable** | `test` unlabelled, `validation` a duplicate, cross-split leakage present (Phase 4.8 §7). **Re-splitting after dedup is mandatory.** |
| **Task proximity, not identity** | `Abusive/Offensive` is *closer* to toxicity than the hate-speech framing, but remains a proxy. |

---

## 7. Decision register

| ID | Decision | **Only the approver can set this** |
|---|---|---|
| **M1** | Approve `Normal → non_toxic` and `Abusive/Offensive → toxic` | **PENDING** |
| **M2** | Approve `Religious Hate`/`Sexism` → `toxic` + `identity_hate` | **PENDING** |
| **M3** | **Confirm exclusion** of `Profane/Untargeted` as unknown (recommended), *or* approve adjudication | **PENDING** |
| **M4** | Accept that **only the binary headline** is evaluable from RUHSOLD | **PENDING** |

**No item is marked approved. Documentation is not approval.**
