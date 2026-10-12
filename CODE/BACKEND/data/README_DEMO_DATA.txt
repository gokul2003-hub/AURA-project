AURA COMMENT TOXICITY — DEMO DATASET README
============================================

WHAT THIS IS
------------
`data/raw/demo_dataset.csv` is **DEMO DATA** written by hand for the AURA
comment-toxicity project so that dataset management, statistics, charts,
train/validation/test splitting, and the pure-Python Naive Bayes training
pipeline can be developed and tested end-to-end.

It is:
  * DEMO DATA for DEVELOPMENT ONLY.
  * NOT a public benchmark.
  * NOT a real training corpus.
  * NOT scraped from any website, platform, or user.
  * NOT representative of any real population or language community.

The 100 rows are short, invented English / code-mixed (Hinglish-Tanglish)
chat-style comments. Labels (toxic, severe_toxic, obscene, threat, insult,
identity_hate) are synthetic and were assigned manually by the author of this
file to give a realistic-looking, majority non-toxic distribution
(78 non-toxic / 22 toxic). The toxic rows are intentionally mild and exist
only to exercise the label columns.

SCHEMA
------
Header (exact):
    comment,toxic,severe_toxic,obscene,threat,insult,identity_hate,source

All rows have source=demo. All label values are 0 or 1.

HOW IT IS USED
--------------
1. On first use, `ml_service.py` seeds the empty `dataset_samples` table in
   `aura.db` from this CSV (marker file: `data/processed/.demo_seeded`).
2. `split_dataset()` deduplicates + shuffles (seeded) and writes
   `data/train/train.csv`, `data/validation/validation.csv`,
   `data/test/test.csv` (70/15/15).
3. `train_model()` trains a pure-Python Multinomial Naive Bayes classifier
   on train.csv and evaluates it on test.csv.

DO NOT USE FOR
--------------
Do not cite these numbers as benchmark results, do not publish them as model
quality claims, and do not treat this file as a toxicity annotation dataset.
Replace it with a properly licensed corpus (and document its licence here)
before any real training or evaluation.

REGENERATING
------------
Edit `data/raw/demo_dataset.csv` directly (keep the exact header, keep every
label as 0/1, keep comments free of raw commas or quote them according to
RFC 4180), then delete `data/processed/.demo_seeded`, TRUNCATE or clear only
the `dataset_samples` table rows you own, and call `ml_service.ensure_dirs()`
followed by any dataset function to re-seed. Never DROP tables in aura.db.
