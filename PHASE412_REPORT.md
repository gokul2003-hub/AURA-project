# AURA Phase 4.12 — Final Report (P5 Cascade Deletion)

**Outcome: P5b cascade deletion IMPLEMENTED and TESTED (23/23). P5a retention
machinery built but policy UNSET — no period invented. 111 regression checks
pass. Production invariants PRESERVED. G1 remains NO-GO.**

Deliverables: `PHASE412_DELETION_DEPENDENCY_MAP.md`,
`PHASE412_IMPLEMENTATION_SUMMARY.md`, this report.

**Not done, by instruction:** no dataset import, no evaluation, no retraining,
no threshold change, no deployment, no engine switch, no migration, no
destructive command against production.

---

## 1. Production-invariant verification evidence (Task F)

Verified **20:16:58** (baseline) and **20:27:40** (final), both via
`file:aura.db?mode=ro`.

| Invariant | Expected | Final observed | Result |
|---|---|---|---|
| `tuned_threshold.json` | `f31f4975d29a151f` | `f31f4975d29a151f` | ✅ **UNCHANGED** |
| `phase2_benchmark.json` | `5a9d94e267806ea0` | `5a9d94e267806ea0` | ✅ **UNCHANGED** |
| `phase3_benchmark.json` | `f3a5ceb488f4a9ad` | `f3a5ceb488f4a9ad` | ✅ **UNCHANGED** |
| `ur_test.csv` (frozen) | `f18d80f3e12e07a6…` | matches | ✅ **UNCHANGED** |
| `ur_val.csv` (frozen) | `8727f2bacf416191…` | matches | ✅ **UNCHANGED** |
| **Production engine** | `legacy` | **`legacy`** | ✅ |
| `PRAGMA integrity_check` | `ok` | **`ok`** | ✅ |
| `PRAGMA foreign_key_check` | clean | **clean** | ✅ |
| `dataset_samples` | 596 | **596** | ✅ |
| Splits | 137/29/31 + 399 | **137 / 29 / 31 + 399** | ✅ |
| `training_runs` | 8 | **8** | ✅ |
| `model_versions` | 12 | **12** | ✅ |
| Active model | `improved_v10` | **`improved_v10`** | ✅ |
| `DATA_ERASURE` rows in production | 0 | **0** | ✅ — feature never ran on prod |
| Source files modified | none | `backend.py` 10:58:36, `ml_service.py` 10-06, `mlexicon.py` 11:08:02 — all **pre-phase** | ✅ |
| Leftover artifacts | none | `.p5_trash` **absent**, `aura-p5-test-*` **0**, RUHSOLD scratch **absent** | ✅ |

**ALL INVARIANTS PRESERVED.**

### ⚠️ Honest exception (see summary §6)

A **live backend** (4 Python processes since 10:53) meant that running the
brief-required regression suites appended **1 row to `moderation_results`
(1,629 → 1,630)** and **1 row to `audit_logs` (1,681 → 1,682)** at 20:22:39.
**Not caused by `p5_deletion`** (it refuses the production DB; `DATA_ERASURE` = 0).
**Not reverted** — deleting it would be a further unauthorized write and would
erase audit evidence. **No listed invariant was breached.** Full account in
`PHASE412_IMPLEMENTATION_SUMMARY.md §6`.

## 2. Deletion dependency map (Task A)

Full map in `PHASE412_DELETION_DEPENDENCY_MAP.md`. Key finding:

> **`aura.db` declares ZERO foreign keys.** `ON DELETE CASCADE` does not exist
> here — the cascade is implemented **explicitly, child-first, in one
> transaction**.

```
live_events (transcript) ──► live_sessions ──► feedback (input_text) ──► moderation_results (message) ──► users
audit_logs   ── PRESERVED by default (retention requirements unclear)
dataset_samples / model_versions / training_runs / settings ── PROTECTED, never touched
```

## 3. Test results — exact pass/fail (Task D)

| Suite | Pass | Fail | Errors |
|---|---|---|---|
| **`tests_p5_cascade_deletion.py` (new)** | **23** | **0** | **0** |
| `tests_threshold_immutability.py` | **30** | **0** | 0 |
| `tests_audit_threshold_phase41.py` | **16** | **0** | 0 |
| `tests_dataset_import_phase4.py` | **42** | **0** | 0 |
| **TOTAL** | **111** | **0** | **0** |

**Every implemented behaviour has a corresponding test** (mapping table in
`PHASE412_IMPLEMENTATION_SUMMARY.md §3`): success, rollback, idempotency,
authorisation 401/403, orphan detection, storage/DB consistency, cross-subject
isolation, P5a ambiguity, production guard, read-only planning.

The suite also **found and fixed two real defects in this phase's own code**:
a lingering `.p5_trash` directory after purge, and leaked SQLite handles that
prevented fixture cleanup on Windows (32 stray dirs → **0** after the fix).

## 4. Files changed (Task B)

| File | Change |
|---|---|
| `CODE/BACKEND/p5_deletion.py` | **NEW** (17,371 B) |
| `CODE/BACKEND/tests_p5_cascade_deletion.py` | **NEW** (19,142 B) |
| `PHASE412_DELETION_DEPENDENCY_MAP.md` | **NEW** |
| `PHASE412_IMPLEMENTATION_SUMMARY.md` | **NEW** |
| `PHASE412_REPORT.md` | **NEW** |
| **Everything else** | **NOT MODIFIED** |

**No existing file was overwritten, reverted or discarded.** With no git repo
available, isolation was achieved by **additive-only** changes.

## 5. Requirements that could NOT be implemented safely (Task G)

| # | Requirement | Why it is unresolved |
|---|---|---|
| **R2** | **P5a retention end date** | Spec says only *"approved up front"* (`PHASE47_PRIVACY_PLAN.md:94`, `PHASE49_…:93`, `PHASE410_REGISTER:26`) — **no date exists**. Implemented the mechanism; **refused to invent a period**. `purge_expired` raises `RetentionPolicyError` while unset. |
| **R3** | **Shared artifact deletion** | `data/backups/*.db` and `data/processed/*_v*.json` hold **all** subjects — removing one for a single subject would destroy others'. Reported as `attributable_to_subject:false`, **not** deleted. |
| **R4** | **Rows inside backup snapshots** | Only whole-file removal is offered; per-subject extraction would need a reviewed procedure. |
| **R5** | **Split CSVs / manifests** | Requires an approved import — **G1 is NO-GO**. |
| **R7** | **Audit retention** | Unclear per the brief → **PRESERVED by default**. |
| **R1** | **No HTTP endpoint** | Wiring into `backend.py` would alter the production API surface — deliberately left for approval. |

**Ambiguous policy remains explicitly unresolved. No erasure-compliance or
legal-approval claim is made** — passing software tests does not establish
either.

## 6. Updated gate register

| Gate | Phase 4.11 | **Phase 4.12** | Blocker now |
|---|---|---|---|
| **G1** Lawful import | 🔴 NO-GO | 🔴 **NO-GO** | **P1/P2 qualified legal review** — unchanged |
| **G2** Mapping freeze | 🟢 READY | 🟢 **READY** | — (M1–M4 approved; not written, would be a file write) |
| **G3** Redaction & preprocessing | 🔴 NO-GO | 🔴 **NO-GO — narrowed** | P3, P3b, P3c still unimplemented; P5a policy unset; R1 endpoint |
| **G4** Leakage-safe split | 🔴 NO-GO | 🔴 **NO-GO** | dedup + group-aware split not started (needs G1) |
| **G5** Hash freeze | 🔴 NO-GO | 🔴 **NO-GO** | depends on G4 |
| **G6** Single evaluation | 🔴 NO-GO | 🔴 **NO-GO** | depends on G1–G5 |
| **G7** `ur-Arab` | ⏸ DEFERRED | ⏸ **DEFERRED** | C1 + compensation pending; no corpus |

### Blocker register update

| Blocker | Phase 4.11 | **Phase 4.12** |
|---|---|---|
| **B1** P1 rights/provenance | open | **open — unchanged** |
| **B2** P2 lawful basis/ToS/erasure | open | **open — but P5b capability now exists** (B3 no longer fully blocks P2.13/P2.14 machinery) |
| **B3** P5 not implemented | open | **PARTIALLY CLOSED** — cascade deletion implemented + tested; **remaining:** retention date (ambiguous), endpoint wiring, backup/cache file policy |
| **B4** P3 redaction | open | **open — unchanged** |
| **B5** P3c salted hashes | open | **open — unchanged** |
| **B6** P3b versioning / NFKC | open | **open — unchanged** |
| **B7** C1 deferred | open | **open — unchanged** |
| **B8** upstream splits unusable | open | **open — unchanged** |
| **B9** no P3–P5 tests | open | **partially closed — P5 now has 23 tests; P3/P4 still untested** |

## 7. GO / NO-GO

| Decision | Verdict | Basis |
|---|---|---|
| **Dataset import (RUHSOLD)** | 🔴 **NO-GO** | **P1/P2 pending and blocking** — unchanged by this phase |
| **Roman Urdu evaluation** | 🔴 **NO-GO** | G1, G3–G6 NO-GO |
| **Urdu-script evaluation** | ⏸ **NO-GO (deferred)** | C1 deferred; no corpus |
| **Retrain / threshold / deploy / engine switch** | 🔴 **NO-GO** | invariants frozen; engine `legacy` |
| **P5 cascade deletion usable in production** | 🔴 **NO-GO for live use** | module is tested, but **not wired to an endpoint** and retention policy is **unset** |

| Quality gate | Cap | Status |
|---|---|---|
| Roman Urdu (`ur-Latn`) | 0.15 | **`NOT PASSED`** |
| Urdu script (`ur-Arab`) | 0.15 | **`NOT PASSED`** |

**Both quality gates remain `NOT PASSED`. G1 remains NO-GO pending qualified
P1/P2 review. G3–G6 remain blocked pending their requirements.**

## 8. Smallest safe next action (recommended, not performed)

1. **P1/P2** — appoint a qualified legal/privacy reviewer
   (`PHASE411_P1P2_REVIEWER_CHECKLIST.md`). Root blocker for G1.
2. **Approve a retention end date** (R2) so P5a can move from *machinery* to
   *enforced policy* — required for P2.12.
3. **Approve endpoint wiring** (R1) if erasure must be reachable over HTTP.
4. **Target regression tests at an isolated backend copy**, not the live service
   (prevents recurrence of the §1 incident).

**No gated action was performed automatically.**
