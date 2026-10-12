"""Phase 3 benchmark: legacy engine vs pretrained model, per language.

Fixes the Phase 2 threshold-selection defect and reports the full Phase 3
metric matrix on the SAME held-out test splits.

Defect fixed
------------
`benchmark_phase2.tune_threshold` / `tune_global` started their sweep at
``t = 0.30``.  Any language whose validation optimum lies below 0.30 was
pinned to the grid edge (ta-Latn was selected at exactly 0.30, the floor) and
could never trade a little validation FPR for recall.  The sweep now starts at
0.05 (env-overridable) and keeps the Phase 2 selection rule untouched:

    max toxic F1  subject to  validation FPR <= AURA_TUNE_FPR_CAP (0.15)
    tie-break -> higher threshold (fewer false positives)

Thresholds are selected on VALIDATION only.  The held-out test split is used
exactly once, for reporting, and never for selection.

Adds per language, for BOTH engines: n, positives, negatives, accuracy,
precision, recall, toxic F1, macro F1, confusion matrix, FPR, ROC-AUC, PR-AUC,
latency; plus validation-vs-test threshold drift, memory, and the
uncertainty / unsupported-language behaviour contract.

Usage:
    python benchmark_phase3.py                     # report only
    python benchmark_phase3.py --write-thresholds  # also persist tuned values
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "models"
GROUPS = ("en", "ta", "ta-Latn", "hi", "bn", "ur")

# Offline benchmarking runs many texts per call on a shared CPU. The adapter's
# serving guard (10s per 16-text chunk) is correct for requests but can trip on
# long Indic text, so the benchmark relaxes it via ENV ONLY - the deployed
# defaults in model_adapter.py are unchanged.
os.environ.setdefault("AURA_MODEL_TIMEOUT_S", "180")
os.environ.setdefault("AURA_MODEL_BATCH_SIZE", "8")

SWEEP_LO = float(os.environ.get("AURA_SWEEP_LO", "0.05"))
SWEEP_HI = float(os.environ.get("AURA_SWEEP_HI", "0.90"))
SWEEP_STEP = float(os.environ.get("AURA_SWEEP_STEP", "0.05"))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


_SCORE_CACHE: dict[tuple, tuple] = {}


def cached_scores(group: str, split: str, texts: list[str]):
    """Score a split once per run; the pooled pass reuses the same scores."""
    key = (group, split)
    if key not in _SCORE_CACHE:
        _SCORE_CACHE[key] = raw_scores(texts)
    return _SCORE_CACHE[key]


def raw_scores(texts: list[str]):
    """Raw per-text toxicity scores + timing from the cached adapter."""
    import model_adapter as ma
    t0 = time.time()
    res = ma.ADAPTER.predict(texts)
    wall = (time.time() - t0) * 1000.0
    scores = [float(s.get("toxicity", 0.0)) for s in res["scores"]]
    return scores, wall / max(1, len(texts)), res


def sweep(y: list[int], scores: list[float]) -> dict:
    """Threshold sweep over the full feasible range (not just >= 0.30)."""
    import benchmark_phase2 as b2
    out: dict[float, dict] = {}
    t = SWEEP_LO
    while t <= SWEEP_HI + 1e-9:
        preds = [1 if s >= t else 0 for s in scores]
        m = b2.metrics(y, preds, scores)
        out[round(t, 3)] = {
            "toxic_f1": m["toxic_f1"], "toxic_recall": m["toxic_recall"],
            "toxic_precision": m["toxic_precision"], "fpr": m["fpr"],
            "accuracy": m["accuracy"],
        }
        t += SWEEP_STEP
    return out


def pick(sweep_map: dict, cap: float):
    """Phase 2 selection rule, unchanged: max toxic F1 under an FPR budget."""
    import benchmark_phase2 as b2
    return b2.select_threshold(sweep_map, cap)


def main() -> int:
    import benchmark_phase2 as b2
    import model_adapter as ma

    write_thresholds = "--write-thresholds" in sys.argv
    cap = b2.fpr_cap()

    print("== Phase 3 benchmark: legacy vs pretrained model (per language) ==")
    print(f"model      : {ma.ModelConfig().model_id}")
    print(f"sweep      : {SWEEP_LO} .. {SWEEP_HI} step {SWEEP_STEP} "
          f"(validation only)")
    print(f"fpr cap    : {cap}")

    mem_before = b2.mem_mb()
    entry = {
        "generated_at": now_iso(),
        "model": {"model_id": ma.ModelConfig().model_id,
                  "sweep_range": [SWEEP_LO, SWEEP_HI, SWEEP_STEP],
                  "fpr_cap": cap,
                  "selection_rule": "max toxic F1 with val FPR <= cap "
                                    "(tie-break higher threshold); validation only"},
        "phase2_thresholds": (json.loads((OUT / "tuned_threshold.json").read_text(
            encoding="utf-8")).get("per_language", {})
            if (OUT / "tuned_threshold.json").is_file() else {}),
        "groups": {},
    }
    tuned: dict[str, float] = {}
    all_ok = True

    for g in GROUPS:
        val = b2.load_split(g, "val")
        test = b2.load_split(g, "test")
        if not val or not test:
            print(f"{g:<8} SKIP (missing split)")
            continue

        # ---------- validation: sweep + select (test never consulted) ------
        v_scores, v_lat, _ = cached_scores(g, "val", [r["text"] for r in val])
        v_y = [r["label"] for r in val]
        v_sweep = sweep(v_y, v_scores)
        thr, rule = pick(v_sweep, cap)
        sel = v_sweep[thr]
        tuned[g] = thr

        # ---------- held-out test: report only ----------------------------
        t_scores, t_lat, _ = cached_scores(g, "test", [r["text"] for r in test])
        t_y = [r["label"] for r in test]
        model = b2.metrics(t_y, [1 if s >= thr else 0 for s in t_scores], t_scores)
        model["latency_ms_per_text"] = round(t_lat, 2)
        model["threshold_used"] = thr

        lp, ls, l_lat = b2.legacy_predict([r["text"] for r in test])
        legacy = b2.metrics(t_y, lp, ls)
        legacy["latency_ms_per_text"] = round(l_lat, 2)

        # drift: where would the test set have preferred a threshold?
        t_sweep = sweep(t_y, t_scores)
        t_thr_opt, _ = pick(t_sweep, cap)
        drift = {
            "val_selected_threshold": thr,
            "test_optimal_threshold": t_thr_opt,
            "test_fpr_at_val_threshold": model["fpr"],
            "test_fpr_cap": cap,
            "test_fpr_exceeds_cap": model["fpr"] > cap,
            "test_f1_at_own_optimum": t_sweep[t_thr_opt]["toxic_f1"],
            "test_f1_at_val_threshold": model["toxic_f1"],
        }
        if model["fpr"] > cap:
            all_ok = False

        phase2_thr = entry["phase2_thresholds"].get(g)
        entry["groups"][g] = {
            "status": "evaluated",
            "val_rows": len(val), "test_rows": len(test),
            "val_positives": sum(v_y), "test_positives": sum(t_y),
            "test_negatives": len(t_y) - sum(t_y),
            "validation": {"threshold": thr, "rule": rule,
                           "toxic_f1": sel["toxic_f1"],
                           "toxic_recall": sel["toxic_recall"],
                           "toxic_precision": sel["toxic_precision"],
                           "fpr": sel["fpr"],
                           "latency_ms_per_text": round(v_lat, 2)},
            "test_model": model,
            "test_legacy": legacy,
            "threshold_drift": drift,
            "phase2_threshold": phase2_thr,
            "validation_sweep": {str(k): v for k, v in v_sweep.items()},
            "delta_toxic_f1_vs_phase2_threshold": (
                round(model["toxic_f1"] - (t_sweep.get(phase2_thr, {}).get(
                    "toxic_f1", model["toxic_f1"]) if phase2_thr else
                    model["toxic_f1"]), 4)),
        }
        print(f"{g:<8} thr {thr:<5} (val F1 {sel['toxic_f1']:.3f} FPR "
              f"{sel['fpr']:.3f})  test F1 {model['toxic_f1']:.3f} "
              f"rec {model['toxic_recall']:.3f} FPR {model['fpr']:.3f} "
              f"macroF1 {model['macro_f1']:.3f} AUC {model['roc_auc']} "
              f"| legacy F1 {legacy['toxic_f1']:.3f} "
              f"| phase2 thr {phase2_thr} -> "
              f"{entry['groups'][g]['delta_toxic_f1_vs_phase2_threshold']:+.3f} F1")

    # ---------- pooled global threshold (validation only) -----------------
    pooled_y, pooled_s = [], []
    for g in GROUPS:
        val = b2.load_split(g, "val")
        if not val:
            continue
        s, _, _ = _SCORE_CACHE.get((g, "val")) or raw_scores([r["text"] for r in val])
        pooled_y.extend(r["label"] for r in val)
        pooled_s.extend(s)
    if pooled_y:
        p_sweep = sweep(pooled_y, pooled_s)
        p_thr, p_rule = pick(p_sweep, cap)
        entry["global_validation"] = {
            "threshold": p_thr, "rule": p_rule, "n": len(pooled_y),
            "positives": sum(pooled_y),
            "toxic_f1": p_sweep[p_thr]["toxic_f1"],
            "fpr": p_sweep[p_thr]["fpr"],
        }
        entry["global_validation"]["sweep"] = {
            str(k): v for k, v in p_sweep.items()}
        print(f"pooled   thr {p_thr:<5} val F1 {p_sweep[p_thr]['toxic_f1']:.3f} "
              f"FPR {p_sweep[p_thr]['fpr']:.3f} (n={len(pooled_y)})")

    # ---------- uncertainty / unsupported-language contract ---------------
    entry["uncertainty_and_coverage"] = {
        "coverage": {lang: {"status": ma.coverage_for(lang)}
                     for lang in sorted(set(list(ma.MODEL_COVERAGE.keys())
                                             + ["te", "ml", "kn", "mr", "gu", "pa"]))},
        "claimed_languages_count": len(ma.MODEL_CLAIMED_LANGUAGES),
        "claimed_excludes_ta": "ta" not in ma.MODEL_CLAIMED_LANGUAGES,
        "evaluated_groups": list(GROUPS),
        "decision_status_rule": {
            "predicted|uncertain": "measured coverage; margin < 0.05 -> uncertain "
                                   "(action HUMAN_REVIEW unless RESTRICT/TEMPORARY_BLOCK)",
            "experimental": "coverage unmeasured/model_card_claimed -> action HUMAN_REVIEW",
            "fallback": "adapter failure -> legacy result stands, sanitised model_error",
            "legacy": "default engine; no toxicity_score field",
        },
        "unsupported_language_behaviour":
            "languages outside the coverage map fall back to the legacy engine "
            "under auto, or are marked experimental + HUMAN_REVIEW under hf; "
            "never silently claimed as supported",
    }

    entry["memory_mb"] = {"before": round(mem_before, 1),
                          "after": round(b2.mem_mb(), 1)}
    entry["fpr_cap_respected_on_test"] = all_ok
    entry["tuned_per_language"] = tuned

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "phase3_benchmark.json").write_text(
        json.dumps(entry, indent=2, ensure_ascii=False), encoding="utf-8")

    if write_thresholds and tuned:
        payload = {
            "threshold": entry.get("global_validation", {}).get("threshold", 0.35),
            "per_language": tuned,
            "source": "phase3_validation_sweep",
            "rationale": (f"validation-only sweep {SWEEP_LO}..{SWEEP_HI} step "
                          f"{SWEEP_STEP} (Phase 2 floor was 0.30 and truncated "
                          f"low-recall languages); selection = max toxic F1 "
                          f"subject to validation FPR <= {cap}; held-out test "
                          f"never used for selection"),
            "tuned_at": now_iso(),
        }
        (OUT / "tuned_threshold.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"wrote tuned thresholds -> {OUT / 'tuned_threshold.json'}")
    print(f"wrote {OUT / 'phase3_benchmark.json'}")
    print(f"test FPR within cap for every language: {all_ok}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
