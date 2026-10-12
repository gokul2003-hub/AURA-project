# AURA Phase 4.11 — Read-Only Approval-Gap Closure & Readiness Audit

**Verdict: dataset import 🔴 NO-GO · Roman Urdu evaluation 🔴 NO-GO ·
Urdu-script evaluation ⏸ deferred/NO-GO · both quality gates `NOT PASSED`.**

**This phase was READ-ONLY.** No source file, database, dataset, model file,
configuration, manifest or threshold was modified. No download, import,
evaluation, training, threshold change, retraining, deployment or engine switch
occurred. Verification checks were non-mutating (`file:aura.db?mode=ro`).

Companion deliverables:
`PHASE411_PRODUCTION_INVARIANTS.md`,
`PHASE411_P1P2_REVIEWER_CHECKLIST.md`,
`PHASE411_P3P5_MATRIX.md`,
`PHASE411_BLOCKER_REGISTER.md`.

---

## A. Materials reviewed (Task A)

Phase 4.10 register/report; Phase 4.7–4.9 reports and supporting artefacts;
Phase 4.4 eval protocol and annotation spec; Phase 4.6 RUHSOLD label audit;
Phase 4.6 Urdu-script collection plan; Phase 4.3 Urdu audit. Implementation:
`backend.py`, `mlexicon.py`, `ml_service.py`, `fetch_external_datasets.py`,
`import_external_datasets.py`, and the `tests_*.py` suites.

## B. Production invariants (Task B) — VERIFIED

| Invariant | Observed | Status |
|---|---|---|
| Engine | **`legacy`** | ✅ |
| `tuned_threshold.json` | `f31f4975d29a151f` | ✅ **UNCHANGED** |
| `phase2_benchmark.json` | `5a9d94e267806ea0` | ✅ **UNCHANGED** |
| `phase3_benchmark.json` | `f3a5ceb488f4a9ad` | ✅ **UNCHANGED** |
| `ur_test.csv` | `f18d80f3…` | ✅ **FROZEN** |
| `ur_val.csv` | `8727f2ba…` | ✅ **FROZEN** |
| Integrity / FK | `ok` / clean | ✅ |
| Rows / splits | **596**; 137/29/31 + 399 | ✅ |
| `training_runs` / `model_versions` | **8 / 12** | ✅ |
| Active model | **`improved_v10`** | ✅ |

**Marked NOT VERIFIED:** checkpoint re-derivation of the HF model file, runtime
behaviour of `audit_logs.details`, and adversarial authz testing. Full detail in
`PHASE411_PRODUCTION_INVARIANTS.md`.

## C. P1/P2 reviewer checklist (Task C) — prepared, no determination made

18 questions across **rights/provenance**, **lawful basis**, **platform terms**,
**PII & sensitive-data risk**, **retention/deletion**, and **cross-border/DPIA**,
each paired with the evidence in hand and the specific missing artefact.

Key evidence positions:
- MIT verifiably covers **the curators' artefact only**; it does not evidently
  reach the **underlying tweets**; upstream *Source Data* is "[More Information Needed]".
- PII measured low (**0 handles, 4 URLs, 0 emails** in 10,010 rows).
- **Special-category risk stands:** classes `2`/`3` = **1,166 rows** assert a
  protected characteristic; handle-stripping does not resolve this.
- **Erasure cannot currently be honoured** — no deletion capability exists (see D).

A signature block is provided **for a qualified reviewer only**. **No legal
conclusion is drawn here.**

## D. P3–P5 matrix (Task D) — the material finding

**8/8 specifications are approved, but only ~2/8 are implemented and 0/8 are tested.**

| Spec | Maturity |
|---|---|
| **P3** redaction before dedup | SPEC APPROVED · **NOT IMPLEMENTED** · NOT TESTED |
| **P3b** versioned preprocessing | SPEC APPROVED · **PARTIAL** (no `preprocess_version`; **NFC not NFKC**) · PARTIAL |
| **P3c** salted text hashes | SPEC APPROVED · **NOT IMPLEMENTED as specified** · NOT TESTED |
| **P4a** restricted access | SPEC APPROVED · **IMPLEMENTED** (401/403/role/blocked/`audit_logs`/`require_ml`) · PARTIAL |
| **P4b** counts-only reporting | SPEC APPROVED · implemented on **static** evidence · **NOT VERIFIED at runtime** |
| **P4c** encryption at rest | SPEC APPROVED · **NOT VERIFIED** |
| **P5a** retention end date | SPEC APPROVED · **NOT IMPLEMENTED** · NOT TESTED |
| **P5b** cascade deletion | SPEC APPROVED · **NOT IMPLEMENTED** · NOT TESTED |

**Three consequences worth flagging:**
1. **No redaction exists**, so Phase 4.8's V5–V7 counts remain valid *only* under
   the current unredacted normalisation and **must be re-derived** once P3 lands.
2. **No cascade deletion exists** — this blocks erasure and therefore partly
   blocks **P2** itself. *P2 closure is contingent on P5 being built.*
3. **P4a is the sole production-grade control**, and explains the 401 observed on
   the protected endpoint in earlier phases.

## E. Deferred/pending dependencies (Task E)

| Item | Status | Effect |
|---|---|---|
| **C1 Urdu-script commissioning** | **DEFERRED** | `ur-Arab` gate **G7** cannot start; **no corpus exists**. Does *not* block Roman Urdu. |
| **Annotator compensation** | **PENDING** | blocking for C1 whenever it resumes |
| **P1/P2 legal review** | **PENDING — BLOCKING** | blocks **all** import and evaluation |

## F. Gate table (Task F)

| Gate | Status | Evidence | Blocker | Needed to unblock |
|---|---|---|---|---|
| **G1** lawful import | 🔴 NO-GO | MIT reaches curators' artefact only; PII 0/4/0 | B1, B2 | **signed qualified-reviewer opinion closing P1+P2** |
| **G2** mapping freeze | 🟢 READY | **M1–M4 approved**; usable 6,746 | — | write frozen mapping artefact *(skipped — would be a write)* |
| **G3** redaction/preprocessing | 🔴 NO-GO | specs approved, code absent | B3–B6 | implement P3/P3b/P3c/P5 + tests |
| **G4** leakage-safe split | 🔴 NO-GO | leakage quantified; `test` unlabelled; `validation` duplicate | B8 | dedup (exact + trigram) → group-aware 40/20/40 → L1–L7 |
| **G5** hash freeze | 🔴 NO-GO | procedure specified | G4 | SHA256 manifest before scoring |
| **G6** single evaluation | 🔴 NO-GO | protocol + sample size frozen | G1–G5 | one frozen run/stratum, Wilson 95 % CI, never pooled |
| **G7** `ur-Arab` | ⏸ DEFERRED | plan exists; no corpus | B7 | C1 + compensation → collect → annotate (κ ≥ 0.70) |

**Only G2 has changed state since Phase 4.10.** Full register in
`PHASE411_BLOCKER_REGISTER.md`.

## G. Smallest safe next action (Task G) — recommended, NOT performed

> **Appoint a qualified legal/privacy reviewer** and hand them
> `PHASE411_P1P2_REVIEWER_CHECKLIST.md` to close **P1/P2**.

It is the **root blocker**, requires **no write, download, import or evaluation**,
and unblocks G1. In parallel: build **P5 cascade deletion**, since P2 erasure
questions cannot be answered without it.

**No gated action was performed automatically.**

---

## GO / NO-GO

| Decision | Verdict |
|---|---|
| **Dataset import** | 🔴 **NO-GO** — P1/P2 pending and blocking |
| **Roman Urdu evaluation** | 🔴 **NO-GO** — G1, G3–G6 NO-GO |
| **Urdu-script evaluation** | ⏸ **NO-GO (deferred)** — no corpus |
| **Retrain / threshold / deploy / engine change** | 🔴 **NO-GO** — out of scope; invariants frozen |
| **Mapping freeze (G2)** | 🟢 GO, **not executed** (would require a write) |

| Quality gate | Cap | Status |
|---|---|---|
| Roman Urdu (`ur-Latn`) | 0.15 | **`NOT PASSED`** |
| Urdu script (`ur-Arab`) | 0.15 | **`NOT PASSED`** |

**The expected decision stands: NO-GO while P1/P2 review is pending.**

## Acceptance

| Requirement | Result |
|---|---|
| Unauthorized writes | **NONE** — only these 5 new audit reports |
| Downloads / imports / evaluation | **NONE** |
| Threshold changes / retraining / deployment | **NONE** |
| Frozen `ur_test`/`ur_val` modified | **NO** |
| Protected hashes / DB invariants | **PRESERVED** |
| Engine | **`legacy`** |
| Unprovable checks | **Marked NOT VERIFIED** |
| Legal claim made | **NONE** |
