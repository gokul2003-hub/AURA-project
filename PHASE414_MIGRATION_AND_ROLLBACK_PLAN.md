# AURA Phase 4.14 — Migration & Rollback Plan (PROPOSED — NOT AUTHORIZED, NOT EXECUTED)

**This is a planning document. No migration was run, no data moved, no key
generated, no production file touched.**

Target: **Option A — SQLCipher-backed SQLite**, per the recommendation in
`PHASE414_ENCRYPTION_OPTIONS.md`, with **Option B** as an interim compensating
control. Prototype status: **NOT IMPLEMENTED** (dependency + policy approvals
missing).

---

## 0. Preconditions — ALL must be ✅ before any migration step runs

| # | Precondition | Status |
|---|---|---|
| **P0** | **Explicit written migration authorization** (this plan is not authorization) | 🔴 **NOT OBTAINED** |
| **P1** | **Key custody decided**: where the key lives (DPAPI / env / vault), who holds the recovery key, what happens if the custodian is unavailable | 🔴 **NOT DECIDED** — no secret store exists |
| **P2** | **Retention decision (B11) answered** — D1–D9 from `PHASE413_RETENTION_DECISION_REQUIRED.md` | 🔴 **UNANSWERED** |
| **P3** | **P1/P2 qualified legal/privacy review complete** (G1) | 🔴 **PENDING** |
| **P4** | SQLCipher build for **Python 3.14 / Windows** obtained and verified (`cipher_version` non-empty) | 🔴 **ABSENT** (probed) |
| **P5** | Decision on the **3 existing plaintext backups** (re-key, retire, or accept as legacy) | 🔴 **NOT DECIDED** |
| **P6** | Decision on the **OneDrive-synced path** (move tree out of sync, or accept ciphertext-in-cloud) | 🔴 **NOT DECIDED** |
| **P7** | Rotate the **hard-coded demo admin credential** (`backend.py:168,172`) — migrate *after*, so the migration preserves a weak credential | 🔴 **NOT DONE** |
| **P8** | **Rehearsal on a copy** in an isolated temp directory, with a measured restore drill | 🔴 **NOT DONE** |
| **P9** | Schema-version checkpoint (there is **no schema-version table**, inventory C8) | 🔴 **ABSENT** |
| **P10** | `PHASE412_DELETION_DEPENDENCY_MAP.md` reviewed — erasure/audit semantics unchanged by encryption | ⚠️ reviewed in Phase 4.12 |

**If any precondition is unmet → STOP. This plan remains a proposal.**

---

## 1. Scope — what is and is not migrated

### IN scope
- `CODE/BACKEND/aura.db` (16,805,888 B)

### OUT of scope (must be handled separately, or explicitly accepted)
| Artifact | Why out of scope |
|---|---|
| `data/backups/*.db` (3 files, 22.3 MB) | **Pre-existing plaintext copies of the same PII.** Encrypting only `aura.db` leaves the largest unencrypted copy in place. Needs its own decision (P5) |
| `data/phase2_eval/ur_test.csv`, `ur_val.csv` | **FROZEN evaluation splits** — hashed by manifest; encrypting changes bytes/manifests. **Must not be touched** |
| `models/*.json` (protected hashes), `models/hf_cache/` | Protected artifacts; engine `legacy` unaffected |
| `data/processed/*`, `data/external/*` | Derived; separate decision |
| `models/benchmark_run2.log` | Contains no personal data (needs confirmation before final sign-off) |
| Memory / live process | Not addressable by at-rest encryption (T6) |

### Invariants that must hold before AND after
- production engine **`legacy`**
- hashes `f31f4975d29a151f`, `5a9d94e267806ea0`, `f3a5ceb488f4a9ad`
- `ur_test.csv` `f18d80f3…`, `ur_val.csv` `8727f2ba…`
- DB: 596 rows · splits 137/29/31+399 · `training_runs` 8 · `model_versions` 12 · active `improved_v10` · `PRAGMA integrity_check` = `ok` · FK clean

---

## 2. Rollback triggers (abort immediately if any fire)

| ID | Trigger | Response |
|---|---|---|
| **R-T1** | `PRAGMA cipher_version` empty on the new build | **ABORT** — not a real SQLCipher (see trap, inventory §3) |
| **R-T2** | Post-migration `integrity_check` ≠ `ok`, or any row-count/split mismatch | **ABORT → §4 rollback** |
| **R-T3** | Any protected hash or frozen split differs | **ABORT → §4 rollback** |
| **R-T4** | Engine ≠ `legacy`, or `model_versions`/`training_runs` drift | **ABORT → §4 rollback** |
| **R-T5** | Service cannot start with the keyed driver | **ABORT → §4 rollback** |
| **R-T6** | Backup and restore drill fails at any point | **ABORT — do not migrate the live file** |
| **R-T7** | Key cannot be retrieved in rehearsal | **ABORT** — migration would create an unreadable DB |

---

## 3. Proposed migration procedure (rehearse on a COPY first — never on `aura.db`)

### Phase M0 — rehearsal only, isolated temp dir
1. Copy `aura.db` → isolated temp path. **Never write to the live file.**
2. Verify the SQLCipher build: `PRAGMA cipher_version` **non-empty** (R-T1).
3. Establish a **pre-migration manifest**: SHA256 of `aura.db`, row counts for
   every table, split counts, integrity result, engine, active model.
4. Rehearse **export → encrypt → reopen → verify → rollback** on the copy.
5. Run a **restore drill** from the rehearsal backup and re-verify the manifest.

**Gate:** only if M0 passes in full does M1 become eligible for authorization.

### Phase M1 — staging (still not the live file)
1. Re-take the manifest immediately before starting.
2. Take a **final plaintext backup** with `Connection.backup()` into
   `data/backups/` named `aura-pre-encryption-<stamp>.db`, record its SHA256 —
   this is the **rollback artifact** (kept per the retention decision, P2).
3. Confirm the backup opens and `integrity_check` = `ok` (**R-T6**).

### Phase M2 — encrypt
1. Stop the service (no concurrent writers; inventory §4 shows a connection per
   call).
2. Export plaintext from the verified backup; import into a **new** encrypted
   file using the external key (key supplied at runtime, **never written to
   disk, source, config or logs**).
3. Verify **all** invariants (§1) against the new file — any miss ⇒ R-T2/T3/T4.
4. **Objective encryption proof** (both required):
   - `PRAGMA cipher_version` → **non-empty**
   - a connection **without** the key fails to read the file
   - *(a successful `PRAGMA key` alone is NOT proof — inventory §3)*
5. Verify **free pages are unreadable** without the key (addresses `secure_delete=0`).

### Phase M3 — cutover
1. Repoint `DB_PATH` — requires a **keyed `connect`** in `backend.py:160`
   `db()`, plus reworking the **~6 URI read-only sites**
   (`tests_dataset_import.py:101,240`, `tests_model_adapter.py:171,618`).
2. Start the service; run health + auth checks (**read-only GET probes only** —
   Phase 4.13 showed live tests can write).
3. Re-verify the full invariant set. Any drift ⇒ R-T2/T3/T4/T5.

### Phase M4 — backups under encryption
1. Redefine `backup_db()` (`import_external_datasets.py:218-237`) so **both**
   source and destination are keyed.
2. Update the byte-equality assertion at
   `tests_dataset_import.py:286-311` — it currently *requires* byte-identical
   plaintext backups and **would fail** (inventory C5).
3. Re-key, retire, or formally accept the **3 legacy plaintext backups** (P5).

### Phase M5 — hygiene (separate authorizations, each independently reversible)
- `secure_delete=1` (addresses T7), `temp_store=1` (addresses temp spill),
  optional VACUUM; rotate the hard-coded credential (P7); resolve the OneDrive
  path (P6).

---

## 4. Rollback procedure (ordered, each step independently verifiable)

**Precondition:** the Phase M1 backup exists, SHA256-verified and confirmed to
open.

| Step | Action | Verification |
|---|---|---|
| **RB1** | Stop the service | no open handles on the DB |
| **RB2** | Move the encrypted file aside to `<name>.encrypted-<stamp>` (**move, never delete**) | encrypted file still present for forensics |
| **RB3** | Restore the Phase M1 plaintext backup to `aura.db` | SHA256 == recorded backup digest |
| **RB4** | Remove the keyed connection / restore original `db()` and read-only URI sites | diff shows only Phase-M3 lines reverted |
| **RB5** | Start the service | health 200 |
| **RB6** | Verify every invariant (§1): 596 rows, splits 137/29/31+399, 8 runs, 12 versions, `improved_v10`, `legacy`, integrity `ok`, FK clean, protected hashes, frozen splits | all ✅ |
| **RB7** | Record the rollback: trigger, time, operator, before/after digests, row counts | appended to audit evidence — **rollback is never silently erased** |

**Rollback limits — stated honestly:**
- Rows written **after** the backup and before the abort are **lost** (they
  exist only in the encrypted file, which is *retained*, not deleted — they can
  be recovered by hand if the key is available).
- Rollback **returns to plaintext**, i.e. it re-opens the exposure. It is an
  availability action, **not** a security improvement.
- The 3 legacy plaintext backups are unaffected by either direction.

---

## 5. Test plan (all against COPIES in isolated temp dirs — never live)

| ID | Test | Pass criterion |
|---|---|---|
| **T-M1** | Create encrypted DB, close, reopen with key | reads back identical rows |
| **T-M2** | Reopen with **wrong key** | hard failure, **no plaintext leaked** |
| **T-M3** | Reopen with **no key** | hard failure |
| **T-M4** | `cipher_version` probe | **non-empty** (guards the `PRAGMA key` trap) |
| **T-M5** | Round-trip every table + row count | equals pre-migration manifest |
| **T-M6** | Backup (both sides keyed) → restore on clean path | manifest matches; **no plaintext backup produced** |
| **T-M7** | Grep logs/reports produced during the run | **no key material, no raw personal records** |
| **T-M8** | Full invariant set (§1) | unchanged |
| **T-M9** | Rollback drill RB1–RB6 on the copy | original state restored |

**Not executed in this phase.** All blocked on P0/P1/P4.

---

## 6. Residual risks after a successful migration

| Risk | Status |
|---|---|
| In-memory plaintext / memory dump (T6) | **not mitigated** — inherent to at-rest encryption |
| Key compromise ⇒ whole DB exposed | **new risk** — single point of failure; demands P1 custody design |
| **Key loss ⇒ permanent total data loss** | **new, severe** — no key-recovery path exists; rehearsal (R-T7) is mandatory |
| `secure_delete=0` free pages | mitigated only *if* the whole file is encrypted; still worth setting explicitly |
| `temp_store` file spill | mitigated only if temp stays inside the encrypted file (verify after M2) |
| 3 legacy plaintext backups | **open until P5** |
| OneDrive-synced copies (T3) | addressed by A **only if** the tree stays in place (ciphertext synced) — otherwise resolve P6 |
| Retention (B11) / P1–P2 | **not addressed by encryption at all** |

---

## 7. Authorization record

| Item | Status |
|---|---|
| This plan executed? | ❌ **NO — proposal only** |
| Migration run on production? | ❌ **NO** |
| Encryption enabled? | ❌ **NO** |
| Production key generated? | ❌ **NO — none exists, none created** |
| Backups created, altered or deleted? | ❌ **NO** |
| Records rewritten / audit evidence touched? | ❌ **NO** |
| Protected artifacts or frozen splits changed? | ❌ **NO** |
| Dependency installed? | ❌ **NO** |
| **Requires:** written migration authorization, key-custody decision, retention decision (B11), P1/P2 review, SQLCipher build, backup decision, rehearsal sign-off | 🔴 **ALL OUTSTANDING** |

**Prototype: NOT IMPLEMENTED. Migration: NOT AUTHORIZED. Rollback: specified
but untested against production.**
