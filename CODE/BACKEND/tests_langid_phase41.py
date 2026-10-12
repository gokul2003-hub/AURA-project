#!/usr/bin/env python3
"""AURA language-detection phase 4.1 tests (C-F-2 + C-F-4).

Stdlib only (no pytest).  Run with:

    .venv\\Scripts\\python.exe tests_langid_phase41.py

Covers, via mlexicon.detect():
  1. ordinary English            -> en
  2. Spanish (Latin, unsupported) -> NOT confidently en (und)
  3. Swahili (Latin, unsupported) -> NOT confidently en (und)
  4. Tamil script                 -> ta
  5. Tanglish (>= 2 markers)      -> ta-Latn, not en
  6. ambiguous short Latin string -> not en, not ta-Latn (und)
  7. mixed-script input           -> deterministic, never a confident en
  8. empty / 1-char input         -> no crash, und, never scored toxic

Exit code 0 only when every case passes.
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_DIR))

import mlexicon  # noqa: E402

RESULTS = []


def check(name, condition, detail=""):
    RESULTS.append((name, bool(condition), str(detail)))
    status = "PASS" if condition else "FAIL"
    extra = f"  [{detail}]" if detail else ""
    print(f"  {status}  {name}{extra}")


def code_of(text):
    return mlexicon.detect(text)["code"]


def main():
    print("AURA language-detection phase 4.1 (C-F-2 unsupported Latin, C-F-4 Tanglish)")
    print()

    # -- 1) ordinary English must stay 'en' --------------------------------
    print("[1] ordinary English -> en")
    for text in (
        "Hello, how are you today?",
        "The class was held in the basement.",
        "You are stupid and useless, I hate you.",
        "I will find you and hurt you tomorrow.",
        "The weather is nice today, let us go for a walk.",
        "Thank you for your help with the project.",
        "Hello friends, have a great day.",
        "You are a worthless moron, go to hell.",
        "hello my friend",
    ):
        check(f"English sentence -> en", code_of(text) == "en", ascii(text[:40]))

    # -- 2) Spanish: Latin script but NOT supported -> unknown, not en ----
    print("[2] Spanish -> NOT confidently en")
    for text in (
        "hola amigo que tal estas hoy",
        "El coche rojo es muy bonito y rapido.",
        "Buenos dias, espero que tengas un buen dia.",
    ):
        check("Spanish sentence -> und (not en)", code_of(text) == "und", ascii(text[:40]))

    # -- 3) Swahili: Latin script but NOT supported -> unknown, not en ----
    print("[3] Swahili -> NOT confidently en")
    for text in (
        "habari yako wewe ni mjinga sana kabisa",
        "Habari za asubuhi, ninafurahi kukutana nawe.",
        "Wote walifurahi sana kwa mfano huu.",
    ):
        check("Swahili sentence -> und (not en)", code_of(text) == "und", ascii(text[:40]))

    # -- 4) Tamil script -> ta ---------------------------------------------
    print("[4] Tamil script -> ta")
    for text in (
        "\u0ba8\u0bc0 \u0b8e\u0baa\u0bcd\u0baa\u0b9f\u0bbf \u0b87\u0bb0\u0bc1\u0b95\u0bcd\u0b95\u0bbf\u0bb1\u0bbe\u0baf\u0bcd",
        "\u0ba8\u0bb2\u0bcd \u0ba8\u0bb2\u0bcd",
        "\u0b95\u0bae\u0bb2\u0bcd \u0ba8\u0bb2\u0bcd \u0b95\u0bbf\u0b9f\u0bc1\u0bae\u0bcd",
    ):
        check("Tamil script -> ta", code_of(text) == "ta", ascii(text[:20]))

    # -- 5) Tanglish -> ta-Latn (never collapsed to en) --------------------
    print("[5] Tanglish/romanised Tamil -> ta-Latn, not en")
    for text in (
        "nee epdi iruka? naan nalla iruken.",
        "nee vera level mudhalai, unnai verukkiren",
        "nee kuppa payyan, yarum unna virumbala.",  # markers: nee + unna
    ):
        got = code_of(text)
        check("Tanglish sentence -> ta-Latn", got == "ta-Latn", ascii(text[:40]))

    # -- 6) ambiguous short Latin string -----------------------------------
    print("[6] ambiguous short Latin string -> und, not en/ta-Latn")
    for text in ("muttal", "ok", "xq", "semma", "vera level"):
        got = code_of(text)
        check(
            "single/ambiguous marker -> not en, not ta-Latn",
            got not in ("en", "ta-Latn"),
            f"{ascii(text)} -> {got}",
        )

    # -- 7) mixed-script input ---------------------------------------------
    print("[7] mixed-script input")
    mixed_ta_en = "\u0ba8\u0bc0 hello \u0b95\u0bbf\u0b9f\u0bc1\u0bae\u0bcd"       # Tamil + Latin
    mixed_ta_te = "\u0ba8\u0bc0 \u0c28\u0c47\u0c28\u0c41"                        # Tamil + Telugu
    got = code_of(mixed_ta_en)
    check("Tamil+Latin (mostly Tamil) -> ta, not en", got == "ta", got)
    got = code_of(mixed_ta_te)
    check("Tamil+Telugu -> und (Mixed), not en", got == "und", got)

    # -- 8) empty / 1-char input: no crash, never toxic --------------------
    print("[8] empty / 1-char input")
    for text in ("", " ", "a", "\u0bcd"):
        try:
            det = mlexicon.detect(text)
            m = mlexicon.match(text, det["code"])
            toxic = float((m.get("category_scores") or {}).get("toxic", 1.0))
            # Never crashes, never matches a lexicon term, never scored
            # toxic.  Pure-whitespace/empty -> und; a single Tamil combining
            # mark is genuinely Tamil script (ta) - that is fine.
            ok = (
                det["code"] in ("und", "ta")
                and not m.get("matched_categories")
                and toxic <= 0.05
            )
            check(
                "empty/short input -> no crash + not toxic",
                ok,
                f"{ascii(text)} -> {det['code']}, toxic={toxic}",
            )
        except Exception as exc:  # pragma: no cover
            check("empty/short input -> und + not toxic", False, f"{ascii(text)} raised {exc!r}")

    passed = sum(1 for _, ok, _ in RESULTS if ok)
    failed = len(RESULTS) - passed
    print()
    print(f"SUMMARY: PASSED {passed} / FAILED {failed}  (of {len(RESULTS)} checks)")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
