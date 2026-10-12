# AURA Phase 4.3 — Final Report

**Objective:** address the Urdu FPR failure through a carefully labelled,
reproducible Urdu dataset and isolated model evaluation — **without** forcing
the existing model to pass via threshold manipulation.

**Gate verdict: `NOT PASSED` — and it cannot be validly passed with the current
corpus, because the corpus measures a different task.**

Baseline captured 14:29:06, final state verified 14:52:43 (**~24 min**).
The 5-minute window was **exceeded**; reported honestly. Safety verification was
never skipped to meet the clock.

> **Agent disclosure:** 3 agents were launched. **1 succeeded** (checkpoint
> identity). **2 failed with a DNS error** (`getaddrinfo ENOTFOUND opencode.ai`)
> and produced **no output** — the corpus audit and the data plan. Both were
> subsequently performed **by the lead**, and no agent result is claimed for
> them. One agent additionally burned the window retrying before failing.

---

## 1. Dataset provenance

| Item | Finding |
|---|---|
| Source | `Adnan855570/Urdu_Hate_Speech` |
| Licence | **MIT** (per-row `source.license`, all 180 test rows) |
| `ur_val` / `ur_test` | **120** (60/60) / **180** (90/90) |
| Missing labels / empty text | **0 / 0** |
| Exact dupes (within & across) | **0 / 0** |
| **Near-dupes** (char-3-gram Jaccard ≥ 0.80, all 21,600 pairs) | **0** |
| Label contradictions | **0** |
| Leakage vs the 596-row production set | **0** overlap |
| The 8 `ur` rows in the DB | `source='curated_demo'` **synthetic**, 0 text overlap — correctly excluded from benchmarking |
| **Collection methodology / intended use** | **NOT DOCUMENTED** anywhere — recorded as a gap, not invented |
| Provenance fragility | per-row `license` and `source_url` columns are **empty**; licence survives only inside an embedded JSON blob |

## 2. Task mismatch — the root cause, now proven

The corpus's own annotation for every one of the 180 test rows reads:

```
'expert-generated hate-speech labels mapped to binary; unmappable values excluded'
```

AURA's task is **multi-dimension toxicity** (`DATASET_GUIDE.md:35,38` —
`toxic` headline plus 5 categories). Every *other* language group in
`manifest.json` comes from a genuine **toxicity/offence** corpus
(`textdetox/multilingual_toxicity_dataset`, `offenseval_dravidian`) with labels
used as-is. **`ur` is the only group sourced from a hate-speech corpus.**

This is a **definitional mismatch, not a threshold problem.** It is consistent
with the measured ROC-AUC of only **0.7044**: a generic toxicity model is
penalised as "false positive" for charged-but-not-hateful sentences that a hate
speech label would catch. **No threshold change can repair a wrong label
definition** — which is precisely why none was made.

## 3. Urdu script and Roman Urdu coverage

| Script | val | test |
|---|---|---|
| Arabic-script Urdu | **120 (100 %)** | **180 (100 %)** |
| **Roman Urdu** | **0** | **0** |

Roman Urdu is **completely unevaluated**. No claim about it is made anywhere in
this phase.

## 4. Checkpoint identity — no new candidate exists

| Item | Value |
|---|---|
| Model | `Horizon-Labs/multilingual-toxicity-small` |
| **Full SHA256** | `14c3250b4784891919040a56e04b410da3aa2fa057148942e0b815997b5f45ec` (562,591,100 B) |
| Config | `modernbert`, **7-label multi-label**, `toxicity = index 0` |
| Licence | **Apache-2.0** (upstream card only; **no licence field in local config**) |
| Cache copies | both **byte-identical**, and hashes match the upstream commit tree's declared `lfs_sha256` for `3baf7739…` |
| Production declares | `model_id = Horizon-Labs/multilingual-toxicity-small` — **identical to the on-disk checkpoint** |

**Verdict: there is NO genuinely different locally available candidate.** The
Phase 4.2 "candidate" **was** the baseline. Re-labelling an identical checkpoint
as an improvement would be fabrication — **no such claim is made**.

Note: no weights hash is recorded anywhere in production; the adapter's
`_model_version` is merely `sha256(id_string)[:8]`, i.e. a hash of the *name*,
not the weights. That is a real provenance weakness worth fixing separately.

## 5. Baseline and candidate metrics (same dataset, same protocol)

| | Phase 3 baseline @0.40 | Phase 4.2 @0.38 (val-selected) |
|---|---|---|
| FPR | **0.2556** | **0.3000** |
| **Wilson 95 % CI** | **[0.1767, 0.3544]** | **[0.2151, 0.4013]** |
| Precision / Recall / F1 | 0.6714 / 0.5222 / 0.5875 | 0.6494 / 0.5556 / 0.5988 |
| ROC-AUC | 0.7044 | 0.7006 |
| Matrix `[[TN,FP],[FN,TP]]` | `[[67,23],[43,47]]` | `[[63,27],[40,50]]` |
| n | 180 (90 neg) | 180 (90 neg) |

**The two FPRs are statistically indistinguishable** — pooled two-proportion
z = 0.666, **p = 0.506**; Fisher exact **p = 0.618**; Δ CI [−0.086, +0.175];
F1 bootstrap CIs overlap ([0.510, 0.678] vs [0.493, 0.671]). Runtime 241.9 s,
free RAM 6.02 → 4.50 GB of 15.63 GB. **No download occurred** (`HF_HUB_OFFLINE=1`).

**Sample-size reality check** — current `n_neg = 90` is inadequate:

| Requirement | negatives needed |
|---|---|
| Wilson CI non-straddling 0.15 at true FPR ≈ 0.25 | 78 |
| **80 % power, two-proportion** | **≈ 250 per group** |
| ±0.03 precision at FPR ≈ 0.25 | 799 |
| Distinguishing 0.2556 from 0.3000 | 1,596 |

## 6. Acceptance gate — `NOT PASSED`

Cap **0.15**. Baseline **0.2556 [0.1767, 0.3544]** and candidate
**0.3000 [0.2151, 0.4013]** both lie entirely above the cap, and the held-out
set is too small to resolve them from it anyway.

Nothing was tuned on test. The cap was not relaxed. No production threshold was
changed. No candidate was deployed. The frozen test set was **not** re-evaluated
this phase — it was hashed and frozen instead.

### Frozen test manifest (recorded before any future tuning)

```
ur_test.csv  f18d80f3e12e07a6f185079f7af0a2adf82ab35b3518c34145a9725f0538e9c5   74,991 B
ur_val.csv   8727f2bacf41619173066466b8c992bc9cb0596e8e33c165d0f979072c61c13a   51,366 B
```
Independently recomputed by the lead **and** by the identity agent — identical.

## 7. Tests actually executed

**112 checks / 0 failed / 0 skipped / all exit 0**, run sequentially (never
concurrent, per the 16 GB constraint):

| Suite | Result | Time |
|---|---|---|
| `tests_threshold_immutability.py` | **30/30** | 0.9 s |
| `tests_model_adapter_phase4.py` | **34/34** | 2.5 s |
| `tests_langid_phase41.py` | **32/32** | 0.4 s |
| `tests_audit_threshold_phase41.py` | **16/16** | 1.5 s |

`tests_threshold_immutability.py` prints `THRESHOLD sha256: f31f4975…5c54` and
its live checks (32–35) confirm **`legacy`, no `toxicity_score`, no pretrained
mode, engine endpoint `legacy`**. `tests_model_adapter.py` (110 tests, 54 s,
switches engine `legacy→hf`) was **deliberately not run** — no adapter code
changed, and running it would needlessly risk stranding the engine on `hf`.

Live endpoint re-check returned **HTTP 401** unauthenticated — authentication
intact, not a failure.

## 8. Files changed

**Production code: NONE.**

| File | Change |
|---|---|
| `PHASE43_URDU_AUDIT.md` | **New** (6,330 B) — corpus audit, written by lead |
| `PHASE43_URDU_DATA_PLAN.md` | **New** (10,483 B) — specification & approval-ready plan |
| `PHASE43_CHECKPOINT_IDENTITY.md` | **New** (14,207 B) — by agent, verified by lead |
| `PHASE43_REPORT.md` | **New** — this report |
| `%TEMP%\*` | throwaway read-only analysis scripts, outside the project |

## 9. Safety verification (baseline 14:29:06 → final 14:52:43)

| Check | Result |
|---|---|
| **Production engine** | **`legacy`** |
| `tuned_threshold.json` | `f31f4975d29a151f…` **UNCHANGED** |
| `phase2_benchmark.json` | `5a9d94e267806ea0…` **UNCHANGED** |
| `phase3_benchmark.json` | `f3a5ceb488f4a9ad…` **UNCHANGED** |
| SQLite `integrity_check` | **ok** |
| SQLite `foreign_key_check` | **clean** |
| Dataset rows | **596** (unchanged) |
| Splits | **137 / 29 / 31 + 399 unassigned** (unchanged) |
| `training_runs` | **8** (unchanged) |
| `model_versions` | **12** (unchanged) |
| Active model | `improved_v10` (unchanged) |
| Frozen `ur_test.csv` / `ur_val.csv` | **UNCHANGED** |
| Deployment / retraining | **NONE / NONE** |
| Downloads | **NONE** — offline mode enforced |
| C-F-1 locking | untouched |

## 10. Remaining blockers and the next required decision

| Blocker | Detail |
|---|---|
| **Gate `NOT PASSED`** | 0.2556 vs cap 0.15; caused by a **label-definition mismatch**, not thresholds |
| **Corpus is hate-speech, task is toxicity** | proven by the corpus's own `label_notes`; `ur` is the only such group |
| **Roman Urdu unevaluated** | 0 rows exist; no claim possible |
| **Test set under-powered** | 90 negatives; ~250/stratum needed for 80 % power |
| **No second candidate on disk** | exactly one model exists; no improvement available locally |
| **No weights hash in production** | `_model_version` hashes the model *name*, not the weights |
| **2 agents failed** | DNS error; audit + data plan done by lead instead |

### Next required decision

**Approve acquisition and annotation of a task-matched Urdu *toxicity* set —
≥ 250 negatives per script stratum, covering Urdu script and Roman Urdu — using
the definitions in `PHASE43_URDU_DATA_PLAN.md`.** Until that exists, the 0.15
gate cannot be validly satisfied, and no threshold change is an acceptable
substitute. Alternatives requiring an explicit decision: an out-of-scope
exception for `ur`, or acceptance of an F1 cost.

**Production remains unchanged and requires separate deployment approval.**
