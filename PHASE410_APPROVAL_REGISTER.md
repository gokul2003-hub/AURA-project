# AURA Phase 4.10 — Approval Register

**Status: REGISTER OPEN — 11 of 11 approvals PENDING. 0 approved.**

**Documentation is not approval.** No item below is authorised. Only the user
(or a qualified legal reviewer, where marked) can change a status.

Consolidates `PHASE47_*`, `PHASE48_*` and `PHASE49_*`. No data was downloaded,
imported, purchased, annotated or evaluated; no threshold tuned; no frozen split
altered.

---

## 1. Master register

### P-series — privacy & legal (owner: **Legal / Privacy Reviewer**)

| ID | Item | Owner | Evidence required to close | Status | Approval record |
|---|---|---|---|---|---|
| **P1** | Licence scope vs **underlying tweet rights** | Legal reviewer | Written opinion: does MIT reach the tweets, or only the curators' artefact? Chain of title for the tweet content. | **PENDING** | *empty — no review received* |
| **P2** | **Lawful basis** / platform ToS / erasure rights | Legal reviewer | Documented lawful basis; ToS secondary-use assessment; a workable erasure procedure; DPIA determination; cross-border position. | **PENDING** | *empty* |
| **P3** | Redaction **before deduplication** | User / Data lead | Approval of the regex set + human spot-check procedure; confirmation it runs **before** dedup. | **PENDING** | *empty* |
| **P3b** | Versioned reproducible preprocessing | User / Engineer | Approval of `preprocess_version` scheme, pinned regex, NFKC, golden fixture; V5–V7 must re-derive exactly. | **PENDING** | *empty* |
| **P3c** | Salted text hashes | User / Engineer | Salt custody arrangement (stored separately, never committed); agreement that hashing ≠ anonymisation. | **PENDING** | *empty* |
| **P4** | Restricted access + counts-only reporting | User / Security | Role model, access logging, encryption-at-rest confirmation. | **PENDING** | *empty* |
| **P5** | Retention limit + **cascade deletion** | User / Security | Approved end date; deletion procedure reaching splits, manifests, cached features and scratch copies. | **PENDING** | *empty* |

### M-series — label mapping (owner: **User / ML Lead**)

Counts are **measured** (`Fine/train`, n = 7,208) and remain **unapproved
planning information**.

| ID | Item | Owner | Evidence required to close | Status | Approval record |
|---|---|---|---|---|---|
| **M1** | `1: Normal` (3,851) → `non_toxic`; `0: Abusive/Offensive` (1,729) → `toxic` | User / ML lead | Acceptance that "abusive/offensive" is a close-but-not-identical proxy for AURA toxicity. | **PENDING** | *empty* |
| **M2** | `2: Religious Hate` (563) & `3: Sexism` (603) → `toxic` + `identity_hate` | User / ML lead | Acceptance of the secondary-dimension assignment. | **PENDING** | *empty* |
| **M3** | **`4: Profane/Untargeted` (462) → EXCLUDED / unknown** | User / ML lead | Confirmation of exclusion (recommended) **or** authorisation of adjudication. | **PENDING** | *empty* |
| **M4** | **Binary headline only** is evaluable | User / ML lead | Acceptance that `severe_toxic`/`obscene`/`threat`/`insult` are structurally unrecoverable from a single label column. | **PENDING** | *empty* |

### C-series — Urdu-script commissioning (owner: **User / Programme owner**)

| ID | Item | Owner | Evidence required to close | Status | Approval record |
|---|---|---|---|---|---|
| **C1** | Commission ≈ **1,250** `ur-Arab` items; **3** native Urdu-script annotators + adjudicator; κ ≥ 0.70; **compensation approved** | User / Programme owner | Budget approval; **explicit compensation approval** (fair hourly, not per-label); wellbeing provisions signed off; source licence cleared. | **PENDING — blocking** | *empty* |

---

## 2. Status summary

| Status | Count | IDs |
|---|---|---|
| **APPROVED** | **0** | — |
| **PENDING** | **11** | P1, P2, P3, P3b, P3c, P4, P5, M1, M2, M3, M4, C1 *(12 slots, C1 blocking)* |
| **BLOCKED** | **2 of the 11** | **P1, P2** — cannot be closed without a qualified legal reviewer |
| REJECTED | 0 | — |

> The register carries **12 approval slots** (P1, P2, P3, P3b, P3c, P4, P5,
> M1, M2, M3, M4, C1). **All 12 are PENDING.**

## 3. Preserved planning information (unapproved, not actionable)

| Item | Value | Status |
|---|---|---|
| `Fine/train` usable pool | **6,746** (toxic 2,895 / non-toxic 3,851 / excluded 462) | unapproved planning data |
| Test negatives @40 % split | **1,540** (vs 250 target) | unapproved planning data |
| Frozen `ur_test.csv` | `f18d80f3e12e07a6f185079f7af0a2adf82ab35b3518c34145a9725f0538e9c5` | frozen, unchanged |
| Frozen `ur_val.csv` | `8727f2bacf41619173066466b8c992bc9cb0596e8e33c165d0f979072c61c13a` | frozen, unchanged |
| `Profane/Untargeted` | **EXCLUDED / unknown — never counted as verified non-toxic** | standing rule |
| `ur-Arab` corpus | **does not exist** | C1 open |

---

## 4. Go / No-Go checklist — lawful import → single evaluation

Every gate must be **GREEN** before the next stage. Current position: **stage 0.**

| # | Stage | Gate condition | Current |
|---|---|---|---|
| **G1** | **Lawful import** | **P1 + P2 closed** by a qualified legal reviewer, in writing | 🔴 **NO-GO** |
| **G2** | Mapping freeze | **M1–M4 approved** and recorded; `Profane/Untargeted` treatment frozen | 🔴 **NO-GO** |
| **G3** | Redaction & preprocessing | **P3, P3b, P3c, P4, P5 approved**; pipeline versioned and deterministic | 🔴 **NO-GO** |
| **G4** | Leakage-safe split | dedupe (exact **+ trigram near-dup**) applied; **group-aware** 40/20/40; assertions **L1–L7** pass; **no** upstream split adopted as-is | 🔴 **NO-GO** |
| **G5** | Hash freeze | test split SHA256 manifest recorded **before** any scoring | 🔴 **NO-GO** |
| **G6** | Single evaluation | **one** frozen-test run, **per script stratum**, never pooled; Wilson 95 % CI reported | 🔴 **NO-GO** |
| **G7** | `ur-Arab` stratum | **C1 approved**, data collected, annotated, validated | 🔴 **NO-GO** |

**Blocking path:** `P1+P2 → G1 → M1–M4 → G2 → P3–P5 → G3 → G4 → G5 → G6`; `C1 → G7` in parallel.

## 5. Gate status

| Gate | FPR cap | Current | Status |
|---|---|---|---|
| **Roman Urdu (`ur-Latn`)** | 0.15 | not evaluated — no approved import or mapping | **`NOT PASSED`** |
| **Urdu script (`ur-Arab`)** | 0.15 | not evaluated — **no corpus exists** | **`NOT PASSED`** |

Neither stratum may be marked PASS without a valid, task-matched, frozen,
independently held-out evaluation with confidence intervals.

---

## 6. Standing invariants

- Production engine remains **`legacy`**.
- Protected hashes `f31f4975…` / `5a9d94e2…` / `f3a5ceb4…` preserved.
- Frozen `ur_test` / `ur_val` unchanged.
- 596-row database, splits, 8 `training_runs`, `improved_v10` preserved.
- **No** legal conclusion is offered in this register.
