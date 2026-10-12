"""Phase 2 — comparable evaluation: AURA legacy engine vs pretrained model.

Runs BOTH engines on the SAME held-out per-language test sets built by
prepare_phase2_eval.py and reports the required metrics:

    accuracy, toxic-class precision/recall/F1, macro-F1, confusion matrix,
    false-positive rate, ROC-AUC and PR-AUC (score-based, where supported),
    per-language results, mean inference latency.

Threshold selection uses ONLY the validation split (test stays untouched):
    --tune  sweeps thresholds on <group>_val.csv and writes
            models/tuned_threshold.json (maximises toxic F1, tie-break:
            higher threshold, i.e. fewer false positives).

Usage:
    python benchmark_phase2.py                 # full run, default thresholds
    python benchmark_phase2.py --tune           # tune on val, then test
    python benchmark_phase2.py --limit 40       # quick smoke (per split)
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

EVAL = HERE / "data" / "phase2_eval"
OUT = HERE / "models"
GROUPS = ("en", "ta", "ta-Latn", "hi", "bn", "ur")


# ------------------------------------------------------------------ helpers
def load_split(group: str, split: str, limit: int | None = None) -> list[dict]:
    path = EVAL / f"{group}_{split}.csv"
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            rows.append({"text": r["text"], "label": int(r["label"])})
    return rows[:limit] if limit else rows


def metrics(y_true: list[int], y_pred: list[int], scores: list[float]) -> dict:
    n = len(y_true)
    tp = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 1)
    fp = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 1)
    fn = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 0)
    tn = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 0)
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    nprec = tn / (tn + fn) if tn + fn else 0.0
    nrec = tn / (tn + fp) if tn + fp else 0.0
    nf1 = 2 * nprec * nrec / (nprec + nrec) if nprec + nrec else 0.0
    acc = (tp + tn) / n if n else 0.0
    fpr = fp / (fp + tn) if fp + tn else 0.0
    roc_auc = _auc(y_true, scores)
    pr_auc = _pr_auc(y_true, scores)
    return {
        "n": n, "positives": sum(y_true), "negatives": n - sum(y_true),
        "accuracy": round(acc, 4),
        "toxic_precision": round(prec, 4), "toxic_recall": round(rec, 4),
        "toxic_f1": round(f1, 4), "macro_f1": round((f1 + nf1) / 2, 4),
        "fpr": round(fpr, 4),
        "confusion_matrix": {"labels": ["non_toxic", "toxic"],
                             "matrix": [[tn, fp], [fn, tp]]},
        "roc_auc": round(roc_auc, 4) if roc_auc is not None else None,
        "pr_auc": round(pr_auc, 4) if pr_auc is not None else None,
    }


def _auc(y: list[int], s: list[float]) -> float | None:
    pos = [v for t, v in zip(y, s) if t == 1]
    neg = [v for t, v in zip(y, s) if t == 0]
    if not pos or not neg:
        return None
    # rank-based Mann-Whitney U
    pairs = sorted(zip(s, [1 if t else 0 for t in y]))
    ranks = {}
    i = 0
    while i < len(pairs):
        j = i
        while j < len(pairs) and pairs[j][0] == pairs[i][0]:
            j += 1
        avg = (i + j + 1) / 2.0
        for k in range(i, j):
            ranks[k] = avg
        i = j
    rank_sum_pos = sum(ranks[k] for k, (_, lab) in enumerate(pairs) if lab == 1)
    n_pos, n_neg = len(pos), len(neg)
    return (rank_sum_pos - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)


def _pr_auc(y: list[int], s: list[float]) -> float | None:
    if sum(y) == 0 or sum(y) == len(y):
        return None
    pairs = sorted(zip(s, y), key=lambda x: -x[0])
    tp = fp = 0
    prev_recall = 0.0
    ap = 0.0
    n_pos = sum(y)
    last_s = None
    points = []
    for score, lab in pairs:
        if lab:
            tp += 1
        else:
            fp += 1
        points.append((score, tp, fp))
    # step-wise AP (ties handled by processing as they come)
    for idx, (score, tp, fp) in enumerate(points):
        if idx + 1 < len(points) and points[idx + 1][0] == score:
            continue
        recall = tp / n_pos
        precision = tp / (tp + fp)
        ap += (recall - prev_recall) * precision
        prev_recall = recall
    return ap


def tune_threshold(group: str) -> float:
    """Pick threshold on VALIDATION only: max toxic F1 subject to the FPR cap."""
    import model_adapter as ma
    rows = load_split(group, "val")
    if not rows:
        return 0.5
    texts = [r["text"] for r in rows]
    y = [r["label"] for r in rows]
    res = ma.ADAPTER.predict(texts)
    scores = [float(s.get("toxicity", 0.0)) for s in res["scores"]]
    sweep: dict[float, dict] = {}
    t = 0.30
    while t <= 0.801:
        preds = [1 if s >= t else 0 for s in scores]
        sweep[round(t, 2)] = metrics(y, preds, scores)
        t += 0.05
    thr, _rule = select_threshold(sweep, fpr_cap())
    return thr


# Selection rule for tuned thresholds (validation split ONLY, never test):
# maximise toxic F1 SUBJECT TO validation FPR <= cap, tie-break higher threshold.
# Rationale (Phase 2 §7): pure F1-max picked thresholds that flagged ~30-40% of
# benign Tamil/Urdu comments on the held-out test split. A moderation system
# that silences a third of legitimate speech is a worse trade-off than one that
# misses some toxic comments, so the sweep optimises recall/precision only
# inside a false-positive budget. Override with AURA_TUNE_FPR_CAP.
def fpr_cap() -> float:
    try:
        v = float(os.environ.get("AURA_TUNE_FPR_CAP", "0.15"))
    except ValueError:
        v = 0.15
    return max(0.0, min(1.0, v))


def select_threshold(sweep: dict[float, dict], cap: float) -> tuple[float, str]:
    """Pick (threshold, rule) from a sweep dict {thr: metrics} under an FPR cap.

    feasible  = thresholds with validation FPR <= cap  -> max toxic F1
    infeasible-> no threshold meets the cap            -> lowest FPR available
    """
    feasible = {t: m for t, m in sweep.items() if m["fpr"] <= cap + 1e-12}
    if feasible:
        best = max(feasible.items(),
                   key=lambda kv: (kv[1]["toxic_f1"], kv[0]))
        return best[0], f"max toxic F1 with val FPR <= {cap}"
    worst = min(sweep.items(), key=lambda kv: (kv[1]["fpr"], -kv[0]))
    return worst[0], f"no threshold met val FPR <= {cap}; chose lowest-FPR threshold"


def tune_global() -> tuple[float, dict]:
    """Pooled + per-language thresholds from ALL groups' validation splits (never test)."""
    import model_adapter as ma
    texts: list[str] = []
    y: list[int] = []
    per_group: dict = {}
    group_scores: dict[str, tuple[list[int], list[float]]] = {}
    for g in GROUPS:
        rows = load_split(g, "val")
        per_group[g] = len(rows)
        if not rows:
            continue
        texts.extend(r["text"] for r in rows)
        y.extend(r["label"] for r in rows)
    if not texts:
        return 0.5, {"error": "no validation data"}
    res = ma.ADAPTER.predict(texts)
    scores = [float(s.get("toxicity", 0.0)) for s in res["scores"]]

    def best_threshold(yy: list[int], ss: list[float]) -> tuple[float, dict]:
        sweep = {}
        t = 0.30
        while t <= 0.801:
            preds = [1 if s >= t else 0 for s in ss]
            m = metrics(yy, preds, ss)
            sweep[round(t, 2)] = {"toxic_f1": m["toxic_f1"],
                                  "toxic_recall": m["toxic_recall"],
                                  "toxic_precision": m["toxic_precision"],
                                  "fpr": m["fpr"]}
            t += 0.05
        thr, rule = select_threshold(sweep, fpr_cap())  # type: ignore[arg-type]
        sweep[thr]["selected"] = True
        return thr, {"sweep": sweep, "rule": rule, "fpr_cap": fpr_cap()}

    g_thr, g_meta = best_threshold(y, scores)
    g_sweep = g_meta["sweep"]
    detail = {"val_rows": len(texts), "per_group": per_group, "sweep": g_sweep,
              "selection_rule": g_meta["rule"], "fpr_cap": g_meta["fpr_cap"],
              "per_language": {}, "per_language_rule": {},
              "per_language_sweep": {}}
    # per-language thresholds (aligned to group index within the pooled arrays)
    idx = 0
    for g in GROUPS:
        n = per_group.get(g, 0)
        if n:
            yy = y[idx:idx + n]
            ss = scores[idx:idx + n]
            group_scores[g] = (yy, ss)
            thr_g, meta_g = best_threshold(yy, ss)
            detail["per_language"][g] = thr_g
            detail["per_language_sweep"][g] = meta_g["sweep"]
            detail["per_language_rule"][g] = meta_g["rule"]
        idx += n
    return g_thr, detail


def legacy_predict(texts: list[str]) -> tuple[list[int], list[float], float]:
    """AURA legacy engine (rule + lexicon), in-process, no DB writes."""
    import backend
    preds, scores = [], []
    t0 = time.time()
    for t in texts:
        req = backend.MessageIn(text=t, user_id="bench", conversation_id="bench")
        r = backend.result(req)
        risk = float(r.get("risk_score") or 0)
        preds.append(1 if backend.derived_overall(risk, 0.5) == "toxic" else 0)
        scores.append(risk / 100.0)
    total = (time.time() - t0) * 1000
    return preds, scores, total / max(1, len(texts))


def hf_predict(texts: list[str], group: str | None = None) -> tuple[list[int], list[float], float]:
    import model_adapter as ma
    res = ma.ADAPTER.predict(texts)
    # per-language tuned threshold when the group has one; else global
    thr = ma.ModelConfig().threshold_for(group) if group else res["threshold"]
    preds, scores = [], []
    for s in res["scores"]:
        tox = float(s.get("toxicity", 0.0))
        scores.append(tox)
        preds.append(1 if tox >= thr else 0)
    return preds, scores, res["latency_ms"]


def mem_mb() -> float:
    """Current process working-set size in MB (Windows: correct ctypes types)."""
    try:
        import ctypes
        from ctypes import wintypes

        class CMS(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        psapi = ctypes.windll.psapi
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE, ctypes.POINTER(CMS), wintypes.DWORD]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        k32 = ctypes.windll.kernel32
        k32.GetCurrentProcess.restype = wintypes.HANDLE
        buf = CMS()
        buf.cb = ctypes.sizeof(CMS)
        if psapi.GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(buf), buf.cb):
            return buf.WorkingSetSize / (1024 * 1024)
        return 0.0
    except Exception:
        return 0.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tune", action="store_true", help="tune threshold on validation first")
    ap.add_argument("--limit", type=int, default=None, help="rows per split (smoke)")
    ap.add_argument("--out", default=str(OUT / "phase2_benchmark.json"))
    args = ap.parse_args()

    import model_adapter as ma
    print("== Phase-2 benchmark: legacy engine vs pretrained model ==")
    print("engine env:", ma.ModelConfig().as_dict())

    results: dict = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                     "model": ma.ADAPTER.info(),
                     "groups": {}}
    mem_before = mem_mb()

    for g in GROUPS:
        val = load_split(g, "val", args.limit)
        test = load_split(g, "test", args.limit)
        entry: dict = {"val_rows": len(val), "test_rows": len(test)}
        if not test:
            entry["status"] = "NOT EVALUATED (no test data)"
            results["groups"][g] = entry
            print(f"[{g}] NOT EVALUATED (no test data)")
            continue

        # ---- threshold tuning on VALIDATION only (once, pooled, then reused)
        if args.tune and "tuned" not in results:
            thr, detail = tune_global()
            (OUT).mkdir(parents=True, exist_ok=True)
            payload = {
                "threshold": thr,
                "per_language": detail.get("per_language", {}),
                "rationale": (f"sweep 0.30..0.80 step 0.05 on POOLED validation "
                              f"splits of all 6 language groups "
                              f"(n={detail.get('val_rows', 0)}) + per-language sweeps "
                              f"from each group's validation split; selection = max "
                              f"toxic F1 subject to validation FPR <= "
                              f"{detail.get('fpr_cap', fpr_cap())} (tie-break: higher "
                              f"threshold); test split never touched"),
                "detail": {k: v for k, v in detail.items() if k != "per_language_sweep"},
                "tuned_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
            (OUT / "tuned_threshold.json").write_text(
                json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            cfg = ma.ModelConfig()  # re-read env + tuned file
            if ma.ADAPTER._config is not None:
                ma.ADAPTER._config.threshold = cfg.threshold
                ma.ADAPTER._config.threshold_source = cfg.threshold_source
                ma.ADAPTER._config.threshold_rationale = cfg.threshold_rationale
            results["tuned_threshold"] = payload
            print(f"tuned threshold -> {thr} ({payload['rationale'][:80]}...)")
            results["tuned"] = True

        texts = [r["text"] for r in test]
        y = [r["label"] for r in test]

        # ---- legacy
        lp, ls, l_lat = legacy_predict(texts)
        entry["legacy"] = metrics(y, lp, ls)
        entry["legacy"]["latency_ms_per_text"] = round(l_lat, 2)

        # ---- pretrained model
        try:
            mp, ms, m_lat = hf_predict(texts, group=g)
            entry["model"] = metrics(y, mp, ms)
            entry["model"]["latency_ms_per_text"] = round(m_lat, 2)
            entry["model"]["threshold_used"] = ma.ModelConfig().threshold_for(g)
            entry["status"] = "EVALUATED"
        except Exception as e:  # model unavailable -> honest NOT EVALUATED
            entry["model"] = {"error": str(e)[:200]}
            entry["status"] = "MODEL UNAVAILABLE"

        results["groups"][g] = entry
        L, M = entry["legacy"], entry.get("model", {})
        print(f"[{g}] n={entry['test_rows']} (+{L['positives']}/-{L['negatives']}) "
              f"| legacy acc={L['accuracy']} f1={L['toxic_f1']} rec={L['toxic_recall']} fpr={L['fpr']}"
              + (f" || model acc={M.get('accuracy')} f1={M.get('toxic_f1')} "
                 f"rec={M.get('toxic_recall')} fpr={M.get('fpr')}"
                 if "accuracy" in M else " || model N/A"))

    mem_after = mem_mb()
    results["memory_mb"] = {"before": round(mem_before, 1),
                            "after": round(mem_after, 1),
                            "delta": round(mem_after - mem_before, 1)}
    # capture adapter info AFTER the run so status/labels reflect the loaded model
    try:
        results["model"] = ma.ADAPTER.info()
    except Exception as e:
        results["model"] = {"error": str(e)[:200]}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(results, indent=2, ensure_ascii=False),
                              encoding="utf-8")
    print("results ->", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
