# AURA Phase 4.2 — Task 3: Isolated Candidate Model Evaluation

Date: 2026-10-11 · Status: **COMPLETE** · Gate verdict: **NOT PASSED** (candidate FPR 0.3000 > cap 0.15)

Evaluation performed by a standalone script (`%TEMP%\p42_cand_eval.py`) importing only
`transformers` / `torch` / stdlib + the held-out CSVs. **No** production module
(`backend.py`, `model_adapter.py`, `mlexicon.py`, `app.py`) was imported, started or modified.
No downloads were made (HF_HUB_OFFLINE=1). No protected artifact was written.

---

## 1. Candidate selection

### 1.1 Local inventory (models found on disk)

| Location | Artifact | Size on disk | Notes |
|---|---|---|---|
| `CODE\BACKEND\models\hf_cache\hub\models--Horizon-Labs--multilingual-toxicity-small\snapshots\3baf7739…\` | `model.safetensors` | 536.53 MB | fp32 ModernBert, 141M params |
| same snapshot | `config.json` | 2.3 KB | `ModernBertForSequenceClassification`, `problem_type=multi_label_classification`, 7 labels (id2label 0=`toxicity` … 6=`sexual_explicit`), vocab 256000, hidden 384, 22 layers, max_pos 8192 |
| same snapshot | `tokenizer.json` / `tokenizer_config.json` | 32.77 MB / 0.04 MB | PreTrainedTokenizerFast, unk=`<unk>` |
| same snapshot | `eval\this_model.json`, `eval\baselines.json`, `training\*.json`, `onnx\quantization_check.json` | <1 MB | provenance/eval metadata; no ONNX weights present locally |
| `CODE\BACKEND\models\` (root) | `phase2_benchmark.json`, `phase3_benchmark.json`, `tuned_threshold.json`, `benchmark_run2.log` | <1 MB | read-only baseline records |
| `%USERPROFILE%\.cache\huggingface` | only `.agent_harnesses.json` | 0.01 MB | no other models cached |

Exactly **one** compatible multilingual toxicity model exists locally; no other candidates were available, and none were downloaded.

### 1.2 Chosen candidate

- **Identifier:** `Horizon-Labs/multilingual-toxicity-small`
- **Local path:** `CODE\BACKEND\models\hf_cache\hub\models--Horizon-Labs--multilingual-toxicity-small\snapshots\3baf7739b9ba7d49dc389851bb336f8a03a6cbef` (revision `3baf7739…`, 536.53 MB weights)
- **Provenance:** built on `jhu-clsp/mmBERT-small`, trained on Civil Comments (CC0) + machine translations (`Horizon-Labs/civil-comments-multilingual`); Detoxify-style 7-label sigmoid head. Fetched model card (README, ~25 KB) only — no weights downloaded.
- **Licence:** **Apache-2.0** per the model card front-matter. NOTE: no `license` field exists in the local `config.json` / `tokenizer_config.json`; Apache-2.0 is asserted from the upstream README only.
- **CRITICAL PROVENANCE FINDING:** `phase3_benchmark.json → model.model_id` is *already* `Horizon-Labs/multilingual-toxicity-small`. The "baseline ur" in Phase 3 is **the same checkpoint** this task evaluates. This isolated run therefore measures the raw checkpoint under the same protocol; any delta vs the baseline numbers reflects eval-harness differences (max_len 96 vs 256; 0.01 vs 0.05 threshold grid) and threshold-run variance — **not** a different model. There was no second local multilingual candidate to try.

## 2. Protocol (mirrors Phase 3, threshold chosen on VAL ONLY)

- Data: `CODE\BACKEND\data\phase2_eval\ur_val.csv` (n=120, 60 pos / 60 neg) for threshold selection only; `ur_test.csv` (n=180, 90 pos / 90 neg) untouched until final scoring. Labels are `0`/`1` in the `label` column.
- Scoring: `sigmoid(logits)[index 0 = toxicity]`; binary decision `p >= threshold`. Identical semantics to `model_adapter.py` (plain text, no prompt template).
- Threshold rule (same as Phase 3): **max toxic F1 on val subject to val FPR <= 0.15**; grid 0.01..0.99 (Phase 3 used 0.05 steps; minor methodology delta, noted in Limitations).
- Tokenization: max_len **96** (vs 256 in production) for CPU runtime; truncation impact measured post-hoc (§5).

## 3. Val-selected threshold and test results (candidate, isolated)

**Val-selected threshold = 0.38** (val at 0.38: FPR 0.1500, precision 0.8125, recall 0.6500, F1 0.7222, TN 51 / FP 9 / FN 21 / TP 39; val ROC-AUC 0.7883). Unconstrained val max-F1 threshold would be 0.31.

**Test (n=180, 90 pos / 90 neg) at threshold 0.38:**

| Metric | Value | 95% Wilson CI |
|---|---|---|
| FPR | **0.3000** (27/90) | [0.2151, 0.4013] |
| Precision | 0.6494 (50/77) | [0.5380, 0.7465] |
| Recall | 0.5556 (50/90) | [0.4527, 0.6538] |
| F1 | 0.5988 | — |
| ROC-AUC | 0.7006 | — |
| Confusion (labels non_toxic, toxic) | TN=63, FP=27, FN=40, TP=50 → `[[63,27],[40,50]]` | — |

## 4. Baseline vs candidate (identical dataset/protocol family)

| Metric (ur test, n=180) | Baseline `test_model` (Phase 3, thr 0.40) | Candidate isolated (thr 0.38, this run) |
|---|---|---|
| FPR | 0.2556 | **0.3000** |
| Precision | 0.6714 | 0.6494 |
| Recall | 0.5222 | 0.5556 |
| F1 | 0.5875 | 0.5988 |
| ROC-AUC | 0.7044 | 0.7006 |
| Confusion | [[67,23],[43,47]] | [[63,27],[40,50]] |
| FPR cap 0.15 | exceeded | exceeded |

The isolated numbers sit within sampling noise of the baseline (FPR CIs overlap: baseline 23/90 Wilson ≈ [0.175, 0.355] vs candidate [0.215, 0.401]) — consistent with the two being the same checkpoint. **The candidate does not fix the Urdu false-positive problem; the root cause is the checkpoint's Urdu discrimination (val AUC 0.79, test AUC 0.70), not the adapter.**

**GATE VERDICT for the 0.15 FPR cap: NOT PASSED** (measured test FPR 0.3000 > 0.15; even the val-selected operating point only satisfied the cap on val, exactly at 0.1500).

## 5. Coverage: Urdu (Arabic script) and Roman Urdu

- **Urdu script:** all 180/180 test and 120/120 val rows contain Arabic-script characters (U+0600–U+06FF). Tokenizer produced **0 `<unk>` tokens** across both splits → full byte-level coverage (no OOV), but heavy fragmentation: **4.48 subwords/word** on test (Urdu probe sentences: 2.11 subwords/word). Fragmentation at 96-token truncation affects 10/180 test rows (5.6%; max actual length 118 tokens) and 5/120 val rows; zero rows exceed 256 tokens, so the production run at 256 has no truncation.
- **Model card:** lists `ur` among 34 claimed languages (machine-translated training data); explicitly warns accuracy is lower for low-resource languages. **No Roman-Urdu claim.** Nearest romanised datapoint: TextDetox Hinglish (romanised Hindi) AUC 0.749 per the bundled `eval\this_model.json`.
- **Roman Urdu (empirical):** the held-out ur splits contain **0 Latin-only rows**, so Roman-Urdu classification quality is **not measured** here. Tokenizer probes: 4 romanised-Urdu/Hinglish sentences → 1.79 subwords/word, **0 unk** tokens → the tokenizer can represent Roman Urdu text, but that says nothing about classification accuracy. Roman-Urdu coverage remains **UNMEASURED**.

## 6. Runtime and resources (actually measured)

| Item | Measured |
|---|---|
| RAM free before run | 6.02 GB (of 15.63 GB total; system was contended) |
| RAM free after run | 4.50 GB (≈1.5 GB consumed incl. torch runtime + weights, fp32) |
| Peak RSS | not measured (psutil absent); bounded by the 1.5 GB free-RAM delta + 536 MB weights |
| Model load (incl. imports) | 35.48 s |
| Inference | 206.31 s for 300 texts ≈ **688 ms/text** (batch 32, max_len 96, torch threads=4) — production adapter reported ~336 ms/text for ur at max_len 256 on a less contended box |
| Total script wall time | 241.87 s, exit code **0** |
| First attempt (max_len 256, batch 16) | **aborted** by 150 s harness timeout mid-inference — no artifacts written; rerun at max_len 96 succeeded. Clean abort, no hang. |

Command (exact):
```
$env:PYTHONIOENCODING='utf-8'; $env:HF_HUB_OFFLINE='1'
& 'C:\Users\gokul\OneDrive\Desktop\zip project\comment toxicity\.venv\Scripts\python.exe' 'C:\Users\gokul\AppData\Local\Temp\p42_cand_eval.py'
```
Exit code: 0. Truncation check (`p42_trunc_check.py`, tokenizer-only): exit code 0.

## 7. Limitations

1. **Same checkpoint as the production baseline** — this evaluation cannot unlock the gate; it confirms the Phase 3 ur result is a property of the model, not of the adapter. No other multilingual toxicity model exists locally to test.
2. max_len 96 vs production 256: 10/180 test rows truncated (max 118 tokens). Test AUC 0.7006 vs baseline 0.7044 suggests negligible effect, but the FPR delta (0.30 vs 0.2556) could partly reflect this + threshold-grid granularity (0.01 vs 0.05 steps) and threshold operating-point variance near a flat F1 region.
3. n=180 (90 negatives): FPR Wilson CI is wide ([0.215, 0.401]); the cap of 0.15 lies below the entire CI, so the NOT PASSED verdict is robust to sampling noise.
4. Licence field absent locally; Apache-2.0 taken from the upstream README (small text fetch only).
5. Roman Urdu: zero rows in held-out data → coverage unmeasured; tokenizer probes show representability only.
6. Training data for `ur` is machine translation of English Civil Comments — cultural/idiomatic Urdu abuse is under-represented (model card limitation, confirmed by the weak val AUC 0.79).
7. Peak RSS not instrumented (psutil unavailable); RAM reported as free-memory delta only.

## 8. Recommendation (informational, no action taken)

The ur FPR gate cannot be met by re-tuning this checkpoint (val sweep shows FPR/F1 trade-off saturates; at val FPR 0.15 test FPR drifts to 0.30). Unlocking requires a model with better Urdu/low-resource discrimination (e.g. a TextDetox-style Urdu-trained classifier) or Urdu-native data — neither is available locally, and neither was downloaded per task constraints.
