# AURA Phase 4.16 — Import-Safety Evidence (B18)

**Verdict: `backend.py` import was ALREADY side-effect-free with respect to the
database. Phase 4.15's B18 was WRONG and is RETRACTED here.**

Everything below is read-only static analysis (AST) plus an isolated
subprocess proof. **No production write was performed to obtain it.**

---

## 1. Correction of the Phase 4.15 finding

| Phase 4.15 claim | Reality (Phase 4.16) |
|---|---|
| *"`backend.py:1088` calls `init_db()` at **module scope**; no `if __name__` guard"* | ❌ **Wrong.** The call is inside `@app.on_event('startup')` → `def startup():` (L1086-1100) |
| *"`import backend` performs a production write"* | ❌ **Wrong.** `startup()` is an **ASGI lifecycle hook**; it runs when the server begins serving, **not** at import |
| *"This is a direct hazard to the regression-isolation rule"* | ⚠️ **Partly withdrawn.** The hazard is to **service restarts**, not to imports |

**How the error happened:** I grepped for `init_db()`, saw a match at L1088 and
the absence of `if __name__`, and concluded module scope **without verifying the
enclosing scope**. That was a verification failure, now corrected.

**What survives from Phase 4.15:** **B17 is fully real.** `init_db()` runs on
**every service start** and executed the credential overwrite. That is the defect
this phase removed.

---

## 2. Static proof (AST — parses text, never imports or executes)

### 2.1 Every database-touching call and its enclosing scope

| Call | Sites | At module scope? |
|---|---|---|
| `sqlite3.connect` | **1** — L160, inside `def db()` | **No** |
| `db()` | **31** | **No — every one inside a function or route** |
| `init_db()` | **1** — L1088 | **No — inside `@app.on_event('startup')`** |

```
calls to init_db(): 1
  L1088   enclosing: app.on_event('startup')

sqlite3.connect call sites and their scope:
  L160    enclosing: <function@L159>          # def db()

calls to db(): 31 — all enclosing scopes are routes or functions
  L1107 app.post('/auth/login')   L1116 app.post('/auth/register')
  L1144 app.get('/history')       L1217 app.post('/admin/block-user')
  ... (26 more, none at module scope)
```

### 2.2 Module-scope statements (all inspected)

146 top-level nodes. Every one is a **pure definition**: `FastAPI()` construction
(L12), one `add_middleware` (L13), constant/regex assignments (L15-18, L41-42,
L47, L118, L156, L238-281, L635-640, L883), and three **defensive** import
blocks (L21-39) that swallow failures:

```python
try: import ml_service    except Exception: ml_service = None
try: import mlexicon      except Exception: mlexicon = None
try: import model_adapter except Exception: model_adapter = None
```

The model adapter is **lazy single-load** (per its own comment at L33-35), so
importing it does not load the model.

**No module-scope call touches the filesystem database.**

### 2.3 Additional check added this phase

`init_db()` remains reachable **only** from the startup hook
(`tests_p416…::test_init_db_is_only_reachable_from_the_startup_hook`).

---

## 3. Dynamic proof (isolated subprocess)

`tests_p416_import_and_credential_safety.py::test_subprocess_import_leaves_production_db_untouched`:

1. Snapshot production DB: `st_mtime_ns`, `st_size`, and counts for `users`,
   `audit_logs`, `moderation_results`, `dataset_samples`, plus the count of
   active admins.
2. Launch a **fresh interpreter** that patches `sqlite3.connect` to *record*,
   then `import backend`, then report.
3. Re-snapshot and compare.

**Result:**

| Assertion | Outcome |
|---|---|
| `connects` recorded during a fresh import | **`[]` — zero** |
| `backend.init_db` present | `True` |
| `backend.provision_admin` present | `True` |
| Production DB snapshot before == after | **identical** |

A second, independent trap runs in the **test process itself**
(`test_import_performed_no_database_connection`): `sqlite3.connect` is wrapped
around the single `import backend`, and the recorded list is **empty**.

---

## 4. What changed this phase (and what did not)

| Aspect | Phase 4.15 | Phase 4.16 |
|---|---|---|
| Import writes the database | **never did** | **still does not** — now proven twice |
| `init_db()` location | `@app.on_event('startup')` | **unchanged — correct location** |
| CLI entry point | none | **added** `if __name__ == '__main__': sys.exit(_cli())` |
| Documented entry point | none | `provision-admin`, `status` |

**Deliberate design decision:** initialization was **not** moved out of the
startup hook, because that is already the correct, framework-sanctioned place
for it. Moving it would have risked breaking the running deployment for no
safety gain. The brief's goal — *"importing the backend module performs no
database writes, schema changes, credential seeding, or other startup side
effects"* — is satisfied and now **evidenced**, not assumed.

---

## 5. Test evidence

| Test | Result |
|---|---|
| `test_import_performed_no_database_connection` | ✅ |
| `test_init_db_is_only_reachable_from_the_startup_hook` | ✅ |
| `test_no_db_touching_call_is_at_module_scope` | ✅ |
| `test_main_guard_exists_and_is_not_run_on_import` | ✅ |
| `test_startup_hook_is_registered_but_not_executed` | ✅ |
| `test_subprocess_import_leaves_production_db_untouched` | ✅ |

**Full suite: `tests_p416_import_and_credential_safety.py` — Ran 35, OK, exit 0.**

---

## 6. Residual observations (not blockers)

| Observation | Note |
|---|---|
| FastAPI emits `DeprecationWarning: on_event is deprecated, use lifespan event handlers instead` | **Pre-existing**, surfaced when the CLI runs. Migrating to a lifespan handler is a clean-up item, **not** a security fix, and would change startup behaviour — left for separate authorization |
| Import is cheap but not free (imports 3 sibling modules) | Acceptable; the model load is lazy |
| Service restarts still run `init_db()` | **By design** — it now performs schema DDL only and **never** touches credentials |

---

## 7. Explicit statements

| Item | Status |
|---|---|
| Import side-effect-free (re: database) | ✅ **VERIFIED — statically and dynamically** |
| Phase 4.15 B18 (*"import writes production"*) | ❌ **RETRACTED — it was incorrect** |
| B17 (*"service start rewrites credentials"*) | ✅ **CONFIRMED — and now FIXED** |
| Production write performed to obtain this evidence | ❌ **NONE** |
| Import of the production backend executed during analysis | ❌ **No — AST only, until the isolated proof** |
