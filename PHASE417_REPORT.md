# AURA Phase 4.17 — Session Invalidation, Auth Telemetry & Login Throttling

**Status:** ✅ **COMPLETE** (security/remediation chain)
**Follows:** Phase 4.16 — import-safe init + admin credential hardening
**Engine:** `legacy` (unchanged) · **Production:** untouched (verified, §7)

> **This phase makes no claim of complete authentication or session security.**
> It proves the specific properties listed in §5 and no others. Throttle
> thresholds are **proposed defaults, not approved policy** (§6).

---

## 1. Objective

Close **B22** (sessions survived credential rotation) and add auditable
authentication telemetry plus brute-force resistance — using **isolated tests
only**, with **zero** production mutation, no restart, and no write-capable HTTP
request to the live service.

| In scope | Out of scope |
|---|---|
| Session binding, revocation, expiry (B22) | Dataset / eval / retrain / deploy / threshold tuning |
| `LOGIN_SUCCESS` / `LOGIN_FAILED` / `SESSIONS_REVOKED` telemetry | Production credential rotation (A2 — needs authorization) |
| Login throttling (proposed defaults) | Migrations against production, encryption, relocation |
| Additive schema in **temp** DBs only | Any change to Phase 4.12 incident records |

---

## 2. Changes to `backend.py`

SHA-256 `bca4c865…` (pre-4.16) → `0275953c…` (post-4.16) → **`48f40943…`
(post-4.17)**. Rollback copy: `%TEMP%\aura-backend-py417-preedit.bak`.

| Area | Change |
|---|---|
| **Session binding** | tokens bound to persisted `users.credential_version`; `current()` re-checks on every request → **revocation survives restart** |
| **Revocation** | `revoke_sessions()` / `purge_user_sessions()` bump the version; every prior token dies at use-time |
| **Expiry** | `SESSION_TTL_SECONDS = 43200`; missing/unparseable `created_at` **fails closed** (rejected) |
| **Telemetry** | `LOGIN_SUCCESS`, `LOGIN_FAILED` (reason label only), `SESSIONS_REVOKED` audit events |
| **Throttling** | `_backoff_seconds()`, `is_login_locked()`, `record_login_failure()`, `clear_login_failures()`, `prune_login_attempts()` |
| **Schema** | additive `login_attempts` table + `users.credential_version`; idempotent |

**Import safety preserved:** `init_db()` remains inside the `@app.on_event("startup")`
hook. AST audit + subprocess connect-trap confirm **0 module-scope DB calls** —
`import backend` performs no database work.

### Defect found and fixed this phase

`login_attempts` had **no pruning**, so every distinct attacker-chosen username
left a permanent row (unbounded table growth). `record_login_failure()` now
deletes expired rows opportunistically. Pruning touches **only expired**
counters, so it never forgives a live failure.

---

## 3. Test diagnostic (truncated file)

The first authored test file was discovered as **0 tests**. Forensics: 3,758 B /
109 lines / SHA `b9a3e0bf…`, ended at a literal `__PART2__` marker with only the
`_Isolated` base class — no `Test*` class, hence no `test_*` methods, hence a
clean "Ran 0 tests". Embedded `.pyc` source-size (3,758) and mtime (22:16:12)
match the stub exactly with **zero** Test classes, so the intended content
survives in **no on-disk artifact**. OneDrive placeholder/conflict copies were
**ruled out**. The stub was **preserved** as
`tests_p417_session_and_auth_hardening.py.truncated-20261012.bak`, not deleted.

The recorded `TypeError: 'sqlite3.Row' object does not support indexing: 'blocked'`
**cannot** come from the current backend: CPython raises `IndexError: No item
with that key` (never `TypeError`, never embedding the key), and the referenced
site was a `SELECT`. It reflects a transient in-flight `backend.py` state; its
exact provenance is **unverified**. Full analysis: `PHASE417_TEST_DIAGNOSTIC.md`.

---

## 4. What was repaired in the suites

Five initial failures in part B were diagnosed, not suppressed:

| Failure | Verdict | Action |
|---|---|---|
| AST audit false-positive | **test bug** — parent `Dict` node unparsed its own literal labels | detector now skips containers/literals; **liveness test added** so it can't be neutered |
| 7 ≠ 5, 8 ≠ 5 counters | **by design** — throttle short-circuits before verification, so the counter caps at 5 | rewritten to test the real invariant (uniformity + accumulation **below** threshold) + explicit capping test |
| stale row not pruned (1 ≠ 0) | **real production weakness** | **fixed in `backend.py`** (§2) |
| `DB_PATH != production` | **test placement bug** — `TestProductionUntouched` isn't `_Isolated`, so the path is production by design | isolation assertion moved into `_Isolated`; replaced with a real "production file unchanged during suite" (size+mtime) check |

---

## 5. Results — 186 tests, all passing

| Suite | Tests | Result |
|---|---|---|
| `tests_p3_privacy.py` | 36 | ✅ OK |
| `tests_p5_cascade_deletion.py` | 23 | ✅ OK |
| `tests_p15_credential_remediation.py` | 28 | ✅ OK |
| `tests_p416_import_and_credential_safety.py` | 35 | ✅ OK |
| `tests_p417_session_security.py` | **29** | ✅ OK |
| `tests_p417_auth_hardening.py` | **35** | ✅ OK |
| **Total** | **186** | **✅ exit 0** |

Recovered from the truncated stub: **0 → 64** Phase 4.17 tests.

**Proven properties (and only these):** revoked/rotated/expired/tampered sessions
rejected by protected endpoints (revocation survives restart); failed or
unauthorized rotations change nothing; auth logs contain no secret material
(statically enforced + liveness-tested); throttling is per-account, uniform
(anti-enumeration), delay-not-lockout (anti-DoS), capped, and bounded in table
growth; additive migration is idempotent and absent from production.

---

## 6. Proposed defaults — NOT approved policy

`LOGIN_BACKOFF_BASE_SECONDS=30`, `LOGIN_BACKOFF_MAX_SECONDS=900`,
`LOGIN_FAILURE_WINDOW_SECONDS=900`, `SESSION_TTL_SECONDS=43200`.

Backoff begins only after 5 failures (0 s before), doubles to a 900 s cap, and
**never becomes a permanent lockout** (a freeze would let any unauthenticated
caller deny service to the sole administrator). **These require an explicit
policy decision.**

---

## 7. Production invariants — verified unchanged

Read-only sweep after all work:

| Check | Value |
|---|---|
| Engine | **legacy** |
| `PRAGMA integrity_check` | **ok** |
| users / admins / blocked | **20 / 1 / 2** |
| audit_logs / moderation_results | **1682 / 1630** |
| training_runs / model_versions / dataset_samples | **8 / 12 / 596** |
| `DATA_ERASURE` | **0** |
| Phase 4.16 + 4.17 auth events | **0** |
| `login_attempts` / `credential_version` | **absent** (migration never applied) |
| Hashes `f31f4975…` / `5a9d94e2…` / `f3a5ceb4…` | **MATCH** |
| Frozen `ur_test.csv` / `ur_val.csv` | **74,991 B / 51,366 B — unchanged** |
| Live service (pid 16944, 11:08:25) | **never restarted**; `GET /health` → 200 |

No credential, hash, salt, token, or raw message text was printed or copied.

---

## 8. Unverified behaviours (explicit)

- **Root cause of the original truncation** — unverified (large-single-write is
  consistent but **not proven**).
- Provenance of the non-standard `TypeError` — unverified.
- Token entropy quality; multi-worker/multi-process session-map consistency;
  TLS/transport and client-side storage; timing side-channels in `verify_password`;
  distributed (slow) brute force across many addresses; credential stuffing with
  valid passwords.
- **Retention of `login_attempts` and telemetry counters is governed by
  unresolved A4 (D1–D9).**

---

## 9. Blockers & gates — UNCHANGED

| Item | Status |
|---|---|
| **A5 / P1+P2** lawful basis | 🔴 open → **root blocker for G1** |
| **A2** live credential rotation | 🔴 not authorized this phase |
| **A3/A9** key custody + SQLCipher · **A4** retention · **A6/A7** relocation · **A8** backup retirement | 🔴 open |
| **B1, B2, B3, B4, B5, B6, B8, B9** (B7/C1 deferred) | 🔴 open |
| Gate **G1** | 🔴 NO-GO · **G2** READY · **G3–G6** 🔴 NO-GO · **G7** deferred |
| Quality gates `ur-Latn` / `ur-Arab` | **both `NOT PASSED`** (`ur-Arab` — no corpus) |

`ur-Latn` and `ur-Arab` are never pooled. Gates G1–G7 unchanged.

---

## 10. Recommended next actions (NOT performed)

1. **A2** — authorize live admin credential rotation (separate approval).
2. **A5** — appoint a qualified legal/privacy reviewer to close P1/P2 (unblocks G1).
3. Approve or amend the **throttle thresholds** (§6) as policy.
4. Resolve **A4 retention** for `login_attempts` and telemetry counters.
5. Consider running future suites only against **isolated backend copies**.

**Artifacts:** `PHASE417_REPORT.md` · `PHASE417_TEST_DIAGNOSTIC.md` ·
`PHASE417_SESSION_SECURITY_EVIDENCE.md` · `PHASE417_AUTH_TELEMETRY_EVIDENCE.md`
· updated `PHASE411_BLOCKER_REGISTER.md`.
