# AURA Phase 4.15 — Credential Remediation Plan (B17 + related)

**PROPOSAL ONLY. Nothing implemented. `backend.py` was not modified; no
credential was rotated, displayed, or copied; the production database was not
written.**

Companion prototype: `CODE/BACKEND/p15_credential_remediation.py` +
`tests_p15_credential_remediation.py` (**27/27 pass, exit 0**, isolated temp DBs,
synthetic fixtures, `backend` never imported).

---

## 1. Verified findings (read-only evidence)

### 1a. The demo credential is ACTIVE, VALID, PRIVILEGED and SOLE

| Check | Result |
|---|---|
| `role` | **`admin`** |
| `blocked` | **`0` — active** |
| `created_at` | `2026-09-02T09:10:06Z` (account is ~5 weeks old) |
| **stored hash == seeded hash** | **`True`** — *(compared in memory; the value is never printed)* |
| Other admin accounts | **none** — this is the only admin |
| Total users / blocked | 20 / 2 |

### 1b. It is not merely seeded — it is **re-imposed on every start-up**

`backend.py:166-172` (`init_db`):

| Branch | Behaviour |
|---|---|
| admin absent | seeds it (expected) |
| **admin present (the normal case)** | **`UPDATE users SET password_hash=?, salt=?, role='admin', blocked=0 WHERE …`** |

Comment at `:170-171` states this is deliberate: *"The project uses one stable
demo admin credential. This also repairs databases created by earlier AURA
builds…"*

**Consequences (all demonstrated by the prototype):**
1. **Any password the operator sets is silently reverted at next start-up.**
2. **A blocked admin is unblocked** (`blocked=0`) at next start-up — blocking
   the admin account is unenforceable.
3. **A demoted admin is re-escalated** (`role='admin'`).
4. The credential is therefore **permanent and self-healing**, not a one-time
   seed.

### 1c. It also runs on **import**, not just start-up

`backend.py:1088` calls `init_db()` at **module scope**, and there is **no
`if __name__ == '__main__'` guard** (verified: absent).

> **B18 (new):** **`import backend` performs a production write.** Any test or
> script that imports the module without first redirecting `DB_PATH` rewrites
> the live admin credential and unblocks the account. This is a **direct hazard
> to the regression-isolation rule** and likely contributed to the Phase 4.12
> class of incidents.

### 1d. Static detector (executes nothing)

`p15_credential_remediation.detect_startup_reseed()` run read-only against the
real source:

```
findings: 1
line   172   scope=init_db   start-up path=True
```

The classifier also correctly **declines** to flag route-scoped rotations
(tested), so a future legitimate change-password endpoint will not be mis-reported.

### 1e. Authentication surface

| Property | Finding | Assessment |
|---|---|---|
| Password storage | PBKDF2-HMAC-SHA256, **150,000** iterations, per-user salt (`:162`) | ✅ sound |
| Login response | single generic `401 'Invalid credentials.'` (`:1109`) | ✅ no username oracle |
| Login checks | `blocked`, `role`, password (`:1109`) | ✅ correct order |
| **Rate limiting / lockout** | **none** | 🔴 brute-force feasible |
| **Password change / reset endpoint** | **none exists** (routes: `/auth/login`, `/auth/register`, `/admin/block-user`, `/admin/verify/{mid}`) | 🔴 no user-driven rotation path |
| **Registration** | **open** — anyone can create an account; `role` hard-coded `'user'` (`:1117`) | 🟡 no privilege escalation, but unbounded account creation |
| **Session tokens** | in-memory `SESSIONS` map only (`:182`); not persisted | ✅ no token at rest |
| **Network bind** | **`127.0.0.1:8010` only**; no `0.0.0.0`/`::` listener | ✅ **localhost-only** — genuine mitigating factor |
| **Audit of authentication** | **no `LOGIN`/`LOGIN_FAILED` actions exist** (distinct actions observed: `ADMIN_VERIFY`, `BLOCK_USER`, `ENGINE_CHANGE`, `HUMAN_REVIEW`, `MODERATION_DECISION`) | 🔴 **no authentication telemetry** |

### 1f. Evidence of external exposure — **NOT VERIFIABLE**

| Question | Status |
|---|---|
| Has the credential been used externally? | **NOT VERIFIED — cannot be determined.** The audit trail records **no authentication events at all**, so neither use nor misuse is observable |
| Was the service ever reachable off-machine? | **NOT VERIFIED.** Currently bound to loopback only; a tunnel, port-forward or reverse proxy would not be visible from the code or DB |
| Are there other admin accounts to check? | **No** — one admin, so scope is bounded |
| Was the account blocked at any point? | **NOT VERIFIABLE** — `blocked` is overwritten to `0` on each start, destroying prior state |

> **Honest conclusion:** the credential's exposure **cannot be measured**. The
> correct statement is *"unknown, and not instrumented"*, not *"no exposure"*.
> The absence of login telemetry is itself a finding, and remediation item
> **R1.5** addresses it.

---

## 2. Remediation plan

### Stage C0 — Preconditions (ALL 🔴 before any change)

| # | Precondition | Status |
|---|---|---|
| **C0.1** | **Written authorization to modify `backend.py`** (authentication behaviour) | 🔴 **NOT OBTAINED** — brief forbids modifying auth behaviour without it |
| **C0.2** | **New admin credential source** decided (operator-supplied, or first-boot secret generated once and shown once). **Must not be a literal in source** | 🔴 **NOT DECIDED** |
| **C0.3** | **Retention decision (B11)** answered — governs how long rotated credentials/audit rows are kept | 🔴 **UNANSWERED** |
| **C0.4** | **P1/P2 qualified review** (G1) | 🔴 **PENDING** |
| **C0.5** | Decide whether the demo account remains an admin at all | 🔴 **NOT DECIDED** |
| **C0.6** | Decide policy for the 19 non-admin accounts (retain / purge / freeze) | 🔴 **NOT DECIDED** |
| **C0.7** | Confirm the deployment runs as a service whose restart is coordinated | 🔴 **UNCONFIRMED** |

### Stage C1 — Rotation (after C0)

| Step | Action | Guard |
|---|---|---|
| 1 | Stop the service (**stop before rotating**, or the next import/start re-seeds) | service down confirmed |
| 2 | Rotate via an **explicit, audited** path — `rotate_password()` (prototype), writing `PASSWORD_ROTATION` with **counts-only** details | audit row present; **no secret in the row** |
| 3 | **Block the old credential's usability** — with C2 applied, it can no longer return | verified by test |
| 4 | Reconcile `C0.5`/`C0.6` | account roles reviewed |
| 5 | Record the change (actor, time, scope, before/after **row counts and hashes-of-hashes**, never the secret) | appended to audit evidence |

### Stage C2 — Remove the start-up re-seed (after C1)

Replace the `else` branch at `backend.py:169-172` with **seed-once semantics**:
create only when absent; **never** rewrite `password_hash`, `salt`, `role`, or
`blocked` on start-up. The prototype's `ensure_admin_account()` is the specified
behaviour, including "the password factory is never invoked for an existing
account".

| Step | Action |
|---|---|
| 1 | Apply the seed-once branch |
| 2 | Move `init_db()` behind an explicit call (**fixes B18**): import must not write |
| 3 | Add a **route-scoped** `/auth/change-password` (own account only, current password required, audited) — closes the "no rotation path" gap |
| 4 | Add `LOGIN` / `LOGIN_FAILED` audit actions with **counts and usernames only — no IPs, no passwords** (closes §1f's observability gap) — *subject to B11 retention* |
| 5 | Optional, needs separate approval: registration lockdown, and login lockout/backoff |

### Stage C3 — Verification (isolated only)

| ID | Test | Pass criterion |
|---|---|---|
| **T-C1** | `ensure_admin_account` twice on a temp DB | second call **preserves** hash |
| **T-C2** | Rotate → 3 restarts on temp DB | password **unchanged** |
| **T-C3** | Block admin → 3 restarts | **stays blocked** |
| **T-C4** | Demote → restart | role **not** re-escalated |
| **T-C5** | Rotation audited, secret-free | `PASSWORD_ROTATION` row, no secret-bearing keys |
| **T-C6** | **`import backend` does not write production** (B18 regression) | production `aura.db` mtime and admin hash **unchanged** across import |
| **T-C7** | Detector reports **zero** start-up paths post-change | `detect_startup_reseed()` → no `is_start_up_path=True` |
| **T-C8** | Existing suites still green | P3 36, P5 23, P15 27 |

> ⚠️ **T-C6 is currently IMPOSSIBLE to satisfy** — importing `backend` writes
> production (§1c). This is precisely why C2 step 2 must land *before* any
> future import-based test is attempted.

**All of T-C1…T-C5 are already passing in the isolated prototype (27/27).**

### Stage C4 — Rollback triggers

| ID | Trigger | Response |
|---|---|---|
| **R-C1** | Old credential still validates after rotation | **ABORT** — rotation incomplete |
| **R-C2** | New credential does not validate | **ABORT → R-C5** |
| **R-C3** | `blocked=1` admin can still authenticate | **ABORT** — access control broken |
| **R-C4** | Any non-admin gains admin role | **ABORT** |
| **R-C5** | Operator locked out (no credential works) | **recover from verified backup** (see storage plan) — the demo credential previously acted as an accidental break-glass; **removing it removes that backstop**, so a break-glass procedure must exist **before** C1 |

### Stage C5 — Rollback

| Step | Action |
|---|---|
| 1 | Stop service |
| 2 | Revert the `backend.py` edits (only the C2 lines; file is uncommitted — **copy aside first, no VCS exists**) |
| 3 | Restore the pre-change DB backup (SHA256-verified) — **see storage plan** |
| 4 | Verify invariants: engine `legacy`, 596 rows, splits 137/29/31+399, 8 runs, 12 versions, `improved_v10`, integrity `ok`, protected hashes, frozen splits |
| 5 | **Record the rollback** — never silently erase the evidence |

**Honest limitation:** rollback **restores the known credential**. That is an
availability action, not a security improvement, and it must be time-boxed.

---

## 3. Decision-makers

| Decision | Who must authorize |
|---|---|
| Modify authentication behaviour (`backend.py`) | **User / project owner**, in writing |
| New credential source & break-glass procedure | **User / project owner** (C0.2, R-C5) |
| Whether the demo account stays admin | **User / project owner** (C0.5) |
| Disposition of the 19 other accounts | **User / project owner** (C0.6) |
| Login telemetry & retention of auth audit rows | **Qualified legal/privacy reviewer** (feeds B11/P2) |
| Registration lockdown / lockout policy | **User / project owner** |
| Any claim of reduced exposure | **Requires implemented + verified remediation** — cannot be claimed now |

---

## 4. Explicit status

| Item | Status |
|---|---|
| Credential rotated | ❌ **NO** |
| `backend.py` modified | ❌ **NO** |
| Reseed removed | ❌ **NO** |
| Credential displayed/copied | ❌ **NO** |
| Production DB written | ❌ **NO** |
| Exposure reduced | ❌ **NO — not claimed** |
| Plan specified | ✅ **YES — C0–C5 with triggers and owners** |
| Prototype + tests | ✅ **27/27, isolated, synthetic** |
| Requires approval | 🔴 **C0.1–C0.7** |
