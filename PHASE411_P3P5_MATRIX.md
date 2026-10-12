# AURA Phase 4.11 — P3–P5 Specification-to-Implementation Matrix

**Approved:** P3–P5 control *specifications* (per Phase 4.11 brief).
**Approval of a specification is NOT implementation.** This audit checks whether
the approved specs exist in code, and at what maturity.

**Four maturity levels used:**

| Level | Meaning |
|---|---|
| **SPEC APPROVED** | the requirement is written and signed off |
| **IMPLEMENTED** | code exists that performs it |
| **TESTED** | an automated test exercises it and passes |
| **NOT VERIFIED** | cannot be proven within this read-only pass |

---

## Matrix

| ID | Approved specification | Implementation found (file:line) | Tests | **Maturity** |
|---|---|---|---|---|
| **P3** | Redaction of `@handles`, URLs, emails, phones, long numeric IDs — **before** dedup, regex **+ human spot-check** | **No redaction code exists.** Only match in tree is an incidental `"redacted"` token inside `models/hf_cache/.../tokenizer.json` (model vocabulary, unrelated). No `[USER]`/`[URL]` substitution anywhere in `CODE/`. | none | **SPEC APPROVED · NOT IMPLEMENTED · NOT TESTED** |
| **P3b** | Versioned, reproducible preprocessing: `preprocess_version`, pinned regex, **NFKC**, golden fixture, V5–V7 re-derivation | **Partial only.** Normalisation exists: `fetch_external_datasets.py:116 normalize()`, `import_external_datasets.py:17,33,200` (whitespace+casefold), dedup at `ml_service.py:991`. **But:** no `preprocess_version` symbol exists anywhere; `mlexicon.py:161` uses **`NFC`, not `NFKC`**; regex set is not pinned by a version. | `tests_dataset_import_phase4.py:469,484` exercise `normalize()` **determinism**, but no golden fixture and no version assertion | **SPEC APPROVED · PARTIALLY IMPLEMENTED · PARTIALLY TESTED (no versioning, no NFKC)** |
| **P3c** | Salted text hashes `SHA256(salt‖normalised_text)` as dedup/overlap join key; salt held separately, never committed | **Not implemented as specified.** Salting exists **only for passwords**: `backend.py:161-163` PBKDF2 + `secrets.token_hex(16)` per user. Text identity uses `backend.py:513` `sha256(user_id‖conversation_id‖text)[:16]` — a **message-ID**, keyed by request context, **not a dedicated secret salt** and **not used for dedup**. Actual dedup (`ml_service.py:991`, `fetch_external_datasets.py:290`) compares **normalised text directly**, not hashed values. | none for text hashing | **SPEC APPROVED · NOT IMPLEMENTED (as specified) · NOT TESTED** |
| **P4a** | Role-restricted access, least privilege, logged | **IMPLEMENTED.** `backend.py:184` Bearer token required → **401**; `backend.py:190` non-admin → **403**; `backend.py:1109` login validates `role` + `blocked` + PBKDF2 password; `backend.py:182` session token `sha256(user:role:secrets.token_hex(16))`; `users.role`, `users.blocked`; `audit_logs` table (`backend.py:165`); admin-only session visibility at `:1782,:1803,:1819,:1834`; ML operations gated by `require_ml` (`backend.py:534`). | exercised indirectly by HTTP suites (401/403 paths) | **SPEC APPROVED · IMPLEMENTED · PARTIALLY TESTED (no dedicated authz suite)** |
| **P4b** | **Counts-only** reporting; raw text never in logs, traces, tickets, reports | **Statically supported, NOT VERIFIED at runtime.** Grep of `CODE/` application code found **no logger/print of raw input text**; prints found are in test scripts and import summaries only. Every Phase 4.6–4.11 report does contain **aggregate counts only**. However, whether `audit_logs.details` or exception traces ever carry raw text under error conditions was **not exercised** in this read-only pass. | none | **SPEC APPROVED · IMPLEMENTED (static evidence) · NOT VERIFIED (runtime)** |
| **P4c** | Encrypted storage at rest | Not evidenced — no DB/file encryption configuration located in `CODE/`. | none | **SPEC APPROVED · NOT VERIFIED** |
| **P5a** | Time-bounded retention with an **approved end date** | **No retention code.** Grep for `retention|purge|erasure` across `CODE/` returned **zero** application-code hits (only tokenizer vocabulary and an unrelated CSV). **No end date is defined anywhere.** | none | **SPEC APPROVED · NOT IMPLEMENTED · NOT TESTED** |
| **P5b** | **Cascade deletion** across splits, hash manifests, cached features, scratch copies, backups | **Not implemented.** The only deletion path is `backend.py:1466 delete_sample` — a **single-row** dataset delete. No cascade reaches `data/external/splits/`, manifests, `hf_cache/`, or backups. | none | **SPEC APPROVED · NOT IMPLEMENTED · NOT TESTED** |

---

## Summary

| Spec | Status |
|---|---|
| **SPEC APPROVED** | **8 / 8** (P3, P3b, P3c, P4a, P4b, P4c, P5a, P5b) |
| **IMPLEMENTED** (fully) | **2 / 8** — P4a, and P4b on static evidence only |
| **PARTIALLY IMPLEMENTED** | **2 / 8** — P3b, P4b |
| **NOT IMPLEMENTED** | **4 / 8** — **P3, P3c, P5a, P5b** |
| **TESTED** (dedicated automated coverage) | **0 / 8** |
| **NOT VERIFIED** | P4b runtime, P4c encryption |

## Consequences

1. **The redaction-before-dedup ordering (P3) has no implementation**, so the
   Phase 4.8 V5–V7 counts are reproducible **only** by re-running the *unredacted*
   normalisation. Once P3 lands, those figures **must be re-derived** under the
   pinned version before they are cited again.
2. **P5 has no deletion capability at all.** This directly blocks P2.13/P2.14
   (erasure rights) — a reviewer cannot be told erasure "can be honoured" while
   no cascade delete exists. **P1/P2 closure is therefore partly contingent on P5.**
3. **P4a is the one genuinely production-grade control** and is why the API
   returned 401 on the protected endpoint in earlier phases.
4. No P3–P5 control currently carries **dedicated automated test coverage**, so
   none may be reported as **TESTED**.
