"""P3 / P3b / P3c privacy controls for AURA (Phase 4.13).

Implements the *approved specifications* only:

* **P3**  — redaction of direct identifiers, and redaction is guaranteed to run
  **before** deduplication (``PHASE49_PRIVACY_REVIEW_CHECKLIST.md`` §P3).
* **P3b** — an explicit ``PREPROCESS_VERSION``, **NFKC** normalisation, pinned
  regex rules, and a version fingerprint so stale artifacts are detectable.
* **P3c** — salted text hashing ``SHA256(salt || normalised_text)`` with the
  salt supplied by the caller, never hard-coded and never committed.
* **M1–M4** — the approved Fine-grained label mapping, keeping
  ``Profane/Untargeted`` (class 4) excluded/unknown.

Isolation guarantees
--------------------
* Standalone: imports neither ``backend`` nor ``ml_service`` and touches no
  database, no dataset, no frozen split and no manifest.
* Contains **no salt**, **no retention period** and **no RUHSOLD data**.
* The legacy engine keeps its own NFC normalisation (``mlexicon.py``) — that is
  deliberately left untouched; NFKC here is the *approved spec* for the new
  preprocessing path.

Spec: PHASE49_PRIVACY_REVIEW_CHECKLIST.md, PHASE49_LABEL_MAPPING_DECISIONS.md
"""
from __future__ import annotations

import hashlib
import re
import secrets
import unicodedata
from typing import Any, Dict, Iterable, List, Sequence, Tuple

__all__ = [
    "PREPROCESS_VERSION",
    "UNICODE_NORMALIZATION",
    "RULES_VERSION",
    "PINNED_REGEX_VERSION",
    "redact",
    "normalise",
    "normalize",
    "text_hash",
    "dedup_key",
    "prepare",
    "mapping_status",
    "map_label",
    "generate_salt",
    "preprocess_fingerprint",
    "EXCLUDED_CLASSES",
    "AMBIGUOUS_LABEL",
]

# --------------------------------------------------------------------------
# P3b — explicit, pinned preprocessing identity
# --------------------------------------------------------------------------
PREPROCESS_VERSION = "1.0.0"
UNICODE_NORMALIZATION = "NFKC"
# Pinned rule set: bump on ANY behavioural change to the patterns below.
RULES_VERSION = "1.0.0"
PINNED_REGEX_VERSION = f"redaction-rules/{RULES_VERSION}"

# Ordered: URLs first (so an email inside a URL is not double-handled),
# then emails, then handles, then phone-like runs, then long numeric IDs.
_PATTERNS: Sequence[Tuple[str, str]] = (
    (r"https?://\S+|www\.\S+|t\.co/\S+", "[URL]"),
    (r"[\w.+-]+@[\w-]+\.[\w.-]+", "[EMAIL]"),
    (r"@\w+", "[USER]"),
    (r"(?<!\w)\+?\d[\d\s().-]{7,}\d(?!\w)", "[PHONE]"),
    (r"(?<!\w)\d{6,}(?!\w)", "[ID]"),
)
_COMPILED: Sequence[Tuple[re.Pattern, str]] = tuple(
    (re.compile(pattern), token) for pattern, token in _PATTERNS
)
_WS = re.compile(r"\s+")

# M3: class 4 is ambiguous and stays excluded/unknown.
AMBIGUOUS_LABEL = 4
EXCLUDED_CLASSES = frozenset({AMBIGUOUS_LABEL})


class P3Error(ValueError):
    """Raised for misuse of the P3 helpers (e.g. an empty salt)."""


def generate_salt(nbytes: int = 32) -> str:
    """Fresh salt. Generated at call time — no salt exists in this module."""
    if nbytes < 16:
        raise P3Error("Salt must be at least 16 bytes.")
    return secrets.token_hex(nbytes)


# --------------------------------------------------------------------------
# P3 — redaction
# --------------------------------------------------------------------------
def redact(text: Any) -> str:
    """Replace direct identifiers with stable tokens.

    Returns ``''`` for non-string input rather than raising, so a bad row can
    never abort a batch silently mid-way.
    """
    if text is None:
        return ""
    s = str(text)
    for pattern, token in _COMPILED:
        s = pattern.sub(token, s)
    return s


# --------------------------------------------------------------------------
# P3b — deterministic normalisation
# --------------------------------------------------------------------------
def normalise(text: Any) -> str:
    """redact -> NFKC -> casefold -> collapse whitespace.

    Deterministic: the same input always yields the same output.
    """
    s = redact(text)
    s = unicodedata.normalize(UNICODE_NORMALIZATION, s)
    s = s.casefold()
    return _WS.sub(" ", s).strip()


# Public alias so either spelling resolves to the single implementation.
normalize = normalise


def preprocess_fingerprint() -> Dict[str, str]:
    """Identity recorded alongside any artifact built with this pipeline.

    Changing any component changes the fingerprint, so a manifest produced under
    an older version is detectably stale instead of silently comparable.
    """
    return {
        "preprocess_version": PREPROCESS_VERSION,
        "unicode_normalization": UNICODE_NORMALIZATION,
        "rules_version": RULES_VERSION,
        "pinned_regex_version": PINNED_REGEX_VERSION,
    }


# --------------------------------------------------------------------------
# P3c — salted hashing
# --------------------------------------------------------------------------
def text_hash(normalised_text: str, salt: str) -> str:
    """``SHA256(salt || normalised_text)`` as a lowercase hex digest.

    The salt is mandatory: an empty/absent salt would make the digest
    reversible by rainbow table, defeating the control.
    """
    if not isinstance(salt, str) or not salt.strip():
        raise P3Error(
            "A non-empty salt is required for P3c text hashing; "
            "refusing to produce an unsalted digest."
        )
    if not isinstance(normalised_text, str):
        raise P3Error("text_hash expects an already-normalised string.")
    return hashlib.sha256(
        (salt + normalised_text).encode("utf-8", "surrogatepass")
    ).hexdigest()


def dedup_key(text: Any, salt: str) -> str:
    """P3 + P3b + P3c in the mandated order: **redact -> normalise -> hash**.

    Because redaction precedes hashing, a handle/URL difference can never
    produce a different key, and raw identifiers never reach the digest.
    """
    return text_hash(normalise(text), salt)


def prepare(records: Iterable[Any], salt: str) -> List[Dict[str, Any]]:
    """Run the pipeline in order and deduplicate.

    Ordering guarantee: every record is **redacted first** (P3) and only then
    normalised (P3b) and hashed (P3c); deduplication is evaluated on the
    redacted key. Two records that differ only by a direct identifier collapse
    to one, proving redaction happened before deduplication.
    """
    if not isinstance(salt, str) or not salt.strip():
        raise P3Error("prepare() requires a non-empty salt.")
    fingerprint = preprocess_fingerprint()
    seen: Dict[str, int] = {}
    out: List[Dict[str, Any]] = []
    for idx, record in enumerate(records):
        normalised = normalise(record)
        key = text_hash(normalised, salt)
        if key in seen:
            continue
        seen[key] = idx
        out.append(
            {
                "index": idx,
                "normalised": normalised,
                "text_hash": key,
                "redacted": redact(record),
                "fingerprint": fingerprint,
            }
        )
    return out


# --------------------------------------------------------------------------
# M1–M4 — approved label mapping
# --------------------------------------------------------------------------
_LABEL_RULES: Dict[int, Dict[str, Any]] = {
    0: {"toxic": 1, "identity_hate": 0, "status": "mapped"},  # Abusive/Offensive
    1: {"toxic": 0, "identity_hate": 0, "status": "mapped"},  # Normal
    2: {"toxic": 1, "identity_hate": 1, "status": "mapped"},  # Religious Hate
    3: {"toxic": 1, "identity_hate": 1, "status": "mapped"},  # Sexism
}


def map_label(class_id: Any) -> Dict[str, Any]:
    """Map one Fine-grained RUHSOLD class under the **approved** M1–M4 rules.

    M3: class 4 (``Profane/Untargeted``) is **excluded and unknown**. It is
    never assigned ``toxic: 0`` — counting it as a verified negative would
    deflate a measured FPR and could manufacture a gate pass.
    """
    if isinstance(class_id, bool) or not isinstance(class_id, int):
        raise P3Error(f"Label must be an integer class id, got {class_id!r}.")
    if class_id in EXCLUDED_CLASSES:
        return {
            "class_id": class_id,
            "status": "excluded_pending_adjudication",
            "truth": "unknown",
            "toxic": None,
            "identity_hate": None,
            "counts_as_verified_negative": False,
            "counts_as_verified_positive": False,
        }
    rule = _LABEL_RULES.get(class_id)
    if rule is None:
        # Unknown class: treat as unknown rather than guessing a polarity.
        return {
            "class_id": class_id,
            "status": "unknown_class",
            "truth": "unknown",
            "toxic": None,
            "identity_hate": None,
            "counts_as_verified_negative": False,
            "counts_as_verified_positive": False,
        }
    return {
        "class_id": class_id,
        "status": rule["status"],
        "truth": "known",
        "toxic": rule["toxic"],
        "identity_hate": rule["identity_hate"],
        "counts_as_verified_negative": rule["toxic"] == 0,
        "counts_as_verified_positive": rule["toxic"] == 1,
    }


def mapping_status(class_id: Any) -> str:
    """Convenience: just the status string."""
    return str(map_label(class_id)["status"])
