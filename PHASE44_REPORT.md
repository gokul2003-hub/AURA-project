# AURA Phase 4.4 — Final Report (Option c: Task-Matched Urdu Toxicity Dataset)

**Outcome: PLANNING MILESTONE COMPLETE — BLOCKED on human-labelled data.**

The four required planning artifacts were produced in full. **No dataset was
created, because none could be legitimately obtained.** The quality gate remains
**`NOT PASSED`**.

Baseline 15:01:56 → final verified 15:07:46 (**~6 min**). The 5-minute window was
marginally exceeded; safety verification was not traded for the clock.

---

## 1. The blocker, stated plainly

**Human-labelled, task-matched Urdu toxicity data does not exist in this
environment, and cannot be obtained from it.**

Evidence:

| Check | Result |
|---|---|
| Any Urdu *toxicity* corpus on disk | **None** |
| Urdu data present | `ur_test.csv` / `ur_val.csv` — **hate-speech** labelled; `ur.json` lexicon (722 B, self-declared *"demo/dev quality. Not benchmark data."*) |
| `data/external/` contents | `civil_comments.csv`, `wiki_toxic.csv` — both **English only** |
| Roman Urdu rows anywhere | **0** |
| External research | **Failed** — 3 web queries returned no results; sub-agents failed with `getaddrinfo ENOTFOUND opencode.ai` → **no network access** |
| Model candidates on disk | **1** (already the baseline; no genuinely distinct candidate) |

Because there is no network, **no external dataset's licence, size or label
quality could be verified.** I therefore named **no** external dataset as
available — doing so without verification would be fabrication.

Per the brief ("*if human-labelled data is not available, stop at the planning
milestone and report the blocker honestly*"), **work stopped there.**

---

## 2. Deliverables produced

### `PHASE44_ANNOTATION_SPEC.md` — annotation specification
- Task definition aligned to AURA's actual multi-dimension toxicity label
  (`DATASET_GUIDE.md:35,38`), explicitly **not** hate speech.
- Operational `toxic`/`non_toxic` definitions and an 11-row category decision
  table covering **borderline, quoted, negated, conversational and
  context-dependent** cases — the exact zones a generic toxicity model
  over-fires on.
- Target shares per category (12 % borderline, 10 % quoted, 8 % negated,
  15 % context-dependent, 10 % identity-reference-without-attack).
- **`ur-Arab` and `ur-Latn` as parallel strata**, never pooled.
- Roman Urdu guidelines: multiple transliteration schemes, variant collapsing,
  code-mixing, and the rule that machine-transliterated rows are **not**
  human-labelled.
- Workflow: 2 independent annotators + third-reviewer adjudication, **Cohen's
  κ ≥ 0.70** per stratum and per category, below which guidelines are revised
  rather than labels force-assigned.
- Full 21-field schema including `provenance`, `group_id`, quoted/negated flags.
- **13-row licensing & provenance checklist**, incl. the human-vs-machine-label
  check grounded in project precedent (`PHASE2_MODEL_EVALUATION.md:42` warns the
  bn labels are Qwen-generated, not human gold).

### `PHASE44_EVAL_PROTOCOL.md` — sample-size plan + leakage-safe protocol
All figures **computed here**, not asserted.

**A correction to my own Phase 4.3 claim.** Phase 4.3 called `n_neg = 90`
"inadequate". Re-computation shows that was imprecise:

| | At n_neg = 90 |
|---|---|
| Detecting a **FAIL** (true FPR ≈ 0.25) | **Adequate** — CI `[0.177, 0.354]` is entirely above 0.15 |
| Confirming a **PASS** (true FPR ≈ 0.10) | **Inadequate** — CI `[0.054, 0.179]` straddles 0.15 |

The existing corpus can already **condemn** the baseline but could never
**acquit** a good candidate. The requirement is therefore driven by
pass-confirmation, and applies to **negatives in the frozen test split, per
stratum**:

| Test negatives | True 0.10 → CI | True 0.25 → CI |
|---|---|---|
| 200 | [0.066, **0.149**] | [**0.195**, 0.314] |
| **250** (recommended) | [0.069, **0.143**] | [**0.199**, 0.305] |

Sizing: 250 test negatives/stratum ÷ 40 % test split = **625** corpus
negatives/stratum → **1,250** items/stratum at 1:1 → **≈ 2,500 items total**
across both script strata. (80 % power for 0.25 vs 0.15 independently requires
**n = 250 per group**, consistent.)

Leakage-safe protocol: dedupe (exact + char-trigram Jaccard ≥ 0.80 +
transliteration families) **before** splitting; **group-aware splitting** with a
programmatic invariant that fails loudly if any `group_id` spans two splits;
**7 named leakage assertions L1–L7** that must pass before any metric is
reported; freeze-before-tuning with a hash manifest; per-stratum reporting with
a gate rule requiring **each** stratum independently ≤ 0.15 with its CI at or
below the cap.

---

## 3. Quality gate — `NOT PASSED`

No new evaluation was run, because there is no valid test set to run one on.
The existing evidence stands unchanged:

| | Baseline @0.40 |
|---|---|
| FPR (Wilson 95 %) | **0.2556** [0.1767, 0.3544] |
| Matrix `[[TN,FP],[FN,TP]]` | `[[67,23],[43,47]]` |
| n | 180 (90 negatives) |

Cap **0.15**; the CI lies entirely above it. Root cause remains the proven
**label-definition mismatch** (`PHASE43_URDU_AUDIT.md §2`), which no threshold
change can repair. No threshold was tuned, the cap was not relaxed, and no
candidate was deployed.

---

## 4. Safety verification (15:01:56 → 15:07:46)

| Check | Result |
|---|---|
| **Production engine** | **`legacy`** |
| `tuned_threshold.json` | `f31f4975d29a151f…` **UNCHANGED** |
| `phase2_benchmark.json` | `5a9d94e267806ea0…**UNCHANGED** |
| `phase3_benchmark.json` | `f3a5ceb488f4a9ad…` **UNCHANGED** |
| **Frozen Urdu splits** | `ur_test.csv` `f18d80f3…`, `ur_val.csv` `8727f2ba…` **UNCHANGED** |
| SQLite `integrity_check` | **ok** |
| SQLite `foreign_key_check` | **clean** |
| Dataset rows / splits | **596**; **137 / 29 / 31 + 399 unassigned** (unchanged) |
| `training_runs` / `model_versions` | **8 / 12** (unchanged) |
| Active model | `improved_v10` (unchanged) |
| Deployment / retraining | **NONE / NONE** |
| Downloads | **NONE** (no network available) |
| **New data files created** | **0** — verified by mtime sweep for `.csv`; nothing fabricated |
| C-F-1 locking | untouched |
| Production code modified | **none** |

No regression suite was run this phase: **no production file changed**, so there
was nothing to regress. Protected hashes and the frozen splits were verified
before and after.

---

## 5. Files changed

| File | Change |
|---|---|
| `PHASE44_ANNOTATION_SPEC.md` | **New** (9,647 B) |
| `PHASE44_EVAL_PROTOCOL.md` | **New** (6,231 B) |
| `PHASE44_REPORT.md` | **New** — this report |

**Production code: NONE. No data: NONE.**

---

## 6. Remaining blockers and the next required decision

| Blocker | Detail |
|---|---|
| **No human-labelled Urdu toxicity data** | Nothing task-matched on disk; 8 `ur` DB rows are `curated_demo` synthetic |
| **No Roman Urdu data at all** | 0 rows; stratum wholly unevaluated |
| **No network access** | Cannot verify, purchase or download any external corpus; cannot name a candidate honestly |
| **Test split under-powered for a PASS** | 90 negatives; need **≥ 200, recommend 250 per stratum** |
| **No distinct candidate model** | Exactly one checkpoint exists; it *is* the baseline |
| **Corpus ≈ 2,500 items needed** | 625 negatives/stratum at 40 % test, 1:1 balance |

### Next required decision

**Restore network/data-acquisition capability and approve acquisition + human
annotation of ≈ 2,500 items** (Urdu script and Roman Urdu, 1:1 balanced, using
`PHASE44_ANNOTATION_SPEC.md`), then execute `PHASE44_EVAL_PROTOCOL.md`.
Until then the gate cannot be validly satisfied.

Alternatives needing explicit approval: an out-of-scope exception for `ur`, or
acceptance of an F1 cost at a relaxed operating point.

**Production remains unchanged and requires separate deployment approval.**
