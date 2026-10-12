# AURA Phase 4.11 — Production-Invariant Verification Summary

**READ-ONLY.** Non-mutating checks only. All connections opened with
`file:aura.db?mode=ro` (SQLite read-only URI). No write was issued.
Verified at **20:10:00**.

---

## 1. Protected artifact hashes

| Artifact | Expected SHA256 (16) | Observed | Result |
|---|---|---|---|
| `models/tuned_threshold.json` | `f31f4975d29a151f` | `f31f4975d29a151f` | **UNCHANGED** |
| `models/phase2_benchmark.json` | `5a9d94e267806ea0` | `5a9d94e267806ea0` | **UNCHANGED** |
| `models/phase3_benchmark.json` | `f3a5ceb488f4a9ad` | `f3a5ceb488f4a9ad` | **UNCHANGED** |

## 2. Frozen Urdu evaluation splits

| File | Expected SHA256 | Observed (16) | Result |
|---|---|---|---|
| `data/phase2_eval/ur_test.csv` | `f18d80f3e12e07a6f185079f7af0a2adf82ab35b3518c34145a9725f0538e9c5` | `f18d80f3e12e07a6` | **FROZEN / UNCHANGED** |
| `data/phase2_eval/ur_val.csv` | `8727f2bacf41619173066466b8c992bc9cb0596e8e33c165d0f979072c61c13a` | `8727f2bacf416191` | **FROZEN / UNCHANGED** |

## 3. Production database invariants

| Invariant | Expected | Observed | Result |
|---|---|---|---|
| Prediction engine | `legacy` | **`legacy`** | **VERIFIED** |
| `PRAGMA integrity_check` | `ok` | **`ok`** | **VERIFIED** |
| `PRAGMA foreign_key_check` | empty | **clean** | **VERIFIED** |
| `dataset_samples` rows | 596 | **596** | **VERIFIED** |
| Split counts | 137 / 29 / 31 + 399 | **`train 137`, `validation 29`, `test 31`, `'' 399`** | **VERIFIED** |
| `training_runs` count | 8 | **8** | **VERIFIED** |
| `model_versions` count | 12 | **12** | **VERIFIED** |
| Active model | `improved_v10` | **`improved_v10`** | **VERIFIED** |

## 4. Non-mutation confirmation

| Check | Result |
|---|---|
| Files written to source/DB/config/manifest/threshold | **NONE** |
| Downloads / imports / evaluations this phase | **NONE** |
| Retraining / threshold changes / deployment | **NONE** |
| Engine switch away from `legacy` | **NONE** |
| Frozen split modification | **NONE** |

## 5. Verification caveats (read honestly)

| Item | Status |
|---|---|
| All 11 invariants above | **VERIFIED** |
| Checkpoint identity of the HF model file | **NOT VERIFIED this phase** — computing it requires reading the full model file; the reference value is recorded in `PHASE43_CHECKPOINT_IDENTITY.md` and was not re-derived here |
| Whether `audit_logs.details` ever contains raw user text | **NOT VERIFIED** — would require runtime exercise of endpoints, which is outside this read-only pass |
| Whether role enforcement holds under adversarial input | **NOT VERIFIED** — no security test suite exists for this |

> The verification script emitted a traceback **after** all 11 checks had already
> printed; the fault was on a non-essential trailing line (an ill-formed digest
> expression), not on any invariant. **No result above depends on that line.**
