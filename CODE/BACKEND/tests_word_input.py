"""AURA word-level / text-identification edge-case test suite.

Covers Phase 5 requirements: single word, short phrase, sentence/paragraph,
case variants, whitespace/punctuation/numbers/empty input, misspellings,
multilingual Unicode, and batch input.

Stdlib only. Reads AURA_BASE_URL (default http://127.0.0.1:8010).
Exit codes: 0 = all pass, 1 = failures, 2 = backend unreachable.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("AURA_BASE_URL", "http://127.0.0.1:8010").rstrip("/")
ADMIN_USER = os.environ.get("AURA_USER", "admin")
ADMIN_PASS = os.environ.get("AURA_PASS", "Admin@1234")

PASS = 0
FAIL = 0
FAILURES = []


def note(ok: bool, name: str, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"PASS  {name}" + (f"  ({detail})" if detail else ""))
    else:
        FAIL += 1
        FAILURES.append(name)
        print(f"FAIL  {name}  {detail}")


def post(path: str, data: dict, token: str | None = None, timeout: int = 20):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(BASE + path, data=json.dumps(data).encode(),
                                 headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode())
        except Exception:
            body = {}
        return e.code, body
    except Exception as e:  # network / timeout
        return -1, {"detail": str(e)}


def login() -> str:
    st, body = post("/auth/login", {"username": ADMIN_USER, "password": ADMIN_PASS})
    if st != 200:
        raise SystemExit(f"login failed: HTTP {st} {body}")
    return body.get("token") or body.get("access_token")


PREDICTABLE = {"language_code", "overall_label", "processing_mode", "confidence",
               "score", "categories"}


def predict(text, token, expect_status=200):
    """POST /predict; returns (status, body)."""
    return post("/predict", {"text": text}, token)


def check_contract(name, st, body, token):
    if st != 200:
        note(False, name, f"HTTP {st} {str(body)[:160]}")
        return None
    missing = PREDICTABLE - set(body)
    note(not missing, name, (f"missing={missing}" if missing else
         f"lang={body.get('language_code')} label={body.get('overall_label')} "
         f"mode={body.get('processing_mode')} conf={body.get('confidence')} "
         f"score={body.get('score')}"))
    return body


def main() -> int:
    print(f"== AURA word/text input suite against {BASE} ==")
    try:
        with urllib.request.urlopen(BASE + "/health", timeout=8) as r:
            if json.loads(r.read().decode()).get("status") != "healthy":
                print("backend unhealthy"); return 2
    except Exception as e:
        print(f"backend unreachable: {e}"); return 2

    token = login()
    print("login OK\n-- single word --")

    # 1. Single neutral word
    b = check_contract("word_hello", *predict("hello", token), token)
    if b:
        note(b.get("overall_label") == "non_toxic", "word_hello_nontoxic",
             f"label={b.get('overall_label')}")

    # 2. Single mild-toxic English word (lexicon term)
    b = check_contract("word_idiot", *predict("idiot", token), token)
    if b:
        note(b.get("overall_label") == "toxic" or (b.get("score") or 0) > 0.2,
             "word_idiot_flagged",
             f"label={b.get('overall_label')} score={b.get('score')} "
             f"terms={b.get('toxic_terms')}")

    # 3. Single strong English toxic word
    b = check_contract("word_threat", *predict("I will hurt you", token), token)
    if b:
        note(b.get("overall_label") == "toxic", "sentence_threat_toxic",
             f"label={b.get('overall_label')}")

    # 4. Short phrase
    check_contract("phrase_good_morning", *predict("good morning", token), token)

    # 5. Full sentence + paragraph
    check_contract("sentence", *predict(
        "The meeting is scheduled for tomorrow at ten in the morning.", token), token)
    check_contract("paragraph", *predict(
        "Climate policy debates often grow heated. Still, participants should "
        "argue from evidence and treat one another with basic courtesy, because "
        "public trust depends on how disagreements are conducted and whether "
        "facts are allowed to settle the question.", token), token)

    print("-- case / whitespace / punctuation / numbers --")
    for name, text in [
        ("upper", "HELLO THERE"),
        ("mixed", "HeLLo wORld"),
        ("lead_trail_spaces", "   hello   "),
        ("punctuation", "hello!!!"),
        ("numbers_only", "12345"),
        ("emoji", "hello \U0001F600"),
        ("only_symbols", "!!!???..."),
    ]:
        b = check_contract(name, *predict(text, token), token)
        if b and name == "lead_trail_spaces":
            note(b.get("text", "").strip() == b.get("text", ""), "spaces_normalized",
                 repr(b.get("text")))

    print("-- empty / invalid --")
    st, body = predict("", token)
    note(st == 400 and bool(body.get("detail")), "empty_400",
         f"HTTP {st} {str(body)[:90]}")
    st, body = predict("    ", token)
    note(st == 400, "whitespace_only_400", f"HTTP {st}")
    st, body = predict(None, token)
    note(st in (400, 422), "null_400_or_422", f"HTTP {st}")

    print("-- misspelled / unfamiliar --")
    b = check_contract("misspelled", *predict("yuo are a stupiid idot", token), token)
    check_contract("unfamiliar", *predict("zorblatt quixen frobnicate", token), token)

    print("-- multilingual single words / sentences --")
    for name, text, want_lang in [
        ("hi_word", "नमस्ते", "hi"),
        ("ta_word", "முட்டை", "ta"),
        ("ta_toxic_word", "முட்டாள்", "ta"),
        ("ur_word", "السلام علیکم", "ur"),
        ("bn_word", "শুভ সকাল", "bn"),
        ("mixed_script", "hello உலகம", None),
        ("unsupported_zh", "你好世界", None),
    ]:
        b = check_contract(name, *predict(text, token), token)
        if b and want_lang:
            note(b.get("language_code") == want_lang, f"{name}_lang",
                 f"got={b.get('language_code')}")
        if b and name == "ta_toxic_word":
            note(b.get("overall_label") == "toxic" or (b.get("score") or 0) > 0.2,
                 "ta_toxic_word_flagged",
                 f"label={b.get('overall_label')} score={b.get('score')}")

    print("-- batch input --")
    st, body = post("/predict/batch", {"comments": [
        "hello", "good morning", "you are an idiot", "नमस्ते", "முட்டாள்",
        "12345"]}, token)
    if st == 200:
        res = body.get("results", [])
        note(len(res) == 6, "batch_count", f"count={body.get('count')}")
        note(all(PREDICTABLE <= set(x) for x in res), "batch_contract",
             "all items carry contract fields" if res else "empty results")
        langs = sorted({x.get("language_code") for x in res})
        note("ta" in langs and "hi" in langs and "en" in langs,
             "batch_multilingual", f"langs={langs}")
    else:
        note(False, "batch_predict", f"HTTP {st} {str(body)[:160]}")

    # batch with an empty item must fail clearly (validation preserved)
    st, body = post("/predict/batch", {"comments": ["hello", ""]}, token)
    note(st == 400 and "empty" in str(body.get("detail", "")).lower(),
         "batch_empty_item_400", f"HTTP {st} {str(body)[:110]}")

    # oversized batch
    st, body = post("/predict/batch", {"comments": ["x"] * 501}, token)
    note(st == 400, "batch_too_large_400", f"HTTP {st}")

    # duplicate rapid requests (idempotent behaviour, no 5xx)
    codes = [post("/predict", {"text": "hello again"}, token)[0] for _ in range(5)]
    note(all(c == 200 for c in codes), "duplicate_requests", f"codes={codes}")

    # very large input
    st, body = predict("hello " * 20000, token)
    note(st in (200, 400, 413), "large_input_no_5xx", f"HTTP {st}")

    print(f"\nWORD-INPUT SUMMARY: PASSED {PASS} / FAILED {FAIL}")
    if FAILURES:
        print("failures:", ", ".join(FAILURES))
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
