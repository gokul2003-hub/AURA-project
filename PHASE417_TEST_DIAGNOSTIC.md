# AURA Phase 4.17 — Test File Diagnostic

**Scope:** explain the integrity failure in the original
`tests_p417_session_and_auth_hardening.py`, prove what survived, and document
the repaired split. Read-only forensics on production; synthetic fixtures only.

---

## 1. Symptom

The first authored Phase 4.17 test file was discovered by `unittest` as
**0 tests** despite being a syntactically valid Python module. A recorded run
also raised a traceback:

```
TypeError: 'sqlite3.Row' object does not support indexing: 'blocked'
```

Both facts are explained below. Neither is a defect in `backend.py`.

---

## 2. File-integrity forensics (the file was truncated on disk)

| Property | Observed |
|---|---|
| Size | **3,758 bytes** |
| Lines | **109** |
| SHA-256 (first 16) | `b9a3e0bf…` |
| Compiles | **Yes** (`py_compile` OK) |
| `unittest` discovery | **0 tests** |
| Literal marker | `__PART2__` present at **line 109** |

The file ended mid-authoring with a literal `__PART2__` marker and contained
only the `_Isolated` base class — **no `Test*` class and therefore no `test_*`
method**. Because the module parsed cleanly, `unittest` reported "Ran 0 tests"
rather than an error, which is exactly how a truncated file masquerades as a
passing-empty suite.

### Corroborating `.pyc` forensics

The cached bytecode for the module embeds the source size and mtime used to
validate freshness. Both match the on-disk stub exactly:

| Embedded field | Value | Matches disk? |
|---|---|---|
| Source size | **3,758** | ✅ exact |
| Source mtime | **22:16:12** | ✅ exact |
| `Test*` classes in bytecode | **0** | ✅ consistent with stub |

The bytecode therefore describes the *stub*, not the intended suite. This rules
out a stale-cache explanation and confirms the 66-test content never reached a
`.pyc` either.

### OneDrive placeholder / conflict-copy ruled out

Because the working tree lives under OneDrive, a placeholder (dehydrated) file
or a `*Conflict*`/`*deleteme*` sibling was considered. **Ruled out:** the file
read back as full, coherent UTF-8 ending at a clean statement boundary, with no
reparse-point or alternate-stream content, and no conflict sibling exists.

**Conclusion: the ~66-test content survives in no on-disk artifact.** The stub
was preserved rather than discarded — see §4.

---

## 3. The recorded `TypeError` is from a *different* backend state

The recorded failure,

```
TypeError: 'sqlite3.Row' object does not support indexing: 'blocked'
```

**cannot** originate from the `backend.py` under test, for two independent
reasons:

1. **Message text.** CPython's `sqlite3.Row` raises
   `IndexError: No item with that key` for an unknown key. It does **not**
   produce a `TypeError`, and it never embeds the offending key in the message.
   The observed string is not a standard CPython message.

2. **Call-site.** The referenced site (`backend.py:1378` in that state) was a
   `SELECT`, not a subscript of `row['blocked']`. The `blocked` subscript in the
   current source lives inside `login()` and is guarded by a preceding
   `row['blocked']`-safe short-circuit.

So the traceback reflects a **transient, intermediate `backend.py`** that existed
only while the phase edits were in flight. Its exact provenance is
**unverified** — it is not reproducible against the current file, and the
pre-edit rollback copy does not contain it. Recorded here as unverified rather
than guessed.

---

## 4. Preservation, not deletion

The truncated stub was copied aside and retained as evidence:

```
CODE/BACKEND/tests_p417_session_and_auth_hardening.py.truncated-20261012.bak
```

Nothing was overwritten in place. The repaired suite was authored as **two new
files** (the original was split to reduce the large-single-write truncation
hazard that caused this failure):

| New file | Part | Tests |
|---|---|---|
| `tests_p417_session_security.py` | A — session binding, revocation, expiry | **29** |
| `tests_p417_auth_hardening.py` | B — auth telemetry, throttling, invariants | **35** |

Every write in this phase was verified by size + SHA-256 + `py_compile` +
AST test-count before being trusted.

---

## 5. Discovery-count evidence

| Artifact | Tests discovered |
|---|---|
| Truncated stub (pre-repair) | **0** |
| `tests_p417_session_security.py` (repaired A) | **29** |
| `tests_p417_auth_hardening.py` (repaired B) | **35** |
| **Total recovered** | **64** |

A stale `__pycache__` once produced a phantom `IndentationError` during this
phase; `*p417*` bytecode was cleared before each authoritative run, so the
counts above are from freshly compiled code.

---

## 6. What this does NOT establish

- The **root cause of the original truncation** is **unverified**. The
  large-single-write hypothesis is consistent with the evidence (the stub ends
  at a chunk boundary) but is **not proven**.
- The provenance of the non-standard `TypeError` is **unverified** (§3).
- These suites prove the properties they assert and **only** those properties.
  They do **not** constitute a complete assessment of authentication security.
