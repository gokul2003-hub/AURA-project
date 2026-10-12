# AURA Phase 4.15 — Storage & Backup Plan (B13, B14, B15)

**PROPOSAL ONLY. No file was moved, copied, deleted, renamed or re-permissioned.
No dependency installed. No key generated. No migration run.**

---

## 1. Verified facts (Stage 1, read-only)

### 1a. Cloud-sync exposure (B15) — **CONFIRMED**

| Check | Result |
|---|---|
| `env:OneDrive` | `C:\Users\gokul\OneDrive` |
| Project path under `\OneDrive\` | **`True`** (`C:\Users\gokul\OneDrive\Desktop\zip project\…`) |
| OneDrive process running | **`True`** |
| Sync accounts configured | **`Accounts\Personal` and `Accounts\Business1` both present** |
| `aura.db` attributes | **`Archive`** |
| ReparsePoint / Offline placeholder | **`0` / `0`** |

**Interpretation:** `aura.db` is **not** an on-demand placeholder — it is a
**fully materialised local file inside the sync root**, i.e. it is in scope for
upload. Combined with the running sync client and two configured accounts, the
database and its backups are **subject to replication**.

> **Precise claim (and its limit):** *the files are inside an active OneDrive
> sync root.* Whether bytes have actually reached the cloud, and to which
> tenant, **cannot be determined from this machine** and is reported as
> **NOT VERIFIABLE**. The control gap is real regardless: the path is in scope.

### 1b. Backups (B13) — **CONFIRMED plaintext**

| File | Size | Created |
|---|---|---|
| `aura-phase41-baseline-20261011-101947.db` | 11,046,912 B | 2026-10-11 10:19 |
| `aura-pre-external-import-20261009-223341.db` | 6,152,192 B | 2026-10-09 22:33 |
| `aura-pre-external-import-20261009-223359.db` | 6,152,192 B | 2026-10-09 22:33 |
| **Total** | **22.3 MB** | — |

- Produced by `import_external_datasets.py:218-237 backup_db()` via
  `sqlite3.Connection.backup()` → **byte-identical plaintext copies**.
- "Best-effort, never fatal" — **failures only print a warning**.
- Located in `data/backups/` → **also inside the OneDrive sync root** (§1a).
- **22.3 MB of unencrypted personal data — 1.3× the live DB's size.**
- **No restore procedure exists anywhere in the codebase.**

### 1c. Permissions & key custody (B14) — **CONFIRMED absent**

- `aura.db` ACL: owner `GOKUL\gokul`; SYSTEM / Administrators / gokul =
  FullControl. **Inherited NTFS ACL only.**
- **No secret store of any kind:** no vault, no DPAPI usage, no `.env`, no key
  file, no environment-held secret. The app reads only `AURA_PREDICTION_ENGINE`
  and `AURA_MODEL_*` (non-secret).
- **Consequence:** there is currently **nowhere approved to put an encryption
  key**. B14 is a hard prerequisite for SQLCipher (Option A) and for field
  encryption (Option C) alike.

### 1d. Distinguishing confirmed from unverifiable

| Confirmed | Unverifiable |
|---|---|
| Files are inside an active sync root | Whether/where they were actually uploaded |
| Backups are plaintext and free-standing | Whether any copy left this machine |
| No restore procedure | Prior backup integrity (only spot-checked) |
| No secret/key store exists | Any historical key custody (none) |
| ACL is inherited-only | Whether another principal ever read the files |

---

## 2. Plan S1 — Relocation out of cloud sync (addresses B15)

**No relocation performed. Requires authorization.**

| Step | Action | Notes |
|---|---|---|
| S1.0 | **Decide the destination** — a non-synced, non-removable location (e.g. a dedicated local volume or an excluded folder) | 🔴 **decision required** |
| S1.1 | Add the destination to **OneDrive sync exclusions** *before* moving anything | avoids re-upload |
| S1.2 | **Stop the service** | no open handles |
| S1.3 | Take a **verified staging backup** (SHA256 recorded) | the rollback artifact |
| S1.4 | Move `aura.db` + `data/backups/` to the destination — **move, never delete** | |
| S1.5 | Repoint `DB_PATH` (`backend.py:11`) — currently hardcoded `BASE_DIR / 'aura.db'` with **no env override** | requires change authorization |
| S1.6 | Start service; verify engine `legacy`, integrity `ok`, 596 rows, splits, 8 runs, 12 versions, `improved_v10`, protected hashes, frozen splits | |
| S1.7 | **Confirm sync no longer covers the destination** | |

**Preconditions:** S1 decision · change authorization for `backend.py:11` ·
**credential plan C0.1/C0.2** (see credential plan) · retention decision B11.
**Rollback triggers:** service cannot open the DB · any invariant drift ·
destination unexpectedly under sync.

### 2b. Compensating control if relocation is declined
Exclude the specific paths from sync, and/or apply volume-level encryption.
⚠️ **Volume encryption does NOT protect a file OneDrive uploads** (sync transfers
file bytes, not an unlocked volume) — so exclusion, not BitLocker, is the
effective mitigation for B15.

---

## 3. Plan S2 — Protected backups, restore rehearsal, retirement (addresses B13)

### S2.0 — Create a protected-backup capability
| Step | Action |
|---|---|
| 1 | Write backups to the **relocated, non-synced** destination (S1), never under `OneDrive` |
| 2 | Make backup **fail-loud, not best-effort** — today `backup_db()` swallows errors (`:236-237`) |
| 3 | Record **SHA256 + row counts + integrity result** per backup; verify on write |
| 4 | Under SQLCipher (S3), key **both** sides of `Connection.backup()`; update the byte-equality assertion at `tests_dataset_import.py:286-311`, which currently **requires plaintext-identical backups** |
| 5 | Do **not** encrypt the frozen `ur_*.csv` or protected model artifacts — they are hashed manifests and must stay byte-stable |

### S2.1 — Restore rehearsal (currently **no restore procedure exists**)
Rehearse **on a copy, in an isolated temp directory**, never on production:

| ID | Test | Pass criterion |
|---|---|---|
| **T-S1** | Restore backup → open | `integrity_check` = `ok` |
| **T-S2** | Row counts + splits match manifest | 596; 137/29/31+399 |
| **T-S3** | Engine/model state match | `legacy`; 8 runs; 12 versions; `improved_v10` |
| **T-S4** | Protected hashes + frozen splits match | all unchanged |
| **T-S5** | Service starts against restored copy | health OK |
| **T-S6** | Under encryption: restore with **wrong key** fails cleanly, **no plaintext produced** | hard failure |

### S2.2 — Retirement of the 3 legacy plaintext copies
🔴 **Do not delete.** They are (a) the only pre-migration rollback artifacts and
(b) audit evidence. Sequence:
1. Confirm a **verified successor backup** exists (T-S1…T-S5 pass).
2. Obtain **written retirement authorization** naming each file.
3. Record each file's SHA256 in the retirement record **before** removal.
4. Remove; confirm removal; record actor, time, justification.

> **Retention duration: NOT INVENTED.** Retention of backups is governed by the
> unanswered **retention decision (B11, D1–D9)** in
> `PHASE413_RETENTION_DECISION_REQUIRED.md`. No period is proposed here.

---

## 4. Plan S3 — SQLCipher, key custody, migration & rollback (addresses B14)

Phase 4.14 already established: **SQLCipher is absent** (12 probes) and
`PRAGMA key` is a **false-positive trap** on stock SQLite. This plan sequences
the *prerequisites*, and defers mechanics to
`PHASE414_MIGRATION_AND_ROLLBACK_PLAN.md`.

### S3.0 — Key custody (B14) — 🔴 **BLOCKED, decision required**
**No key-management policy is invented here.** The approver must specify:

| Question | Why it cannot be defaulted |
|---|---|
| Where does the key live? (DPAPI / environment / vault / OS keyring) | nothing exists today |
| Who is the custodian, and who is the deputy? | single-custodian loss = total data loss |
| What is the recovery procedure if the custodian is unavailable? | **no key ⇒ permanent data loss**; rehearsal is mandatory |
| How is the key provisioned to a cold start (service boot)? | the app currently has no secret channel |
| Is the key rotated, and on what trigger? | **duration NOT invented** |

### S3.1 — Install (after authorization)
Obtain a SQLCipher build for **Python 3.14 / Windows**. Verify by
**`PRAGMA cipher_version` returning non-empty** *and* a keyless connection
failing to read a test file. **A successful `PRAGMA key` is NOT proof.**

### S3.2 — Migrate
Execute `PHASE414_MIGRATION_AND_ROLLBACK_PLAN.md` M0–M5: rehearse on a copy →
staging backup → encrypt → cut over (key `db()` at `backend.py:160`, rework the
~6 `file:…?mode=ro` URI sites) → keyed backups → hygiene.

### S3.3 — Rollback
RB1–RB7 from the Phase 4.14 plan: **move** (never delete) the encrypted file →
restore the SHA256-verified plaintext backup → revert code → verify invariants →
**record the rollback**.

**Honest limits:** rollback restores availability but **returns to
plaintext**; rows written after the staging backup are lost from the live file
but retained in the moved encrypted file; the 3 legacy plaintext copies are
unaffected in either direction.

---

## 5. Ordering — why this sequence

```
B11 retention ─┐
C0.1 auth-change authorization ─┬─► S1 relocate ─► S2 protected backups + restore rehearsal ─► S3 key custody ─► SQLCipher migrate
C0.2 credential source ─────────┘                                                                 │
                                                                                                  └─► retire legacy plaintext (last)
```

1. **S1 before S2** — creating backups *inside* the sync root would multiply
   the exposure it is meant to fix.
2. **S2 before retiring anything** — never remove the only rollback artifact.
3. **S3 last** — migrating before relocation would encrypt a file that then has
   to be moved and re-keyed, doubling the risk.
4. **B17 (credential) alongside S1** — `init_db()`'s re-seed would otherwise
   reassert a known credential into whatever storage S1 selects.

---

## 6. Explicit status

| Item | Status |
|---|---|
| Files moved / deleted / renamed | ❌ **NO** |
| Backups created, altered or retired | ❌ **NO — all 3 intact, original timestamps** |
| Permissions changed | ❌ **NO** |
| Dependency installed | ❌ **NO** |
| Encryption key generated | ❌ **NO** |
| Migration executed | ❌ **NO** |
| Retention duration invented | ❌ **NO** |
| Key-management policy invented | ❌ **NO** |
| Exposure reduced | ❌ **NO — not claimed** |
| Plan specified | ✅ **S1 + S2 + S3 with ordering, triggers, tests, owners** |
| Requires approval | 🔴 **S1 destination, S2.2 retirement, S3.0 key custody, B11 retention** |
