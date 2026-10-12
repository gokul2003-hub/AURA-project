# AURA Phase 4.13 — Incident Review (Phase 4.12 production write)

**Attribution: VERIFIED (conclusive).**
**No record was deleted or altered. The audit trail is untouched.**

---

## 1. The reported anomaly

| Table | Before (Phase 4.11 baseline) | After | Delta | Timestamp |
|---|---|---|---|---|
| `moderation_results` | 1,629 | **1,630** | **+1** | `2026-10-11T14:52:39.559639+00:00` |
| `audit_logs` | 1,681 | **1,682** | **+1** (`id=1682`) | same event |

`14:52:39Z` = **20:22:39 local (UTC+05:30)**, matching the `aura.db` mtime.

## 2. Evidence gathered (read-only queries only)

### Row identity — the smoking gun

```
moderation_results id=1630
  user_id    = 'admin'
  message    = 'you are stupid and I hate you'
  source     = 'text'      language = en / English / existing_model
  created_at = 2026-10-11T14:52:39.559639+00:00
  overall    = non_toxic   confidence = 0.93
```

| Assertion | Result |
|---|---|
| message == payload at `tests_threshold_immutability.py:186` | **`True`** (byte-identical) |
| user_id == test default `AURA_TEST_USER` = `'admin'` (line 181) | **`True`** |

### Neighbour rows corroborate the pattern

| id | user | message | created_at (UTC) |
|---|---|---|---|
| 1627 | admin | `idiot` | 05:44:46 |
| 1628 | admin | `nee vera level mudhalai, unnai verukkire` | 05:44:46 |
| **1629** | admin | **`you are stupid and I hate you`** | 09:01:54 |
| **1630** | admin | **`you are stupid and I hate you`** | **14:52:39** |

Row **1629 carries the identical payload** from an earlier run — so **this is a
pre-existing defect in the test, not something introduced in Phase 4.12.** The
Phase 4.12 run was simply the first time the write was noticed.

## 3. Attribution

| Element | Identification |
|---|---|
| **Test responsible** | `tests_threshold_immutability.py` — **regression suite 1 of Phase 4.12** |
| **Exact line** | **`:186`** → `http('POST', '/predict', {'text': 'you are stupid and I hate you'}, token=tok)` |
| **Request** | `POST /predict` body `{"text":"you are stupid and I hate you"}` with a Bearer token from `:181` (`POST /auth/login`, default user `admin`) |
| **Route** | `/predict` (`backend.py:1239`) → `run_engine()` → **`backend.py:1076` `store_moderation(...)`** → `:617` `INSERT INTO moderation_results` then `:620` `INSERT INTO audit_logs (action='MODERATION_DECISION', details={'moderation_id':1630,'decision':…})` |
| **Process** | `python.exe` uvicorn backend listening on **`http://127.0.0.1:8010`**, PID started **10:53:08** (a live service, not started by this phase) |
| **Timing fit** | P5 test bytecode compiled **20:22:34**, ran ~3.3 s → regression 1 began ≈ **20:22:38**, `POST /predict` at **20:22:39**. Consistent. |

The audit payload shape `{"moderation_id":…,"decision":…}` matches
`backend.py:620` exactly, confirming `store_moderation()` as the writer of
**both** records in a single `c.commit()` (line 621) — which is why both counts
advanced together.

## 4. Correction to the Phase 4.12 report

`PHASE412_IMPLEMENTATION_SUMMARY.md §6` attributed the write to
*"regression 2+3"* (`tests_audit_threshold_phase41.py` /
`tests_dataset_import_phase4.py`). **That was incorrect.** The evidence above
shows it was **regression 1, `tests_threshold_immutability.py`**.

This correction is recorded rather than silently edited, so the original
statement remains auditable.

## 5. Root cause

**A legacy test suite issues live HTTP calls to whatever is listening on
`127.0.0.1:8010`.** When the production backend is running, those calls are
real production writes. The test has no isolation guard and no `--dry-run`.

Contributing factors:
1. The backend was already running from an earlier session.
2. `tests_threshold_immutability.py` hardcodes `BASE = 'http://127.0.0.1:8010'` (`:152`).
3. `/predict` persists every request (`store_moderation`).
4. Phase 4.12 ran the suite as a "read-only regression" assuming it only read hashes.

**`p5_deletion` is excluded as a cause:** it refuses `aura.db` unless
`allow_production=True`, its tests use temp DBs, and **`DATA_ERASURE` rows in
production = 0**.

## 6. Disposition — no action taken on the records

| Option | Decision |
|---|---|
| Delete `moderation_results` 1630 | **NOT DONE** — would be a further unauthorized production write and would falsify history |
| Delete `audit_logs` 1682 | **NOT DONE** — erasing audit evidence is explicitly prohibited |
| Restore an old database snapshot | **NOT DONE** — prohibited by Phase 4.13 rule E |
| **Record the finding and the root cause** | **DONE — this document** |

The two rows are **expected, explained changes** — not corruption. They are
retained as evidence of the incident.

## 7. Preventive controls (recommended, not applied to production code)

| # | Control | Status |
|---|---|---|
| 1 | Run live-HTTP suites only against an **isolated backend on a different port**, or stop the production service first | **recommended — not applied** (would require editing `tests_threshold_immutability.py`, an existing file) |
| 2 | Make `BASE` overridable via env var and default to a non-production port | **recommended** |
| 3 | Add a guard: refuse `/predict` writes when `AURA_ALLOW_LIVE_WRITES` is unset | **recommended — would modify production `backend.py`; needs authorization** |
| 4 | Phase 4.13 rule 5 already applied: **no live-backend regression suites were run in this phase** | **applied** |

## 8. Verdict

- **Source: VERIFIED** — `tests_threshold_immutability.py:186` via `POST /predict`
  on the live backend, writing through `store_moderation()` (`backend.py:617,620`).
- **Impact: 2 rows** (`moderation_results` +1, `audit_logs` +1).
- **Production invariants: unaffected** — `dataset_samples` 596, splits
  137/29/31+399, `training_runs` 8, `model_versions` 12, `improved_v10`,
  engine `legacy`, protected hashes and frozen splits unchanged.
- **No records deleted, no audit trail altered.**
