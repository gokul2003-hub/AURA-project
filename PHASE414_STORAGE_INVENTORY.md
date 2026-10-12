# AURA Phase 4.14 — Stage 1: Sensitive-Storage Inventory (read-only)

**Read-only assessment. No file was created, modified, moved or deleted.**
Workspace state recorded first: **no `.git`** at root or under `comment
toxicity` (unchanged from Phases 4.12/4.13) — therefore every file is
uncommitted user work and all changes must be **additive only**.

Environment: Windows 11 · Python **3.14.3** · libsqlite **3.50.4** ·
`sqlite3` stdlib at `C:\Python314\Lib\sqlite3`.

---

## 1. Persistence locations

### 1a. Primary database

| Path | Size | Notes |
|---|---|---|
| `CODE/BACKEND/aura.db` | **16,805,888 B (16.8 MB)** | the only live database |

**Live configuration (read via `PRAGMA`, read-only connection):**

| PRAGMA | Value | Significance |
|---|---|---|
| `journal_mode` | **`delete`** | rollback-journal mode, **not WAL**. A transient `aura.db-journal` exists only during a write and is removed on commit — **no persistent `.db-wal`/`.db-shm`** (confirmed: none present) |
| `synchronous` | `2` (FULL) | durable, not a security setting |
| `page_size` | `4096` | — |
| `secure_delete` | **`0` (OFF)** | ⚠️ **freed pages are not overwritten** — deleted rows can survive in free pages until reused |
| `temp_store` | **`0` (default = FILE)** | ⚠️ **large sorts/spills write to disk unencrypted** |
| `auto_vacuum` | `0` | no reclamation; free pages retained |

**Contains (personal data):** `moderation_results.message` (1,630),
`feedback.input_text` (5), `live_events.transcript` (16), `users` (20) incl.
`password_hash`+`salt`, `audit_logs` (1,682).

### 1b. Backups — **plaintext copies**

`data/backups/` — **3 files, 22.3 MB total**, produced by
`import_external_datasets.py:218 backup_db()` using
`sqlite3.Connection.backup()`:

| File | Size | Date |
|---|---|---|
| `aura-phase41-baseline-20261011-101947.db` | 11,046,912 B | 2026-10-11 10:19 |
| `aura-pre-external-import-20261009-223341.db` | 6,152,192 B | 2026-10-09 22:33 |
| `aura-pre-external-import-20261009-223359.db` | 6,152,192 B | 2026-10-09 22:33 |

⚠️ These are **full plaintext duplicates of the personal data**, sitting outside
the live file. Encrypting `aura.db` alone would **leave 22 MB of unencrypted
PII in place** — a migration must address them explicitly.

### 1c. Derived / processed artifacts

| Path | Files | Size | Risk |
|---|---|---|---|
| `data/processed/` | 14 | 0.4 MB | derived analytics; may embed comment text |
| `data/external/` | 6 | 0.2 MB | external dataset rows |
| `data/external/splits/` | 3 | 0.2 MB | split CSVs (train/val/test) |
| `data/raw`, `train`, `validation`, `test` | 1 each | ~0 | split CSVs |
| `data/phase2_eval/` | 13 | 1.4 MB | **frozen** `ur_test`/`ur_val` + evaluation sets |

### 1d. Logs & temp

| Path | Size | Notes |
|---|---|---|
| `models/benchmark_run2.log` | 2,324 B | **the only log file in the tree** (no application logging to file; `backend.py` has no `logging`/`loguru` config) |
| WAL/SHM/journal sidecars | **none present** | — |
| SQLite `temp_store` spill | n/a | may write **unencrypted** temp files during heavy queries (§1a) |

---

## 2. Permissions, backups, secrets, startup

### 2a. Filesystem permissions (`aura.db` ACL)

```
Owner : GOKUL\gokul
NT AUTHORITY\SYSTEM   : FullControl (Allow)
BUILTIN\Administrators: FullControl (Allow)
Gokul\gokul           : FullControl (Allow)
```

**Only inherited NTFS ACLs — no encryption of any kind.** Any process running as
the user or as Administrators/SYSTEM reads the file in plaintext.

### 2b. Backup practice

- Created by `backup_db()` (`import_external_datasets.py:218-237`),
  "best-effort, never fatal" — **failures only print a warning**.
- Mechanism: `src.backup(dst)` → **byte-for-byte plaintext copy**.
- Compared byte-for-byte by `tests_dataset_import.py:286-311`.
- **No encrypted-backup mechanism exists.**

### 2c. Secret management — **none**

| Mechanism | Status |
|---|---|
| External secret store / vault / DPAPI | **absent** |
| `.env` / committed config secrets | **absent** |
| Environment variables read by app | only `AURA_PREDICTION_ENGINE`, `AURA_MODEL_*` — **non-secret** |
| Password storage | `pbkdf2_hmac('sha256', …, 150000)` + per-user salt (`backend.py:162`) — **sound** |
| Session tokens | in-memory `SESSIONS` map, `sha256(user:role:token_hex(16))` (`:182`) — not persisted |
| ⚠️ **Hard-coded demo admin credential** | **present in `backend.py:168,172`** (and as the default in 5 test files). Value deliberately **not reproduced in this report**. It is a **credential in source**, and `init_db()` **re-seeds it on every startup** (`:172`). |

**There is no key-management mechanism to hang an encryption key on.** This is
the single largest gap for any at-rest encryption option.

### 2d. Startup dependencies

`init_db()` (`backend.py:164-173`) runs `CREATE TABLE IF NOT EXISTS` +
`PRAGMA table_info` additive-column checks (`:175, :615, :1145, :1282`).
**No versioned migration framework, no schema-version table.** `DB_PATH` is
resolved at import (`:11`) as `BASE_DIR / 'aura.db'` — no env override.

---

## 3. Is an encrypted-storage mechanism available? (**Do not assume — probed**)

| Probe | Result |
|---|---|
| `importlib.util.find_spec('pysqlcipher3')` | **absent** |
| `find_spec('sqlcipher3')` / `sqlcipher3_bytes` | **absent** / **absent** |
| `find_spec('apsw')` | **absent** |
| `find_spec('cryptography')` | **absent** |
| `find_spec('Crypto')` (pycryptodome) | **absent** |
| `find_spec('pysqlite3')` | **absent** |
| `pip list` → sqlcipher/cryptography/pycryptodome/apsw | **none installed** |
| `sqlite3.connect(db, cipher=…)` | **`TypeError: unexpected keyword argument 'cipher'`** |
| `sqlite3.connect(db, key=…)` / `kdf_iter=…` | **`TypeError`** both |
| `PRAGMA cipher_version` | **`[]`** (empty) |
| `PRAGMA cipher` / `kdf_iter` / `cipher_integrity_check` | **`[]`** all |
| `PRAGMA compile_options` containing `CIPHER` | **NONE** — 43 options, stock SQLite, **not SQLCipher-patched** |
| `sqlcipher[.exe]` on PATH | **absent** |
| `openssl[.exe]` on PATH | **absent** |

### ⚠️ Critical trap — `PRAGMA key` is a false positive

```
PRAGMA key = '…'   ->   ACCEPTED (no error)
```

**Stock SQLite silently ignores unknown PRAGMAs.** `PRAGMA key` returning
successfully **does not mean the database is encrypted**. Any implementation or
test that treats "no error from `PRAGMA key`" as proof of encryption would be
**wrong**. The only valid checks are: `PRAGMA cipher_version` returns a **non-empty**
version string, *and* a fresh connection without the key fails to read the file.

**Conclusion: SQLCipher is NOT installed and NOT available in this environment.**

---

## 4. Connection, migration, concurrency, backup/restore map

| Concern | Current behaviour | Location |
|---|---|---|
| **Connection creation** | `sqlite3.connect(DB_PATH)`, `row_factory=Row`, **no PRAGMAs, no key**; a new connection per call, closed by callers | `backend.py:159-160` |
| **Read-only access** | `sqlite3.connect(f"file:…?mode=ro", uri=True, …)` — **URI mode used in ≥6 places** | `tests_dataset_import.py:101,240`, `tests_model_adapter.py:171,618`, `p5_deletion.py` (read-only probes), Phase 4.11–4.14 verification scripts |
| **Migrations** | none — `CREATE TABLE IF NOT EXISTS` + ad-hoc `PRAGMA table_info` column adds | `backend.py:164-173`, `:175/:615/:1145/:1282` |
| **Concurrency** | default; `check_same_thread` default; `timeout=30` only in `p5_deletion.py:127` | — |
| **Backup** | `Connection.backup()` → **plaintext** file, best-effort | `import_external_datasets.py:218-237` |
| **Restore** | **no restore procedure exists** | — |
| **Recovery** | `integrity_check` used in verification scripts; no automated recovery | — |
| **Test isolation** | good: `tests_audit_threshold_phase41.py:175-192` repoints `backend.DB_PATH` to a temp file; `tests_dataset_import_phase4.py:169` **refuses** to target live `aura.db` | — |

---

## 5. Database encryption vs filesystem encryption vs encrypted backups

**These are three different controls. Conflating them would misstate the posture.**

| Control | Protects | Does NOT protect | Current state |
|---|---|---|---|
| **A. Database-level encryption (SQLCipher)** | the `.db` bytes, WAL/SHM/journal, temp spill, and the file if exfiltrated | data **in use** in RAM; the process itself | ❌ **absent — `aura.db` is plaintext** |
| **B. Filesystem/volume encryption (BitLocker/EFS/DPAPI)** | files at rest on that volume against offline/lost-device theft | anything readable by a process while the volume is mounted; copies taken elsewhere | ❌ **not evidenced** (ACL only; no evidence of BitLocker on this volume) |
| **C. Encrypted backups** | the 3 backup copies in `data/backups/` | the live file | ❌ **absent — backups are plaintext** |
| **D. Application-level field encryption** | selected columns even if the file leaks | table names, row counts, non-encrypted columns | ❌ **absent** |

> **Explicit statement required by the brief: `aura.db` is PLAINTEXT SQLite. It is
> NOT encrypted at rest, and no compensating control has been evidenced.**
> Phase 4.13 confirmed this from the file magic (`SQLite format 3\0`); Stage 1
> confirms no SQLCipher, no key handling and no volume-encryption evidence.

---

## 6. Compatibility risks if SQLCipher were adopted

| # | Risk | Evidence |
|---|---|---|
| **C1** | **No Python binding available**; `sqlcipher3` on **Python 3.14/Windows** likely needs a toolchain or a wheel that may not exist for 3.14 | §3 probes |
| **C2** | **Every `sqlite3.connect` must become a keyed connection.** `db()` is centralised (`backend.py:160`), but tests/scripts open raw connections independently | §4 |
| **C3** | **URI read-only mode (`file:…?mode=ro`) is used pervasively** and is a known friction point with SQLCipher keying; ~6 call sites would need rework or removal | `tests_dataset_import.py:101,240`, `tests_model_adapter.py:171,618` |
| **C4** | **Keys are per-connection, not per-file** — forgetting the key on any one connection yields a corrupt-file error at runtime | SQLCipher semantics |
| **C5** | **Existing `Connection.backup()` produces plaintext** unless both source and destination are keyed; `tests_dataset_import.py:286-311` asserts byte-for-byte backup equality and would need redefinition | §2b |
| **C6** | **The 3 existing plaintext backups would remain plaintext** after migrating only the live DB | §1b |
| **C7** | **False-positive trap**: `PRAGMA key` succeeds on stock SQLite → a migration test could "pass" while nothing is encrypted | §3 |
| **C8** | **No schema-version table** → no safe point to gate a migration | §2d |
| **C9** | **`secure_delete=0`** → erasure is not secure wipe regardless of encryption | §1a |
| **C10** | **`temp_store=0` (file)** → spill files unencrypted unless filesystem-level control is also applied | §1a |
| **C11** | **In-process plaintext**: decryption happens on read, so a memory dump or core file exposes keys/data | §5 |
| **C12** | **No secret store exists** to hold the key (§2c) — key would have to be introduced from scratch | §2c |

**Prototype feasibility (Stage 3):** SQLCipher-based prototype → **NOT FEASIBLE**
here (dependency absent, and installing one would alter the environment).
See `PHASE414_ENCRYPTION_OPTIONS.md` for the option that *is* prototypable safely.
