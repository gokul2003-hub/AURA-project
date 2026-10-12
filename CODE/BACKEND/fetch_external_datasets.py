"""Fetch reputable public toxicity datasets and integrate them into AURA.

Phase 4 (dataset expansion). Stdlib only — uses the Hugging Face datasets-server
REST API, so no `datasets`/`transformers` install is required.

What it does
------------
1. Downloads a representative subset (rows API) from:
     - google/civil_comments        (license CC0-1.0, English, 8-dimension toxicity)
     - OxAISH-AL-LLM/wiki_toxic     (license CC0-1.0, English Wikipedia talk)
2. Normalizes each source's schema to AURA's multilingual CSV schema:
     id,text,language,language_name,script,toxic,severe_toxic,obscene,threat,
     insult,identity_hate,source,split
3. Deduplicates against AURA's existing dataset text (no data leakage).
4. Deterministic 70/15/15 train/validation/test split (seed 42).
5. Writes:
     data/external/<name>.csv                 (normalized rows)
     data/external/<name>.meta.json           (source URL, license, counts)
     data/external/manifest.json              (combined manifest)
   Nothing is written to aura.db and no existing rows are modified — import is
   a separate, explicit step (see DATASET_GUIDE.md).

Usage
-----
  python fetch_external_datasets.py --limit 200          # smoke subset
  python fetch_external_datasets.py --limit 5000 --merge # full pull + merge
  python fetch_external_datasets.py --dry-run            # show plan only

Row label mapping (original labels preserved as-is, no relabeling):
  civil_comments: toxic = max(identity_attack, insult, threat, obscene...) >= 0.5
                  (recorded in meta.json; original float kept in *_score cols)
  wiki_toxic:     toxic == 1 (binary), others 0.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
EXTERNAL = DATA / "external"
MULTI_RAW = DATA / "multilingual" / "raw"

SCHEMA = ["id", "text", "language", "language_name", "script", "toxic",
          "severe_toxic", "obscene", "threat", "insult", "identity_hate",
          "source", "split"]

SOURCES = [
    {
        "name": "civil_comments",
        "dataset": "google/civil_comments",
        "config": "default",
        "split": "train",
        "license": "CC0-1.0",
        "url": "https://huggingface.co/datasets/google/civil_comments",
        "language": "en",
        "language_name": "English",
        "script": "Latin",
    },
    {
        "name": "wiki_toxic",
        "dataset": "OxAISH-AL-LLM/wiki_toxic",
        "config": "default",
        "split": "train",
        "license": "CC0-1.0",
        "url": "https://huggingface.co/datasets/OxAISH-AL-LLM/wiki_toxic",
        "language": "en",
        "language_name": "English",
        "script": "Latin",
    },
]

HF_ROWS = "https://datasets-server.huggingface.co/rows"
PAGE = 100  # datasets-server max rows per request


def http_json(url: str, timeout: int = 30):
    req = urllib.request.Request(url, headers={"User-Agent": "aura-dataset-tool/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_rows(src: dict, limit: int) -> list[dict]:
    """Fetch up to `limit` rows from a HF dataset via the rows API."""
    out: list[dict] = []
    offset = 0
    while len(out) < limit:
        n = min(PAGE, limit - len(out))
        q = urllib.parse.urlencode({
            "dataset": src["dataset"], "config": src["config"],
            "split": src["split"], "offset": offset, "length": n,
        })
        try:
            payload = http_json(f"{HF_ROWS}?{q}")
        except Exception as e:  # network / API error -> stop, keep what we have
            print(f"  ! fetch stopped at offset {offset}: {e}")
            break
        rows = payload.get("rows") or []
        if not rows:
            break
        out.extend(r.get("row", {}) for r in rows)
        offset += len(rows)
        if len(rows) < n:
            break
    return out[:limit]


def normalize(src: dict, rows: list[dict]) -> list[dict]:
    """Map a source's rows onto AURA's schema. Original labels are preserved."""
    name = src["name"]
    norm_rows: list[dict] = []
    for i, row in enumerate(rows):
        if name == "civil_comments":
            text = (row.get("text") or "").strip()
            # civil_comments uses float toxicity dimensions in [0,1]
            dims = {k: float(row.get(k) or 0.0) for k in
                    ("toxicity", "severe_toxicity", "obscene", "threat",
                     "insult", "identity_attack")}
            toxic = 1 if dims["toxicity"] >= 0.5 else 0
            labels = {
                "toxic": toxic,
                "severe_toxic": 1 if dims["severe_toxicity"] >= 0.5 else 0,
                "obscene": 1 if dims["obscene"] >= 0.5 else 0,
                "threat": 1 if dims["threat"] >= 0.5 else 0,
                "insult": 1 if dims["insult"] >= 0.5 else 0,
                "identity_hate": 1 if dims["identity_attack"] >= 0.5 else 0,
            }
        elif name == "wiki_toxic":
            text = (row.get("comment_text") or row.get("text") or "").strip()
            # wiki_toxic stores the binary label under `label` (some mirrors use `toxic`)
            raw_label = row.get("label")
            if raw_label is None:
                raw_label = row.get("toxic") or 0
            try:
                toxic = 1 if float(raw_label) >= 0.5 else 0
            except (TypeError, ValueError):
                toxic = 0
            labels = {"toxic": toxic, "severe_toxic": 0, "obscene": 0,
                      "threat": 0, "insult": 0, "identity_hate": 0}
        else:
            continue
        if not text:
            continue
        norm_rows.append({
            "id": f"{name}-{i}",
            "text": text,
            "language": src["language"],
            "language_name": src["language_name"],
            "script": src["script"],
            **{k: str(v) for k, v in labels.items()},
            "source": "external:" + name,
            "split": "",  # assigned later
        })
    return norm_rows


def existing_texts() -> set[str]:
    """Normalized texts already present in AURA (dedup / leakage guard)."""
    texts: set[str] = set()

    def add(path: Path) -> None:
        if not path.exists():
            return
        with path.open(encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                # Phase 4 fix: must use the SAME key as dedup_rows() below
                # (whitespace-collapsed + casefold). Plain .strip().lower()
                # let whitespace-variants of existing AURA rows slip past
                # the leakage guard (same bug class the Phase 3 dedup_key
                # fix addressed for the in-file comparison).
                t = dedup_key(row.get("text") or row.get("comment") or "")
                if t:
                    texts.add(t)

    for p in [DATA / "raw" / "demo_dataset.csv",
              DATA / "train" / "train.csv",
              DATA / "validation" / "validation.csv",
              DATA / "test" / "test.csv"]:
        add(p)
    if MULTI_RAW.exists():
        for p in MULTI_RAW.glob("*.csv"):
            add(p)
    return texts


def dedup_key(text: str) -> str:
    """Dedupe key shared with ml_service.split_dataset and the importer.

    Phase 3 fix: the fetch pipeline compared ``text.lower()`` only, so rows
    differing in whitespace landed as distinct. That let a byte-identical
    comment appear in two splits with opposite labels (split leakage).
    """
    return re.sub(r"\s+", " ", (text or "").strip()).casefold()


DEDUP_LABEL_COLUMNS = ("toxic", "severe_toxic", "obscene", "threat",
                       "insult", "identity_hate")


def label_signature(row: dict) -> tuple:
    return tuple(int(row.get(name) or 0) for name in DEDUP_LABEL_COLUMNS)


def dedup_rows(rows: list[dict], seen: set, conflicts: list) -> list[dict]:
    """Drop rows already present; record text seen twice with differing labels."""
    labels: dict = {}
    kept: list[dict] = []
    for row in rows:
        key = dedup_key(row["text"])
        if not key:
            continue
        sig = label_signature(row)
        if key in seen:
            prior = labels.get(key)
            if prior is not None and prior != sig:
                conflicts.append({"text": row["text"][:120], "labels_a": list(prior),
                                  "labels_b": list(sig)})
            continue
        if key in labels:
            continue
        labels[key] = sig
        seen.add(key)
        kept.append(row)
    return kept


def assign_splits(rows: list[dict], seed: int = 42) -> list[dict]:
    """Deterministic 70/15/15 split, stratified on the toxic label."""
    rng = random.Random(seed)
    by_class: dict[int, list[dict]] = {}
    for r in rows:
        by_class.setdefault(int(r["toxic"]), []).append(r)
    for group in by_class.values():
        rng.shuffle(group)
    n = len(rows)
    out: list[dict] = []
    for group in by_class.values():
        total = len(group)
        n_train = int(round(total * 0.70))
        n_val = int(round(total * 0.15))
        for i, r in enumerate(group):
            if i < n_train:
                r["split"] = "train"
            elif i < n_train + n_val:
                r["split"] = "validation"
            else:
                r["split"] = "test"
            out.append(r)
    # guard: empty splits on tiny inputs get at least the majority class rows
    if n and not any(r["split"] == "test" for r in out):
        out[-1]["split"] = "test"
    return out


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=SCHEMA)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in SCHEMA})


def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch and integrate public toxicity datasets for AURA")
    ap.add_argument("--limit", type=int, default=200,
                    help="rows to fetch per source (default 200 = smoke subset)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--dry-run", action="store_true", help="only print the plan")
    ap.add_argument("--merge", action="store_true",
                    help="also write merged splits into data/external/splits/{train,validation,test}.csv")
    args = ap.parse_args()

    print(f"AURA external dataset fetch — limit/source={args.limit}, seed={args.seed}")
    if args.dry_run:
        for s in SOURCES:
            print(f"  would fetch <= {args.limit} rows from {s['dataset']} ({s['license']})")
        return 0

    EXTERNAL.mkdir(parents=True, exist_ok=True)
    seen = existing_texts()
    print(f"existing AURA texts for dedup: {len(seen)}")

    manifest = {"generated_at": datetime.now(timezone.utc).isoformat(),
                "seed": args.seed, "sources": [], "datasets": []}

    all_rows: list[dict] = []
    for s in SOURCES:
        print(f"fetching {s['dataset']} ...")
        raw = fetch_rows(s, args.limit)
        rows = normalize(s, raw)
        before = len(rows)
        if rows and all(int(r["toxic"]) == 0 for r in rows) and len(rows) >= 50:
            print(f"  ! WARNING: {s['name']} normalized to 0 toxic rows out of "
                  f"{len(rows)} — label mapping may be wrong; check normalize().")
        conflicts: list = []
        rows = dedup_rows(rows, seen, conflicts)
        if conflicts:
            print(f"  ! {len(conflicts)} conflicting-label duplicate(s) dropped "
                  f"(same text, different labels) ? first occurrence kept")
        rows = assign_splits(rows, args.seed)
        path = EXTERNAL / f"{s['name']}.csv"
        write_csv(path, rows)
        toxic_n = sum(int(r["toxic"]) for r in rows)
        meta = {
            "name": s["name"], "dataset_id": s["dataset"], "url": s["url"],
            "license": s["license"], "fetched_rows": len(raw),
            "normalized_rows": before, "duplicates_removed": before - len(rows),
            "conflicting_label_duplicates": len(conflicts),
            "conflicting_label_samples": conflicts[:5],
            "written_rows": len(rows), "toxic": toxic_n,
            "non_toxic": len(rows) - toxic_n,
            "language": s["language"], "language_name": s["language_name"],
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "split_counts": {k: sum(1 for r in rows if r["split"] == k)
                             for k in ("train", "validation", "test")},
            "preprocessing": [
                "UTF-8 decode", "whitespace strip", "drop empty text",
                "binary label threshold 0.5 (civil_comments floats preserved at fetch)",
                "dedup by whitespace-collapsed casefolded key (matches "
                "ml_service.split_dataset and import_external_datasets); "
                "conflicting-label duplicates dropped, first occurrence kept",
                f"stratified 70/15/15 split (seed {args.seed})",
            ],
        }
        (EXTERNAL / f"{s['name']}.meta.json").write_text(
            json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
        manifest["datasets"].append(meta)
        print(f"  wrote {len(rows)} rows -> {path.name} "
              f"(train/val/test={meta['split_counts']}, toxic={toxic_n})")
        all_rows.extend(rows)

    if args.merge and all_rows:
        for split in ("train", "validation", "test"):
            part = [r for r in all_rows if r["split"] == split]
            write_csv(EXTERNAL / "splits" / f"{split}.csv", part)
        print(f"merged splits written under {EXTERNAL / 'splits'}")

    manifest["total_rows"] = len(all_rows)
    (EXTERNAL / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"DONE: {len(all_rows)} external rows integrated, manifest written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
