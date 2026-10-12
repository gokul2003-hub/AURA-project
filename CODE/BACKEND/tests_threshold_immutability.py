# -*- coding: utf-8 -*-
"""Phase 4 — production immutability guard.

Direct evidence for acceptance gates 1, 2, 8 and 9:

  1. no unauthorized changes to the production engine, threshold file,
     dataset splits or the live database
  2. legacy prediction behaviour is preserved
  8. (read-only checks only — nothing here mutates state)
  9. no retraining or deployment occurred

Expected values are NOT hardcoded magic numbers: the byte-level expectations are
read from the Phase 4 baseline snapshot taken before any change
(``PHASE4_CHECKSUMS.json`` at the project root, outside the production data
directory).  Semantic expectations (threshold values, engine, splits, active
model) are asserted explicitly so a matching-but-wrong file cannot pass.

Read-only with respect to production state: the database is opened with a
read-only URI and no setting is ever written.  Exit 0 = all checks passed.
"""
import hashlib
import json
import os
import sqlite3
import sys
from pathlib import Path

BACKEND = Path(r"C:\Users\gokul\OneDrive\Desktop\zip project\comment toxicity\CODE\BACKEND")
ROOT = BACKEND.parent.parent
THRESHOLD_FILE = BACKEND / "models" / "tuned_threshold.json"
BASELINE = ROOT / "PHASE4_CHECKSUMS.json"
DB = BACKEND / "aura.db"

EXPECTED_PER_LANGUAGE = {"en": 0.55, "ta": 0.40, "ta-Latn": 0.30,
                         "hi": 0.35, "bn": 0.30, "ur": 0.40}
EXPECTED_GLOBAL = 0.35
EXPECTED_TUNED_AT = "2026-10-09T16:57:48"
EXPECTED_SPLITS = {"train": 137, "validation": 29, "test": 31, "": 399}
EXPECTED_ENGINE = "legacy"
EXPECTED_ACTIVE_MODEL = "improved_v10"
FORBIDDEN_ADOPTIONS = (0.25,)   # ta-Latn 0.25 / bn 0.25 must never be deployed

results = {}


def ck(name, ok, detail=''):
    results[name] = (bool(ok), str(detail)[:400])


# ------------------------------------------------------------ 1. threshold file
raw = THRESHOLD_FILE.read_bytes()
sha = hashlib.sha256(raw).hexdigest()
ck('01_threshold_file_exists', THRESHOLD_FILE.is_file(), str(THRESHOLD_FILE))

baseline_sha = None
if BASELINE.is_file():
    try:
        base = json.loads(BASELINE.read_text(encoding='utf-8'))
        baseline_sha = (base.get('sha256') or {}).get(
            'CODE/BACKEND/models/tuned_threshold.json', {}).get('sha256')
    except Exception as e:
        ck('02_baseline_snapshot_readable', False, str(e)[:200])
ck('02_baseline_snapshot_readable', BASELINE.is_file(), str(BASELINE))
ck('03_threshold_sha_matches_phase4_baseline',
   baseline_sha is not None and sha == baseline_sha,
   f'now={sha[:24]} baseline={str(baseline_sha)[:24]}')

t = json.loads(raw.decode('utf-8'))
ck('04_global_threshold_unchanged', t.get('threshold') == EXPECTED_GLOBAL, str(t.get('threshold')))
ck('05_per_language_thresholds_unchanged',
   t.get('per_language') == EXPECTED_PER_LANGUAGE, json.dumps(t.get('per_language')))
ck('06_tuned_at_is_phase2', t.get('tuned_at') == EXPECTED_TUNED_AT, str(t.get('tuned_at')))
ck('07_no_forbidden_025_adoption',
   all(v not in FORBIDDEN_ADOPTIONS for v in (t.get('per_language') or {}).values()),
   json.dumps(t.get('per_language')))
ck('08_fpr_cap_still_015',
   (t.get('detail') or {}).get('fpr_cap') == 0.15, str((t.get('detail') or {}).get('fpr_cap')))

# ------------------------------------------- 2. database: read-only inspection
con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True, timeout=20)
try:
    ck('10_integrity_check_ok', con.execute('PRAGMA integrity_check').fetchone()[0] == 'ok',
       str(con.execute('PRAGMA integrity_check').fetchone()[0]))
    ck('11_foreign_key_check_clean', not con.execute('PRAGMA foreign_key_check').fetchall(), 'violations present')

    settings = dict(con.execute('SELECT key, value FROM settings'))
    ck('12_engine_is_legacy', settings.get('prediction_engine') == EXPECTED_ENGINE,
       str(settings.get('prediction_engine')))
    ck('13_toxicity_threshold_unchanged', settings.get('toxicity_threshold') == '0.5',
       str(settings.get('toxicity_threshold')))

    splits = dict((r[0] or '', r[1]) for r in
                  con.execute('SELECT split, COUNT(*) FROM dataset_samples GROUP BY split'))
    ck('14_splits_unchanged', splits == EXPECTED_SPLITS, json.dumps(splits))
    ck('15_imported_rows_still_unassigned', splits.get('', 0) == 399, str(splits.get('', 0)))
    ck('16_dataset_row_count_unchanged', sum(splits.values()) == 596, str(sum(splits.values())))

    active = con.execute(
        "SELECT model_version FROM model_versions WHERE status='active' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    ck('17_active_model_unchanged', bool(active) and active[0] == EXPECTED_ACTIVE_MODEL,
       str(active))

    # no new training run during Phase 4 (Phase 4 forbids retraining)
    latest_run = con.execute('SELECT COUNT(*) FROM training_runs').fetchone()[0]
    ck('18_training_runs_count_stable', latest_run == 8, f'{latest_run} runs (baseline 8)')

    n_users = con.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    ck('19_users_not_deleted', n_users >= 13, f'{n_users} users (baseline 13, may grow via test logins)')

    # the 399 imported rows must not have acquired split assignments
    imported_assigned = con.execute(
        "SELECT COUNT(*) FROM dataset_samples WHERE external_id IS NOT NULL AND split != ''"
    ).fetchone()[0]
    ck('20_no_imported_row_assigned_to_split', imported_assigned == 0, str(imported_assigned))

    original = con.execute(
        "SELECT COUNT(*) FROM dataset_samples WHERE external_id IS NULL"
    ).fetchone()[0]
    ck('21_original_197_preserved', original == 197, str(original))
finally:
    con.close()

# --------------------------------------------- 3. live legacy prediction check
# Static guard for Phase 4 defect D-3: the regression suite must never point the
# importer at the production report path (data/external/import_report.json),
# because that destroys the audit trail of the real import.  Before the fix the
# suite used the importer's default path and overwrote that file on every run.
_src = (BACKEND / "tests_dataset_import.py").read_text(encoding="utf-8")
_flat = " ".join(_src.split())
_idx = _flat.find("cmd = [sys.executable, str(IMPORTER)")
_runner = _flat[_idx:_idx + 260] if _idx >= 0 else None
ck('22_suite_redirects_report_away_from_production',
   _runner is not None and '"--report"' in _runner,
   f'run_importer cmd: {str(_runner)[:200]}')
ck('23_suite_always_pins_db_flag',
   _runner is not None and '"--db"' in _runner,
   f'run_importer cmd: {str(_runner)[:200]}')
ck('24_suite_has_no_production_report_reference_in_code',
   'BACKEND_DIR / "data" / "external" /' not in _src
   and 'data" / "external" / "import_report' not in _src,
   'old production-path expression absent from suite source')

_prod_report = BACKEND / "data" / "external" / "import_report.json"
if _prod_report.is_file():
    _h1 = hashlib.sha256(_prod_report.read_bytes()).hexdigest()
    ck('25_production_import_report_exists', True, f'{_prod_report.stat().st_size} bytes')
else:
    ck('25_production_import_report_exists', False, 'missing')

# --------------------------------------------- 3. live legacy prediction check
BASE = 'http://127.0.0.1:8010'


def http(method, path, body=None, token=None, timeout=30):
    import urllib.error
    import urllib.request
    headers = {'Accept': 'application/json'}
    data = None
    if body is not None:
        data = json.dumps(body).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    if token:
        headers['Authorization'] = 'Bearer ' + token
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode('utf-8'))
        except Exception:
            return e.code, {}
    except Exception as e:
        return -1, {'_error': type(e).__name__}


try:
    st, r = http('GET', '/health')
    ck('30_backend_healthy', st == 200 and r.get('status') == 'healthy', f'{st} {r}')
    st, lg = http('POST', '/auth/login', {'username': os.environ.get('AURA_TEST_USER', 'admin'),
                                          'password': os.environ.get('AURA_TEST_PASS', 'Admin@1234')})
    tok = (lg or {}).get('token')
    ck('31_login_ok', st == 200 and bool(tok), str(st))
    if tok:
        st, p = http('POST', '/predict', {'text': 'you are stupid and I hate you'}, token=tok)
        ck('32_live_response_is_legacy',
           st == 200 and p.get('decision_status') == 'legacy'
           and p.get('model_name') == 'aura-legacy-rules-lexicon',
           f"status={p.get('decision_status')} model={p.get('model_name')}")
        ck('33_live_response_has_no_toxicity_score', 'toxicity_score' not in p,
           str([k for k in p if 'toxic' in k and 'score' in k]))
        ck('34_live_response_no_pretrained_mode', p.get('processing_mode') != 'pretrained_model',
           str(p.get('processing_mode')))
        st, eng = http('GET', '/models/engine', token=tok)
        ck('35_engine_endpoint_legacy', st == 200 and eng.get('engine') == 'legacy'
           and eng.get('default') == 'legacy', json.dumps(eng, ensure_ascii=True)[:200])
except Exception:
    ck('30_backend_healthy', False, str(sys.exc_info()[1])[:200])

passed = sum(1 for v in results.values() if v[0])
failed = {k: v[1] for k, v in results.items() if not v[0]}
print('\n=== PHASE 4 IMMUTABILITY GUARD ===')
for k in sorted(results):
    print(('PASS ' if results[k][0] else 'FAIL ') + k)
print('THRESHOLD sha256: ' + sha)
print('TOTAL: %d/%d passed' % (passed, len(results)))
if failed:
    print('\nFAILURES:')
    for k, d in failed.items():
        print('- %s: %s' % (k, d))
sys.exit(0 if not failed else 1)
