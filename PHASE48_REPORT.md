# AURA Phase 4.8 — Final Report

**Outcome: A1 scratch verification EXECUTED and COMPLETE (V1–V11). Nothing
imported. Three decisive findings, one of which supersedes a Phase 4.7 concern.**

Deliverables: `PHASE48_SCRATCH_VERIFICATION.md`, this report.

---

## A1 authorization

Confirmed before downloading. Basis of record: the Phase 4.8 brief is titled
**"Approved Scratch Verification Only"** and directs scratch download,
verification and scratch cleanup. Download was therefore treated as authorised
**for scratch-only, read-only purposes**.

## Execution

6 parquet files → `%TEMP%\aura-phase48-scratch` (**outside the project tree**),
chmod **0o444 read-only**. Total ≈ 1.93 MB. **Nothing imported into AURA.**
No raw tweet text was printed or written into the project — every figure is an
aggregate count.

**Byte totals reconcile to the byte** with the card's published `download_size`
(Coarse 730,720 B; Fine 1,199,660 B).

---

## ⚠️ Finding 1 — the 2,002-row `test` split is UNLABELLED *(supersedes Phase 4.7)*

All 2,002 rows carry **`label = null`** in **both** Coarse and Fine.

**This supersedes the Phase 4.7 concern** about "not using the authors'
validation split as an independent test set". The real reason that split is
unusable is far simpler and decisive: **there are no labels to score against.**
It cannot serve any supervised purpose.

## ⚠️ Finding 2 — YAML is authoritative; the prose is wrong

V1 counts match the YAML **exactly** (7,208 / 2,002 / 800). The narrative
(7,209 / 2,003 / 801) is simply incorrect. **Prose dismissed; YAML confirmed.**

## ⚠️ Finding 3 — `Fine_Grained/validation` == `train` *(confirmed)*

Same SHA256 (`00eadf72…`), same 525,885 B, identical content **and** labels.
V6 shows 7,198 normalised texts shared. **Confirmed unusable.**

## Leakage — near-duplicates are 3–4× exact duplicates

| Pair | Near-dup (J ≥ 0.80) | Exact |
|---|---|---|
| Coarse train↔test | **15** | 4 |
| Coarse train↔validation | **5** | 2 |
| Coarse test↔validation | **2** | 1 |
| Fine train↔test | **22** | 9 |

A dedup pass relying on exact matching alone would have **missed ~75 %** of the
cross-split leakage. Combined with 19 intra-split duplicate extras in
Coarse/train, **no upstream split may be adopted as-is** — re-splitting after
deduplication is mandatory.

## Step 6 — usable negatives after exclusions

Applying `PHASE47_LABEL_MAPPING.md`, `4: Profane/Untargeted` is **excluded and
classified as unknown — never counted as a negative.**

| Pool | toxic | non-toxic | excluded | **USABLE** | Test negatives @40 % |
|---|---|---|---|---|---|
| **`Fine/train`** | 2,895 | 3,851 | **462** | **6,746** | **1,540** ✅ |
| Coarse train+validation | 3,730 | 4,278 | *n/a* | 8,008 | 1,711 |

**The 250-negative per-stratum target is comfortably met** (1,540 ≈ 6× target).

### ⚠️ The exclusion decision forces the Fine layer

**Coarse folds `Profane/Untargeted` into `Abusive/Offensive`** — with Coarse
labels it is **impossible** to honour the exclusion; the 462 profane rows become
indistinguishable from toxic ones. **The Fine layer must be used**, or the
Phase 4.7 exclusion policy is silently violated. This is a new constraint that
was not visible before the data was obtained.

**Scope:** this is the **Roman Urdu (`ur-Latn`)** stratum only. `ur-Arab`
remains at **zero**.

## Confirmed split strategy

1. Pool **`Fine/train`** (7,208) — the only labelled, non-duplicated Fine source.
2. **Discard** `Fine/validation` (duplicate) and `Fine/test` (unlabelled).
3. Dedupe (exact **+ trigram near-duplicate**).
4. Group-aware 40/20/40, failing loudly on straddling groups.
5. Assert L1–L7; freeze the test split with a SHA256 manifest.

## Verification completeness

**All V1–V11 checks COMPLETE.** No verification remains outstanding.
(`_verify.py` reported V7 partial at a 90 s budget; a pruned exhaustive re-run
closed both partial pairs — results in `PHASE48_SCRATCH_VERIFICATION.md §7`.)

## PII (V11) — lower risk than estimated

Across 10,010 rows: **`@handles` = 0**, **URLs = 4**, **emails = 0**. Handles
appear to have been **stripped upstream**, materially lowering the risk
estimated in `PHASE47_PRIVACY_PLAN.md`. Redaction controls remain appropriate;
the **special-category** concern (classes 2/3 assert religious/gender attributes)
**stands**.

Script: `latin = 10,010` (100 %), `arabic_script = 3`, `mixed = 3` — confirms
Roman Urdu only.

## Safety

| Check | Result |
|---|---|
| **Production engine** | **`legacy`** |
| `tuned_threshold.json` | `f31f4975d29a151f…` **UNCHANGED** |
| `phase2_benchmark.json` | `5a9d94e267806ea0…` **UNCHANGED** |
| `phase3_benchmark.json` | `f3a5ceb488f4a9ad…` **UNCHANGED** |
| Frozen `ur_test` / `ur_val` | **UNCHANGED** |
| SQLite integrity / FK | **ok** / **clean** |
| Rows / splits | **596**; **137 / 29 / 31 + 399 unassigned** |
| `training_runs` / `model_versions` | **8 / 12** |
| Active model | `improved_v10` |
| Imported into AURA | **NONE** |
| Benchmark metrics created | **NONE** |
| Project `data/` written | **NONE** (mtime sweep clean) |
| Raw text in any project file | **NONE** |

**Cleanup:** the 10 newly created scratch files were removed; read-only flags
cleared first. **User files and existing project data untouched.** Verification
evidence is preserved in `PHASE48_SCRATCH_VERIFICATION.md` (checksums, counts and
findings recorded there before cleanup).

## Not done (by instruction)

- **No import** into AURA.
- **No label mapping resolved** — `Profane/Untargeted` remains **excluded/unknown**; M1–M4 untouched.
- **No benchmark metrics.**
- Legal reviews **P1–P2** remain open.

## Remaining blockers and next decisions

| Blocker | Detail |
|---|---|
| **M1–M4 unresolved** | label mappings incl. `Profane/Untargeted` exclusion still unapproved |
| **P1–P2 open** | legal review of MIT vs underlying tweet rights; lawful basis |
| **Upstream splits unusable** | `test` unlabelled, `validation` duplicated, all splits leaky |
| **`ur-Arab` still zero** | commissioning (~1,250 items) not started |

**Both quality gates remain `NOT PASSED`.** Roman Urdu now has a **verified,
sufficiently-sized** labelled pool (6,746 usable, 1,540 test negatives at 40 %),
but no evaluation may run until M1–M4 and P1–P2 close. Urdu-script remains
unmeasured.
