"""Phase 2 — reproducible evaluation-set builder for AURA.

Builds held-out, per-language-group evaluation sets from VERIFIED public
datasets (see DATASET_GUIDE.md for licenses/provenance). Nothing here touches
aura.db or any training data: outputs go to data/phase2_eval/ only.

Language groups produced (required by Phase 2 §2/§6):
    en      English
    ta      Tamil (native script)
    ta-Latn Tanglish / code-mixed Tamil in Latin script
    hi      Hindi (Devanagari)
    bn      Bengali script
    ur      Urdu script

Sources (all fetched live from the Hugging Face datasets-server / resolve API):
    en/hi   textdetox/multilingual_toxicity_dataset (OpenRAIL++)  binary `toxic`
    ta / ta-Latn
            community-datasets/offenseval_dravidian (CC-BY-4.0)
            Tamil-English code-mixed; labels 0=Not_offensive, 1-4=Offensive,
            5=not-Tamil (EXCLUDED). Script decides ta vs ta-Latn group.
    bn      Polygl0t/bengali-toxicity-qwen-annotations (Apache-2.0)
            1-5 rating (Qwen annotations = weak/synthetic labels; documented).
            score>=4 -> toxic, score<=2 -> non_toxic, score==3 -> EXCLUDED
            (ambiguous kept out of binary evaluation, Phase 3 §3.4).
    ur      Adnan855570/Urdu_Hate_Speech (MIT, expert-generated)  xlsx

Each group gets a stratified, seeded validation split (threshold tuning) and a
test split that stays untouched during tuning/model selection.

Usage:
    python prepare_phase2_eval.py --per-class 150       # default
    python prepare_phase2_eval.py --dry-run             # show plan only
"""
from __future__ import annotations

import argparse
import collections
import csv
import io
import json
import random
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "data" / "phase2_eval"
UA = {"User-Agent": "aura-eval-builder/1.0"}
SEED = 42

TA_SCRIPT = re.compile(r"[\u0b80-\u0bff]")
BN_SCRIPT = re.compile(r"[\u0980-\u09ff]")
UR_SCRIPT = re.compile(r"[\u0600-\u06ff\u0750-\u077f]")
HI_SCRIPT = re.compile(r"[\u0900-\u097f]")

GROUPS = ("en", "ta", "ta-Latn", "hi", "bn", "ur")


def http_json(url: str, timeout: int = 40):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def http_bytes(url: str, timeout: int = 90) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def hf_rows(dataset: str, config: str, split: str, offset: int, length: int,
            retries: int = 6) -> list[dict]:
    """One rows-API page with backoff (HF rate-limits anonymous paging and
    occasionally returns 5xx — both are transient and retried)."""
    q = urllib.parse.urlencode({"dataset": dataset, "config": config,
                                "split": split, "offset": offset, "length": length})
    url = "https://datasets-server.huggingface.co/rows?" + q
    delay = 2.0
    for attempt in range(retries):
        try:
            payload = http_json(url)
            return [x.get("row", {}) for x in payload.get("rows", [])]
        except Exception as e:
            msg = str(e)
            transient = ("429" in msg or "Too Many" in msg or "502" in msg
                         or "503" in msg or "504" in msg or "Bad Gateway" in msg)
            if transient and attempt < retries - 1:
                time.sleep(delay)
                delay = min(delay * 2, 30)
                continue
            print(f"  ! rows page failed at {offset}: {e}")
            return []
    return []


def page_all(dataset: str, config: str, split: str, want: int,
             offsets: list[int] | None = None) -> list[dict]:
    """Fetch `want` rows. textdetox splits are LABEL-SORTED, so callers must
    pass INTERLEAVED offsets or the quota silently fills with one class only.
    A failed page skips ahead instead of aborting the whole run."""
    out: list[dict] = []
    step = 100
    if offsets is None:
        offsets = list(range(0, 100_000, step))
    misses = 0
    for off in offsets:
        if len(out) >= want:
            break
        got = hf_rows(dataset, config, split, off, step)
        if not got:
            misses += 1
            if misses >= 6:      # give up after 6 straight failures
                break
            continue
        misses = 0
        out.extend(got)
        time.sleep(1.0)  # stay under the anonymous rate limit
    return out[:want]


def spread_offsets(total: int, pages: int) -> list[int]:
    """Evenly spread page offsets across a split of `total` rows."""
    step = 100
    if total <= pages * step:
        return list(range(0, total, step))
    stride = max(step, (total - step) // max(1, pages - 1))
    offs, off = [], 0
    while len(offs) < pages and off < total:
        offs.append(off)
        off += stride
    return offs


# ---------------------------------------------------------------- sources
# textdetox splits are label-sorted (en: 0s first then 1s; hi: 1s first then 0s),
# so we INTERLEAVE offsets from both ends of the split to reach both classes.
TEXTDETOX_TOTAL = 5000


def _interleaved_offsets(total: int, half: int = 1500, step: int = 100) -> list[int]:
    lo = list(range(0, half, step))
    hi = list(range(total - half, total, step))
    out: list[int] = []
    for a, b in zip(lo, reversed(hi)):
        out.extend((a, b))
    return out


def collect_en(per_class: int) -> list[dict]:
    raw = page_all("textdetox/multilingual_toxicity_dataset", "default", "en",
                   per_class * 10, offsets=_interleaved_offsets(TEXTDETOX_TOTAL))
    return [{"text": r.get("text", ""), "label": int(r.get("toxic") or 0),
             "source_row_id": f"textdetox-en-{i}"}
            for i, r in enumerate(raw) if (r.get("text") or "").strip()]


def collect_hi(per_class: int) -> list[dict]:
    raw = page_all("textdetox/multilingual_toxicity_dataset", "default", "hi",
                   per_class * 10, offsets=_interleaved_offsets(TEXTDETOX_TOTAL))
    return [{"text": r.get("text", ""), "label": int(r.get("toxic") or 0),
             "source_row_id": f"textdetox-hi-{i}"}
            for i, r in enumerate(raw) if (r.get("text") or "").strip()]


def collect_dravidian(per_class: int) -> list[dict]:
    """Tamil code-mixed; returns rows tagged later into ta / ta-Latn by script."""
    raw: list[dict] = []
    for split in ("train", "validation"):
        raw.extend(page_all("community-datasets/offenseval_dravidian", "tamil", split, 4000))
    out = []
    for i, r in enumerate(raw):
        text = (r.get("text") or "").strip()
        lab = r.get("label")
        if not text or lab is None:
            continue
        try:
            lab = int(lab)
        except (TypeError, ValueError):
            continue
        if lab == 5:      # 'not-Tamil' — not a toxicity label; excluded
            continue
        out.append({"text": text, "label": 1 if lab in (1, 2, 3, 4) else 0,
                    "source_row_id": f"dravidian-ta-{split}-{i}"})
    return out


def collect_bn(per_class: int) -> list[dict]:
    # Qwen-score dist skews to 1-2; page broadly (with 429 backoff) to find >=4.
    raw = page_all("Polygl0t/bengali-toxicity-qwen-annotations", "default", "train",
                   per_class * 12, offsets=list(range(0, 12000, 100)))
    out = []
    for i, r in enumerate(raw):
        text = (r.get("text") or "").strip()
        if not text:
            continue
        try:
            score = int(r.get("score"))
        except (TypeError, ValueError):
            continue
        if score >= 4:
            label = 1
        elif score <= 2:
            label = 0
        else:
            continue  # ambiguous score 3 excluded from binary evaluation
        out.append({"text": text, "label": label,
                    "source_row_id": f"bengali-qwen-{r.get('id', i)}"})
    return out


def collect_ur(per_class: int) -> list[dict]:
    url = ("https://huggingface.co/datasets/Adnan855570/Urdu_Hate_Speech/"
           "resolve/main/Urdu_Hate_Speech.xlsx")
    try:
        data = http_bytes(url)
    except Exception as e:
        print(f"  ! urdu download failed: {e}")
        return []
    try:
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True)
        ws = wb.active
        rows = ws.iter_rows(values_only=True)
        header = [str(c).strip().lower() if c else "" for c in next(rows)]
        # observed sheet: ['tag', 'combinedtweet'] (0/1 hate tag)
        ti = next((i for i, h in enumerate(header)
                   if h in ("text", "tweet", "comment", "sentence", "combinedtweet", "tweet_text")), None)
        li = next((i for i, h in enumerate(header)
                   if h in ("label", "hate", "hate_speech", "class", "tag")), None)
        if ti is None or li is None:
            print(f"  ! urdu sheet columns unexpected: {header}")
            return []
        out = []
        for i, row in enumerate(rows):
            if not row or len(row) <= max(ti, li):
                continue
            text = str(row[ti] or "").strip()
            if not text:
                continue
            raw_lab = row[li]
            try:
                label = int(float(raw_lab))
            except (TypeError, ValueError):
                s = str(raw_lab).strip().lower()
                if s in ("hate", "hateful", "offensive", "yes", "true", "toxic"):
                    label = 1
                elif s in ("no hate", "non-hate", "non hate", "normal", "no", "false", "not"):
                    label = 0
                else:
                    continue  # ambiguous mapping excluded
            out.append({"text": text, "label": 1 if label >= 1 else 0,
                        "source_row_id": f"urdu-hate-{i}"})
        return out
    except Exception as e:
        print(f"  ! urdu parse failed: {e}")
        return []


# ---------------------------------------------------------------- assembly
def stratify(rows: list[dict], per_class: int, seed: int = SEED):
    rng = random.Random(seed)
    by: dict[int, list[dict]] = {0: [], 1: []}
    for r in rows:
        by.setdefault(r["label"], []).append(r)
    picked = []
    for lab in (0, 1):
        grp = by.get(lab, [])
        rng.shuffle(grp)
        picked.extend(grp[:per_class])
    rng.shuffle(picked)
    return picked, {0: min(len(by.get(0, [])), per_class),
                    1: min(len(by.get(1, [])), per_class)}


def split_val_test(rows: list[dict], val_frac: float = 0.4, seed: int = SEED):
    """Stratified val/test split; test is later kept untouched during tuning."""
    rng = random.Random(seed + 7)
    by: dict[int, list[dict]] = {0: [], 1: []}
    for r in rows:
        by[r["label"]].append(r)
    val, test = [], []
    for lab in (0, 1):
        grp = by[lab]
        rng.shuffle(grp)
        n_val = max(1, int(round(len(grp) * val_frac))) if len(grp) > 2 else 0
        val.extend(grp[:n_val])
        test.extend(grp[n_val:])
    rng.shuffle(val)
    rng.shuffle(test)
    return val, test


def write_csv(path: Path, rows: list[dict], meta: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["id", "text", "language", "label", "source", "source_row_id",
              "source_url", "license", "split", "label_notes"]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-class", type=int, default=150)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    print(f"Phase-2 eval builder — {args.per_class}/class/group, seed={SEED}")
    if args.dry_run:
        print("would fetch:", ", ".join(GROUPS)); return 0

    OUT.mkdir(parents=True, exist_ok=True)
    manifest = {"generated_at": datetime.now(timezone.utc).isoformat(),
                "seed": SEED, "per_class": args.per_class, "groups": {}}
    ok_any = False

    def emit(group: str, rows: list[dict], source: dict, notes: str) -> None:
        nonlocal ok_any
        picked, counts = stratify(rows, args.per_class)
        if not picked:
            manifest["groups"][group] = {"status": "NO DATA", "error": notes}
            print(f"[{group}] NO DATA: {notes}")
            return
        val, test = split_val_test(picked)
        stamp = {"source": source, "label_notes": notes}
        for name, part in (("val", val), ("test", test)):
            for r in part:
                r.update({"language": group, "split": name, **stamp})
        write_csv(OUT / f"{group}_val.csv", val, stamp)
        write_csv(OUT / f"{group}_test.csv", test, stamp)
        manifest["groups"][group] = {
            "status": "OK",
            "source": source,
            "label_notes": notes,
            "fetched_rows": len(rows),
            "selected": {"toxic": counts[1], "non_toxic": counts[0]},
            "val_rows": len(val),
            "val_pos": sum(r["label"] for r in val),
            "val_neg": sum(1 - r["label"] for r in val),
            "test_rows": len(test),
            "test_pos": sum(r["label"] for r in test),
            "test_neg": sum(1 - r["label"] for r in test),
        }
        ok_any = True
        print(f"[{group}] val={len(val)} (+{manifest['groups'][group]['val_pos']}"
              f"/-{manifest['groups'][group]['val_neg']}) "
              f"test={len(test)} (+{manifest['groups'][group]['test_pos']}"
              f"/-{manifest['groups'][group]['test_neg']})")

    print("fetching en ...")
    emit("en", collect_en(args.per_class), {
        "dataset": "textdetox/multilingual_toxicity_dataset",
        "url": "https://huggingface.co/datasets/textdetox/multilingual_toxicity_dataset",
        "license": "OpenRAIL++"}, "binary column `toxic` (0/1) used as-is")

    print("fetching hi ...")
    emit("hi", collect_hi(args.per_class), {
        "dataset": "textdetox/multilingual_toxicity_dataset",
        "url": "https://huggingface.co/datasets/textdetox/multilingual_toxicity_dataset",
        "license": "OpenRAIL++"}, "binary column `toxic` (0/1) used as-is")

    print("fetching dravidian tamil (ta / ta-Latn split by script) ...")
    dr = collect_dravidian(args.per_class)
    ta_rows = [r for r in dr if TA_SCRIPT.search(r["text"])]
    latn_rows = [r for r in dr if not TA_SCRIPT.search(r["text"])]
    emit("ta", ta_rows, {
        "dataset": "community-datasets/offenseval_dravidian",
        "url": "https://huggingface.co/datasets/community-datasets/offenseval_dravidian",
        "license": "CC-BY-4.0"},
        "label 0=Not_offensive -> 0; labels 1-4=Offensive* -> 1; label 5 (not-Tamil) excluded; native Tamil script rows only")
    emit("ta-Latn", latn_rows, {
        "dataset": "community-datasets/offenseval_dravidian",
        "url": "https://huggingface.co/datasets/community-datasets/offenseval_dravidian",
        "license": "CC-BY-4.0"},
        "same labels as `ta`; rows WITHOUT Tamil script (Tanglish/code-mixed Latin) only")

    print("fetching bn ...")
    emit("bn", collect_bn(args.per_class), {
        "dataset": "Polygl0t/bengali-toxicity-qwen-annotations",
        "url": "https://huggingface.co/datasets/Polygl0t/bengali-toxicity-qwen-annotations",
        "license": "Apache-2.0"},
        "WEAK LABELS (Qwen annotations): score>=4 -> toxic, <=2 -> non_toxic, score 3 excluded; human review not available")

    print("fetching ur ...")
    emit("ur", collect_ur(args.per_class), {
        "dataset": "Adnan855570/Urdu_Hate_Speech",
        "url": "https://huggingface.co/datasets/Adnan855570/Urdu_Hate_Speech",
        "license": "MIT"}, "expert-generated hate-speech labels mapped to binary; unmappable values excluded")

    manifest["generated_by"] = "prepare_phase2_eval.py"
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print("manifest ->", OUT / "manifest.json")
    return 0 if ok_any else 1


if __name__ == "__main__":
    sys.exit(main())
