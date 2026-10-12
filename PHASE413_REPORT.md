# AURA Phase 4.13 — Final Report

**Outcome: incident source VERIFIED · retention escalated as an unanswered
decision (no date chosen) · P3/P3b/P3c IMPLEMENTED and TESTED (36/36) · P4a
runtime-verified · P4b runtime NOT VERIFIED · P4c proven NOT implemented
(plaintext storage) · production invariants PRESERVED.**

**G1 🔴 NO-GO · G3–G6 🔴 NO-GO · G7 ⏸ DEFERRED · both quality gates `NOT PASSED`.**

Companion deliverables: `PHASE413_INCIDENT_REVIEW.md`,
`PHASE413_RETENTION_DECISION_REQUIRED.md`, `PHASE413_P3P4_EVIDENCE.md`.

---

## A. Workspace state inspected before editing (rule 7)

| Item | Finding |
|---|---|
| Git repository | **NONE** at root or under `comment toxicity` — same as Phase 4.12. **No change may be assumed committed.** |
| Proxy for uncommitted work | 13 files modified 20:11–20:28 (all mine: `PHASE411_*`, `PHASE412_*`, `p5_deletion.py`, `tests_p5_cascade_deletion.py`) |
| Approach | **Additive only** — no existing file modified, overwritten or reverted |
| `PHASE411_APPROVAL_REGISTER.md` | **Does not exist** — the register is `PHASE410_APPROVAL_REGISTER.md`. Discrepancy recorded, not silently "fixed" |

## B. Task A — Incident review ✅ **VERIFIED (conclusive)**

Full account: `PHASE413_INCIDENT_REVIEW.md`.

| Element | Finding |
|---|---|
| **Test** | `tests_threshold_immutability.py` — **regression suite 1 of Phase 4.12** |
| **Line** | **`:186`** → `POST /predict` `{'text': 'you are stupid and I hate you'}` |
| **Route** | `/predict` (`:1239`) → `:1076 store_moderation()` → `:617` INSERT + `:620` `MODERATION_DECISION` (single commit `:621` → both counts advance together) |
| **Process** | live uvicorn on `127.0.0.1:8010`, started 10:53:08 |
| **Proof** | row 1630 message **byte-identical** to the test payload; `user_id='admin'` = test default; `created_at 14:52:39Z` = **20:22:39** local; timing fits (P5 suite compiled 20:22:34, ran 3.3 s) |
| **Pre-existing?** | **Yes** — row **1629 carries the identical payload** from an earlier run |

**Correction to Phase 4.12:** that report blamed *"regression 2+3"*. The
evidence shows **regression 1**. Recorded rather than silently edited.

**Disposition: no record deleted, no audit trail altered.** The two rows are
retained as incident evidence.

## C. Task B — Retention decision ✅ **STOPPED AT THE DECISION**

`PHASE413_RETENTION_DECISION_REQUIRED.md` — **no date chosen.**

All six sources inspected; **none supplies a date**, only *"approved up front"*.
Nine data classes **D1–D9** are broken out for separate decisions (including
**D7 audit evidence** and **D8/D9 frozen evaluation + dataset state**), with the
authorizer, the evidence to assess, and the configuration/validation procedure.

> **Exact question for the authorized reviewer (§3):**
> *What is the approved retention end date (or duration) for each class D1–D9,
> and what is the trigger event?*

`purge_expired()` **remains BLOCKED** (`RetentionPolicyError`) — 5 dedicated
tests assert the unset/malformed/no-op paths.

## D. Task C — P3 controls ✅ **IMPLEMENTED + TESTED (36/36)**

New module `CODE/BACKEND/p3_privacy.py` (existing files untouched, **no RUHSOLD,
no manifest recomputation**).

| Control | Status |
|---|---|
| **P3** redaction before dedup | ✅ 5 pinned ordered rules; ordering enforced and proven (2 identifier-only variants → **1** record) |
| **P3b** version + NFKC | ✅ `PREPROCESS_VERSION`/`RULES_VERSION`/`PINNED_REGEX_VERSION`, fingerprint embedded per record, version-bump changes fingerprint. Legacy engine keeps **NFC** (frozen, engine-protected); NFKC applies to the new path |
| **P3c** salted hashing | ✅ `SHA256(salt‖normalised)`; empty salt **refused**; **no salt literal in source** (test-asserted) |
| **M1–M4** mapping | ✅ class 4 → `excluded_pending_adjudication`, `toxic:None`, **never** `counts_as_verified_negative` |

**Coverage:** ordering 4/4 · deterministic normalisation 7/7 · version changes
5/5 · salt handling 7/7 · PII fixtures 5/5 · ambiguous-label exclusion 6/6 ·
isolation 2/2 = **36/36, exit 0**.

## E. Task D — P4 controls

| Control | Source evidence | Runtime evidence | **Verdict** |
|---|---|---|---|
| **P4a** role-restricted access | `backend.py:183-191` 401/403 + 5 enforcement sites | **8 unauthenticated probes → 401**; counts identical before/after → **`NO WRITES: True`**; plus 3 passing `authorise()` tests | ✅ **VERIFIED (both)** |
| **P4b** counts-only logging | **0** candidate raw-text `print/logger/log` statements; `audit_log` payloads carry ids/engines only | **NOT VERIFIED** — error paths not exercised | ⚠️ **SOURCE VERIFIED · RUNTIME NOT VERIFIED** |
| **P4c** encryption at rest | **`SQLite format 3\0` plaintext**; no SQLCipher; no `PRAGMA key`/`encrypt`/`Fernet`/`AES` in `backend.py`; `DB_PATH = BASE_DIR/'aura.db'` | n/a | ❌ **NOT IMPLEMENTED — plaintext confirmed** |

**Encryption at rest is NOT claimed** — the opposite is evidenced.
**403 runtime evidence is NOT VERIFIED** (would require creating a session = a write).

## F. Task E — Safety and regression (isolated suites only)

**No live-backend test capable of creating records was run** (rule 5).

| Invariant | Expected | Observed | Result |
|---|---|---|---|
| Production engine | `legacy` | **`legacy`** | ✅ |
| `tuned_threshold.json` | `f31f4975d29a151f` | matches | ✅ **UNCHANGED** |
| `phase2_benchmark.json` | `5a9d94e267806ea0` | matches | ✅ **UNCHANGED** |
| `phase3_benchmark.json` | `f3a5ceb488f4a9ad` | matches | ✅ **UNCHANGED** |
| `ur_test.csv` / `ur_val.csv` | frozen digests | match | ✅ **UNCHANGED** |
| Integrity / FK | `ok` / clean | `ok` / clean | ✅ |
| `dataset_samples` | 596 | **596** | ✅ |
| Splits | 137/29/31+399 | **137 / 29 / 31 + 399** | ✅ |
| `training_runs` | 8 | **8** | ✅ |
| `model_versions` / active | 12 / `improved_v10` | **12 / `improved_v10`** | ✅ |

### Row counts — expected vs unexplained

| Table | Count | Classification |
|---|---|---|
| `moderation_results` | **1,630** | **EXPECTED** — Phase 4.12 incident, +1, attributed in §B |
| `audit_logs` | **1,682** | **EXPECTED** — same incident, +1 |
| `DATA_ERASURE` rows | **0** | **EXPECTED** — erasure never run on production |
| `users` / `feedback` / `live_sessions` / `live_events` | **20 / 5 / 6 / 16** | **unchanged** |
| **Unexplained changes** | **NONE** | — |

**No count was repaired by deleting records or restoring an old database**
(rule E). Isolated suites: **P3 36/36 exit 0 · P5 23/23 exit 0**.

## G. Files changed

| File | Change |
|---|---|
| `CODE/BACKEND/p3_privacy.py` | **NEW** |
| `CODE/BACKEND/tests_p3_privacy.py` | **NEW** |
| `PHASE413_INCIDENT_REVIEW.md` | **NEW** |
| `PHASE413_RETENTION_DECISION_REQUIRED.md` | **NEW** |
| `PHASE413_P3P4_EVIDENCE.md` | **NEW** |
| `PHASE413_REPORT.md` | **NEW** |
| Everything else | **NOT MODIFIED** |

## H. Updated blocker register

| ID | Blocker | Phase 4.12 | **Phase 4.13** |
|---|---|---|---|
| **B1** P1 rights/provenance | open | 🔴 **open** |
| **B2** P2 lawful basis / ToS / erasure | open | 🔴 **open — now also needs the retention decision D1–D9** |
| **B3** P5 not implemented | partially closed | ✅ **CLOSED for cascade deletion** (23/23). 🔴 **P5a open** — decision required (`PHASE413_RETENTION_DECISION_REQUIRED.md`) |
| **B4** P3 redaction | open | ✅ **CLOSED** (36/36) |
| **B5** P3c salted hashes | open | ✅ **CLOSED** (36/36) |
| **B6** P3b versioning / NFKC | open | ✅ **CLOSED** (36/36; legacy NFC unchanged by design) |
| **B7** C1 deferred | open | ⏸ **deferred** — compensation pending; no corpus |
| **B8** upstream splits unusable | open | 🔴 **open** |
| **B9** no P3–P5 tests | partially closed | 🔴 **partially open** — P3 ✔, P5 ✔; **P4b runtime + P4c untested/absent** |
| **B10 (new)** P4c encryption at rest | — | 🔴 **NEW: proven absent (plaintext storage)** — storage/key decision required |
| **B11 (new)** retention policy decision | — | 🔴 **NEW: D1–D9 unanswered; `purge_expired` blocked** |
| **B12 (new)** live-test isolation defect | — | 🔴 **NEW: `tests_threshold_immutability.py:186` writes production when the service is live** — fix needs authorization to edit an existing test |

## I. Updated gate register

| Gate | Phase 4.12 | **Phase 4.13** | Prerequisite still missing |
|---|---|---|---|
| **G1** Lawful import | 🔴 NO-GO | 🔴 **NO-GO** | **P1/P2 qualified review** |
| **G2** Mapping freeze | 🟢 READY | 🟢 **READY** | — |
| **G3** Redaction & preprocessing | 🔴 NO-GO | 🔴 **NO-GO — materially narrowed** | P3/P3b/P3c now ✅; remaining: **P4b runtime evidence, P4c encryption, retention policy (B11), endpoint wiring (R1)** |
| **G4** Leakage-safe split | 🔴 NO-GO | 🔴 **NO-GO** | needs G1 |
| **G5** Hash freeze | 🔴 NO-GO | 🔴 **NO-GO** | depends on G4 |
| **G6** Single evaluation | 🔴 NO-GO | 🔴 **NO-GO** | depends on G1–G5 |
| **G7** `ur-Arab` | ⏸ DEFERRED | ⏸ **DEFERRED** | C1 + compensation; no corpus |

## J. Final decision

| Decision | Verdict |
|---|---|
| **Dataset import (G1)** | 🔴 **NO-GO** — pending qualified P1/P2 review |
| **Roman Urdu evaluation** | 🔴 **NO-GO** — G3–G6 prerequisites not evidenced |
| **Urdu-script evaluation (G7)** | ⏸ **DEFERRED** |
| **Retention enforcement** | 🔴 **BLOCKED** — decision required, no date chosen |
| **Production erasure / endpoint wiring** | 🔴 **NOT AUTHORIZED** (rule 9) |
| **Encryption-at-rest claim** | ❌ **NOT MADE — plaintext confirmed** |

| Quality gate | Cap | Status |
|---|---|---|
| Roman Urdu (`ur-Latn`) | 0.15 | **`NOT PASSED`** |
| Urdu script (`ur-Arab`) | 0.15 | **`NOT PASSED`** |

### Open decisions for the authorized reviewer (exact questions)

1. **Retention (§3 of the retention doc):** *What is the approved retention end
   date/duration for each class D1–D9, and what is the trigger event?*
2. **P4c storage:** *Approve encryption at rest (SQLCipher with out-of-repo key,
   or full-volume encryption) and its key-custody procedure — or formally accept
   plaintext storage as a documented risk?*
3. **P4b:** *Authorize a runtime logging exercise (isolated service) to convert
   source evidence into runtime evidence?*
4. **B12:** *Authorize the isolation fix for `tests_threshold_immutability.py`?*
5. **P1/P2:** appoint the qualified legal/privacy reviewer.

**No gated action was performed. G1 remains NO-GO. G3–G6 remain NO-GO. G7 remains deferred.**
