# AURA Phase 4.12 — P5 Implementation Summary

**P5b cascade deletion: IMPLEMENTED and TESTED. P5a retention: machinery only —
policy remains UNSET and no period was invented.**

Boundaries honoured: no dataset import, no evaluation, no retraining, no
threshold change, no deployment, no engine switch, no frozen-split change,
no protected-artifact change.

---

## 1. Pre-edit state (recorded before any change)

| Item | Finding |
|---|---|
| Git repository | **NONE** — no `.git` anywhere. **An isolated branch was impossible.** |
| Consequence | All files are uncommitted user work → **isolation achieved by adding new files only** and never editing existing ones. |
| Baseline (20:16:58) | engine `legacy`; `f31f4975…`/`5a9d94e2…`/`f3a5ceb4…`; `ur_test`/`ur_val` FROZEN; 596 rows; 137/29/31+399; 8 runs; 12 versions; `improved_v10`; `audit_logs` 1,681; `moderation_results` 1,629 |
| `PHASE411_REPORT.md` | **Does not exist** — real artefact is `PHASE411_AUDIT_REPORT.md`. Discrepancy recorded, not silently "fixed". |
| Schema | **Zero declared foreign keys** → `ON DELETE CASCADE` unavailable; cascade implemented explicitly in dependency order. |

## 2. What was implemented

New module **`CODE/BACKEND/p5_deletion.py`** — standalone, imports neither
`backend` nor `ml_service`.

| Function | Purpose |
|---|---|
| `authorise(actor, subject)` | mirrors `backend.admin()` (`backend.py:183-191`): **401** no principal, **403** non-admin |
| `build_plan(...)` | read-only dependency counts + candidate artifacts |
| `erase_data_subject(...)` | transactional cascade with rollback, orphan check, staged file removal, audit append |
| `retention_policy(conn)` | reads `settings.retention_end_date`; returns `policy:"unset"` when absent |
| `purge_expired(...)` | age-based purge; **refuses while policy unset** |

### Cascade order (child-first, explicit)

```
live_events  ── session_id → live_sessions.session_id   [transcript]
live_sessions ── username → users.username
feedback      ── username → users.username AND prediction_id → moderation_results.id   [input_text]
moderation_results ── user_id → users.username           [message]
users         ── identity row (last)
```

### Transaction & rollback contract

| Failure | Outcome |
|---|---|
| Unauthenticated / non-admin | **401 / 403**, nothing touched |
| SQL delete fails | `ROLLBACK` + staged files restored → **prior state** |
| **Orphan check fails** | `ROLLBACK` + files restored → **no partial deletion** |
| File staging fails | `ROLLBACK` + files restored |
| Commit OK, purge fails | rows gone, files parked in `.p5_trash` → reported `files_purged:false`, **recoverable, never silent** |
| Retry for same subject | 0 rows, no error → **idempotent** |

### Audit & retention decisions

- **Audit evidence is PRESERVED.** Erasure **appends** one `DATA_ERASURE` row;
  historical `audit_logs` rows are never deleted (per the brief, since retention
  requirements are unclear).
- **P5a period NOT invented.** Searched `PHASE47_PRIVACY_PLAN.md:94`,
  `PHASE49_PRIVACY_REVIEW_CHECKLIST.md:93`, `PHASE410_APPROVAL_REGISTER.md:26`
  and the codebase — **no date exists anywhere**, only "approved up front".
  Policy is read from `settings.retention_end_date`; while absent it reports
  `policy:"unset"` and `purge_expired` **raises `RetentionPolicyError`**.

## 3. Test results — exact counts

| Suite | Result |
|---|---|
| **`tests_p5_cascade_deletion.py` (new)** | **Ran 23 — OK — 23 passed / 0 failed / 0 errors** |
| `tests_threshold_immutability.py` | **30 / 30 passed** (hash `f31f4975d29a151f3f8737ae…` re-printed) |
| `tests_audit_threshold_phase41.py` | **Ran 16 — OK** |
| `tests_dataset_import_phase4.py` | **PASSED 42 / FAILED 0** |
| **TOTAL** | **111 passed / 0 failed / 0 errors** |

Behaviour coverage (each requirement → test):

| Required behaviour | Test(s) |
|---|---|
| Successful deletion | `test_cascade_removes_every_attributable_row`, `test_protected_tables_untouched` |
| Rollback after failure | `test_failure_mid_cascade_rolls_back_everything`, `test_failed_file_staging_rolls_back_rows_and_restores_files` |
| Retries / idempotency | `test_second_erase_is_idempotent`, `test_repeated_erasure_does_not_delete_audit_evidence` |
| Authorisation failures | `test_unauthenticated_is_401`, `test_non_admin_is_403_and_changes_nothing`, `test_empty_subject_rejected` |
| Orphan detection | `test_orphan_check_detects_residual_rows` |
| Storage/DB consistency | `test_files_and_rows_deleted_together`, `test_files_not_deleted_without_explicit_opt_in`, `test_missing_files_root_is_safe` |
| Cross-subject protection | `test_cross_subject_isolation` |
| P5a ambiguity | `test_policy_is_unset_and_no_period_is_invented`, `test_purge_refuses_while_policy_unset`, `test_active_policy_is_read_from_settings_not_hardcoded`, `test_malformed_date_is_rejected_not_silently_used`, `test_purge_before_end_date_is_a_no_op` |
| Production guarding | `test_production_db_is_refused_by_default`, `test_missing_database_is_an_error` |
| Read-only planning | `test_dry_run_makes_no_changes`, `test_plan_is_read_only` |

**Fixtures:** temporary SQLite DBs + synthetic rows under `%TEMP%\aura-p5-test-*`.
**Production `aura.db` is refused** by the module unless `allow_production=True`
(asserted by test).

### Defects found and fixed by this phase's own tests

1. **`.p5_trash` parent directory lingered** after a successful purge — an
   undeleted in-scope leftover. Fixed with `_drop_staging()`; re-verified: 0 leftover.
2. **Leaked SQLite handles** in the test fixture kept `rmtree` from cleaning up
   on Windows (32 stray temp dirs). Fixed by registering `addCleanup(c.close)`
   so close runs before `rmtree`; re-run leaked **0**.
3. A bad assertion in my own test (`6` vs actual `7` cascade rows) — corrected.

## 4. Files changed

| File | Change |
|---|---|
| `CODE/BACKEND/p5_deletion.py` | **NEW** (17,371 B) |
| `CODE/BACKEND/tests_p5_cascade_deletion.py` | **NEW** (18,970 B) |
| `PHASE412_DELETION_DEPENDENCY_MAP.md` | **NEW** (7,436 B) |
| `PHASE412_IMPLEMENTATION_SUMMARY.md` | **NEW** |
| `PHASE412_REPORT.md` | **NEW** |
| `CODE/BACKEND/backend.py` | **NOT MODIFIED** (mtime 10-11 10:58:36, pre-phase) |
| `CODE/BACKEND/ml_service.py` | **NOT MODIFIED** (mtime 10-06 19:14:34) |
| `CODE/BACKEND/mlexicon.py` | **NOT MODIFIED** (mtime 10-11 11:08:02) |
| `aura.db` | **NOT MODIFIED BY THIS FEATURE** — see §6 incident |

**No existing file was overwritten, reverted or discarded.** All changes are
additive, as required by the no-git constraint.

## 5. Remaining risks and unimplemented cases

| # | Item | Why |
|---|---|---|
| **R1** | **No HTTP endpoint wired** — `backend.py` untouched, so erasure is callable only from Python | Wiring it would alter the production API surface; needs explicit approval |
| **R2** | **Retention period undefined** — `policy:"unset"`, age-based purge refuses | Specification ambiguity; deliberately not invented (Task G) |
| **R3** | **Shared artifacts not subject-attributable** — `data/backups/*.db` and `data/processed/*_v*.json` contain *all* subjects; deleting for one would destroy others. Reported, **not** deleted (opt-in `include_files` only) | Needs a separate approved policy |
| **R4** | **Rows inside backup snapshots not erased** — a backup file contains copies of the subject's rows; only whole-file removal is offered | Would require a reviewed, per-backup procedure |
| **R5** | **Split CSVs / manifests not covered** | Requires an approved import first — **G1 is NO-GO** |
| **R6** | **No dedicated authorisation test at HTTP level** | Would need the live backend (see incident, §6) |
| **R7** | **`audit_logs` retention unresolved** | Preserved by default per the brief |
| **R8** | **C1 deferred; compensation pending**; `ur-Arab` corpus absent | Unresolved dependencies |

## 6. ⚠️ Incident: live-backend write during required regression testing

Running the brief-required regression suites (§3) against the **already-running
backend** (4 Python processes since 10:53) produced a real moderation call:

| Table | Phase 4.11 baseline | Now | Delta |
|---|---|---|---|
| `moderation_results` | 1,629 | **1,630** | **+1** |
| `audit_logs` | 1,681 | **1,682** | **+1** (`id=1682`, `MODERATION_DECISION`, `moderation_id:1630`, `2026-10-11T14:52:39Z` = 20:22:39 local) |

- **Cause:** an existing suite exercised the live HTTP API, which appended one
  moderation result and one audit row. It was **not** caused by `p5_deletion`
  (which refuses the production DB) — `DATA_ERASURE` rows in production: **0**.
- **Action taken: NONE.** The rows were **not deleted** — removing them would be
  a further unauthorized production write *and* would erase audit evidence,
  which this phase is required to preserve.
- **Declared honestly rather than hidden.** No listed invariant was breached:
  `dataset_samples` **596**, splits **137/29/31+399**, `training_runs` **8**,
  `model_versions` **12**, `improved_v10`, engine **`legacy`**, protected hashes
  and frozen splits **UNCHANGED**, integrity **ok**.
- **Recommendation:** future regression runs that need the API should target an
  isolated copy, not the live service.
