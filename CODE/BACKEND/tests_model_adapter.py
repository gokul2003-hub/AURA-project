"""AURA Phase 2 — pretrained model adapter test suite.

Covers the Phase 2 contract end to end:
  1. Engine admin endpoints (auth 401/403, validation 400/422, GET shape).
  2. Legacy backward compatibility (unchanged contract, no toxicity_score).
  3. Switch to hf -> model prediction contract + adapter info sanitisation.
  4. Loading/caching (single load, load_ms stable, warm predict fast).
  5. Per-language word + sentence across the 6 evaluated groups
     (en, ta, ta-Latn, hi, bn, ur) with tuned per-language thresholds.
  6. Unmeasured language (te) -> experimental / unmeasured / HUMAN_REVIEW.
  7. Batch behaviour + empty/oversized/oversize-batch limits under hf.
  8. SQLite persistence of model decisions (history API + direct DB read).
  9. auto engine gating (te -> legacy, en/ta -> model).
 10. Clean fallback: second instance with an unloadable model -> 200,
     decision_status='fallback', sanitised model_error, no stack traces.
 11. In-process failure backoff (2nd failure is fast) + pre-load validation.
 12. Restore legacy engine and verify.

Stdlib only. Reads AURA_BASE_URL (default http://127.0.0.1:8010).
Exit codes: 0 = all pass, 1 = failures, 2 = backend unreachable.
The suite ALWAYS restores the legacy engine before exiting (finally block).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

BASE = os.environ.get("AURA_BASE_URL", "http://127.0.0.1:8010").rstrip("/")
ADMIN_USER = os.environ.get("AURA_USER", "admin")
ADMIN_PASS = os.environ.get("AURA_PASS", "Admin@1234")
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BACKEND_DIR, "aura.db")

PASS = 0
FAIL = 0
FAILURES = []

MODEL_LEGACY_NAME = "aura-legacy-rules-lexicon"
MODEL_MODES = ("legacy", "auto", "hf")
HUMAN_ACTIONS = ("HUMAN_REVIEW", "RESTRICT", "TEMPORARY_BLOCK")

# word + sentence samples (language detection verified against mlexicon)
GROUPS = [
    ("en", "hello", "You are stupid and useless, I hate you."),
    ("ta", "முட்டாள்",
     "\u0ba8\u0bc0 \u0b92\u0bb0\u0bc1 \u0bae\u0bc1\u0b9f\u0bcd\u0b9f\u0bbe\u0bb3\u0bcd, \u0b89\u0ba9\u0bc8 \u0bb5\u0bc6\u0bb1\u0bc1\u0b95\u0bcd\u0b95\u0bbf\u0bb1\u0bc7\u0ba9\u0bcd."),
    ("ta-Latn", "nee muttal", "nee vera level mudhalai, unnai verukkiren"),
    ("hi", "\u092c\u0947\u0935\u0915\u0942\u092b",
     "\u0924\u0941\u092e \u092c\u0939\u0941\u0924 \u092c\u0947\u0935\u0915\u0942\u092b \u0939\u094b, \u092e\u0948\u0902 \u0924\u0941\u092e\u0938\u0947 \u0928\u092b\u0930\u0924 \u0915\u0930\u0924\u093e \u0939\u0942\u0901."),
    ("bn", "\u09ac\u09cb\u0995\u09be",
     "\u09a4\u09c1\u09ae\u09bf \u098f\u0995\u099c\u09a8 \u09ac\u09cb\u0995\u09be, \u0986\u09ae\u09bf \u09a4\u09cb\u09ae\u09be\u0995\u09c7 \u0998\u09cd\u09b0\u09a3\u09be \u0995\u09b0\u09bf\u0964"),
    ("ur", "\u0628\u0642\u0648\u0641",
     "\u062a\u0645 \u0627\u06cc\u06a9 \u0628\u06cc\u0648\u0642\u0648\u0641 \u06c7\u062f\u0648\u060c \u0645\u06cc\u0646 \u062a\u0645 \u0633\u06d2 \u0646\u0641\u0631\u062a \u06a9\u0631\u062a\u0627 \u06c1\u0648\u0646\u060c"),
]
COVERAGE = {
    "en": "validated", "hi": "validated",
    "ta": "experimental", "ta-Latn": "experimental",
    "bn": "experimental", "ur": "experimental",
}
LATIN_GROUPS = {"en", "ta-Latn"}          # script cannot confirm -> None + script_ambiguous
SCRIPT_GROUPS = {"ta", "hi", "bn", "ur"}  # native script -> script_share in (0,1]
TE_SENTENCE = "నువువు ఒక పిచ్చివాడివి, నిన్ను ద్వేషిస్తున్నాను."

RAW_BODY = {}  # last raw response text per request, for sanitisation checks


def note(ok: bool, name: str, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"PASS  {name}" + (f"  ({detail})" if detail else ""))
    else:
        FAIL += 1
        FAILURES.append(name)
        print(f"FAIL  {name}  {detail}")


def request(method: str, path: str, data=None, token: str | None = None,
            timeout: int = 30):
    """HTTP request; returns (status, parsed_body)."""
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    body = None if data is None else json.dumps(data).encode()
    req = urllib.request.Request(BASE + path, data=body, headers=headers,
                                 method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            text = r.read().decode()
            RAW_BODY[path] = text
            try:
                return r.status, json.loads(text)
            except Exception:
                return r.status, {"_raw": text[:400]}
    except urllib.error.HTTPError as e:
        text = e.read().decode()
        RAW_BODY[path] = text
        try:
            return e.code, json.loads(text)
        except Exception:
            return e.code, {"_raw": text[:400]}
    except Exception as e:  # network / timeout
        return -1, {"detail": str(e)}


def get(path, token=None, timeout=30):
    return request("GET", path, None, token, timeout)


def post(path, data, token=None, timeout=30):
    return request("POST", path, data, token, timeout)


def login() -> str:
    st, body = post("/auth/login", {"username": ADMIN_USER, "password": ADMIN_PASS})
    if st != 200:
        raise SystemExit(f"login failed: HTTP {st} {body}")
    return body.get("token") or body.get("access_token")


def raw_for(path: str) -> str:
    return RAW_BODY.get(path, "")


def tuned_thresholds():
    """(per_language dict, global threshold) from models/tuned_threshold.json."""
    path = os.path.join(BACKEND_DIR, "models", "tuned_threshold.json")
    try:
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
        return dict(d.get("per_language") or {}), float(d.get("threshold") or 0.5)
    except Exception:
        return {}, 0.5


def deep_strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from deep_strings(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from deep_strings(v)


def no_internals(body) -> tuple[bool, str]:
    """No stack traces, no local filesystem paths in any string of the body."""
    for s in deep_strings(body):
        if "Traceback" in s or "File \"" in s:
            return False, "stack trace leaked"
        if re.search(r"[A-Za-z]:\\", s) or re.search(r"/(?:home|usr|var|tmp|Users|opt)/", s):
            return False, "filesystem path leaked"
    return True, ""


def db_value(key: str, tries: int = 4):
    """Read one settings value straight from aura.db (retry on lock)."""
    for i in range(tries):
        try:
            c = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=5)
            row = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            c.close()
            return row[0] if row else None
        except Exception:
            time.sleep(0.4 * (i + 1))
    return "__unreachable__"


def set_engine(token: str, mode: str, timeout: int = 15):
    return post("/models/engine", {"engine": mode}, token, timeout)


def engine_info(token: str):
    return get("/models/engine", token)


# ---------------------------------------------------------------------------
# 1) Engine admin endpoints — auth + validation + shape
# ---------------------------------------------------------------------------
def section_engine_admin(token: str) -> None:
    print("\n-- 1) engine admin endpoints --")
    st, body = get("/models/engine")
    note(st == 401, "engine_get_requires_auth", f"HTTP {st}")
    st, body = post("/models/engine", {"engine": "hf"})
    note(st == 401, "engine_post_requires_auth", f"HTTP {st}")

    # non-admin token (fresh registered user)
    stamp = str(int(time.time()) % 100000000)
    st, reg = post("/auth/register", {"username": "p2user_" + stamp,
                                      "password": "phase2pass"})
    if st != 200:
        note(False, "register_non_admin", f"HTTP {st} {str(reg)[:120]}")
        user_token = None
    else:
        user_token = reg.get("token") or reg.get("access_token")
        st, _ = get("/models/engine", user_token)
        note(st == 403, "engine_get_forbidden_for_user", f"HTTP {st}")
        st, _ = post("/models/engine", {"engine": "hf"}, user_token)
        note(st == 403, "engine_post_forbidden_for_user", f"HTTP {st}")

    # validation
    st, body = post("/models/engine", {"engine": "deepseek"}, token)
    note(st == 400, "engine_invalid_400", f"HTTP {st} {str(body)[:120]}")
    st, body = post("/models/engine", {"engine": ""})
    note(st in (400, 422), "engine_empty_400_or_422", f"HTTP {st}")
    st, body = post("/models/engine", {})
    note(st in (400, 422), "engine_missing_400_or_422", f"HTTP {st}")

    # normalise to legacy for the compatibility section (also proves persistence)
    st, body = set_engine(token, "legacy")
    note(st == 200 and body.get("engine") == "legacy", "engine_set_legacy",
         f"HTTP {st} {str(body)[:80]}")
    st, body = engine_info(token)
    note(st == 200 and body.get("engine") == "legacy" and body.get("source") == "settings",
         "engine_get_legacy_settings", f"HTTP {st} engine={body.get('engine')} "
         f"source={body.get('source')}")
    note(body.get("modes") == list(MODEL_MODES), "engine_modes",
         f"modes={body.get('modes')}")
    note(body.get("default") == "legacy", "engine_default_legacy",
         f"default={body.get('default')}")
    note(body.get("adapter_available") is True, "engine_adapter_available",
         f"adapter_available={body.get('adapter_available')}")
    cov = body.get("coverage") or {}
    got_cov = {k: (cov.get(k) or {}).get("status") for k in COVERAGE}
    ok_cov = all(got_cov[c] == COVERAGE[c] for c in COVERAGE)
    note(ok_cov, "engine_coverage_statuses", f"got={got_cov}")
    adapter = body.get("adapter") or {}
    note(isinstance(adapter, dict) and "cache_dir" not in adapter,
         "engine_adapter_info_sanitised",
         f"keys={sorted(adapter)[:8]}")

    # case normalisation
    st, body = set_engine(token, "HF")
    info_st, info = engine_info(token)
    note(st == 200 and body.get("engine") == "hf" and info.get("engine") == "hf",
         "engine_case_normalised", f"HTTP {st} engine={info.get('engine')}")
    set_engine(token, "legacy")


# ---------------------------------------------------------------------------
# 2) Legacy backward compatibility (default engine)
# ---------------------------------------------------------------------------
def section_legacy(token: str) -> None:
    print("\n-- 2) legacy backward compatibility --")
    st, b = post("/predict", {"text": "hello"}, token)
    if st != 200:
        note(False, "legacy_predict", f"HTTP {st} {str(b)[:160]}")
    else:
        required = {"language_code", "overall_label", "processing_mode",
                    "confidence", "score", "categories", "label", "threshold",
                    "model_name", "model_version", "decision_status",
                    "language_confidence", "language_confidence_kind"}
        missing = required - set(b)
        note(not missing, "legacy_contract_fields",
             f"missing={missing}" if missing else
             f"label={b.get('overall_label')} mode={b.get('processing_mode')}")
        note(b.get("model_name") == MODEL_LEGACY_NAME, "legacy_model_name",
             f"model_name={b.get('model_name')}")
        note(b.get("decision_status") == "legacy", "legacy_decision_status",
             f"decision_status={b.get('decision_status')}")
        note("toxicity_score" not in b, "legacy_no_toxicity_score",
             "toxicity_score absent under legacy")
        note(b.get("processing_mode") in ("existing_model", "language_lexicon",
                                          "fallback"),
             "legacy_processing_mode", f"mode={b.get('processing_mode')}")
        note(isinstance(b.get("threshold"), (int, float)) and 0 < b["threshold"] <= 1,
             "legacy_threshold", f"threshold={b.get('threshold')}")
        note(b.get("language_confidence_kind") in
             ("script_share", "script_ambiguous", "no_signal"),
             "legacy_language_confidence_kind",
             f"kind={b.get('language_confidence_kind')} "
             f"lc={b.get('language_confidence')}")

    st, b = post("/predict", {"text": "\u0ba8\u0bb2\u0bcd \u0ba8\u0bb2\u0bcd"}, token)
    note(st == 200 and b.get("processing_mode") == "language_lexicon"
         and b.get("decision_status") == "legacy"
         and "toxicity_score" not in b,
         "legacy_lexicon_language",
         f"HTTP {st} mode={b.get('processing_mode')} status={b.get('decision_status')}")

    # limits under legacy
    st, b = post("/predict", {"text": ""}, token)
    note(st == 400, "legacy_empty_400", f"HTTP {st} {str(b)[:100]}")
    st, b = post("/predict", {"text": "w" * 50000}, token, timeout=60)
    note(st not in (-1,) and st < 500, "legacy_oversized_no_5xx", f"HTTP {st}")
    st, b = post("/predict/batch", {"comments": []}, token)
    note(st == 400, "legacy_batch_empty_400", f"HTTP {st}")
    st, b = post("/predict/batch", {"comments": ["ok", ""]}, token)
    note(st == 400, "legacy_batch_blank_item_400", f"HTTP {st}")
    st, b = post("/predict/batch", {"comments": ["hi"] * 501}, token, timeout=60)
    note(st == 400, "legacy_batch_over_max_400", f"HTTP {st}")


# ---------------------------------------------------------------------------
# 3) Switch to hf — model prediction contract
# ---------------------------------------------------------------------------
def model_contract(name: str, st: int, body: dict, code: str,
                   expected_model: str | None, per_lang: dict, global_thr: float,
                   expect_status=("predicted", "uncertain"),
                   expect_coverage: str | None = None) -> dict | None:
    """Assert the full Phase 2 prediction contract for one /predict response."""
    if st != 200:
        note(False, name, f"HTTP {st} {str(body)[:160]}")
        return None
    expect_coverage = expect_coverage or COVERAGE.get(code, "unmeasured")
    problems = []
    required = {"language_code", "overall_label", "processing_mode", "confidence",
                "score", "categories", "label", "threshold", "toxicity_score",
                "model_name", "model_version", "decision_status", "model_coverage",
                "model_coverage_note", "language_confidence",
                "language_confidence_kind", "confidence_kind", "model_latency_ms"}
    missing = required - set(body)
    if missing:
        problems.append(f"missing={missing}")
    if body.get("processing_mode") != "pretrained_model":
        problems.append(f"mode={body.get('processing_mode')}")
    if body.get("confidence_kind") != "model":
        problems.append(f"confidence_kind={body.get('confidence_kind')}")
    if body.get("language_code") != code:
        problems.append(f"lang={body.get('language_code')}")
    if expected_model and body.get("model_name") != expected_model:
        problems.append(f"model_name={body.get('model_name')}")
    if not body.get("model_version"):
        problems.append("model_version empty")
    status = body.get("decision_status")
    if status not in expect_status:
        problems.append(f"status={status}")
    label = body.get("label")
    if label not in ("toxic", "non_toxic"):
        problems.append(f"label={label}")
    if body.get("overall_label") != label:
        problems.append(f"overall={body.get('overall_label')}")
    tox, thr = body.get("toxicity_score"), body.get("threshold")
    if not isinstance(tox, (int, float)) or not (0.0 <= tox <= 1.0):
        problems.append(f"tox={tox}")
    if not isinstance(thr, (int, float)) or not (0.0 < thr <= 1.0):
        problems.append(f"thr={thr}")
    else:
        want = per_lang.get(code, per_lang.get(str(code).split("-")[0], global_thr))
        if abs(float(thr) - float(want)) > 1e-6:
            problems.append(f"thr={thr} want={want}")
        # exact label-vs-threshold consistency (skip rounding-boundary window)
        if isinstance(tox, (int, float)) and abs(float(tox) - float(thr)) > 0.0002:
            if (float(tox) >= float(thr)) != (label == "toxic"):
                problems.append(f"label/score mismatch tox={tox} thr={thr}")
    if body.get("model_coverage") != expect_coverage:
        problems.append(f"coverage={body.get('model_coverage')}")
    if not str(body.get("model_coverage_note") or "").strip():
        problems.append("coverage note empty")
    cov = body.get("model_coverage")
    if cov in ("unmeasured", "model_card_claimed"):
        if status != "experimental":
            problems.append("unmeasured coverage must be experimental")
    elif status == "experimental":
        problems.append("measured coverage must not be experimental")
    if status == "experimental" and (body.get("decision") or {}).get("action") != "HUMAN_REVIEW":
        problems.append(f"action={((body.get('decision') or {}).get('action'))}")
    if status == "uncertain":
        act = (body.get("decision") or {}).get("action")
        if act not in HUMAN_ACTIONS:
            problems.append(f"uncertain action={act}")
    conf = body.get("confidence")
    if not isinstance(conf, (int, float)) or not (0.4 <= conf <= 1.0):
        problems.append(f"conf={conf}")
    elif isinstance(tox, (int, float)):
        if abs(float(conf) - max(float(tox), 1.0 - float(tox))) > 0.002:
            problems.append(f"conf={conf} vs tox={tox}")
    lat = body.get("model_latency_ms")
    if not isinstance(lat, (int, float)) or lat < 0:
        problems.append(f"latency={lat}")
    if code in LATIN_GROUPS:
        if body.get("language_confidence_kind") != "script_ambiguous" \
                or body.get("language_confidence") is not None:
            problems.append(f"lc_kind={body.get('language_confidence_kind')} "
                            f"lc={body.get('language_confidence')}")
    elif code in SCRIPT_GROUPS:
        lc = body.get("language_confidence")
        if body.get("language_confidence_kind") != "script_share" \
                or not isinstance(lc, (int, float)) or not (0 < lc <= 1):
            problems.append(f"lc_kind={body.get('language_confidence_kind')} lc={lc}")
    ok, why = no_internals(body)
    if not ok:
        problems.append(why)
    note(not problems, name,
         ("; ".join(problems) if problems else
          f"lang={code} label={label} tox={tox} thr={thr} status={status} "
          f"cov={cov} lc={body.get('language_confidence')}"))
    return body if not problems else None


def section_hf_switch(token: str) -> tuple[str | None, dict, float]:
    print("\n-- 3) switch to hf + model contract --")
    per_lang, global_thr = tuned_thresholds()
    note(bool(per_lang), "tuned_thresholds_readable",
         f"per_language={per_lang} global={global_thr}")
    st, body = set_engine(token, "hf", timeout=20)
    note(st == 200 and body.get("engine") == "hf", "engine_set_hf",
         f"HTTP {st} {str(body)[:80]}")
    st, info = engine_info(token)
    note(st == 200 and info.get("engine") == "hf" and info.get("source") == "settings",
         "engine_hf_persisted",
         f"engine={info.get('engine')} source={info.get('source')}")

    # first prediction may wait for the background warm-up load (cold ~24s)
    t0 = time.time()
    st, b = post("/predict",
                 {"text": "You are stupid and useless, I hate you."}, token,
                 timeout=240)
    elapsed = time.time() - t0
    body = model_contract("hf_first_predict_contract", st, b, "en", None,
                          per_lang, global_thr)
    print(f"      first hf predict took {elapsed:.1f}s "
          f"(load+inference, timeout budget 240s)")

    # adapter info (authoritative model id + load status + sanitisation)
    st, ad = get("/models/adapter", token)
    adapter = (ad or {}).get("adapter") or {}
    note(st == 200 and isinstance(adapter, dict), "adapter_info_http",
         f"HTTP {st}")
    note(adapter.get("status") in ("ready", "loading"), "adapter_status_ready",
         f"status={adapter.get('status')} error={adapter.get('error')}")
    note(bool(adapter.get("weights_available")) or adapter.get("status") == "loading",
         "adapter_weights_available", f"weights={adapter.get('weights_available')}")
    note("cache_dir" not in adapter, "adapter_cache_dir_hidden",
         f"keys={sorted(adapter)[:10]}")
    clean, why = no_internals(adapter)
    note(clean, "adapter_info_no_internals", why)
    model_id = adapter.get("model_id")
    note(bool(model_id), "adapter_model_id", f"model_id={model_id}")
    groups = ((ad or {}).get("benchmark") or {}).get("groups") or {}
    note(len(groups) >= 6, "adapter_benchmark_groups",
         f"groups={sorted(groups)}")
    note("ta" not in ((ad or {}).get("claimed_languages") or ["ta"]),
         "claimed_languages_excludes_ta",
         f"claimed_has_ta={'ta' in ((ad or {}).get('claimed_languages') or [])}")
    # model_name from the response must match the adapter's model id
    if body and model_id and body.get("model_name") != model_id:
        note(False, "model_name_matches_adapter",
             f"resp={body.get('model_name')} adapter={model_id}")
    elif body:
        note(True, "model_name_matches_adapter", f"model_id={model_id}")
    return model_id, per_lang, global_thr


# ---------------------------------------------------------------------------
# 4) Loading / caching — single load, warm predicts fast
# ---------------------------------------------------------------------------
def section_loading_cache(token: str, model_id: str | None,
                          per_lang: dict, global_thr: float) -> None:
    print("\n-- 4) loading / caching --")
    st, ad1 = get("/models/adapter", token)
    load1 = ((ad1.get("adapter") or {}).get("load_ms")
             if st == 200 else None)
    t0 = time.time()
    st, b = post("/predict", {"text": "hello"}, token, timeout=60)
    warm = time.time() - t0
    note(st == 200 and warm < 10.0, "warm_predict_fast",
         f"HTTP {st} took {warm:.2f}s")
    st, ad2 = get("/models/adapter", token)
    load2 = ((ad2.get("adapter") or {}).get("load_ms")
             if st == 200 else None)
    note(isinstance(load1, (int, float)) and load1 > 0
         and load1 == load2, "load_ms_stable_no_reload",
         f"load_ms {load1} -> {load2}")
    model_contract("warm_predict_contract", st if st == 200 else 200, b, "en",
                   model_id, per_lang, global_thr)
    if st == 200:
        note((b.get("model_latency_ms") or 0) < 10000, "model_latency_sane",
             f"latency_ms={b.get('model_latency_ms')}")


# ---------------------------------------------------------------------------
# 5) Per-language word + sentence across the 6 evaluated groups
# ---------------------------------------------------------------------------
def section_per_language(token: str, model_id: str | None,
                         per_lang: dict, global_thr: float) -> None:
    print("\n-- 5) per-language word + sentence (6 evaluated groups) --")
    for code, word, sentence in GROUPS:
        for kind, text in (("word", word), ("sentence", sentence)):
            st, b = post("/predict", {"text": text}, token, timeout=60)
            model_contract(f"hf_{code}_{kind}", st, b, code, model_id,
                           per_lang, global_thr,
                           expect_coverage=COVERAGE[code])


# ---------------------------------------------------------------------------
# 6) Unmeasured language under hf -> experimental / unmeasured / human review
# ---------------------------------------------------------------------------
def section_unmeasured(token: str, model_id: str | None,
                       per_lang: dict, global_thr: float) -> None:
    print("\n-- 6) unmeasured language gating (te) --")
    st, b = post("/predict", {"text": TE_SENTENCE}, token, timeout=60)
    body = model_contract("hf_te_experimental", st, b, "te", model_id,
                          per_lang, global_thr,
                          expect_status=("experimental",),
                          expect_coverage="unmeasured")
    if body:
        note((body.get("decision") or {}).get("action") == "HUMAN_REVIEW",
             "hf_te_human_review",
             f"action={(body.get('decision') or {}).get('action')}")
        note(body.get("model_coverage_note") is not None,
             "hf_te_coverage_note", str(body.get("model_coverage_note"))[:80])


# ---------------------------------------------------------------------------
# 7) Batch + limits under hf
# ---------------------------------------------------------------------------
def section_batch_limits(token: str, model_id: str | None,
                         per_lang: dict, global_thr: float) -> None:
    print("\n-- 7) batch + input limits under hf --")
    comments = ["hello world",
                "\u0ba8\u0bc0 \u0b92\u0bb0\u0bc1 \u0bae\u0bc1\u0b9f\u0bcd\u0b9f\u0bbe\u0bb3\u0bcd",
                "\u0924\u0941\u092e \u092c\u0939\u0941\u0924 \u092c\u0947\u0935\u0915\u0942\u092b \u0939\u094b"]
    st, b = post("/predict/batch", {"comments": comments}, token, timeout=180)
    if st != 200:
        note(False, "hf_batch_http", f"HTTP {st} {str(b)[:160]}")
        return
    note(b.get("count") == 3, "hf_batch_count", f"count={b.get('count')}")
    rows = b.get("results") or []
    want_codes = ["en", "ta", "hi"]
    for i, (row, want) in enumerate(zip(rows, want_codes)):
        problems = []
        if row.get("language_code") != want:
            problems.append(f"lang={row.get('language_code')}")
        if row.get("processing_mode") != "pretrained_model":
            problems.append(f"mode={row.get('processing_mode')}")
        if row.get("decision_status") not in ("predicted", "uncertain"):
            problems.append(f"status={row.get('decision_status')}")
        if not isinstance(row.get("toxicity_score"), (int, float)):
            problems.append("toxicity_score missing")
        if model_id and row.get("model_name") != model_id:
            problems.append(f"model_name={row.get('model_name')}")
        thr = row.get("threshold")
        if not isinstance(thr, (int, float)):
            problems.append("threshold missing")
        else:
            want_thr = per_lang.get(want, global_thr)
            if abs(float(thr) - float(want_thr)) > 1e-6:
                problems.append(f"thr={thr} want={want_thr}")
        if row.get("label") not in ("toxic", "non_toxic"):
            problems.append(f"label={row.get('label')}")
        if "language_confidence_kind" not in row:
            problems.append("language_confidence_kind missing")
        if row.get("model_coverage") != COVERAGE[want]:
            problems.append(f"coverage={row.get('model_coverage')}")
        note(not problems, f"hf_batch_item{i}_{want}",
             "; ".join(problems) or f"status={row.get('decision_status')} "
             f"tox={row.get('toxicity_score')} thr={row.get('threshold')}")
    clean, why = no_internals(b)
    note(clean, "hf_batch_no_internals", why)

    # limits under hf (validation must stay fast and never 5xx)
    st, _ = post("/predict", {"text": ""}, token, timeout=60)
    note(st == 400, "hf_empty_400", f"HTTP {st}")
    st, _ = post("/predict", {"text": "w" * 50000}, token, timeout=120)
    note(st != -1 and st < 500, "hf_oversized_no_5xx", f"HTTP {st}")
    st, _ = post("/predict/batch", {"comments": []}, token)
    note(st == 400, "hf_batch_empty_400", f"HTTP {st}")
    st, _ = post("/predict/batch", {"comments": ["ok", ""]}, token, timeout=60)
    note(st == 400, "hf_batch_blank_item_400", f"HTTP {st}")
    st, _ = post("/predict/batch", {"comments": ["hi"] * 501}, token, timeout=60)
    note(st == 400, "hf_batch_over_max_400", f"HTTP {st}")


# ---------------------------------------------------------------------------
# 8) SQLite persistence — history API + direct DB read
# ---------------------------------------------------------------------------
def section_persistence(token: str, model_id: str | None,
                        per_lang: dict, global_thr: float) -> None:
    print("\n-- 8) SQLite persistence --")
    sentinel = "phase2-sentinel-42 hello there"
    st, b = post("/predict", {"text": sentinel}, token, timeout=60)
    if st != 200:
        note(False, "persist_sentinel_predict", f"HTTP {st}")
        return
    note(b.get("processing_mode") == "pretrained_model"
         and b.get("decision_status") in ("predicted", "uncertain"),
         "persist_sentinel_contract",
         f"mode={b.get('processing_mode')} status={b.get('decision_status')}")

    st, hist = get("/history?q=phase2-sentinel-42&limit=20", token)
    row = None
    if st == 200 and isinstance(hist, list):
        for r in hist:
            if "phase2-sentinel-42" in str(r.get("message") or ""):
                row = r
                break
    note(row is not None, "persist_history_row_found", f"HTTP {st}")
    if row:
        note(row.get("processing_mode") == "pretrained_model",
             "persist_history_mode", f"mode={row.get('processing_mode')}")
        res = row.get("result") or {}
        note(res.get("decision_status") in ("predicted", "uncertain")
             and (model_id is None or res.get("model_name") == model_id)
             and isinstance(res.get("toxicity_score"), (int, float))
             and "threshold" in res,
             "persist_history_result_fields",
             f"status={res.get('decision_status')} model={res.get('model_name')} "
             f"tox={res.get('toxicity_score')} thr={res.get('threshold')}")

    # direct DB read: settings row + stored result_json
    eng = db_value("prediction_engine")
    note(eng == "hf", "persist_settings_row_hf", f"prediction_engine={eng}")
    found = None
    for _ in range(4):
        try:
            c = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=5)
            rj = c.execute(
                "SELECT result_json FROM moderation_results WHERE message LIKE ? "
                "ORDER BY id DESC LIMIT 1", ("%phase2-sentinel-42%",)).fetchone()
            c.close()
            found = rj[0] if rj else None
            break
        except Exception:
            time.sleep(0.4)
    if not found:
        note(False, "persist_db_result_json", "sentinel row not found in aura.db")
    else:
        try:
            res = json.loads(found)
        except Exception:
            res = {}
        note(res.get("decision_status") in ("predicted", "uncertain")
             and res.get("processing_mode") == "pretrained_model"
             and isinstance(res.get("toxicity_score"), (int, float))
             and res.get("model_coverage") in ("validated", "experimental"),
             "persist_db_model_fields",
             f"status={res.get('decision_status')} mode={res.get('processing_mode')} "
             f"tox={res.get('toxicity_score')} cov={res.get('model_coverage')}")


# ---------------------------------------------------------------------------
# 9) auto engine gating
# ---------------------------------------------------------------------------
def section_auto(token: str, model_id: str | None,
                 per_lang: dict, global_thr: float) -> None:
    print("\n-- 9) auto engine gating --")
    st, body = set_engine(token, "auto")
    note(st == 200 and body.get("engine") == "auto", "engine_set_auto",
         f"HTTP {st}")
    st, info = engine_info(token)
    note(info.get("engine") == "auto" and info.get("source") == "settings",
         "engine_auto_persisted", f"engine={info.get('engine')}")

    # te: not measured, not claimed -> legacy
    st, b = post("/predict", {"text": TE_SENTENCE}, token, timeout=60)
    note(st == 200 and b.get("decision_status") == "legacy"
         and b.get("processing_mode") != "pretrained_model"
         and "toxicity_score" not in b,
         "auto_te_legacy",
         f"HTTP {st} status={b.get('decision_status')} mode={b.get('processing_mode')}")

    # en: measured+claimed -> model
    st, b = post("/predict", {"text": "You are stupid and useless, I hate you."},
                 token, timeout=60)
    note(st == 200 and b.get("processing_mode") == "pretrained_model"
         and b.get("decision_status") in ("predicted", "uncertain"),
         "auto_en_model",
         f"HTTP {st} mode={b.get('processing_mode')} status={b.get('decision_status')}")

    # ta: measured (NOT claimed by the model card) -> model via coverage map
    st, b = post("/predict",
                 {"text": "\u0ba8\u0bc0 \u0b92\u0bb0\u0bc1 \u0bae\u0bc1\u0b9f\u0bcd\u0b9f\u0bbe\u0bb3\u0bcd, "
                          "\u0b89\u0ba9\u0bc8 \u0bb5\u0bc6\u0bb1\u0bc1\u0b95\u0bcd\u0b95\u0bbf\u0bb1\u0bc7\u0ba9\u0bcd."},
                 token, timeout=60)
    note(st == 200 and b.get("processing_mode") == "pretrained_model"
         and b.get("model_coverage") == "experimental",
         "auto_ta_model_via_coverage_map",
         f"HTTP {st} mode={b.get('processing_mode')} "
         f"cov={b.get('model_coverage')}")


# ---------------------------------------------------------------------------
# 10) Fallback: second instance whose model cannot load
# ---------------------------------------------------------------------------
def free_port(candidates=(8099, 8098, 8111, 8123, 8145, 8177)):
    for p in candidates:
        s = socket.socket()
        try:
            s.bind(("127.0.0.1", p))
            s.close()
            return p
        except OSError:
            s.close()
    return None


def section_fallback(token: str) -> None:
    print("\n-- 10) clean fallback (unloadable model) --")
    st, body = set_engine(token, "hf")
    note(st == 200, "fallback_engine_hf_prepared", f"HTTP {st}")
    port = free_port()
    if port is None:
        note(False, "fallback_port_free", "no free port available")
        return
    empty_cache = tempfile.mkdtemp(prefix="aura_fallback_cache_")
    log_path = os.path.join(tempfile.gettempdir(),
                            f"aura_fallback_{port}.log")
    env = dict(os.environ)
    for k in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE"):
        env.pop(k, None)
    env["AURA_MODEL_ID"] = "bogus/nonexistent-aura-model"
    env["AURA_MODEL_OFFLINE"] = "1"
    env["AURA_MODEL_CACHE"] = empty_cache
    env["AURA_MODEL_RETRY_S"] = "60"
    env["AURA_PREDICTION_ENGINE"] = "hf"
    proc = None
    try:
        log = open(log_path, "w", encoding="utf-8", errors="replace")
        proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "main:app",
             "--host", "127.0.0.1", "--port", str(port)],
            cwd=BACKEND_DIR, env=env, stdout=log, stderr=subprocess.STDOUT)
        child = f"http://127.0.0.1:{port}"
        healthy = False
        for _ in range(120):  # <= 120s startup budget (slow under contention)
            if proc.poll() is not None:
                break
            try:
                with urllib.request.urlopen(child + "/health", timeout=2) as r:
                    if json.loads(r.read().decode()).get("status") == "healthy":
                        healthy = True
                        break
            except Exception:
                pass
            time.sleep(1.0)
        note(healthy, "fallback_instance_up",
             f"port={port} poll=60s")
        if not healthy:
            try:
                with open(log_path, encoding="utf-8", errors="replace") as fh:
                    tail = fh.read()[-400:]
            except Exception:
                tail = "(no log)"
            print(f"      child log tail: {tail}")
            return

        cbase = f"http://127.0.0.1:{port}"
        st, lb = post("/auth/login",
                      {"username": ADMIN_USER, "password": ADMIN_PASS})
        # NOTE: post() targets BASE, so hit the child explicitly below
        req = urllib.request.Request(
            cbase + "/auth/login",
            data=json.dumps({"username": ADMIN_USER,
                             "password": ADMIN_PASS}).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                ctoken = json.loads(r.read().decode()).get("token")
        except Exception as e:
            ctoken = None
            note(False, "fallback_child_login", str(e)[:120])
        if not ctoken:
            return

        def cpost(path, data, timeout=300):
            rq = urllib.request.Request(
                cbase + path, data=json.dumps(data).encode(),
                headers={"Content-Type": "application/json",
                         "Authorization": "Bearer " + ctoken}, method="POST")
            try:
                with urllib.request.urlopen(rq, timeout=timeout) as r:
                    return r.status, json.loads(r.read().decode())
            except urllib.error.HTTPError as e:
                try:
                    return e.code, json.loads(e.read().decode())
                except Exception:
                    return e.code, {}
            except Exception as e:
                return -1, {"detail": str(e)}

        def cget(path, timeout=30):
            rq = urllib.request.Request(
                cbase + path, headers={"Authorization": "Bearer " + ctoken})
            try:
                with urllib.request.urlopen(rq, timeout=timeout) as r:
                    return r.status, json.loads(r.read().decode())
            except urllib.error.HTTPError as e:
                try:
                    return e.code, json.loads(e.read().decode())
                except Exception:
                    return e.code, {}
            except Exception as e:
                return -1, {"detail": str(e)}

        st, b = cpost("/predict",
                      {"text": "You are stupid and useless, I hate you."})
        note(st == 200, "fallback_predict_200", f"HTTP {st} {str(b)[:120]}")
        note(b.get("decision_status") == "fallback", "fallback_decision_status",
             f"status={b.get('decision_status')}")
        note(b.get("model_name") == MODEL_LEGACY_NAME, "fallback_model_name",
             f"model_name={b.get('model_name')}")
        err = b.get("model_error")
        note(isinstance(err, str) and bool(err.strip()), "fallback_model_error",
             f"error={str(err)[:120]}")
        if isinstance(err, str):
            note("Traceback" not in err and "\n" not in err
                 and not re.search(r"[A-Za-z]:\\", err),
                 "fallback_error_sanitised",
                 f"single-line, path-masked error ({len(err)} chars)")
        ok, why = no_internals(b)
        note(ok, "fallback_response_no_internals", why)
        note(b.get("processing_mode") in ("existing_model", "language_lexicon",
                                          "fallback"),
             "fallback_legacy_mode", f"mode={b.get('processing_mode')}")
        required = {"label", "threshold", "score", "categories",
                    "language_code", "overall_label"}
        note(required <= set(b), "fallback_contract_intact",
             f"missing={required - set(b)}")
        note("toxicity_score" not in b, "fallback_no_toxicity_score",
             "toxicity_score absent on fallback")

        st, ad = cget("/models/adapter")
        adapter = (ad or {}).get("adapter") or {}
        deadline = time.time() + 120
        while adapter.get("status") == "loading" and time.time() < deadline:
            time.sleep(3)
            st, ad = cget("/models/adapter")
            adapter = (ad or {}).get("adapter") or {}
        note(st == 200 and adapter.get("status") == "unavailable",
             "fallback_adapter_unavailable",
             f"HTTP {st} status={adapter.get('status')}")
        note(bool(adapter.get("error")), "fallback_adapter_error_present",
             f"error={str(adapter.get('error'))[:120]}")
        clean, why = no_internals(adapter)
        note(clean, "fallback_adapter_info_sanitised", why)
        note("cache_dir" not in adapter, "fallback_adapter_cache_hidden",
             f"keys={sorted(adapter)[:10]}")
        st, eng = cget("/models/engine")
        note(st == 200 and eng.get("engine") == "hf",
             "fallback_child_engine_hf",
             f"HTTP {st} engine={eng.get('engine')}")
    finally:
        if proc is not None:
            try:
                proc.kill()
                proc.wait(timeout=10)
            except Exception:
                pass
        shutil.rmtree(empty_cache, ignore_errors=True)


# ---------------------------------------------------------------------------
# 11) In-process adapter: pre-load validation + failure backoff
# ---------------------------------------------------------------------------
def section_inprocess_backoff() -> None:
    print("\n-- 11) in-process adapter validation + backoff --")
    keys = ["AURA_MODEL_ID", "AURA_MODEL_OFFLINE", "AURA_MODEL_CACHE",
            "AURA_MODEL_RETRY_S", "AURA_PREDICTION_ENGINE",
            "HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE"]
    saved = {k: os.environ.pop(k, None) for k in keys}
    tmp = tempfile.mkdtemp(prefix="aura_inproc_cache_")
    sys.path.insert(0, BACKEND_DIR)
    try:
        os.environ["AURA_MODEL_ID"] = "bogus/nonexistent-aura-model"
        os.environ["AURA_MODEL_OFFLINE"] = "1"
        os.environ["AURA_MODEL_CACHE"] = tmp
        os.environ["AURA_MODEL_RETRY_S"] = "60"
        os.environ["AURA_PREDICTION_ENGINE"] = "hf"
        import model_adapter as ma

        ad = ma.HFToxicityAdapter()
        # pre-load validation must fire before any (expensive) load attempt
        t0 = time.time()
        try:
            ad.predict([])
            note(False, "inproc_empty_raises", "no exception raised")
        except ma.AdapterUnavailable as e:
            note(time.time() - t0 < 1.0 and "no text" in str(e),
                 "inproc_empty_raises", f"{e} in {time.time() - t0:.2f}s")
        except Exception as e:
            note(False, "inproc_empty_raises", f"{type(e).__name__}: {e}")
        note(ad.status == "not_loaded", "inproc_empty_no_load",
             f"status={ad.status}")
        t0 = time.time()
        try:
            ad.predict(["x"] * 1001)
            note(False, "inproc_oversize_batch_raises", "no exception raised")
        except ma.AdapterUnavailable as e:
            note(time.time() - t0 < 1.0 and "too large" in str(e),
                 "inproc_oversize_batch_raises",
                 f"{e} in {time.time() - t0:.2f}s")
        except Exception as e:
            note(False, "inproc_oversize_batch_raises",
                 f"{type(e).__name__}: {e}")
        note(ad.status == "not_loaded", "inproc_oversize_no_load",
             f"status={ad.status}")

        # first real attempt: offline bogus id -> fails after the (slow) import
        t0 = time.time()
        first_err = None
        try:
            ad.predict(["probe"])
        except Exception as e:
            first_err = e
        first_s = time.time() - t0
        note(first_err is not None, "inproc_first_load_fails",
             f"{type(first_err).__name__ if first_err else 'none'} "
             f"in {first_s:.1f}s")
        note(ad.status == "unavailable" and bool(ad.error),
             "inproc_status_unavailable",
             f"status={ad.status} error={ad.error[:80]}")
        note("Traceback" not in ad.error, "inproc_error_not_traceback",
             f"error={ad.error[:80]}")

        # second attempt must hit the retry backoff (fast, no reload)
        t0 = time.time()
        second_err = None
        try:
            ad.predict(["probe2"])
        except Exception as e:
            second_err = e
        second_s = time.time() - t0
        note(second_err is not None and second_s < 2.0,
             "inproc_backoff_second_fail_fast",
             f"{type(second_err).__name__ if second_err else 'none'} "
             f"in {second_s:.2f}s (first {first_s:.1f}s)")

        ad.reset()
        note(ad.status == "not_loaded" and not ad.error,
             "inproc_reset_clears", f"status={ad.status}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        sys.path[:] = [p for p in sys.path if p != BACKEND_DIR] or sys.path


# ---------------------------------------------------------------------------
# 12) Restore legacy + final verification
# ---------------------------------------------------------------------------
def section_restore(token: str) -> None:
    print("\n-- 12) restore legacy engine --")
    st, body = set_engine(token, "legacy")
    note(st == 200 and body.get("engine") == "legacy", "restore_set_legacy",
         f"HTTP {st} {str(body)[:80]}")
    st, info = engine_info(token)
    note(st == 200 and info.get("engine") == "legacy"
         and info.get("source") == "settings",
         "restore_verified",
         f"engine={info.get('engine')} source={info.get('source')}")
    st, b = post("/predict", {"text": "hello"}, token, timeout=30)
    note(st == 200 and b.get("decision_status") == "legacy"
         and b.get("processing_mode") == "existing_model"
         and "toxicity_score" not in b,
         "restore_predict_legacy",
         f"HTTP {st} status={b.get('decision_status')} "
         f"mode={b.get('processing_mode')}")
    eng = db_value("prediction_engine")
    note(eng == "legacy", "restore_settings_row", f"prediction_engine={eng}")


def main() -> int:
    print(f"== AURA Phase 2 model-adapter suite against {BASE} ==")
    try:
        with urllib.request.urlopen(BASE + "/health", timeout=8) as r:
            if json.loads(r.read().decode()).get("status") != "healthy":
                print("backend unhealthy")
                return 2
    except Exception as e:
        print(f"backend unreachable: {e}")
        return 2

    token = login()
    print("login OK")
    try:
        section_engine_admin(token)
        section_legacy(token)
        model_id, per_lang, global_thr = section_hf_switch(token)
        section_loading_cache(token, model_id, per_lang, global_thr)
        section_per_language(token, model_id, per_lang, global_thr)
        section_unmeasured(token, model_id, per_lang, global_thr)
        section_batch_limits(token, model_id, per_lang, global_thr)
        section_persistence(token, model_id, per_lang, global_thr)
        section_auto(token, model_id, per_lang, global_thr)
        section_fallback(token)
        section_inprocess_backoff()
    except Exception as e:  # always restore the engine before exiting
        note(False, "suite_unexpected_error",
             f"{type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
    finally:
        try:
            section_restore(token)
        except Exception as e:
            note(False, "restore_failed", f"{type(e).__name__}: {e}")

    print(f"\nMODEL-ADAPTER SUMMARY: PASSED {PASS} / FAILED {FAIL}")
    if FAIL:
        print("failed: " + ", ".join(FAILURES))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
