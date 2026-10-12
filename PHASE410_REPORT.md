# AURA Phase 4.10 — Final Report

**Outcome: approval tracking established. 12 of 12 approvals PENDING, 0 approved,
0 blockers closed. Both quality gates remain `NOT PASSED`.**

Deliverables: `PHASE410_APPROVAL_REGISTER.md`, this report.

---

## 1. Completed documentation (Phases 4.7–4.10)

| Phase | Artifact | Contribution |
|---|---|---|
| 4.7 | `PHASE47_SPLIT_VERIFICATION_PLAN.md` | V1–V11 procedure, upstream metadata conflicts |
| 4.7 | `PHASE47_LABEL_MAPPING.md` | proposed mappings, `Profane/Untargeted` exclusion |
| 4.7 | `PHASE47_PRIVACY_PLAN.md` | MIT scope limits, PII plan |
| 4.8 | `PHASE48_SCRATCH_VERIFICATION.md` | **measured** V1–V11 results |
| 4.8 | `PHASE48_REPORT.md` | three decisive findings |
| 4.9 | `PHASE49_LABEL_MAPPING_DECISIONS.md` | M1–M4 decision table |
| 4.9 | `PHASE49_PRIVACY_REVIEW_CHECKLIST.md` | P1–P2 questions, P3–P5 controls, C1 |
| 4.10 | `PHASE410_APPROVAL_REGISTER.md` | **master register + go/no-go** |

## 2. Register — every approval is PENDING

| Group | IDs | Owner | Status |
|---|---|---|---|
| Privacy/legal | **P1, P2** | Legal/privacy reviewer | **PENDING — BLOCKED** (needs qualified reviewer) |
| Controls | **P3, P3b, P3c, P4, P5** | User / data & security leads | **PENDING** (specs ready) |
| Label mapping | **M1, M2, M3, M4** | User / ML lead | **PENDING** (counts measured) |
| Commissioning | **C1** | User / programme owner | **PENDING — blocking** |

**APPROVED: 0.** Per instruction, nothing was set to APPROVED — no explicit
authorisation or qualified review evidence exists for any item. **Documentation
alone is not approval.**

## 3. Decisions required from the user

1. **P1 / P2** — appoint a qualified legal reviewer to opine on: MIT vs the
   **underlying tweet rights**; chain of title; **lawful basis**; platform ToS;
   erasure/objection rights; cross-border transfer; DPIA applicability.
   *These cannot be closed by this project — only by a qualified reviewer.*
2. **M1** — accept `Normal → non_toxic` and `Abusive/Offensive → toxic`.
3. **M2** — accept `Religious Hate`/`Sexism` → `toxic` + `identity_hate`.
4. **M3** — confirm **exclusion** of `Profane/Untargeted` as unknown (recommended),
   *or* authorise adjudication.
5. **M4** — accept that **only the binary headline** is evaluable from RUHSOLD.
6. **P3–P5** — approve the redaction/preprocessing/hashing/access/retention specs.
7. **C1** — approve commissioning ≈1,250 `ur-Arab` items and **explicitly approve
   annotator compensation** (fair hourly, not per-label).

## 4. Go / No-Go status — all stages NO-GO

| # | Stage | Gate | Current |
|---|---|---|---|
| **G1** | Lawful import | P1 + P2 closed in writing | 🔴 **NO-GO** |
| **G2** | Mapping freeze | M1–M4 approved | 🔴 **NO-GO** |
| **G3** | Redaction & preprocessing | P3, P3b, P3c, P4, P5 approved | 🔴 **NO-GO** |
| **G4** | Leakage-safe split | dedup + group-aware 40/20/40 + L1–L7 | 🔴 **NO-GO** |
| **G5** | Hash freeze | test split SHA256 manifest before scoring | 🔴 **NO-GO** |
| **G6** | Single evaluation | one frozen-test run per stratum, never pooled | 🔴 **NO-GO** |
| **G7** | `ur-Arab` stratum | C1 approved, data collected and validated | 🔴 **NO-GO** |

**Current position: stage 0.** The phase is **not** evaluation-ready.

## 5. Preserved as unapproved planning information

- `Fine/train` usable pool **6,746** (toxic 2,895 / non-toxic 3,851 /
  **excluded 462**); test negatives @40 % **1,540** vs 250 target.
- **`Profane/Untargeted` remains EXCLUDED / unknown and is never counted as
  verified non-toxic** — that rule is unchanged and not subject to reinterpretation.
- `ur-Arab` corpus **does not exist**; no Urdu-script data is claimed.

## 6. Safety

| Check | Result |
|---|---|
| **Production engine** | **`legacy`** |
| `tuned_threshold.json` | `f31f4975d29a151f…` **UNCHANGED** |
| `phase2_benchmark.json` | `5a9d94e267806ea0…` **UNCHANGED** |
| `phase3_benchmark.json` | `f3a5ceb488f4a9ad…` **UNCHANGED** |
| Frozen `ur_test` / `ur_val` | **UNCHANGED** |
| SQLite integrity / FK | **ok** / **clean** |
| Rows / splits | **596**; **137 / 29 / 31 + 399 unassigned** |
| `training_runs` / `model_versions` | **8 / 12** |
| Active model | `improved_v10` |
| Downloaded / imported / purchased / annotated | **NONE** |
| Evaluation run / thresholds tuned | **NONE** |
| Frozen splits altered | **NONE** |
| Project `data/` written | **NONE** (mtime sweep clean) |
| Legal conclusion offered | **NONE** |
| User changes preserved | **yes** |

## 7. Gate status

| Gate | FPR cap | Status |
|---|---|---|
| Roman Urdu (`ur-Latn`) | 0.15 | **`NOT PASSED`** — no approved import or mapping |
| Urdu script (`ur-Arab`) | 0.15 | **`NOT PASSED`** — no corpus exists |

---

**Phase 4.10 is complete as documentation and remains BLOCKED on approval.**
No stage may be reported as approved or evaluation-ready while any blocking
approval (P1, P2, C1) is open.
