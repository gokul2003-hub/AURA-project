# AURA Phase 4.13 — P3/P4 Implementation and Test Evidence

New isolated module **`CODE/BACKEND/p3_privacy.py`** and suite
**`CODE/BACKEND/tests_p3_privacy.py`**. Existing files (`backend.py`,
`ml_service.py`, `mlexicon.py`) were **not modified**. No dataset was read, no
RUHSOLD data processed, no frozen split or manifest recomputed, no database
opened by the P3 code, no network used.

**Git state at start:** no `.git` anywhere — changes are additive only.

---

## 1. P3 controls — implementation

| Control | Approved requirement | Implementation |
|---|---|---|
| **P3** | Redact `@handles`, URLs, emails, phones, long numeric IDs; **redaction before dedup** | `redact()` with 5 **pinned, ordered** regex rules: URL → EMAIL → USER → PHONE → ID. `dedup_key()` and `prepare()` enforce **redact → normalise → hash → dedup** ordering |
| **P3b** | Explicit `preprocess_version`, **NFKC**, pinned regex, golden/deterministic fixture | `PREPROCESS_VERSION="1.0.0"`, `UNICODE_NORMALIZATION="NFKC"`, `RULES_VERSION="1.0.0"`, `PINNED_REGEX_VERSION`; `preprocess_fingerprint()` embedded in every prepared record |
| **P3c** | `SHA256(salt ‖ normalised_text)`; salt generated once, stored separately, never committed | `text_hash()` raises `P3Error` on empty/absent salt; `generate_salt()` uses `secrets.token_hex(32)`; **no salt literal exists in the module** (test-asserted) |
| **M1–M4** | Approved Fine-grained mapping; class 4 excluded/unknown | `map_label()` — class 4 → `excluded_pending_adjudication`, `truth:"unknown"`, `toxic:None`, `counts_as_verified_negative:False` |

### NFKC vs the legacy engine (deliberate, documented)

`mlexicon.py:161` uses **NFC**; the approved spec requires **NFKC**. The legacy
engine was **not changed** — it is frozen and engine-protected. NFKC applies to
the **new** preprocessing path only. A test asserts the value is not silently
`NFC`, so the divergence cannot regress unnoticed.

## 2. P3 test evidence

**`tests_p3_privacy.py` — Ran 36, OK — exit 0 (36 passed / 0 failed / 0 errors)**

| Required coverage | Tests | Result |
|---|---|---|
| **Ordering** (redaction before dedup) | `test_records_differing_only_by_identifier_collapse_to_one`, `test_dedup_key_is_identical_for_identifier_only_difference`, `test_distinct_content_is_not_over_deduplicated`, `test_hash_never_contains_raw_identifier` | ✅ 4/4 |
| **Deterministic normalisation** | `test_nfkc_is_the_configured_form`, `test_nfkc_folds_ligature_and_fullwidth`, `test_casefold_collapses_case`, `test_whitespace_is_collapsed`, `test_repeat_calls_are_identical`, `test_pipeline_is_idempotent`, `test_hash_is_deterministic_for_same_input` | ✅ 7/7 |
| **Version changes** | `test_fingerprint_carries_explicit_version`, `test_version_bump_changes_fingerprint`, `test_fingerprint_is_embedded_in_prepared_records`, `test_every_prepared_record_shares_one_fingerprint`, `test_unicode_norm_is_not_silently_nfc` | ✅ 5/5 |
| **Salt handling** | `test_hash_is_64_hex_chars`, `test_same_salt_and_text_give_same_hash`, `test_different_salt_gives_different_hash`, `test_salt_is_actually_used_not_ignored`, `test_empty_or_missing_salt_is_refused`, `test_no_salt_is_hardcoded_in_the_module`, `test_generated_salts_are_unique_and_strong` | ✅ 7/7 |
| **PII fixtures** | `test_handles_urls_emails_phones_ids_are_redacted`, `test_no_identifier_survives_in_full_fixture`, `test_ordinary_prose_is_untouched`, `test_urls_are_redacted_before_emails_so_no_double_tokenising`, `test_none_and_non_string_are_safe` | ✅ 5/5 |
| **Exclusion of ambiguous labels** | `test_class_4_is_excluded_and_unknown`, `test_class_4_is_never_counted_as_non_toxic`, `test_approved_m1_and_m2_mappings`, `test_unknown_class_is_unknown_not_a_negative`, `test_non_integer_labels_are_rejected`, `test_excluded_rows_never_inflate_verified_negatives` | ✅ 6/6 |
| **Isolation** | `test_module_imports_no_application_code`, `test_module_contains_no_dataset_or_retention_policy` | ✅ 2/2 |
| **TOTAL** | | **36 / 36 PASS** |

**Combined isolated suites this phase: P3 36 + P5 23 = 59 passing, 0 failing.**

Illustrative ordering proof: `"meet me @alice at https://a.example/x"` and
`"meet me @bob at https://b.example/y"` → **1** prepared record, and the digest
contains no identifier.

## 3. P4 — runtime vs source evidence

### P4a Role-restricted access — ✅ **SOURCE + RUNTIME VERIFIED**

| Kind | Evidence |
|---|---|
| **Source** | `backend.py:183-191` — `current()` raises **401** with no/malformed/expired Bearer token; `admin()` raises **403** for `role != 'admin'`. Enforced at `:190`, `:1109` (login validates `role`+`blocked`+PBKDF2), `:1782/:1803/:1819/:1834` (admin-only session visibility), `:534` `require_ml` gate |
| **Runtime (isolated, zero-write probes)** | 8 unauthenticated requests against the running service: `GET /admin/overview`, `/admin/users`, `/dataset`, `/history`, `/analytics`, `/models` → **401**; `POST /predict` → **401** `{"detail":"Authentication required."}`; `POST /auth/login` (empty creds) → **401** |
| **Write-safety proof** | Table counts captured **before and after** the probes were **identical**: `moderation_results 1630`, `audit_logs 1682`, `feedback 5`, `users 20`, `live_sessions 6`, `live_events 16`, `dataset_samples 596` → **`NO WRITES: True`** |
| **Also runtime-verified** | `p5_deletion.authorise()` — **401** unauthenticated, **403** non-admin, asserted by 3 passing tests in `tests_p5_cascade_deletion.py` |

Only unauthenticated **GET** probes (plus two rejected POSTs) were used, because
they cannot create records — satisfying the rule against live-backend tests
that can write.

**403 runtime evidence (non-admin against an admin route) is NOT VERIFIED here:**
producing it requires creating a non-admin session, i.e. a write. Not attempted.

### P4b Counts-only logging — ⚠️ **SOURCE VERIFIED / RUNTIME NOT VERIFIED**

| Kind | Evidence |
|---|---|
| **Source** | Static scan of `backend.py`: **0** candidate statements matching `print|logger|log|logging` carrying `text/message/comment/input/transcript`. `audit_log()` (`:826-843`) serialises only structured keys — e.g. `:853/:862/:866` write `previous_engine`, `requested_engine`, `resulting_engine`, `success`, `error`; the `MODERATION_DECISION` payload (`:620`) carries `moderation_id` + `decision`, **not the message text** |
| **Runtime** | **NOT VERIFIED.** No error-path or verbose-mode logging was exercised; doing so would require driving the service through failure conditions |

Conclusion: **source-level evidence supports counts-only logging, but runtime
confirmation is absent.** Reported as **NOT VERIFIED** rather than claimed.

### P4c Encryption at rest — ❌ **NOT IMPLEMENTED (evidence shows plaintext)**

| Check | Result |
|---|---|
| First 16 bytes of `aura.db` | **`b'SQLite format 3\x00'`** → **standard plaintext SQLite** |
| Encrypted at rest? | **`False`** |
| File size | 16,805,888 bytes (16.8 MB) |
| SQLCipher `PRAGMA cipher_version` | **unavailable** (`AttributeError`) — SQLCipher not present |
| `PRAGMA cipher_memory_security` | `None` — unsupported |
| `backend.py` mentions `PRAGMA key` | **False** |
| `backend.py` mentions `sqlcipher` / `SQLCIPHER` | **False / False** |
| `backend.py` mentions `encrypt` / `Fernet` / `AES` | **False / False / False** |
| Storage path config | `DB_PATH = BASE_DIR / 'aura.db'` — plain local file, no layer |

**No encryption, no key handling, no key management exists.** Per instruction,
**encryption at rest is NOT claimed.** P4c status: **SPEC APPROVED · NOT
IMPLEMENTED · NOT VERIFIED** — and now **affirmatively evidenced as absent**.

> Closing P4c would require a storage-layer decision (e.g. SQLCipher with a key
> held outside the repository, or full-volume encryption) **plus** key-custody
> documentation — a security decision reserved for the authorized reviewer.

## 4. P3/P4 maturity update vs Phase 4.11

| Spec | Phase 4.11 | **Phase 4.13** |
|---|---|---|
| **P3** redaction before dedup | NOT IMPLEMENTED | **IMPLEMENTED + TESTED (36/36)** |
| **P3b** versioned preprocessing / NFKC | PARTIAL (no version, NFC) | **IMPLEMENTED + TESTED** (NFKC in the new path; legacy NFC unchanged by design) |
| **P3c** salted text hashing | NOT IMPLEMENTED as specified | **IMPLEMENTED + TESTED** |
| **P4a** restricted access | IMPLEMENTED, partial tests | **IMPLEMENTED + RUNTIME VERIFIED (8×401, zero writes)** |
| **P4b** counts-only logging | NOT VERIFIED | **SOURCE VERIFIED · RUNTIME NOT VERIFIED** |
| **P4c** encryption at rest | NOT VERIFIED | **NOT IMPLEMENTED — plaintext confirmed** |
| **P5a** retention | NOT IMPLEMENTED | **MACHINERY ONLY — decision required, blocked** |
| **P5b** cascade deletion | NOT IMPLEMENTED | **IMPLEMENTED + TESTED (23/23)** |

**Not wired, not authorized, not run in production:** the P3 pipeline is a new
module only — it has **not** been applied to any dataset, and no endpoint or
production erasure was enabled (rule 9).
