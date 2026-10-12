# AURA Phase 4.14 — Final Report
**SQLite Encryption-at-Rest Assessment & Safe Remediation Plan**

**Outcome: Stage 1 read-only assessment COMPLETE · Stage 2 options compared with
a RECOMMENDATION (not implemented) · Stage 3 PROTOTYPE = NOT IMPLEMENTED
(dependency and policy approvals both missing) · migration & rollback plan
specified but NOT AUTHORIZED · zero production writes · all invariants
PRESERVED.**

**G1 🔴 NO-GO · G3–G6 🔴 NO-GO · G7 ⏸ DEFERRED · both quality gates `NOT PASSED`.**

Companion deliverables: `PHASE414_STORAGE_INVENTORY.md`,
`PHASE414_ENCRYPTION_OPTIONS.md`, `PHASE414_MIGRATION_AND_ROLLBACK_PLAN.md`.

---

## 0. Workspace state recorded first (as required)

| Item | Finding |
|---|---|
| Git repository | **NONE** at root or under `comment toxicity` — unchanged from 4.12/4.13. **No change may be assumed committed** |
| Uncommitted-work proxy | 8 files modified 20:34–20:40 — **all Phase 4.13 deliverables** (`PHASE413_*`, `p3_privacy.py`, `tests_p3_privacy.py`) |
| Approach | **Additive only** — 3 new files created; **no existing file modified, moved or deleted** |
| Brief's referenced reports | all 4 present and read ✅ |

---

## 1. Stage 1 — Read-only assessment (summary)

Full detail: `PHASE414_STORAGE_INVENTORY.md`.

### 1.1 Where sensitive data is persisted

| Location | Size | Plaintext? |
|---|---|---|
| `CODE/BACKEND/aura.db` | 16.8 MB | ✅ **yes** — `SQLite format 3` magic |
| `data/backups/*.db` (**3 files**) | **22.3 MB** | ✅ **yes — full PII duplicates** |
| `data/processed/` (14), `data/external/` (+3 splits), `data/raw|train|validation|test` | ~0.6 MB | ✅ yes (derived) |
| `data/phase2_eval/` (13) | 1.4 MB | **frozen splits — out of scope** |
| `models/benchmark_run2.log` | 2,324 B | the **only** log file in the tree |
| WAL/SHM/journal sidecars | **none present** | `journal_mode = delete` |

⚠️ **The working tree is inside `C:\Users\gokul\OneDrive\...`** — `aura.db` and
all backups are **synced to OneDrive in plaintext**. This is the dominant
exposure and it is **not** mitigated by volume encryption.

### 1.2 Permissions, backups, secrets, startup

- **Permissions:** `Owner GOKUL\gokul`; SYSTEM / Administrators / gokul =
  FullControl. **Inherited NTFS ACL only — no encryption of any kind.**
- **Backup practice:** `Connection.backup()` → byte-identical **plaintext**;
  "best-effort, never fatal" (failure only prints a warning). **No restore
  procedure exists at all.**
- **Secret management: NONE.** No vault, no `.env`, no DPAPI usage; the app
  reads only non-secret env vars. Passwords are PBKDF2-SHA256/150k + salt
  (`backend.py:162`) — sound.
  ⚠️ **A hard-coded demo admin credential exists in `backend.py:168,172`** (and
  as the default in 5 test files), and `init_db()` **re-seeds it every
  startup**. Value deliberately **not reproduced** in this report.
- **Startup:** `init_db()` = `CREATE TABLE IF NOT EXISTS` + ad-hoc
  `PRAGMA table_info` column adds. **No versioned migration framework, no
  schema-version table.**
- **Storage posture read live (read-only):** `secure_delete = 0` (freed pages
  not overwritten → T7), `temp_store = 0` (file → unencrypted spill),
  `auto_vacuum = 0`, `synchronous = 2`, `page_size = 4096`.

### 1.3 Is SQLCipher available? — **NO. Probed, not assumed.**

| Probe | Result |
|---|---|
| `find_spec` → `pysqlcipher3` / `sqlcipher3` / `sqlcipher3_bytes` / `apsw` | **absent ×4** |
| `find_spec` → `cryptography` / `Crypto` / `pysqlite3` | **absent ×3** |
| `pip list` (sqlcipher/cryptography/pycryptodome/apsw) | **none installed** |
| `connect(cipher=…)`, `connect(key=…)`, `connect(kdf_iter=…)` | **`TypeError` ×3** |
| `PRAGMA cipher_version` / `cipher` / `kdf_iter` / `cipher_integrity_check` | **`[]` ×4** |
| `PRAGMA compile_options` containing `CIPHER` | **NONE** — 43 options, **stock SQLite 3.50.4, not SQLCipher-patched** |
| `sqlcipher` / `openssl` on PATH | **absent ×2** |

> ### ⚠️ Critical trap documented
> **`PRAGMA key = '…'` is ACCEPTED with no error on stock SQLite.** Stock
> SQLite silently ignores unknown PRAGMAs. **A migration test could "pass" while
> nothing is encrypted.** The only valid proofs are: `cipher_version`
> returns a **non-empty** string, **and** a keyless connection fails to read
> the file. This false-positive is recorded as a named risk (**C7**) because it
> is the most likely way an encryption rollout would be falsely declared done.

### 1.4 Connection / migration / concurrency / backup map

`db()` (`backend.py:159-160`) = plain `sqlite3.connect(DB_PATH)`, **no PRAGMAs,
no key**, connection-per-call. **~6 sites use `file:…?mode=ro` URI read-only
connections** (`tests_dataset_import.py:101,240`, `tests_model_adapter.py:171,618`,
plus verification scripts). Backups via `Connection.backup()`; **no restore
procedure**; test isolation is already good
(`tests_audit_threshold_phase41.py:175-192` repoints `DB_PATH`;
`tests_dataset_import_phase4.py:169` refuses to target live `aura.db`).

### 1.5 Database vs filesystem vs backup encryption — kept distinct

**`aura.db` is PLAINTEXT. It is NOT encrypted at rest.** No compensating
control has been evidenced. Three separate controls, none present:

| Control | State |
|---|---|
| A. Database encryption | ❌ absent (plaintext file) |
| B. Filesystem/volume encryption | ❌ **not evidenced** (ACL only; BitLocker status not checked) |
| C. Encrypted backups | ❌ absent — 3 plaintext backups |
| D. Field-level encryption | ❌ absent |

### 1.6 Compatibility risks — **12 catalogued (C1–C12)**

Headlines: no Py3.14/Win binding (C1) · every `connect` must be keyed (C2) ·
URI read-only pattern friction (C3) · **keys are per-connection** (C4) ·
backup byte-equality test must be redefined (C5) · **3 legacy backups stay
plaintext** (C6) · **`PRAGMA key` false positive** (C7) · no schema-version
gate (C8) · `secure_delete=0` (C9) · `temp_store` spill (C10) · in-process
plaintext (C11) · **no secret store for the key** (C12).

---

## 2. Stage 2 — Options compared → **RECOMMENDATION**

Full detail: `PHASE414_ENCRYPTION_OPTIONS.md`.

Threat model fixed first (T1–T7), including **T3 = OneDrive cloud sync**, which
BitLocker does **not** cover because sync transfers file bytes, not an unlocked
volume.

| Dimension | **A — SQLCipher** | **B — OS/volume** | **C — Field-level** |
|---|---|---|---|
| Scope | **whole DB file** (tables, free pages, journal, temp spill) | whole volume/file | **selected columns only** |
| vs. cloud sync (T3) | ✅ ciphertext synced | ⚠️ **does not protect synced file** | ⚠️ partial |
| Key management | **required — none exists** | OS/TPM-managed | required, rotation costly |
| Operational complexity | high (driver swap) | **low, zero code** | high (every read/write path) |
| Backup/restore | both sides must be keyed; 3 legacy backups unaffected | inherits only if stored on the volume | unchanged |
| Migration risk | **high** (full rewrite, no schema gate) | **very low, reversible** | medium (+ backfill) |
| **Testability** | ✅ **objective** (wrong key ⇒ unreadable) | ⚠️ poor — OS property, not CI-observable | ✅ good |
| Available here | ❌ **absent** | ✅ OS facility (status **not evidenced**) | ⚠️ no crypto lib present |

> ### Recommendation (proposed only)
> **Layered: Option A as the target architecture, Option B as an immediate
> no-code interim control, Option C only for specific columns if needed.**
>
> Also recommended independently: **move the tree out of the OneDrive-synced
> path**, set `secure_delete=1` and `temp_store=1`, and **rotate the hard-coded
> demo credential before** any migration.
>
> **NOT AUTHORIZED, NOT IMPLEMENTED.**

---

## 3. Stage 3 — **PROTOTYPE = NOT IMPLEMENTED**

Per the brief: *"If dependencies or policy approvals are missing, stop at the
assessment and mark the prototype NOT IMPLEMENTED."* **Both are missing.**

| Gate | Finding |
|---|---|
| **Dependency** | ❌ No SQLCipher, no `cryptography`, no `Crypto` (probed §1.3). Installing one would alter the environment — outside this stage's authorization |
| **Policy approval** | ❌ No key-custody mechanism (§1.2), **retention unanswered (B11)**, **P1/P2 review pending**. Creating a key before a custodian exists would produce an unmanaged secret — explicitly prohibited |
| **Hand-rolled crypto alternative** | ❌ **Declined.** A bespoke cipher in a report is indistinguishable from a credible security claim and cannot be reviewed to production standard here |

**Verification performed:**

| Check | Result |
|---|---|
| Encrypted-prototype files present | **NONE** |
| `sqlcipher3` / `cryptography` / `Crypto` installed | **False ×3** |
| Production key generated | **NO — none exists, none created** |
| `aura.db` magic | **`b'SQLite format 3'`** — still plaintext, unchanged |
| Dependency installed | **NO** |

**Prototype: NOT IMPLEMENTED. No key generated. No encrypted DB created.**

---

## 4. Migration & rollback plan (specified, NOT authorized)

Full detail: `PHASE414_MIGRATION_AND_ROLLBACK_PLAN.md`.

- **10 preconditions (P0–P10)**, all 🔴 outstanding — incl. written
  authorization, key custody, retention (B11), P1/P2 review, SQLCipher build,
  legacy-backup decision, OneDrive decision, credential rotation, rehearsal,
  schema-version checkpoint.
- **Scope:** `aura.db` only. **Explicitly excluded:** the 3 plaintext backups
  (separate decision), frozen `ur_*.csv` (must not be touched), protected model
  artifacts.
- **7 rollback triggers (R-T1…R-T7)**, including *"key cannot be retrieved in
  rehearsal ⇒ abort"*.
- **Phases M0–M5:** rehearse on a **copy** first → staging backup (the rollback
  artifact) → encrypt → cut over (repoint `db()` + rework ~6 URI sites) →
  keyed backups → hygiene.
- **Objective encryption proof required:** non-empty `cipher_version` **AND**
  keyless connection fails (**guards the `PRAGMA key` trap**).
- **Rollback RB1–RB7:** move (never delete) the encrypted file → restore
  verified backup → revert code → verify invariants → **record the rollback in
  audit evidence**.
- **Honest limits stated:** post-backup rows are lost (retained in the
  encrypted file, not deleted); **rollback restores availability but returns to
  plaintext**; the 3 legacy backups are unaffected either way.
- **9 test scenarios (T-M1…T-M9)** — all isolated, all **not executed**.

---

## 5. Acceptance criteria — verified vs proposed vs requiring approval

| Statement | Status |
|---|---|
| `aura.db` encrypted | ❌ **NOT ENCRYPTED — plaintext, stated explicitly** |
| SQLCipher available | ❌ **NO — verified absent by 12 probes** |
| Encryption enabled / migration run | ❌ **NO — not authorized, not performed** |
| Production DB modified / schema migrated | ❌ **NO** |
| Production key generated | ❌ **NO — none exists** |
| Credentials/keys exposed in any report | ❌ **NO** — the hard-coded credential is *referenced*, never reproduced |
| Records, backups or audit evidence deleted/rewritten | ❌ **NO** |
| Dependency installed | ❌ **NO** |
| Live-backend test that can write | ❌ **NOT RUN** (read-only `mode=ro` + `PRAGMA` probes only) |
| Dataset import/eval/retrain/threshold/deploy | ❌ **NONE** |
| **Storage inventory (Stage 1)** | ✅ **VERIFIED — read-only probes** |
| **Options comparison (Stage 2)** | ✅ **COMPLETED — evidence-based** |
| **Recommendation (layered A + B + C)** | 📋 **PROPOSED — needs approval** |
| **Migration & rollback plan** | 📋 **PROPOSED — needs authorization** |
| **Prototype** | ❌ **NOT IMPLEMENTED — dependency + policy missing** |
| **All §6 approvals** | 🔴 **REQUIRED** |

**Verified** = §1 Stage 1 findings and §5 invariant checks (directly measured).
**Proposed** = the recommendation and the migration/rollback plan (not executed).
**Requires approval** = every item in `PHASE414_ENCRYPTION_OPTIONS.md` §6.

---

## 6. Safety verification (end of phase)

| Invariant | Expected | Observed | Result |
|---|---|---|---|
| Production engine | `legacy` | **`legacy`** | ✅ |
| `tuned_threshold.json` | `f31f4975d29a151f` | matches | ✅ **UNCHANGED** |
| `phase2_benchmark.json` | `5a9d94e267806ea0` | matches | ✅ **UNCHANGED** |
| `phase3_benchmark.json` | `f3a5ceb488f4a9ad` | matches | ✅ **UNCHANGED** |
| `ur_test.csv` / `ur_val.csv` | frozen digests | match | ✅ **UNCHANGED** |
| Integrity / FK | `ok` / clean | `ok` / clean | ✅ |
| `dataset_samples` | 596 | **596** | ✅ |
| Splits | 137/29/31+399 | **137 / 29 / 31 / 399** | ✅ |
| `training_runs` / `model_versions` / active | 8 / 12 / `improved_v10` | **8 / 12 / `improved_v10`** | ✅ |
| `journal_mode` | `delete` | **`delete`** | ✅ **no migration occurred** |
| Backups | 3, untouched | **3, all original timestamps** | ✅ |
| `moderation_results` / `audit_logs` | 1,630 / 1,682 | **1,630 / 1,682** | ✅ **unchanged from Phase 4.13** |
| `DATA_ERASURE` | 0 | **0** | ✅ |

**Unexplained changes: NONE.** **No count was repaired by deleting records or
restoring a database.**

### Files changed
| File | Change |
|---|---|
| `PHASE414_STORAGE_INVENTORY.md` | **NEW** |
| `PHASE414_ENCRYPTION_OPTIONS.md` | **NEW** |
| `PHASE414_MIGRATION_AND_ROLLBACK_PLAN.md` | **NEW** |
| `PHASE414_REPORT.md` | **NEW** |
| Everything else | **NOT MODIFIED** |

---

## 7. Updated blocker register

| ID | Blocker | 4.13 | **4.14** |
|---|---|---|---|
| **B1** P1 rights/provenance | 🔴 open | 🔴 **open** |
| **B2** P2 lawful basis/ToS/erasure | 🔴 open | 🔴 **open — also needs retention D1–D9** |
| **B3** P5a retention machinery | 🔴 open (decision required) | 🔴 **open — unchanged** |
| **B4/B5/B6** P3 / P3c / P3b | ✅ closed | ✅ **closed (36/36)** |
| **B7** C1 deferred | ⏸ deferred | ⏸ **deferred** |
| **B8** upstream splits unusable | 🔴 open | 🔴 **open** |
| **B9** P4b runtime / P4c tests | 🔴 partial | 🔴 **partial — P4b runtime still unverified; P4c now *characterised*** |
| **B10** **P4c encryption at rest** | 🔴 proven absent | 🔴 **ASSESSED → remediation plan proposed; REMAINS OPEN. Root cause now documented: no SQLCipher (12 probes), no key custody (C12), no secret store. Prototype NOT IMPLEMENTED** |
| **B11** retention decision | 🔴 new | 🔴 **open — unchanged** |
| **B12** live-test isolation defect | 🔴 new | 🔴 **open — unchanged** |
| **B13 (new)** plaintext backups ×3 (22.3 MB PII) | — | 🔴 **NEW — 1.6× the live DB's plaintext exposure; outside any DB-only encryption scope** |
| **B14 (new)** no secret/key-custody mechanism | — | 🔴 **NEW — hard prerequisite for A and C** |
| **B15 (new)** working tree inside OneDrive-synced path | — | 🔴 **NEW — plaintext cloud replication; volume encryption does not cover it** |
| **B16 (new)** `PRAGMA key` false-positive trap | — | 🟡 **NEW — documented as C7; any future test must assert non-empty `cipher_version` + keyless-open failure** |
| **B17 (new)** hard-coded demo admin credential re-seeded at startup | — | 🔴 **NEW — must be rotated before migration, not preserved by it** |

---

## 8. Updated gate register

| Gate | 4.13 | **4.14** | Prerequisite still missing |
|---|---|---|---|
| **G1** lawful import | 🔴 NO-GO | 🔴 **NO-GO** | **P1/P2 qualified review** |
| **G2** mapping freeze | 🟢 READY | 🟢 **READY** | — |
| **G3** redaction & preprocessing | 🔴 NO-GO (narrowed) | 🔴 **NO-GO — scope clarified** | P3 ✅ 36/36; now explicitly: **P4b runtime evidence, P4c/B10 encryption authorization, B11 retention, B13 backups, B14 key custody, endpoint wiring (R1)** |
| **G4** leakage-safe split | 🔴 NO-GO | 🔴 **NO-GO** | needs G1 |
| **G5** hash freeze | 🔴 NO-GO | 🔴 **NO-GO** | depends on G4 |
| **G6** single evaluation | 🔴 NO-GO | 🔴 **NO-GO** | depends on G1–G5 |
| **G7** `ur-Arab` | ⏸ DEFERRED | ⏸ **DEFERRED** | C1 + compensation; no corpus |

> **Note:** encryption-at-rest (B10) is a **privacy-readiness** item for G3. It
> does **not** unblock G1 — G1 turns solely on the P1/P2 legal review.

---

## 9. Final decision

| Decision | Verdict |
|---|---|
| **Encryption enabled** | ❌ **NO — not authorized** |
| **Migration executed** | ❌ **NO — proposal only** |
| **Prototype** | ❌ **NOT IMPLEMENTED — dependency + policy approvals missing** |
| **Production key generated** | ❌ **NO** |
| **Dataset import (G1)** | 🔴 **NO-GO — pending qualified P1/P2 review** |
| **Roman Urdu evaluation (G3–G6)** | 🔴 **NO-GO** |
| **Urdu-script evaluation (G7)** | ⏸ **DEFERRED** |
| **Encryption-at-rest claim** | ❌ **NOT MADE — plaintext confirmed and characterised** |

| Quality gate | Cap | Status |
|---|---|---|
| Roman Urdu (`ur-Latn`) | 0.15 | **`NOT PASSED`** |
| Urdu script (`ur-Arab`) | 0.15 | **`NOT PASSED`** |

### Open decisions for the authorized reviewer (exact questions)

1. **Migration authorization (P0):** *Approve or decline the Option A SQLCipher
   migration described in `PHASE414_MIGRATION_AND_ROLLBACK_PLAN.md`?*
2. **Key custody (P1/B14):** *Where does the encryption key live (DPAPI /
   environment / vault), who is the custodian, and what is the recovery
   procedure if the custodian is unavailable?*
3. **Interim control (P6/B15):** *Move the working tree out of the OneDrive
   sync path, and/or enable volume encryption — which, and who performs it?*
4. **Legacy backups (P5/B13):** *Re-key, retire, or formally accept the 3
   existing plaintext backups (22.3 MB of PII)?*
5. **Credential (P7/B17):** *Authorize rotating the hard-coded demo admin
   credential before migration?*
6. **Still open from Phase 4.13:** retention end date (B11) · P1/P2 reviewer
   (G1) · P4b runtime logging exercise · B12 live-test isolation fix.

**No gated action was performed. G1 remains NO-GO. G3–G6 remain NO-GO. G7 remains deferred.**
