# AURA Phase 4.13 — Retention Decision REQUIRED

**STATUS: DECISION REQUIRED — NO DATE CHOSEN.**
`purge_expired()` remains **BLOCKED** while the policy is unset. Nothing below
is approved, and **no legal or privacy approval is claimed**.

This document stops at the decision point, as required. The authorized reviewer
must answer the question in §5.

---

## 1. Why this decision is being escalated rather than decided

The approved specification is *"time-bounded retention with an explicit end
date **approved up front**"*. Every source was inspected:

| Source | Wording | Date supplied? |
|---|---|---|
| `PHASE47_PRIVACY_PLAN.md:94` | "defined **deletion date**, approved up front" | **No** |
| `PHASE49_PRIVACY_REVIEW_CHECKLIST.md:93` | "explicit end date **approved up front**" | **No** |
| `PHASE410_APPROVAL_REGISTER.md:26` (P5) | "Approved end date" — status **PENDING** | **No** |
| `PHASE411_P3P5_MATRIX.md:28` (P5a) | "No retention code… **No end date is defined anywhere**" | **No** |
| Codebase (`retention\|purge\|erasure` in `CODE/`) | zero application-code hits | **No** |
| `settings` table in `aura.db` | keys are only `prediction_engine`, `toxicity_threshold` | **No** |

**No retention period exists in any artefact.** Choosing one would be inventing
a legal/privacy obligation — explicitly prohibited.

## 2. Current technical state (not a policy)

| Aspect | State |
|---|---|
| Mechanism | `p5_deletion.retention_policy()` reads `settings.retention_end_date` |
| Current value | **absent** → returns `policy:"unset"`, `enforced:False` |
| `purge_expired()` | **raises `RetentionPolicyError`** — refuses to delete anything on age grounds |
| Malformed value | also rejected (`RetentionPolicyError`), never silently used |
| Verified by | `tests_p5_cascade_deletion.py` — 5 retention tests, all passing |

**The enforcement gate is therefore already in the safe state.** The only
missing input is the reviewer's decision.

## 3. The exact policy decision required

> **QUESTION FOR THE AUTHORIZED REVIEWER:**
>
> **What is the approved retention end date (or retention duration, expressed as
> an end date) for each class of data AURA holds — and from which trigger date
> does it run?**
>
> Required granularity, because a single date is almost certainly wrong for
> data with different lifecycles:
>
> | Data class | Tables / artifacts | Decision needed |
> |---|---|---|
> | **D1** Moderation content | `moderation_results.message` | retention end date / duration |
> | **D2** User-submitted text | `feedback.input_text` | retention end date / duration |
> | **D3** Live transcripts | `live_events.transcript` | retention end date / duration |
> | **D4** Identity records | `users` | retention end date / duration |
> | **D5** Derived caches | `data/processed/*_v*.json` | retention end date / duration |
> | **D6** Database snapshots | `data/backups/*.db` | retention end date / duration |
> | **D7** **Audit evidence** | `audit_logs` (1,682 rows) | **retain / purge** + end date, if any |
> | **D8** Evaluation splits | `data/phase2_eval/ur_*.csv` | **frozen** — likely exempt; needs explicit confirmation |
> | **D9** Dataset & model state | `dataset_samples`, `model_versions`, `training_runs` | likely exempt; needs explicit confirmation |
>
> Plus: **what is the trigger event** (row creation date, session end, account
> deletion, or a fixed calendar date)?

**Sub-decision already flagged as ambiguous:** D7. The brief for Phase 4.12
directed *"do not automatically erase audit evidence if retention requirements
are unclear"*, so audit rows are **currently preserved indefinitely**. That is a
holding position, not an approved policy, and D7 must be resolved explicitly.

## 4. Who must authorize

| Decision | Authorizer | Why |
|---|---|---|
| **D1–D6, D8, D9** — retention periods | **Qualified legal/privacy reviewer**, countersigned by the **user/data owner** | Determines lawful-basis and storage-limitation obligations under **P2**, which is still **PENDING and BLOCKING** |
| **D7** — audit-evidence retention | **Security/audit owner + legal reviewer** | Security evidence may have a *shorter* or *longer* obligation than content; also feeds **P2.13/P2.14** |
| Loading the value into `settings` | **Engineer, only after written approval** | Configuration change touching production |
| Re-enabling `purge_expired()` | **Engineer, only after the value is approved AND validated** | Currently hard-blocked by design |

**No date may be entered by an automated process or by this project.**

## 5. Evidence the qualified reviewer must assess

1. **`PHASE411_P1P2_REVIEWER_CHECKLIST.md`** — especially **P2.12** (retention
   period/end date), **P2.13** (erasure honourable), **P2.14** (cascade reach).
2. **`PHASE413_INCIDENT_REVIEW.md`** — demonstrates that live traffic writes
   content rows continuously (`moderation_results` grows on every `/predict`),
   which directly affects any duration measured from creation date.
3. **Current data volumes** (read-only, verified this phase):
   `moderation_results` **1,630**, `audit_logs` **1,682**, `feedback` **5**,
   `live_events` **16**, `users` **20**, `dataset_samples` **596**.
4. **Deletion capability** — `PHASE412_IMPLEMENTATION_SUMMARY.md`: cascade
   deletion is implemented and tested (23/23), so an end date is now
   *executable*, but **not wired to an endpoint (R1)**.
5. **Backups hold copies** (`data/backups/*.db`) — erasing a row from the live
   DB does **not** erase it from snapshots; a backup-specific decision is needed.
6. **Special-category content** — 1,166 rows sit in classes 2/3 (`PHASE49`),
   which may attract stricter limits.
7. **Frozen-evaluation exemption** — deleting `ur_test`/`ur_val` would destroy
   the benchmark; the reviewer must explicitly confirm D8/D9 as exempt.

## 6. How the end date will be configured and validated

Once — and only once — written approval exists:

| Step | Action | Guard |
|---|---|---|
| 1 | Record the approved date in the decision record, with approver name, date and scope (D1–D9) | approval evidence attached |
| 2 | Write `settings.retention_end_date` as **`YYYY-MM-DD`** | production config change — **requires separate authorization** |
| 3 | Validation already enforced in code: `strptime('%Y-%m-%d')`, else `RetentionPolicyError` | malformed values are rejected, never silently used |
| 4 | Re-run `tests_p5_cascade_deletion.py` — 5 retention tests must still pass (incl. `test_policy_is_unset_and_no_period_is_invented`) | must be updated to assert the *approved* value |
| 5 | Confirm `retention_policy()` returns `policy:"active"`, `enforced:True` | read-back check |
| 6 | **Do not** re-enable bulk purge without a reviewed, dry-run-first procedure | `purge_expired` still raises when expiry is reached, because bulk expiry of protected tables is outside approved P5 scope |

**Validation properties already tested (no change needed):**
policy unset → block · malformed date → reject · date not reached → no-op ·
date never read from a hard-coded constant.

## 7. Blocking status

| Item | Status |
|---|---|
| **Retention end date (D1–D9)** | 🔴 **REQUIRED — unanswered** |
| `purge_expired()` | 🔴 **BLOCKED** (raises `RetentionPolicyError`) |
| P2.12 / P2.13 / P2.14 | 🔴 **PENDING** — cannot be closed until D1–D7 are set |
| G1 | 🔴 **NO-GO** — P1/P2 review outstanding |

> **This phase stops here.** No retention period was chosen, configured or
> inferred. The exact question for the authorized reviewer is in **§3**.
