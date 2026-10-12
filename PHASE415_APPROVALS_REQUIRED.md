# AURA Phase 4.15 — Approvals Required

**Consolidated register of every decision blocking remediation of B13, B14,
B15, B17 (and B18). No approval is claimed for any item. Nothing below has been
granted.**

Status key: 🔴 **BLOCKING** (work cannot proceed) · 🟡 **required before the
step that depends on it** · ⏸ deferred.

---

## 1. Blocking approvals

| ID | Decision required | Why it blocks | Who must authorize | Status |
|---|---|---|---|---|
| **A1 / C0.1** | **Authorize modifying `backend.py` authentication behaviour** (remove start-up re-seed at `:169-172`; move `init_db()` off module scope at `:1088`) | The brief forbids changing auth behaviour without explicit authorization. **B17 and B18 cannot be fixed without it** | User / project owner, in writing | 🔴 **NOT OBTAINED** |
| **A2 / C0.2** | **Choose the new credential source** (operator-supplied, or one-time generated-and-shown-once) **and a break-glass procedure** | Removing the demo credential removes the only known fallback; without break-glass the operator could be locked out (**R-C5**) | User / project owner | 🔴 **NOT DECIDED** |
| **A3 / S3.0 (B14)** | **Key-custody policy**: where the key lives, custodian + deputy, cold-start provisioning, recovery procedure, rotation trigger | Nothing exists to hold a key. **No policy is invented here.** Loss of key = **permanent data loss** | User / project owner (+ security reviewer) | 🔴 **NOT DECIDED** |
| **A4 / B11** | **Retention end date / duration, D1–D9**, incl. audit evidence (D7) and backups | Governs backup retirement, auth-audit retention, and P2.12. **No duration invented** | Qualified legal/privacy reviewer | 🔴 **UNANSWERED** (open since Phase 4.13) |
| **A5** | **Appoint the qualified legal/privacy reviewer** (P1/P2) | Root blocker for **G1**; also ratifies A4 | User / project owner | 🔴 **NOT APPOINTED** |

---

## 2. Required before the dependent step

| ID | Decision required | Dependent step | Who | Status |
|---|---|---|---|---|
| **A6 / S1.0** | **Destination for relocation out of OneDrive sync** | Plan S1 (B15) | User / project owner | 🔴 **NOT DECIDED** |
| **A7 / S1.5** | **Authorize repointing `DB_PATH`** (`backend.py:11`, currently hardcoded) | Plan S1 step 5 | User / project owner | 🔴 **NOT OBTAINED** |
| **A8 / S2.2** | **Authorize retiring the 3 legacy plaintext backups**, naming each file | Removing 22.3 MB of plaintext PII (B13) | User / project owner | 🔴 **NOT OBTAINED** — *and must come after a verified successor backup* |
| **A9 / S3.1** | **Authorize installing a SQLCipher build for Python 3.14/Windows** | Encryption (B10) | User / project owner | 🔴 **NOT OBTAINED** |
| **A10 / C0.5** | **Does the demo account remain an admin?** | Credential plan Stage C1 | User / project owner | 🔴 **NOT DECIDED** |
| **A11 / C0.6** | **Disposition of the other 19 accounts** (2 blocked) | Credential plan Stage C1 | User / project owner | 🔴 **NOT DECIDED** |
| **A12 / C2.4** | **Add authentication audit events** (`LOGIN` / `LOGIN_FAILED`, counts + usernames only, no IPs) — retention governed by A4 | Observability of exposure | User + legal/privacy reviewer | 🔴 **NOT OBTAINED** |
| **A13** | **Registration lockdown and/or login lockout policy** | Hardening (optional, separately approvable) | User / project owner | 🔴 **NOT DECIDED** |
| **A14 / S2.0.2** | **Make backup failures loud** (`backup_db()` currently swallows errors) | Reliable protected backups | User / project owner | 🔴 **NOT OBTAINED** |
| **A15** | **Endpoint wiring for deletion (R1)** — carried from Phase 4.12/4.13 | HTTP erasure capability | User / project owner | 🔴 **NOT OBTAINED** |

---

## 3. Explicitly NOT claimed, NOT done

| Item | Status |
|---|---|
| Any approval above granted | ❌ **NONE** |
| Exposure reduced | ❌ **NO — not claimed**; no remediation implemented or verified |
| Credentials displayed, copied or rotated | ❌ **NO** |
| `backend.py` / auth behaviour modified | ❌ **NO** |
| Files moved, deleted, renamed or re-permissioned | ❌ **NO** |
| Backups created, altered or retired | ❌ **NO** |
| Production DB written / migrated | ❌ **NO** |
| Dependency installed | ❌ **NO** |
| Production key generated | ❌ **NO** |
| Retention duration or key policy invented | ❌ **NO** |
| Security control disabled | ❌ **NO** |
| Dataset import / eval / training / threshold / deploy | ❌ **NONE** |

---

## 4. Verification status after this phase

| Gate | Prerequisite | Status |
|---|---|---|
| **G1** lawful import | **A5 → A4** (P1/P2 review, retention) | 🔴 **NO-GO** |
| **G2** mapping freeze | — | 🟢 **READY** |
| **G3** redaction & preprocessing | P4b runtime · **A3 + A9** (key custody, encryption) · **A4** (retention) · **A15** (endpoint) | 🔴 **NO-GO** |
| **G4** leakage-safe split | G1 | 🔴 **NO-GO** |
| **G5** hash freeze | G4 | 🔴 **NO-GO** |
| **G6** single evaluation | G1–G5 | 🔴 **NO-GO** |
| **G7** `ur-Arab` | C1 commissioning + compensation | ⏸ **DEFERRED** |

| Quality gate | Cap | Status |
|---|---|---|
| Roman Urdu (`ur-Latn`) | 0.15 | **`NOT PASSED`** |
| Urdu script (`ur-Arab`) | 0.15 | **`NOT PASSED`** |

---

## 5. Recommended sequence for the approver

1. **A5** — appoint the legal/privacy reviewer (unblocks G1 and A4).
2. **A1 + A2** — authorize the auth fix and choose the credential source
   (closes B17, B18, and the lockout risk R-C5).
3. **A4** — answer retention D1–D9 (closes B11, enables backup retirement A8).
4. **A6 + A7** — relocate out of OneDrive (closes B15).
5. **A3 + A9** — key custody, then SQLCipher (closes B14, B10).
6. **A8** — retire the legacy plaintext backups, only after a verified successor
   backup (closes B13).

> Each step is independently authorizable and independently reversible except
> **A8** (retirement), which must be last and must be preceded by a verified
> restore rehearsal.
