# AURA Phase 4.12 — Deletion Dependency Map & Implementation/Rollback Design

**Written BEFORE any code change** (Tasks A and B).

---

## 0. Pre-edit state record

| Item | Finding |
|---|---|
| **Git repository** | **NONE** — no `.git` at `zip project` or under `comment toxicity`. **An isolated branch is therefore impossible.** |
| Consequence | **Every file on disk is uncommitted user work.** Nothing may be overwritten, reverted or discarded. Isolation is achieved by **adding new files only** and never editing existing ones. |
| Isolation strategy | New module + new test file only. **`backend.py`, `ml_service.py`, `aura.db` are NOT edited.** |
| `PHASE411_REPORT.md` | **Does not exist.** The real artefact is `PHASE411_AUDIT_REPORT.md`. Naming discrepancy recorded, not "fixed". |
| Production baseline | recorded 20:16:58 — engine `legacy`; `f31f4975…`/`5a9d94e2…`/`f3a5ceb4…` UNCHANGED; `ur_test`/`ur_val` FROZEN; 596 rows; 137/29/31+399; 8 runs; 12 versions; `improved_v10`. |

### Schema facts (read from `aura.db`, not assumed)

**There are ZERO declared foreign keys** (`PRAGMA foreign_key_list` empty for all
11 tables). All relationships are **application-level only**. Therefore:

> **`ON DELETE CASCADE` cannot be used and does not exist here. The cascade must
> be implemented explicitly, in dependency order, inside one transaction.**

---

## 1. Deletion dependency map

### 1a. Row-level dependencies (data subject = a username)

| # | Table | Link column → target | Raw-text column | Prod rows | Order |
|---|---|---|---|---|---|
| 1 | `live_events` | `session_id` → `live_sessions.session_id` | **`transcript`** | 16 | **first (child)** |
| 2 | `live_sessions` | `username` → `users.username` | — | 6 | 2nd |
| 3 | `feedback` | `username` → `users.username` **AND** `prediction_id` → `moderation_results.id` (`backend.py:1078,1338`) | **`input_text`** | 5 | 3rd |
| 4 | `moderation_results` | `user_id` → `users.username` | **`message`** | 1,629 | 4th |
| 5 | `users` | — (the identity row) | `password_hash`,`salt` | 20 | **last (parent)** |

**Verification chain** — after deletion, each of 1–5 must return 0 rows for the
subject, otherwise it is an **orphan failure**.

### 1b. Audit evidence — **AMBIGUOUS, DEFAULT = PRESERVE**

| Table | Link | Content | Decision |
|---|---|---|---|
| `audit_logs` | `user_id` → `users.username` | `details` JSON | **PRESERVED.** The brief says *"do not automatically erase audit evidence if retention requirements are unclear"* and **no retention period is specified** (`PHASE47_PRIVACY_PLAN.md:94` = "approved up front" — no date). Erasure therefore **appends** a `DATA_ERASURE` record and leaves historical rows intact. |

### 1c. Explicitly OUT OF SCOPE (never deleted by this feature)

| Asset | Why |
|---|---|
| `dataset_samples` (596) | production training data; 596-row invariant |
| `model_versions`, `training_runs`, `settings` | system/config state |
| `data/phase2_eval/ur_test.csv`, `ur_val.csv` | frozen evaluation splits |
| `models/**` incl. `hf_cache` | model weights, not personal data |
| `data/external/**` | dataset content, not data-subject rows |
| protected `*_benchmark.json`, `tuned_threshold.json` | protected artifacts |

### 1d. Stored-artifact dependencies

| Artifact | In scope? | Basis |
|---|---|---|
| `data/backups/*.db` | **YES — deferred** | snapshots **contain** data-subject rows (`PHASE4_WORKSTREAM_B.md` R6: accumulate with no retention) |
| `data/processed/*_v*.json` | **YES — deferred** | derived caches of analysed content |
| audio uploads (`backend.py:1723`) | **N/A** | read in memory, **never persisted** — nothing to erase |
| split CSVs / manifests | NO (this phase) | would only be in scope after an approved RUHSOLD import, which is **NO-GO (G1)** |

---

## 2. Proposed implementation (stated before coding)

```
p5_deletion.py   (NEW FILE — backend.py and ml_service.py untouched)

erase_data_subject(db_path, actor, subject, *, files_root=None, dry_run=False)
    │
    ├─ (1) AUTHORISE   actor must be a dict {'username','role'}; role=='admin'
    │                  else raise AuthorisationError (401 unauthenticated /
    │                  403 forbidden — mirrors backend.admin(), backend.py:183-191)
    │                  + non-admin cannot erase another user -> 403
    ├─ (2) VALIDATE    subject must be a non-empty str; reject empty
    ├─ (3) PLAN        read-only counts of every dependency (1a) + file targets
    │                  dry_run=True stops here and returns the plan untouched
    ├─ (4) TRANSACTION BEGIN
    │                  DELETE children -> parents in the 1a order
    ├─ (5) ORPHAN CHECK re-query each link; any residual row => raise
    ├─ (6) FILES       move in-scope files to a staging/trash dir (REVERSIBLE),
    │                  journaling original paths
    ├─ (7) COMMIT      or, on any failure, ROLLBACK + restore staged files
    ├─ (8) PURGE       only after commit: remove staged files
    └─ (9) AUDIT       append DATA_ERASURE row (never deletes audit evidence)
```

**Transaction-awareness & rollback strategy (the core safety property):**

| Failure point | Result |
|---|---|
| Authorisation | nothing touched |
| SQL delete fails | `ROLLBACK` + staged files restored → **state identical to before** |
| Orphan check fails | `ROLLBACK` + files restored → **no partial deletion** |
| File staging fails | `ROLLBACK` + files restored |
| Commit succeeds, purge fails | rows deleted, files remain in **trash staging** — recoverable, explicitly reported as `purged:false`, **never a silent partial** |
| Retry / second call for same subject | returns `already_erased` with 0 counts — **idempotent, no error** |

**Ordering rationale:** files are staged *before* commit so a rollback can restore
them; purge happens *only after* commit so a crash mid-purge leaves a
recoverable trash dir rather than data loss with rows still present.

## 3. P5a — retention end date: **AMBIGUOUS, WILL NOT BE INVENTED**

The approved requirement is *"time-bounded, with an explicit end date **approved
up front**"*. Checked sources:

| Source | Wording | Date given? |
|---|---|---|
| `PHASE47_PRIVACY_PLAN.md:94` | "defined **deletion date**, approved up front" | **No** |
| `PHASE49_PRIVACY_REVIEW_CHECKLIST.md:93` | "explicit end date **approved up front**" | **No** |
| `PHASE410_APPROVAL_REGISTER.md:26` | "Approved end date" — status **PENDING** | **No** |
| Codebase | zero `retention` hits in application code | **No** |

**Therefore P5a implements only the mechanism**, not a policy:
`retention_end_date` is read from `settings`. If absent, enforcement reports
`policy:unset` and **refuses to delete anything on age grounds**. **No retention
period is fabricated.** The ambiguity is reported (Task G), not resolved.

## 4. Scope boundary (stated up front)

- **Implemented:** P5b row cascade + transaction/rollback/idempotency/authz/orphan
  checks; P5a *machinery* with explicit unset policy; audit **preservation**.
- **Deliberately NOT implemented (requires approval):** wiring an HTTP endpoint
  into `backend.py` (would alter the production API surface); deleting
  `data/backups` and `data/processed` for real (implemented as an explicit,
  separately-gated `include_files` path, disabled by default); retention age
  enforcement (no approved date exists).
