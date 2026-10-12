"""AURA Phase 4 / Workstream C — model adapter + fallback contract tests.

SAFE TO RUN CONCURRENTLY WITH OTHER WORK: this suite never loads model weights.
  * The HuggingFace adapter singleton is replaced by a stub for every
    backend-path test; the real ``_ensure_loaded`` torch/transformers import
    path is never executed.
  * ``backend.db`` is replaced by an in-memory SQLite connection and
    ``backend.store_moderation`` is stubbed, so aura.db is NEVER opened for
    writing and no moderation row is ever persisted.
  * No HTTP server is started; no service, process or worker is touched.

What is verified (all weight-free):
  1. models/tuned_threshold.json exact Phase 2 values + sha256 checksum.
  2. model_adapter deployed defaults (timeout 10 s, batch 16) read from env
     only; benchmark_phase3.py relaxes them via os.environ.setdefault at ITS
     import time and never mutates model_adapter's defaults in source.
  3. categorise() decision contract (threshold, uncertain margin, categories).
  4. Coverage map honesty: en/hi validated, ta/ta-Latn/bn/ur experimental,
     ta NOT model-card claimed, unmeasured vs model_card_claimed distinction.
  5. should_try_model gating: legacy never, hf always, auto only measured or
     claimed languages.
  6. mlexicon.detect per language (en, ta, ta-Latn, hi, bn, ur) + the
     unsupported-language states (Swahili/Spanish -> en, Chinese -> und,
     emoji-only -> und) and the single-marker Tanglish -> en limitation.
  7. Legacy response contract through run_engine(): decision_status='legacy',
     model_name='aura-legacy-rules-lexicon', NO toxicity_score key.
  8. Failure truthfulness: a failing/timing-out adapter yields
     decision_status='fallback' + sanitised model_error, keeps the legacy
     model_name, and never fabricates a toxicity_score.
  9. State distinction: predicted vs fallback vs experimental are distinct
     responses; and the unsupported-Latin-script collapse into 'en' is
     characterised (documented finding, not changed here).
 10. Adapter concurrency guard: single-flight (no second load can start while
     one is in progress) and the documented 'model is loading' fast-fail is
     unreachable under real lock contention (characterised, report-only).

Run:
    .venv\\Scripts\\python.exe tests_model_adapter_phase4.py
Exit codes: 0 = all pass, 1 = failures.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
from contextlib import contextmanager
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_DIR))

EXPECTED_TUNED = {  # Phase 2 deployed values — must never change silently
    "threshold": 0.35,
    "per_language": {"en": 0.55, "ta": 0.40, "ta-Latn": 0.30,
                     "hi": 0.35, "bn": 0.30, "ur": 0.40},
    "tuned_at": "2026-10-09T16:57:48",
}
EXPECTED_SHA256 = ("f31f4975d29a151f3f8737ae18875f6a5d11c2ee8719d126c587f7b3"
                   "39285c54")

# Tamil script, Devanagari (hi), Bengali, Arabic-script Urdu, Tanglish.
TA_SCRIPT = "\u0ba8\u0bb2\u0bcd \u0ba8\u0bb2\u0bcd"
TA_SENT = "\u0ba8\u0bb0\u0bae\u0bbe\u0ba9 \u0ba8\u0bc0\u0b9a\u0bb5\u0bb0\u0bcd" \
          "\u0ba4\u0bc1\u0bae\u0bcd"
HI_SENT = "\u092c\u0947\u0935\u0915\u0942\u092b \u0939\u094b"
BN_SENT = "\u09ac\u09cb\u0995\u09be \u09b9\u09cb\u09df\u09be"
URDU = "\u0628\u0642\u0648\u0641 \u0647\u0648"   # Arabic-script Urdu
TANGLISH_2MARK = "nee vera level mudhalai, unnai verukkiren"
TANGLISH_1MARK = "muttal"
SWAHILI = "habari yako wewe ni mjinga sana kabisa"
SPANISH = "hola amigo que tal estas hoy"
CHINESE = "\u4f60\u597d \u670b\u53cb"
EMOJI = "\U0001F600\U0001F44D\U0001F525"

import model_adapter as ma  # noqa: E402  (path set above; torch never imported)
import mlexicon as mlx  # noqa: E402


class _StubAdapter:
    """Stand-in for ma.ADAPTER: returns a fixed payload or raises."""

    def __init__(self, payload=None, error=None):
        self.payload = payload or {}
        self.error = error
        self.calls = 0

    def predict(self, texts):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return dict(self.payload)

    def info(self):
        return {"status": "ready" if self.error is None else "unavailable"}


def _model_payload(tox=0.9, per_lang=None, model_id="stub/model-x"):
    return {
        "ok": True,
        # label names match the real model id2label set (model_adapter
        # MODEL_LABEL_MAP keys: severe_toxicity, identity_attack, ...)
        "scores": [{"toxicity": tox, "severe_toxicity": 0.1, "obscene": 0.1,
                    "threat": 0.1, "insult": 0.2, "identity_attack": 0.05,
                    "sexual_explicit": 0.01}],
        "model_id": model_id,
        "model_version": "stubv1",
        "threshold": 0.35,
        "per_language_thresholds": dict(
            per_lang or EXPECTED_TUNED["per_language"]),
        "threshold_source": "tuned_validation",
        "threshold_rationale": "stub",
        "latency_ms": 1.0,
        "labels": ["toxicity", "severe_toxicity", "obscene", "threat",
                   "insult", "identity_attack", "sexual_explicit"],
        "problem_type": "multi_label_classification",
    }


@contextmanager
def patched_backend_db():
    """backend.db() -> fresh in-memory connection (aura.db never touched)."""
    import backend
    saved = backend.db

    def memdb():
        c = sqlite3.connect(":memory:")
        c.row_factory = sqlite3.Row
        c.execute("CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,"
                  " value TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS moderation_results(id INTEGER"
                  " PRIMARY KEY AUTOINCREMENT)")
        return c

    backend.db = memdb
    try:
        yield backend
    finally:
        backend.db = saved


@contextmanager
def patched(name, value):
    import backend
    saved = getattr(backend, name)
    setattr(backend, name, value)
    try:
        yield
    finally:
        setattr(backend, name, saved)


@contextmanager
def env_overrides(**kw):
    saved = {k: os.environ.get(k) for k in kw}
    os.environ.update(kw)
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


@contextmanager
def stub_adapter(payload=None, error=None):
    """Replace the module-level singleton with a stub (no weights ever)."""
    saved = ma.ADAPTER
    ma.ADAPTER = _StubAdapter(payload, error)
    try:
        yield ma.ADAPTER
    finally:
        ma.ADAPTER = saved


# ---------------------------------------------------------------------------
# 1) tuned_threshold.json — exact values + checksum
# ---------------------------------------------------------------------------
class TestTunedThresholdFile(unittest.TestCase):
    PATH = BACKEND_DIR / "models" / "tuned_threshold.json"

    def test_sha256_checksum(self):
        digest = hashlib.sha256(self.PATH.read_bytes()).hexdigest()
        self.assertEqual(digest, EXPECTED_SHA256,
                         f"tuned_threshold.json sha256 changed: {digest}")

    def test_phase2_values_exactly(self):
        d = json.loads(self.PATH.read_text(encoding="utf-8"))
        self.assertEqual(d["threshold"], EXPECTED_TUNED["threshold"])
        self.assertEqual(d["per_language"], EXPECTED_TUNED["per_language"])
        self.assertEqual(d["tuned_at"], EXPECTED_TUNED["tuned_at"])
        # the rejected Phase 3 values must NOT be deployed
        for lang, val in d["per_language"].items():
            self.assertNotEqual(val, 0.25,
                                f"{lang} deployed threshold is the rejected "
                                "0.25 value")

    def test_model_config_reads_deployed_thresholds(self):
        with env_overrides(AURA_MODEL_TUNED_THRESHOLD=str(self.PATH)):
            cfg = ma.ModelConfig()
        self.assertEqual(cfg.threshold, 0.35)
        self.assertEqual(cfg.per_language,
                         {k: float(v) for k, v in
                          EXPECTED_TUNED["per_language"].items()})
        self.assertEqual(cfg.threshold_for("en"), 0.55)
        self.assertEqual(cfg.threshold_for("ta"), 0.40)
        self.assertEqual(cfg.threshold_for("ta-Latn"), 0.30)
        self.assertEqual(cfg.threshold_for("hi"), 0.35)
        self.assertEqual(cfg.threshold_for("bn"), 0.30)
        self.assertEqual(cfg.threshold_for("ur"), 0.40)
        self.assertEqual(cfg.threshold_for("te"), 0.35)  # global fallback
        self.assertEqual(cfg.threshold_source, "tuned_validation")

    def test_malformed_tuned_file_keeps_per_language(self):
        """A bad/missing global threshold must not silently drop valid
        per-language values. Characterised as a latent gap in Phase 4;
        fixed in Phase 4.1 (C-F-5): per_language is now parsed
        independently of the global entry."""
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "t.json"
            p.write_text(json.dumps(
                {"per_language": {"en": 0.55, "ta": 0.40}}), encoding="utf-8")
            with env_overrides(AURA_MODEL_TUNED_THRESHOLD=str(p),
                               AURA_MODEL_THRESHOLD="0.5"):
                cfg = ma.ModelConfig()
        # FIXED: valid per-language values survive a missing global entry.
        self.assertEqual(cfg.per_language, {"en": 0.55, "ta": 0.40},
                         "per-language thresholds must be preserved when the "
                         "global threshold entry is missing")
        # ...and the documented fallback still applies to the GLOBAL value,
        # rather than a valid language value being overwritten by it.
        self.assertEqual(cfg.threshold_for("en"), 0.55)
        self.assertEqual(cfg.threshold_for("ta"), 0.40)
        self.assertEqual(cfg.threshold_for("te"), 0.5,
                         "global fallback follows AURA_MODEL_THRESHOLD")


# ---------------------------------------------------------------------------
# 2) Deployed defaults + Phase 3 env-only relaxation
# ---------------------------------------------------------------------------
class TestDeployedDefaults(unittest.TestCase):
    def test_default_timeout_and_batch(self):
        keys = ["AURA_MODEL_TIMEOUT_S", "AURA_MODEL_BATCH_SIZE"]
        saved = {k: os.environ.pop(k, None) for k in keys}
        try:
            cfg = ma.ModelConfig()
            self.assertEqual(cfg.timeout_s, 10.0)
            self.assertEqual(cfg.batch_size, 16)
        finally:
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v

    def test_benchmark_phase3_relaxes_env_only(self):
        src = (BACKEND_DIR / "benchmark_phase3.py").read_text(encoding="utf-8")
        self.assertIn('os.environ.setdefault("AURA_MODEL_TIMEOUT_S"',
                      src)
        self.assertIn('os.environ.setdefault("AURA_MODEL_BATCH_SIZE"', src)
        self.assertNotIn('os.environ["AURA_MODEL_TIMEOUT_S"] =', src)
        self.assertNotIn('os.environ["AURA_MODEL_BATCH_SIZE"] =', src)
        adapter_src = (BACKEND_DIR / "model_adapter.py").read_text(
            encoding="utf-8")
        self.assertIn('_env("AURA_MODEL_TIMEOUT_S", "10")', adapter_src)
        self.assertIn('_env("AURA_MODEL_BATCH_SIZE", "16")', adapter_src)

    def test_coverage_notes_match_deployed_threshold_artifact(self):
        """Coverage notes must be correct FOR THE DEPLOYED thresholds and
        must name the threshold each figure belongs to (Phase 4 finding D-E1:
        notes that do not name their threshold read as a contradiction of
        models/phase3_benchmark.json, which reports the swept-but-not-
        adopted values)."""
        import re
        tuned = json.loads((BACKEND_DIR / "models" / "tuned_threshold.json")
                           .read_text(encoding="utf-8"))["per_language"]
        p2 = json.loads((BACKEND_DIR / "models" / "phase2_benchmark.json")
                        .read_text(encoding="utf-8"))
        for lang in ("en", "ta", "ta-Latn", "hi", "bn", "ur"):
            status, note_text = ma.MODEL_COVERAGE[lang]
            self.assertIn("threshold", note_text, f"{lang} note names no "
                                                  f"threshold: {note_text}")
            named = re.search(r"threshold ([0-9.]+)", note_text)
            self.assertIsNotNone(named, f"{lang}: {note_text}")
            self.assertAlmostEqual(float(named.group(1)), float(tuned[lang]),
                                   places=2, msg=f"{lang} note threshold")
            # the figure must match the artifact produced at that threshold
            model = p2["groups"][lang]["model"]
            self.assertEqual(float(model["threshold_used"]),
                             float(tuned[lang]),
                             f"{lang} phase2 artifact threshold_used")
            f1 = float(re.search(r"F1 ([0-9.]+)", note_text).group(1))
            fpr = float(re.search(r"FPR ([0-9.]+)", note_text).group(1))
            self.assertLessEqual(abs(f1 - float(model["toxic_f1"])), 0.0006,
                                 f"{lang} note F1 vs artifact")
            self.assertLessEqual(abs(fpr - float(model["fpr"])), 0.0006,
                                 f"{lang} note FPR vs artifact")


# ---------------------------------------------------------------------------
# 3) categorise() decision contract
# ---------------------------------------------------------------------------
class TestCategorise(unittest.TestCase):
    def test_toxic_above_threshold(self):
        dec = ma.categorise({"toxicity": 0.9}, 0.55)
        self.assertEqual(dec["label"], "toxic")
        self.assertEqual(dec["decision_status"], "predicted")
        self.assertEqual(dec["toxicity_score"], 0.9)
        self.assertEqual(dec["threshold"], 0.55)

    def test_negative_below_threshold(self):
        dec = ma.categorise({"toxicity": 0.1}, 0.55)
        self.assertEqual(dec["label"], "non_toxic")
        self.assertEqual(dec["decision_status"], "predicted")

    def test_uncertain_margin(self):
        dec = ma.categorise({"toxicity": 0.54}, 0.55)
        self.assertEqual(dec["decision_status"], "uncertain")
        self.assertEqual(dec["margin"], 0.01)

    def test_label_map_and_non_toxic_head(self):
        dec = ma.categorise({"toxicity": 0.9, "severe_toxicity": 0.8,
                             "identity_attack": 0.7}, 0.55)
        self.assertEqual(dec["categories"]["severe_toxic"], 0.8)
        self.assertEqual(dec["categories"]["identity_hate"], 0.7)
        self.assertAlmostEqual(dec["categories"]["non_toxic"], 0.1, places=4)


# ---------------------------------------------------------------------------
# 4) Coverage honesty + engine gating
# ---------------------------------------------------------------------------
class TestCoverageAndGating(unittest.TestCase):
    def test_coverage_statuses(self):
        self.assertEqual(ma.coverage_for("en")[0], "validated")
        self.assertEqual(ma.coverage_for("hi")[0], "validated")
        for code in ("ta", "ta-Latn", "bn", "ur"):
            self.assertEqual(ma.coverage_for(code)[0], "experimental", code)
        self.assertEqual(ma.coverage_for("te")[0], "unmeasured")
        self.assertEqual(ma.coverage_for("fr")[0], "model_card_claimed")

    def test_ta_not_claimed_by_model_card(self):
        self.assertNotIn("ta", ma.MODEL_CLAIMED_LANGUAGES)
        self.assertNotIn("ta", {c.split("-")[0]
                                for c in ma.MODEL_CLAIMED_LANGUAGES})

    def test_engine_gating(self):
        for mode, expected in (("legacy", False), ("hf", True)):
            with env_overrides(AURA_PREDICTION_ENGINE=mode):
                for code in ("en", "ta", "ta-Latn", "hi", "bn", "ur", "te",
                             "fr", "und"):
                    self.assertEqual(ma.should_try_model(code), expected,
                                     f"{mode}/{code}")
        with env_overrides(AURA_PREDICTION_ENGINE="auto"):
            for code in ("en", "ta", "ta-Latn", "hi", "bn", "ur", "fr"):
                self.assertTrue(ma.should_try_model(code), f"auto/{code}")
            for code in ("te", "ml", "kn", "und"):
                self.assertFalse(ma.should_try_model(code), f"auto/{code}")


# ---------------------------------------------------------------------------
# 5) mlexicon language detection per language + unsupported states
# ---------------------------------------------------------------------------
class TestLanguageDetection(unittest.TestCase):
    def test_six_languages(self):
        self.assertEqual(mlx.detect("hello my friend")["code"], "en")
        self.assertEqual(mlx.detect(TA_SCRIPT)["code"], "ta")
        self.assertEqual(mlx.detect(TANGLISH_2MARK)["code"], "ta-Latn")
        self.assertEqual(mlx.detect(HI_SENT)["code"], "hi")
        self.assertEqual(mlx.detect(BN_SENT)["code"], "bn")
        self.assertEqual(mlx.detect(URDU)["code"], "ur")

    def test_unsupported_states(self):
        # Latin-script unsupported -> 'und' (explicit unsupported state;
        # C-F-2 FIXED in Phase 4.1 — no longer silently collapsed to 'en')
        self.assertEqual(mlx.detect(SWAHILI)["code"], "und")
        self.assertEqual(mlx.detect(SPANISH)["code"], "und")
        # non-Latin unsupported / no letters -> 'und'
        self.assertEqual(mlx.detect(CHINESE)["code"], "und")
        self.assertEqual(mlx.detect(EMOJI)["code"], "und")

    def test_unsupported_latin_is_not_labelled_english(self):
        # C-F-2: unsupported Latin must not be presented as English.
        self.assertNotEqual(mlx.detect(SWAHILI)["code"], "en")
        self.assertNotEqual(mlx.detect(SPANISH)["code"], "en")

    def test_single_marker_tanglish_not_labelled_english(self):
        # C-F-4 FIXED: 'muttal' alone is 1 weak marker, so it is ambiguous
        # ('und') rather than confidently English; >=2 markers -> ta-Latn.
        self.assertNotEqual(mlx.detect(TANGLISH_1MARK)["code"], "en")
        self.assertIn(mlx.detect(TANGLISH_1MARK)["code"], ("und", "ta-Latn"))
        self.assertEqual(mlx.detect(TANGLISH_2MARK)["code"], "ta-Latn")

    def test_lexicons_exist_for_six(self):
        avail = {c: mlx.lexicon_available(c)
                 for c in ("en", "ta", "ta-Latn", "hi", "bn", "ur")}
        self.assertTrue(all(avail.values()), str(avail))


# ---------------------------------------------------------------------------
# 6) backend contract: legacy purity, fallback truthfulness, state split
# ---------------------------------------------------------------------------
class TestBackendContract(unittest.TestCase):
    def setUp(self):
        import backend
        self.backend = backend
        self._saved_env = os.environ.get("AURA_PREDICTION_ENGINE")
        self.ctx_db = patched_backend_db()
        self.ctx_store = patched("store_moderation",
                                 lambda *a, **k: 12345)
        self.ctx_db.__enter__()
        self.ctx_store.__enter__()

    def tearDown(self):
        self.ctx_store.__exit__(None, None, None)
        self.ctx_db.__exit__(None, None, None)
        if self._saved_env is None:
            os.environ.pop("AURA_PREDICTION_ENGINE", None)
        else:
            os.environ["AURA_PREDICTION_ENGINE"] = self._saved_env

    def _run(self, text, engine="legacy"):
        with env_overrides(AURA_PREDICTION_ENGINE=engine):
            self.backend.set_engine(engine)
            req = self.backend.MessageIn(text=text, user_id="tester",
                                         conversation_id="phase4")
            r, extra = self.backend.run_engine(req, "text")
        return r, extra

    # ---- legacy contract -------------------------------------------------
    def test_legacy_contract_no_toxicity_score(self):
        r, extra = self._run("hello my friend", engine="legacy")
        self.assertEqual(r["decision_status"], "legacy")
        self.assertEqual(r["model_name"], "aura-legacy-rules-lexicon")
        self.assertNotIn("toxicity_score", r)
        self.assertEqual(r["processing_mode"], "existing_model")
        self.assertEqual(extra["prediction_id"], 12345)

    def test_legacy_tamil_contract(self):
        r, _ = self._run(TA_SENT, engine="legacy")
        self.assertEqual(r["decision_status"], "legacy")
        self.assertEqual(r["language_code"], "ta")
        self.assertEqual(r["processing_mode"], "language_lexicon")
        self.assertNotIn("toxicity_score", r)
        self.assertGreater(r["language_confidence"], 0.0)
        self.assertEqual(r["language_confidence_kind"], "script_share")

    def test_legacy_engine_never_calls_adapter(self):
        with stub_adapter(payload=_model_payload()) as stub:
            r, _ = self._run("You are stupid and useless", engine="legacy")
        self.assertEqual(stub.calls, 0, "legacy path invoked the adapter")
        self.assertEqual(r["decision_status"], "legacy")
        self.assertNotIn("toxicity_score", r)

    # ---- hf engine: success + failure truthfulness -----------------------
    def test_hf_success_uses_tuned_thresholds_and_provenance(self):
        with stub_adapter(payload=_model_payload(tox=0.9)):
            r, _ = self._run("You are stupid and useless", engine="hf")
        self.assertEqual(r["decision_status"], "predicted")
        self.assertEqual(r["processing_mode"], "pretrained_model")
        self.assertEqual(r["confidence_kind"], "model")
        self.assertEqual(r["model_name"], "stub/model-x")
        self.assertEqual(r["model_coverage"], "validated")
        self.assertEqual(r["threshold"], 0.55)      # en tuned threshold
        self.assertEqual(r["toxicity_score"], 0.9)
        self.assertEqual(r["label"], "toxic")

    def test_hf_tamil_gets_ta_threshold_and_experimental_coverage(self):
        """Measured-but-experimental language (ta): decision_status stays
        predicted/uncertain (backend.py:948 sets 'experimental' only for
        unmeasured/model_card_claimed coverage); the caveat is carried by
        model_coverage + note, and the deployed ta threshold 0.40 applies."""
        with stub_adapter(payload=_model_payload(tox=0.9)):
            r, _ = self._run(TA_SENT, engine="hf")
        self.assertEqual(r["language_code"], "ta")
        self.assertEqual(r["threshold"], 0.40)      # ta tuned threshold
        self.assertEqual(r["model_coverage"], "experimental")
        self.assertIn(r["decision_status"], ("predicted", "uncertain"))
        self.assertTrue(r["model_coverage_note"])

    def test_hf_timeout_falls_back_truthfully(self):
        err = ma.AdapterUnavailable(
            "inference timeout (> 10.0s per batch chunk)")
        with stub_adapter(error=err):
            r, _ = self._run("You are stupid and useless", engine="hf")
        self.assertEqual(r["decision_status"], "fallback")
        self.assertIn("timeout", r["model_error"])
        self.assertEqual(r["model_name"], "aura-legacy-rules-lexicon")
        self.assertNotIn("toxicity_score", r)      # never a fabricated score
        self.assertNotIn("Traceback", r["model_error"])
        self.assertNotIn("\n", r["model_error"])

    def test_hf_load_failure_falls_back_truthfully(self):
        err = ma.AdapterUnavailable("OSError: offline and weights unavailable")
        with stub_adapter(error=err):
            r, _ = self._run("hello my friend", engine="hf")
        self.assertEqual(r["decision_status"], "fallback")
        self.assertIn("OSError", r["model_error"])
        self.assertEqual(r["model_name"], "aura-legacy-rules-lexicon")
        self.assertNotIn("toxicity_score", r)

    def test_hf_unmeasured_language_is_experimental(self):
        te = "నువువు ఒక పిచ్చివాడివి"
        with stub_adapter(payload=_model_payload(tox=0.9)):
            r, _ = self._run(te, engine="hf")
        self.assertEqual(r["language_code"], "te")
        self.assertEqual(r["model_coverage"], "unmeasured")
        self.assertEqual(r["decision_status"], "experimental")
        self.assertEqual(r["decision"]["action"], "HUMAN_REVIEW")

    # ---- state distinction (predicted / fallback / experimental) ---------
    def test_three_states_are_distinct(self):
        with stub_adapter(payload=_model_payload(tox=0.1)):
            pred, _ = self._run("hello my friend", engine="hf")
        with stub_adapter(error=ma.AdapterUnavailable("model unavailable")):
            fb, _ = self._run("hello my friend", engine="hf")
        te = "నువువు ఒక పిచ్చివాడివి"
        with stub_adapter(payload=_model_payload(tox=0.9)):
            exp, _ = self._run(te, engine="hf")
        statuses = {pred["decision_status"], fb["decision_status"],
                    exp["decision_status"]}
        self.assertEqual(statuses, {"predicted", "fallback", "experimental"})
        self.assertNotIn("toxicity_score", fb)
        self.assertIn("model_error", fb)
        self.assertIn("toxicity_score", pred)
        self.assertIn("toxicity_score", exp)

    def test_unsupported_latin_is_marked_unsupported(self):
        """C-F-2 FIXED in Phase 4.1.

        Swahili/Spanish are undetectable by the script/marker heuristic and
        are now returned as an explicit unsupported state ('und') that routes
        to the neutral fallback, instead of an English prediction."""
        r, _ = self._run(SWAHILI, engine="legacy")
        self.assertEqual(r["language_code"], "und")
        self.assertEqual(r["language"], "Unknown")
        # Latin-script unknown keeps the default safety lexicon so known toxic
        # terms are still scored; the honest part is the language disclosure.
        self.assertEqual(r["processing_mode"], "existing_model")
        self.assertEqual(r["language_confidence_kind"], "no_signal")
        self.assertIsNone(r["language_confidence"])
        # Unknown language must NOT be treated as toxic merely for being
        # unknown: the fallback stays neutral and permissive.
        self.assertEqual(r["decision_status"], "legacy")
        self.assertEqual(r["label"], "non_toxic")
        self.assertEqual(r["action"], "ALLOW")
        # scored by the default safety lexicon, so it carries the lexicon's own
        # risk band rather than the fallback's forced "Low"
        self.assertEqual(r["risk_level"], "Safe")
        # Response keys are unchanged (backward compatible) and still expose
        # no fabricated confidence or toxicity score.
        self.assertNotIn("toxicity_score", r)

    def test_non_latin_unsupported_is_marked(self):
        r, _ = self._run(CHINESE, engine="legacy")
        self.assertEqual(r["language_code"], "und")
        self.assertEqual(r["processing_mode"], "fallback")
        self.assertIn("no safety lexicon is available", r["xai"]["reason"])


# ---------------------------------------------------------------------------
# 7) Adapter concurrency guard (no weights; lock behaviour only)
# ---------------------------------------------------------------------------
class TestAdapterConcurrency(unittest.TestCase):
    def test_status_loading_blocks_instead_of_fast_fail(self):
        """Characterisation of report finding D1.

        With the load thread holding _lock (as _ensure_loaded does), a
        concurrent predict() blocks on the lock; the documented
        'model is loading' fast-fail at model_adapter.py:240-241 never fires
        under real contention, so callers wait instead of falling back to
        legacy immediately."""
        ad = ma.HFToxicityAdapter()
        ad._status = "loading"          # as _ensure_loaded sets it mid-load
        outcome = []

        def call():
            try:
                ad._ensure_loaded()
                outcome.append("returned")
            except ma.AdapterUnavailable as e:
                outcome.append(f"raised:{e}")

        with ad._lock:                  # simulate the in-flight load
            t = threading.Thread(target=call, daemon=True)
            t.start()
            t.join(1.0)
            self.assertTrue(t.is_alive(),
                            "concurrent call returned/raised while the load "
                            f"lock was held — outcome={outcome}")
        t.join(5.0)
        self.assertFalse(t.is_alive(), "thread never released")
        # after the load finishes (lock released, status still 'loading' in
        # this simulation) the waiter is finally rejected — never a 2nd load.
        self.assertEqual(outcome, ["raised:model is loading"])

    def test_ready_path_bypasses_lock(self):
        ad = ma.HFToxicityAdapter()
        ad._status = "ready"
        ad._config = None
        t0 = time.time()
        cfg = ad._ensure_loaded()       # returns a fresh ModelConfig, no lock
        self.assertEqual(ad.status, "ready")
        self.assertLess(time.time() - t0, 1.0)
        self.assertIsNotNone(cfg)

    def test_predict_prechecks_do_not_load(self):
        ad = ma.HFToxicityAdapter()
        for texts, frag in (([], "no text"), (["x"] * 1001, "too large")):
            t0 = time.time()
            with self.assertRaises(ma.AdapterUnavailable) as cm:
                ad.predict(texts)
            self.assertIn(frag, str(cm.exception))
            self.assertLess(time.time() - t0, 1.0)
            self.assertEqual(ad.status, "not_loaded",
                             "pre-check must not start a load")

    def test_deadline_check_is_per_chunk_post_hoc(self):
        ad = ma.HFToxicityAdapter()
        cfg = ma.ModelConfig()
        cfg.timeout_s = 0.001
        with self.assertRaises(ma.AdapterUnavailable) as cm:
            ad._check_deadline(time.time() - 1.0, cfg)
        self.assertIn("timeout", str(cm.exception))
        cfg.timeout_s = 0               # 0 disables the guard
        ad._check_deadline(time.time() - 10.0, cfg)


if __name__ == "__main__":
    unittest.main(verbosity=2)
