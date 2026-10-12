# AURA Phase 4.7 — Final Report

**Outcome: all four plans complete. NOTHING DOWNLOADED, IMPORTED, PURCHASED,
ANNOTATED or DEPLOYED. Both gates remain `NOT PASSED`.**

15:47:42 → 15:51:36 (**~3.9 min**, within the 5-minute window).

Deliverables: `PHASE47_SPLIT_VERIFICATION_PLAN.md`, `PHASE47_LABEL_MAPPING.md`,
`PHASE47_PRIVACY_PLAN.md`, this report.

---

## Step 1 — Upstream split metadata

Documented exactly as published. **Three independent inconsistencies:**

| Size band | Prose (*Data Splits*) | YAML (`dataset_info`) |
|---|---|---|
| 70 % | Train 7,209 | `train` 7,208 |
| 20 % | **Valid 2,003** | **`test` 2,002** |
| 10 % | **Test 801** | **`validation` 800** |

1. **Name swap** — the 20 % split is *validation* to the authors, `test` to the
   loader. Purpose is **not** inferable from the filename, per instruction.
2. **Totals conflict** — YAML 10,010; prose 10,013; *Data Fields* says
   **"select 10000 tweets"**. Both exceed 10,000.
3. **`Fine_Grained/validation` == `train`** — identical 723,666 B / 7,208 rows.
   **Unusable**, on metadata evidence alone.

**Download NOT requested as executed — it is requested as an approval (A1)** for
6 parquet files (≈ 1.93 MB) to a **scratch location outside the project tree**.
**V1–V11 verification is specified and blocked pending A1.** It covers row
counts, checksums, schema, label set, intra-split duplicates, **cross-split
overlap across every pair**, trigram near-dupes, the validation==train
confirmation, Coarse/Fine alignment, class distribution and a PII scan.

**Split strategy recommendation: do not adopt any upstream split.** The
authors' true test split (801 rows → ~200–400 negatives) is below the 250
target; the 2,002-row split is their validation set and is explicitly not to be
used as an independent test set. Recommended: pool `train` + the 2,002-row
split, quarantine the 801-row set, dedupe, then **group-aware 40/20/40** with a
frozen SHA256 manifest. The ~1,470-negatives projection is stated as a
**projection, not a measurement**.

## Step 2 — Label mapping

| RUHSOLD | → AURA `toxic` | Confidence |
|---|---|---|
| `1: Normal` | **0** | High |
| `0: Abusive/Offensive` | **1** | Medium-High |
| `2: Religious Hate` | **1** + `identity_hate` | High |
| `3: Sexism` | **1** + `identity_hate` | High |
| **`4: Profane/Untargeted`** | **EXCLUDED** | unresolved |

**Critical limitation:** RUHSOLD has a **single label column**, so
`severe_toxic`, `obscene`, `threat` and `insult` **cannot be recovered**. Only
the **binary headline** is evaluable; any category-level metric from this source
would be fabricated.

**`Profane/Untargeted` is excluded by default** — and explicitly **NOT counted
as verified negatives**. An excluded item is *unknown*, not *negative*;
counting exclusions as negatives would deflate the measured FPR and could
manufacture a gate pass. Excluded rows are retained with
`mapping_status = excluded_pending_adjudication`. Exclusion **shrinks the usable
pool**, so the 250-negative projection must be recomputed after V10.

## Step 3 — Privacy and licensing

**MIT is necessary but NOT sufficient.** It licenses the *curators'* artefact;
it does **not** resolve rights in the **underlying tweets**, data-protection
lawful basis, platform ToS, or erasure obligations. Upstream performed **no**
PII assessment (*"[More Information Needed]"*).

Controls specified: **minimization** (salted `text_hash` as join key, never
store handles); **redaction** at ingest (`[USER]`/`[URL]`/`[EMAIL]`/`[PHONE]`,
regex **plus human spot-check**, applied **before dedup** and versioned so V5–V7
reproduce); **role-restricted access** with **aggregate-counts-only reporting**;
**time-bounded retention** with a cascade-capable erasure procedure; per-row
provenance plus a `licence_scope_note` recording MIT's limits.

⚠️ Flagged: class membership itself asserts **special-category** attributes
(Religious Hate, Sexism), and the paper's own example contains a slur — hence
mandatory annotator wellbeing provisions.

## Step 4 — Urdu-script commissioning specification

≈ **1,250 items**, `ur-Arab`, 1:1 balanced, 8 categories per
`PHASE44_ANNOTATION_SPEC.md §1.4`, with the **625 non-toxic** items as the
critical path. **3 native Urdu-script annotators** + senior adjudicator,
**κ ≥ 0.70** per category, calibration quiz, wellbeing provisions, and
**compensation requiring explicit approval** (fair hourly, not per-label).
Commissioned text preferred over scraped text to eliminate third-party PII.

## Step 5 — Safeguards

| Check | Result |
|---|---|
| **Production engine** | **`legacy`** |
| `tuned_threshold.json` | `f31f4975d29a151f…` **UNCHANGED** |
| `phase2_benchmark.json` | `5a9d94e267806ea0…` **UNCHANGED** |
| `phase3_benchmark.json` | `f3a5ceb488f4a9ad…` **UNCHANGED** |
| Frozen `ur_test` / `ur_val` | **UNCHANGED** |
| SQLite `integrity_check` / `foreign_key_check` | **ok** / **clean** |
| Rows / splits | **596**; **137 / 29 / 31 + 399 unassigned** |
| `training_runs` / `model_versions` | **8 / 12** |
| Active model | `improved_v10` |
| Downloaded / imported / purchased / annotated / deployed | **NONE** |
| Working-tree changes preserved | **yes** (23 phase `.md` files intact) |
| Production code modified | **none** |
| Raw PII in any log or report | **none** |

## Approvals required

| # | Item | Status |
|---|---|---|
| **A1** | Download 6 parquet files (≈ 1.93 MB) to scratch | **PENDING — blocks V1–V11** |
| **A2** | Split-strategy recommendation | PENDING |
| **M1–M4** | Label mappings; **`Profane/Untargeted` exclusion**; accept binary-only evaluation | PENDING |
| **P1–P2** | **Legal review of MIT vs underlying tweet rights; lawful basis** | **PENDING — blocks import** |
| P3–P5 | Redaction, retention, access controls | PENDING |
| **C1** | **`ur-Arab` commissioning** + annotator compensation | PENDING |

## Blockers

| Blocker | Impact |
|---|---|
| No download authorization | V1–V11 unexecuted; overlap/duplication unknown |
| Split-name swap | no trustworthy Roman Urdu held-out split |
| `Fine_Grained/validation` == `train` | that split unusable |
| True test split possibly too small | 801 rows may miss the 250-negative target |
| `Profane/Untargeted` unresolved | usable pool shrinks; projection stale |
| MIT does not clear tweet rights | legal review required before import |
| No upstream PII assessment | controls built from scratch |
| No `ur-Arab` corpus | full annotation required |

**Both quality gates remain `NOT PASSED`.** Roman Urdu is unverified;
Urdu-script is unmeasured. **No metric was reported this phase**, because
neither mapping nor split integrity is approved. Production remains on `legacy`
and requires separate deployment approval.
