# AURA Phase 4.5 — Final Report: Urdu Data Acquisition Readiness

**Outcome: candidates identified and metadata-verified. NOTHING ACQUIRED —
authorisation does not exist. Gate remains `NOT PASSED`.**

15:18:52 → 15:22:32 (**~3.7 min**, within the 5-minute window).

---

## 1. Headline: two findings that change the plan

**1. Network access IS available — and Phase 4.4's blocker was wrong.**
Verified directly: DNS resolves for all hosts; TCP 443 reachable to HF/GitHub/PyPI;
HTTPS GET returns **200 in 0.2 s**; no proxy configured. Phase 4.4 concluded
"no network access" — that was a **fault in the search-tool integration, not the
network**. I retract that specific claim. Phase 4.4's substantive conclusion
(no human-labelled, task-matched Urdu data *on disk*) remains correct and was
re-verified this phase. No restriction was bypassed; none exists.

**2. A Roman Urdu candidate exists that would satisfy the sample-size
requirement with no annotation spend.** Details in §3.

---

## 2. Task 2/3 — candidates identified, metadata verified

Queries against the HuggingFace datasets API surfaced 75 unique datasets; 4
matched toxic/hate/abuse/offensive. **Only metadata was read** — the API and each
dataset's `README.md`. **No data file was fetched.**

| Dataset | Licence | Script | Label definition | Verdict |
|---|---|---|---|---|
| **`community-datasets/roman_urdu_hate_speech`** (RUHSOLD) | **MIT** | **Roman Urdu** | **verified** | **RECOMMENDED** |
| `hafiz-hassaan-saeed/Roman-Urdu-Toxic-Corpus` | CC-BY-4.0 | Roman Urdu | **undocumented** (30-byte README) | rejected |
| `Adnan855570/Urdu_Hate_Speech` | MIT | Urdu script | hate vs not_hate — task-mismatched | known, in use |
| `devzohaib/roman-urdu-HateSpeech` | AFL-3.0 | Roman Urdu | not documented | rejected |

`Roman-Urdu-Toxic-Corpus` is rejected **despite the promising name**: its entire
README is a licence line, so its label definitions cannot be verified — it fails
checklist item 10 outright.

## 3. Verification of RUHSOLD (from its own dataset card)

| Field | Verified |
|---|---|
| Licence | **MIT** |
| Annotations | **`expert-generated`** |
| Language | `ur`, monolingual, `language_creators: crowdsourced` |
| Splits | train **7,208** / test **2,002** / val 800 (`Coarse_Grained`) |
| Download size | **730,720 B** — trivially small |

**Labels:**
- `Coarse_Grained`: `0: Abusive/Offensive`, `1: Normal`
- `Fine_Grained`: `+ 2: Religious Hate`, `3: Sexism`, **`4: Profane/Untargeted`**

**Why it fits:** `Profane/Untargeted` is exactly the *ambient-profane-but-not-
toxic* class that `PHASE44_ANNOTATION_SPEC.md §1.3` identifies as the dominant
false-positive zone, and `Religious Hate`/`Sexism` map onto AURA's
`identity_hate`. The taxonomy is structurally compatible with our policy.

**Sample-size impact — the key result:** we require **≥ 200, recommended 250
test negatives per stratum**. RUHSOLD's test split is **2,002 rows**; even at a
conservative 50 % non-toxic rate that is **≈ 1,000 test negatives — about 4× the
recommended minimum.** Subject to the mapping decision below, RUHSOLD alone
could satisfy the **Roman Urdu** stratum with **no annotation budget**.

**Three caveats, honestly stated:**
1. `Abusive/Offensive` is **not identical** to AURA `toxicity` — closer than
   hate speech, and structurally better aligned, but the mapping needs explicit
   approval.
2. RUHSOLD is **Roman Urdu only**. **No candidate provides Urdu-script (Arabic)
   toxicity data** — that stratum still has no acquisition path.
3. `Fine_Grained/validation` (7,208) equals `train` — looks like an upstream
   defect; confirm before use.

## 4. Tasks 4 and 6 — nothing acquired, nothing fabricated

| Constraint | Status |
|---|---|
| No download / purchase / import | ✅ **Enforced** — mtime sweep over `data/` shows **0 files written** since phase start |
| Metadata-only reads | ✅ API + `README.md` only; no parquet/CSV fetched |
| No synthetic rows called human-labelled | ✅ none created |
| Frozen splits altered | ✅ `ur_test` `f18d80f3…` / `ur_val` `8727f2ba…` **UNCHANGED** |
| Tuning on test / retrain / deploy | ✅ none |

## 5. Task 5 — human-annotation plan (condensed from Phase 4.4)

If acquisition is declined: approve labels (κ ≥ 0.70 pilot gate) → bilingual
guidelines with worked quoting/negation/reclaimed-slur examples → 2 independent
annotators + third-reviewer adjudication → dedupe **before** splitting →
group-aware split failing loudly on a straddling `group_id` → assertions L1–L7 →
freeze + hash manifest → single per-stratum evaluation.

**Partial-acquisition lever:** if RUHSOLD is authorised, the annotation budget
roughly **halves**, since only the Urdu-script stratum would need commissioning.

## 6. Safety verification (15:18:52 → 15:22:32)

| Check | Result |
|---|---|
| **Production engine** | **`legacy`** |
| `tuned_threshold.json` | `f31f4975d29a151f…` **UNCHANGED** |
| `phase2_benchmark.json` | `5a9d94e267806ea0…` **UNCHANGED** |
| `phase3_benchmark.json` | `f3a5ceb488f4a9ad…` **UNCHANGED** |
| Frozen Urdu splits | **UNCHANGED** |
| SQLite `integrity_check` / `foreign_key_check` | **ok** / **clean** |
| Rows / splits | **596**; **137 / 29 / 31 + 399 unassigned** |
| `training_runs` / `model_versions` | **8 / 12** |
| Active model | `improved_v10` |
| Deployment / retraining | **NONE / NONE** |
| Dataset files written this phase | **0** |
| Production code modified | **none** |

## 7. Files changed

| File | Change |
|---|---|
| `PHASE45_ACQUISITION_READINESS.md` | **New** (8,449 B) — checklist, verification, recommendation |
| `PHASE45_REPORT.md` | **New** — this report |

**Production code: none. Data: none.**

## 8. Task 7 — gate

**`NOT PASSED`**, for **both** script strata. Neither `ur-Arab` nor `ur-Latn` has
been measured at FPR ≤ 0.15 on a frozen, appropriate test set with CIs reported.
The existing Urdu-script figure stands at **0.2556 [0.1767, 0.3544]**, entirely
above the cap, on a corpus whose labels are definitionally mismatched.

## 9. Task 8 — the exact next user decision

**Two decisions are required:**

1. **Authorise acquisition of `community-datasets/roman_urdu_hate_speech`**
   (MIT, expert-generated, 10,010 rows, 730 KB) — **and** approve the label
   mapping `Abusive/Offensive → toxic`, `Normal → non_toxic`, with
   **`Profane/Untargeted` treated as non-toxic** per
   `PHASE44_ANNOTATION_SPEC.md §1.3`.
2. **Decide the Urdu-script (Arabic) stratum's source.** No toxicity-labelled
   Urdu-script corpus was found; that stratum will require commissioned
   annotation regardless of decision 1.

Also requiring answers before import: annotator count and compensation
(checklist #6/#7), a **PII assessment** for public social-media text (#8), and
full collection-methodology review (#9).

**Until both decisions are authorised, nothing is imported and the gate stays
`NOT PASSED`. Production remains on `legacy` and requires separate deployment
approval.**
