# AURA Phase 4.17 — Session Security Evidence (B22)

**Control:** B22 — sessions must be revocable and must not survive a credential
rotation. Complements Phase 4.16 (import-safe init + credential hardening).

**Suite:** `CODE/BACKEND/tests_p417_session_security.py` — **29 tests, 29 OK**.
All against a **temporary database**; synthetic accounts and synthetic passwords
only. No dataset, no model, no frozen artifact, no network, no write-capable
HTTP request to the live service.

---

## 1. Mechanism

Sessions are opaque bearer tokens held in an in-memory map. Phase 4.16 proved a
rotation left previously minted tokens valid; Phase 4.17 binds every session to
the user's persisted **`credential_version`**.

| Change | Purpose |
|---|---|
| `users.credential_version` (additive column) | durable counter, bumped on rotation |
| `current()` re-checks version on **every** request | a stale token is rejected at use-time |
| `revoke_sessions()` / `purge_user_sessions()` | bump the counter → every live token dies |
| `SESSION_TTL_SECONDS = 43200` (12 h) | bound token lifetime even if never revoked |

Revocation therefore **survives a process restart**: the decision is read from
the database, not from process memory.

### Fail-closed expiry

Missing or unparseable `created_at` **rejects** the session. This was not the
initial behaviour — an early implementation returned `False` on a parse failure,
which *failed open*. A test in this suite caught it; the code now rejects.

---

## 2. Properties proven (29 tests)

| # | Property | Result |
|---|---|---|
| 1 | A live session is accepted by protected endpoints | ✅ |
| 2 | **Revoked** session rejected by `current()` | ✅ |
| 3 | **Revoked** session rejected by `admin()` | ✅ |
| 4 | Revocation **survives a simulated restart** (version re-read from DB) | ✅ |
| 5 | Rotation invalidates every token minted before it | ✅ |
| 6 | Token minted *after* rotation is valid | ✅ |
| 7 | Expired token rejected (`SESSION_TTL_SECONDS` enforced) | ✅ |
| 8 | Missing/garbage `created_at` **fails closed** | ✅ |
| 9 | Tampered/unknown token rejected | ✅ |
| 10 | Revoking one user does not kill another user's session | ✅ |
| 11 | Session state is per-user, not global | ✅ |
| 12 | No secret/token material is logged by session code | ✅ |
| 13 | Revocation endpoints require admin (non-admin → 403) | ✅ |

Each row is backed by one or more named tests; see the suite for exact names.

---

## 3. Audit events emitted

| Event | When | Detail recorded |
|---|---|---|
| `SESSIONS_REVOKED` | `revoke_sessions()` / rotation purge | target user id + count |

No token, hash, or password value is ever placed in an audit record. A static
AST check in part B enforces this across every `audit_log()` call.

---

## 4. Isolation guarantees

- `backend.DB_PATH` repointed to a temp file in `setUp`; restored in `tearDown`.
- `backend.SESSIONS` cleared per test.
- `TestProductionUntouched` opens production with `mode=ro` only.
- A dedicated guard test asserts the isolation harness has repointed `DB_PATH`
  **away** from `aura.db` before any write-capable code runs.

---

## 5. Production impact — none

Verified read-only after the suite:

| Check | Value |
|---|---|
| `login_attempts` table in production | **absent** (migration not applied) |
| `users.credential_version` in production | **absent** (migration not applied) |
| `LOGIN_SUCCESS`/`LOGIN_FAILED`/`SESSIONS_REVOKED` rows | **0** |
| Users / admins / blocked | 20 / 1 / 2 |
| `PRAGMA integrity_check` | **ok** |
| Engine | **legacy** (unchanged) |
| Live service (pid 16944, started 11:08:25) | **never restarted**; `GET /health` → 200 |

The additive migration must **never** be run against production without separate
approval; the suite asserts it is absent.

---

## 6. What this does NOT establish

- **No claim of complete session or authentication security.** These 29 tests
  prove the 13 properties above and nothing more.
- **Not verified:** token entropy quality, in-memory map behaviour under real
  concurrency/multi-worker deployment, TLS/token transport, client-side storage,
  and replay via any channel other than the token itself.
- The throttle **thresholds are PROPOSED DEFAULTS, not approved policy.**
