#!/usr/bin/env python3
"""AURA multilingual smoke-test matrix.

Hits a *running* AURA backend over HTTP and validates the multilingual
prediction contract: 12 languages x {non_toxic, toxic} plus English extras,
followed by a small end-to-end block (health, batch, history, dataset stats,
analytics).  A pass/fail table is printed and the process exits 0 only when
every matrix case and every end-to-end check passes.

Expectations are fixed (language + toxic/non-toxic); API outputs are never
hardcoded.  When the real multilingual dataset or lexicon example sentences
exist next to this file, the built-in sample sentences are overridden with
dataset rows so the matrix tracks the real data.

Usage:
    python tests_multilingual.py [--username admin] [--password Admin@1234]
                                 [--timeout 30] [--base-url http://127.0.0.1:8010]

Environment:
    AURA_BASE_URL   base URL of the backend (default http://127.0.0.1:8010)

Exit codes:
    0  every matrix case and every end-to-end check passed
    1  at least one matrix case or end-to-end check failed
    2  connection / timeout error - the backend could not be reached
    3  login failed - the matrix could not run

Standard library only: urllib, json, argparse, csv (+ os, sys, pathlib).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

# --------------------------------------------------------------------------
# configuration
# --------------------------------------------------------------------------
DEFAULT_BASE_URL = "http://127.0.0.1:8010"
DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "Admin@1234"
DEFAULT_TIMEOUT = 30.0

# processing modes that count as "supported" for the 12 matrix languages.
VALID_MODES = ("existing_model", "language_lexicon")

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
MULTILINGUAL_DIR = DATA_DIR / "multilingual"
MULTILINGUAL_CSV = MULTILINGUAL_DIR / "raw" / "multilingual_demo.csv"
LEXICON_DIR = DATA_DIR / "lexicons"
MAIN_DATASET_DIRS = ("raw", "train", "test", "validation")

LANG_NAMES = {
    "en": "English",
    "ta": "Tamil",
    "ta-Latn": "Tanglish",
    "hi": "Hindi",
    "te": "Telugu",
    "ml": "Malayalam",
    "kn": "Kannada",
    "bn": "Bengali",
    "mr": "Marathi",
    "gu": "Gujarati",
    "pa": "Punjabi",
    "ur": "Urdu",
    "und": "Unknown",
}

NAME_TO_CODE = {
    "english": "en",
    "tamil": "ta",
    "tamil + english": "ta",
    "tamil-latin": "ta-Latn",
    "tanglish": "ta-Latn",
    "roman tamil": "ta-Latn",
    "hindi": "hi",
    "hindi + english": "hi",
    "telugu": "te",
    "telugu + english": "te",
    "malayalam": "ml",
    "malayalam + english": "ml",
    "kannada": "kn",
    "kannada + english": "kn",
    "bengali": "bn",
    "bengali + english": "bn",
    "marathi": "mr",
    "marathi + english": "mr",
    "gujarati": "gu",
    "punjabi": "pa",
    "urdu": "ur",
    "unknown": "und",
}

TEXT_COLUMNS = (
    "text",
    "comment",
    "sentence",
    "content",
    "message",
    "sample",
    "utterance",
    "review",
    "comments",
)
LABEL_COLUMNS = (
    "label",
    "toxicity",
    "toxic",
    "class",
    "target",
    "is_toxic",
    "overall_label",
    "category",
    "sentiment",
    "tag",
)
LANGUAGE_COLUMNS = (
    "language_code",
    "language",
    "lang_code",
    "lang",
    "detected_language",
    "native_language",
    "language_name",
)
EXAMPLE_KEYS = (
    "examples",
    "example_sentences",
    "samples",
    "sentences",
    "demo_samples",
    "demo",
)

TOXIC_VALUES = {
    "toxic",
    "1",
    "true",
    "yes",
    "hate",
    "hate_speech",
    "offensive",
    "abusive",
    "harmful",
    "unsafe",
    "severe_toxic",
}
NON_TOXIC_VALUES = {
    "non_toxic",
    "nontoxic",
    "not_toxic",
    "neutral",
    "0",
    "false",
    "no",
    "benign",
    "safe",
    "ham",
    "normal",
    "acceptable",
    "clean",
}


# --------------------------------------------------------------------------
# test matrix (expectations only - never API outputs)
# --------------------------------------------------------------------------
def build_cases():
    """Return the full 12-language x {non_toxic, toxic} matrix + English extras."""
    cases = []

    def add(code, kind, text):
        cases.append(
            {
                "display": LANG_NAMES.get(code, code),
                "text": text,
                "expected_code": code,
                "expected_type": kind,
            }
        )

    # English (part of the 12-language matrix)
    add("en", "non_toxic", "Hello, how are you today?")
    add("en", "toxic", "You are stupid and useless, I hate you.")

    # Tamil
    add("ta", "non_toxic", "நீ எப்படி இருக்கிறாய்? நன்றாக இருக்கிறேன்.")
    add("ta", "toxic", "நீ ஒரு முட்டாள், உன்னை வெறுக்கிறேன்.")

    # Tanglish (romanised Tamil)
    add("ta-Latn", "non_toxic", "nee epdi iruka? naan nalla iruken.")
    add("ta-Latn", "toxic", "nee vera level mudhalai, unnai verukkiren")

    # Hindi
    add("hi", "non_toxic", "नमस्ते, आप कैसे हैं?")
    add("hi", "toxic", "तुम बहुत बेवकूफ हो, मैं तुमसे नफरत करता हूँ.")

    # Telugu
    add("te", "non_toxic", "నువ్వు ఎలా ఉన్నావు? నేను బాగున్నాను.")
    add("te", "toxic", "నువ్వు ఒక పిచ్చివాడివి, నిన్ను ద్వేషిస్తున్నాను.")

    # Malayalam
    add("ml", "non_toxic", "നിങ്ങൾ എങ്ങനെയാണ്? ഞാൻ നന്നായിരിക്കുന്നു.")
    add("ml", "toxic", "നീ ഒരു വിഡ്ഢിയാണ്, ഞാൻ നിന്നെ വെറുക്കുന്നു.")

    # Kannada
    add("kn", "non_toxic", "ನೀನು ಹೇಗಿದ್ದೀಯಾ? ನಾನು ಚೆನ್ನಾಗಿದ್ದೇನೆ.")
    add("kn", "toxic", "ನೀನು ಒಂದು ಮೂರ್ಖ, ನಿನ್ನನ್ನು ದ್ವೇಷಿಸುತ್ತೇನೆ.")

    # Bengali
    add("bn", "non_toxic", "আপনি কেমন আছেন? আমি ভালো আছি.")
    add("bn", "toxic", "তুমি একজন বোকা, আমি তোমাকে ঘৃণা করি.")

    # Marathi
    add("mr", "non_toxic", "नमस्ते, तुम्ही कसे आहात? मी छान आहे.")
    add("mr", "toxic", "तू एक मूर्ख आहेस, मी तुला नफरत करतो.")

    # Gujarati
    add("gu", "non_toxic", "તમે કેમ છો? હું સારો છું.")
    add("gu", "toxic", "તું એક મૂર્ખ છે, હું તને નફરત કરું છું.")

    # Punjabi
    add("pa", "non_toxic", "ਤੁਸੀਂ ਕਿਵੇਂ ਹੋ? ਮੈਂ ਠੀਕ ਹਾਂ.")
    add("pa", "toxic", "ਤੂੰ ਇੱਕ ਮੂਰਖ ਹੈਂ, ਮੈਂ ਤੈਨੂੰ ਨਫ਼ਰਤ ਕਰਦਾ ਹਾਂ.")

    # Urdu
    add("ur", "non_toxic", "آپ کیسے ہیں؟ میں ٹھیک ہوں.")
    add("ur", "toxic", "تم ایک بیوقوف ہو، میں تم سے نفرت کرتا ہوں.")

    # English extras: threats, obscene/insult guards, false-positive guards
    add("en", "toxic", "I will find you and hurt you tomorrow.")
    add("en", "toxic", "I will hurt you badly tomorrow.")
    add("en", "toxic", "You are a fucking idiot, shut up.")
    add("en", "non_toxic", "The class was held in the basement.")
    add("en", "non_toxic", "Hello friends, have a great day.")

    return cases


# --------------------------------------------------------------------------
# language-code resolution from an API payload
# --------------------------------------------------------------------------
def looks_like_code(value):
    """True for short code-shaped strings such as 'ta' or 'hi'."""
    if not value or not isinstance(value, str):
        return False
    text = value.strip()
    if not (2 <= len(text) <= 4):
        return False
    return all(ch.isalnum() or ch in "-_" for ch in text)


def resolve_detected_code(payload):
    """language_code first, then a code-shaped `language`, then the language name.

    The API may carry the display NAME in `language` and the CODE in
    `language_code`, so `language_code` always wins when present.
    """
    if not isinstance(payload, dict):
        return None

    code = payload.get("language_code")
    if isinstance(code, str) and code.strip():
        return code.strip()

    language = payload.get("language")
    if isinstance(language, str) and language.strip():
        text = language.strip()
        if looks_like_code(text):  # e.g. "ta", "hi"
            return text
        mapped = NAME_TO_CODE.get(text.lower())
        if mapped:
            return mapped

    name = payload.get("language_name")
    if not isinstance(name, str) or not name.strip():
        name = language if isinstance(language, str) else ""
    name = (name or "").strip()
    if name:
        mapped = NAME_TO_CODE.get(name.lower())
        if mapped:
            return mapped
        base = name.lower().split("+")[0].strip()
        if base in NAME_TO_CODE:
            return NAME_TO_CODE[base]
    return None


# --------------------------------------------------------------------------
# dataset / lexicon overrides
# --------------------------------------------------------------------------
def _norm(value):
    return " ".join(str(value).split()).lower()


def normalize_label(value):
    """Map a dataset label to 'toxic' / 'non_toxic' (or None when unknown)."""
    if value is None:
        return None
    text = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    if not text:
        return None
    if text in TOXIC_VALUES:
        return "toxic"
    if text in NON_TOXIC_VALUES:
        return "non_toxic"
    return None


def coerce_code(value):
    """Turn a dataset language cell (code or display name) into a canonical code."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None

    hyphenated = text.replace("_", "-")
    for code in LANG_NAMES:
        if code.lower() == hyphenated.lower():
            return code
    if hyphenated.lower() == "ta-latn":
        return "ta-Latn"

    lowered = text.lower()
    if lowered in NAME_TO_CODE:
        return NAME_TO_CODE[lowered]
    base = lowered.split("+")[0].strip()
    if base in NAME_TO_CODE:
        return NAME_TO_CODE[base]

    # Unknown but code-shaped values ("bn", "ur-IN", ...) are kept as-is.
    if 2 <= len(hyphenated) <= 6 and all(ch.isalnum() or ch == "-" for ch in hyphenated):
        return hyphenated
    return None


def _first_value(row, columns):
    """First non-empty cell among `columns`, exact match first then case-insensitive."""
    if not isinstance(row, dict):
        return None
    for key in columns:
        value = row.get(key)
        if value not in (None, ""):
            return value
    lowered = {}
    for key, value in row.items():
        if key is not None:
            lowered[str(key).strip().lower()] = value
    for key in columns:
        value = lowered.get(key)
        if value not in (None, ""):
            return value
    return None


def _read_csv_rows(path):
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames:
                return []
            return [dict(row) for row in reader]
    except (OSError, UnicodeDecodeError, csv.Error):
        return []


def _multilingual_csv_paths():
    paths = []
    if MULTILINGUAL_CSV.is_file():
        paths.append(MULTILINGUAL_CSV)
    if MULTILINGUAL_DIR.is_dir():
        for path in sorted(MULTILINGUAL_DIR.rglob("*.csv")):
            if path not in paths:
                paths.append(path)
    return paths


def load_multilingual_samples():
    """(code, kind, text, origin) rows from data/multilingual/**.csv when present."""
    samples = []
    for path in _multilingual_csv_paths():
        for row in _read_csv_rows(path):
            code = coerce_code(_first_value(row, LANGUAGE_COLUMNS))
            kind = normalize_label(_first_value(row, LABEL_COLUMNS))
            raw = _first_value(row, TEXT_COLUMNS)
            if not code or kind is None or raw is None:
                continue
            text = str(raw).strip()
            if text:
                samples.append((code, kind, text, path.name))
    return samples


def _examples_from(blob, code, origin):
    """Example sentences from a lexicon payload value (any accepted shape)."""
    found = []
    if isinstance(blob, dict):
        for key, values in blob.items():
            kind = normalize_label(key)
            if kind is None or not isinstance(values, (list, tuple)):
                continue
            for item in values:
                if isinstance(item, str) and item.strip():
                    found.append((code, kind, item.strip(), origin))
    elif isinstance(blob, (list, tuple)):
        for item in blob:
            if not isinstance(item, dict):
                continue  # a bare string carries no label
            text = (
                item.get("text")
                or item.get("comment")
                or item.get("sentence")
                or item.get("message")
            )
            kind = normalize_label(
                item.get("label") or item.get("toxicity") or item.get("class")
            )
            if text and kind:
                found.append((code, kind, str(text).strip(), origin))
    return found


def load_lexicon_examples():
    """(code, kind, text, origin) example sentences from data/lexicons/*.json."""
    examples = []
    if not LEXICON_DIR.is_dir():
        return examples
    for path in sorted(LEXICON_DIR.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        code = coerce_code(
            payload.get("language_code")
            or payload.get("language")
            or payload.get("code")
            or path.stem
        )
        if not code:
            continue
        for key in EXAMPLE_KEYS:
            if key in payload:
                examples.extend(_examples_from(payload.get(key), code, path.name))
        for label_key in ("toxic", "non_toxic"):
            kind = normalize_label(label_key)
            blob = payload.get(label_key)
            if kind and isinstance(blob, (list, tuple)):
                for item in blob:
                    if isinstance(item, str) and item.strip():
                        examples.append((code, kind, item.strip(), path.name))
    return examples


def load_main_dataset_texts():
    """Normalised texts of the main dataset (used to prefer overlapping rows)."""
    texts = set()
    for folder_name in MAIN_DATASET_DIRS:
        folder = DATA_DIR / folder_name
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.csv")):
            for row in _read_csv_rows(path):
                raw = _first_value(row, TEXT_COLUMNS)
                if raw not in (None, ""):
                    texts.add(_norm(raw))
    return texts


def build_dataset_overrides():
    """{(code, kind): (text, note)} - dataset rows win over the built-in samples.

    Priority: multilingual row also present in the main dataset > any other
    multilingual row > example sentence found in data/lexicons/*.json.
    """
    samples = load_multilingual_samples()
    lexicon_examples = load_lexicon_examples()
    if not samples and not lexicon_examples:
        return {}

    overrides = {}
    for code, kind, text, origin in lexicon_examples:
        overrides.setdefault((code, kind), (text, f"example sentence from {origin}"))

    if samples:
        main_texts = load_main_dataset_texts()
        fallback = {}
        preferred = {}
        for code, kind, text, origin in samples:
            fallback.setdefault((code, kind), (text, f"row from {origin}"))
            if main_texts and _norm(text) in main_texts:
                preferred.setdefault(
                    (code, kind),
                    (text, f"row from {origin} that also appears in the main dataset"),
                )
        overrides.update(fallback)
        overrides.update(preferred)
    return overrides


def apply_dataset_overrides(cases):
    """Override each language's toxic/non-toxic text with real dataset rows."""
    overrides = build_dataset_overrides()
    applied = []
    for case in cases:
        key = (case["expected_code"], case["expected_type"])
        if key not in overrides:
            continue
        text, note = overrides[key]
        if text != case["text"]:
            case["text"] = text
            case["override_note"] = note
            applied.append((key, note))
    return applied


# --------------------------------------------------------------------------
# HTTP client
# --------------------------------------------------------------------------
class TransportError(Exception):
    """Connection / timeout level failure - the backend could not be reached."""


def _decode(raw):
    try:
        return json.loads(raw)
    except ValueError:
        return raw


def _short(data, limit=200):
    try:
        text = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    except (TypeError, ValueError):
        text = str(data)
    text = " ".join(str(text).split())
    if len(text) > limit:
        text = text[: limit - 3] + "..."
    return text


class Client:
    def __init__(self, base_url, timeout):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.token = None

    def request(self, method, path, payload=None, auth=True):
        """Return (status_code, parsed_body); raise TransportError when unreachable."""
        url = self.base_url + path
        headers = {"Accept": "application/json"}
        data = None
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if auth and self.token:
            headers["Authorization"] = "Bearer " + self.token

        request = urllib.request.Request(
            url, data=data, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8", "replace")
                return int(response.getcode() or 200), _decode(raw)
        except urllib.error.HTTPError as exc:  # HTTP errors still carry a body
            try:
                raw = exc.read().decode("utf-8", "replace")
            except OSError:
                raw = ""
            return int(exc.code), _decode(raw)
        except urllib.error.URLError as exc:
            raise TransportError(f"{method} {url} failed: {exc.reason}") from exc
        except TimeoutError as exc:
            raise TransportError(
                f"{method} {url} timed out after {self.timeout:g}s"
            ) from exc
        except OSError as exc:
            raise TransportError(f"{method} {url} failed: {exc}") from exc


# --------------------------------------------------------------------------
# matrix execution + reporting
# --------------------------------------------------------------------------
TABLE_COLUMNS = (
    ("language", 9),
    ("expected_type", 13),
    ("detected_code", 13),
    ("actual_label", 12),
    ("processing_mode", 16),
    ("confidence", 10),
    ("lang_ok", 7),
    ("label_ok", 8),
    ("PASS/FAIL", 9),
)


def _table_line(values):
    return "  ".join(
        str(value).ljust(width) for value, (_, width) in zip(values, TABLE_COLUMNS)
    ).rstrip()


def _flag(value):
    return "OK" if value else "FAIL"


def _fmt_confidence(value):
    if value is None:
        return "-"
    try:
        return f"{float(value):.3f}"
    except (TypeError, ValueError):
        return str(value)[:10]


def run_matrix(client, cases):
    rows = []
    total = len(cases)
    for index, case in enumerate(cases, 1):
        print(
            f"  [{index:>2}/{total}] {case['expected_code']:<9} "
            f"{case['expected_type']:<9} ...",
            flush=True,
        )
        row = {
            "case": case,
            "detected_code": None,
            "actual_label": None,
            "mode": None,
            "confidence": None,
            "lang_ok": False,
            "label_ok": False,
            "mode_ok": False,
            "passed": False,
            "error": None,
        }
        status, data = client.request(
            "POST", "/predict", {"text": case["text"], "source": "text"}
        )
        if status != 200:
            row["error"] = f"HTTP {status}: {_short(data)}"
        elif not isinstance(data, dict):
            row["error"] = f"unexpected response body: {_short(data)}"
        else:
            code = resolve_detected_code(data)
            actual = data.get("overall_label")
            actual = str(actual).strip().lower() if actual is not None else None
            mode = data.get("processing_mode")
            mode = str(mode).strip() if mode is not None else None
            confidence = data.get("confidence")

            row["detected_code"] = code
            row["actual_label"] = actual
            row["mode"] = mode
            row["confidence"] = confidence
            row["lang_ok"] = code == case["expected_code"]
            row["label_ok"] = actual == case["expected_type"]
            row["mode_ok"] = mode in VALID_MODES
            row["passed"] = row["lang_ok"] and row["label_ok"] and row["mode_ok"]
            if mode not in VALID_MODES:
                row["error"] = f"processing_mode '{mode or '-'}' is not supported"
        rows.append(row)
    return rows


def print_matrix_table(rows):
    print()
    print(_table_line([name for name, _ in TABLE_COLUMNS]))
    print(_table_line(["-" * width for _, width in TABLE_COLUMNS]))
    for row in rows:
        case = row["case"]
        print(
            _table_line(
                [
                    case["expected_code"],
                    case["expected_type"],
                    row["detected_code"] or "-",
                    row["actual_label"] or "-",
                    row["mode"] or "-",
                    _fmt_confidence(row["confidence"]),
                    _flag(row["lang_ok"]),
                    _flag(row["label_ok"]),
                    "PASS" if row["passed"] else "FAIL",
                ]
            )
        )


def print_failure_details(rows):
    failed = [row for row in rows if not row["passed"]]
    if not failed:
        return
    print()
    print("Failure details (lang_ok / label_ok reported separately):")
    for row in failed:
        case = row["case"]
        print(
            f"  - {case['expected_code']} ({case['display']}) expected={case['expected_type']}: "
            f"lang_ok={row['lang_ok']} detected_code={row['detected_code'] or '-'} | "
            f"label_ok={row['label_ok']} actual_label={row['actual_label'] or '-'} | "
            f"mode_ok={row['mode_ok']} processing_mode={row['mode'] or '-'}"
            + (f" | {row['error']}" if row["error"] else "")
        )


def print_breakdown(rows):
    groups = {}
    for row in rows:
        groups.setdefault(row["case"]["expected_code"], []).append(row)
    print()
    print("Per-language breakdown:")
    for code, items in groups.items():
        passed = sum(1 for item in items if item["passed"])
        status = "PASS" if passed == len(items) else "FAIL"
        print(
            f"  {code:<9} {LANG_NAMES.get(code, code):<10} "
            f"{passed}/{len(items)} passed  {status}"
        )


# --------------------------------------------------------------------------
# end-to-end checks
# --------------------------------------------------------------------------
def run_end_to_end(client):
    checks = []

    def record(name, passed, detail):
        checks.append(
            {"name": name, "passed": bool(passed), "detail": str(detail or "")}
        )

    # 1) health
    status, data = client.request("GET", "/health", auth=False)
    healthy = (
        status == 200
        and isinstance(data, dict)
        and str(data.get("status") or "") == "healthy"
    )
    detail = (
        f"HTTP {status}, status={data.get('status')!r}"
        if isinstance(data, dict)
        else f"HTTP {status}, body={_short(data)}"
    )
    record("GET /health -> status=='healthy'", healthy, detail)

    # 2) batch prediction with mixed-language comments
    comments = [
        "Hello, how are you today?",
        "நீ எப்படி இருக்கிறாய்? நன்றாக இருக்கிறேன்.",
        "तुम बहुत बेवकूफ हो, मैं तुमसे नफरत करता हूँ.",
    ]
    status, data = client.request(
        "POST", "/predict/batch", {"comments": comments, "source": "batch"}
    )
    problems = []
    if status != 200:
        problems.append(f"HTTP {status}: {_short(data)}")
    elif not isinstance(data, dict):
        problems.append(f"response is not an object: {_short(data)}")
    else:
        if data.get("count") != 3:
            problems.append(f"count={data.get('count')!r}, expected 3")
        results = data.get("results")
        if not isinstance(results, list) or len(results) != 3:
            problems.append("results is not a list of 3 items")
        else:
            required = (
                "language",
                "language_code",
                "processing_mode",
                "overall_label",
                "confidence",
            )
            for position, item in enumerate(results, 1):
                if not isinstance(item, dict):
                    problems.append(f"item {position} is not an object")
                    continue
                missing = [key for key in required if item.get(key) in (None, "")]
                if missing:
                    problems.append(
                        f"item {position} missing {', '.join(missing)}"
                    )
    record(
        "POST /predict/batch (3 mixed-language comments)",
        not problems,
        "; ".join(problems) or "count=3, all contract fields present",
    )

    # 3) history shape check (language filter may be a no-op - rows may be 0)
    status, data = client.request("GET", "/history?language=ta")
    history_ok = status == 200 and isinstance(data, list)
    record(
        "GET /history?language=ta (auth) returns HTTP 200",
        history_ok,
        f"HTTP {status}, body type={type(data).__name__}",
    )

    # 4) dataset statistics
    status, data = client.request("GET", "/dataset/stats")
    problems = []
    if status != 200:
        problems.append(f"HTTP {status}: {_short(data)}")
    elif not isinstance(data, dict):
        problems.append(f"response is not an object: {_short(data)}")
    else:
        for key in ("by_language", "languages"):
            if key not in data:
                problems.append(f"missing key '{key}'")
    record(
        "GET /dataset/stats has by_language + languages",
        not problems,
        "; ".join(problems) or "keys present",
    )

    # 5) analytics language distribution
    status, data = client.request("GET", "/analytics")
    problems = []
    if status != 200:
        problems.append(f"HTTP {status}: {_short(data)}")
    elif not isinstance(data, dict):
        problems.append(f"response is not an object: {_short(data)}")
    elif "language_distribution" not in data:
        problems.append("missing key 'language_distribution'")
    record(
        "GET /analytics has language_distribution",
        not problems,
        "; ".join(problems) or "key present",
    )

    return checks


def print_e2e_checks(checks):
    print()
    print("END-TO-END CHECKS:")
    for check in checks:
        status = "PASS" if check["passed"] else "FAIL"
        line = f"  {status}  {check['name']}"
        if check["detail"]:
            line += f"  ({check['detail']})"
        print(line)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="AURA multilingual smoke-test matrix (HTTP smoke tests)."
    )
    parser.add_argument(
        "--username",
        default=DEFAULT_USERNAME,
        help=f"login username (default: {DEFAULT_USERNAME})",
    )
    parser.add_argument(
        "--password",
        default=DEFAULT_PASSWORD,
        help="login password (default: the admin password)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help="per-request timeout in seconds (default: 30)",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("AURA_BASE_URL", DEFAULT_BASE_URL),
        help="backend base URL, defaults to $AURA_BASE_URL "
        f"or {DEFAULT_BASE_URL}",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    client = Client(args.base_url, args.timeout)

    print("AURA multilingual smoke-test matrix")
    print(f"  base URL : {client.base_url}")
    print(f"  timeout  : {args.timeout:g}s")
    print()

    # ---- login ----------------------------------------------------------
    try:
        status, data = client.request(
            "POST",
            "/auth/login",
            {"username": args.username, "password": args.password},
            auth=False,
        )
    except TransportError as exc:
        print(f"CONNECTION ERROR: {exc}", file=sys.stderr)
        print(
            "The AURA backend is unreachable - start it or point AURA_BASE_URL "
            "at the right host/port.",
            file=sys.stderr,
        )
        return 2

    token = None
    if isinstance(data, dict):
        token = data.get("access_token") or data.get("token")
    if status != 200 or not token:
        print(
            f"LOGIN FAILED (HTTP {status}): {_short(data)}",
            file=sys.stderr,
        )
        print("The matrix cannot run without a valid session.", file=sys.stderr)
        return 3
    client.token = str(token)

    # ---- matrix ---------------------------------------------------------
    cases = build_cases()
    applied = apply_dataset_overrides(cases)
    if applied:
        print("Dataset overrides applied (matrix tracks the real data):")
        for (code, kind), note in applied:
            print(f"  - {code}/{kind} <- {note}")
        print()
    print(f"Running {len(cases)} matrix cases...")

    try:
        rows = run_matrix(client, cases)
        checks = run_end_to_end(client)
    except TransportError as exc:
        print(f"CONNECTION ERROR: {exc}", file=sys.stderr)
        print(
            "Lost contact with the AURA backend mid-run - is it restarting?",
            file=sys.stderr,
        )
        return 2

    print_matrix_table(rows)
    print_failure_details(rows)
    print_breakdown(rows)
    print_e2e_checks(checks)

    passed = sum(1 for row in rows if row["passed"])
    failed = len(rows) - passed
    e2e_passed = sum(1 for check in checks if check["passed"])
    e2e_failed = len(checks) - e2e_passed

    print()
    print(f"MATRIX SUMMARY: PASSED {passed} / FAILED {failed}  (of {len(rows)} cases)")
    print(
        f"END-TO-END SUMMARY: PASSED {e2e_passed} / FAILED {e2e_failed}  "
        f"(of {len(checks)} checks)"
    )

    if failed == 0 and e2e_failed == 0:
        print("OVERALL: PASS")
        return 0

    reasons = []
    if failed:
        reasons.append(f"{failed} matrix case(s)")
    if e2e_failed:
        reasons.append(f"{e2e_failed} end-to-end check(s)")
    print("OVERALL: FAIL - " + ", ".join(reasons))
    return 1


if __name__ == "__main__":
    sys.exit(main())
