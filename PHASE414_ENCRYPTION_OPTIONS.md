# AURA Phase 4.14 — Stage 2: Encryption Options Comparison

**Comparison only. Nothing implemented. No key generated for production, no
migration, no production write.**

Evidence base: `PHASE414_STORAGE_INVENTORY.md` (Stage 1).

---

## 0. Threat model fixed first (an option is only "best" relative to a threat)

| ID | Threat | Realistic given current posture? |
|---|---|---|
| **T1** | Offline theft of the machine / disk, or unauthorised copy of `aura.db` or `data/backups/*.db` | **Yes** — user-profile ACL only, 3 plaintext backups |
| **T2** | Malware or another process running as the same user reads the file | **Yes** — no isolation |
| **T3** | Cloud sync / accidental share of `code` folder (it sits in OneDrive Desktop) | **Yes** — path is `C:\Users\gokul\OneDrive\...` |
| **T4** | Backup file exfiltrated independently of the machine | **Yes** — backups are free-standing plaintext |
| **T5** | SQL injection / attacker with app-level DB access | Partially — mitigation is input handling, not encryption |
| **T6** | Memory dump / live process inspection | **Yes** — any at-rest control is bypassed by design |
| **T7** | Deleted-row recovery from free pages (`secure_delete=0`) | **Yes** — independent of encryption |

**Note T3:** the working tree is inside a **OneDrive-synced** folder. This means
`aura.db` and all backups are, by default, **replicated to cloud storage** in
plaintext. That materially raises the value of *some* at-rest control and is
arguably the strongest argument for acting.

---

## 1. The three options

### Option A — SQLCipher-backed SQLite (encrypted database, key external)

Replaces the driver with a SQLCipher build; `PRAGMA key` per connection;
whole-file AES-256-CBC + HMAC-SHA1/256 page encryption.

### Option B — OS / volume-level encryption as a compensating control

BitLocker (volume), EFS (per-file), or DPAPI (per-secret). Application code
unchanged; the OS transparently encrypts at rest.

### Option C — Application-level encryption for selected fields

Encrypt specific high-sensitivity columns (`moderation_results.message`,
`feedback.input_text`, `live_events.transcript`) in the app before INSERT,
decrypt on read. DB file itself stays SQLite plaintext.

---

## 2. Comparison matrix

| Dimension | **A — SQLCipher** | **B — OS / volume** | **C — Field-level** |
|---|---|---|---|
| **Protection scope** | **Whole DB file**: all tables, indexes, free pages, journal/WAL, temp spill *inside* the DB | **Whole volume/file**, incl. backups *on that volume* and temp files | **Only selected columns**; metadata (table names, row counts, `user_id`, `created_at`, `result_json`, `audit_logs`) stays plaintext |
| **T1** offline theft | ✅ strong | ✅ strong | ⚠️ partial — structure + metadata exposed |
| **T2** same-user process | ❌ no (key is in-process) | ❌ no (volume unlocked) | ❌ no |
| **T3** cloud sync | ✅ **yes — encrypted blob synced** | ⚠️ **depends** — OneDrive syncs *files*, not the unlocked volume ⇒ **BitLocker does NOT protect a synced file**; EFS/DPAPI-sidecar might | ⚠️ partial — columns protected, rest not |
| **T4** backup exfiltration | ✅ if backups taken from keyed conn | ⚠️ only if backups stay on the encrypted volume | ⚠️ partial |
| **T7** free-page recovery | ✅ encrypted pages unreadable | ✅ if volume encrypted | ❌ plaintext pages still readable |
| **Key management** | **Required**: key per connection, external to DB (env/DPAPI/vault). **No store exists today** (§2c of inventory) | **OS-managed** — TPM/PIN/recovery key; **no app change** | Required: per-record or per-field key, external; rotation is expensive |
| **Operational complexity** | **High** — driver swap on Py3.14/Win, every `connect` keyed, key custody | **Low** for BitLocker (ops task); **near-zero code** | **High** — schema change, encrypt/decrypt in every read/write path |
| **Backup/restore** | Must key **both** sides of `Connection.backup()`; existing byte-equality test (`tests_dataset_import.py:286-311`) redefinition needed. **3 existing backups stay plaintext** unless separately migrated | Transparent — backups inherit protection *only if stored on the protected volume* | Backup unaffected (DB already plaintext); protects the copied columns anyway |
| **Migration risk** | **High** — full file rewrite (`sqlcipher_export`/decrypt-rekey); no schema-version table to gate on (C8); all 3 `data/backups/*.db` become oracles of pre-migration plaintext | **Very low** — no data movement, reversible by decrypting the volume | **Medium** — column rewrite + backfill; needs a version marker to know which rows are encrypted |
| **Testability** | ✅ **Excellent & objective**: wrong key ⇒ `file is not a database`; `cipher_version` non-empty proves the build | ⚠️ **Poor** — status is an OS property (`manage-bde -status`), not observable by the app's test suite; hard to assert in CI | ✅ good: round-trip, wrong-key, tamper-detect per field |
| **Availability here** | ❌ **absent** (probed: no binding, no binary, no cipher PRAGMA, stock SQLite) | ✅ OS facility — but **not evidenced as enabled** | ✅ implementable in stdlib… **but see §5** |
| **Performance** | ~5–15% write overhead (page encryption + HMAC) | negligible | per-column; adds base64/hex expansion (~33%) |
| **Failure mode** | Wrong/missing key ⇒ **total DB unreadable** (catastrophic if key lost) | Volume unlock failure ⇒ **all files unreadable** | Degraded — non-encrypted columns still leak |

---

## 3. Interactions with AURA-specific constraints

| Constraint | Effect on the choice |
|---|---|
| **Production engine `legacy`**, protected hashes, frozen splits | **All three options leave model/artifact files untouched.** Encryption of `aura.db` does **not** affect `models/*.json` or `data/phase2_eval/*.csv`. The **frozen `ur_*.csv` splits must NOT be encrypted** — they are evaluation inputs, hashed by manifest |
| **P5 cascade deletion / `audit_logs` preservation** | Encrypted at rest, erasure semantics unchanged. **But** `secure_delete=0` (T7) means *logical* erasure still leaves free pages — independent remediation |
| **Retention decision (B11, still unanswered)** | Encryption ≠ retention. A does nothing for P2.12; must not be presented as satisfying it |
| **No schema-version table (C8)** | Blocks safe A/C migration (no gate point). B needs none |
| **OneDrive-synced path (T3)** | Strongly favours **A**; **B does not help** for synced files |
| **`tests_dataset_import.py` byte-equality backup test** | Breaks under A unless backup is redefined as keyed⇒keyed |
| **No secret store (§2c)** | **A and C both blocked** until an external key source exists |
| **Hard-coded demo admin credential in `backend.py:168,172`** | Independent finding: rotation/seeding must be resolved *before* any migration, or the migration will happily preserve a weak credential |

---

## 4. Recommendation

> **Recommend: layered — adopt Option A as the target architecture, with
> Option B as an immediate, no-code compensating control, and Option C only for
> specific columns if field-granular separation is later required.**
>
> **NOT AUTHORIZED, NOT IMPLEMENTED.** Requires an explicit migration
> authorization (§Stage 3 / `PHASE414_MIGRATION_AND_ROLLBACK_PLAN.md`).

| Order | Action | Why |
|---|---|---|
| **1st (interim, ops-only)** | **Option B — enable volume/file encryption**, and **move the working tree + `data/backups` out of the OneDrive-synced path** | Zero code change, immediately reduces T1/T3/T4. Must verify with the OS — **not currently evidenced**. Note B does **not** protect OneDrive-synced copies |
| **2nd (target)** | **Option A — SQLCipher**, key external, keyed backups | Only option that protects the **whole DB file including free pages and temp spill**, is objectively testable, and survives cloud sync as ciphertext. Directly addresses T1/T3/T4/T7 |
| **3rd (conditional)** | **Option C — field encryption** for `message` / `input_text` / `transcript` | Only if defence-in-depth for specific columns is required. **Does not** replace A; metadata stays exposed |
| **Always also** | `secure_delete=1` (+ optional VACUUM) and `temp_store=1` | Fixes T7 and removes temp spill, **independently of any encryption decision** — but both need authorization as config changes |

### Why not B alone

**BitLocker does not protect a file that OneDrive syncs as ciphertext-free
bytes.** With the project under `C:\Users\gokul\OneDrive\...`, the at-rest
copies in cloud sync are the dominant exposure, and only **file-level**
encryption (A, or C for columns) addresses that.

### Why not C alone

Column encryption leaves `audit_logs.details`, `result_json`, row counts,
`user_id` and timestamps readable — insufficient against T1/T4, and it is the
most invasive change to application read/write paths.

### Why A despite the migration risk

It is the only option whose protection scope matches the inventory's actual
findings (plaintext DB **+** plaintext backups **+** free pages **+** temp
spill **+** cloud sync), and the only one with an **objective pass/fail test**.

---

## 5. Stage 3 feasibility determination

| Candidate prototype | Feasible here? | Basis |
|---|---|---|
| **A — SQLCipher** | ❌ **NO** | Dependency absent (probed, §3 of inventory). Installing one would alter the environment — outside this stage's authorization |
| **B — OS/volume** | ❌ **NO** | Would change machine-wide storage configuration; status is not observable from the test suite; **needs ops authorization** |
| **C — Field-level** | ⚠️ **Conditionally** | No third-party crypto library present (`cryptography`/`Crypto` both absent). A prototype would require either installing a crypto library (**not authorized**) or **hand-rolled cryptography** — which must **not** be presented as production-viable |

### Decision: **PROTOTYPE = NOT IMPLEMENTED (stopped at assessment)**

Per the brief: *"If dependencies or policy approvals are missing, stop at the
assessment and mark the prototype NOT IMPLEMENTED."*

**Both are missing:**

1. **Dependency missing** — no SQLCipher, no `cryptography`, no `Crypto` (§3 of
   the inventory; re-verified).
2. **Policy approval missing** — no approved key-management mechanism exists
   (§2c of the inventory), **no retention decision (B11)**, and **P1/P2 review is
   still pending**. Generating any key before a custodian and storage location
   are approved would create an unmanaged secret — explicitly prohibited by
   *"Do not create an encryption key in source code, logs, reports, or committed
   configuration."*

**Additional reason not to hand-roll:** a bespoke cipher in a report would be
inseparable from a credible security claim, and cannot be reviewed to
production standard within this stage. Declining it is the correct outcome, not
an incomplete one.

> **PROTOTYPE STATUS: NOT IMPLEMENTED.** No key was generated, no encrypted
> database was created, no dependency was installed.

---

## 6. What each option would require (for the approver)

| Option | Must be decided before any implementation |
|---|---|
| **A** | (1) key custody: DPAPI / env / vault + who holds the recovery key; (2) authorize installing a SQLCipher build for Python 3.14/Windows; (3) authorize rewriting all `connect` sites + the URI read-only pattern; (4) authorize re-keying the 3 existing plaintext backups **or** formally accepting them as legacy plaintext; (5) define the export/restore drill **before** cutting over |
| **B** | (1) confirm the volume's current status (`manage-bde -status` / `fsutil fsinfo`) — **not yet evidenced**; (2) decide on the OneDrive path (move vs. encrypt-in-place); (3) recovery-key escrow |
| **C** | (1) which columns exactly; (2) approved crypto library; (3) backfill + row-version marker; (4) effect on any query that filters on encrypted text |
| **all** | rotate the hard-coded demo admin credential first; set `secure_delete=1`; resolve **retention (B11)** — encryption does **not** satisfy P2.12 |

---

## 7. Explicit status statements (acceptance criteria)

| Item | Status |
|---|---|
| `aura.db` is encrypted | ❌ **NO — plaintext. Not described as encrypted anywhere in this phase** |
| SQLCipher available | ❌ **NO — verified absent** |
| Encryption enabled / migration run | ❌ **NO — explicitly not authorized and not performed** |
| Production DB modified | ❌ **NO** |
| Production key generated | ❌ **NO — none exists, none created** |
| Dependency installed | ❌ **NO** |
| Option recommendation | ✅ **PROPOSED — layered A (+B interim, C conditional)** |
| Prototype | ❌ **NOT IMPLEMENTED — dependency + policy approvals missing** |
| Requires approval | ✅ **ALL of §6** |
