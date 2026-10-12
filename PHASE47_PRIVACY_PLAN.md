# AURA Phase 4.7 — Privacy and Licensing Plan (RUHSOLD)

**Status: PLAN — NOT APPROVED. No data was downloaded, so no PII has been
observed, extracted or stored.**

---

## 1. MIT licence — scope, and what it does NOT cover

**Verified:** API `license:mit`; README states the repository
*"is under MIT License"*. Curators: Hammad Rizwan, Muhammad Haroon Shakeel, Asim
Karim (LUMS). Peer-reviewed EMNLP 2020.

### What MIT does cover
Rights to use, copy, modify, merge, publish and distribute the **repository's
artwork** — here, the curated file of tweets with labels.

### What MIT does **not** resolve ⚠️

| Obligation | Status |
|---|---|
| **Rights in the underlying tweets** | **UNRESOLVED.** MIT was granted by the *curators*, who almost certainly cannot re licence Twitter/X content wholesale. The tweets remain the property of their authors under the platform's terms. |
| **Data-protection law (GDPR/local equivalents)** | **UNRESOLVED.** A software licence does not establish a lawful basis for processing personal data. |
| **Platform ToS compliance** | **UNRESOLVED.** |
| **Ongoing deletion/erasure requests** | **UNRESOLVED.** |
| **Annotator privacy** | N/A for RUHSOLD (upstream annotators); applies to our own `ur-Arab` commissioning. |

**Conclusion: MIT clearance is necessary but not sufficient.** A legal/privacy
review is required before import. This is recorded as a **blocker**, not assumed
away.

---

## 2. PII assessment — public social-media text

**Source:** tweets. **Upstream performed no PII assessment** — the README's
*Personal and Sensitive Information* section reads *"[More Information Needed]"*
(`PHASE46_RUHSOLD_LABEL_AUDIT.md §2`). We cannot rely on upstream handling.

### Expected PII classes (assessed structurally; **none observed**)

| Class | Likelihood | Notes |
|---|---|---|
| `@usernames` / handles | **High** | pervasive in tweets |
| Display names | **High** | |
| URLs (incl. profile links) | **High** | |
| Third parties **quoted** by the author | **Medium** | PII of people who did not author the tweet |
| Locality / self-disclosure | **Medium** | "main Karachi se…" |
| Email / phone | **Low–Medium** | |
| Images / avatars | **None** | text-only dataset |
| Special-category data (religion, gender, health, politics) | **High by design** | classes 2 and 3 are *Religious Hate* and *Sexism* — the labels themselves assert protected characteristics about the target |

⚠️ **The last row is the significant one.** Class membership is itself an
inference about a person's identity characteristics. Even pseudonymised rows
carry special-category implications.

⚠️ **Content risk:** the paper's own example row contains an ethnic/religious
slur. Annotator wellbeing provisions are mandatory (see
`PHASE46_URDU_SCRIPT_COLLECTION_PLAN.md §4`).

---

## 3. Controls — required before any import

### 3.1 Minimization
- Ingest **only** `tweet` + `label`; drop every other upstream field.
- Immediately derive and store **`text_hash`** (salted SHA256) as the join key.
  Retain raw text **only** where operationally necessary.
- **Never** persist handles, display names or profile URLs.

### 3.2 Redaction (at ingest, before storage)
| Pattern | Action |
|---|---|
| `@\w+` handles | replace with `[USER]` |
| `https?://\S+`, `t.co/\S+` | replace with `[URL]` |
| Email addresses | replace with `[EMAIL]` |
| Phone-number patterns | replace with `[PHONE]` |
| Numeric IDs ≥ 6 digits | flag for human review |

Redaction is **regex + human spot-check**; regex alone is insufficient for
Roman Urdu romanisations and obfuscated forms (`@user` → `u$er`).

**Redaction changes the text** — it must be applied **consistently across all
splits before deduplication**, and the redaction function versioned, or
V5–V7 duplicate results will not reproduce.

### 3.3 Restricted access
- Role-based; access logged.
- Raw text **never** emitted to application logs, error traces or reports.
- Benchmark reports contain **aggregate counts only** — never a raw row.
  (This phase's own outputs obey that rule: no tweet text appears anywhere.)

### 3.4 Retention and deletion
- Time-bounded retention with a defined **deletion date**, approved up front.
- Documented **erasure procedure** capable of removing an individual row and
  cascading to derived artifacts (splits, manifests, cached features).
- Backups included in the deletion schedule.

### 3.5 Provenance
Per-row `source`, `source_url`, retrieval date, **snapshot SHA256**
(V2 in `PHASE47_SPLIT_VERIFICATION_PLAN.md`), `licence = MIT`, and an explicit
`licence_scope_note` recording that MIT covers the curated artefact but **not**
the underlying tweets.

---

## 4. Annotator privacy (applies to `ur-Arab` commissioning)

- Commissioned text is **preferred over scraped text** — eliminates third-party
  PII entirely (`PHASE46_URDU_SCRIPT_COLLECTION_PLAN.md §3`).
- Annotator IDs pseudonymised in all stored artifacts; identity mapping held
  separately with restricted access.
- Wellbeing: content warnings, opt-out, rotation, and access to support for
  slur-heavy material.

---

## 5. Approvals required

| # | Approval | Status |
|---|---|---|
| P1 | **Legal review** of MIT scope vs underlying tweet rights | **PENDING — blocks import** |
| P2 | Lawful basis / ToS compliance determination | **PENDING — blocks import** |
| P3 | Redaction patterns and the human spot-check procedure | PENDING |
| P4 | Retention period and deletion procedure | PENDING |
| P5 | Access-control model | PENDING |

**No PII was observed, extracted, stored or reproduced. No raw personal
identifier appears in any log or report produced this phase.**
