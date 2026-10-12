# AURA Phase 4.11 — Blocker & Dependency Register, Gate Table, GO/NO-GO

**Consolidates Phase 4.10 with the Phase 4.11 read-only audit.**

> **Updated through Phase 4.17.** **B22 (session invalidation) is RESOLVED** —
> see §2.1. Quality gates `ur-Latn` / `ur-Arab` remain **`NOT PASSED`**; gates
> G1–G7 and every approval/blocker below are otherwise **unchanged**. No
> dataset, evaluation, retraining, threshold tuning or deployment occurred.

---

## 1. Approval status after Phase 4.11

| ID | Item | Phase 4.10 | **Phase 4.11** | Owner |
|---|---|---|---|---|
| **M1** | `Normal → non_toxic`; `Abusive/Offensive → toxic` | PENDING | **✅ APPROVED** | user |
| **M2** | `Religious Hate`/`Sexism` → `toxic` + `identity_hate` flag | PENDING | **✅ APPROVED** | user |
| **M3** | Exclude `Profane/Untargeted` as unknown | PENDING | **✅ APPROVED** | user |
| **M4** | Binary headline evaluation only | PENDING | **✅ APPROVED** | user |
| **P3–P5** | Control *specifications* | PENDING | **✅ SPEC APPROVED** *(implementation largely absent — see matrix)* | user |
| **C1** | Urdu-script commissioning | PENDING | **⏸ DEFERRED** | user |
| — | Annotator compensation | PENDING | **⏳ PENDING** | user |
| **P1** | Rights / provenance review | BLOCKED | **🔴 PENDING — BLOCKING** | **qualified legal reviewer** |
| **P2** | Lawful basis / ToS / erasure | BLOCKED | **🔴 PENDING — BLOCKING** | **qualified legal reviewer** |

**Approved: 6 · Deferred: 1 · Pending: 1 · Blocking-pending: 2.**

---

## 2. Blocker register

| # | Blocker | Type | Depends on | Blocks | Evidence needed to clear |
|---|---|---|---|---|---|
| **B1** | **P1 rights/provenance** — MIT does not evidently reach underlying tweets; upstream *Source Data* = "[More Information Needed]" | **External — legal** | qualified reviewer | **all import** | written reviewer opinion on P1.2–P1.6 |
| **B2** | **P2 lawful basis / ToS / erasure** — no basis identified; no ToS review | **External — legal** | qualified reviewer | **all import** | documented lawful basis + ToS position |
| **B3** | **P5 not implemented** — no retention date, **no cascade deletion capability** | **Engineering** | P3–P5 spec (now approved) | **P2.13/P2.14** (erasure cannot be honoured) | implemented + tested cascade delete; approved end date |
| **B4** | **P3 not implemented** — no redaction before dedup | **Engineering** | P3 spec (approved) | reproducibility of Phase 4.8 V5–V7 under the final pipeline | implemented redaction + re-derived V5–V7 |
| **B5** | **P3c not implemented** — dedup uses raw normalised text, not salted hashes | **Engineering** | P3c spec (approved) | privacy-preserving dedup/overlap detection | salted hash join key + salt custody |
| **B6** | **P3b not versioned / no NFKC** — no `preprocess_version`; `mlexicon.py:161` uses NFC | **Engineering** | P3b spec (approved) | claim of reproducible preprocessing | versioned pipeline + golden fixture |
| **B7** | **C1 deferred** — `ur-Arab` corpus does not exist; compensation pending | **Commercial / resource** | user budget approval | **Urdu-script gate** | C1 + compensation approval, then collection |
| **B8** | **Upstream splits unusable** — `test` unlabelled (2,002 nulls), `validation` duplicate of `train`, near-dup leakage 15/5/2/22 | **Data** | M1–M4 (approved) | any evaluation using upstream splits | dedup + group-aware re-split + L1–L7 + hash freeze |
| **B9** | **No dedicated tests for any P3–P5 control** | **Engineering** | B3–B6 | any "TESTED" claim | automated coverage |

### 2.1 Resolved through Phase 4.17

| # | Blocker | Status | Evidence |
|---|---|---|---|
| **B22** | **Sessions survived credential rotation** — a token minted before rotation remained valid | ✅ **RESOLVED (4.17)** | sessions bound to persisted `credential_version`; revocation/rotation bump it; **revocation survives restart**; 29 dedicated tests (`PHASE417_SESSION_SECURITY_EVIDENCE.md`) |

**Also delivered in 4.17 (no blocker cleared):** auth telemetry
(`LOGIN_SUCCESS`/`LOGIN_FAILED`/`SESSIONS_REVOKED`, secret-free by static AST
enforcement) and login **throttling as exponential backoff — never a permanent
lockout**. Thresholds are **PROPOSED DEFAULTS, not approved policy**. A real
unbounded-growth weakness in `login_attempts` was **found and fixed**.

**Open items introduced (need decisions, do not block G1):**
**A2** live credential rotation not authorized · **A4 retention** governs the
new `login_attempts` + telemetry counters · **throttle-threshold policy
approval**.

---

## 3. Gate table — lawful import → single evaluation

| Gate | Status | Evidence in hand | Blocker | Exact evidence/approval needed |
|---|---|---|---|---|
| **G1** Lawful import | 🔴 **NO-GO** | MIT covers curators' artefact only; PII measured 0/4/0 | **B1, B2** | **signed written opinion from a qualified legal/privacy reviewer** closing P1 and P2 |
| **G2** Mapping freeze | 🟢 **READY** | **M1–M4 APPROVED**; counts measured (toxic 2,895 / non-toxic 3,851 / excluded 462 / usable 6,746) | — | freeze the approved mapping into a versioned artefact *(not yet written — would require a file write, skipped per restriction 1)* |
| **G3** Redaction & preprocessing | 🔴 **NO-GO** | **spec approved**, but P3/P3b/P3c/P4c incomplete | **B3, B4, B5, B6** | implementation + tests + V5–V7 re-derived; P5 deletion capability |
| **G4** Leakage-safe split | 🔴 **NO-GO** | leakage quantified (Phase 4.8); `test` unlabelled, `validation` duplicate | **B8** | dedup (exact **+ trigram**), group-aware 40/20/40, assertions L1–L7 pass |
| **G5** Hash freeze | 🔴 **NO-GO** | procedure specified (`PHASE47_SPLIT_VERIFICATION_PLAN.md`) | **G4** | SHA256 manifest recorded **before** any scoring |
| **G6** Single evaluation | 🔴 **NO-GO** | protocol + sample-size math frozen (`PHASE44_EVAL_PROTOCOL.md`) | **G1–G5** | one frozen-test run per stratum, Wilson 95 % CI, never pooled |
| **G7** `ur-Arab` stratum | ⏸ **DEFERRED** | plan exists (`PHASE46_URDU_SCRIPT_COLLECTION_PLAN.md`); **no corpus** | **B7** | C1 + compensation approval → collection → annotation (κ ≥ 0.70) |

**G2 is the only gate that has become READY.** G1, G3–G6 remain NO-GO.

---

## 4. Dependencies

```
P1 ─┐                       ┌─ P3 ── P3b ── P3c ─┐
P2 ─┴─► G1 (lawful import)  │                     ├─► G3 ─► G4 ─► G5 ─► G6 ─► EVALUATE
        (qualified reviewer) └─ P4 ── P5 ─────────┘         ▲
                                                            │
            M1 ✅ M2 ✅ M3 ✅ M4 ✅  ─► G2 (mapping freeze) ─┘

C1 ⏸ (deferred) + compensation ⏳ ─► G7 ─► ur-Arab stratum
```

- **G1 is the root dependency** — nothing downstream is actionable without it.
- **B3 (P5) is a hidden dependency of P2**: a reviewer cannot confirm erasure is
  honourable while no cascade delete exists.
- **C1 deferral does not block Roman Urdu**, only the Urdu-script gate.

---

## 5. Explicit GO / NO-GO decision

| Decision | **Verdict** | Basis |
|---|---|---|
| **Dataset import (RUHSOLD)** | 🔴 **NO-GO** | **P1 and P2 pending and blocking**; no qualified reviewer opinion exists. Secondary: P3/P5 unimplemented (B3, B4) |
| **Roman Urdu (`ur-Latn`) evaluation** | 🔴 **NO-GO** | G1, G3, G4, G5, G6 all NO-GO |
| **Urdu-script (`ur-Arab`) evaluation** | ⏸ **NO-GO (deferred)** | C1 deferred; no corpus exists |
| **Retrain / threshold change / deploy / engine switch** | 🔴 **NO-GO** | out of scope; engine `legacy`, hashes frozen |
| **Mapping freeze (G2)** | 🟢 **GO — but not executed** | M1–M4 approved; writing the frozen artefact would be a file write, **skipped under restriction 1** |

> **The expected dataset-import/evaluation decision remains NO-GO while P1/P2
> review is pending.** Confirmed: **NO-GO.**

---

## 6. Gate status

| Gate | FPR cap | Status |
|---|---|---|
| Roman Urdu (`ur-Latn`) | 0.15 | **`NOT PASSED`** |
| Urdu script (`ur-Arab`) | 0.15 | **`NOT PASSED`** — no corpus |

**Both quality gates remain `NOT PASSED`.**

---

## 7. Smallest safe next action (recommended, NOT performed)

**Recommended:** appoint a qualified legal/privacy reviewer and hand them
`PHASE411_P1P2_REVIEWER_CHECKLIST.md` to close **P1/P2**.

**Why this one:** it is the **root blocker (B1/B2)**, it unblocks G1, and it can
be started immediately **without any file write, download, import or evaluation**.
Closing P2 also requires **B3 (P5 cascade deletion)** to be built, so a
parallel engineering task is: *implement retention + cascade deletion with tests*.

**Actions deliberately NOT taken this phase:** no gated action was executed
automatically — no import, no evaluation, no mapping-freeze artefact, no P3–P5
implementation, no re-split.
