# AURA — Dataset Guide

> How to obtain, configure, validate, and process datasets for the AURA
> comment-toxicity project. Covers the built-in datasets **and** the external
> expansion pipeline added in `CODE/BACKEND/fetch_external_datasets.py`.

---

## 1. Datasets in this project

| Dataset | Location | Rows | License | Language | Labels |
|---|---|---|---|---|---|
| Demo dataset | `CODE/BACKEND/data/raw/demo_dataset.csv` (+ `train/`, `validation/`, `test/`) | 100 | project-owned demo data | en | 6 toxicity dimensions (0/1) |
| Multilingual curated demo | `CODE/BACKEND/data/multilingual/raw/multilingual_demo.csv` (+ split mirrors) | 96 | project-owned curated demo | 12 languages | same schema |
| DB-resident samples | `CODE/BACKEND/aura.db` → `dataset_samples` | 197 total | project-owned | en + 11 others | same schema |
| **civil_comments (new)** | `CODE/BACKEND/data/external/civil_comments.csv` | 200 (smoke subset) | **CC0-1.0** | en | toxicity dims, threshold 0.5 |
| **wiki_toxic (new)** | `CODE/BACKEND/data/external/wiki_toxic.csv` | 200 (smoke subset) | **CC0-1.0** | en | binary `label` |

Sources:

- https://huggingface.co/datasets/google/civil_comments (CC0-1.0, verified via HF API `cardData.license`)
- https://huggingface.co/datasets/OxAISH-AL-LLM/wiki_toxic (CC0-1.0, verified via HF API)

Per-run provenance (row counts, license, fetch time, preprocessing steps,
split counts) is written to `CODE/BACKEND/data/external/<name>.meta.json` and
aggregated in `CODE/BACKEND/data/external/manifest.json`.

---

## 2. Schema

All AURA CSVs use the same header:

```
id,text,language,language_name,script,toxic,severe_toxic,obscene,threat,insult,identity_hate,source,split
```

- `toxic` is the binary headline label; the other five columns are categories.
- `split` ∈ `train` | `validation` | `test`.
- `source` records provenance (`demo`, `curated_demo`, `external:civil_comments`, …).
- Original labels are never altered; derived binary labels (e.g. civil_comments
  float → 0.5 threshold) are recorded in the `.meta.json` preprocessing list.

---

## 3. Fetching / expanding external data

Stdlib only — no `datasets`/`transformers` install required (uses the HF
datasets-server rows API).

```powershell
$py = "C:\Users\gokul\OneDrive\Desktop\zip project\comment toxicity\.venv\Scripts\python.exe"
cd "C:\Users\gokul\OneDrive\Desktop\zip project\comment toxicity\CODE\BACKEND"

& $py fetch_external_datasets.py --dry-run           # show plan
& $py fetch_external_datasets.py --limit 200 --merge # smoke subset (used in this audit)
& $py fetch_external_datasets.py --limit 5000 --merge # larger pull
```

Options:

| Flag | Meaning |
|---|---|
| `--limit N` | rows to fetch **per source** (default 200) |
| `--seed N` | split seed (default 42, deterministic) |
| `--merge` | also write `data/external/splits/{train,validation,test}.csv` |
| `--dry-run` | print the plan, download nothing |

Guarantees enforced by the script:

1. **Deduplication** — every fetched row is checked (case-insensitive) against
   `data/raw`, `data/train|validation|test`, and `data/multilingual/raw`;
   duplicates are dropped before splitting.
2. **No leakage** — the 70/15/15 split happens *after* dedup, stratified on the
   toxic label, with a fixed seed, so no text can appear in two splits.
3. **Sanity check** — if a source normalizes to 0 toxic rows out of ≥50, the
   script prints a loud warning instead of silently writing junk (this caught a
   real bug during the audit: wiki_toxic stores its label as `label`, not `toxic`).
4. **Non-destructive** — only `data/external/**` is written. `aura.db`, the
   existing CSVs, and the existing splits are untouched.

---

## 4. Importing external rows into the app (manual step)

External rows are **not** auto-inserted into the database (to protect existing
user data). To import deliberately:

```powershell
# via the API (admin token required)
# POST /dataset  { "comment": "...", "label": ..., "language": "en", "source": "external:civil_comments" }
```

or bulk-load a CSV with the same schema through the Dataset Management page in
the frontend. Re-run `/models/train` afterwards so the model sees the new rows.

---

## 5. Training / evaluation

```powershell
# start the backend first, then:
# POST /models/train  {"config": {"variant": "improved", "seed": 42}}
# GET  /models/train/{job_id}   -> status + measured metrics
# GET  /models/performance      -> accuracy/precision/recall/F1/confusion matrix
```

Measured on the current 197-row dataset (test n=31), model `improved_v10`,
trained during this audit:

| Metric | Value |
|---|---|
| Accuracy | 0.677 |
| Precision | 0.602 |
| Recall | 0.552 |
| F1 | 0.539 |
| Confusion matrix | `[[19, 2], [8, 2]]` (labels: non_toxic, toxic) |
| Per-language | en: acc 0.882 (support 17); kn: acc 0.667 (support 3); others: **Not evaluated** (support < 3) |

Metrics that were never measured are returned as the literal
`"Not evaluated"` — never fabricated.

---

## 6. Adding another dataset

1. Add an entry to `SOURCES` in `fetch_external_datasets.py` with
   `dataset`, `config`, `split`, verified `license`, and label mapping.
2. Add a branch in `normalize()` that maps its columns to the AURA schema —
   **preserve original labels**, derive binaries only with a documented threshold.
3. Run with `--limit 50` first and confirm the toxic/non-toxic counts look sane.
4. Record the license in the `.meta.json` (the script does this automatically).

Recommended next sources (not yet integrated):

| Dataset | Why | License |
|---|---|---|
| HASOC / SemEval hate speech (Hinglish, Hindi) | extends beyond-English ML beyond lexicons | check per task page |
| Jigsaw Multilingual Toxic Comment (Kaggle) | real multilingual toxicity labels | CC BY-SA 4.0 |
| Civil Comments-Ewafi / Indic languages sets | Indic-language toxicity | check per dataset |

> Network access to `huggingface.co` and `datasets-server.huggingface.co` is
> required for fetching. If unavailable, the script fails cleanly and keeps any
> rows already fetched; the integration code itself is ready for when download
> access exists.

---

## 7. Phase 2 — Evaluation splits (data/phase2_eval/)

Held-out **validation / test** splits used to tune and benchmark the pretrained
model (Phase 2, `PHASE2_MODEL_EVALUATION.md`). Regenerated by
`CODE/BACKEND/prepare_phase2_eval.py`.

| Language | Validation CSV rows | Test CSV rows |
|---|---:|---:|
| en | 120 | 180 |
| hi | 120 | 180 |
| ta | 120 | 180 |
| ta-Latn | 120 | 180 |
| ur | 120 | 180 |
| bn | 95 | 143 |

- **Provenance** — `CODE/BACKEND/data/phase2_eval/manifest.json` records the
  source corpora, per-group counts, and generation parameters for each split.
  Verified source table (Phase 3):

| Group | Source dataset | License | Label basis |
|---|---|---|---|
| en, hi | `textdetox/multilingual_toxicity_dataset` | OpenRAIL++ | binary `toxic` column used as-is |
| ta | `community-datasets/offenseval_dravidian` | CC-BY-4.0 | `0=Not_offensive -> 0`, `1-4=Offensive* -> 1`; label 5 (not-Tamil) excluded; **native Tamil script only** |
| ta-Latn | `community-datasets/offenseval_dravidian` | CC-BY-4.0 | same labels as `ta`, restricted to rows **without** Tamil script (Tanglish / code-mixed Latin) |
| bn | `Polygl0t/bengali-toxicity-qwen-annotations` | Apache-2.0 | **WEAK LABELS (Qwen annotations)**: score ≥4 -> toxic, ≤2 -> non_toxic, score 3 excluded; no human review available |
| ur | `Adnan855570/Urdu_Hate_Speech` | MIT | expert-generated **hate-speech** labels mapped to binary; unmappable values excluded |

  *(Correction: an earlier revision of this guide said the Phase 2 splits were
  "carved from the same curated multilingual corpora used in Phase 1". That was
  wrong — they come from the Hugging Face datasets above, not from the local
  demo corpora.)*

- **Task mismatch matters** — three groups are **not** generic-toxicity
  corpora: `ta`/`ta-Latn` label *offensiveness*, `ur` labels *hate speech*, and
  `bn` uses weak model annotations. Scoring them with a general toxicity model
  is a deliberately hard, partly mis-aligned comparison, which is the most
  plausible root cause of the ur FPR (0.256) and ta/ta-Latn weakness. Read the
  per-language numbers with the label basis in mind.
- **Data hygiene is clean** — verified in Phase 3: classes are balanced
  (50/50 for every group except bn at 37%), there are **zero** exact or
  whitespace/case-normalised duplicates within or between val and test, and no
  text is reused across language groups.
- **bn caveat** — Bengali labels are **weak annotations produced by a Qwen
  model, not human gold labels**; treat bn metrics accordingly.
- **Tuning discipline** — thresholds were tuned on the **validation splits
  only**; the test split was **never touched** during tuning (see
  `models/tuned_threshold.json`).
- **Phase 3 results** — these splits were re-benchmarked with the extended
  threshold sweep; per-language precision/recall/F1, macro-F1, confusion
  matrices, ROC-AUC, PR-AUC, latency and memory are in
  `CODE/BACKEND/models/phase3_benchmark.json` and summarised in
  `PHASE2_MODEL_EVALUATION.md` §10.3. Highlights: ta-Latn test F1
  0.245 -> **0.313** once the 0.30 threshold floor was removed; bn
  0.624 -> 0.722 but with test FPR 0.178 (above the 0.15 budget, not adopted);
  ur and bn remain above the test FPR cap because of the task mismatch above.
- **Schema** — same AURA header as §2 above; original labels are never altered.
- **Regenerator** — `CODE/BACKEND/prepare_phase2_eval.py` rebuilds every split
  deterministically (non-destructive: only `data/phase2_eval/**` is written).

---

## 8. Phase 3 — External datasets imported into `aura.db`

Phase 1 fetched the datasets but never imported them. Phase 3 imported them
with `CODE/BACKEND/import_external_datasets.py` (**dry run by default**;
writes only with `--apply`).

### Sources (both CC0-1.0)

| Dataset | HF id | Rows imported | Toxic |
|---|---|---:|---:|
| Civil Comments | `google/civil_comments` | 199 | 11 |
| Wiki Toxic | `OxAISH-AL-LLM/wiki_toxic` | 200 | 21 |
| | **Total** | **399** | **32** |

### Actual counts from the applied run

| Outcome | Rows |
|---|---:|
| Read from source CSVs | 400 |
| **Inserted** | **399** |
| Skipped — duplicate text (`civil_comments-84`, byte-identical to `-82` but labelled toxic=1) | 1 |
| Skipped — already imported (2nd run) | 399 |
| Rejected — bad schema / label / language / empty / too long | **0** |
| `dataset_samples` rows before → after | **197 → 596** |

The 197 pre-existing rows are **byte-identical** after the import (verified by
comparing `id, comment, 6 labels, source, language, split` against the
pre-import backup in `CODE/BACKEND/data/backups/`). Users (11) and history
(658 rows) were untouched.

### Safety properties (all covered by `tests_dataset_import.py`, 38 checks)

- **Dry run first** — no writes unless `--apply`; row counts re-verified after.
- **Additive only** — the importer contains no DELETE/UPDATE/REPLACE.
- **Transactional** — one `BEGIN IMMEDIATE`…`COMMIT`; on error the whole batch
  rolls back (proved by injecting a `RAISE(ABORT)` trigger mid-batch: 0 of 4
  rows landed).
- **Idempotent** — `external_id` column + partial `UNIQUE` index
  `idx_dataset_samples_external_id`; a second `--apply` run inserted **0**.
- **Schema-validated** — a file missing required columns aborts *before* the
  transaction opens.
- **Label-validated** — every label must parse to exactly 0/1 (a `0.37` was
  rejected, not coerced).
- **Language-scoped** — only AURA-detectable languages are imported; unsupported
  rows are rejected with a reason, never relabelled as English.
- **Deduplicated** — whitespace-collapsed + casefolded key, matching
  `ml_service.split_dataset`; checked within-file, cross-file and against the DB.

### Provenance and mapping

| External CSV | `dataset_samples` | Note |
|---|---|---|
| `id` | `external_id` (new column) | within-dataset key; **not** an upstream id (see caveat) |
| `text` | `comment` | |
| `toxic`, `severe_toxic`, `obscene`, `threat`, `insult`, `identity_hate` | same names | already binary (0.5 float threshold applied at fetch time) |
| `language`, `language_name`, `script` | same names | |
| `source` (`external:civil_comments`) | `source` = `external_civil` | renamed: `:` violates AURA's `DATASET_SOURCE_RE` |
| `split` | *(blank)* | AURA's deterministic splitter owns the split |

Full audit trail per run: `CODE/BACKEND/data/external/import_report.json`
(inserted / skipped / rejected tallies, per-reason rejections, file SHA-256,
before/after counts).

### Caveats

1. **Labels were binarised at fetch time** (`>= 0.5` on the float scores); the
   original float toxicity is not retained, so the 0.5 cut cannot be revisited.
2. **`external_id` is positional, not upstream.** `fetch_external_datasets.py`
   numbers rows by fetch position, so re-fetching with a different `--limit`
   renumbers them. It is a valid idempotency key for *this artifact* only.
3. **One toxic label was lost to dedup.** The byte-identical pair
   `civil_comments-82/84` carry opposite labels; first occurrence won, so the DB
   has 11 civil toxic rows vs the 12 recorded in the fetch manifest.
4. **English only.** Both smoke subsets are English; the 399 rows add no
   non-English coverage and cannot fix the Indic-language weaknesses.
5. **Unassigned splits.** The 399 rows have `split=''` until AURA's splitter
   runs; when it does, it reshuffles *all* rows, so the previously documented
   197-row model metrics will change on the next training run.
6. **No global uniqueness on `comment`.** Rows added through `POST /dataset`
   (`ml_service.add_sample`) are still not deduped against imported rows.

