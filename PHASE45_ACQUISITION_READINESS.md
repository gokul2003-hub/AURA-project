# AURA Phase 4.5 — Urdu Data Acquisition Readiness

**Status: CANDIDATES IDENTIFIED & METADATA-VERIFIED — NO DATASET ACQUIRED.**

Network access **is** available (verified §1). Per the standing instruction
(*"do not download, purchase, or import any dataset without explicit
authorization"*), **nothing was downloaded, purchased or imported.** Only
authoritative **metadata** was read: the HuggingFace datasets API and each
dataset's `README.md`. No data file was fetched.

**The gate remains `NOT PASSED`** — for *both* script strata.

---

## 1. Network access — available and verified

| Probe | Result |
|---|---|
| DNS (`huggingface.co`, `github.com`, `pypi.org`, `opencode.ai`) | **all resolve** |
| TCP 443 to HF / GitHub / PyPI | **all reachable** |
| HTTPS GET `https://huggingface.co` | **HTTP 200 in 0.2 s** |
| HTTPS GET `https://api.github.com` | **HTTP 200 in 0.2 s** |
| Proxy | `ProxyEnable=0`, no env proxy set — **direct, unrestricted** |

> **Correction to Phase 4.4.** That phase concluded "no network access". That was
> **wrong**: the failure was in the *search-tool integration*, not the network.
> Raw connectivity was available throughout. Phase 4.4's blocker statement on
> this point is hereby retracted; its substantive conclusion (no *human-labelled,
> task-matched* data on disk) remains correct and was re-verified this phase.

No restriction was bypassed — none exists to bypass.

---

## 2. Candidates identified (metadata verified from the authoritative API)

75 unique datasets surfaced across 7 queries; 4 matched toxic/hate/abuse/offensive.

| # | Dataset | Licence | Script | Label definition | Size | Verdict |
|---|---|---|---|---|---|---|
| 1 | **`community-datasets/roman_urdu_hate_speech`** (RUHSOLD) | **MIT** | **Roman Urdu** | **Verified — see §3** | **10,010 rows** | **RECOMMENDED** |
| 2 | `hafiz-hassaan-saeed/Roman-Urdu-Toxic-Corpus` | CC-BY-4.0 | Roman Urdu | **NOT DOCUMENTED** (README = 30 B, licence line only) | 1 parquet | **NOT RECOMMENDED** |
| 3 | `Adnan855570/Urdu_Hate_Speech` | MIT | Urdu script | hate vs not_hate — **task-mismatched** | 300 used | **known; already in use** |
| 4 | `devzohaib/roman-urdu-HateSpeech` | AFL-3.0 | Roman Urdu | not documented; no description | — | **NOT RECOMMENDED** |

All four are `gated: false`, `private: false` — none requires an approval gate.

---

## 3. Verification of the recommended candidate

**`community-datasets/roman_urdu_hate_speech`** — read from its own dataset card:

| Field | Verified value |
|---|---|
| Licence | **MIT** |
| Annotation provenance | **`annotations_creators: expert-generated`** |
| Language provenance | `language_creators: crowdsourced`, `language: ur`, monolingual |
| Task | `text-classification`, `multi-class-classification` |
| Size | `1K < n < 10K`; download **730,720 B** (tiny) |
| Source | `original` |

**Splits (authoritative, from the card):**

| Config | train | test | validation |
|---|---|---|---|
| `Coarse_Grained` | 7,208 | **2,002** | 800 |
| `Fine_Grained` | 7,208 | **2,002** | 7,208 |

**Label definitions (authoritative):**

| Config | Classes |
|---|---|
| `Coarse_Grained` | `0: Abusive/Offensive`, `1: Normal` |
| `Fine_Grained` | `0: Abusive/Offensive`, `1: Normal`, `2: Religious Hate`, `3: Sexism`, **`4: Profane/Untargeted`** |

### Why this is a strong fit

`Fine_Grained` class **`4: Profane/Untargeted`** is precisely the
*ambient-profane-but-not-toxic* category that `PHASE44_ANNOTATION_SPEC.md §1.3`
identifies as the dominant false-positive zone — and `2: Religious Hate` /
`3: Sexism` map onto AURA's `identity_hate` dimension. The taxonomy is
structurally compatible with AURA's annotation policy.

### Why it is not yet sufficient

1. **`Abusive/Offensive` ≠ AURA `toxicity`.** It is *closer* than hate speech,
   and structurally better aligned, but the mapping still requires an explicit
   approved decision — it is not a drop-in replacement.
2. **It is Roman Urdu only.** No candidate anywhere provides **Urdu-script
   (Arabic) toxicity** data.
3. Its `Fine_Grained/validation` split (7,208) equals `train`, which looks like
   an upstream defect — must be confirmed before use.

### Sample-size adequacy — this is the important finding

Required per stratum (from `PHASE44_EVAL_PROTOCOL.md`): **≥ 200, recommended
250 test negatives.** RUHSOLD's test split is **2,002 rows**. Even at a
conservative 50 % non-toxic rate that is **≈ 1,000 test negatives** —
**roughly 4× the recommended minimum.** Subject to the §3 mapping decision,
RUHSOLD alone could satisfy the Roman Urdu stratum's statistical requirement
**without any annotation spend.**

---

## 4. Acquisition checklist

Complete **before** any download or import. A single unchecked row blocks.

| # | Check | RUHSOLD status |
|---|---|---|
| 1 | Licence name + version | ✅ **MIT** (verified, card + API) |
| 2 | Commercial use permitted | ✅ MIT permits |
| 3 | Redistribution permitted | ✅ MIT permits |
| 4 | Derivative labels permitted | ✅ MIT permits |
| 5 | **Human vs machine labels** | ✅ **expert-generated** |
| 6 | Annotator count / qualification | ⚠️ **not stated — query upstream** |
| 7 | Annotator compensation | ⚠️ **not stated — query upstream** |
| 8 | Consent / PII | ⚠️ **tweets — must assess before use** |
| 9 | Collection methodology documented | ⚠️ partial — card exists, needs full read |
| 10 | **Label definitions published** | ✅ **verified above** |
| 11 | Roman Urdu coverage | ✅ **native Roman Urdu, not transliterated** |
| 12 | Source URL + retrieval date | ✅ `huggingface.co/datasets/community-datasets/roman_urdu_hate_speech` |
| 13 | Stable snapshot hash | ⬜ **record SHA256 at acquisition** |

**Items 6, 7, 8 and 9 are unresolved and must be answered before import** —
particularly **#8**, since the source is public social-media text.

---

## 5. Human-annotation execution plan (if acquisition is declined)

Full plan lives in `PHASE44_ANNOTATION_SPEC.md` and `PHASE44_EVAL_PROTOCOL.md`.
Condensed:

1. Approve label definitions (κ ≥ 0.70 pilot gate).
2. Bilingual guidelines with worked examples for quoting, negation, reclaimed slurs.
3. Pilot 50 items across both strata; revise if κ < 0.70.
4. **2 independent annotators + third-reviewer adjudication**, 1:1 balance.
5. Target **≈ 2,500 items** (625 negatives/stratum ÷ 40 % test split) — or
   **≈ 1,250** if RUHSOLD supplies the Roman Urdu stratum, leaving only the
   Urdu-script stratum to annotate.
6. Dedupe (exact + trigram Jaccard ≥ 0.80) **before** splitting; group-aware
   split that fails loudly on a straddling `group_id`; assertions L1–L7.
7. Freeze test split, hash manifest, single evaluation, per-stratum reporting.

**Partial-acquisition option:** buy/authorise nothing yet, but note that
acquiring RUHSOLD would cut the annotation budget by roughly **half** by
eliminating the Roman Urdu stratum.

---

## 6. Remaining blockers

| Blocker | Detail |
|---|---|
| **No authorization to acquire** | Network works; **permission does not exist**. Nothing downloaded. |
| **No Urdu-script toxicity corpus** | Every candidate is Roman Urdu or hate-speech. **This stratum has no acquisition path yet.** |
| **Task mapping unapproved** | `Abusive/Offensive` → AURA `toxicity` needs an explicit decision. |
| **Unresolved provenance items** | Annotator count/compensation, PII assessment, collection methodology. |
| **Gate `NOT PASSED`** | Both strata unmeasured against 0.15 on a frozen, appropriate test set. |
| **`Roman-Urdu-Toxic-Corpus` undocumented** | CC-BY-4.0 but a 30-byte README — label definitions unverifiable; fails checklist #10. |

---

## 7. The exact next user decision

**Authorise acquisition of `community-datasets/roman_urdu_hate_speech` (MIT,
expert-generated, 10,010 rows), AND approve the label mapping from
`Abusive/Offensive` + `Normal` to AURA's binary `toxic` — treating
`Profane/Untargeted` as non-toxic per `PHASE44_ANNOTATION_SPEC.md §1.3`.**

Separately: **decide how the Urdu-script (Arabic) stratum will be sourced** —
no toxicity-labelled Urdu-script corpus was found, so that stratum will require
commissioned annotation regardless.

Until both are authorised, the gate stays **`NOT PASSED`** and nothing is
imported.

**No frozen split, threshold, benchmark hash, database record or model was
created, modified or deleted. Production remains on `legacy`.**
