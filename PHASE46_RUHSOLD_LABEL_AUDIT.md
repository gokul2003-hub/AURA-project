# AURA Phase 4.6 — RUHSOLD Label Audit

**Dataset:** `community-datasets/roman_urdu_hate_speech` (RUHSOLD)
**Status: AUDIT COMPLETE — NOT APPROVED FOR IMPORT.** No data file was
downloaded, imported or persisted. Only the datasets API and the `README.md`
(7,821 B) were read.

---

## 1. VERIFIED metadata (authoritative sources)

| Item | Verified value | Source |
|---|---|---|
| Licence | **MIT** | API `license:mit`; README *"under MIT License"* |
| Gated / private | **False / False** | API |
| Last modified | 2024-06-24 | API |
| Files | 6 parquet + `README.md` + `.gitattributes` | API siblings |
| Provenance | **peer-reviewed EMNLP 2020**, Rizwan, Shakeel & Karim, **LUMS** | README + bibtex |
| Homepage | `aclanthology.org/2020.emnlp-main.197/` | README |
| Point of contact | M. Haroon Shakeel, LUMS | README |
| **Annotators** | **three independent annotators**, conflicts by **majority vote** | README *Data Fields* |
| Annotator expertise | *"annotated by experts in the relevant language"* | README *Summary* |
| Sampling | random sample of **10,000** from a **50,000**-tweet base | README *Data Fields* |
| Download size | **730,720 B** (Coarse) | YAML `download_size` |
| Script | **Roman Urdu**, BCP-47 `ur`, monolingual | README *Languages* |

**This resolves two previously-open checklist items:**
- ✅ **#6 annotator count/qualification → 3 expert annotators.**
- ✅ **#5 human vs machine → human, expert, 3-way majority vote.**

## 2. UNVERIFIED claims

| Claim | Status |
|---|---|
| **PII / sensitive information** | **NOT DOCUMENTED** — README says *"[More Information Needed]"* |
| Collection methodology beyond "random 10k of 50k" | **NOT DOCUMENTED** |
| Source language producers | **NOT DOCUMENTED** |
| Curation rationale | **NOT DOCUMENTED** |
| Discussion of biases | **NOT DOCUMENTED** |
| Other known limitations | **NOT DOCUMENTED** |
| Annotator compensation | **NOT DOCUMENTED** |
| Empirical duplicate/near-duplicate overlap | **NOT VERIFIED — requires download authorization** |
| Whether the shipped parquet matches the card | **NOT VERIFIED — requires download authorization** |

## 3. Row counts — consistent, with a minor discrepancy

YAML sums to **10,010** (7,208 + 2,002 + 800), matching the 10,010 I reported in
Phase 4.5. The prose instead states **7,209 / 2,003 / 801 = 10,013**.

**Δ = 3 rows** between the narrative and the machine-readable block. Immaterial
to the gate, but it means **the card is internally inconsistent** and the
parquet must be treated as the only authority once authorised.

---

## 4. ⚠️ CRITICAL FINDING A — the split names are SWAPPED

The README's **prose** and its **machine-readable YAML** disagree about which
split is which:

| Prose (*Data Splits*) | YAML (*dataset_info*) |
|---|---|
| *"split … with **70,20,10** split ratio"* | consistent with 70/20/10 |
| Train **7,209** | `train` **7,208** |
| **Valid 2,003** (the 20 % split) | **`test` 2,002** (the 20 % split) |
| **Test 801** (the 10 % split) | **`validation` 800** (the 10 % split) |

**The 20 % split is called `validation` by the authors and `test` by the loader.**
The 10 % split is called `test` by the authors and `validation` by the loader.

**Consequence — this is a genuine methodological trap.** Adopting the YAML
`test` split as our held-out evaluation set would mean evaluating on the split
the **authors themselves designed as validation data**. That is precisely the
kind of silent leakage `PHASE44_EVAL_PROTOCOL.md §4.3` exists to prevent.
**No split may be designated as our frozen test set until this is resolved.**

## 5. ⚠️ CRITICAL FINDING B — `Fine_Grained/validation` IS `train`

Card metadata, identical to the byte:

| Config | train | validation |
|---|---|---|
| `Fine_Grained` | num_bytes **723,666**, num_examples **7,208** | num_bytes **723,666**, num_examples **7,208** |

Byte count **and** row count are identical. `Coarse_Grained/validation`, by
contrast, is a distinct 79,755 B / 800 rows.

**`Fine_Grained/validation` is a duplicate of `train` and is UNUSABLE** for
selection or evaluation. This is an upstream defect, already visible from
metadata alone.

## 6. Which split can be trusted?

| Split | Trust | Reason |
|---|---|---|
| `Fine_Grained/validation` | ❌ **UNUSABLE** | byte-identical to `train` |
| `Coarse_Grained/validation` (800) | ⚠️ plausible, **unverified** | distinct size; no empirical check permitted |
| YAML `test` / prose `Valid` (2,002) | ❌ **not yet usable** | authors treat it as *validation* (Finding A) |
| YAML `validation` / prose `Test` (800) | ⚠️ **candidate**, unverified | the authors' true held-out set, but only 800 rows |

**Honest verdict: NO split can currently be certified for evaluation.** The
authors' genuine test split appears to be the **801-row** one — which yields
only **≈ 400 negatives at best, and likely ~200–400**, marginal against the
**250**-negative target in `PHASE44_EVAL_PROTOCOL.md §2`. This materially
weakens the Phase 4.5 claim that RUHSOLD alone satisfies the sample-size gate:
the 2,002-row split that would have done so is the one the authors call
*validation*.

Empirical duplicate and near-duplicate verification (Jaccard ≥ 0.80) **requires
downloading the parquet — not authorised**, and therefore **not performed**.

## 7. Label mapping — semantic-distortion analysis

| Class | Maps to AURA | Verdict |
|---|---|---|
| `1: Normal` | `non_toxic` | ✅ clean |
| `0: Abusive/Offensive` | `toxic` | ✅ reasonable — "abusive/offensive" ≈ AURA's "rude, disrespectful" |
| `2: Religious Hate` | `toxic` (`identity_hate`) | ✅ clean |
| `3: Sexism` | `toxic` (`identity_hate`) | ✅ clean |
| **`4: Profane/Untargeted`** | **AMBIGUOUS** | ⚠️ **requires adjudication — see below** |

### ⚠️ Revision of my own Phase 4.5 recommendation

Phase 4.5 recommended mapping **`Profane/Untargeted` → non-toxic**. **That was
too hasty and I withdraw it.** Per Task 1.5, profane language is **not**
non-toxic in every context.

AURA's definition is *"rude, disrespectful or unreasonable in a way likely to
make a person leave the conversation."* Untargeted profanity sits astride that
line: *"what a f***ing mess"* is profane but ambient, while heavy profanity can
still be rude and exclusionary **without** naming a target. A blanket rule in
either direction introduces **semantic distortion** — the exact failure this
audit exists to catch.

**Proposed adjudication policy (requires approval):**
- `Profane/Untargeted` is **excluded from the headline binary mapping by
  default** and routed to adjudication.
- Adjudicator applies AURA's definition verbatim; **targeting is not required**
  for toxicity, only for the `identity_hate` category.
- Items are recorded with `mapping_confidence`; low-confidence items are
  **excluded from gate metrics** rather than force-labelled.
- The chosen treatment (exclude vs adjudicate-to-label) must be **frozen before
  any scoring**, and reported with the result.

**Because this is unresolved, no performance metric is reported in this phase** —
per Task 1.8.

## 8. PII / privacy assessment (Task 1.7)

Source is **public social-media text (Twitter/X)**. Inherently present: handles,
@mentions, URLs, display names, and quoted third parties.

**Aggravating factor:** upstream's *Personal and Sensitive Information* section
is **"[More Information Needed]"** — the authors performed **no** PII assessment.
We cannot rely on upstream handling.

**Required controls before any import:**

| Control | Requirement |
|---|---|
| **Minimization** | Strip @handles, URLs, and user IDs at ingest; store a derived `text_hash`, not the raw handle |
| **Redaction** | Regex pass for handles/URLs/emails/phone numbers, plus human spot-check |
| **Retention** | Time-bounded; deletion schedule defined and approved |
| **Access** | Role-restricted; no production log emission of raw text |
| **Aggregation** | Reports expose **counts only** — never raw rows |
| **Provenance** | Per-row `source_url` + retrieval date + snapshot SHA256 |
| **Legal basis** | Confirm MIT covers the *tweets* (the repo is MIT; the underlying tweet content's status needs review) |

⚠️ Note: the paper's own example row contains an ethnic/religious slur
reference. Handling such content requires annotator wellbeing provisions too.

## 9. Decisions requiring approval

1. **Split designation** — accept that the authors' true test set is the 801-row
   split, or accept evaluating on the 2,002-row split with the leakage caveat
   explicitly documented. **Blocks everything downstream.**
2. **`Profane/Untargeted` treatment** — exclude, or adjudicate-to-label.
3. **PII controls** — approve the table in §8.
4. **Download authorization** — required before any empirical duplicate or
   integrity verification can be performed.

## 10. Blockers

| Blocker | Detail |
|---|---|
| **Split-name swap** | no trustworthy held-out split identified yet |
| **`Fine_Grained/validation` == `train`** | unusable |
| **True test split too small?** | 801 rows → ~200–400 negatives vs 250 target |
| **`Profane/Untargeted` unresolved** | semantic-distortion risk in either direction |
| **No PII assessment upstream** | must be built from scratch |
| **Empirical verification blocked** | download not authorised |

**No performance metrics are reported: mapping and split integrity are not yet
approved.**

**No production file, threshold, benchmark artifact, frozen split or model was
created, modified or deleted.**
