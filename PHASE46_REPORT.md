# AURA Phase 4.6 — Final Report

**Outcome: audit and planning complete. NOTHING IMPORTED. Two critical
defects found in RUHSOLD that invalidate the Phase 4.5 recommendation.**

15:31:25 → 15:36:27 (**~5.0 min**, at the window boundary).

Deliverables: `PHASE46_RUHSOLD_LABEL_AUDIT.md`, `PHASE46_URDU_SCRIPT_COLLECTION_PLAN.md`, this report.

---

## 1. Two critical findings that change the plan

### ⚠️ A. RUHSOLD's split names are SWAPPED

The README's **prose** and its **machine-readable YAML** disagree:

| Prose (*Data Splits*) | YAML (*dataset_info*) |
|---|---|
| Train 7,209 | `train` 7,208 |
| **Valid 2,003** ← the 20 % split | **`test` 2,002** ← the 20 % split |
| **Test 801** ← the 10 % split | **`validation` 800** ← the 10 % split |

**The split the authors designed as *validation* is served to loaders as `test`.**
Adopting YAML `test` as our held-out set would evaluate on the authors'
validation data — exactly the silent leakage `PHASE44_EVAL_PROTOCOL.md §4.3`
exists to prevent.

### ⚠️ B. `Fine_Grained/validation` IS `train`

Byte count **and** row count are identical (723,666 B / 7,208 rows).
**`Fine_Grained/validation` is unusable.** Visible from metadata alone; an
upstream defect.

### Consequence — a correction to Phase 4.5

Phase 4.5 claimed RUHSOLD's 2,002-row split would give ≈ 1,000 test negatives,
~4× the requirement, making annotation unnecessary. **That claim is withdrawn.**
The 2,002-row split is the authors' *validation* set. Their genuine test split
is **801 rows → ~200–400 negatives**, which is **marginal against the 250
target**. RUHSOLD may still be useful, but it does **not** by itself discharge
the Roman Urdu stratum.

## 2. Task 1 — RUHSOLD verified

**Verified (API + full 7,821 B README):** licence **MIT**; **peer-reviewed EMNLP
2020** (Rizwan, Shakeel, Karim — LUMS); **three independent expert annotators**,
conflicts by **majority vote**; Roman Urdu, BCP-47 `ur`; 730,720 B; not gated.
This **resolves** previously-open checklist items #5 (human labels) and
#6 (annotator count/qualification).

**Row counts:** YAML sums to **10,010**, matching my Phase 4.5 figure. Prose
states 10,013. **Δ 3 rows** — the card is internally inconsistent; the parquet is
the only authority once authorised.

**Unverified / not documented upstream:** PII (**"[More Information Needed]"** —
the authors performed **no** PII assessment), collection methodology, source
producers, curation rationale, biases, limitations, annotator compensation.

### Label mapping — semantic-distortion analysis

`Normal → non_toxic`, `Abusive/Offensive → toxic`, `Religious Hate → toxic`,
`Sexism → toxic` are all defensible.

**`4: Profane/Untargeted` is genuinely ambiguous — and I withdraw my Phase 4.5
recommendation to map it to non-toxic.** Per Task 1.5, profane language is not
non-toxic in every context: AURA's definition ("rude, disrespectful or
unreasonable…") does not require a *target*. A blanket rule in either direction
introduces semantic distortion. **Proposed:** exclude from the headline mapping
by default, route to adjudication, record `mapping_confidence`, and exclude
low-confidence items from gate metrics rather than force-label.

**Per Task 1.8, no performance metrics are reported** — mapping and split
integrity are not approved.

### PII (Task 1.7)
Source is public Twitter/X text with handles, @mentions and URLs, and **upstream
performed no PII assessment**. Required before import: strip handles/URLs at
ingest, store `text_hash` not raw handles, regex + human redaction pass,
time-bounded retention, role-restricted access, counts-only reporting, and legal
review of whether MIT covers the underlying tweets.

## 3. Task 2 — Urdu-script (`ur-Arab`) collection plan

**No Urdu-script toxicity corpus exists** — all candidates were Roman Urdu or
hate-speech. This stratum **must be commissioned**.

Sizing (from `PHASE44_EVAL_PROTOCOL.md §2`, verified): **250 test negatives**
(min 200) → ÷ 40 % test split = 625 negatives → **≈ 1,250 items at 1:1 balance**.

The **625 non-toxic** items are the critical path since the gate is FPR-driven;
borderline/quoted/negated/context-dependent rows are deliberately over-sampled
within the non-toxic half. Workforce: **3 independent native Urdu-script
annotators** + senior adjudicator, **κ ≥ 0.70** acceptance per category,
calibration quiz, **compensation requiring explicit approval**, and wellbeing
provisions for slur exposure. **Commissioned text is preferred over scraped
text** to eliminate third-party PII entirely.

## 4. Safeguards — all held

| Check | Result |
|---|---|
| **Production engine** | **`legacy`** |
| `tuned_threshold.json` | `f31f4975d29a151f…` **UNCHANGED** |
| `phase2_benchmark.json` | `5a9d94e267806ea0…` **UNCHANGED** |
| `phase3_benchmark.json` | `f3a5ceb488f4a9ad…` **UNCHANGED** |
| Frozen Urdu splits | `ur_test` `f18d80f3…` / `ur_val` `8727f2ba…` **UNCHANGED** |
| SQLite `integrity_check` / `foreign_key_check` | **ok** / **clean** |
| Rows / splits | **596**; **137 / 29 / 31 + 399 unassigned** |
| `training_runs` / `model_versions` | **8 / 12** |
| Active model | `improved_v10` |
| **Dataset imported or downloaded** | **NONE** — mtime sweep over `data/` clean |
| Production code modified | **none** |
| Retrain / deploy | **none** |
| Working-tree changes preserved | **yes** |

Only the datasets API and `README.md` were read — no parquet was fetched.

## 5. Acceptance criteria

| Criterion | Status |
|---|---|
| No dataset imported without authorization | ✅ |
| No production or frozen benchmark changes | ✅ |
| No gate marked PASS without a valid task-matched frozen test set | ✅ — both strata **`NOT PASSED`** |
| Roman Urdu and Urdu-script reported separately | ✅ |
| Exact next decisions reported | ✅ §6 |

## 6. Exact next user decisions

1. **Split designation for RUHSOLD** — accept the authors' true **801-row** test
   split (small, ~200–400 negatives), **or** accept the 2,002-row split with the
   leakage caveat permanently documented. **Blocks everything downstream.**
2. **`Profane/Untargeted` treatment** — exclude from the binary mapping
   (recommended), or adjudicate-to-label.
3. **Authorize download** — required before any empirical duplicate, near-
   duplicate or shipped-vs-card verification can be performed.
4. **Approve PII controls** (§2 above).
5. **Approve `ur-Arab` commissioning** — ≈ 1,250 items, 3 annotators, and
   **fair compensation**.

## 7. Remaining blockers

| Blocker | Impact |
|---|---|
| Split-name swap | no trustworthy Roman Urdu held-out split identified |
| `Fine_Grained/validation` == `train` | that split is unusable |
| True test split possibly too small | 801 rows may miss the 250-negative target |
| `Profane/Untargeted` unresolved | semantic-distortion risk either way |
| No upstream PII assessment | controls must be built from scratch |
| No `ur-Arab` corpus at all | full annotation required |
| Empirical verification blocked | download not authorised |

**Gate: `NOT PASSED` for both strata.** Roman Urdu unverified; Urdu-script
unmeasured. Production remains on `legacy` and requires separate deployment
approval.
