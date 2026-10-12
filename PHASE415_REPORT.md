# AURA Phase 4.15 — Final Report
**Exposure Reduction & Credential Remediation Planning (B13, B14, B15, B17)**

**Outcome: Stage 1 read-only verification COMPLETE · three remediation plans
specified (credential / storage & backup / approvals) · Stage 3 = isolated
additive prototype only, **27/27 tests pass** · **zero production writes** ·
**no exposure reduction is claimed** (nothing implemented or verified) · all
invariants PRESERVED.**

**G1 🔴 NO-GO · G3–G6 🔴 NO-GO · G7 ⏸ DEFERRED · both quality gates `NOT PASSED`.**

Companion deliverables: `PHASE415_CREDENTIAL_REMEDIATION_PLAN.md`,
`PHASE415_STORAGE_AND_BACKUP_PLAN.md`, `PHASE415_APPROVALS_REQUIRED.md`.

---

## 0. Workspace state recorded before any change

| Item | Finding |
|---|---|
| Git repository | **NONE** at root or under `comment toxicity` — unchanged from 4.12/4.13/4.14. **No change may be assumed committed** |
| Files modified since Phase 4.14 | **4** — all Phase 4.14 deliverables, all mine (20:47–20:51) |
| Brief's referenced reports | all 4 present and read ✅ |
| Approach | **Additive only** — 2 new prototype files + 4 new reports; **no existing file modified** |

Existing source mtimes **unchanged** this phase: `backend.py` 10:58:36 ·
`ml_service.py` · `mlexicon.py` · `p5_deletion.py` · `p3_privacy.py` ·
`import_external_datasets.py`.

---

## 1. Stage 1 — Read-only verification

### 1.1 B15 — OneDrive sync: **CONFIRMED**

| Check | Result |
|---|---|
| `env:OneDrive` | `C:\Users\gokul\OneDrive` |
| Project path under `\OneDrive\` | **`True`** |
| OneDrive process running | **`True`** |
| Sync accounts | **`Accounts\Personal` + `Accounts\Business1` both present** |
| `aura.db` attributes | **`Archive`** — ReparsePoint **0**, Offline **0** |

`aura.db` is a **fully materialised local file inside an active sync root**, so
it is in scope for upload. **Precise limit:** *whether bytes actually reached the
cloud, and to which tenant, is **NOT VERIFIABLE** from this machine.* The
control gap exists regardless of actual upload state.

### 1.2 B13 — Backups: **CONFIRMED plaintext, 22.3 MB**

| File | Size |
|---|---|
| `aura-phase41-baseline-20261011-101947.db` | 11,046,912 B |
| `aura-pre-external-import-20261009-223341.db` | 6,152,192 B |
| `aura-pre-external-import-20261009-223359.db` | 6,152,192 B |

Produced by `Connection.backup()` → **byte-identical plaintext**;
"best-effort, never fatal" (`import_external_datasets.py:236-237` swallows
errors); **inside the same sync root**; **no restore procedure exists**.

### 1.3 B17 — The demo credential: **ACTIVE, VALID, PRIVILEGED, SOLE**

| Check | Result |
|---|---|
| `role` | **`admin`** |
| `blocked` | **`0` — active** |
| `created_at` | `2026-09-02T09:10:06Z` |
| **stored hash == seeded hash** | **`True`** *(compared in memory; value never printed)* |
| Other admins | **none** — sole admin account |

#### ⚠️ Escalation beyond Phase 4.14
`backend.py:166-172` does **not** merely seed. When the admin already exists
(the normal case) it executes:

```
UPDATE users SET password_hash=?, salt=?, role='admin', blocked=0 WHERE …
```

| Consequence | Effect |
|---|---|
| Password set by the operator | **silently reverted on next start-up** |
| Admin blocked by operator | **unblocked** on start-up |
| Admin demoted | **re-escalated to `admin`** |
| Net | the credential is **permanent and self-healing**, not a one-time seed |

Comment at `:170-171` shows this is **deliberate** ("one stable demo admin
credential … also repairs databases created by earlier AURA builds").

#### ⚠️ NEW BLOCKER B18 — it also runs on **import**
`backend.py:1088` calls `init_db()` at **module scope**; **no
`if __name__ == '__main__'` guard** (verified absent).

> **`import backend` performs a production write** — it rewrites the live admin
> credential and unblocks the account. Any test importing the module without
> first redirecting `DB_PATH` mutates production. **This is a direct hazard to
> the regression-isolation rule** and is a plausible contributor to the
> Phase 4.12 incident class. I therefore **did not import `backend`** at any
> point in this phase.

#### Static detector (executes nothing)
`detect_startup_reseed()` run read-only against the real source:
```
findings: 1
line   172   scope=init_db   start-up path=True
```
The classifier also **correctly declines** to flag route-scoped rotations
(tested), so a future legitimate change-password endpoint will not be mis-reported.

### 1.4 Authentication surface

| Property | Finding | Assessment |
|---|---|---|
| Password storage | PBKDF2-HMAC-SHA256, **150k** iterations, per-user salt (`:162`) | ✅ sound |
| Login response | single generic `401` (`:1109`) | ✅ no username oracle |
| **Rate limiting / lockout** | **none** | 🔴 brute-force feasible |
| **Password change / reset endpoint** | **none** | 🔴 no rotation path |
| **Registration** | **open**; `role` hard-coded `'user'` (`:1117`) | 🟡 no escalation, but unbounded account creation |
| Session tokens | in-memory only (`:182`) | ✅ nothing at rest |
| **Network bind** | **`127.0.0.1:8010` only**; no `0.0.0.0`/`::` | ✅ **localhost-only** — genuine mitigating factor |

### 1.5 External exposure — **NOT VERIFIABLE**

Audit trail contains **no `LOGIN` or `LOGIN_FAILED` events** (only
`ADMIN_VERIFY`, `BLOCK_USER`, `ENGINE_CHANGE`, `HUMAN_REVIEW`,
`MODERATION_DECISION`).

> **Honest conclusion:** exposure **cannot be measured** — the system has **no
> authentication telemetry**. The correct statement is *"unknown, and not
> instrumented"*, **not** *"no exposure"*. Prior `blocked` state is also
> unverifiable, because `init_db()` overwrites it to `0` on every start.

### 1.6 B14 — Key custody: **CONFIRMED absent**
No vault, no DPAPI, no `.env`, no key file, no secret env var. **There is
nowhere approved to put an encryption key.**

---

## 2. Stage 2 — Remediation plans specified

| Plan | Addresses | Contents |
|---|---|---|
| `PHASE415_CREDENTIAL_REMEDIATION_PLAN.md` | **B17, B18** | Stages **C0–C5**: preconditions · audited rotation · **seed-once** replacement · route-scoped change-password · `LOGIN` telemetry · 8 verification tests · 5 rollback triggers · 5-step rollback · decision-makers |
| `PHASE415_STORAGE_AND_BACKUP_PLAN.md` | **B13, B14, B15** | **S1** relocation out of sync · **S2** protected backups + **restore rehearsal (T-S1…T-S6)** + retirement sequence · **S3** key custody + SQLCipher migration/rollback · **ordering rationale** |
| `PHASE415_APPROVALS_REQUIRED.md` | all | **5 blocking + 11 step-gated** approvals, each with owner and status |

**Ordering rationale:** S1 before S2 (creating backups inside the sync root
would multiply the exposure); S2 before retiring anything (never remove the only
rollback artifact); S3 last (migrating before relocating forces a re-key);
**B17 alongside S1** (otherwise `init_db()` reasserts a known credential into
whatever storage S1 selects).

**Not invented, as instructed:** no retention duration (governed by
unanswered **B11/D1–D9**), no key-management policy (governed by **A3**).

---

## 3. Stage 3 — Isolated additive prototype (no authorization needed)

`CODE/BACKEND/p15_credential_remediation.py` + `tests_p15_credential_remediation.py`

**Isolation:** temp DBs only · synthetic fixtures · `backend` **never imported** ·
no file IO primitives in the module · no hard-coded credential literal · the one
production-adjacent action is **read-only static text analysis**.

| Capability | Behaviour |
|---|---|
| `ensure_admin_account()` | **seed once, never overwrite** — preserves hash, `blocked` and `role`; the password factory is **never called** for an existing account |
| `rotate_password()` | explicit, audited (`PASSWORD_ROTATION`), **counts-only** details; **never** touches role or blocked |
| `set_blocked()` | audited; **not** undone by start-up |
| `record_audit()` | **refuses** secret-bearing keys (`AuditNotWritten`) |
| `detect_startup_reseed()` | static classifier — start-up path vs route-scoped rotation |

**`tests_p15_credential_remediation.py` — Ran 27, OK, exit 0**

| Area | Tests |
|---|---|
| No-reseed across restarts, factory-not-invoked, blocked preserved, role not forced, case-insensitive, blank rejected | 8 |
| Explicit rotation, audited secret-free, never grants role/unblocks, unknown-account/empty-password rejected, per-call salt, block/unblock audited | 8 |
| Audit secret refusal + metadata allowed | 2 |
| Detection on real source, `init_db` attribution, route-scope discrimination, clean-source negative, module-scope `init_db()` | 6 |
| Hygiene (no literal, no app import, no file IO) + **production DB mtime unchanged across the suite** | 3 |

> A first run showed **1 failure** — a **test-contract bug of mine** (the
> detector legitimately *reports* route-scoped rewrites; it just must not
> *classify* them as start-up). I fixed the **test**, then found and fixed a
> **real defect** in the module's scope tracker (the `def` line overwrote the
> `@app.*` decorator marker). Both corrected; re-run **27/27, exit 0**.

**This prototype proves the proposed semantics are implementable and testable.
It does not change production behaviour.**

---

## 4. Safety verification (end of phase)

| Invariant | Expected | Observed | Result |
|---|---|---|---|
| Production engine | `legacy` | **`legacy`** | ✅ |
| `tuned_threshold.json` | `f31f4975d29a151f` | matches | ✅ **UNCHANGED** |
| `phase2_benchmark.json` | `5a9d94e267806ea0` | matches | ✅ **UNCHANGED** |
| `phase3_benchmark.json` | `f3a5ceb488f4a9ad` | matches | ✅ **UNCHANGED** |
| `ur_test.csv` / `ur_val.csv` | frozen digests | match | ✅ **UNCHANGED** |
| Integrity / FK | `ok` / clean | `ok` / clean | ✅ |
| `dataset_samples` | 596 | **596** | ✅ |
| Splits | 137/29/31+399 | **137 / 29 / 31 / 399** | ✅ |
| `training_runs` / `model_versions` / active | 8 / 12 / `improved_v10` | **8 / 12 / `improved_v10`** | ✅ |
| `journal_mode` | `delete` | **`delete`** | ✅ **no migration** |
| Backups | 3, untouched | **3, original timestamps** | ✅ |
| `moderation_results` / `audit_logs` | 1,630 / 1,682 | **1,630 / 1,682** | ✅ **Phase 4.12 records untouched** |
| `DATA_ERASURE` / users / admins | 0 / 20 / 1 | **0 / 20 / 1** | ✅ |

**Unexplained changes: NONE.** No count was repaired by deleting records or
restoring a database. **No credential was displayed, copied or rotated. No file
moved, deleted or re-permissioned. No dependency installed. No key generated.**

### Files changed
| File | Change |
|---|---|
| `CODE/BACKEND/p15_credential_remediation.py` | **NEW** |
| `CODE/BACKEND/tests_p15_credential_remediation.py` | **NEW** |
| `PHASE415_REPORT.md` | **NEW** |
| `PHASE415_CREDENTIAL_REMEDIATION_PLAN.md` | **NEW** |
| `PHASE415_STORAGE_AND_BACKUP_PLAN.md` | **NEW** |
| `PHASE415_APPROVALS_REQUIRED.md` | **NEW** |
| Everything else | **NOT MODIFIED** |

---

## 5. Updated blocker register

| ID | Blocker | 4.14 | **4.15** |
|---|---|---|---|
| **B1** P1 rights/provenance | 🔴 open | 🔴 **open** |
| **B2** P2 lawful basis/erasure | 🔴 open | 🔴 **open** |
| **B3** P5a retention machinery | 🔴 open | 🔴 **open** |
| **B4/B5/B6** P3 / P3c / P3b | ✅ closed | ✅ **closed (36/36)** |
| **B7** C1 deferred | ⏸ deferred | ⏸ **deferred** |
| **B8** upstream splits unusable | 🔴 open | 🔴 **open** |
| **B9** P4b runtime / P4c | 🔴 partial | 🔴 **partial** |
| **B10** P4c encryption at rest | 🔴 assessed, plan proposed | 🔴 **open — now additionally blocked by B14** |
| **B11** retention decision | 🔴 open | 🔴 **open — also governs auth-audit + backup retention** |
| **B12** live-test isolation defect | 🔴 open | 🔴 **open — WORSENED by B18** |
| **B13** plaintext backups ×3 | 🔴 new | 🔴 **open — plan S2 specified; retirement needs A8 + verified successor backup** |
| **B14** no key custody | 🔴 new | 🔴 **open — plan S3.0 specified; no policy invented** |
| **B15** OneDrive sync path | 🔴 new | 🔴 **CONFIRMED this phase** (sync root + running client + 2 accounts + hydrated file); plan S1 specified; needs A6/A7 |
| **B16** `PRAGMA key` false positive | 🟡 new | 🟡 **documented (C7)** |
| **B17** hard-coded demo credential | 🔴 new | 🔴 **open — escalated: ACTIVE/VALID/PRIVILEGED/SOLE, and re-imposed every start-up (`:169-172`) + on import** |
| **B18 (new)** `init_db()` at module scope | — | 🔴 **NEW — `import backend` writes production; blocks import-based testing; undermines isolation rules** |
| **B19 (new)** no authentication telemetry | — | 🔴 **NEW — no `LOGIN`/`LOGIN_FAILED` events ⇒ exposure is unmeasurable** |
| **B20 (new)** no rate-limit/lockout, open registration | — | 🟡 **NEW — hardening items (A13), separately approvable** |
| **B21 (new)** no restore procedure exists | — | 🔴 **NEW — backups exist but have never been rehearsed for restore** |

---

## 6. Updated gate register

| Gate | 4.14 | **4.15** | Prerequisite still missing |
|---|---|---|---|
| **G1** lawful import | 🔴 NO-GO | 🔴 **NO-GO** | **A5** appoint reviewer → **P1/P2 review** |
| **G2** mapping freeze | 🟢 READY | 🟢 **READY** | — |
| **G3** redaction & preprocessing | 🔴 NO-GO | 🔴 **NO-GO — prerequisites now itemised** | P3 ✅; remaining: **P4b runtime** · **A3 key custody** · **A9 SQLCipher** · **A4 retention (B11)** · **A15 endpoint wiring** |
| **G4** leakage-safe split | 🔴 NO-GO | 🔴 **NO-GO** | needs G1 |
| **G5** hash freeze | 🔴 NO-GO | 🔴 **NO-GO** | depends on G4 |
| **G6** single evaluation | 🔴 NO-GO | 🔴 **NO-GO** | depends on G1–G5 |
| **G7** `ur-Arab` | ⏸ DEFERRED | ⏸ **DEFERRED** | C1 + compensation; no corpus |

> Exposure-reduction items (B13/B14/B15/B17/B18/B19/B21) are **privacy-readiness**
> work supporting G3. **None of them unblocks G1**, which turns solely on the
> P1/P2 legal review.

---

## 7. Final decision

| Item | Status |
|---|---|
| **Exposure reduced** | ❌ **NOT CLAIMED** — no remediation implemented or verified |
| Credentials rotated / `backend.py` modified | ❌ **NO** |
| Files moved / backups retired / deps installed / keys generated | ❌ **NO** |
| Retention or key policy invented | ❌ **NO** |
| **Dataset import (G1)** | 🔴 **NO-GO — pending qualified P1/P2 review** |
| **Roman Urdu evaluation (G3–G6)** | 🔴 **NO-GO** |
| **Urdu-script evaluation (G7)** | ⏸ **DEFERRED** |

| Quality gate | Cap | Status |
|---|---|---|
| Roman Urdu (`ur-Latn`) | 0.15 | **`NOT PASSED`** |
| Urdu script (`ur-Arab`) | 0.15 | **`NOT PASSED`** |

### Verified vs proposed vs requires-approval

| Category | Items |
|---|---|
| **VERIFIED** (directly measured) | OneDrive sync scope · backup inventory/plaintext/permissions · credential active+valid+privileged+sole · re-seed at `:169-172` · module-scope `init_db()` · auth surface (no lockout/reset, open registration, loopback-only bind) · absent auth telemetry · absent key store · detector result · **27/27 tests** · all invariants |
| **PROPOSED** (specified, not executed) | Credential plan C0–C5 · Storage/backup plans S1–S3 · ordering · test & rollback matrices |
| **REQUIRES APPROVAL** (15 items) | **A1–A5 blocking** · A6–A15 step-gated — see `PHASE415_APPROVALS_REQUIRED.md` |
| **UNVERIFIABLE** (stated as such) | whether files actually uploaded to cloud · historical credential use · prior `blocked` state · whether data ever left this machine |

### Recommended sequence for the approver
1. **A5** appoint legal/privacy reviewer → unblocks G1 and A4
2. **A1 + A2** authorize the auth fix + credential source (closes B17, B18, R-C5)
3. **A4** answer retention D1–D9 (closes B11, enables A8)
4. **A6 + A7** relocate out of OneDrive (closes B15)
5. **A3 + A9** key custody then SQLCipher (closes B14, B10)
6. **A8** retire legacy plaintext backups — **last**, after a verified restore rehearsal (closes B13)

**No gated action was performed. G1 remains NO-GO. G3–G6 remain NO-GO. G7 remains deferred.**
