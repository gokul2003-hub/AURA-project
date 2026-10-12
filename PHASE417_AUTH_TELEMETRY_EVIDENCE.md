# AURA Phase 4.17 — Authentication Telemetry & Login Throttling Evidence

**Controls:** auditable authentication events (no secret material) and
brute-force resistance that does **not** create an admin denial-of-service.

**Suite:** `CODE/BACKEND/tests_p417_auth_hardening.py` — **35 tests, 35 OK**.
Temporary database, synthetic accounts and synthetic passwords only. No dataset,
model, frozen artifact, network, or write-capable HTTP request to the live
service.

---

## 1. Telemetry

| Event | Emitted on | Recorded detail |
|---|---|---|
| `LOGIN_SUCCESS` | successful authentication | username, role |
| `LOGIN_FAILED` | any rejected login | username, **machine-readable reason only** |
| `SESSIONS_REVOKED` | revocation / rotation purge | target id, count |

Reason labels are literals such as `unknown_user`, `blocked`, `role_mismatch`,
`bad_password`, `throttled` — **never** the attempted password, hash, or salt.

### No secret material — enforced statically

A dedicated AST test walks every `audit_log()` call and fails if any argument
could carry live secret material (variable, attribute, or subscript mentioning
password/passwd/salt/token/secret). String **literals are exempt** because they
are reason labels, not secret values — without this exemption the legitimate
label `current_password_mismatch` was a false positive.

A **liveness test** parses a synthetic leaky sample and asserts the detector
still flags it, so the check cannot be silently weakened into a no-op.

---

## 2. Throttling — exponential backoff, never a lockout

| Parameter | Value | Status |
|---|---|---|
| `LOGIN_BACKOFF_BASE_SECONDS` | 30 | **PROPOSED DEFAULT** |
| `LOGIN_BACKOFF_MAX_SECONDS` | 900 (15 min) | **PROPOSED DEFAULT** |
| `LOGIN_FAILURE_WINDOW_SECONDS` | 900 | **PROPOSED DEFAULT** |
| Delay before 5 failures | **0** | — |
| Delay shape | 30 s doubling (5→30 s, 6→60 s …) capped at 900 s | — |

**These values are proposed defaults, NOT approved policy.** They require an
explicit policy decision before being treated as production thresholds.

### Design decisions proven by test

| Property | Rationale |
|---|---|
| Delay, **not** a permanent lockout | a freeze would let any unauthenticated caller deny service to the **sole administrator** by triggering failed logins |
| Account recovers after the window elapses | DoS resistance |
| Backoff is **capped** at 900 s | bounded worst case |
| **0 s delay** for the first 4 failures | no penalty for ordinary typos |
| Throttled response is **byte-identical** to a bad password | the delay is the only observable difference |
| **Unknown usernames are tracked identically** | otherwise the delay becomes an account-enumeration oracle |
| Throttling is **per-account** | one account's failures do not affect another |
| Successful login **clears** the counter | legitimate user is not punished |
| Counter **restarts** after the window | rolling, not lifetime, tally |
| Blocked account is **not revealed** by throttling | indistinguishable 401 |
| Attempt table **never stores the password** | attack strings are not persisted |
| **Stale rows pruned** | bounds table growth from attacker-chosen names |

### Counter capping (by design)

Throttling is checked **before** credential verification, so once an account is
inside its backoff window further attempts are rejected without running PBKDF2
and without incrementing the counter. The counter therefore **caps at 5** during
a window rather than climbing forever. Two tests pin this explicitly so the
capping is not mistaken for lost updates.

### Table-growth bound

A weakness found by test was **fixed** this phase: `login_attempts` had no
pruning, so every distinct attacker-chosen username left a permanent row (an
unbounded-growth vector). `record_login_failure()` now opportunistically deletes
rows whose window has expired. Pruning removes only **expired** counters, so it
never forgives a live failure.

---

## 3. Schema

Additive and idempotent (verified by running `init_db()` twice):

- `login_attempts(username, fail_count, first_fail_at, last_fail_at, locked_until)`
- `users.credential_version` (default 0 for existing rows)

Both are additive migrations that must **never** run against production without
separate approval; tests assert their absence from production.

---

## 4. Production impact — none

Verified read-only: `login_attempts` **absent**, `credential_version` **absent**,
0 authentication events, users/admins/blocked = 20/1/2, `integrity_check` **ok**,
engine **legacy**, protected hashes `f31f4975…` / `5a9d94e2…` / `f3a5ceb4…`
unchanged, frozen `ur_test.csv` (74,991 B) and `ur_val.csv` (51,366 B) untouched,
live service never restarted, `GET /health` → 200.

---

## 5. What this does NOT establish

- **No claim of complete authentication or telemetry security.** Only the
  asserted properties are proven.
- **Not verified:** resistance to distributed (slow) brute force across many
  source addresses, timing side-channels in `verify_password`, credential
  stuffing with valid passwords, and multi-worker/multi-process consistency of
  the in-memory session map.
- **Retention (A4/D1–D9) governs `login_attempts` and the telemetry counters**
  and is unresolved; these tables are currently unbounded in time.
- Throttle thresholds remain **proposed defaults pending policy approval.**
