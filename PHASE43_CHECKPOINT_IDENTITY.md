# AURA Phase 4.3 — Section 4: CHECKPOINT IDENTITY

**Scope:** establish the byte-level identity of the single local model checkpoint, decide whether *any*
genuinely different candidate exists, recompute uncertainty for the Phase 4.2 vs Phase 3 baseline
comparison **without loading the model**, freeze the held-out test set, and give sample-size guidance.

**Method:** SHA256 hashing + JSON parsing in pure Python (`hashlib`/`json`/`math`), throwaway scripts in
`%TEMP%`. **No model load, no inference, no download, no backend start, no engine switch, no retrain.**
Only this file was written.

---

## 1. Checkpoint hashing (both cache locations)

Snapshot dir (both copies): `...\3baf7739b9ba7d49dc389851bb336f8a03a6cbef\`

| File | Bytes | SHA256 (copy A = `models/hf_cache/…`) | SHA256 (copy B = `models/hf_cache/hub/…`) | Identical |
|---|---:|---|---|---|
| `model.safetensors` | 562,591,100 | `14c3250b4784891919040a56e04b410da3aa2fa057148942e0b815997b5f45ec` | `14c3250b4784891919040a56e04b410da3aa2fa057148942e0b815997b5f45ec` | **YES** |
| `config.json` | 2,317 | `cfd6935691cc4225216fa04d32cca9669d85521d36da74c6ff42d7aa00da4365` | `cfd6935691cc4225216fa04d32cca9669d85521d36da74c6ff42d7aa00da4365` | **YES** |
| `tokenizer.json` | 34,363,286 | `4379fe7f4a7af10b1ac15ffc8ae90f446f92082393699e9dd54b8c3b5ec0abad` | `4379fe7f4a7af10b1ac15ffc8ae90f446f92082393699e9dd54b8c3b5ec0abad` | **YES** |
| `tokenizer_config.json` | 46,440 | `ea349495764b24570b4560fe2e4a557e5c0a47e6bce782c2409b1d6445cf8633` | `ea349495764b24570b4560fe2e4a557e5c0a47e6bce782c2409b1d6445cf8633` | **YES** |
| `special_tokens_map.json` | 636 | `baec30ea10906f16adb8c18af7a34023002c1746542612b8b41c9f09e1351351` | `baec30ea10906f16adb8c18af7a34023002c1746542612b8b41c9f09e1351351` | **YES** |

- **The two cache copies are byte-identical for every model file.** They are two HF-cache layouts of the
  same snapshot, not two models. Copy A contains only the 5 model files; copy B additionally carries the
  upstream sidecar dirs `eval/`, `training/`, `onnx/` (metadata only — **no ONNX weights on disk**).
- **Upstream cross-check:** `hf_cache/hub/…/trees/3baf7739….json` (the HF repo tree for that exact commit)
  records `"lfs_sha256": "14c3250b4784891919040a56e04b410da3aa2fa057148942e0b815997b5f45ec"` for
  `model.safetensors` (size 562,591,100) and `4379fe7f…abad` for `tokenizer.json`. **Our computed hashes
  match the upstream commit's declared LFS hashes exactly** → the weights are unmodified, un-tampered
  bytes of commit `3baf7739b9ba7d49dc389851bb336f8a03a6cbef`.
- Both `refs/main` files point to `3baf7739b9ba7d49dc389851bb336f8a03a6cbef`.
- **Full safetensors SHA256 (both copies):**
  `14c3250b4784891919040a56e04b410da3aa2fa057148942e0b815997b5f45ec`
- Repository-wide weight inventory (`*.safetensors|*.bin|*.onnx`, excluding `.venv`): **exactly 2 files,
  both this checkpoint** (the two cache copies). No second model exists anywhere under ROOT.

---

## 2. `config.json` identity (2,317 B)

| Field | Value |
|---|---|
| `model_type` | **`modernbert`** |
| `architectures` | `["ModernBertForSequenceClassification"]` |
| `problem_type` | `multi_label_classification` (sigmoid multi-label) |
| `num_labels` | **key absent** — implied **7** by `id2label` |
| `_name_or_path` | **key absent** (no local provenance string in config) |
| licence field | **absent** — no `license`/`licence` key in `config.json` or `tokenizer_config.json` |
| commit/revision metadata | **absent** from config; revision lives only in the cache path / `refs/main` |
| `transformers_version` | `5.17.0` |
| geometry | `hidden_size` 384, `num_hidden_layers` 22, `intermediate_size` 1152, `num_attention_heads` 6, `vocab_size` 256000, `max_position_embeddings` 8192, `dtype` float32, `classifier_pooling` mean, `classifier_activation` gelu |

`id2label` (order = head index):

```
0 toxicity           1 severe_toxicity   2 obscene        3 threat
4 insult             5 identity_attack   6 sexual_explicit
```

`label2id`: `identity_attack:5, insult:4, obscene:2, severe_toxicity:1, sexual_explicit:6, threat:3, toxicity:0`.

**Toxicity = index 0** — the single score the adapter exposes.

### Sidecar identity/provenance files (copy B only)

- **`eval/this_model.json` (2,159 B)** — upstream authoring metadata, keyed by the *upstream build path*
  `/fast/awuhrmann/agent-outputs/run-20260923-130458/720d8595-01bf-4e25-ba2c-fb389c35372c/model`.
  Asserts: the same 7 labels in the same order (`labels` == `mapped`, identity mapping), Civil test
  n=20,000 mean AUC 0.9878 / toxicity AUC 0.9719, plus per-language Toxicity-Detoxiset AUCs
  (am, ar, de, en, es, fr, he, hi, hin, it, ja, ru, tt, uk, zh). **No `ur` and no `bn` entry** — upstream
  never measured Urdu. Also no commit hash inside.
- **`training/val_metrics.json` (79 B)**: `{"step": 6000, "macro_f1": 0.9499221996171535,
  "bce": 0.17273980994215296}` — an *upstream training-run* validation checkpoint (step 6000), **not**
  an AURA/Urdu validation result. Must not be confused with our own `ur_val` metrics.
- `training/train_log.json`: base `jhu-clsp/mmBERT-small`, 2 epochs, lr 5e-5, seed 0, 9,868 steps,
  `n_train` 890,982 / `n_val` 18,327, toxic share 0.229, per-language ~11,900 rows × 33 languages
  (**Urdu 11,896 — machine translations of English Civil Comments**).
- `eval/baselines.json`: upstream comparison vs `unitary/unbiased-toxic-roberta`,
  `unitary/multilingual-toxic-xlm-roberta`, `unitary/toxic-bert` — upstream-only artefacts, **not locally
  runnable (their weights are not on disk)**.
- `onnx/quantization_check.json`: fp32 18.5 ms, best variant `gather_only` (agree 0.9955, 268 MB);
  `gather_int8_matmul_q4` degrades (agree 0.9107) → quantisation rejected upstream.

---

## 3. Production baseline's declared model identity

| Source (read-only) | Declared identity |
|---|---|
| `CODE/BACKEND/models/phase3_benchmark.json → model.model_id` | `Horizon-Labs/multilingual-toxicity-small` |
| `CODE/BACKEND/models/phase2_benchmark.json → model.model_id` | `Horizon-Labs/multilingual-toxicity-small` |
| `CODE/BACKEND/model_adapter.py:118` | `_env("AURA_MODEL_ID", "Horizon-Labs/multilingual-toxicity-small")` |
| `CODE/BACKEND/model_adapter.py:400` | responses echo `model_id` from that config |
| `CODE/BACKEND/backend.py:1005,1013` | reports `model_id` / `model_name` straight from the adapter |
| Recorded **weights hash** in any production record | **NONE** |
| `model_adapter.py:415-420 _model_version()` | `sha256(model_id_string)[:8]` — a *hash of the id string*, **not a hash of the weights** |

**Verdict (definitive): the on-disk checkpoint IS the baseline model.** Every production record declares
the same `model_id`, that `model_id` resolves to exactly one local snapshot
(`hf_cache*/models--Horizon-Labs--multilingual-toxicity-small` → `refs/main` = `3baf7739…`), and no other
weights file exists under ROOT. No production record pins a weight hash, so byte-level equality with
"the baseline" can only be argued the same way production identifies it — by `model_id` + single local
snapshot + upstream LFS hash match. It is one checkpoint, not two.

---

## 4. Verdict: is there a genuinely different locally available candidate?

**NO.**

- Exactly **one** model exists locally (two byte-identical cache copies of one HF commit).
- Phase 4.2's "candidate" **is** the Phase 3 baseline checkpoint — same `model_id`, same bytes, same
  revision. The Phase 4.2 ↔ Phase 3 metric deltas come from harness/protocol differences
  (threshold grid, `max_len`, val-selection noise), **not** from a different model.
- The only other multilingual models referenced anywhere (`unitary/*`, upstream baselines in
  `eval/baselines.json`) exist **as JSON metadata only** — their weights are not on disk and were not
  downloaded.
- **Re-labelling this identical checkpoint as an "improved candidate" would be fabrication.**
  **No such claim is made here or in any Phase 4.x deliverable.** Any future "new model" claim must
  present a *different* safetensors SHA256.

---

## 5. Uncertainty (pure-Python Wilson; **no model load**)

Wilson score interval, 95% (`z = 1.959964`): `centre = (p̂ + z²/2n)/(1 + z²/n)`,
`half = z·√(p̂(1−p̂)/n + z²/4n²)/(1 + z²/n)`.

| Metric | Phase 4.2 (thr 0.38) | 95% CI | Phase 3 baseline (thr 0.40) | 95% CI |
|---|---:|---|---:|---|
| **FPR** | 27/90 = **0.3000** | **[0.2151, 0.4013]** | 23/90 = **0.2556** | **[0.1767, 0.3544]** |
| Precision | 50/77 = 0.6494 | [0.5380, 0.7465] | 47/70 = 0.6714 | [0.5550, 0.7700] |
| Recall | 50/90 = 0.5556 | [0.4527, 0.6538] | 47/90 = 0.5222 | [0.4202, 0.6224] |
| F1 | 0.5988 | [0.5096, 0.6780]* | 0.5875 | [0.4933, 0.6706]* |

\* F1 intervals by nonparametric parametric-free **bootstrap over the three 2×2 cells** (tp/fp/fn),
20,000 resamples, seed 12345 — Wilson does not apply directly to F1.

**Are 0.3000 and 0.2556 distinguishable? — NO.** Methods used (all agree):

1. **CI overlap:** [0.2151, 0.4013] ∩ [0.1767, 0.3544] = [0.2151, 0.3544] — **substantial overlap.**
2. **Two-proportion z-test (pooled):** z = **0.6656**, **p = 0.5056** (two-sided) — nowhere near 0.05.
3. **Difference CI (unpooled Wald):** Δ = +0.0444, 95% CI **[−0.0863, +0.1752]** — **contains 0.**
4. **Fisher exact two-sided** on the negative-class table `[[27, 63], [23, 67]]`: **p = 0.6179.**

**Conclusion (evidence-based):** the apparent FPR regression 0.3000 → 0.2556 (and the F1 "gain"
0.5875 → 0.5988) is **noise at n = 90 negatives / 180 test rows**. With these intervals the two runs are
statistically indistinguishable — which is exactly what one expects when both runs score *the same
bytes*: only the decision threshold moved.

---

## 6. Frozen held-out test manifest

| File | Bytes | SHA256 |
|---|---:|---|
| `CODE/BACKEND/data/phase2_eval/ur_test.csv` | 74,991 | `f18d80f3e12e07a6f185079f7af0a2adf82ab35b3518c34145a9725f0538e9c5` |
| `CODE/BACKEND/data/phase2_eval/ur_val.csv` | 51,366 | `8727f2bacf41619173066466b8c992bc9cb0596e8e33c165d0f979072c61c13a` |

**These hashes freeze the held-out set.** Any drift in `ur_test.csv` invalidates every test metric
recorded in Phase 2/3/4.x. **Future threshold tuning must use `ur_val.csv` (validation) only; the test
split must not be consulted for selection, iteration, or tie-breaking.** Re-verify these hashes before
any future benchmark run.

---

## 7. Sample-size guidance (Wilson 95%, no model load)

**(a) "CI must not straddle the other FPR"** — smallest `n_neg` such that the Wilson CI at the true rate
stays on one side of the comparison value for *all* `n ≥ n_neg` (avoids lucky small-sample dips):

| True FPR | Must not straddle | Required **negative-class** n | CI at that n |
|---:|---:|---:|---|
| 0.15 | 0.25 | **78** | [0.0903, 0.2499] |
| 0.20 | 0.30 | **89** | [0.1319, 0.2972] |
| 0.10 | 0.20 | **68** | [0.0508, 0.1976] |
| 0.05 | 0.15 | **55** | [0.0187, 0.1485] |
| 0.25 | 0.35 | **95** | [0.1760, 0.3484] |
| 0.2556 | 0.30 | **426** | [0.2167, 0.2994] |

**(b) Precision (CI half-width) at a given FPR:**

| True FPR | ±0.05 | ±0.03 | ±0.02 |
|---:|---:|---:|---:|
| 0.15 | 195 | 543 | 1,223 |
| 0.25 | **285** | **799** | **1,799** |
| 0.30 | 320 | 894 | 2,014 |

**(c) Two-proportion power (80 % power, α = 0.05, two-sided), n per group:**

| Comparison | n per group |
|---|---:|
| 0.15 vs 0.25 | **250** |
| 0.20 vs 0.30 | 293 |
| 0.2556 vs 0.30 | **1,596** |

**Gate guidance:** the current **n_neg = 90** is right at the edge for a coarse 0.15-vs-0.25 gate
(table a: 78) but is ~3× too small for any precision claim (table b) and ~18× too small to tell today's
0.2556/0.3000 apart (table c). **A defensible ur FPR gate needs roughly n_neg ≥ 250 (≈ 500 test rows at
today's 46 % toxic share) for 0.15-vs-0.25, and n_neg ≥ 800 for ±0.03 precision around FPR 0.25.**

---

## 8. Runtime / resources / licence / limitations — single model

| Property | Value |
|---|---|
| Model | `Horizon-Labs/multilingual-toxicity-small`, commit `3baf7739b9ba7d49dc389851bb336f8a03a6cbef` |
| Licence | **Apache-2.0** — asserted from the upstream model card only; **no licence field exists in the local `config.json` / `tokenizer_config.json`** (documented caveat, Phase 4.2 §licence) |
| Weights | `model.safetensors` **562,591,100 B ≈ 536.5 MiB**, fp32, **≈ 140.6 M parameters ("141 M")** |
| Architecture | ModernBert (base `jhu-clsp/mmBERT-small`): 22 layers × 384 hidden, 6 heads, vocab 256 k, max pos 8192 |
| Heads | **7 sigmoid multi-label**; decision `p_toxicity ≥ threshold`, **toxicity = index 0** |
| Memory | ≈ 560 MB for fp32 weights + tokenizer (`tokenizer.json` 34 MB) + activations → fits comfortably in 16 GB alongside other processes; measured here **without loading** |
| Latency | upstream ONNX fp32 ≈ **18.5 ms/sample** (448-sample check); no ONNX weights present locally, so Python/`transformers` path applies |
| Quantisation | int8-gather+q4-matmul rejected upstream (agreement 0.911 vs 0.996 for gather-only) — do not ship q4 |
| Limitations | Urdu training data is **machine translation of English Civil Comments** (11,896 rows); model card warns lower accuracy for low-resource languages; **no Roman-Urdu claim**; upstream `this_model.json` has **no `ur` measurement at all**; bundled eval shows weak low-resource AUCs |

---

## Bottom line

1. One checkpoint, two byte-identical cache copies, hash matches the upstream commit's own LFS hash.
2. That checkpoint **is** the production baseline (`model_id` identical everywhere).
3. **No genuinely different locally available candidate exists — NO.** No "improvement" claim is made.
4. The 0.3000 vs 0.2556 FPR difference is **not statistically distinguishable** (p = 0.51 pooled-z /
   0.62 Fisher; Δ CI [−0.086, +0.175]).
5. `ur_test.csv` is frozen at
   `f18d80f3e12e07a6f185079f7af0a2adf82ab35b3518c34145a9725f0538e9c5`; tune on validation only.
6. Gate needs **n_neg ≥ 250** (0.15 vs 0.25, Wilson non-straddling = 78 but 80 % power = 250 per group).

*Generated by a read-only Phase 4.3 subagent: no download, no deployment, no backend start, no engine
switch, no retrain, no protected file modified.*
