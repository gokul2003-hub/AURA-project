# PHASE 4.2 — Task 2: Urdu (ur) Dataset Assessment

**Date:** 2026-10-10 · **Files inspected (read-only):** `CODE/BACKEND/data/phase2_eval/ur_val.csv`, `ur_test.csv`, `manifest.json`, `CODE/BACKEND/data/lexicons/ur.json`, `CODE/BACKEND/aura.db` (sqlite `mode=ro`), plus `PHASE2_MODEL_EVALUATION.md`, `DATASET_GUIDE.md`, `PROJECT_AUDIT_REPORT.md`, `PHASE4_WORKSTREAM_E.md`, `PHASE41_URDU_FPR.md`.

## 1. Provenance & licence

Verified against the source of truth `CODE/BACKEND/data/phase2_eval/manifest.json`, group `ur` (lines 106–125):

| Field | Value |
|---|---|
| Dataset | **`Adnan855570/Urdu_Hate_Speech`** (Phase 4 recollection confirmed) |
| URL | https://huggingface.co/datasets/Adnan855570/Urdu_Hate_Speech |
| **Licence** | **MIT** (explicit `"license": "MIT"` in manifest — not invented) |
| Label notes | "expert-generated hate-speech labels mapped to binary; unmappable values excluded" |
| Fetched rows | 26,174 → balanced to 150 toxic / 150 non-toxic → 120 val + 180 test |

Corroborated identically at `DATASET_GUIDE.md:174`, `PROJECT_AUDIT_REPORT.md:478`, `PHASE4_WORKSTREAM_E.md:175` ("MATCH"), `PHASE41_URDU_FPR.md:56`. Licence is stated consistently as MIT in all five places.

**Important nuance:** the labels are **expert hate-speech** annotations, scored by a **generic toxicity model** (`Horizon-Labs/multilingual-toxicity-small`) — a documented task mismatch (`PHASE41_URDU_FPR.md:56`, `PHASE2_MODEL_EVALUATION.md:217`). This is the root cause of the ur FPR 0.256 finding, not a data-integrity defect.

## 2. Sample counts & class balance

Label column: **`label`** (binary `0`/`1`; `1` = toxic/hate). Full schema: `id, text, language, label, source, source_row_id, source_url, license, split, label_notes`.

| File | Rows | Toxic (1) | Non-toxic (0) | Empty text | Empty label | Label values |
|---|---|---|---|---|---|---|
| `ur_val.csv` | **120** | 60 | 60 | 0 | 0 | {0, 1} |
| `ur_test.csv` | **180** | 90 | 90 | 0 | 0 | {0, 1} |

Perfectly balanced; matches manifest `val_rows/test_rows` exactly. No missing or malformed labels.

## 3. Duplicates & train/test leakage

| Check | Count |
|---|---|
| Exact-duplicate texts **within** `ur_val.csv` | **0** (120/120 unique) |
| Exact-duplicate texts **within** `ur_test.csv` | **0** (180/180 unique) |
| Texts shared **between** val and test (leakage) | **0** |
| Label contradictions (identical text, different label, across files) | **0** — no contradictions exist to sample |

Clean: no duplication, no val↔test contamination.

## 4. Train overlap (aura.db, read-only)

`dataset_samples` splits overall: 137 train / 29 validation / 31 test + **399 unassigned** (the external rows, all unassigned) — confirmed via `SELECT split, COUNT(*)`.

Urdu rows in DB: **8**, `source = 'curated_demo'`, `external_id = NULL`, Arabic-script demo sentences (e.g. `"اپ کیس ہیں؟ میں ٹھیک ہوں."`). Splits: 6 train / 2 test — but these are **synthetic demo rows**, not corpus rows. **Text overlap between these 8 DB rows and the 300 eval-file rows: 0.** The 300 real Urdu eval rows (ur_val/ur_test) are **NOT in the train split** — confirmed; no ur eval contamination of training data.

## 5. Script coverage: Arabic vs Roman Urdu

| Script class | ur_val (120) | ur_test (180) |
|---|---|---|
| Arabic-script only (U+0600–U+06FF, no ASCII letters) | **120 (100%)** | **180 (100%)** |
| Latin / Roman Urdu only | **0** | **0** |
| Mixed Latin+Arabic | **0** | **0** |

**Roman Urdu is entirely absent** from the ur evaluation set — measured, not assumed. Independently corroborated by `PHASE41_URDU_FPR.md:70` ("0/90 negatives are Latin-only and 0/90 mixed → no romanised-Urdu rows"). Also 0 rows in `lexicons/ur.json` are Latin (that lexicon is Arabic-script only, 15 terms total, self-described as "demo/dev quality. Not benchmark data." line 5).

## 6. Label consistency

No contradictions found (0 shared texts across files, 0 intra-file duplicate texts with conflicting labels). Nothing to sample.

## 7. Synthetic vs real — verdict with evidence

**The eval CSVs are REAL corpus rows; the DB rows and lexicon are SYNTHETIC demo.** Evidence:

- **Real (benchmark) data:** `ur_val.csv`/`ur_test.csv` — manifest line 114 `"fetched_rows": 26174` from HuggingFace `Adnan855570/Urdu_Hate_Speech`, each row carries `source_row_id` + `source_url` back to the source corpus; labels are expert hate-speech annotations (`manifest.json:113`).
- **Synthetic (demo only, NOT benchmark):** the 8 `aura.db` urdu rows carry `source = 'curated_demo'` (DB query output above), and `ur.json:5` states: *"Small curated heuristic lexicon (demo/dev quality). Not benchmark data."*

## 8. Is a suitable dataset already present?

**Verdict: EXISTING-SUITABLE — for evaluation benchmarking only.** A real, licensed (MIT), provenance-tracked, deduplicated, balanced Urdu eval set of 300 rows already exists and is in active use. It is *not* sufficient for two documented gaps:

1. **Zero Roman-Urdu coverage** (measured §5) — a real production failure mode is untested.
2. **Task mismatch** (hate-speech labels vs generic toxicity model) plus small n=180 test → the ur FPR 0.256 cannot be reliably fixed from this set alone (`PHASE41_URDU_FPR.md` ruled out lexicon/threshold fixes; option (c) "commission a ur-specific labelled set" is the documented remedy).

### If a supplementary set is commissioned: schema + import pipeline DESIGN (no data fabricated here)

Schema (mirrors existing `phase2_eval` CSVs so `prepare_phase2_eval.py` conventions hold):

```
id,text,language,label,source,source_row_id,source_url,license,split,label_notes
```

Pipeline design (documented, not executed):
1. **Acquire** — pick a source per group with explicit licence (MIT/CC-BY/Apache/OpenRAIL++ only); record dataset id, URL, licence, label mapping in `manifest.json` group `ur` (same structure as lines 106–125). Prefer sources with both Arabic-script and Roman-Urdu strata.
2. **Stratify** — tag each row `script ∈ {arabic, latin, mixed}` (same U+0600–U+06FF vs ASCII-letter rule used in §5) and split stratified by script × label.
3. **Deduplicate** — exact-text dedupe within and across splits (as verified clean in §3) before writing CSVs.
4. **Hold out** — new rows must land in val/test only; assert zero overlap with `dataset_samples` train (the §4 check) to prevent leakage.
5. **Evaluate** — score with the existing adapter; report per-script FPR/F1 to close the Roman-Urdu gap.

*Constraint respected: no training claimed, no dataset generated; assessment only.*
