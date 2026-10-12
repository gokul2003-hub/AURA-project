# -*- coding: utf-8 -*-
"""FINAL AURA frontend verification (Streamlit AppTest, live backend 8010).
Covers: admin login, 8 multilingual UI predictions, all 16 nav pages
(no exceptions), and page-specific multilingual UI markers."""
import os, sys, traceback
os.environ['AURA_BACKEND_URL'] = 'http://127.0.0.1:8010'
from streamlit.testing.v1 import AppTest

APP = r"C:\Users\gokul\OneDrive\Desktop\zip project\comment toxicity\CODE\FRONTEND\app.py"
results = {}
def ck(name, ok, detail=''):
    results[name] = (bool(ok), str(detail)[:400])

def exc(at):
    try:
        return [str(e.value)[:250] for e in at.exception]
    except Exception:
        return ['<cannot read exceptions>']

def clean(v):
    if not isinstance(v, str):
        return str(v)
    if '<style>' in v[:300] or '@import url' in v[:300] or v.startswith('<div class="login'):
        return ''
    return v

def page_text(at):
    parts = []
    for coll in ('markdown', 'text', 'caption', 'warning', 'success', 'error',
                 'code', 'subheader', 'header', 'title', 'metric', 'html', 'json'):
        try:
            for el in getattr(at, coll, []):
                try:
                    v = el.value
                    if isinstance(v, dict):
                        parts.append(str(v.get('label', '')) + ' ' + str(v.get('value', '')))
                    else:
                        s = clean(v)
                        if s.strip():
                            parts.append(s)
                except Exception:
                    pass
        except Exception:
            pass
    return '\n'.join(parts)

def up(s):
    return s.upper().replace('-', ' ').replace('_', ' ')

at = AppTest.from_file(APP, default_timeout=120)
at.run()
ck('01_app_starts', not exc(at), exc(at))

# ---------------------------------------------------------------- admin login
try:
    [w for w in at.text_input if w.label == 'Admin Username'][0].set_value('admin')
    [w for w in at.text_input if w.label == 'Password'][1].set_value('Admin@1234')
    [b for b in at.button if b.label == 'ENTER AURA'][1].click()
    at.run()
    u = at.session_state['user'] if 'user' in at.session_state else None
    ck('02_admin_login', isinstance(u, dict) and u.get('role') == 'admin', repr(u))
except Exception:
    ck('02_admin_login', False, traceback.format_exc())

# ------------------------------------------------- 8 multilingual UI predictions
def run_text(t):
    at.session_state['page'] = 'text'
    at.run()
    [w for w in at.text_area if w.key == 'comment_text'][0].set_value(t)
    [b for b in at.button if b.key == 'run'][0].click()
    at.run()
    return page_text(at), exc(at)

cases = [
    ('03_ta_toxic',    'நீ ஒரு முட்டாள், உன்னை வெறுக்கிறேன்.',          ['TAMIL', 'LEXICON', 'TOXIC']),
    ('04_en_nontoxic', 'Hello, how are you today?',                    ['ENGLISH', 'EXISTING MODEL', 'NON TOXIC']),
    ('05_en_toxic',    'You are stupid and useless, I hate you.',       ['ENGLISH', 'EXISTING MODEL', 'TOXIC']),
    ('06_ta_nontoxic', 'நீ எப்படி இருக்கிறாய்? நன்றாக இருக்கிறேன்.',   ['TAMIL', 'LEXICON', 'NON TOXIC']),
    ('07_tang_toxic',  'nee vera level mudhalai, unnai verukkiren.',    ['TANGLISH', 'LEXICON', 'TOXIC']),
    ('08_tang_nontox', 'nee epdi iruka? naan nalla iruken.',           ['TANGLISH', 'NON TOXIC']),
    ('09_hi_nontoxic', 'नमस्ते, आप कैसे हैं?',                        ['HINDI', 'LEXICON', 'NON TOXIC']),
    ('10_ur_toxic',    'تم ایک بیوقوف ہو، میں تم سے نفرت کرتا ہوں.', ['URDU', 'LEXICON', 'TOXIC']),
    ('11_fp_guard',    'The class was held in the basement.',          ['ENGLISH', 'NON TOXIC']),
]
for name, text, must in cases:
    try:
        txt, e = run_text(text)
        t = up(txt)
        miss = [m for m in must if m not in t]
        heur = 'HEURISTIC' in t and 'CONFIDENCE' in t
        ck(name, (not e) and not miss and heur, 'exc=%s miss=%s heur=%s | %s' % (e, miss, heur, txt[:250].replace('\n', ' ')))
    except Exception:
        ck(name, False, traceback.format_exc())

# ------------------------------------------------------------- every nav page
pages = ['dashboard', 'review', 'comments', 'users', 'safety', 'text', 'batch',
         'voice', 'live', 'analytics', 'history', 'dataset', 'model_perf',
         'models', 'training', 'settings']
page_texts, page_sbs = {}, {}
for p in pages:
    try:
        at.session_state['page'] = p
        at.run()
        e = exc(at)
        page_texts[p] = page_text(at)
        page_sbs[p] = [str(s.label) for s in at.selectbox]
        ck('page_' + p, not e, e)
    except Exception:
        ck('page_' + p, False, traceback.format_exc())

# --------------------------------------------------- page-specific assertions
def T(p):
    return up(page_texts.get(p, ''))

ck('12_dataset_lang_filter_ui', all(x in T('dataset') for x in ('SAMPLES BY LANGUAGE', 'BY SPLIT'))
   and any(l == 'Language' for l in page_sbs['dataset'])
   and any(l.lower() == 'split' for l in page_sbs['dataset'])
   and any(l == 'Toxicity' for l in page_sbs['dataset']),
   str(page_sbs['dataset'])[:200])

ck('13_modelperf_by_lang_ui', 'PERFORMANCE BY LANGUAGE' in T('model_perf')
   and 'NOT EVALUATED' in T('model_perf') and 'ENGLISH (EN)' in T('model_perf'),
   page_texts.get('model_perf', '')[:300].replace('\n', ' | '))

ck('14_history_lang_filter_ui', 'Language' in page_sbs['history'],
   str(page_sbs['history']))

ck('15_analytics_lang_chart_ui', 'LANGUAGE DISTRIBUTION' in T('analytics'),
   page_texts.get('analytics', '')[:300].replace('\n', ' | '))

try:
    at.session_state['page'] = 'history'
    at.run()
    lang_sb = [s for s in at.selectbox if str(s.label) == 'Language']
    assert lang_sb, 'no language selectbox: %s' % [str(s.label) for s in at.selectbox]
    opts = [str(o) for o in lang_sb[0].options]
    assert 'ta' in opts, opts
    lang_sb[0].set_value('ta')
    at.run()
    ck('16_history_lang_filter_works', not exc(at), 'options=%s exc=%s' % (opts, exc(at)))
except Exception:
    ck('16_history_lang_filter_works', False, traceback.format_exc())

ck('17_batch_ui', 'BATCH' in T('batch') or 'COMMENT' in T('batch'), page_texts.get('batch', '')[:200])
ck('18_voice_ui', 'VOICE' in T('voice'), page_texts.get('voice', '')[:200])
ck('19_training_ui', 'TRAIN' in T('training'), page_texts.get('training', '')[:200])

# ------------------------------------------------------------------- summary
passed = sum(1 for v in results.values() if v[0])
failed = {k: v[1] for k, v in results.items() if not v[0]}
print('\n=== FINAL APPTEST RESULTS ===')
for k in sorted(results):
    print(('PASS ' if results[k][0] else 'FAIL ') + k)
print('TOTAL: %d/%d passed' % (passed, len(results)))
if failed:
    print('\nFAILURES:')
    for k, d in failed.items():
        print('- %s: %s' % (k, d))
sys.exit(0 if not failed else 1)
