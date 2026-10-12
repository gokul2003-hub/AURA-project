# AURA Phase 4.16 — Admin Credential Evidence (B17)

**Verdict: the self-healing start-up credential overwrite is REMOVED. No reusable
demo credential remains in startup logic. The live production admin account was
NOT changed — that requires separate authorization and was not performed.**

---

## 1. What was removed

### Before (Phase ≤ 4.15), `init_db()`:

```python
admin_row=c.execute('SELECT id FROM users WHERE lower(username)=lower(?)',('admin',)).fetchone()
if not admin_row:
 h,s=hash_password('<REDACTED>'); c.execute('INSERT INTO users(...) VALUES(?,?,?,?,?)',('admin',h,s,'admin',now()))
else:
 # The project uses one stable demo admin credential. This also repairs databases
 # created by earlier AURA builds that seeded a different password.
 h,s=hash_password('<REDACTED>'); c.execute("UPDATE users SET password_hash=?, salt=?, role='admin', blocked=0 WHERE lower(username)=lower(?)",(h,s,'admin'))
```

The `else` branch — the **normal** case — unconditionally rewrote four columns on
**every service start**.

| Harm | Mechanism |
|---|---|
| Operator password silently reverted | `password_hash`, `salt` overwritten |
| Blocked administrator unblocked | `blocked=0` forced |
| Demoted account re-escalated | `role='admin'` forced |
| Known credential permanent | literal hard-coded, re-applied indefinitely |

### After (Phase 4.16)

```python
admin_row=c.execute('SELECT id FROM users WHERE lower(username)=lower(?)',(DEFAULT_ADMIN_USERNAME,)).fetchone()
 if not admin_row:
  print('[startup] no administrator account present; create one explicitly with `python backend.py provision-admin`.', file=sys.stderr)
```

**No `UPDATE`. No `INSERT`. No credential literal.** Start-up performs **schema
DDL only**.

---

## 2. Source-level verification

| Check | Result |
|---|---|
| Occurrences of the retired demo literal in `backend.py` | **0** |
| Occurrences of `role='admin'` as a *write* | **0** (the single textual hit is an explanatory comment at L301) |
| `INSERT INTO users` statements in the file | **2** — `provision_admin` (role supplied as a **parameter**) and `register` (role hard-coded **`'user'`**) |
| Role writes anywhere | `provision_admin` (explicit, operator-initiated) · `register` (`'user'`) — **no route assigns admin** |
| `getpass` used for interactive input | **Yes** |
| Password printed/logged | **No** — only a `ProvisioningError` message is printed |

---

## 3. New explicit mechanisms

| Function | Guarantee |
|---|---|
| `provision_admin(username, password, interactive)` | Creates **only if absent**; **refuses** to touch an existing account; interactive input via `getpass` (not echoed, not in argv, not in shell history); audits `ADMIN_PROVISIONED` **without secret material** |
| `rotate_credential(username, current, new, actor)` | The **only** sanctioned change path; **requires the current password**; refuses policy violations; **never touches `role` or `blocked`** (rotation is not authorisation); audits `CREDENTIAL_ROTATION` / `CREDENTIAL_ROTATION_DENIED` |
| `_refuse_insecure_password()` | Rejects: empty · shorter than 12 chars · equal to the username · **retired demo-credential shape** (matched by **regex shape**, so the literal is not retained) · fewer than 5 distinct characters |
| `_cli()` + `__main__` guard | `python backend.py provision-admin [--username] [--password]` and `python backend.py status`. **Importing the module does not execute it** |
| `DEFAULT_ADMIN_USERNAME` | Overridable via `AURA_ADMIN_USER`; defaults to `admin` |

---

## 4. Test evidence vs the brief's Stage 3.5 requirements

`tests_p416_import_and_credential_safety.py` — **Ran 35, OK, exit 0.** All DB
tests repoint `backend.DB_PATH` at a temp file.

| Brief requirement | Test(s) | Result |
|---|---|---|
| **First-time provisioning does not create a reusable hard-coded password** | `test_startup_creates_no_administrator` · `test_provisioning_creates_an_administrator_explicitly` · `test_provisioned_password_verifies_and_is_salted` · `test_provisioning_leaves_no_reusable_literal` · `test_weak_and_retired_shapes_are_refused` · `test_password_equal_to_username_is_refused` | ✅ 6/6 |
| **Repeated initialization preserves password hash, role and blocked** | `test_repeated_init_db_preserves_hash_role_and_blocked` (6 simulated restarts) | ✅ |
| **Startup cannot silently unblock** | `test_startup_cannot_silently_unblock` (3 restarts) | ✅ |
| **Startup cannot re-escalate** | `test_startup_cannot_reescalate_demoted_account` (3 restarts) · `test_startup_does_not_create_any_user_when_absent` | ✅ 2/2 |
| **Authorized rotation changes credentials only through the explicit path** | `test_authorized_rotation_changes_only_the_credential` · `test_rotation_never_touches_role_or_blocked` · `test_rotation_requires_current_password_argument` | ✅ 3/3 |
| **Unauthorized rotation rejected** | `test_unauthorized_rotation_is_rejected` · `test_unauthorized_rotation_is_audited_as_denied` · `test_rotation_of_unknown_account_rejected` · `test_rotation_to_same_password_rejected` | ✅ 4/4 |
| **Privilege escalation rejected** | `test_provision_admin_cannot_be_used_to_demote_or_block` · `test_no_route_assigns_the_admin_role` · `test_only_provisioning_and_register_write_roles` · `test_register_route_hard_codes_the_user_role` · `test_login_still_requires_role_and_blocked_checks` | ✅ 5/5 |
| Never log secrets | `test_provisioning_is_audited_without_secret_material` · `test_password_is_never_printed_or_logged` | ✅ 2/2 |
| Schema still idempotent | `test_schema_is_still_created_idempotently` | ✅ |
| Production untouched | `test_production_db_unchanged_by_entire_suite` | ✅ |

### Independent detector re-run (`p15.detect_startup_reseed` on the fixed source)

```
total credential rewrites found: 1
  line   258   scope=rotate_credential   start-up path=False
=> no START-UP reseed remains
```

The single remaining rewrite is the **explicit, caller-initiated** rotation
helper — correctly classified as *not* a start-up path.

> **Detector refinement (a real defect I introduced and fixed):** the original
> heuristic treated *any* non-route function as a start-up path, so it
> misclassified the new `rotate_credential()`. The classifier now models
> **automatic execution** (module scope, `init_db`, `startup`, `on_event`
> hooks) instead of "not a route". Two tests were added to prove it still
> detects the genuine defect and still ignores explicit operator functions.

### P15 detector tests inverted — with justification

Three Phase 4.15 tests asserted the defect **existed**. They now assert it is
**gone**, and one new test feeds a synthetic *buggy* sample to prove the
detector was not neutered (`test_detector_still_detects_the_defect_when_present`).

---

## 5. What was deliberately NOT done

| Item | Status |
|---|---|
| **Changing the live production admin account** | ❌ **NOT DONE** — the brief requires separate explicit authorization. Production still holds its existing credential; **20 users / 1 admin / 2 blocked unchanged** |
| Provisioning a new admin on production | ❌ **NOT DONE** — 0 `ADMIN_PROVISIONED` rows in production |
| Rotating any credential | ❌ **NOT DONE** — 0 `CREDENTIAL_ROTATION` rows |
| Adding a `/auth/change-password` HTTP route | ❌ **NOT DONE** — would expose rotation over HTTP; needs its own authorization and rate-limiting first |
| Login throttling / lockout | ❌ **NOT IMPLEMENTED** — assessed only (see report Stage 4) |
| Auth telemetry (`LOGIN`/`LOGIN_FAILED`) | ❌ **NOT IMPLEMENTED** — assessed only |
| Session invalidation on rotation | ❌ **NOT IMPLEMENTED** — assessed only |
| Migrating `on_event` → lifespan | ❌ **NOT DONE** — pre-existing deprecation, no security impact |

---

## 6. Rollback

A pre-edit copy is held **outside the synced tree**:
`%TEMP%\aura-backend-py416-preedit.bak` (111,834 bytes).

| | SHA256 |
|---|---|
| Before this phase | `bca4c8657ffaba5a19197c88027aeb65105bdf70546c185138f925acdd946303` |
| After this phase | `0275953c6bdf24c64186f59479734f965658526e7e19dc09bed3f3f0073700d1` |

Rollback = copy the `.bak` back over `backend.py`. The running service
(pid 16944, started 11:08:25) holds the **old** code in memory and was **not
restarted**, so it is unaffected by this edit until it next restarts — at which
point the **new, safe** `init_db()` runs.

---

## 7. Explicit statements

| Item | Status |
|---|---|
| Reusable demo credential in startup logic | ❌ **REMOVED — 0 occurrences** |
| Start-up overwrites password/role/blocked | ❌ **REMOVED — no `UPDATE users` in any automatic path** |
| First-time provisioning explicit, no default credential | ✅ **IMPLEMENTED + TESTED** |
| Rotation only via explicit, current-password-gated path | ✅ **IMPLEMENTED + TESTED** |
| Privilege escalation possible via these paths | ❌ **REJECTED — 5/5 tests** |
| Security tests on isolated fixtures | ✅ **35/35, temp DBs, synthetic data** |
| **Production admin account changed** | ❌ **NO — separate authorization required** |
| Exposure reduced | 🟡 **Partially — the self-healing defect is fixed and verified; the live credential itself is unchanged and still must be rotated (needs A2)** |
