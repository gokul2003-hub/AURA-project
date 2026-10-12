"""AURA multilingual language detection + safety-lexicon matching.

Pure standard library: no third-party imports, no network access, no model
downloads, no file writes.  Everything here is deterministic and HEURISTIC -
scores are derived from lexicon hits and are never calibrated probabilities.

Public API
----------
detect(text)            -> {"code", "name", "script"}
load_lexicons()         -> {code: {"language","language_name","script","categories"}}
lexicon_available(code) -> bool   (True when the language lexicon file loads)
match(text, lang_code)  -> {"category_scores", "matched_terms", "matched_categories"}

Lexicon files live in ``data/lexicons/{en,ta,tanglish,hi,te,ml,kn,bn,mr,gu,pa,ur}.json``
and are written by the data pipeline.  A missing or malformed file never raises:
that language simply reports "not available" and the caller uses the fallback
path.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

__all__ = [
    "BASE_DIR",
    "LEXICON_DIR",
    "CATEGORIES",
    "SUPPORTED_CODES",
    "LANG_NAMES",
    "MIXED_LANGUAGE_NAME",
    "detect",
    "load_lexicons",
    "lexicon_available",
    "match",
    "normalize",
]

BASE_DIR = Path(__file__).resolve().parent
LEXICON_DIR = BASE_DIR / "data" / "lexicons"

# Same order as the backend LABELS tuple.
CATEGORIES = ("toxic", "severe_toxic", "obscene", "threat", "insult", "identity_hate")

# Non-English languages that may run through a lexicon when their file exists.
SUPPORTED_CODES = ("ta", "ta-Latn", "hi", "te", "ml", "kn", "bn", "mr", "gu", "pa", "ur")
KNOWN_CODES = ("en", "ta", "ta-Latn", "hi", "te", "ml", "kn", "bn", "mr", "gu", "pa", "ur", "und")

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
MIXED_LANGUAGE_NAME = "Mixed Indian Languages"

# ---------------------------------------------------------------------------
# Script ranges (detection)
# ---------------------------------------------------------------------------
SCRIPT_RANGES = (
    ("Tamil", 0x0B80, 0x0BFF),
    ("Telugu", 0x0C00, 0x0C7F),
    ("Malayalam", 0x0D00, 0x0D7F),
    ("Kannada", 0x0C80, 0x0CFF),
    ("Bengali", 0x0980, 0x09FF),
    ("Devanagari", 0x0900, 0x097F),
    ("Gujarati", 0x0A80, 0x0AFF),
    ("Gurmukhi", 0x0A00, 0x0A7F),
    ("Arabic", 0x0600, 0x06FF),
    ("Latin", 0x0041, 0x024F),
)
INDIC_SCRIPTS = (
    "Tamil",
    "Telugu",
    "Malayalam",
    "Kannada",
    "Bengali",
    "Devanagari",
    "Gujarati",
    "Gurmukhi",
)
LANG_BY_SCRIPT = {
    "Tamil": "ta",
    "Telugu": "te",
    "Malayalam": "ml",
    "Kannada": "kn",
    "Bengali": "bn",
    "Devanagari": "hi",
    "Gujarati": "gu",
    "Gurmukhi": "pa",
    "Arabic": "ur",
}
SCRIPT_BY_LANG = {
    "en": "Latin",
    "ta": "Tamil",
    "ta-Latn": "Latin",
    "hi": "Devanagari",
    "te": "Telugu",
    "ml": "Malayalam",
    "kn": "Kannada",
    "bn": "Bengali",
    "mr": "Devanagari",
    "gu": "Gujarati",
    "pa": "Gurmukhi",
    "ur": "Arabic",
    "und": "Unknown",
}


# U+0964/U+0965 (danda / double danda) sit inside the Devanagari block but
# are shared sentence terminators across Indic scripts (Bengali, Hindi, ...).
# Counting them made every danda-terminated Bengali/Hindi comment register as
# two scripts -> "Mixed" -> und, so they never count as a script signal.
SHARED_INDIC_PUNCTUATION = frozenset((0x0964, 0x0965))


def _build_script_map():
    mapping = {}
    for name, lo, hi in SCRIPT_RANGES:
        for cp in range(lo, hi + 1):
            if cp in SHARED_INDIC_PUNCTUATION:
                continue
            mapping[cp] = name
    return mapping


_SCRIPT_OF = _build_script_map()

# ---------------------------------------------------------------------------
# Normalisation shared by detection and lexicon matching
# ---------------------------------------------------------------------------
_ZERO_WIDTH = {0x00AD: None, 0x200B: None, 0x200C: None, 0x200D: None, 0x2060: None, 0xFEFF: None}
_RUN3 = re.compile(r"([a-z])\1{2,}")
_RUN1 = re.compile(r"([a-z])\1+")
_WS = re.compile(r"\s+")


def _collapse_run(match):
    return match.group(1) * 2


def normalize(text, collapse_runs=True):
    """Casefold + NFC + strip zero-width + collapse whitespace (+ 3+ -> 2 runs).

    ``collapse_runs=False`` keeps long letter runs intact; the matcher uses that
    form to recognise obfuscation such as "stuuuupid" -> "stupid".
    """
    if text is None:
        return ""
    s = unicodedata.normalize("NFC", str(text))
    s = s.translate(_ZERO_WIDTH)
    s = s.casefold()
    s = _WS.sub(" ", s).strip()
    if collapse_runs:
        s = _RUN3.sub(_collapse_run, s)
    return s


# ---------------------------------------------------------------------------
# Marker tables (whole-token matches only, never substring matches)
# ---------------------------------------------------------------------------
LATIN_WORD_CLASS = r"0-9A-Za-z\u00C0-\u024F"
DEVANAGARI_WORD_CLASS = r"0-9\u0900-\u097F"
# Whole Latin-script word tokens used to weigh English evidence in detect().
_LATIN_TOKEN_RE = re.compile(r"[A-Za-z\u00C0-\u024F]+")

# >= 2 distinct markers are required before Latin text is called Tanglish, so
# ordinary English never trips the detector ("enna" can not match inside
# "dinner" because the lookarounds are token boundaries).
TANGLISH_MARKERS = (
    # conversational Tamil written in Latin script
    "nee", "nepdi", "epdi", "iruka", "irukken", "irukka", "unna", "unnai",
    "ennadi", "ennada", "enna", "machan", "machi", "semma", "vera level",
    "koopta", "thooku", "paiya", "sollu", "pannu", "poda", "saapdu", "sapdu",
    "venum", "illa", "illai", "thalaiva", "kollu",
    # romanised Tamil safety words already used by AURA's script detector
    "muttal", "moodan", "kevalam", "kevalamanavan", "asingam", "paithiyam",
    "savu", "seththu", "po tholai", "poy tholai", "kirukkan", "thevadiya",
    "pundai", "porukki", "ozhi", "myre", "mairu",
)

# Very common English function words / greetings used as POSITIVE evidence
# that Latin-script text really is English.  Without such evidence, any
# Latin-script string (Spanish, Swahili, ...) used to be silently labelled
# "en" (finding C-F-2).  Tokens shared with other Latin-script languages
# ("a", "an", "no", "me", "he", "hi", ...) are deliberately excluded so a
# Spanish/Swahili word that merely looks English never counts as evidence.
ENGLISH_MARKERS = (
    # determiners / prepositions / conjunctions
    "the", "of", "to", "in", "on", "at", "by", "for", "with", "from",
    "and", "or", "but", "if", "then", "than", "because", "not",
    # be / do / have
    "is", "are", "was", "were", "be", "been", "am",
    "do", "does", "did", "have", "has", "had",
    # modals
    "will", "would", "can", "could", "should", "shall", "must",
    # demonstratives / pronouns
    "this", "that", "these", "those", "it", "its",
    "i", "you", "she", "we", "they", "them", "their", "his", "her",
    "my", "your", "our", "us",
    # question words
    "who", "what", "when", "where", "why", "how",
    # greetings / politeness
    "hello", "please", "thank", "thanks",
    # Everyday English content words.  Function words alone are too sparse:
    # "have a nice day everyone" carried a single marker ("have") and was
    # wrongly demoted to 'und', which broke ordinary English detection
    # (regression found during Phase 4.1 integration).  These are chosen for
    # high precision — they are not common Spanish/Swahili vocabulary, and
    # token-boundary matching means e.g. Swahili "bado" can not match "bad".
    "nice", "good", "great", "bad", "better", "best", "happy", "sad",
    "sorry", "sure", "maybe", "really", "very", "always", "never", "again",
    "still", "also", "just", "only", "much", "many", "more", "most", "some",
    "any", "all", "every", "each", "other", "another", "thing", "things",
    "way", "place", "time", "times", "day", "days", "today", "tomorrow",
    "yesterday", "night", "morning", "week", "year", "people", "person",
    "life", "world", "friend", "friends", "family", "home", "house",
    "school", "work", "city", "country", "water", "food", "movie", "music",
    "book", "game", "story", "everyone", "somebody", "nobody", "everything",
    "nothing", "want", "wants", "need", "needs", "like", "love", "help",
    "know", "think", "look", "make", "made", "give", "take", "keep",
)

# Devanagari alone is ambiguous (Hindi vs Marathi); >= 2 distinct Marathi
# markers are required before the text is labelled Marathi.
MARATHI_MARKERS = (
    "आहे", "आहेत", "नाही", "नाहीत", "करा", "करतो", "करून", "आहोत",
    "कसे", "काय झालं", "मी", "तुम्ही", "तुमच्या", "आमच्या", "म्हणून",
    "केलं", "झालं",
)

_MARKER_PATTERNS = {}


def _marker_pattern(marker, word_class):
    key = (marker, word_class)
    pat = _MARKER_PATTERNS.get(key)
    if pat is None:
        body = r"[\s\W]*".join(re.escape(part) for part in marker.split(" "))
        pat = re.compile(r"(?<![%s])%s(?![%s])" % (word_class, body, word_class))
        _MARKER_PATTERNS[key] = pat
    return pat


def _marker_count(text, markers, word_class):
    """Number of DISTINCT markers that match a whole token in ``text``."""
    found = set()
    for marker in markers:
        if marker in found:
            continue
        if _marker_pattern(marker, word_class).search(text):
            found.add(marker)
    return len(found)


def detect(text):
    """Detect the language of ``text``.

    Returns {"code", "name", "script"} where code is one of
    en, ta, ta-Latn, hi, te, ml, kn, bn, mr, gu, pa, ur, und.
    """
    norm = normalize(text)
    counts = {}
    for ch in norm:
        name = _SCRIPT_OF.get(ord(ch))
        if name is not None:
            counts[name] = counts.get(name, 0) + 1
    if not counts:
        return {"code": "und", "name": "Unknown", "script": "Unknown"}

    indic = [name for name in INDIC_SCRIPTS if counts.get(name)]
    if len(indic) >= 2:
        return {"code": "und", "name": MIXED_LANGUAGE_NAME, "script": "Mixed"}
    if len(indic) == 1:
        script = indic[0]
        if script == "Devanagari":
            code = "mr" if _marker_count(norm, MARATHI_MARKERS, DEVANAGARI_WORD_CLASS) >= 2 else "hi"
        else:
            code = LANG_BY_SCRIPT[script]
        return {"code": code, "name": LANG_NAMES[code], "script": script}

    arabic = counts.get("Arabic", 0)
    latin = counts.get("Latin", 0)
    if arabic and arabic >= latin:
        return {"code": "ur", "name": LANG_NAMES["ur"], "script": "Arabic"}
    if latin:
        tanglish_hits = _marker_count(norm, TANGLISH_MARKERS, LATIN_WORD_CLASS)
        if tanglish_hits >= 2:
            return {"code": "ta-Latn", "name": LANG_NAMES["ta-Latn"], "script": "Latin"}
        english_hits = _marker_count(norm, ENGLISH_MARKERS, LATIN_WORD_CLASS)
        # Ordinary English keeps "en".  Discrimination against unsupported
        # Latin languages comes from the MARKER SET, not the count: Spanish /
        # Swahili / French sentences score 0 hits because shared tokens ("a",
        # "an", "no", "me", "he", "hi") are excluded from ENGLISH_MARKERS.
        # Requiring >= 2 hits instead demoted real English such as
        # "have a nice day everyone" (1 hit) and the adapter suite's
        # "phase2-sentinel-42 hello there" (1 hit) to 'und'.
        if english_hits >= 1:
            return {"code": "en", "name": LANG_NAMES["en"], "script": "Latin"}
        # Latin script alone can not identify a language (C-F-2): Spanish /
        # Swahili / ... used to be silently labelled "en".  With no English
        # evidence - and a lone weak Tanglish marker (C-F-4) - the text is
        # reported as unknown Latin so the caller uses the conservative
        # fallback path instead of the English model.
        return {"code": "und", "name": LANG_NAMES["und"], "script": "Latin"}
    return {"code": "und", "name": "Unknown", "script": "Unknown"}


# ---------------------------------------------------------------------------
# Lexicon loading (graceful when files are missing or malformed)
# ---------------------------------------------------------------------------
_CODE_ALIAS = {
    "tanglish": "ta-Latn",
    "ta-latn": "ta-Latn",
    "ta_latn": "ta-Latn",
    "roman-tamil": "ta-Latn",
    "roman_tamil": "ta-Latn",
    "english": "en",
    "tamil": "ta",
    "hindi": "hi",
    "telugu": "te",
    "malayalam": "ml",
    "kannada": "kn",
    "bengali": "bn",
    "marathi": "mr",
    "gujarati": "gu",
    "punjabi": "pa",
    "urdu": "ur",
}


def norm_code(code):
    """Normalise a language code / file stem / language name to a known code."""
    raw = str(code or "").strip()
    if not raw:
        return ""
    if raw in KNOWN_CODES:
        return raw
    low = raw.lower()
    if low in _CODE_ALIAS:
        return _CODE_ALIAS[low]
    if low in KNOWN_CODES:
        return low
    return raw


def _code_for(stem, payload):
    code = norm_code(stem)
    if code in KNOWN_CODES and code != "und":
        return code
    if isinstance(payload, dict):
        code = norm_code(payload.get("language"))
        if code in KNOWN_CODES and code != "und":
            return code
    return None


def _stamp():
    try:
        if not LEXICON_DIR.is_dir():
            return ()
        entries = []
        for path in sorted(LEXICON_DIR.glob("*.json")):
            st = path.stat()
            entries.append((path.name, st.st_mtime_ns, st.st_size))
        return tuple(entries)
    except OSError:
        return ()


_CACHE = {"stamp": None, "data": None}


def load_lexicons():
    """Read every lexicon file under ``data/lexicons`` (cached by file stamp)."""
    stamp = _stamp()
    cached = _CACHE.get("data")
    if cached is not None and _CACHE.get("stamp") == stamp:
        return cached
    data = {}
    for name, _mtime, _size in stamp:
        path = LEXICON_DIR / name
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        code = _code_for(path.stem, payload)
        if code is None:
            continue
        clean = {}
        categories = payload.get("categories")
        if isinstance(categories, dict):
            for cat in CATEGORIES:
                values = categories.get(cat)
                if isinstance(values, (list, tuple)):
                    terms = [str(v).strip() for v in values if str(v or "").strip()]
                    if terms:
                        clean[cat] = terms
        data[code] = {
            "language": code,
            "language_name": str(payload.get("language_name") or LANG_NAMES.get(code, "Unknown")),
            "script": str(payload.get("script") or SCRIPT_BY_LANG.get(code, "Unknown")),
            "categories": clean,
        }
    _CACHE["stamp"] = stamp
    _CACHE["data"] = data
    return data


def lexicon_available(code):
    """True when a lexicon file for ``code`` loads successfully."""
    return norm_code(code) in load_lexicons()


# ---------------------------------------------------------------------------
# Boundary-safe term matching
# ---------------------------------------------------------------------------
# Python's re has no \p{L}, so the token boundary class is written explicitly:
# ASCII + Latin-1/Extended-A letters, the Indic blocks and Arabic.
_WORD_CLASS = r"0-9A-Za-z\u00C0-\u024F\u0900-\u0D7F\u0A00-\u0BFF\u0600-\u06FF"
_TOKEN_RE = re.compile(r"[^%s]+" % _WORD_CLASS)
_FRAG_RE = re.compile(r"(?<![%s])(?:[a-z][^\w]+){2,}[a-z](?![%s])" % (_WORD_CLASS, _WORD_CLASS))
_NON_ALNUM_RE = re.compile(r"[^0-9a-z]+")
_STRIPPABLE = " \t\r\n'\"‘’“”.,!?;:()[]{}<>/\\|-_…·"

_PAT_CACHE = {}
# Split only on the punctuation above (never on combining marks such as the
# Tamil pulli U+0BCD, which \W would treat as a non-word character).
_STRIPPABLE_RE = re.compile("[" + re.escape(_STRIPPABLE) + "]+")


def _clean_term(term):
    return normalize(term).strip(_STRIPPABLE)


def _term_pattern(cleaned):
    pat = _PAT_CACHE.get(cleaned, False)
    if pat is False:
        words = [w for w in _STRIPPABLE_RE.split(cleaned) if w]
        if not words:
            pat = None
        else:
            body = r"[\s\W]*".join(re.escape(w) for w in words)
            try:
                pat = re.compile(r"(?<![%s])%s(?![%s])" % (_WORD_CLASS, body, _WORD_CLASS))
            except re.error:
                pat = None
        _PAT_CACHE[cleaned] = pat
    return pat


BASE_SCORES = {
    "insult": 0.85,
    "threat": 0.90,
    "obscene": 0.80,
    "identity_hate": 0.75,
    "severe_toxic": 0.95,
}


def match(text, lang_code):
    """Match ``text`` against the lexicon of ``lang_code``.

    Returns category scores in 0..1, the matched lexicon terms and the matched
    categories.  With no hits (or no lexicon file) every category is 0.0 and
    ``toxic`` is the neutral 0.05.
    """
    code = norm_code(lang_code)
    lex = load_lexicons().get(code)
    neutral = {cat: 0.0 for cat in CATEGORIES}
    neutral["toxic"] = 0.05
    if not isinstance(lex, dict):
        return {"category_scores": neutral, "matched_terms": [], "matched_categories": []}

    ntext = normalize(text)
    rawtext = normalize(text, collapse_runs=False)
    hits = {cat: [] for cat in CATEGORIES}
    # normalised single-word term -> [(lexicon term, category), ...]
    term_index = {}

    def record(cat, term):
        if term not in hits[cat]:
            hits[cat].append(term)

    categories = lex.get("categories") or {}
    for cat in CATEGORIES:
        for term in categories.get(cat) or []:
            cleaned = _clean_term(term)
            if not cleaned:
                continue
            pat = _term_pattern(cleaned)
            if pat is not None and pat.search(ntext):
                record(cat, term)
            if " " not in cleaned and not _STRIPPABLE_RE.search(cleaned):
                term_index.setdefault(cleaned, []).append((term, cat))

    if term_index:
        # Repeated characters: "stuuuupid" -> "stupid" (only for 3+ runs, so
        # ordinary doubles such as "good" or "cool" are never rewritten).
        for token in _TOKEN_RE.split(rawtext):
            if len(token) >= 4 and _RUN3.search(token):
                squashed = _RUN1.sub(r"\1", token)
                if squashed != token:
                    for term, cat in term_index.get(squashed, ()):
                        record(cat, term)
        # Spaced / punctuated single letters: "f u c k", "f.u.c.k" -> "fuck".
        # Only accepted when the joined form really is a lexicon term.
        for m in _FRAG_RE.finditer(ntext):
            joined = _NON_ALNUM_RE.sub("", m.group(0))
            if not joined:
                continue
            for term, cat in term_index.get(joined, ()):
                record(cat, term)

    matched_terms = []
    matched_categories = []
    for cat in CATEGORIES:
        if not hits[cat]:
            continue
        matched_categories.append(cat)
        for term in hits[cat]:
            if term not in matched_terms:
                matched_terms.append(term)

    if not matched_categories:
        return {"category_scores": neutral, "matched_terms": [], "matched_categories": []}

    scores = {cat: 0.0 for cat in CATEGORIES}
    for cat in matched_categories:
        if cat == "toxic":
            continue
        base = BASE_SCORES.get(cat, 0.80)
        extra = 0.05 * max(0, len(hits[cat]) - 1)
        scores[cat] = round(min(0.95, base + extra), 4)
    # Any category hit raises the umbrella "toxic" signal; two or more
    # distinct categories raise it a little further.
    scores["toxic"] = round(0.95 if len(matched_categories) >= 2 else 0.90, 4)
    return {
        "category_scores": scores,
        "matched_terms": matched_terms,
        "matched_categories": matched_categories,
    }
