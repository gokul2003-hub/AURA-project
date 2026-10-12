"""Modular pretrained-model inference adapter for AURA.

Design goals (Phase 2, §4):
  * Load a selected HF classifier ONCE (lazy singleton), never per-request.
  * No coupling between backend.py and any specific model vendor: everything
    (model id, cache dir, device, max length, threshold, engine choice) comes
    from environment configuration.
  * Evaluation mode + no gradients, batching, truncation, inference timeout,
    graceful error handling. Errors never leak stack traces to API clients.
  * Explicit OFFLINE / cache-only mode; when weights are unavailable the adapter
    reports ``unavailable`` and the caller falls back to the legacy engine.
  * Legacy Naive Bayes + lexicon engines remain the default and the fallback.

Engine selection (read at call time so tests can flip it without reimport):
    AURA_PREDICTION_ENGINE = legacy (default) | hf | auto
      legacy - always use the existing AURA rule/lexicon engine (unchanged)
      hf     - use the pretrained model when it loads; on failure fall back to
               legacy and mark the result decision_status='fallback'
      auto   - hf for languages the model card covers, legacy otherwise

Model configuration:
    AURA_MODEL_ID        default Horizon-Labs/multilingual-toxicity-small
    AURA_MODEL_CACHE     default <backend>/models/hf_cache  (kept out of git)
    AURA_MODEL_DEVICE    cpu (default) | cuda | auto
    AURA_MODEL_MAX_LENGTH       256
    AURA_MODEL_THRESHOLD        0.5   (overridden by tuned threshold file)
    AURA_MODEL_TUNED_THRESHOLD  path to JSON {"threshold": x, "rationale": "..."}
    AURA_MODEL_TIMEOUT_S        10
    AURA_MODEL_BATCH_SIZE       16
    AURA_MODEL_OFFLINE          0 | 1   (1 = cache-only, never hit network)
    AURA_MODEL_EAGER_LOAD       0 | 1   (1 = load during FastAPI startup)

Label semantics: the candidate outputs SEVEN INDEPENDENT SIGMOID scores
(Detoxify-style multi-label), NOT a softmax. Toxicity decision =
sigmoid(toxicity) >= threshold. See PHASE2_MODEL_EVALUATION.md.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Optional

BASE_DIR = Path(__file__).resolve().parent

# Config-load problems must be VISIBLE, never silently swallowed (C-F-5).
# Standard library logging: messages propagate to the root logger, so
# assertLogs()/basicConfig() in tests and deployments can see them.
LOG = logging.getLogger(__name__)

# label mapping: model label -> AURA category name
MODEL_LABEL_MAP = {
    "toxicity": "toxic",
    "severe_toxicity": "severe_toxic",
    "obscene": "obscene",
    "threat": "threat",
    "insult": "insult",
    "identity_attack": "identity_hate",
}
# labels kept under their own name in the response's extra categories
MODEL_EXTRA_LABELS = ("sexual_explicit",)

# Languages the model card claims (used by engine=auto; see model card README).
MODEL_CLAIMED_LANGUAGES = frozenset({
    "en", "de", "fr", "es", "pt", "it", "nl", "pl", "ru", "uk", "cs", "ro",
    "sv", "da", "fi", "hu", "el", "tr", "ar", "he", "fa", "hi", "bn", "ur",
    "zh", "ja", "ko", "vi", "th", "id", "sw", "am",
    # NOTE: 'ta' (Tamil) is deliberately ABSENT — the model card does not claim
    # Tamil coverage. Do not mark Tamil as supported by this model without
    # measured evidence (see PHASE2_MODEL_EVALUATION.md).
})

# Phase-2 coverage: language groups AURA itself measured on held-out data
# (data/phase2_eval, results in models/phase2_benchmark.json). The 'note' is
# surfaced to API clients so a language is never presented as fully supported
# just because the model accepts its characters.
#   validated   - measured on human-labeled data, clearly beats the legacy engine
#   experimental- measured, but with important caveats (see note)
MODEL_COVERAGE = {
    "en":       ("validated",    "held-out n=180 at the deployed threshold 0.55: F1 0.948 vs legacy 0.540, FPR 0.011, ROC-AUC 0.989 (textdetox)"),
    "hi":       ("validated",    "held-out n=180 at the deployed threshold 0.35: F1 0.638 vs legacy 0.065, FPR 0.044, ROC-AUC 0.861 (textdetox)"),
    "ta":       ("experimental", "held-out n=180: F1 0.529 vs legacy 0.021, FPR 0.144 (FPR-capped threshold 0.40); not claimed by the model card (Dravidian CodeMix)"),
    "ta-Latn":  ("experimental", "held-out n=180 at the deployed threshold 0.30: F1 0.245 vs legacy 0.104, FPR 0.033 — weak absolute performance; Tanglish remains experimental"),
    "bn":       ("experimental", "held-out n=143 at the deployed threshold 0.30: F1 0.624 vs legacy 0.000, FPR 0.122; labels are weak LLM annotations, not human gold"),
    "ur":       ("experimental", "held-out n=180: F1 0.588 vs legacy 0.000 but FPR 0.256 (FPR-capped threshold 0.40) — still a high false-positive rate"),
}


def coverage_for(language_code: str) -> tuple[str, str]:
    """(status, note) for a language — 'unmeasured' when we have no evidence."""
    code = (language_code or "").strip()
    if code in MODEL_COVERAGE:
        return MODEL_COVERAGE[code]
    base = code.split("-")[0]
    if base in MODEL_COVERAGE:
        return MODEL_COVERAGE[base]
    if code in MODEL_CLAIMED_LANGUAGES or base in MODEL_CLAIMED_LANGUAGES:
        return ("model_card_claimed",
                "claimed by the model card but not independently evaluated by AURA")
    return ("unmeasured", "no AURA held-out evaluation for this language")


def _env(name: str, default: str) -> str:
    v = os.environ.get(name)
    return v if v not in (None, "") else default


class AdapterUnavailable(RuntimeError):
    """Raised when the pretrained model cannot serve a request."""


class ModelConfig:
    def __init__(self) -> None:
        self.engine = _env("AURA_PREDICTION_ENGINE", "legacy").strip().lower()
        self.model_id = _env("AURA_MODEL_ID", "Horizon-Labs/multilingual-toxicity-small")
        self.cache_dir = Path(_env("AURA_MODEL_CACHE", str(BASE_DIR / "models" / "hf_cache")))
        self.device = _env("AURA_MODEL_DEVICE", "cpu").strip().lower()
        self.max_length = int(_env("AURA_MODEL_MAX_LENGTH", "256"))
        self.timeout_s = float(_env("AURA_MODEL_TIMEOUT_S", "10"))
        self.batch_size = max(1, int(_env("AURA_MODEL_BATCH_SIZE", "16")))
        self.offline = _env("AURA_MODEL_OFFLINE", "0") == "1"
        self.eager_load = _env("AURA_MODEL_EAGER_LOAD", "0") == "1"
        self.threshold = float(_env("AURA_MODEL_THRESHOLD", "0.5"))
        self.tuned_path = Path(_env(
            "AURA_MODEL_TUNED_THRESHOLD",
            str(BASE_DIR / "models" / "tuned_threshold.json")))
        self._load_tuned()

    def _load_tuned(self) -> None:
        """Tuned threshold(s) selected on VALIDATION data beat the env default.

        File format (models/tuned_threshold.json):
          {"threshold": 0.45,                       # global fallback
           "per_language": {"en": 0.55, "ta": 0.35, ...},
           "rationale": "..."}

        Parsing rules (C-F-5, see tests_audit_threshold_phase41.py):
          * per-language entries are parsed INDEPENDENTLY of the global entry,
            so a missing/malformed global threshold can never discard them;
          * a missing/malformed global entry follows the DOCUMENTED fallback
            (AURA_MODEL_THRESHOLD, default 0.5) - never a silent total reset;
          * a valid language-specific value is NEVER overridden by the global
            one (threshold_for() always prefers ``per_language``);
          * unexpected errors are LOGGED through this module's logger and then
            fall back to the documented default - they are not swallowed.
        """
        self.per_language: dict[str, float] = {}
        # Documented fallback, applied up front so every exit path leaves the
        # config in a coherent state (rationale/source always defined).
        self.threshold_rationale = "default 0.5 (not tuned yet)"
        self.threshold_source = "default"
        try:
            if not self.tuned_path.exists():
                return
            try:
                payload = json.loads(self.tuned_path.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001 - log then documented fallback
                LOG.warning(
                    "AURA: cannot parse tuned threshold file %s (%s: %s); "
                    "falling back to documented default threshold %s",
                    self.tuned_path, type(exc).__name__, exc, self.threshold)
                return
            if not isinstance(payload, dict):
                LOG.warning(
                    "AURA: tuned threshold file %s is not a JSON object "
                    "(%s); falling back to documented default threshold %s",
                    self.tuned_path, type(payload).__name__, self.threshold)
                return

            # --- global entry: missing/malformed -> documented fallback ------
            # Never raises: a bad global must not discard per-language values.
            try:
                raw_global = payload.get("threshold")
                t = None if raw_global is None else float(raw_global)
            except (TypeError, ValueError):
                t = None
            if t is not None and 0.0 < t < 1.0:
                self.threshold = t
                self.threshold_rationale = str(
                    payload.get("rationale", "tuned on validation split"))
                self.threshold_source = "tuned_validation"
            elif raw_global is not None:
                LOG.warning(
                    "AURA: global tuned threshold %r in %s is invalid; using "
                    "documented default %s (per-language values still apply)",
                    raw_global, self.tuned_path, self.threshold)

            # --- per-language entries: parsed even if the global one is bad ---
            raw_per_lang = payload.get("per_language")
            if raw_per_lang is None:
                raw_per_lang = {}
            elif not isinstance(raw_per_lang, dict):
                LOG.warning(
                    "AURA: 'per_language' in %s is not an object (%s); "
                    "ignoring it", self.tuned_path, type(raw_per_lang).__name__)
                raw_per_lang = {}
            for lang, val in raw_per_lang.items():
                try:
                    fv = float(val)
                    if 0.0 < fv < 1.0:
                        self.per_language[str(lang)] = fv
                except (TypeError, ValueError):
                    continue
            if self.per_language:
                self.threshold_rationale += " | per-language thresholds applied"
        except Exception as exc:  # noqa: BLE001 - unexpected -> LOGGED fallback
            LOG.warning(
                "AURA: unexpected error loading tuned thresholds from %s "
                "(%s: %s); using documented default threshold %s and keeping "
                "%d valid per-language value(s)",
                self.tuned_path, type(exc).__name__, exc, self.threshold,
                len(self.per_language))
            if not self.threshold_rationale:
                self.threshold_rationale = "default 0.5 (not tuned yet)"
            self.threshold_source = self.threshold_source or "default"

    def threshold_for(self, language_code: str | None) -> float:
        """Per-language tuned threshold, falling back to the global one."""
        code = (language_code or "").strip()
        if code in self.per_language:
            return self.per_language[code]
        base = code.split("-")[0]
        if base in self.per_language:
            return self.per_language[base]
        return self.threshold

    def as_dict(self) -> dict[str, Any]:
        return {
            "engine": self.engine,
            "model_id": self.model_id,
            "device": self.device,
            "max_length": self.max_length,
            "threshold": self.threshold,
            "per_language_thresholds": self.per_language,
            "threshold_source": self.threshold_source,
            "threshold_rationale": self.threshold_rationale,
            "offline": self.offline,
            "cache_dir": str(self.cache_dir),
        }


class HFToxicityAdapter:
    """Lazy, thread-safe single-load adapter for a sigmoid multi-label model."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._model = None
        self._tokenizer = None
        self._config: Optional[ModelConfig] = None
        self._status = "not_loaded"
        self._error: str = ""
        self._labels: list[str] = []
        self._load_ms: float = 0.0
        self._torch = None
        self._next_retry: float = 0.0  # failure backoff (see _ensure_loaded)

    # ---------------- configuration / status ----------------
    @property
    def status(self) -> str:
        return self._status

    @property
    def error(self) -> str:
        return self._error

    @property
    def labels(self) -> list[str]:
        return list(self._labels)

    def info(self) -> dict[str, Any]:
        cfg = self._config
        return {
            "status": self._status,
            "error": self._error or None,
            "model_id": cfg.model_id if cfg else None,
            "labels": list(self._labels),
            "device": cfg.device if cfg else None,
            "max_length": cfg.max_length if cfg else None,
            "threshold": cfg.threshold if cfg else None,
            "per_language_thresholds": (cfg.per_language if cfg else {}),
            "threshold_source": cfg.threshold_source if cfg else None,
            "threshold_rationale": cfg.threshold_rationale if cfg else None,
            "load_ms": round(self._load_ms, 1),
            "offline": cfg.offline if cfg else None,
            "engine": cfg.engine if cfg else None,
            "weights_available": self._status == "ready",
        }

    # ---------------- loading ----------------
    def _ensure_loaded(self) -> ModelConfig:
        cfg = ModelConfig()
        self._config = cfg
        if self._status == "ready":
            return cfg
        with self._lock:
            if self._status == "ready":
                return cfg
            if self._status == "loading":
                raise AdapterUnavailable("model is loading")
            # After a failed load, do NOT retry on every request (a cold load
            # can take ~20s and a broken config would stall every prediction).
            # AURA_MODEL_RETRY_S (default 60) controls the backoff.
            if self._status == "unavailable" and time.time() < self._next_retry:
                raise AdapterUnavailable(
                    self._error or "model unavailable (retry backoff active)")
            self._status = "loading"
            t0 = time.time()
            try:
                if cfg.offline:
                    os.environ.setdefault("HF_HUB_OFFLINE", "1")
                    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
                import torch
                from transformers import AutoModelForSequenceClassification, AutoTokenizer

                self._torch = torch
                cfg.cache_dir.mkdir(parents=True, exist_ok=True)
                self._tokenizer = AutoTokenizer.from_pretrained(
                    cfg.model_id, cache_dir=str(cfg.cache_dir))
                self._model = AutoModelForSequenceClassification.from_pretrained(
                    cfg.model_id, cache_dir=str(cfg.cache_dir))
                self._model.eval()
                self._device = torch.device(
                    cfg.device if cfg.device != "auto" else
                    ("cuda" if torch.cuda.is_available() else "cpu"))
                if cfg.device == "cuda" and not torch.cuda.is_available():
                    self._device = torch.device("cpu")
                self._model.to(self._device)
                id2label = getattr(self._model.config, "id2label", None) or {}
                self._labels = [str(id2label[k]).lower() for k in sorted(
                    (int(k) for k in id2label.keys()))] if id2label else []
                self._load_ms = (time.time() - t0) * 1000
                self._status = "ready"
                self._error = ""
            except Exception as e:  # noqa: BLE001 - any failure => unavailable
                self._status = "unavailable"
                self._error = f"{type(e).__name__}: {e}"[:300]
                self._model = None
                self._tokenizer = None
                try:
                    retry_s = float(_env("AURA_MODEL_RETRY_S", "60"))
                except ValueError:
                    retry_s = 60.0
                self._next_retry = time.time() + max(0.0, retry_s)
            return cfg

    def reset(self) -> None:
        """Testing hook: drop the loaded model (does not delete cache files)."""
        with self._lock:
            self._model = None
            self._tokenizer = None
            self._status = "not_loaded"
            self._error = ""
            self._next_retry = 0.0

    # ---------------- inference ----------------
    def predict(self, texts: list[str]) -> dict[str, Any]:
        """Batch predict. Returns a dict describing the run.

        Raises AdapterUnavailable for empty input, oversized input, timeout or
        any load/inference failure — callers fall back to the legacy engine.
        """
        clean = [t for t in (texts if isinstance(texts, list) else []) if isinstance(t, str)]
        if not clean:
            raise AdapterUnavailable("no text to classify")
        if len(clean) > 1000:
            raise AdapterUnavailable("batch too large for model adapter (max 1000)")
        cfg = self._ensure_loaded()
        if self._status != "ready":
            raise AdapterUnavailable(self._error or "model unavailable")
        torch = self._torch
        t0 = time.time()
        try:
            outputs: list[dict[str, float]] = []
            for i in range(0, len(clean), cfg.batch_size):
                chunk = clean[i:i + cfg.batch_size]
                chunk_t0 = time.time()  # deadline is PER CHUNK, not cumulative:
                # a 500-item batch must not be killed by an aggregate budget,
                # but each chunk must still finish within the timeout.
                enc = self._tokenizer(
                    chunk, return_tensors="pt", padding=True, truncation=True,
                    max_length=cfg.max_length)
                enc = {k: v.to(self._device) for k, v in enc.items()}
                with torch.no_grad():
                    logits = self._model(**enc).logits
                probs = torch.sigmoid(logits).detach().cpu().tolist()
                for row in probs:
                    outputs.append({
                        label: float(val)
                        for label, val in zip(self._labels, row)
                    }) if self._labels else outputs.append(
                        {"score": float(row[0])})
                self._check_deadline(chunk_t0, cfg)
            latency_ms = (time.time() - t0) * 1000
            return {
                "ok": True,
                "scores": outputs,
                "model_id": cfg.model_id,
                "model_version": self._model_version(),
                "threshold": cfg.threshold,
                "per_language_thresholds": dict(cfg.per_language),
                "threshold_source": cfg.threshold_source,
                "threshold_rationale": cfg.threshold_rationale,
                "latency_ms": round(latency_ms / max(1, len(clean)), 2),
                "labels": list(self._labels),
                "problem_type": str(getattr(self._model.config, "problem_type", "") or ""),
            }
        except AdapterUnavailable:
            raise
        except Exception as e:  # noqa: BLE001
            raise AdapterUnavailable(f"inference failed: {type(e).__name__}: {e}"[:300])

    def _model_version(self) -> str:
        """Stable-ish version string: short hash of model id + load time bucket."""
        import hashlib
        cfg = self._config
        h = hashlib.sha256((cfg.model_id if cfg else "?").encode()).hexdigest()[:8]
        return f"{h}"

    def _check_deadline(self, chunk_t0: float, cfg: ModelConfig) -> None:
        if cfg.timeout_s > 0 and time.time() - chunk_t0 > cfg.timeout_s:
            raise AdapterUnavailable(f"inference timeout (> {cfg.timeout_s}s per batch chunk)")


# module-level singleton (one load per process)
ADAPTER = HFToxicityAdapter()


def engine_mode() -> str:
    return _env("AURA_PREDICTION_ENGINE", "legacy").strip().lower()


def should_try_model(language_code: str) -> bool:
    """Whether engine selection asks for the pretrained model for this language.

    legacy - never (existing Naive Bayes / lexicon engine stays the default)
    hf     - always (explicit override for testing and controlled rollout)
    auto   - only where AURA or the model card has evidence for the language:
             our six measured groups (incl. Tamil/Tanglish, which the card does
             not claim) plus the card's claimed languages.
    """
    mode = engine_mode()
    if mode == "hf":
        return True
    if mode == "auto":
        code = (language_code or "en").strip()
        base = code.split("-")[0]
        return (code in MODEL_COVERAGE or base in MODEL_COVERAGE
                or code in MODEL_CLAIMED_LANGUAGES
                or base in MODEL_CLAIMED_LANGUAGES)
    return False


def categorise(scores: dict[str, float], threshold: float) -> dict[str, Any]:
    """Map raw model scores onto the AURA prediction contract.

    Multi-label semantics: every label is an independent sigmoid score; the
    binary decision uses ONLY the 'toxicity' score against `threshold`.
    """
    toxic_score = float(scores.get("toxicity", scores.get("score", 0.0)))
    categories = {}
    for model_label, aura_label in MODEL_LABEL_MAP.items():
        if model_label in scores:
            categories[aura_label] = round(float(scores[model_label]), 4)
    for extra in MODEL_EXTRA_LABELS:
        if extra in scores:
            categories[extra] = round(float(scores[extra]), 4)
    categories["non_toxic"] = round(max(0.0, 1.0 - toxic_score), 4)
    label = "toxic" if toxic_score >= threshold else "non_toxic"
    margin = abs(toxic_score - threshold)
    if margin < 0.05:
        decision_status = "uncertain"
    else:
        decision_status = "predicted"
    return {
        "label": label,
        "toxicity_score": round(toxic_score, 4),
        "threshold": threshold,
        "categories": categories,
        "decision_status": decision_status,
        "margin": round(margin, 4),
    }


def language_gate(language_code: str) -> tuple[bool, str]:
    """(model_allowed, reason). Tamil is NOT claimed by the model card."""
    code = (language_code or "").strip() or "en"
    base = code.split("-")[0]
    if code in MODEL_CLAIMED_LANGUAGES or base in MODEL_CLAIMED_LANGUAGES:
        return True, "model_card_language"
    return False, f"language '{code}' not claimed by model card"
