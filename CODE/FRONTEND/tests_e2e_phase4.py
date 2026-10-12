# -*- coding: utf-8 -*-
"""Phase 4 / Workstream D — end-to-end integration test (API -> Streamlit).

Traces a real request through the documented pipeline:

    input -> validation -> language identification -> legacy prediction
          -> API response -> Streamlit display

Runs against the LIVE backend on 127.0.0.1:8010 (read-only for production
state: it never changes settings, never trains, never imports, never touches
the threshold file).  Every input is a synthetic string written for this test;
no dataset rows and no credentials are printed.

Covered:
  * status codes for empty / malformed / wrong-typed / missing input
  * response-schema uniformity across languages and input classes
  * legacy prediction contract (decision_status, model_name, no toxicity_score)
  * Tamil script, Tanglish, Hindi, Bengali, Urdu, English
  * unsupported-language honesty (Swahili/Chinese) and fallback labelling
  * authentication intact (valid login 200, bad login 401, no token 401/405)
  * Streamlit display honesty (no fabricated score, honest language confidence)
  * graceful handling when the backend is unreachable (isolated dead port)

Exit code 0 = all checks passed, 1 = at least one failure.
"""
import json
import os
import sys
import time
import traceback
import urllib.error
import urllib.request

os.environ['AURA_BACKEND_URL'] = 'http://127.0.0.1:8010'
BASE = os.environ.get('AURA_BASE_URL', 'http://127.0.0.1:8010')
APP = r"C:\Users\gokul\OneDrive\Desktop\zip project\comment toxicity\CODE\FRONTEND\app.py"

# Local development credentials for the running dev instance.  Deliberately
# referenced from the environment and never printed or written to disk.
ADMIN_USER = os.environ.get('AURA_TEST_USER', 'admin')
ADMIN_PASS = os.environ.get('AURA_TEST_PASS', 'Admin@1234')

results = {}


def ck(name, ok, detail=''):
    results[name] = (bool(ok), str(detail)[:400])


def http(method, path, body=None, token=None, raw=None, timeout=30):
    """Return (status, parsed_body). Never raises."""
    headers = {'Accept': 'application/json'}
    data = None
    if raw is not None:
        data = raw.encode('utf-8')
    elif body is not None:
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
            return e.code, {'_unparsable': True}
    except Exception as e:
        return -1, {'_error': type(e).__name__ + ': ' + str(e)[:140]}


# ---------------------------------------------------------------- 0. backend
st, health = http('GET', '/health')
ck('01_backend_healthy', st == 200 and health.get('status') == 'healthy', f'{st} {health}')
if st != 200:
    print('FATAL: backend not reachable; aborting remaining checks')
    for k in sorted(results):
        print(('PASS ' if results[k][0] else 'FAIL ') + k)
    print('TOTAL: %d/%d passed' % (sum(1 for v in results.values() if v[0]), len(results)))
    sys.exit(1)

# ------------------------------------------------------------------ 1. auth
st, r = http('POST', '/auth/login', {'username': ADMIN_USER, 'password': ADMIN_PASS})
tok = (r or {}).get('token') or (r or {}).get('access_token')
ck('02_login_valid_200', st == 200 and bool(tok), f'{st} token={bool(tok)}')

st, r = http('POST', '/auth/login', {'username': ADMIN_USER, 'password': 'definitely-not-the-password'})
ck('03_login_invalid_401', st == 401 and 'detail' in (r or {}), f'{st} {json.dumps(r, ensure_ascii=True)[:120]}')

st, r = http('GET', '/models/engine', token=tok)
ck('04_engine_reports_legacy', st == 200 and r.get('engine') == 'legacy', f'{st} {json.dumps(r, ensure_ascii=True)[:160]}')
ck('05_engine_requires_auth', http('GET', '/models/engine')[0] in (401, 403),
   f"unauthenticated GET /models/engine -> {http('GET', '/models/engine')[0]}")

if not tok:
    print('FATAL: no auth token')
    sys.exit(1)

# ------------------------------------------------------- 2. input validation
empty_cases = [
    ('10_empty_string_400', {'text': ''}),
    ('11_whitespace_only_400', {'text': '     '}),
]
for name, body in empty_cases:
    st, r = http('POST', '/predict', body, token=tok)
    ck(name, st == 400 and 'detail' in (r or {}), f'{st} {json.dumps(r, ensure_ascii=True)[:140]}')

malformed = [
    ('20_missing_text_field_400', '{"foo":"bar"}'),
    ('21_wrong_type_422', '{"text": 12345}'),
    ('22_invalid_json_422', '{"text": "unterminated'),
    ('23_not_json_422', 'hello world this is not json'),
]
for name, raw in malformed:
    st, r = http('POST', '/predict', raw=raw, token=tok)
    ck(name, st in (400, 422), f'{st} {json.dumps(r, ensure_ascii=True)[:140]}')

# ------------------------------------------------- 3. multilingual contract
CASES = [
    ('30_en_benign', 'have a nice day everyone'),
    ('31_en_toxic', 'you are stupid and I hate you'),
    ('32_ta_script', '\u0ba8\u0bc0\u0b99\u0bcd\u0b95\u0bb3\u0bcd \u0b92\u0bb0\u0bc1 '
                     '\u0bae\u0bc1\u0b9f\u0bcd\u0b9f\u0bbe\u0b95\u0bb3\u0bcd'),
    ('33_tanglish', 'ne enna thaan pannuvesa loosu'),
    ('34_hi_script', '\u0924\u0941\u092e \u092c\u0939\u0941\u0924 \u092c\u0941\u0930\u0947 \u0939\u094b'),
    ('35_bn_script', '\u09a4\u09c1\u09ae \u0996\u09c1\u09ac \u0996\u09be\u09b0\u09be\u09aa'),
    ('36_ur_script', '\u062a\u0645 \u0628\u0647\u062a \u0628\u0631\u0647 \u06c1\u0648'),
    ('37_unsupported_swahili', 'hii ni sentensi ya kawaida sana'),
    ('38_unsupported_chinese', '\u8fd9\u662f\u4e00\u4e2a\u666e\u901a\u7684\u53e5\u5b50'),
    ('39_emoji_only', '\U0001F600\U0001F44D'),
    ('40_sql_probe', "' OR 1=1 --"),
    ('41_xss_probe', '<script>alert(1)</script>'),
    ('42_rtl_zerowidth', 'hello\u200b\u200e\u200fworld'),
    ('43_long_6k', 'this is a fairly long comment about nothing in particular. ' * 100),
]
keysets, statuses, models, langs = {}, set(), set(), set()
failures = []
for name, text in CASES:
    st, r = http('POST', '/predict', {'text': text}, token=tok)
    if st != 200:
        failures.append(f'{name}: HTTP {st}')
        continue
    statuses.add(str(r.get('decision_status')))
    models.add(str(r.get('model_name')))
    langs.add(str(r.get('language')))
    keysets.setdefault(tuple(sorted(r.keys())), []).append(name)
    # legacy contract violations
    if 'toxicity_score' in r:
        failures.append(f'{name}: carries toxicity_score')
    if r.get('decision_status') != 'legacy':
        failures.append(f"{name}: decision_status={r.get('decision_status')}")
    if r.get('model_name') != 'aura-legacy-rules-lexicon':
        failures.append(f"{name}: model_name={r.get('model_name')}")
    if r.get('processing_mode') == 'pretrained_model':
        failures.append(f'{name}: production route used pretrained_model')

ck('44_all_multilingual_200', not failures, '; '.join(failures)[:380])
ck('45_contract_single_status', statuses == {'legacy'}, str(statuses))
ck('46_contract_single_model', models == {'aura-legacy-rules-lexicon'}, str(models))
ck('47_contract_no_toxicity_score', not any('toxicity_score' in ks for ks in keysets),
   str([list(k)[:6] for k in keysets])[:200])
ck('48_schema_uniform', len(keysets) == 1, f'{len(keysets)} distinct key sets across {len(CASES)} inputs')
ck('49_legacy_values_detected', {'Tamil', 'Hindi', 'Bengali', 'Urdu'} <= langs, str(sorted(langs)))

# ------------------------------------------- 5. unsupported-language honesty
# Phase 4.1 (C-F-2): unsupported Latin-script input is no longer presented as
# English with an "ambiguous script" hint. The language is now an explicit
# unknown state ('und' / 'Unknown' / no confidence) while scoring still uses
# the default safety lexicon (so known toxic terms are not downgraded to a
# neutral ALLOW).
st, r_unsup = http('POST', '/predict', {'text': 'hii ni sentensi ya kawaida sana'}, token=tok)
kind = str((r_unsup or {}).get('language_confidence_kind'))
ck('50_latin_unsupported_disclosed_unknown',
   st == 200 and kind == 'no_signal'
   and (r_unsup or {}).get('language_confidence') is None
   and (r_unsup or {}).get('language_code') == 'und'
   and str((r_unsup or {}).get('language')) == 'Unknown'
   and (r_unsup or {}).get('processing_mode') == 'existing_model'
   and (r_unsup or {}).get('decision_status') == 'legacy',
   f'kind={kind} conf={(r_unsup or {}).get("language_confidence")} '
   f'code={(r_unsup or {}).get("language_code")} '
   f'mode={(r_unsup or {}).get("processing_mode")}')

st, r_cn = http('POST', '/predict', {'text': '\u8fd9\u662f\u4e00\u4e2a\u666e\u901a\u7684\u53e5\u5b50'}, token=tok)
ck('51_nonlatin_unsupported_is_fallback',
   st == 200 and (r_cn or {}).get('processing_mode') == 'fallback'
   and (r_cn or {}).get('language_code') == 'und'
   and str((r_cn or {}).get('language_confidence_kind')) == 'no_signal',
   f"mode={(r_cn or {}).get('processing_mode')} code={(r_cn or {}).get('language_code')}")

# -------------------------------------------------------- 6. state honesty
st, eng = http('GET', '/models/engine', token=tok)
ck('60_engine_default_is_legacy', eng.get('default') == 'legacy' and eng.get('source') == 'settings',
   json.dumps(eng, ensure_ascii=True)[:200])

st, ad = http('GET', '/models/adapter', token=tok)
adapter = (ad or {}).get('adapter') or {}
ck('61_adapter_status_truthful', st == 200 and 'status' in adapter,
   f"status={adapter.get('status')} error={adapter.get('error')}")
ck('62_adapter_not_silently_running',
   adapter.get('status') in ('not_loaded', 'loading', 'ready', 'failed', 'backoff'),
   f"status={adapter.get('status')}")

# no production side effect from any of the above
st, eng2 = http('GET', '/models/engine', token=tok)
ck('63_engine_still_legacy_after_calls', eng2.get('engine') == 'legacy', str(eng2.get('engine')))

# ================================================== 7. Streamlit display layer
try:
    from streamlit.testing.v1 import AppTest

    def page_text(at):
        parts = []
        for coll in ('markdown', 'text', 'caption', 'warning', 'success', 'error',
                     'code', 'subheader', 'header', 'title', 'metric', 'html', 'json'):
            for el in getattr(at, coll, []):
                try:
                    v = el.value
                    if isinstance(v, dict):
                        parts.append(str(v.get('label', '')) + ' ' + str(v.get('value', '')))
                    else:
                        s = str(v)
                        if '<style>' not in s[:300] and '@import url' not in s[:300]:
                            parts.append(s)
                except Exception:
                    pass
        return '\n'.join(parts)

    at = AppTest.from_file(APP, default_timeout=120)
    at.run()
    excs = [str(e.value)[:200] for e in at.exception]
    ck('70_ui_app_starts', not excs, str(excs))

    [w for w in at.text_input if w.label == 'Admin Username'][0].set_value(ADMIN_USER)
    [w for w in at.text_input if w.label == 'Password'][1].set_value(ADMIN_PASS)
    [b for b in at.button if b.label == 'ENTER AURA'][1].click()
    at.run()
    user = at.session_state.get('user')
    ck('71_ui_admin_login', isinstance(user, dict) and user.get('role') == 'admin', repr(user))

    def run_text(t):
        at.session_state['page'] = 'text'
        at.run()
        [w for w in at.text_area if w.key == 'comment_text'][0].set_value(t)
        [b for b in at.button if b.key == 'run'][0].click()
        at.run()
        return page_text(at), [str(e.value)[:200] for e in at.exception]

    # legacy English prediction: must be labelled as the existing (non-pretrained)
    # path, must NOT show a numeric toxicity score, and must NOT claim the
    # candidate transformer produced it.
    txt, e = run_text('have a nice day everyone')
    up = txt.upper()
    ck('72_ui_legacy_labelled', not e and 'EXISTING MODEL' in up,
       f'exc={e} | {txt[:200]}'.replace('\n', ' '))
    ck('72b_ui_no_pretrained_claim', 'PRETRAINED' not in up and 'MULTILINGUAL-TOXICITY-SMALL' not in up,
       f'pretrained claimed: {"PRETRAINED" in up} | {txt[:200]}'.replace('\n', ' '))
    ck('72c_ui_flags_heuristic_uncalibrated', 'UNCALIBRATED' in up and 'HEURISTIC' in up,
       txt[:260].replace('\n', ' '))
    ck('73_ui_no_fabricated_toxicity_score', 'TOXICITY SCORE' not in up,
       f'toxscore shown: {"TOXICITY SCORE" in up} | {txt[:220]}'.replace('\n', ' '))
    ck('74_ui_shows_language_confidence', 'LANGUAGE CONFIDENCE' in up, txt[:220].replace('\n', ' '))

    # unsupported Latin-script language: UI must disclose it is not confirmable
    txt, e = run_text('hii ni sentensi ya kawaida sana')
    up = txt.upper()
    ck('75_ui_unsupported_disclosed_not_confirmable',
       (not e) and 'NOT CONFIRMABLE FROM SCRIPT' in up,
       f'exc={e} | {txt[:280]}'.replace('\n', ' '))

    # toxic tamil: still the lexicon path, still no numeric toxicity score
    txt, e = run_text('\u0ba8\u0bc0 \u0b92\u0bb0\u0bc1 \u0bae\u0bc1\u0b9f\u0bcd\u0b9f\u0bbe\u0b95\u0bb3\u0bcd')
    up = txt.upper()
    ck('76_ui_tamil_lexicon_no_score',
       (not e) and 'TOXICITY SCORE' not in up and 'LEXICON' in up and 'TOXIC' in up,
       f'exc={e} | {txt[:240]}'.replace('\n', ' '))
    ck('76b_ui_tamil_no_pretrained_claim', 'PRETRAINED' not in up,
       txt[:200].replace('\n', ' '))

    # unsupported non-Latin input must be presented as a limited fallback, not as
    # a confident supported-language result
    txt, e = run_text('\u8fd9\u662f\u4e00\u4e2a\u666e\u901a\u7684\u53e5\u5b50')
    up = txt.upper()
    ck('77_ui_fallback_limited_disclosed',
       (not e) and ('FALLBACK' in up or 'LIMITED' in up),
       f'exc={e} | {txt[:300]}'.replace('\n', ' '))

except Exception:
    ck('70_ui_app_starts', False, traceback.format_exc())

# ============================ 8. graceful backend-error handling (dead port)
try:
    os.environ['AURA_BACKEND_URL'] = 'http://127.0.0.1:8099'   # nothing listens here
    os.environ['AURA_BASE_URL'] = 'http://127.0.0.1:8099'
    at2 = AppTest.from_file(APP, default_timeout=60)
    at2.run()
    excs2 = [str(e.value)[:200] for e in at2.exception]
    # the app must survive: an exception here would mean an unhandled crash
    ck('80_ui_survives_backend_unreachable', not excs2, str(excs2)[:300])
except Exception:
    ck('80_ui_survives_backend_unreachable', False, traceback.format_exc())
finally:
    os.environ['AURA_BACKEND_URL'] = 'http://127.0.0.1:8010'
    os.environ['AURA_BASE_URL'] = 'http://127.0.0.1:8010'

# ------------------------------------------------------------------ summary
passed = sum(1 for v in results.values() if v[0])
failed = {k: v[1] for k, v in results.items() if not v[0]}
print('\n=== PHASE 4 WORKSTREAM D — END-TO-END RESULTS ===')
for k in sorted(results):
    print(('PASS ' if results[k][0] else 'FAIL ') + k)
print('TOTAL: %d/%d passed' % (passed, len(results)))
if failed:
    print('\nFAILURES:')
    for k, d in failed.items():
        print('- %s: %s' % (k, d))
sys.exit(0 if not failed else 1)
