from __future__ import annotations
import csv, html, io, json, os, re, time
from datetime import datetime
from urllib.parse import urlencode

import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components

BACKEND_URL=os.getenv('AURA_BACKEND_URL','http://127.0.0.1:8000').rstrip('/')
RED='#FF1744'; BLACK='#080808'; CREAM='#F6F1EA'; WHITE='#FFFFFF'; INK='#151515'; MUTED='#74706B'; LINE='#DDD7D0'
st.set_page_config(page_title='AURA — Intelligent Content Safety',page_icon='✦',layout='wide',initial_sidebar_state='expanded')
st.markdown('''<style>
@import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=DM+Sans:wght@400;500;600;700;800&display=swap');
:root{--red:#FF1744;--black:#080808;--cream:#F6F1EA;--white:#FFFFFF;--ink:#151515;--muted:#74706B;--line:#DDD7D0;}
html,body,[data-testid="stAppViewContainer"],.stApp{background:var(--cream)!important;color:var(--ink)!important;font-family:'DM Sans',sans-serif!important}
[data-testid="stHeader"]{background:transparent!important} .block-container{max-width:1500px!important;padding:.45rem 2.4rem 3rem!important}
h1,h2,h3,h4{font-family:'DM Sans',sans-serif!important;color:var(--ink)!important}
.display,.display-medium,.login-title{background:linear-gradient(90deg,#111111 0%,#111111 32%,#7b1734 62%,#FF1744 100%)!important;-webkit-background-clip:text!important;background-clip:text!important;-webkit-text-fill-color:transparent!important;color:transparent!important}
.display{font-family:'Bebas Neue',sans-serif!important;font-size:clamp(3.2rem,4.3vw,4.5rem)!important;line-height:.9!important;text-transform:uppercase!important;margin:0!important}
.display-medium{font-family:'Bebas Neue',sans-serif!important;font-size:4.7rem!important;line-height:.9!important;text-transform:uppercase!important}
.eyebrow{font-size:.68rem;font-weight:800;letter-spacing:.28em;text-transform:uppercase;color:var(--red)!important;margin-bottom:.65rem}
.subtle{color:var(--muted)!important;font-size:.92rem;line-height:1.65}
.surface{background:rgba(255,255,255,.78);border:1px solid var(--line);border-radius:18px;padding:20px;box-shadow:0 14px 35px rgba(0,0,0,.05)}
.dark-panel{background:var(--black);color:white;border-radius:25px;padding:32px;box-shadow:0 25px 60px rgba(0,0,0,.16)}
.dark-panel h2,.dark-panel h3{color:white!important;font-family:'Bebas Neue'!important;font-size:2.7rem!important}
.flow-step{padding:14px 0;border-top:1px solid #292929;color:#d9d9d9;line-height:1.5} .flow-step b{color:var(--red);margin-right:15px}
.metric{background:white;border:1px solid var(--line);border-radius:17px;padding:20px;min-height:115px} .metric-label{font-size:.65rem;letter-spacing:.18em;text-transform:uppercase;color:#777;font-weight:800} .metric-value{font-family:'Bebas Neue';font-size:3.3rem;line-height:1;color:var(--red);margin-top:9px}
.result{background:var(--black);color:#fff;border:2px solid var(--red);border-radius:20px;padding:28px;margin-top:20px} .result .score{font-family:'Bebas Neue';font-size:6rem;line-height:.78;color:var(--red)} .result .level{font-family:'Bebas Neue';font-size:2.7rem;margin-top:16px} .result .meta{color:#d6d6d6;margin-top:7px}
.action{background:#111;color:#fff;border-left:4px solid var(--red);padding:14px 16px;margin-top:16px;line-height:1.55}
.signals{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:16px} .sig{background:#fff;border:1px solid var(--line);border-radius:14px;padding:13px} .sig b{display:block;font-size:.58rem;letter-spacing:.14em;color:#777;text-transform:uppercase} .sig span{font-family:'Bebas Neue';font-size:2.2rem;color:var(--red)}
.xai{background:#090909;color:#fff;border-radius:20px;border:1px solid #303030;padding:26px;margin-top:18px} .xai .xai-title{font-family:'Bebas Neue';font-size:3rem;color:var(--red)!important;-webkit-text-fill-color:var(--red)!important;background:none!important;text-transform:uppercase;margin:4px 0 16px} .xai-row{border-top:1px solid #2c2c2c;padding:15px 0;color:#ddd;line-height:1.65}
.history{background:#fff;border:1px solid var(--line);border-radius:16px;padding:17px;margin:10px 0} .badge{display:inline-block;background:#ece8e3;border-radius:999px;padding:5px 10px;font-size:.64rem;font-weight:800;margin-right:5px}
.admin-table{width:100%;border-collapse:collapse;background:#fff;border:1px solid var(--line)} .admin-table th,.admin-table td{padding:13px;border-bottom:1px solid #e7e1db;text-align:left} .admin-table th{font-size:.68rem;text-transform:uppercase;letter-spacing:.12em;color:#777}
.login-panel{min-height:697px;box-sizing:border-box;width:100%;height:100%}
.login-red{background:#FF1744!important;color:white;padding:48px 58px;display:flex;flex-direction:column;justify-content:flex-start;min-height:697px;border-radius:0!important}
.login-red *{color:white!important}
.login-red .login-heading{background:none!important;-webkit-text-fill-color:white!important;color:white!important}
.login-white{background:#F6F1EA!important;border:0;padding:0;box-sizing:border-box;min-height:697px!important;height:100%!important}
body:has(.auth-marker) .block-container{max-width:1500px!important;padding:1.2rem 2.4rem 2.4rem!important}
body:has(.auth-marker) [data-testid="stHorizontalBlock"]{column-gap:48px!important;gap:48px!important;align-items:stretch!important;margin:0!important;width:100%!important}
body:has(.auth-marker) [data-testid="stHorizontalBlock"] > [data-testid="column"]{padding:0!important;margin:0!important;min-height:697px!important;align-self:stretch!important;box-sizing:border-box!important}
body:has(.auth-marker) [data-testid="stHorizontalBlock"] > [data-testid="column"]:nth-child(1){background:#FF1744!important;flex:0 0 calc(50% - 24px)!important}
body:has(.auth-marker) [data-testid="stHorizontalBlock"] > [data-testid="column"]:nth-child(2){background:#F6F1EA!important;min-height:697px!important;padding:46px 58px!important;display:flex!important;align-items:center!important;justify-content:center!important;border:1px solid #DED6CC!important;border-radius:0!important;flex:0 0 calc(50% - 24px)!important}
body:has(.auth-marker) [data-testid="stHorizontalBlock"] > [data-testid="column"]:nth-child(2) > div{width:100%!important;max-width:700px!important;margin:0 auto!important}
body:has(.auth-marker) .login-white{display:block!important;min-height:0!important;height:auto!important;padding:0!important;border:0!important;width:100%!important;background:transparent!important}
body:has(.auth-marker) .login-white > div{width:100%!important;max-width:700px!important;margin:0 auto!important}
body:has(.auth-marker) .login-white .stTabs{width:100%!important}
body:has(.auth-marker) .login-white .stForm{background:#fff!important}
body:has(.auth-marker) .login-white .stTabs [data-baseweb="tab-list"]{justify-content:flex-start!important}
.account-card{background:#fff!important;border:1px solid #ddd7d0!important;border-radius:18px!important;padding:16px 18px!important;margin-top:25px!important;display:flex!important;align-items:center!important;gap:13px!important;box-shadow:0 8px 24px rgba(0,0,0,.05)!important}
.account-avatar{width:42px!important;height:42px!important;min-width:42px!important;border-radius:50%!important;background:#FF1744!important;color:#fff!important;display:flex!important;align-items:center!important;justify-content:center!important;font-size:18px!important;font-weight:800!important}
.account-info{min-width:0!important}.account-info b{font-size:.92rem!important;color:#30333a!important}.account-role{font-size:.58rem!important;letter-spacing:.18em!important;text-transform:uppercase!important;color:#888!important;margin-top:3px!important}
[data-testid="stSidebar"] [class*="st-key-nav_safety"] button,
[data-testid="stSidebar"] [class*="st-key-nav_history"] button,
[data-testid="stSidebar"] [class*="st-key-nav_safety"] button:hover,
[data-testid="stSidebar"] [class*="st-key-nav_history"] button:hover,
[data-testid="stSidebar"] [class*="st-key-nav_safety"] button:focus,
[data-testid="stSidebar"] [class*="st-key-nav_history"] button:focus,
[data-testid="stSidebar"] [class*="st-key-nav_safety"] button:active,
[data-testid="stSidebar"] [class*="st-key-nav_history"] button:active{background:#080808!important;color:#fff!important;border-color:rgba(255,255,255,.22)!important;box-shadow:inset 0 1px 0 rgba(255,255,255,.10),0 12px 30px rgba(0,0,0,.16)!important;transform:none!important}
.side-logo{background:#FF1744!important;color:#fff!important;-webkit-text-fill-color:#fff!important;width:48px!important;height:48px!important;min-width:48px!important;border-radius:14px!important;font-size:24px!important}
.side-logo *{color:#fff!important;-webkit-text-fill-color:#fff!important}
.login-brand{display:flex;align-items:center;gap:14px;margin-bottom:35px;margin-top:0} .login-logo{width:60px;height:60px;border-radius:17px;background:white;color:var(--red)!important;display:flex;align-items:center;justify-content:center;font-size:30px;font-weight:800} .login-brand-name{font-family:'Bebas Neue';font-size:2.3rem;line-height:1} .login-tag{font-size:.6rem;letter-spacing:.25em;margin-top:5px;opacity:.9} .login-kicker{font-size:.7rem;font-weight:800;letter-spacing:.25em;text-transform:uppercase;margin-bottom:55px} .login-heading{font-family:'Bebas Neue';font-size:4.5rem;line-height:.88;text-transform:uppercase} .login-copy{font-size:1rem;line-height:1.7;max-width:650px;margin-top:26px} .login-title{font-family:'Bebas Neue';font-size:3.4rem;line-height:.9;text-transform:uppercase} .login-sub{color:#777;margin:14px 0 24px} .login-white .stTabs{margin-top:10px!important} .login-white .stTabs [data-baseweb=tab-list]{border-bottom:1px solid #ddd7d0!important} .login-white .stTabs [aria-selected=true]{color:var(--red)!important} .login-white .stTabs [data-baseweb=tab-highlight]{background:var(--red)!important}
body:has(.auth-marker) [data-testid="stTextInput"] button svg{color:var(--red)!important;fill:var(--red)!important;stroke:var(--red)!important} body:has(.auth-marker) [data-testid="stTextInput"] button{color:var(--red)!important}
[data-testid="stSidebar"]{background:#eef0f3!important;border-right:1px solid #d6d8db}
.stButton>button{background:rgba(8,8,8,.94)!important;color:#fff!important;border:1px solid rgba(255,255,255,.22)!important;border-radius:17px!important;min-height:52px!important;font-weight:700!important;box-shadow:inset 0 1px 0 rgba(255,255,255,.10),0 12px 30px rgba(0,0,0,.16)!important;backdrop-filter:blur(12px)!important;-webkit-backdrop-filter:blur(12px)!important;transition:background .18s ease,box-shadow .18s ease,transform .18s ease!important}
.stButton>button:hover,.stButton>button:focus{background:var(--red)!important;color:#fff!important;border-color:var(--red)!important;box-shadow:0 12px 28px rgba(255,23,68,.25)!important;transform:translateY(-1px)}
.stTextInput input,.stTextArea textarea{background:#f0f2f6!important;border:1px solid #e0e0e0!important;border-radius:13px!important;color:#151515!important}
div[data-testid="stForm"]{background:#fff;border:1px solid var(--line);border-radius:17px;padding:18px}

.status-posted{color:#169447!important;font-weight:800}
.posted-status{color:#159447!important;background:#e7f6ec!important}
.flagged-status{color:#ff1744!important;background:#ffe8ed!important}
.user-row{padding:15px 18px!important;margin:0!important}

body:has(.auth-marker) .login-white button[kind="secondaryFormSubmit"]{background:#080808!important;color:#fff!important;border:1px solid #080808!important;border-radius:13px!important;min-height:52px!important;font-weight:800!important}
body:has(.auth-marker) .login-white button[kind="secondaryFormSubmit"]:hover,body:has(.auth-marker) .login-white button[kind="secondaryFormSubmit"]:focus{background:#080808!important;color:#fff!important;border-color:#080808!important;transform:none!important;box-shadow:0 10px 24px rgba(0,0,0,.16)!important}
/* FINAL REQUESTED VISUAL CHANGES — VISUAL CSS ONLY */
.display,.display-medium{
  background:linear-gradient(90deg,#080808 0%,#080808 24%,#3f1020 46%,#8d1635 70%,#FF1744 100%)!important;
  -webkit-background-clip:text!important;
  background-clip:text!important;
  -webkit-text-fill-color:transparent!important;
  color:transparent!important;
}
.display{
  font-size:clamp(4rem,4.9vw,5.2rem)!important;
  line-height:.9!important;
}
.display-medium{
  font-size:4.7rem!important;
  line-height:.9!important;
}

/* Sidebar: smaller logo, larger AURA wordmark, testuser-only round profile */
[data-testid="stSidebar"] .side-logo{
  width:34px!important;
  height:34px!important;
  min-width:34px!important;
  border-radius:10px!important;
  font-size:17px!important;
}
[data-testid="stSidebar"] .side-logo + div > div:first-child{
  font-size:2.25rem!important;
  line-height:.9!important;
}
[data-testid="stSidebar"] .side-logo + div > div:last-child{
  font-size:.48rem!important;
}
[data-testid="stSidebar"] .account-avatar.test-user-avatar{
  width:30px!important;
  height:30px!important;
  min-width:30px!important;
  border-radius:50%!important;
  background:#080808!important;
  border:2px solid #080808!important;
  color:#fff!important;
  display:flex!important;
  align-items:center!important;
  justify-content:center!important;
  font-size:12px!important;
  font-weight:800!important;
}

/* User navigation buttons: glassmorphic, red only on pointer/focus/press */
[data-testid="stSidebar"] [class*="st-key-nav_safety"] button,
[data-testid="stSidebar"] [class*="st-key-nav_history"] button,
[data-testid="stSidebar"] [class*="st-key-nav_safety"] button:focus,
[data-testid="stSidebar"] [class*="st-key-nav_history"] button:focus{
  background:rgba(8,8,8,.72)!important;
  color:#fff!important;
  border:1px solid rgba(255,255,255,.24)!important;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.12),0 12px 30px rgba(0,0,0,.16)!important;
  backdrop-filter:blur(14px)!important;
  -webkit-backdrop-filter:blur(14px)!important;
}
[data-testid="stSidebar"] [class*="st-key-nav_safety"] button:hover,
[data-testid="stSidebar"] [class*="st-key-nav_history"] button:hover,
[data-testid="stSidebar"] [class*="st-key-nav_safety"] button:active,
[data-testid="stSidebar"] [class*="st-key-nav_history"] button:active{
  background:#FF1744!important;
  color:#fff!important;
  border-color:#FF1744!important;
  box-shadow:0 12px 28px rgba(255,23,68,.25)!important;
}

/* Login: keep ENTER AURA black and improve vertical spacing inside cream panel */
body:has(.auth-marker) .login-white{
  background:#F6F1EA!important;
  padding-top:4px!important;
}
body:has(.auth-marker) .login-white .eyebrow{
  margin-bottom:10px!important;
}
body:has(.auth-marker) .login-white .login-title{
  margin-top:0!important;
  margin-bottom:16px!important;
}
body:has(.auth-marker) .login-white .login-sub{
  margin:0 0 30px!important;
}
body:has(.auth-marker) .login-white [data-testid="stFormSubmitButton"] button{
  background:#080808!important;
  color:#fff!important;
  border:1px solid #080808!important;
  border-radius:13px!important;
  min-height:52px!important;
  font-weight:800!important;
  box-shadow:0 10px 24px rgba(0,0,0,.16)!important;
}
body:has(.auth-marker) .login-white [data-testid="stFormSubmitButton"] button:hover,
body:has(.auth-marker) .login-white [data-testid="stFormSubmitButton"] button:focus,
body:has(.auth-marker) .login-white [data-testid="stFormSubmitButton"] button:active{
  background:#080808!important;
  color:#fff!important;
  border-color:#080808!important;
}

/* FINAL REQUESTED VISUAL CORRECTIONS — ONLY THE ITEMS REQUESTED */
[data-testid="stSidebar"] .side-logo{
  width:28px!important;
  height:28px!important;
  min-width:28px!important;
  border-radius:8px!important;
  font-size:14px!important;
  flex:0 0 28px!important;
}
[data-testid="stSidebar"] .login-brand{
  align-items:center!important;
  gap:11px!important;
}
[data-testid="stSidebar"] .login-brand > div:nth-child(2) > div:first-child{
  font-size:2.45rem!important;
  line-height:.88!important;
}
[data-testid="stSidebar"] .login-brand > div:nth-child(2) > div:last-child{
  font-size:.48rem!important;
  line-height:1!important;
}

/* Small, neatly aligned active-user circle; the letter is supplied by the user name. */
[data-testid="stSidebar"] .test-user-avatar{
  width:27px!important;
  height:27px!important;
  min-width:27px!important;
  max-width:27px!important;
  min-height:27px!important;
  max-height:27px!important;
  border-radius:50%!important;
  background:#080808!important;
  color:#fff!important;
  border:0!important;
  display:flex!important;
  align-items:center!important;
  justify-content:center!important;
  font-family:'DM Sans',sans-serif!important;
  font-size:11px!important;
  font-weight:800!important;
  line-height:1!important;
  margin:0!important;
}
[data-testid="stSidebar"] .test-user-avatar::after{
  content:none!important;
}

/* Main/page titles: clearly visible black → red gradient, same Bebas Neue font. */
.display,.display-medium,.login-title{
  background:linear-gradient(90deg,#080808 0%,#080808 22%,#3b0d1b 42%,#8f1638 68%,#FF1744 100%)!important;
  -webkit-background-clip:text!important;
  background-clip:text!important;
  -webkit-text-fill-color:transparent!important;
  color:transparent!important;
}
.display{
  font-size:clamp(4.15rem,5vw,5.35rem)!important;
  line-height:.9!important;
}
.display-medium{
  font-size:clamp(4.25rem,4.9vw,5.15rem)!important;
  line-height:.9!important;
}

/* User navigation buttons: solid black normally, red only on pointer/focus/press. */
[data-testid="stSidebar"] [class*="st-key-nav_safety"] button,
[data-testid="stSidebar"] [class*="st-key-nav_history"] button,
[data-testid="stSidebar"] [class*="st-key-nav_safety"] button:focus,
[data-testid="stSidebar"] [class*="st-key-nav_history"] button:focus{
  background:#080808!important;
  color:#fff!important;
  border-color:#080808!important;
}
[data-testid="stSidebar"] [class*="st-key-nav_safety"] button:hover,
[data-testid="stSidebar"] [class*="st-key-nav_history"] button:hover,
[data-testid="stSidebar"] [class*="st-key-nav_safety"] button:active,
[data-testid="stSidebar"] [class*="st-key-nav_history"] button:active{
  background:#FF1744!important;
  color:#fff!important;
  border-color:#FF1744!important;
}

/* Preserve the requested block-button alignment. */
[data-testid="stHorizontalBlock"] [data-testid="stButton"]{
  margin-top:18px!important;
}
</style>''',unsafe_allow_html=True)

def init():
 for k,v in {'token':None,'user':None,'page':'safety','result':None,'show_xai':False,'activity':[]}.items():
  if k not in st.session_state: st.session_state[k]=v
init()

def api(path,method='GET',payload=None):
    """Call AURA backend with route compatibility.

    The running backend versions used in this project have used slightly
    different prefixes/names for history and admin read endpoints.  We keep
    the moderation/auth contract unchanged and only retry safe GET aliases
    when the server returns 404.  A missing optional history/read endpoint
    never becomes the visible 'AURA: Not Found' error.
    """
    token = st.session_state.get('token')
    headers = {'Authorization': f'Bearer {token}'} if token else {}

    username = str((st.session_state.get('user') or {}).get('username', '')).strip()
    user_id = str((st.session_state.get('user') or {}).get('id', '')).strip()

    aliases = {
        '/history': [
            '/history',
            f'/history/{username}' if username else '',
            f'/history/{user_id}' if user_id else '',
            f'/user/history/{username}' if username else '',
            '/user/history',
            f'/users/{username}/history' if username else '',
            '/api/history',
            '/api/user/history',
        ],
        '/admin/comments': [
            '/admin/comments',
            '/admin/all-comments',
            '/admin/comments/all',
            '/api/admin/comments',
            '/api/admin/all-comments',
        ],
        '/admin/human-review': [
            '/admin/human-review',
            '/admin/review',
            '/admin/human_review',
            '/api/admin/human-review',
        ],
        '/admin/users': [
            '/admin/users',
            '/admin/user-profiles',
            '/admin/user_profiles',
            '/api/admin/users',
        ],
    }

    paths = [p for p in aliases.get(path, [path]) if p]
    last_404 = False

    for candidate in paths:
        try:
            r = requests.request(
                method,
                BACKEND_URL + candidate,
                json=payload,
                headers=headers,
                timeout=30
            )
        except requests.RequestException:
            # Only a real connection failure is shown as a backend error.
            st.error('AURA backend is unavailable. Start the backend on port 8000.')
            return None

        if r.status_code == 404:
            last_404 = True
            continue

        if not r.ok:
            try:
                body = r.json()
                detail = body.get('detail', 'Request failed.')
            except Exception:
                detail = r.text or f'HTTP {r.status_code}'
            st.error(f'AURA: {detail}')
            return None

        try:
            data = r.json()
        except ValueError:
            st.error('AURA: Backend returned an invalid response.')
            return None

        # Normalise common list wrappers so pages can consume every supported
        # backend response without changing the existing UI.
        if path in {'/history','/admin/comments','/admin/human-review','/admin/users'}:
            if isinstance(data, dict):
                for key in ('items','results','data','comments','history','users','reviews'):
                    if isinstance(data.get(key), list):
                        return data[key]
        return data

    # History/read data is optional for display.  Do NOT show "AURA: Not Found".
    # The moderation screen remains fully usable, and current-session activity
    # is retained locally as a fallback.
    if last_404 and method.upper() == 'GET':
        return []
    if last_404:
        st.error('AURA: Backend endpoint was not found.')
    return None

CAT_ROWS=[('Toxic','toxic'),('Severe Toxic','severe_toxic'),('Obscene','obscene'),('Threat','threat'),('Insult','insult'),('Identity Hate','identity_hate')]
LABEL_OPTIONS=['non_toxic','toxic','severe_toxic','obscene','threat','insult','identity_hate']

# --- Multilingual contract (backend returns these on every prediction) ---
LANG_CODES=['en','ta','ta-Latn','hi','te','ml','kn','bn','mr','gu','pa','ur']
LANG_NAMES={'en':'English','ta':'Tamil','ta-Latn':'Tanglish','hi':'Hindi','te':'Telugu','ml':'Malayalam','kn':'Kannada','bn':'Bengali','mr':'Marathi','gu':'Gujarati','pa':'Punjabi','ur':'Urdu','und':'Unknown','mixed':'Mixed Indian Languages'}
LANG_FLAGS={'en':'🇬🇧','ta':'🇮🇳','ta-Latn':'🇮🇳','hi':'🇮🇳','te':'🇮🇳','ml':'🇮🇳','kn':'🇮🇳','bn':'🇮🇳','mr':'🇮🇳','gu':'🇮🇳','pa':'🇮🇳','ur':'🇵🇰'}
SCRIPT_BY_LANG={'en':'Latin','ta':'Tamil','ta-Latn':'Latin','hi':'Devanagari','te':'Telugu','ml':'Malayalam','kn':'Kannada','bn':'Bengali','mr':'Devanagari','gu':'Gujarati','pa':'Gurmukhi','ur':'Arabic'}
NOT_SET='— not set —'
LANG_FIELD_OPTS=[NOT_SET]+LANG_CODES
NAME_FIELD_OPTS=[NOT_SET]+[LANG_NAMES[c] for c in LANG_CODES]+['Mixed Indian Languages','Unknown']
SCRIPT_FIELD_OPTS=[NOT_SET,'Latin','Tamil','Devanagari','Telugu','Malayalam','Kannada','Bengali','Gujarati','Gurmukhi','Arabic','Mixed','Unknown']
SPLIT_FIELD_OPTS=[NOT_SET,'train','validation','test']
SPLIT_FILTER_OPTS=['All','train','validation','test','unassigned']
LANG_FILTER_OPTS=['All']+LANG_CODES
TOX_FILTER_OPTS=['All','toxic','non_toxic']

def api_files(path, files, timeout=90, data=None):
    """POST multipart files to the AURA backend with the session Bearer token.

    Kept separate from api() so the JSON helper keeps its current behaviour.
    `data` is an optional dict of extra multipart form fields (for example the
    language hint on /voice/transcribe) sent alongside the files; callers that
    do not pass it behave exactly as before.
    Returns the parsed JSON body, or None after showing an error."""
    token = st.session_state.get('token')
    headers = {'Authorization': f'Bearer {token}'} if token else {}
    try:
        r = requests.post(BACKEND_URL + path, files=files, data=data, headers=headers, timeout=timeout)
    except requests.RequestException:
        st.error('AURA backend is unavailable. Start the backend on port 8000.')
        return None
    if not r.ok:
        try:
            detail = r.json().get('detail', 'Request failed.')
        except Exception:
            detail = r.text or f'HTTP {r.status_code}'
        st.error(f'AURA: {detail}')
        return None
    try:
        return r.json()
    except ValueError:
        st.error('AURA: Backend returned an invalid response.')
        return None

def build_path(path, params):
    """Attach only the non-empty query params to a path."""
    clean = {k: v for k, v in (params or {}).items() if v is not None and v != ''}
    if not clean:
        return path
    return f'{path}?{urlencode(clean)}'

def _num(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default

def pct_of(v):
    """Backend probabilities are 0..1; older answers used 0..100."""
    n = _num(v)
    return n if n > 1.5 else n * 100.0

def confidence_pct(r):
    return pct_of((r or {}).get('confidence'))

def lang_info(r):
    """Null-safe language metadata (code, name, script, processing mode).

    Works for prediction bodies, history items and dataset rows; an older
    backend that sends none of these simply yields empty strings."""
    if not isinstance(r, dict):
        return {'code': '', 'name': '', 'script': '', 'mode': ''}
    # Prefer the explicit code; fall back to 'language' only when it IS a code
    # (the backend may carry the display name in 'language' for older clients).
    code = str(r.get('language_code') or '').strip()
    if not code:
        cand = str(r.get('language') or '').strip()
        if cand in LANG_NAMES:
            code = cand
    name = str(r.get('language_name') or '').strip()
    if not name:
        lang_field = str(r.get('language') or '').strip()
        if lang_field in LANG_NAMES.values():
            name = lang_field
    script = str(r.get('script') or '').strip()
    mode = str(r.get('processing_mode') or '').strip()
    if not name and code:
        name = LANG_NAMES.get(code, '')
    if not code and name:
        for k, v in LANG_NAMES.items():
            if str(v).lower() == name.lower():
                code = k
                break
    if not script and code:
        script = SCRIPT_BY_LANG.get(code, '')
    return {'code': code, 'name': name, 'script': script, 'mode': mode}

def lang_flag(code):
    """Flag emoji for the 12 supported languages; anything else -> 🌐."""
    return LANG_FLAGS.get(str(code or '').strip(), '🌐')

def mode_text(mode, name=''):
    """Human label for a processing_mode value from the contract."""
    m = str(mode or '').strip()
    if m == 'pretrained_model':
        return 'Pretrained model (multilingual-toxicity-small)'
    if m == 'existing_model':
        return 'Existing Model'
    if m == 'language_lexicon':
        return f'{name or "Language"} Lexicon'
    if m == 'fallback':
        return 'Fallback · Limited'
    return ''

def model_short_name(name):
    """Short display form of a model id: 'org/model' -> 'model'."""
    s = str(name or '').strip()
    return s.rsplit('/', 1)[-1] if '/' in s else s

def decision_status_text(status):
    """Human wording for the contract's decision_status values."""
    s = str(status or '').strip()
    return {
        'predicted': 'Predicted by the model',
        'uncertain': 'Uncertain — the model is not confident in this result',
        'experimental': 'Experimental — not yet validated, treat as uncertain',
        'legacy': 'Legacy rules',
        'fallback': 'Model unavailable — used legacy rules',
    }.get(s, s)

def has_model_fields(r):
    """True when a Phase-2 model produced (or attempted) this prediction.

    Legacy responses carry decision_status='legacy', the rules model name and
    the shared threshold but none of the model's own outputs, so they keep the
    original result display unchanged."""
    if not isinstance(r, dict):
        return False
    if r.get('toxicity_score') is not None or r.get('model_error'):
        return True
    if str(r.get('processing_mode') or '').strip() == 'pretrained_model':
        return True
    if str(r.get('decision_status') or '').strip() in ('predicted', 'uncertain', 'experimental', 'fallback'):
        return True
    if str(r.get('model_coverage') or '').strip() or r.get('model_coverage_note'):
        return True
    return str(r.get('confidence_kind') or '').strip() == 'model'

def language_confidence_text(r):
    """Wording for language_confidence together with its kind.

    A percentage is only shown when the backend reports a usable value; an
    ambiguous script, no signal or a null value is reported as 'not
    confirmable from script' instead of a fabricated number.  Returns ''
    when the response carries neither field."""
    if not isinstance(r, dict):
        return ''
    kind = str(r.get('language_confidence_kind') or '').strip()
    val = r.get('language_confidence')
    if val is None and not kind:
        return ''
    if val is None or kind in ('script_ambiguous', 'no_signal'):
        return 'Language confidence: not confirmable from script'
    try:
        c = float(val)
    except (TypeError, ValueError):
        return 'Language confidence: not confirmable from script'
    if abs(c) <= 1.5:
        c *= 100.0
    txt = f'Language confidence: {c:.0f}%'
    if kind == 'script_share':
        txt += ' (script share)'
    elif kind:
        txt += f' ({kind})'
    return txt

def model_block_html(result, lang_conf_txt=''):
    """Phase-2 model summary surface for a prediction result.

    Returns '' for legacy responses (see has_model_fields) so the original
    result display stays exactly as before on the default engine."""
    if not has_model_fields(result):
        return ''
    body = ''
    name = model_short_name(result.get('model_name'))
    version = str(result.get('model_version') or '').strip()
    if name:
        body += (
            '<div style="font-family:Bebas Neue,Arial,sans-serif;font-size:1.6rem;line-height:1.15;color:#151515">'
            f'{html.escape(name)}'
            + (f' · version {html.escape(version)}' if version else '')
            + '</div>'
        )
    meta = []
    if result.get('toxicity_score') is not None:
        meta.append(f'Toxicity score: <b>{pct_of(result.get("toxicity_score")):.1f}%</b> ({_num(result.get("toxicity_score")):.3f})')
    if result.get('threshold') is not None:
        meta.append(f'Threshold: <b>{_num(result.get("threshold")):.2f}</b>')
    if meta:
        body += '<div class="subtle" style="margin-top:4px">' + ' · '.join(meta) + '</div>'
    status = str(result.get('decision_status') or '').strip()
    if status == 'fallback':
        line = '<b>Model unavailable — used legacy rules.</b>'
        err = str(result.get('model_error') or '').strip()
        if err:
            line += f'<div class="subtle" style="margin-top:3px">Reason: {html.escape(err)}</div>'
        body += f'<div class="subtle" style="margin-top:4px">{line}</div>'
    elif status:
        body += f'<div class="subtle" style="margin-top:4px"><b>Decision status:</b> {html.escape(decision_status_text(status))}</div>'
    cov = str(result.get('model_coverage') or '').strip()
    if cov:
        cov_txt = cov.replace('_', ' ')
        note = str(result.get('model_coverage_note') or '').strip()
        if note:
            cov_txt += ' · ' + note
        body += f'<div class="subtle" style="margin-top:4px"><b>Model coverage:</b> {html.escape(cov_txt)}</div>'
    if lang_conf_txt:
        body += f'<div class="subtle" style="margin-top:4px">{html.escape(lang_conf_txt)}</div>'
    if not body:
        return ''
    return '<div class="surface" style="margin-top:14px"><div class="eyebrow">PREDICTION MODEL</div>' + body + '</div>'

def support_limited(info):
    """True when the language is und/Unknown or the mode fell back."""
    if not isinstance(info, dict):
        return False
    if str(info.get('mode') or '').strip() == 'fallback':
        return True
    code = str(info.get('code') or '').strip().lower()
    name = str(info.get('name') or '').strip().lower()
    return code in ('und', 'unknown') or name == 'unknown'

def score_pct(r):
    """Heuristic risk as 0..100.

    Prefers the contract `score` (0..1) and falls back to the legacy canonical
    `risk_score`, which this app already renders out of 100 in show_result()."""
    if not isinstance(r, dict):
        return None
    if r.get('score') is not None:
        return pct_of(r.get('score'))
    if r.get('risk_score') is not None:
        return _num(r.get('risk_score'))
    risk = r.get('risk')
    if isinstance(risk, dict) and risk.get('score') is not None:
        return _num(risk.get('score'))
    return None

def language_block_html(result):
    """Prominent 'Language / Processing' line with the score vs confidence split.

    Returns an empty string when the response carries no language data at all,
    so older backend builds keep rendering exactly as before."""
    if not isinstance(result, dict):
        return ''
    info = lang_info(result)
    if not any(info.values()):
        return ''
    flag = lang_flag(info['code'])
    name = info['name'] or 'Unknown'
    script = info['script'] or 'Unknown'
    mode = mode_text(info['mode'], name) or 'Not reported'
    sc = score_pct(result)
    score_txt = f'{sc:.0f}%' if sc is not None else '—'
    conf = confidence_pct(result) if result.get('confidence') is not None else None
    conf_txt = f'{conf:.0f}%' if conf is not None else '—'
    badge = '<span class="badge" style="background:#FFE8ED;color:#FF1744">SUPPORT STATUS: LIMITED</span>' if support_limited(info) else ''
    # language_confidence + kind; ambiguous scripts / no signal / null values are
    # reported explicitly instead of as a fabricated percentage.
    lc_txt = language_confidence_text(result)
    lc_html = f'<div class="subtle" style="margin-top:4px">{html.escape(lc_txt)}</div>' if lc_txt else ''
    return (
        '<div class="surface" style="margin-top:14px">'
        '<div class="eyebrow">LANGUAGE &amp; PROCESSING</div>'
        f'<div style="font-family:Bebas Neue,Arial,sans-serif;font-size:1.85rem;line-height:1.15;color:#151515">'
        f'{flag} Language: {html.escape(name)} ({html.escape(script)}) · Processing: {html.escape(mode)}</div>'
        f'<div class="subtle" style="margin-top:5px">Score: {score_txt} <b>(heuristic)</b> · Confidence: {conf_txt} '
        '<span style="font-size:.78rem">(heuristic, uncalibrated)</span></div>'
        f'{lc_html}{badge}</div>'
    )

def cat_percentages(result):
    cats = result.get('categories') if isinstance(result, dict) and isinstance(result.get('categories'), dict) else {}
    return {key: pct_of(cats.get(key)) for key in ('toxic','severe_toxic','obscene','threat','insult','identity_hate','non_toxic')}

def top_category(cats):
    if not isinstance(cats, dict):
        return ''
    best = ''
    best_val = -1.0
    for key, val in cats.items():
        if str(key) == 'non_toxic':
            continue
        v = pct_of(val)
        if v > best_val:
            best_val = v
            best = str(key)
    return best

def bars_html(pcts):
    rows = ''
    for key, val in pcts.items():
        label = key.replace('_', ' ').upper()
        width = max(0.0, min(100.0, _num(val)))
        colour = '#169447' if key == 'non_toxic' else '#FF1744'
        rows += (
            '<div style="display:flex;align-items:center;gap:12px;margin:7px 0">'
            f'<div style="width:130px;font-size:.63rem;font-weight:800;letter-spacing:.12em">{label}</div>'
            '<div style="flex:1;background:#e9e4de;border-radius:999px;height:15px;overflow:hidden">'
            f'<div style="width:{width:.1f}%;background:{colour};height:100%"></div></div>'
            f'<div style="width:60px;text-align:right;font-weight:800;font-size:.8rem">{_num(val):.1f}%</div></div>'
        )
    return f'<div class="surface" style="margin-top:14px"><div class="eyebrow">PROBABILITY BREAKDOWN</div>{rows}</div>'

def highlight_terms(text, terms):
    body = str(text or '')
    usable = sorted({str(t).strip() for t in (terms or []) if str(t).strip()}, key=len, reverse=True)
    if not usable:
        return html.escape(body)
    pattern = re.compile('|'.join(re.escape(t) for t in usable), re.IGNORECASE)
    parts = []
    last = 0
    for m in pattern.finditer(body):
        parts.append(html.escape(body[last:m.start()]))
        parts.append('<span style="background:#FF1744;color:#fff;padding:1px 4px;border-radius:4px">' + html.escape(m.group(0)) + '</span>')
        last = m.end()
    parts.append(html.escape(body[last:]))
    return ''.join(parts)

def _opts_with(base, current):
    """Selectbox options that never drop the value already stored on a row."""
    cur = str(current or '').strip()
    if cur and cur not in base:
        return list(base) + [cur]
    return list(base)

def _lang_payload(language='', language_name='', script='', split=''):
    """Language fields for POST/PUT /dataset.

    Only non-empty values are sent (the NOT_SET sentinel is skipped) so rows
    saved through an older backend keep working, and language_name is derived
    from the code when the name itself was left unset."""
    out = {}
    lang = str(language or '').strip()
    if lang and lang != NOT_SET:
        out['language'] = lang
    name = str(language_name or '').strip()
    if (not name or name == NOT_SET) and out.get('language'):
        name = LANG_NAMES.get(out['language'], '')
    if name and name != NOT_SET:
        out['language_name'] = name
    sc = str(script or '').strip()
    if sc and sc != NOT_SET:
        out['script'] = sc
    sp = str(split or '').strip()
    if sp and sp != NOT_SET:
        out['split'] = sp
    return out

def csv_text(header, rows):
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    return buf.getvalue()

def _send_feedback(pid, correct, corrected, key_prefix):
    payload = {'prediction_id': pid, 'correct': bool(correct)}
    if not correct and corrected:
        payload['corrected_label'] = corrected
    out = api('/feedback', 'POST', payload)
    if out is None:
        st.error('Feedback could not be saved. Please try again.')
        return
    st.session_state[f'{key_prefix}_done_{pid}'] = True
    st.session_state[f'{key_prefix}_fix_{pid}'] = False
    st.rerun()

def feedback_widget(result, key_prefix='fb'):
    pid = (result or {}).get('prediction_id')
    if not pid:
        st.markdown('<div class="subtle" style="margin-top:14px">Feedback is unavailable for this result (no prediction id was returned).</div>', unsafe_allow_html=True)
        return
    if st.session_state.get(f'{key_prefix}_done_{pid}'):
        st.success('Thank you — your feedback was recorded.')
        return
    st.markdown('<div class="eyebrow" style="margin-top:16px">WAS THIS PREDICTION CORRECT?</div>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    if c1.button('Correct', use_container_width=True, key=f'{key_prefix}_correct_{pid}'):
        _send_feedback(pid, True, None, key_prefix)
    if c2.button('Incorrect', use_container_width=True, key=f'{key_prefix}_incorrect_{pid}'):
        st.session_state[f'{key_prefix}_fix_{pid}'] = True
        st.rerun()
    if st.session_state.get(f'{key_prefix}_fix_{pid}'):
        corrected = st.selectbox('Corrected label', LABEL_OPTIONS, key=f'{key_prefix}_label_{pid}')
        if st.button('SUBMIT CORRECTION', use_container_width=True, key=f'{key_prefix}_submit_{pid}'):
            _send_feedback(pid, False, corrected, key_prefix)

def predict_extras(result, comment, key_prefix='pred'):
    """Probability bars, explicit score block, toxic-word highlighting,
    feedback widget and CSV download for a /predict style response."""
    if not isinstance(result, dict):
        return
    # Language + processing mode + score vs confidence (multilingual contract).
    lang_html = language_block_html(result)
    if lang_html:
        st.markdown(lang_html, unsafe_allow_html=True)
    # Phase-2 model summary (empty for legacy responses -> display unchanged).
    lc_txt = '' if lang_html else language_confidence_text(result)
    model_html = model_block_html(result, lc_txt)
    if model_html:
        st.markdown(model_html, unsafe_allow_html=True)
    elif lc_txt:
        st.markdown(f'<div class="surface" style="margin-top:14px"><div class="subtle">{html.escape(lc_txt)}</div></div>', unsafe_allow_html=True)
    pcts = cat_percentages(result)
    st.markdown(bars_html(pcts), unsafe_allow_html=True)

    overall = str(result.get('overall_label') or ('toxic' if pcts.get('toxic', 0.0) >= 50.0 else 'non_toxic'))
    block = (
        '<div class="surface" style="margin-top:14px"><div class="eyebrow">EXPLICIT PREDICTION</div>'
        f'<div style="font-family:Bebas Neue,Arial,sans-serif;font-size:2.1rem;line-height:1.05;color:#151515">'
        f'Overall: {html.escape(overall.upper().replace("_", " "))} · Confidence: {confidence_pct(result):.1f}%</div>'
    )
    for label, key in CAT_ROWS:
        block += f'<div class="subtle" style="margin-top:3px"><b>{label}:</b> {pcts.get(key, 0.0):.1f}%</div>'
    block += f'<div class="subtle" style="margin-top:3px"><b>Non Toxic:</b> {pcts.get("non_toxic", 0.0):.1f}%</div></div>'
    st.markdown(block, unsafe_allow_html=True)

    terms = result.get('toxic_terms') if isinstance(result.get('toxic_terms'), list) else []
    method = str(result.get('highlighting_method') or 'heuristic')
    method_label = 'Heuristic keyword highlighting' if 'heuristic' in method.lower() else html.escape(method)
    # Language note for the matched terms (the lexicon that produced them).
    info = lang_info(result)
    lang_note = ''
    if info['name'] or info['code']:
        lang_note = f' · Terms matched in <b>{html.escape(info["name"] or info["code"])}</b>'
        if info['script']:
            lang_note += f' ({html.escape(info["script"])}) script'
    st.markdown('<div class="eyebrow" style="margin-top:16px">TOXIC WORD HIGHLIGHTING</div>', unsafe_allow_html=True)
    if terms:
        st.markdown(
            f'<div class="surface"><div class="subtle" style="margin-bottom:8px">{method_label} · {len(terms)} term(s) marked{lang_note}</div>'
            f'<div style="line-height:1.95">{highlight_terms(comment, terms)}</div></div>',
            unsafe_allow_html=True
        )
    else:
        st.markdown('<div class="surface"><div class="subtle">No toxic terms were returned for this comment, so nothing was highlighted.</div></div>', unsafe_allow_html=True)

    feedback_widget(result, key_prefix=key_prefix)

    header = ['comment','overall_label','confidence','toxic','severe_toxic','obscene','threat','insult','identity_hate','timestamp']
    row = [
        str(comment or ''),
        str(result.get('overall_label') or ''),
        f'{confidence_pct(result):.2f}',
    ] + [f'{pcts.get(key, 0.0):.2f}' for _, key in CAT_ROWS] + [str(result.get('created_at') or '')]
    st.download_button(
        'DOWNLOAD RESULT CSV',
        data=csv_text(header, [row]),
        file_name='aura_prediction.csv',
        mime='text/csv',
        use_container_width=True,
        key=f'{key_prefix}_download'
    )

def auth_page():
 st.markdown('<div class="auth-marker"></div>',unsafe_allow_html=True)
 left,right=st.columns([1,1],gap='large',vertical_alignment='top')
 with left:
  st.markdown('''<div class="login-panel login-red"><div class="login-brand"><div class="login-logo">✦</div><div><div class="login-brand-name">AURA</div><div class="login-tag">INTELLIGENT CONTENT SAFETY</div></div></div><div class="login-kicker">A CALM LAYER OF PROTECTION</div><div class="login-heading">UNDERSTAND WORDS.<br>PROTECT CONVERSATIONS.</div><div class="login-copy">AURA analyzes multilingual and code-mixed social content, evaluates harmful signals, explains the decision, and keeps uncertain content with a human reviewer before publication.</div><div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:8px"><span style="border:1px solid rgba(255,255,255,.75);border-radius:22px;padding:9px 15px;font-size:.65rem;font-weight:800">AI MODERATION</span><span style="border:1px solid rgba(255,255,255,.75);border-radius:22px;padding:9px 15px;font-size:.65rem;font-weight:800">EXPLAINABLE AI</span><span style="border:1px solid rgba(255,255,255,.75);border-radius:22px;padding:9px 15px;font-size:.65rem;font-weight:800">HUMAN REVIEW</span></div></div>''',unsafe_allow_html=True)
 with right:
  st.markdown('''<div class="login-white"><div class="eyebrow">WELCOME TO AURA</div><div class="login-title">YOUR SAFETY WORKSPACE.</div><div class="login-sub">Sign in or create a new account to continue.</div><div style="height:20px;border-bottom:2px solid #202020;margin-bottom:28px"></div>''',unsafe_allow_html=True)
  user_tab,admin_tab,create_tab=st.tabs(['Sign in','Admin Login','Create account'])
  with user_tab:
   with st.form('user_login'):
    u=st.text_input('Username',placeholder='Enter username')
    p=st.text_input('Password',type='password',placeholder='Enter password')
    go=st.form_submit_button('ENTER AURA',use_container_width=True)
   if go:
    out=api('/auth/login','POST',{'username':u,'password':p,'role':'user'})
    if out:
     st.session_state.token=out['token']; st.session_state.user=out['user']; st.session_state.page='safety'; st.rerun()
  with admin_tab:
   with st.form('admin_login'):
    u=st.text_input('Admin Username',placeholder='Enter admin username')
    p=st.text_input('Password',type='password',placeholder='Enter admin password')
    go=st.form_submit_button('ENTER AURA',use_container_width=True)
   if go:
    out=api('/auth/login','POST',{'username':u,'password':p,'role':'admin'})
    if out:
     st.session_state.token=out['token']; st.session_state.user=out['user']; st.session_state.page='dashboard'; st.rerun()
  with create_tab:
   with st.form('register'):
    u=st.text_input('Username',placeholder='Choose a username')
    p=st.text_input('Password',type='password',placeholder='Minimum 6 characters')
    q=st.text_input('Confirm Password',type='password',placeholder='Repeat password')
    go=st.form_submit_button('CREATE ACCOUNT',use_container_width=True)
   if go:
    if p!=q:
     st.error('Passwords do not match.')
    else:
     out=api('/auth/register','POST',{'username':u,'password':p})
     if out: st.success('Account created. Use Sign in to continue.')
  st.markdown('''<div style="margin-top:54px;font-size:.65rem;letter-spacing:.08em;color:#999;text-transform:uppercase">SECURE LOCAL SIGN-IN · AURA 2026</div></div>''',unsafe_allow_html=True)

def sidebar():
 u=st.session_state.user
 with st.sidebar:
  st.markdown('<div class="login-brand"><div class="login-logo side-logo">✦</div><div><div style="font-family:Bebas Neue;font-size:2rem;line-height:1">AURA</div><div style="font-size:.58rem;letter-spacing:.24em;color:#888">AI SAFETY</div></div></div><div class="eyebrow">WORKSPACE</div>',unsafe_allow_html=True)
  user_nav=[('safety','✦  AI Safety'),('text','◆  Text Detection'),('batch','▣  Batch Detection'),('voice','◉  Voice Detection'),('live','◈  Live Guard'),('analytics','▤  Analytics'),('history','◈  History')]
  admin_nav=[('dashboard','✦  Admin Dashboard'),('review','◈  Human Review'),('comments','▣  All Comments'),('users','◯  User Profiles')]+user_nav+[('dataset','▦  Dataset Mgmt'),('model_perf','◔  Model Performance'),('models','◇  Model Versions'),('training','▷  Training'),('settings','⚙  System Settings')]
  nav=admin_nav if u['role']=='admin' else user_nav
  for key,label in nav:
   if st.button(label,use_container_width=True,key='nav_'+key): st.session_state.page=key; st.rerun()
  avatar_html = f'<div class="account-avatar test-user-avatar">{html.escape(u["username"][:1].upper())}</div>' if u["username"] else ""
  st.markdown(f'<div style="display:flex;align-items:center;gap:12px;margin-top:25px;padding:4px 0 2px">{avatar_html}<div class="account-info"><div class="eyebrow" style="margin-bottom:5px">ACTIVE ACCOUNT</div><b>{html.escape(u["username"])}</b><div class="account-role">{html.escape(u["role"])}</div></div></div>',unsafe_allow_html=True)
  if st.button('↪  Logout',use_container_width=True,key='logout'):
   st.session_state.token=None; st.session_state.user=None; st.session_state.result=None; st.rerun()

def show_result(r):
 risk=r.get('risk',{}); cls=r.get('classification',{}); d=r.get('decision',{}); score=float(r.get('risk_score',risk.get('score',0)) or 0); action=d.get('label','Allow'); level=r.get('risk_level',d.get('risk_level','Safe'))
 st.markdown(f'<div class="result"><div class="eyebrow">LIVE MODERATION RESULT</div><div class="score">{score:.1f}</div><div class="meta">/ 100 canonical risk score</div><div class="level">{html.escape(action)}</div><div class="meta">Risk level: <b style="color:#fff">{html.escape(level)}</b> · Language: <b style="color:#fff">{html.escape(r.get("language","Unknown"))}</b></div></div>',unsafe_allow_html=True)
 if action=='Allow': msg='ALLOW — the comment is safe and is posted normally.'
 elif action=='Human Review': msg='HUMAN REVIEW — the automatic system is uncertain and sends the item to an administrator.'
 else: msg=f'{action.upper()} — the comment is not published normally.'
 st.markdown(f'<div class="action">{html.escape(msg)}</div>',unsafe_allow_html=True)
 labels=[('TOXIC','toxic'),('SEVERE TOXIC','severe_toxic'),('OBSCENE','obscene'),('THREAT','threat'),('INSULT','insult'),('IDENTITY HATE','identity_hate')]
 st.markdown('<div class="signals">'+''.join(f'<div class="sig"><b>{a}</b><span>{float(cls.get(b,0) or 0):.1f}%</span></div>' for a,b in labels)+'</div>',unsafe_allow_html=True)
 if st.button('EXPLAINABLE AI',use_container_width=True,key='xai_toggle'): st.session_state.show_xai=not st.session_state.show_xai; st.rerun()
 if st.session_state.show_xai:
  x=r.get('xai',{}); b=r.get('behavioural_analysis',{}); h=r.get('harassment_escalation',{}); c=r.get('confidence_uncertainty',{})
  st.markdown(f'<div class="xai"><div class="eyebrow">EXPLAINABLE AI</div><div class="xai-title">WHY AURA MADE THIS DECISION.</div><div class="xai-row"><b>Decision explanation</b><br>{html.escape(str(x.get("reason","No explanation returned.")))}</div><div class="xai-row"><b>Important evidence</b><br>{html.escape(str(x.get("important_evidence","No harmful evidence detected.")))}</div><div class="xai-row"><b>Behavioural risk: {float(b.get("behavioural_risk",0) or 0):.1f}/100</div><div class="xai-row"><b>Harassment & escalation</b><br>Harassment: {float(h.get("harassment_risk",0) or 0):.1f}% · Escalation: {float(h.get("escalation_risk",0) or 0):.1f}%</div><div class="xai-row"><b>Confidence / uncertainty</b><br>Confidence: {float(c.get("confidence",0) or 0):.1f}% · Uncertainty: {float(c.get("uncertainty",0) or 0):.1f}%</div><div class="xai-row"><b>Summary</b><br>{html.escape(str(x.get("summary","AURA combined available evidence.")))}</div></div>',unsafe_allow_html=True)

def safety_page():
 st.markdown('<div class="eyebrow">AURA AI SAFETY</div><div class="display">UNDERSTAND WORDS.<br>PROTECT CONVERSATIONS.</div><div class="subtle" style="max-width:820px;margin-top:12px">Analyze multilingual or code-mixed comments using safety classification, context, behaviour, harassment, risk and explainable decision logic.</div><div style="height:20px"></div>',unsafe_allow_html=True)
 left,right=st.columns([1.04,.96],gap='large')
 with left:
  st.markdown('<div class="eyebrow">COMMENT INPUT</div>',unsafe_allow_html=True); text=st.text_area('Comment',height=170,placeholder='Write a comment…',label_visibility='collapsed',key='comment_text'); context=""
  if st.button('RUN AI SAFETY CHECK',use_container_width=True,key='run'):
   if not text.strip(): st.warning('Please enter a comment first.')
   else:
    with st.spinner('Analyzing language, safety signals, context and risk…'):
     out=api('/predict','POST',{'text':text.strip(),'context':context,'source':'text'})
     if not out: out=api('/moderate','POST',{'text':text.strip(),'context':context})
    if out:
     st.session_state.result=out
     # Keep the current user's moderation history available even when an
     # older backend build does not expose its history GET route.
     item={
      'message':text.strip(),
      'created_at':out.get('created_at',''),
      'result':out
     }
     st.session_state.activity=[item]+[
      x for x in st.session_state.get('activity',[])
      if not (x.get('message')==item['message'] and x.get('created_at')==item['created_at'])
     ]
     st.session_state.show_xai=False
     st.rerun()
  if st.session_state.result:
   show_result(st.session_state.result)
   predict_extras(st.session_state.result, st.session_state.result.get('text') or text or '', key_prefix='text')
  st.markdown('<div class="eyebrow" style="margin-top:30px">PUBLIC COMMENT PREVIEW</div>',unsafe_allow_html=True); rows=api('/history') or []
  if not rows: rows=st.session_state.get('activity',[])
  posted=[x for x in rows if x.get('result',{}).get('publication',{}).get('posted')]
  if not posted: st.markdown('<div class="surface">Approved comments will appear here after a safe comment is posted.</div>',unsafe_allow_html=True)
  else:
   for x in posted[:8]: st.markdown(f'<div class="surface" style="margin:9px 0"><b>{html.escape(x.get("message",""))}</b><div class="subtle">Posted · {html.escape(str(x.get("created_at","")))}</div></div>',unsafe_allow_html=True)
 with right:
  st.markdown('<div class="dark-panel"><div class="eyebrow">AURA DECISION FLOW</div><h2>One message. One safe path.</h2><div class="flow-step"><b>01</b> Text and language analysis</div><div class="flow-step"><b>02</b> Six-label safety classification</div><div class="flow-step"><b>03</b> Context, behaviour and harassment</div><div class="flow-step"><b>04</b> Canonical risk calculation</div><div class="flow-step"><b>05</b> Allow / Warn / Quarantine / Restrict / Temporary Block</div><div class="flow-step"><b>06</b> Uncertain content → Human Review</div><div class="flow-step"><b>07</b> Admin decision → publish or keep blocked</div></div>',unsafe_allow_html=True)

def history_page():
 st.markdown('<div class="eyebrow">USER ACTIVITY</div><div class="display-medium">MY ACTIVITY.</div>',unsafe_allow_html=True)
 st.markdown('<div class="eyebrow" style="margin-top:8px">FILTERS</div>',unsafe_allow_html=True)
 fc1,fc2,fc3=st.columns([2,1,1])
 with fc1: q=st.text_input('Search',placeholder='Search comments…',key='hist_q')
 with fc2: label_f=st.selectbox('Label',['All','toxic','non_toxic'],key='hist_label')
 with fc3: cat_f=st.selectbox('Category',['All','toxic','severe_toxic','obscene','threat','insult','identity_hate','non_toxic'],key='hist_cat')
 fc4,fc5,fc6,fc7=st.columns([1,1,1,1])
 with fc4: source_f=st.selectbox('Source',['All','text','batch','voice','live'],key='hist_source')
 with fc5: from_f=st.date_input('From',value=None,key='hist_from')
 with fc6: to_f=st.date_input('To',value=None,key='hist_to')
 with fc7: lang_f=st.selectbox('Language',LANG_FILTER_OPTS,key='hist_lang')
 if 'hist_conf' not in st.session_state: st.session_state['hist_conf']=(0.0,1.0)
 conf_f=st.slider('Confidence range',0.0,1.0,step=0.01,key='hist_conf')
 try: min_c,max_c=float(conf_f[0]),float(conf_f[1])
 except Exception: min_c,max_c=0.0,1.0
 params={
  'q':str(q or '').strip(),
  'label':'' if label_f=='All' else label_f,
  'category':'' if cat_f=='All' else cat_f,
  'source':'' if source_f=='All' else source_f,
  'language':'' if lang_f=='All' else lang_f,
  'from_date':from_f.isoformat() if from_f else '',
  'to_date':to_f.isoformat() if to_f else '',
  'min_conf':'' if min_c<=0.0 else f'{min_c:.2f}',
  'max_conf':'' if max_c>=1.0 else f'{max_c:.2f}',
 }
 filters_on=any(v for v in params.values())
 if filters_on:
  rows=api(build_path('/history',params))
  if isinstance(rows,dict):
   rows=next((rows[k] for k in ('items','results','data','history') if isinstance(rows.get(k),list)),[])
  if not isinstance(rows,list): rows=[]
 else:
  rows=api('/history') or []
  if not isinstance(rows,list): rows=[]
  if not rows: rows=st.session_state.get('activity',[])
 if not rows:
  st.markdown('<div class="surface" style="margin-top:16px">'+('No activity matches these filters.' if filters_on else 'No moderation activity yet.')+'</div>',unsafe_allow_html=True)
  return
 for x in rows:
  if not isinstance(x,dict): continue
  r=x.get('result',{}) if isinstance(x.get('result'),dict) else {}
  d=r.get('decision',{}) if isinstance(r.get('decision'),dict) else {}
  created=str(x.get('created_at',''))
  try:
   dt=datetime.fromisoformat(created.replace('Z','+00:00'))
   created=dt.astimezone().strftime('%d %b %Y · %I:%M %p')
  except Exception:
   pass
  label=str(d.get('label') or x.get('overall_label') or 'Unknown')
  status=str(r.get('publication',{}).get('status','UNKNOWN')) if isinstance(r.get('publication'),dict) else 'UNKNOWN'
  status_html='POSTED' if status=='POSTED' else 'FLAGGED · NOT POSTED'
  status_class='posted-status' if status=='POSTED' else 'flagged-status'
  extra=''
  if x.get('confidence') is not None: extra+=f'<span class="badge">CONFIDENCE {confidence_pct(x):.0f}%</span>'
  if x.get('source'): extra+=f'<span class="badge">{html.escape(str(x.get("source")))}</span>'
  # Language + processing badges. Older rows have neither key -> nothing shown.
  li=lang_info(x)
  if not any(li.values()): li=lang_info(r)
  if li['name'] or li['code']:
   lname=li['name'] or li['code']
   extra+=f'<span class="badge">{lang_flag(li["code"])} {html.escape(lname)} · {html.escape(li["code"] or "unknown")}</span>'
  if li['mode']:
   extra+=f'<span class="badge">{html.escape(mode_text(li["mode"], li["name"]) or li["mode"])}</span>'
  st.markdown(
   f'<div class="history"><b>{html.escape(x.get("message",""))}</b>'
   f'<div class="subtle">{html.escape(created)}</div>'
   f'<span class="badge">{html.escape(label)}</span>'
   f'<span class="badge {status_class}">{status_html}</span>{extra}</div>',
   unsafe_allow_html=True
  )

def admin_dashboard():
 st.markdown('<div class="eyebrow">MODERATION CENTER</div><div class="display-medium">ADMIN DASHBOARD.</div>',unsafe_allow_html=True)
 rows=api('/admin/comments') or []; users=api('/admin/users') or []; review=api('/admin/human-review') or []
 vals=[('COMMENTS',len(rows)),('POSTED',sum(bool(x.get('result',{}).get('publication',{}).get('posted')) for x in rows)),('FLAGGED',sum(bool(x.get('result',{}).get('publication',{}).get('flagged')) for x in rows)),('PENDING REVIEW',len(review)),('USERS',len(users))]
 cs=st.columns(5)
 for col,(a,b) in zip(cs,vals): col.markdown(f'<div class="metric"><div class="metric-label">{a}</div><div class="metric-value">{b}</div></div>',unsafe_allow_html=True)
 st.markdown('<div style="height:20px"></div>',unsafe_allow_html=True)
 active=[u for u in users if u.get('role')=='user' and not u.get('blocked')]
 st.markdown('<div class="eyebrow">ADMIN CONTROL</div><div class="surface"><b>BLOCK USER</b><div class="subtle">Block an active user directly from the admin dashboard.</div></div>',unsafe_allow_html=True)
 if active:
  for idx,user in enumerate(active):
   bc1,bc2=st.columns([5,1],gap='medium')
   with bc1:
    st.markdown(
     f'<div class="surface user-row"><b>{html.escape(user.get("username",""))}</b>'
     f'<div class="subtle">{html.escape(user.get("role","USER").upper())} · ACTIVE ACCOUNT</div></div>',
     unsafe_allow_html=True
    )
   with bc2:
    if st.button('BLOCK',use_container_width=True,key=f'block_user_{idx}'):
     if api('/admin/block-user','POST',{'username':user.get('username')}):
      st.success(f'User {user.get("username")} blocked successfully.')
      st.rerun()
 else:
  st.markdown('<div class="surface">There are no active user accounts available to block.</div>',unsafe_allow_html=True)

def admin_review():
 st.markdown('<div class="eyebrow">MODERATION CENTER</div><div class="display-medium">HUMAN REVIEW.</div>',unsafe_allow_html=True)
 admin_review_queue()
 admin_feedback_review()

def admin_review_queue():
 events=api('/admin/human-review') or []
 if not events: st.markdown('<div class="surface">Human review queue is clear.</div>',unsafe_allow_html=True); return
 for e in events:
  r=e.get('result',{}); d=r.get('decision',{}); st.markdown(f'<div class="history"><b>{html.escape(e.get("message",""))}</b><div class="subtle">{html.escape(str(e.get("created_at","")))}</div><span class="badge">{html.escape(str(d.get("label","Human Review")))}</span><span class="badge">REVIEW REQUIRED</span></div>',unsafe_allow_html=True)
  mid=e.get('moderation_id')
  if not mid:
   st.markdown('<div class="subtle">No moderation id was returned for this item, so review actions are unavailable.</div>',unsafe_allow_html=True)
   continue
  a,b,c=st.columns(3)
  if a.button('APPROVE & POST',key=f'a{mid}',use_container_width=True):
   if api(f'/admin/human-review/{mid}','POST',{'decision':'APPROVE','note':'Approved by admin.'}): st.rerun()
  if b.button('REJECT',key=f'r{mid}',use_container_width=True):
   if api(f'/admin/human-review/{mid}','POST',{'decision':'REJECT','note':'Rejected by admin.'}): st.rerun()
  if c.button('RESTRICT',key=f'x{mid}',use_container_width=True):
   if api(f'/admin/human-review/{mid}','POST',{'decision':'RESTRICT','note':'Restricted by admin.'}): st.rerun()

def admin_feedback_review():
 st.markdown('<div class="eyebrow" style="margin-top:36px">FEEDBACK REVIEW</div><div class="subtle" style="max-width:840px">Verify what users reported about a prediction and push corrected samples straight into the training dataset.</div>',unsafe_allow_html=True)
 fb=api('/feedback')
 if isinstance(fb,dict): items=fb.get('items') or []
 elif isinstance(fb,list): items=fb
 else: items=[]
 if not items:
  st.markdown('<div class="surface">No feedback has been submitted yet.</div>',unsafe_allow_html=True)
  return
 for it in items:
  if not isinstance(it,dict): continue
  mid=it.get('moderation_id') or it.get('prediction_id') or it.get('id')
  message=str(it.get('input') or it.get('comment') or it.get('text') or it.get('message') or '—')
  pred=str(it.get('predicted_label') or it.get('prediction') or it.get('label') or '—')
  conf=it.get('confidence')
  corrected=it.get('corrected_label')
  correct=it.get('correct')
  if isinstance(correct,bool): verdict='CORRECT' if correct else 'INCORRECT'
  elif correct is None or str(correct).strip()=='': verdict='NOT RATED'
  else: verdict='CORRECT' if str(correct).strip().lower() in ('1','true','yes') else 'INCORRECT'
  created=str(it.get('created_at') or '')
  conf_txt=f'{confidence_pct(it):.1f}%' if conf is not None else '—'
  st.markdown(
   f'<div class="history"><b>{html.escape(message)}</b>'
   f'<div class="subtle">Prediction: <b>{html.escape(pred)}</b> · Confidence: {conf_txt} · Feedback: <b>{verdict}</b> · {html.escape(created)}</div>'
   + (f'<span class="badge">CORRECTED: {html.escape(str(corrected).upper())}</span>' if corrected else '')
   + f'<span class="badge">{verdict}</span></div>',
   unsafe_allow_html=True
  )
  if st.session_state.get(f'fb_verified_{mid}'):
   st.success('Verified and added to the dataset.')
   continue
  if not mid:
   st.markdown('<div class="subtle">No id was returned for this feedback item, so verification is unavailable.</div>',unsafe_allow_html=True)
   continue
  if corrected:
   cl=str(corrected)
   st.markdown(f'<div class="subtle">Corrected label: <b>{html.escape(cl)}</b></div>',unsafe_allow_html=True)
  else:
   default_idx=LABEL_OPTIONS.index(pred) if pred in LABEL_OPTIONS else 0
   cl=st.selectbox('Corrected label',LABEL_OPTIONS,index=default_idx,key=f'fb_cl_{mid}')
  if st.button('VERIFY & ADD TO DATASET',key=f'fb_verify_{mid}',use_container_width=True):
   out=api(f'/admin/verify/{mid}','POST',{'verified':True,'add_to_dataset':True,'corrected_label':cl})
   if out is None: st.error('Verification failed. Please try again.')
   else:
    st.session_state[f'fb_verified_{mid}']=True
    st.success('Verified and added to the dataset.')
    st.rerun()

def admin_comments():
 st.markdown('<div class="eyebrow">ADMIN · ALL COMMENTS</div><div class="display-medium">EVERY COMMENT.</div>',unsafe_allow_html=True); rows=api('/admin/comments') or []
 if not rows: st.markdown('<div class="surface">No comments have been analyzed.</div>',unsafe_allow_html=True); return
 for x in rows:
  r=x.get('result',{}); d=r.get('decision',{}); p=r.get('publication',{}); status='POSTED' if p.get('posted') else ('HUMAN REVIEW' if p.get('needs_human') else 'NOT POSTED')
  st.markdown(f'<div class="history"><b>{html.escape(x.get("message",""))}</b><div class="subtle">{html.escape(str(x.get("created_at","")))}</div><span class="badge">{html.escape(str(d.get("label","Unknown")))}</span><span class="badge">{status}</span></div>',unsafe_allow_html=True)

def admin_users():
 st.markdown('<div class="eyebrow">BEHAVIOURAL SAFETY</div><div class="display-medium">USER RISK PROFILES.</div>',unsafe_allow_html=True); users=api('/admin/users') or []; rows=api('/admin/comments') or []; p={u['username']:{'username':u['username'],'role':u['role'],'comments':0,'posted':0,'flagged':0,'threats':0,'insults':0,'blocked':bool(u['blocked'])} for u in users}
 for x in rows:
  name=x['user_id']; p.setdefault(name,{'username':name,'role':'user','comments':0,'posted':0,'flagged':0,'threats':0,'insults':0,'blocked':False}); q=p[name]; q['comments']+=1; r=x.get('result',{}); q['posted']+=int(bool(r.get('publication',{}).get('posted'))); q['flagged']+=int(bool(r.get('publication',{}).get('flagged'))); q['threats']+=int(float(r.get('classification',{}).get('threat',0) or 0)>0); q['insults']+=int(float(r.get('classification',{}).get('insult',0) or 0)>0)
 table='<table class="admin-table"><tr><th>User</th><th>Role</th><th>Comments</th><th>Posted</th><th>Flagged</th><th>Threats</th><th>Insults</th><th>Status</th></tr>'
 for q in p.values(): table+=f'<tr><td>{html.escape(q["username"])}</td><td>{q["role"]}</td><td>{q["comments"]}</td><td>{q["posted"]}</td><td>{q["flagged"]}</td><td>{q["threats"]}</td><td>{q["insults"]}</td><td>{"BLOCKED" if q["blocked"] else "ACTIVE"}</td></tr>'
 st.markdown(table+'</table>',unsafe_allow_html=True)

def batch_page():
 st.markdown('<div class="eyebrow">AURA BATCH DETECTION</div><div class="display-medium">BATCH DETECTION.</div><div class="subtle" style="max-width:860px;margin-top:10px">Upload a CSV with a comment, text or comments column. AURA analyzes up to 500 rows in one run and every row is stored with <b>source=batch</b>.</div><div style="height:16px"></div>',unsafe_allow_html=True)
 up=st.file_uploader('Upload CSV',type=['csv'],key='batch_file')
 if up is None:
  st.markdown('<div class="surface">No file selected yet. Upload a .csv file to begin.</div>',unsafe_allow_html=True)
  return
 try:
  df=pd.read_csv(io.BytesIO(up.getvalue()))
 except Exception as e:
  st.error(f'Could not parse the CSV file: {e}')
  return
 if df is None or df.empty or len(df.columns)==0:
  st.error('The CSV file has no rows to analyze.')
  return
 names=[str(c) for c in df.columns]
 lowered={str(c).strip().lower():c for c in df.columns}
 col=None
 for cand in ('comment','text','comments'):
  if cand in lowered:
   col=lowered[cand]; break
 if col is None:
  st.error('No comment column found. Expected a column named comment, text or comments. Columns found: '+', '.join(names))
  return
 def _clean(v):
  s=str(v).strip()
  if not s or s.lower() in ('nan','none','null','<na>','nat'): return ''
  return s
 cleaned=[_clean(v) for v in df[col].tolist()]
 valid=[v for v in cleaned if v]
 skipped=len(cleaned)-len(valid)
 truncated=False
 if len(valid)>500:
  valid=valid[:500]; truncated=True
 if skipped: st.warning(f'{skipped} empty or invalid row(s) were skipped.')
 if truncated: st.warning('The file was truncated to the first 500 rows (batch limit).')
 st.info(f'{len(valid)} valid comment(s) ready for analysis.')
 if not valid:
  st.error('No valid comments to analyze in this file.')
  return
 if st.button('RUN BATCH ANALYSIS',use_container_width=True,key='run_batch'):
  with st.spinner('Analyzing batch comments...'):
   out=api('/predict/batch','POST',{'comments':valid})
  if isinstance(out,dict) and isinstance(out.get('results'),list):
   st.session_state['batch_results']=out['results']
   st.success(f"Batch analysis complete: {out.get('count', len(out['results']))} comment(s) processed.")
  elif out is None:
   st.error('Batch analysis failed. Check the backend and try again.')
  else:
   st.error('Batch analysis returned an unexpected response.')
 res=st.session_state.get('batch_results')
 if not isinstance(res,list) or not res: return
 rows=[]
 for it in res:
  if not isinstance(it,dict): continue
  cats=it.get('categories') if isinstance(it.get('categories'),dict) else {}
  li=lang_info(it)
  row={
   'text':str(it.get('text') or it.get('comment') or it.get('comments') or ''),
   'language':li['code'],
   'language_name':li['name'],
   'overall_label':str(it.get('overall_label') or ''),
   'confidence':round(confidence_pct(it),1),
   'processing_mode':li['mode'],
  }
  for _,k in CAT_ROWS: row[k]=round(pct_of(cats.get(k))/100.0,4)
  row['timestamp']=str(it.get('created_at') or '')
  rows.append(row)
 if not rows:
  st.markdown('<div class="surface">No batch results were returned.</div>',unsafe_allow_html=True)
  return
 st.markdown('<div class="eyebrow" style="margin-top:22px">BATCH RESULTS</div>',unsafe_allow_html=True)
 # Per-row language badge table (first 50 rows); the dataframe below and the
 # CSV carry every row with the same columns.
 badge_table='<table class="admin-table"><tr><th>#</th><th>Comment</th><th>Language</th><th>Label</th><th>Confidence</th><th>Processing</th></tr>'
 for n,rw in enumerate(rows[:50],1):
  lbadge=f'<span class="badge">{lang_flag(rw["language"])} {html.escape(rw["language_name"] or rw["language"] or "Unknown")}</span>'
  if rw['language']: lbadge+=f'<span class="badge">{html.escape(rw["language"])}</span>'
  mtxt=mode_text(rw['processing_mode'], rw['language_name'])
  badge_table+=(f'<tr><td>{n}</td><td>{html.escape(str(rw["text"])[:70])}</td><td>{lbadge}</td>'
   f'<td>{html.escape(rw["overall_label"] or "—")}</td><td>{rw["confidence"]}%</td>'
   f'<td>{html.escape(mtxt or rw["processing_mode"] or "—")}</td></tr>')
 badge_table+='</table>'
 st.markdown('<div class="surface">'+badge_table+'</div>',unsafe_allow_html=True)
 if len(rows)>50:
  st.markdown('<div class="subtle" style="margin-top:8px">Showing the first 50 rows as badges — the full table and the CSV cover every row.</div>',unsafe_allow_html=True)
 st.dataframe(pd.DataFrame(rows),use_container_width=True)
 # CSV columns are fixed by the multilingual contract. The six category columns
 # are 0..1 probabilities (the same scale the API categories use, e.g. 0.85),
 # confidence stays a 0..100 percentage, timestamp is the prediction time.
 header=['text','language','language_name','overall_label','confidence','processing_mode','toxic','severe_toxic','obscene','threat','insult','identity_hate','timestamp']
 table_rows=[[rw['text'],rw['language'],rw['language_name'],rw['overall_label'],rw['confidence'],rw['processing_mode'],rw['toxic'],rw['severe_toxic'],rw['obscene'],rw['threat'],rw['insult'],rw['identity_hate'],rw['timestamp']] for rw in rows]
 st.download_button('DOWNLOAD RESULTS CSV',data=csv_text(header,table_rows),file_name='aura_batch_results.csv',mime='text/csv',use_container_width=True,key='batch_download')

def voice_page():
 st.markdown('<div class="eyebrow">AURA VOICE DETECTION</div><div class="display-medium">VOICE DETECTION.</div><div class="subtle" style="max-width:860px;margin-top:10px">Record a comment, review the transcript, then run the same AURA safety model. Voice predictions are stored with <b>source=voice</b> and appear in History.</div><div style="height:16px"></div>',unsafe_allow_html=True)
 VOICE_LANGS=[('Auto (default)',''),('English','en'),('Tamil','ta'),('Tanglish','ta-Latn'),('Hindi','hi'),('Telugu','te'),('Malayalam','ml'),('Kannada','kn'),('Bengali','bn'),('Marathi','mr'),('Gujarati','gu'),('Punjabi','pa'),('Urdu','ur')]
 voice_lang_labels=[l for l,_ in VOICE_LANGS]
 voice_lang_choice=st.selectbox('Language hint',voice_lang_labels,key='voice_lang',help='Optional recognition hint sent to /voice/transcribe. Auto leaves the language undetected by the browser engine.')
 voice_lang_code=dict(VOICE_LANGS).get(voice_lang_choice,'')
 audio=st.audio_input('Record your comment',key='voice_input')
 audio_bytes=None
 if audio is not None:
  try:
   if isinstance(audio,(bytes,bytearray)): audio_bytes=bytes(audio)
   elif hasattr(audio,'getvalue'): audio_bytes=audio.getvalue()
  except Exception:
   audio_bytes=None
 if audio_bytes:
  sig=f'{len(audio_bytes)}:{hash(audio_bytes)}:{voice_lang_code}'
  if st.session_state.get('voice_sig')!=sig:
   st.session_state['voice_sig']=sig
   with st.spinner('Transcribing audio...'):
    out=api_files('/voice/transcribe',{'file':('audio.wav',audio_bytes,'audio/wav')},data={'language':voice_lang_code} if voice_lang_code else None)
   if isinstance(out,dict) and out.get('ok'):
    st.session_state['voice_box']=str(out.get('transcript') or '')
    st.success('Transcript ready - edit it below if needed.')
   elif isinstance(out,dict):
    reason=out.get('error') or out.get('engine') or 'unknown engine error'
    st.warning(f'Automatic transcription failed: {reason}. Type or paste the transcript below so the feature still works.')
 if 'voice_box' not in st.session_state: st.session_state['voice_box']=''
 transcript=st.text_area('Transcript',key='voice_box',height=150,placeholder='The transcript appears here - you can also type it manually.')
 if st.button('ANALYZE TRANSCRIPT',use_container_width=True,key='voice_run'):
  if not str(transcript or '').strip(): st.warning('Please provide a transcript first.')
  else:
   with st.spinner('Analyzing transcript...'):
    out2=api('/voice/predict','POST',{'transcript':str(transcript).strip()})
   if isinstance(out2,dict) and out2:
    st.session_state['voice_result']=out2
    st.rerun()
   else:
    st.error('The transcript could not be analyzed. Please try again.')
 res=st.session_state.get('voice_result')
 if isinstance(res,dict) and res:
  show_result(res)
  predict_extras(res,res.get('text') or transcript or '',key_prefix='voice')
 st.markdown('<div class="subtle" style="margin-top:16px">Voice predictions are stored with <b>source=voice</b> and appear in History.</div>',unsafe_allow_html=True)

LIVE_HTML='''<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<style>
html,body{margin:0;padding:0;background:#080808;color:#fff;font-family:'DM Sans',Arial,Helvetica,sans-serif}
.wrap{display:flex;gap:12px;padding:10px}
.cam{flex:1 1 auto;position:relative;background:#111;border:1px solid #2a2a2a;border-radius:16px;overflow:hidden;min-height:270px}
#vid{display:block;width:100%;height:100%;min-height:270px;object-fit:cover;background:#000}
.camtag{position:absolute;left:10px;top:10px;background:rgba(255,23,68,.92);color:#fff;font-size:10px;font-weight:800;letter-spacing:.14em;padding:5px 9px;border-radius:6px}
.side{width:330px;flex:0 0 330px;display:flex;flex-direction:column;gap:9px}
.toprow{display:flex;justify-content:space-between;align-items:center}
.pill{font-size:11px;font-weight:800;letter-spacing:.14em;padding:6px 12px;border-radius:999px;background:#2b2b2b;color:#bbb}
.pill.on{background:#169447;color:#fff}
.clock{font-family:'Bebas Neue',Arial,sans-serif;font-size:26px}
.card{background:#101010;border:2px solid #169447;border-radius:14px;padding:12px 14px}
.card.toxic{border-color:#FF1744}
.big{font-family:'Bebas Neue',Arial,sans-serif;font-size:34px;line-height:1;color:#3ddc7f}
.card.toxic .big{color:#FF1744}
.meta{font-size:12px;color:#bbb;margin-top:6px}
.cap{background:#101010;border:1px solid #2a2a2a;border-radius:12px;padding:10px;min-height:66px;max-height:120px;overflow:auto;font-size:13px;color:#ddd}
.cap .lbl{display:block;font-size:10px;letter-spacing:.18em;color:#FF1744;font-weight:800;margin-bottom:5px}
.row2{display:flex;gap:8px}
input{flex:1 1 auto;min-width:0;background:#151515;border:1px solid #333;color:#fff;border-radius:9px;padding:9px 10px;font-size:13px}
select{flex:1 1 auto;min-width:0;background:#151515;border:1px solid #333;color:#fff;border-radius:9px;padding:9px 10px;font-size:12px;font-weight:800;letter-spacing:.06em}
button{border:0;border-radius:11px;padding:11px 12px;font-weight:800;font-size:12px;letter-spacing:.08em;cursor:pointer}
.start{background:#fff;color:#080808}
.stop{background:#FF1744;color:#fff}
.send{background:#FF1744;color:#fff;flex:0 0 78px}
.banner{display:none;background:#FF1744;color:#fff;font-weight:700;font-size:13px;padding:10px 12px;border-radius:10px;margin:10px 10px 0}
.timeline{margin:10px;padding:12px;background:#101010;border:1px solid #2a2a2a;border-radius:14px;max-height:165px;overflow:auto}
.timeline h4{margin:0 0 8px;font-size:11px;letter-spacing:.2em;color:#FF1744;font-family:'Bebas Neue',Arial,sans-serif}
.item{font-size:12px;color:#ddd;padding:5px 0;border-top:1px solid #232323}
.t{color:#888;display:inline-block;width:52px}
.err{font-size:12px;color:#FF1744;font-weight:700;min-height:15px}
.note{font-size:11px;color:#777}
</style>
</head>
<body>
<div class="banner" id="banner"></div>
<div class="wrap">
  <div class="cam"><video id="vid" autoplay muted playsinline></video><div class="camtag">LIVE CAMERA - STAYS IN YOUR BROWSER</div></div>
  <div class="side">
    <div class="toprow"><span class="pill" id="status">STOPPED</span><span class="clock" id="clock">00:00</span></div>
    <div class="card" id="card"><div class="big" id="resLabel">-</div><div class="meta" id="resMeta">Press START LIVE DETECTION to begin.</div><div class="meta" id="resLang">Language: -</div></div>
    <div class="cap"><span class="lbl">LIVE TRANSCRIPT</span><span id="transcript">...</span></div>
    <div class="row2"><input id="manual" placeholder="Type a text chunk..."/><button class="send" id="sendBtn">SEND</button></div>
    <div class="row2"><select id="langSel" title="Speech recognition language"><option value="">Auto (default)</option><option value="en-IN">English (en-IN)</option><option value="ta-IN">Tamil (ta-IN)</option><option value="hi-IN">Hindi (hi-IN)</option><option value="te-IN">Telugu (te-IN)</option><option value="ml-IN">Malayalam (ml-IN)</option><option value="kn-IN">Kannada (kn-IN)</option><option value="bn-IN">Bengali (bn-IN)</option><option value="mr-IN">Marathi (mr-IN)</option><option value="gu-IN">Gujarati (gu-IN)</option><option value="pa-IN">Punjabi (pa-IN)</option></select></div>
    <div class="row2"><button class="start" id="startBtn" style="flex:1">START LIVE DETECTION</button><button class="stop" id="stopBtn" style="flex:1">STOP LIVE DETECTION</button></div>
    <div class="err" id="err"></div>
    <div class="note">Audio and video never leave this page - only recognized text chunks are sent to AURA.</div>
  </div>
</div>
<div class="timeline"><h4>TIMELINE</h4><div id="tl"><div class="item">No events yet.</div></div></div>
<script>
var BACKEND=__AURA_BACKEND__;
var TOKEN=__AURA_TOKEN__;
var sessionId=null,listening=false,startedAt=0,recog=null,stream=null,clockTimer=null,pushTimer=null;
var interim='',pending='',DEFAULT_LANG='';
function $(id){return document.getElementById(id);}
function banner(msg){var b=$('banner');b.textContent=msg;b.style.display='block';}
function clearBanner(){$('banner').style.display='none';}
function err(msg){$('err').textContent=msg||'';}
function mmss(s){var m=Math.floor(s/60),x=Math.floor(s-60*m);return (m<10?'0':'')+m+':'+(x<10?'0':'')+x;}
function elapsed(){return startedAt?((Date.now()-startedAt)/1000):0;}
function headers(){return {'Content-Type':'application/json','Authorization':'Bearer '+TOKEN};}
function setStatus(on){var s=$('status');if(on){s.className='pill on';s.textContent='LISTENING';}else{s.className='pill';s.textContent='STOPPED';}}
function pc(v){v=Number(v);if(!isFinite(v)){v=0;}return v>1.5?v:v*100;}
function modeTxt(mode,name){
  mode=String(mode||'');
  if(mode==='pretrained_model'){return 'Pretrained model (multilingual-toxicity-small)';}
  if(mode==='existing_model'){return 'Existing Model';}
  if(mode==='language_lexicon'){return (name||'Language')+' Lexicon';}
  if(mode==='fallback'){return 'Fallback · Limited';}
  return '';
}
function langCode(d){return String((d&&d.language)||'');}
function langName(d){
  var n=String((d&&d.language_name)||'');
  var c=langCode(d);
  if(!n&&c){n=c;}
  if(!n&&String((d&&d.script)||'')){n='Unknown';}
  return n;
}
function setLangRow(d){
  var row=$('resLang');
  if(!row){return;}
  if(!d){row.textContent='Language: -';return;}
  var name=langName(d),code=langCode(d),script=String((d&&d.script)||''),mode=String((d&&d.processing_mode)||'');
  if(!name&&!code&&!script&&!mode){row.textContent='Language: -';return;}
  var mt=modeTxt(mode,name);
  row.textContent='Language: '+(name||code||'Unknown')+(script?(' ('+script+')'):'')+(mt?(' · '+mt):'');
}
function topCat(cats){var best='',bv=-1;if(!cats){cats={};}for(var k in cats){if(k==='non_toxic'){continue;}var v=pc(cats[k]);if(v>bv){bv=v;best=k;}}return {name:String(best).replace(/_/g,' ').toUpperCase(),val:bv};}
function showResult(label,conf,cats,info){
  var l=String(label||'').toLowerCase();
  var toxic=(l.indexOf('toxic')>=0&&l.indexOf('non')<0)||l==='blocked'||l==='quarantine';
  var card=$('card');
  if(toxic){card.className='card toxic';}else{card.className='card';}
  $('resLabel').textContent=toxic?'TOXIC':'SAFE';
  var t=topCat(cats);
  $('resMeta').textContent='Confidence: '+Math.round(pc(conf))+'%'+(t.name?(' - '+t.name+' '+Math.round(t.val)+'%'):'')+' - '+(label||'');
  setLangRow(info||null);
}
function pushLine(txt){
  var tl=$('tl');
  var first=tl.querySelector('.item');
  if(first&&first.textContent.indexOf('No events yet.')===0){tl.innerHTML='';}
  var d=document.createElement('div');d.className='item';d.innerHTML=txt;tl.insertBefore(d,tl.firstChild);
}
function sendChunk(text){
  text=String(text||'').trim();
  if(!text){return;}
  if(!sessionId){ensureSession(function(){sendChunk(text);});return;}
  fetch(BACKEND+'/live/chunk',{method:'POST',headers:headers(),body:JSON.stringify({session_id:sessionId,transcript:text,elapsed_s:elapsed()})})
   .then(function(r){return r.json().catch(function(){return {};});})
   .then(function(d){
     if(!d){return;}
     if(d.error){err(String(d.error));return;}
     if(!d.label){return;}
     err('');
     showResult(d.label,d.confidence,d.categories,d);
     var t=topCat(d.categories);
     var name=t.name||String(d.label).toUpperCase();
     var emoji=(String(d.label).toLowerCase().indexOf('toxic')>=0)?'&#128308;':'&#128994;';
     var lcode=langCode(d);
     pushLine('<span class="t">'+mmss(elapsed())+'</span> '+emoji+' '+name+' '+Math.round(t.val)+'%'+(lcode?(' · '+lcode):''));
   })
   .catch(function(e){err('Could not reach the AURA backend: '+e);});
}
function pushPending(){
  var text=(pending+' '+interim).trim();
  pending='';interim='';
  if(text){sendChunk(text);}
}
function ensureSession(cb){
  if(sessionId){if(cb){cb();}return;}
  fetch(BACKEND+'/live/start',{method:'POST',headers:headers(),body:'{}'})
   .then(function(r){return r.json().catch(function(){return {};});})
   .then(function(d){
     sessionId=(d&&(d.session_id||d.sessionId))||null;
     if(sessionId){if(!startedAt){startedAt=Date.now();}if(cb){cb();}}
     else{banner('The AURA backend did not return a live session id.');}
   })
   .catch(function(e){banner('Could not start a live session: '+e+' - check that the backend runs on port 8000 and allows browser requests (CORS).');});
}
function applyRecogLang(){
  if(!recog){return;}
  var sel=$('langSel');
  var v=sel?String(sel.value||''):'';
  if(!v){v=DEFAULT_LANG||'';}
  if(!v){return;}
  try{recog.lang=v;}catch(e){}
}
function startRecog(){
  var SR=window.SpeechRecognition||window.webkitSpeechRecognition;
  if(!SR){banner('Speech recognition is not available in this browser. Use the manual text box - live analysis still works.');return;}
  try{recog=new SR();}catch(e){banner('Speech recognition could not start: '+e);return;}
  recog.continuous=true;recog.interimResults=true;
  if(!DEFAULT_LANG){try{DEFAULT_LANG=recog.lang||'';}catch(e){DEFAULT_LANG='';}}
  applyRecogLang();
  recog.onresult=function(ev){
    var inter='';
    for(var i=ev.resultIndex;i<ev.results.length;i++){
      var res=ev.results[i];
      if(res.isFinal){pending+=res[0].transcript+' ';}else{inter+=res[0].transcript;}
    }
    interim=inter;
    var shown=(pending+' '+interim).trim();
    $('transcript').textContent=shown||'...';
    if(pending.trim()){var p=pending;pending='';sendChunk(p);}
  };
  recog.onerror=function(ev){
    if(ev.error==='not-allowed'||ev.error==='service-not-allowed'){banner('Microphone permission was denied. Live transcription is off - use the manual text box below.');}
    else if(ev.error!=='no-speech'&&ev.error!=='aborted'){err('Speech recognition error: '+ev.error);}
  };
  recog.onend=function(){if(listening){try{recog.start();}catch(e){}}};
  try{recog.start();}catch(e){err('Speech recognition could not start: '+e);}
}
function startLocal(){
  listening=true;startedAt=Date.now();pending='';interim='';
  clearBanner();err('');setStatus(true);
  $('clock').textContent='00:00';
  clockTimer=setInterval(function(){$('clock').textContent=mmss(elapsed());},500);
  pushTimer=setInterval(pushPending,4000);
  if(navigator.mediaDevices&&navigator.mediaDevices.getUserMedia){
    navigator.mediaDevices.getUserMedia({video:true,audio:true}).then(function(s){
      stream=s;$('vid').srcObject=s;
    }).catch(function(e){
      banner('Camera/microphone unavailable ('+(e&&e.name?e.name:'error')+'). Live video is off - transcript analysis still works.');
    });
  }else{
    banner('This browser does not expose getUserMedia, so live video is unavailable. Text chunks still work.');
  }
  startRecog();
}
function stopLocal(){
  listening=false;
  if(clockTimer){clearInterval(clockTimer);clockTimer=null;}
  if(pushTimer){clearInterval(pushTimer);pushTimer=null;}
  setStatus(false);
  if(recog){try{recog.stop();}catch(e){}recog=null;}
  if(stream){try{stream.getTracks().forEach(function(tr){tr.stop();});}catch(e){}stream=null;try{$('vid').srcObject=null;}catch(e){}}
}
function start(){
  if(listening){return;}
  stopLocal();
  ensureSession(function(){startLocal();});
}
function stop(){
  var wasSession=sessionId;
  stopLocal();
  if(!wasSession){return;}
  fetch(BACKEND+'/live/stop',{method:'POST',headers:headers(),body:JSON.stringify({session_id:wasSession})})
   .then(function(r){return r.json().catch(function(){return {};});})
   .then(function(d){pushLine('<span class="t">'+mmss(elapsed())+'</span> &#9209; SESSION STOPPED'+(d&&d.events!=null?(' - '+d.events+' events'):''));})
   .catch(function(e){err('Session could not be closed: '+e);});
}
$('startBtn').onclick=start;
$('stopBtn').onclick=stop;
$('sendBtn').onclick=function(){
  var v=$('manual').value;
  if(!String(v).trim()){err('Type a text chunk first.');return;}
  err('');$('manual').value='';
  sendChunk(v);
};
$('manual').addEventListener('keydown',function(e){if(e.key==='Enter'){$('sendBtn').onclick();}});
var langSelEl=$('langSel');
if(langSelEl){langSelEl.addEventListener('change',function(){applyRecogLang();});}
if(!(window.SpeechRecognition||window.webkitSpeechRecognition)){banner('Speech recognition is not available in this browser. Use the manual text box - live analysis still works.');}
</script>
</body>
</html>'''

def live_page():
 st.markdown('<div class="eyebrow">AURA LIVE GUARD</div><div class="display-medium">LIVE GUARD.</div><div class="subtle" style="max-width:900px;margin-top:10px">Real-time camera preview with continuous speech recognition. Audio and video never leave your browser - only recognized text chunks are sent to AURA, and every event is stored with <b>source=live</b>.</div><div style="height:14px"></div>',unsafe_allow_html=True)
 token=str(st.session_state.get('token') or '')
 frame=LIVE_HTML.replace('__AURA_BACKEND__',json.dumps(BACKEND_URL)).replace('__AURA_TOKEN__',json.dumps(token).replace('</','<\\/'))
 components.html(frame,height=700)
 st.markdown('<div class="eyebrow" style="margin-top:22px">LIVE SESSION HISTORY</div>',unsafe_allow_html=True)
 raw=api('/live/sessions')
 items=[]
 if isinstance(raw,dict): items=raw.get('items') or []
 elif isinstance(raw,list): items=raw
 if not isinstance(items,list): items=[]
 summary=[]
 for i in items:
  if not isinstance(i,dict): continue
  summary.append({'session_id':str(i.get('session_id') or ''),'started_at':str(i.get('started_at') or ''),'ended_at':str(i.get('ended_at') or ''),'status':str(i.get('status') or ''),'event_count':i.get('event_count',0)})
 if not summary:
  st.markdown('<div class="surface">No live sessions have been recorded yet. Start a session above, then come back here.</div>',unsafe_allow_html=True)
  return
 st.dataframe(pd.DataFrame(summary),use_container_width=True)
 ids=[s['session_id'] for s in summary if s['session_id']]
 if not ids:
  st.info('Sessions were returned without an id, so events cannot be loaded.')
  return
 sid=st.selectbox('Load session',ids,key='live_pick')
 det=api(f'/live/{sid}')
 events=[]
 if isinstance(det,dict): events=det.get('events') or []
 elif isinstance(det,list): events=det
 if not isinstance(events,list): events=[]
 if not events:
  st.info('This session has no events yet.')
  return
 rows=[]
 for e in events:
  if not isinstance(e,dict): continue
  cats=e.get('categories') if isinstance(e.get('categories'),dict) else {}
  rows.append({
   'session_id':str(sid),
   'time':str(e.get('created_at') or ''),
   'transcript':str(e.get('transcript') or ''),
   'label':str(e.get('label') or ''),
   'confidence':round(confidence_pct(e),1),
   'category':str(e.get('category') or top_category(cats) or ''),
  })
 if rows: st.dataframe(pd.DataFrame(rows),use_container_width=True)
 else: st.info('This session has no readable events.')

def analytics_page():
 st.markdown('<div class="eyebrow">AURA ANALYTICS</div><div class="display-medium">ANALYTICS.</div>',unsafe_allow_html=True)
 data=api('/analytics')
 if not isinstance(data,dict):
  st.markdown('<div class="surface">Analytics data is unavailable right now.</div>',unsafe_allow_html=True)
  return
 feedback=data.get('feedback') if isinstance(data.get('feedback'),dict) else {}
 acc=feedback.get('accuracy')
 acc_txt='—' if acc is None else f'{pct_of(acc):.1f}%'
 tp=data.get('toxic_pct'); ntp=data.get('non_toxic_pct')
 cards=[
  ('TOTAL ANALYZED',str(data.get('total') if data.get('total') is not None else 0)),
  ('TOXIC %','—' if tp is None else f'{pct_of(tp):.1f}%'),
  ('NON TOXIC %','—' if ntp is None else f'{pct_of(ntp):.1f}%'),
  ('FEEDBACK ACCURACY',acc_txt),
 ]
 cs=st.columns(4)
 for col,(a,b) in zip(cs,cards): col.markdown(f'<div class="metric"><div class="metric-label">{a}</div><div class="metric-value">{b}</div></div>',unsafe_allow_html=True)
 if isinstance(feedback,dict) and feedback:
  st.markdown(f'<div class="subtle" style="margin-top:8px">Feedback: {feedback.get("correct",0) if feedback.get("correct") is not None else 0} correct · {feedback.get("incorrect",0) if feedback.get("incorrect") is not None else 0} incorrect · {feedback.get("total",0) if feedback.get("total") is not None else 0} total</div>',unsafe_allow_html=True)
 st.markdown('<div style="height:16px"></div>',unsafe_allow_html=True)
 cat=data.get('category_distribution')
 if isinstance(cat,dict) and cat:
  st.markdown('<div class="eyebrow">CATEGORY DISTRIBUTION</div>',unsafe_allow_html=True)
  st.bar_chart(pd.Series({str(k):_num(v) for k,v in cat.items()}))
 else:
  st.info('Category distribution: no data yet.')
 lang_dist=data.get('language_distribution')
 if isinstance(lang_dist,dict) and lang_dist:
  st.markdown('<div class="eyebrow" style="margin-top:18px">LANGUAGE DISTRIBUTION</div>',unsafe_allow_html=True)
  st.bar_chart(pd.Series({LANG_NAMES.get(str(k),str(k)):_num(v) for k,v in lang_dist.items()}))
 else:
  st.info('Language distribution: no data yet.')
 daily=data.get('daily')
 if isinstance(daily,list) and daily:
  st.markdown('<div class="eyebrow" style="margin-top:18px">DAILY ACTIVITY</div>',unsafe_allow_html=True)
  try:
   ddf=pd.DataFrame(daily)
   if 'date' in ddf.columns and 'count' in ddf.columns: ddf=ddf.set_index('date')
   st.line_chart(ddf)
  except Exception:
   st.info('Daily activity: data could not be displayed.')
 else:
  st.info('Daily activity: no data yet.')
 src=data.get('source_distribution')
 if isinstance(src,dict) and src:
  st.markdown('<div class="eyebrow" style="margin-top:18px">SOURCE DISTRIBUTION</div>',unsafe_allow_html=True)
  st.bar_chart(pd.Series({str(k):_num(v) for k,v in src.items()}))
 else:
  st.info('Source distribution: no data yet.')
 dec=data.get('decisions')
 if isinstance(dec,dict) and dec:
  st.markdown('<div class="eyebrow" style="margin-top:18px">DECISIONS</div>',unsafe_allow_html=True)
  table='<table class="admin-table"><tr><th>Decision</th><th>Count</th></tr>'
  for k,v in dec.items(): table+=f'<tr><td>{html.escape(str(k))}</td><td>{html.escape(str(v))}</td></tr>'
  st.markdown(table+'</table>',unsafe_allow_html=True)
 else:
  st.info('Decision breakdown: no data yet.')

def dataset_page():
 st.markdown('<div class="eyebrow">ADMIN · TRAINING DATA</div><div class="display-medium">DATASET MGMT.</div>',unsafe_allow_html=True)
 flash=st.session_state.pop('ds_flash',None)
 if flash: st.success(flash)
 stats=api('/dataset/stats')
 stats_d=stats if isinstance(stats,dict) else {}
 rep_langs=[str(x) for x in stats_d.get('languages') if str(x or '').strip()] if isinstance(stats_d.get('languages'),list) else []
 rep_sources=[str(x) for x in stats_d.get('by_source') if str(x or '').strip()] if isinstance(stats_d.get('by_source'),dict) else []
 ds_lang_opts=['All']+(rep_langs or LANG_CODES)
 ds_source_opts=['All']+sorted(rep_sources or ['text','batch','voice','live','demo'])
 if isinstance(stats,dict):
  def cell(v): return '—' if v is None else html.escape(str(v))
  vals=[('TOTAL SAMPLES',cell(stats.get('total'))),('TOXIC',cell(stats.get('toxic'))),('NON TOXIC',cell(stats.get('non_toxic'))),('MISSING LABELS',cell(stats.get('missing_labels'))),('DUPLICATES',cell(stats.get('duplicates')))]
  cs=st.columns(5)
  for col,(a,b) in zip(cs,vals): col.markdown(f'<div class="metric"><div class="metric-label">{a}</div><div class="metric-value">{b}</div></div>',unsafe_allow_html=True)
  class_dist=stats.get('class_distribution')
  if not isinstance(class_dist,dict):
   cd=stats.get('category_counts')
   class_dist=dict(cd) if isinstance(cd,dict) else {}
   class_dist['non_toxic']=stats.get('non_toxic')
  if class_dist and any(_num(v)>0 for v in class_dist.values()):
   st.markdown('<div class="eyebrow" style="margin-top:18px">CLASS DISTRIBUTION</div>',unsafe_allow_html=True)
   st.bar_chart(pd.Series({str(k):_num(v) for k,v in class_dist.items()}))
  by_lang=stats.get('by_language')
  if isinstance(by_lang,dict) and (by_lang or rep_langs):
   lang_keys=[]
   for src_keys in (rep_langs,list(by_lang.keys()),LANG_CODES):
    for k in src_keys:
     k=str(k or '').strip()
     if k and k not in lang_keys: lang_keys.append(k)
   st.markdown('<div class="eyebrow" style="margin-top:18px">SAMPLES BY LANGUAGE</div>',unsafe_allow_html=True)
   st.bar_chart(pd.Series({k:_num(by_lang.get(k)) for k in lang_keys}))
  else:
   st.info('Samples by language: not available from this backend yet.')
  st.markdown('<div class="eyebrow" style="margin-top:18px">BY TOXICITY</div>',unsafe_allow_html=True)
  def _stat_txt(v): return '—' if v is None else html.escape(str(v))
  st.markdown(
   f'<div class="surface"><b>Toxic:</b> {_stat_txt(stats.get("toxic"))} · <b>Non toxic:</b> {_stat_txt(stats.get("non_toxic"))}'
   f' · <b>Missing labels:</b> {_stat_txt(stats.get("missing_labels"))} · <b>Duplicates:</b> {_stat_txt(stats.get("duplicates"))}</div>',
   unsafe_allow_html=True
  )
  by_split=stats.get('by_split')
  if isinstance(by_split,dict) and by_split:
   split_keys=[]
   for k in list(SPLIT_FILTER_OPTS[1:])+list(by_split.keys()):
    k=str(k or '').strip()
    if k and k not in split_keys: split_keys.append(k)
   st.markdown('<div class="eyebrow" style="margin-top:18px">BY SPLIT</div>',unsafe_allow_html=True)
   st.bar_chart(pd.Series({k:_num(by_split.get(k)) for k in split_keys}))
  else:
   st.info('Samples by split: not available from this backend yet.')
 else:
  st.info('Dataset statistics are unavailable right now.')
 st.markdown('<div class="eyebrow" style="margin-top:26px">FILTERS</div>',unsafe_allow_html=True)
 fb1,fb2,fb3,fb4=st.columns(4)
 with fb1: f_lang=st.selectbox('Language',_opts_with(ds_lang_opts,st.session_state.get('ds_lang')),key='ds_lang',help='Languages reported by GET /dataset/stats; falls back to the 12 supported codes.')
 with fb2: f_tox=st.selectbox('Toxicity',TOX_FILTER_OPTS,key='ds_tox')
 with fb3: f_src=st.selectbox('Source',_opts_with(ds_source_opts,st.session_state.get('ds_src')),key='ds_src')
 with fb4: f_split=st.selectbox('Split',SPLIT_FILTER_OPTS,key='ds_split')
 ds_filters={
  'language':'' if f_lang=='All' else f_lang,
  'label':'' if f_tox=='All' else f_tox,
  'source':'' if f_src=='All' else f_src,
  'split':'' if f_split=='All' else f_split,
 }
 if st.session_state.get('ds_filters')!=ds_filters:
  st.session_state['ds_filters']=ds_filters
  st.session_state['ds_offset']=0
 st.markdown('<div class="eyebrow" style="margin-top:26px">SAMPLES</div>',unsafe_allow_html=True)
 if 'ds_offset' not in st.session_state: st.session_state['ds_offset']=0
 limit=20
 with st.form('ds_search_form'):
  q=st.text_input('Search samples',key='ds_q',placeholder='Search comment text...')
  do_search=st.form_submit_button('SEARCH')
 if do_search: st.session_state['ds_offset']=0
 off=int(st.session_state.get('ds_offset') or 0)
 out=api(build_path('/dataset',{'limit':limit,'offset':off,'q':str(q or '').strip(),**ds_filters}))
 items=[]; total=0
 if isinstance(out,dict):
  items=out.get('items') or []; total=out.get('total')
 elif isinstance(out,list):
  items=out
 if not isinstance(items,list): items=[]
 try: total=int(total)
 except Exception: total=len(items)
 items=[i for i in items if isinstance(i,dict)]
 if not items:
  st.markdown('<div class="surface">No dataset samples matched this search.</div>',unsafe_allow_html=True)
 else:
  view=[]
  for i in items:
   src=str(i.get('source') or '')
   li=lang_info(i)
   view.append({'id':i.get('id'),'comment':str(i.get('comment') or '')[:90],'language':li['code'],'language_name':li['name'],'script':li['script'],'split':str(i.get('split') or ''),'toxic':i.get('toxic'),'severe_toxic':i.get('severe_toxic'),'obscene':i.get('obscene'),'threat':i.get('threat'),'insult':i.get('insult'),'identity_hate':i.get('identity_hate'),'source':src+(' · DEMO DATA' if src=='demo' else '')})
  st.dataframe(pd.DataFrame(view),use_container_width=True)
  pc1,pc2,pc3=st.columns([1,1,2])
  if pc1.button('← PREVIOUS',key='ds_prev',disabled=off<=0,use_container_width=True):
   st.session_state['ds_offset']=max(0,off-limit); st.rerun()
  if pc2.button('NEXT →',key='ds_next',disabled=off+limit>=total,use_container_width=True):
   st.session_state['ds_offset']=off+limit; st.rerun()
  pc3.markdown(f'<div class="subtle" style="margin-top:14px">Showing {off+1}–{off+len(view)} of {total}</div>',unsafe_allow_html=True)
 st.markdown('<div class="eyebrow" style="margin-top:26px">ADD SAMPLE</div>',unsafe_allow_html=True)
 with st.form('ds_add_form'):
  comment=st.text_area('Comment',key='ds_add_comment',height=110,placeholder='Sample comment text...')
  r1,r2,r3=st.columns(3)
  labels={}
  with r1:
   labels['toxic']=st.checkbox('toxic',key='ds_add_toxic')
   labels['severe_toxic']=st.checkbox('severe_toxic',key='ds_add_severe')
   labels['obscene']=st.checkbox('obscene',key='ds_add_obscene')
  with r2:
   labels['threat']=st.checkbox('threat',key='ds_add_threat')
   labels['insult']=st.checkbox('insult',key='ds_add_insult')
   labels['identity_hate']=st.checkbox('identity_hate',key='ds_add_identity')
  with r3:
   source=st.selectbox('Source',['text','batch','voice','live','demo'],key='ds_add_source')
  r4,r5,r6,r7=st.columns(4)
  with r4:
   add_lang=st.selectbox('Language',LANG_FIELD_OPTS,key='ds_add_lang',help='Optional multilingual metadata sent with the sample.')
  with r5:
   add_lname=st.selectbox('Language name',NAME_FIELD_OPTS,key='ds_add_langname')
  with r6:
   add_script=st.selectbox('Script',SCRIPT_FIELD_OPTS,key='ds_add_script')
  with r7:
   add_split=st.selectbox('Split',SPLIT_FIELD_OPTS,key='ds_add_split')
  add_go=st.form_submit_button('ADD TO DATASET',use_container_width=True)
 if add_go:
  if not str(comment or '').strip(): st.warning('Comment text is required.')
  else:
   payload={'comment':str(comment).strip(),'source':source}
   payload.update({k:(1 if labels.get(k) else 0) for k in ('toxic','severe_toxic','obscene','threat','insult','identity_hate')})
   payload.update(_lang_payload(add_lang,add_lname,add_script,add_split))
   res=api('/dataset','POST',payload)
   if res is None: st.error('The sample could not be saved.')
   else:
    st.session_state['ds_flash']='Sample added to the dataset.'
    st.session_state['ds_offset']=0
    st.rerun()
 st.markdown('<div class="eyebrow" style="margin-top:26px">EDIT / DELETE SAMPLE</div>',unsafe_allow_html=True)
 editable=[i for i in items if i.get('id') is not None]
 if not editable:
  st.info('No samples are loaded for editing. Run a search above to load samples first.')
  return
 def _fmt(i):
  s=str(i.get('comment') or '')
  return f'#{i.get("id")} · {s[:60]}'
 pick=st.selectbox('Sample',[_fmt(i) for i in editable],key='ds_pick')
 sample=next((i for i in editable if _fmt(i)==pick),editable[0])
 cid=sample.get('id')
 if st.session_state.get('ds_edit_id')!=cid or 'ds_e_comment' not in st.session_state:
  st.session_state['ds_edit_id']=cid
  data={
   'comment':str(sample.get('comment') or ''),
   'toxic':bool(sample.get('toxic')),
   'severe_toxic':bool(sample.get('severe_toxic')),
   'obscene':bool(sample.get('obscene')),
   'threat':bool(sample.get('threat')),
   'insult':bool(sample.get('insult')),
   'identity_hate':bool(sample.get('identity_hate')),
   'source':str(sample.get('source') or 'text'),
   'language':str(sample.get('language') or ''),
   'language_name':str(sample.get('language_name') or ''),
   'script':str(sample.get('script') or ''),
   'split':str(sample.get('split') or ''),
  }
  st.session_state['ds_edit']=data
  st.session_state['ds_del_confirm']=None
  st.session_state['ds_e_comment']=data['comment']
  st.session_state['ds_e_toxic']=data['toxic']
  st.session_state['ds_e_severe']=data['severe_toxic']
  st.session_state['ds_e_obscene']=data['obscene']
  st.session_state['ds_e_threat']=data['threat']
  st.session_state['ds_e_insult']=data['insult']
  st.session_state['ds_e_identity']=data['identity_hate']
  st.session_state['ds_e_source']=data['source']
  st.session_state['ds_e_lang']=data['language'] or NOT_SET
  st.session_state['ds_e_langname']=data['language_name'] or NOT_SET
  st.session_state['ds_e_script']=data['script'] or NOT_SET
  st.session_state['ds_e_split']=data['split'] or NOT_SET
 e_comment=st.text_area('Comment',key='ds_e_comment',height=100)
 q1,q2,q3=st.columns(3)
 with q1:
  e_toxic=st.checkbox('toxic',key='ds_e_toxic')
  e_severe=st.checkbox('severe_toxic',key='ds_e_severe')
  e_obscene=st.checkbox('obscene',key='ds_e_obscene')
 with q2:
  e_threat=st.checkbox('threat',key='ds_e_threat')
  e_insult=st.checkbox('insult',key='ds_e_insult')
  e_identity=st.checkbox('identity_hate',key='ds_e_identity')
 with q3:
  e_source=st.selectbox('Source',['text','batch','voice','live','demo'],key='ds_e_source')
 q4,q5,q6,q7=st.columns(4)
 with q4:
  e_lang=st.selectbox('Language',_opts_with(LANG_FIELD_OPTS,st.session_state.get('ds_e_lang')),key='ds_e_lang',help='Optional multilingual metadata sent with the sample.')
 with q5:
  e_lname=st.selectbox('Language name',_opts_with(NAME_FIELD_OPTS,st.session_state.get('ds_e_langname')),key='ds_e_langname')
 with q6:
  e_script=st.selectbox('Script',_opts_with(SCRIPT_FIELD_OPTS,st.session_state.get('ds_e_script')),key='ds_e_script')
 with q7:
  e_split=st.selectbox('Split',_opts_with(SPLIT_FIELD_OPTS,st.session_state.get('ds_e_split')),key='ds_e_split')
 b1,b2=st.columns(2)
 if b1.button('SAVE CHANGES',key='ds_save',use_container_width=True):
  if not str(e_comment or '').strip(): st.warning('Comment text is required.')
  else:
   payload={'comment':str(e_comment).strip(),'source':e_source}
   payload.update({k:(1 if v else 0) for k,v in {'toxic':e_toxic,'severe_toxic':e_severe,'obscene':e_obscene,'threat':e_threat,'insult':e_insult,'identity_hate':e_identity}.items()})
   payload.update(_lang_payload(e_lang,e_lname,e_script,e_split))
   res=api(f'/dataset/{cid}','PUT',payload)
   if res is None: st.error('Changes could not be saved.')
   else:
    st.session_state['ds_flash']='Sample updated.'
    st.session_state['ds_edit_id']=None
    st.rerun()
 if b2.button('DELETE SAMPLE',key='ds_delete',use_container_width=True):
  st.session_state['ds_del_confirm']=cid; st.rerun()
 if st.session_state.get('ds_del_confirm')==cid:
  st.warning(f'Click CONFIRM DELETE to permanently remove sample #{cid}.')
  d1,d2=st.columns(2)
  if d1.button('CONFIRM DELETE',key='ds_del_yes',use_container_width=True):
   res=api(f'/dataset/{cid}','DELETE')
   if res is None: st.error('The sample could not be deleted.')
   else:
    st.session_state['ds_flash']='Sample deleted.'
    st.session_state['ds_del_confirm']=None
    st.session_state['ds_edit_id']=None
    st.rerun()
  if d2.button('CANCEL',key='ds_del_no',use_container_width=True):
   st.session_state['ds_del_confirm']=None; st.rerun()

def compare_rows(cmp):
 rows=[]
 if isinstance(cmp,dict):
  nested=cmp.get('items')
  if isinstance(nested,list):
   for it in nested:
    if isinstance(it,dict): rows.append((it.get('metric') or it.get('name','—'),it.get('baseline','—'),it.get('improved','—')))
  else:
   base=cmp.get('baseline') or cmp.get('baseline_metrics') or cmp.get('base')
   imp=cmp.get('improved') or cmp.get('improved_metrics') or cmp.get('new')
   if isinstance(base,dict) and base and isinstance(imp,dict):
    for k in base: rows.append((k,base.get(k,'—'),imp.get(k,'—')))
   else:
    for k,v in cmp.items():
     if isinstance(v,(dict,list)): continue
     rows.append((k,v,'—'))
 elif isinstance(cmp,list):
  for it in cmp:
   if isinstance(it,dict): rows.append((it.get('metric') or it.get('name','—'),it.get('baseline','—'),it.get('improved','—')))
 return rows

def admin_call(path, method='GET', payload=None):
    """Call an admin-only AURA endpoint with the session Bearer token.

    Returns (data, status_code) where status 0 means the backend could not be
    reached.  Failures come back as a bare status code so pages can show a
    short friendly note instead of raw error text or stack traces."""
    token = st.session_state.get('token')
    headers = {'Authorization': f'Bearer {token}'} if token else {}
    try:
        r = requests.request(method, BACKEND_URL + path, json=payload, headers=headers, timeout=30)
    except requests.RequestException:
        return None, 0
    if not r.ok:
        return None, r.status_code
    try:
        return r.json(), r.status_code
    except ValueError:
        return None, r.status_code

def admin_note(status):
    """Friendly one-line wording for an admin endpoint status code."""
    if status == 0:
        return 'The AURA backend is unreachable. Start the backend and try again.'
    if status == 401:
        return 'Your session is not valid for this admin action. Sign in again and retry.'
    if status == 403:
        return 'Admin access is required for this action.'
    if status == 404:
        return 'This backend build does not expose the Phase 2 model endpoint yet.'
    return 'The request could not be completed right now.'

def rate_txt(v):
    """Format a 0..1 benchmark rate as a percentage ('—' when not reported)."""
    if v is None:
        return '—'
    try:
        f = float(v)
    except (TypeError, ValueError):
        return '—'
    return f'{f * 100:.1f}%'

def rate_pair(legacy_v, model_v):
    """'legacy → model' wording for one benchmark metric."""
    a = rate_txt(legacy_v)
    b = rate_txt(model_v)
    if a == '—':
        return b
    if b == '—':
        return a
    return f'{a} → {b}'

def ms_txt(v):
    """Format a millisecond latency ('—' when not reported)."""
    if v is None:
        return '—'
    try:
        f = float(v)
    except (TypeError, ValueError):
        return '—'
    return f'{f:.1f} ms'

def phase2_model_section():
 """Phase 2 admin view: legacy vs pretrained benchmark table + engine switch."""
 st.markdown('<div class="eyebrow" style="margin-top:28px">PHASE 2 · PRETRAINED MODEL</div><div class="subtle" style="max-width:920px">Legacy rules compared with the pretrained multilingual model on the labelled benchmark, plus the live prediction-engine switch.</div>',unsafe_allow_html=True)
 ok=st.session_state.pop('p2_flash_ok',None)
 if ok: st.success(ok)
 bad=st.session_state.pop('p2_flash_bad',None)
 if bad: st.warning(bad)
 eng,eng_st=admin_call('/models/engine')
 data,ad_st=admin_call('/models/adapter')
 shown=set()
 def warn_once(status):
  if status in shown: return
  shown.add(status)
  st.warning(admin_note(status))
 engine_name=''; engine_src=''; engine_src_note=''; adapter={}
 if isinstance(eng,dict):
  engine_name=str(eng.get('engine') or '')
  engine_src=str(eng.get('source') or '')
  engine_src_note=str(eng.get('source_note') or '')
  if isinstance(eng.get('adapter'),dict): adapter=eng.get('adapter')
 else:
  warn_once(eng_st)
 if isinstance(data,dict):
  if not engine_name: engine_name=str(data.get('engine') or '')
  if not adapter and isinstance(data.get('adapter'),dict): adapter=data.get('adapter')
 else:
  warn_once(ad_st)
 if engine_name:
  head=f'<b>Active engine:</b> {html.escape(engine_name)}'
  if engine_src: head+=f' · <b>Source:</b> {html.escape(engine_src)}'
  if engine_src_note: head+=f'<div class="subtle" style="margin-top:4px">{html.escape(engine_src_note)}</div>'
  ad_status=str(adapter.get('status') or '')
  ad_model=model_short_name(adapter.get('model_id'))
  if ad_status or ad_model:
   head+=f'<div class="subtle" style="margin-top:4px">Adapter: {html.escape(ad_status or "—")}'+(f' · {html.escape(ad_model)}' if ad_model else '')+'</div>'
  st.markdown(f'<div class="surface" style="margin-top:14px">{head}</div>',unsafe_allow_html=True)
 if isinstance(data,dict):
  bench=data.get('benchmark') if isinstance(data.get('benchmark'),dict) else {}
  groups=bench.get('groups') if isinstance(bench.get('groups'),dict) else {}
  thr=bench.get('tuned_threshold')
  if isinstance(thr,dict):
   thr_val=thr.get('threshold'); thr_lang=thr.get('per_language') if isinstance(thr.get('per_language'),dict) else {}
  else:
   thr_val=thr; thr_lang={}
  cov=data.get('coverage') if isinstance(data.get('coverage'),dict) else {}
  if not cov and isinstance(eng,dict) and isinstance(eng.get('coverage'),dict): cov=eng.get('coverage')
  mem=data.get('memory_mb') if isinstance(data.get('memory_mb'),dict) else {}
  claimed=[str(x).strip() for x in data.get('claimed_languages') if str(x).strip()] if isinstance(data.get('claimed_languages'),list) else []
  line=f'<b>Tuned threshold:</b> {_num(thr_val):.2f}' if thr_val is not None else '<b>Tuned threshold:</b> —'
  if thr_lang: line+=' · <b>Per language:</b> '+html.escape(' · '.join(f'{k} {_num(v):.2f}' for k,v in thr_lang.items()))
  line+=f'<div class="subtle" style="margin-top:4px">Benchmark: {html.escape(str(bench.get("generated_at") or "—"))}'
  if mem: line+=f' · Model memory: {_num(mem.get("after")):.0f} MB'
  line+='</div>'
  if claimed: line+=f'<div class="subtle" style="margin-top:4px">Model-card claimed languages: {html.escape(", ".join(claimed))}</div>'
  st.markdown(f'<div class="surface" style="margin-top:14px">{line}</div>',unsafe_allow_html=True)
  if not groups:
   st.info('Benchmark groups are not available from this backend yet.')
  else:
   order=[c for c in LANG_CODES if c in groups]+[k for k in groups if k not in LANG_CODES]
   table='<table class="admin-table"><tr><th>Language</th><th>Samples</th><th>Accuracy legacy → model</th><th>Toxic F1 legacy → model</th><th>FPR legacy → model</th><th>Threshold used</th><th>Model latency</th><th>Coverage</th></tr>'
   notes=[]
   for code in order:
    g=groups.get(code) if isinstance(groups.get(code),dict) else {}
    lg=g.get('legacy') if isinstance(g.get('legacy'),dict) else {}
    mg=g.get('model') if isinstance(g.get('model'),dict) else {}
    cov_v=cov.get(code)
    if isinstance(cov_v,dict):
     cov_txt=str(cov_v.get('status') or '—'); cov_note=str(cov_v.get('note') or '')
    elif isinstance(cov_v,str) and cov_v.strip():
     cov_txt=cov_v.strip(); cov_note=''
    else:
     cov_txt='—'; cov_note=''
    if cov_note: notes.append((code,cov_note))
    label=f'{lang_flag(code)} {html.escape(LANG_NAMES.get(str(code),str(code)))} ({html.escape(str(code))})'
    n=g.get('n'); n_txt='—' if n is None else html.escape(str(n))
    thr_used=g.get('threshold_used'); thr_txt='—' if thr_used is None else f'{_num(thr_used):.2f}'
    lat=mg.get('latency_ms_per_text') if mg.get('latency_ms_per_text') is not None else g.get('latency_ms_per_text')
    cells=[n_txt,rate_pair(lg.get('accuracy'),mg.get('accuracy')),rate_pair(lg.get('toxic_f1'),mg.get('toxic_f1')),rate_pair(lg.get('fpr'),mg.get('fpr')),thr_txt,ms_txt(lat),html.escape(cov_txt.replace('_',' '))]
    table+=f'<tr><td>{label}</td>'+''.join(f'<td>{cv}</td>' for cv in cells)+'</tr>'
   st.markdown(table+'</table>',unsafe_allow_html=True)
   if notes:
    st.markdown(''.join(f'<div class="subtle" style="margin-top:4px"><b>{html.escape(LANG_NAMES.get(str(nc),str(nc)))}:</b> {html.escape(nn)}</div>' for nc,nn in notes),unsafe_allow_html=True)
 # Engine switch control (POST /models/engine) with a confirm-style step.
 st.markdown('<div class="eyebrow" style="margin-top:24px">ENGINE CONTROL</div>',unsafe_allow_html=True)
 modes=[str(m).strip() for m in (eng.get('modes') if isinstance(eng,dict) and isinstance(eng.get('modes'),list) else []) if str(m).strip()]
 if not modes: modes=['legacy','auto','hf']
 if engine_name and engine_name not in modes: modes=[engine_name]+modes
 idx=modes.index(engine_name) if engine_name in modes else 0
 blocked=(not isinstance(eng,dict)) and eng_st in (0,401,403,404)
 pick=st.selectbox('Prediction engine',modes,index=idx,key='p2_engine_pick',disabled=blocked,help='Sent to POST /models/engine; applies to new predictions and requires an admin token.')
 if st.button('SWITCH ENGINE',use_container_width=True,key='p2_engine_go',disabled=blocked):
  st.session_state['p2_engine_confirm']=str(pick); st.rerun()
 target=str(st.session_state.get('p2_engine_confirm') or '')
 if target:
  st.warning(f'Click CONFIRM SWITCH to change the live prediction engine to "{target}". Existing history is not affected.')
  c1,c2=st.columns(2)
  if c1.button('CONFIRM SWITCH',use_container_width=True,key='p2_engine_yes'):
   out,pst=admin_call('/models/engine','POST',{'engine':target})
   st.session_state['p2_engine_confirm']=None
   if isinstance(out,dict) and out.get('ok'): st.session_state['p2_flash_ok']=f'Prediction engine is now {str(out.get("engine") or target)}.'
   else: st.session_state['p2_flash_bad']=admin_note(pst)
   st.rerun()
  if c2.button('CANCEL',use_container_width=True,key='p2_engine_no'):
   st.session_state['p2_engine_confirm']=None; st.rerun()

def model_perf_page():
 st.markdown('<div class="eyebrow">ADMIN · ML EVALUATION</div><div class="display-medium">MODEL PERFORMANCE.</div>',unsafe_allow_html=True)
 perf=api('/models/performance')
 if not isinstance(perf,dict):
  st.markdown('<div class="surface">Model performance data is unavailable right now.</div>',unsafe_allow_html=True)
  phase2_model_section()
  return
 def mval(v):
  if v is None: return 'Not evaluated'
  if isinstance(v,str): return v
  try: f=float(v)
  except Exception: return str(v)
  if 0.0<=f<=1.0: return f'{f*100:.1f}%'
  if abs(f-round(f))<1e-9: return str(int(round(f)))
  return f'{f:g}'
 cards=[('ACCURACY',perf.get('accuracy')),('PRECISION',perf.get('precision')),('RECALL',perf.get('recall')),('F1',perf.get('f1'))]
 cs=st.columns(4)
 for col,(a,v) in zip(cs,cards):
  col.markdown(f'<div class="metric"><div class="metric-label">{a}</div><div class="metric-value" style="font-size:1.9rem">{html.escape(mval(v))}</div></div>',unsafe_allow_html=True)
 def txt(v): return '—' if v is None else html.escape(str(v))
 st.markdown(
  '<div class="eyebrow" style="margin-top:20px">EVALUATION DETAILS</div>'
  f'<div class="surface"><b>Status:</b> {txt(perf.get("status"))} · <b>Model version:</b> {txt(perf.get("model_version"))} · <b>Evaluated at:</b> {txt(perf.get("evaluated_at"))}'
  f'<div class="subtle" style="margin-top:8px">Training samples: <b>{txt(perf.get("training_samples"))}</b> · Validation samples: <b>{txt(perf.get("validation_samples"))}</b> · Test samples: <b>{txt(perf.get("test_samples"))}</b></div></div>',
  unsafe_allow_html=True
 )
 st.markdown('<div class="eyebrow" style="margin-top:22px">CONFUSION MATRIX</div>',unsafe_allow_html=True)
 cm=perf.get('confusion_matrix')
 labels=cm.get('labels') if isinstance(cm,dict) else None
 matrix=cm.get('matrix') if isinstance(cm,dict) else None
 if isinstance(labels,list) and labels and isinstance(matrix,list) and matrix:
  table='<table class="admin-table"><tr><th></th>'+''.join(f'<th>{html.escape(str(l))}</th>' for l in labels)+'</tr>'
  for i,row in enumerate(matrix):
   rl=str(labels[i]) if i<len(labels) else str(i)
   table+=f'<tr><th>{html.escape(rl)}</th>'
   if isinstance(row,(list,tuple)):
    row_sum=sum(_num(c) for c in row)
    for j,c in enumerate(row):
     frac=_num(c)/row_sum if row_sum>0 else 0.0
     frac=max(0.0,min(1.0,frac))
     rgb='22,148,71' if i==j else '255,23,68'
     fg='#fff' if frac>0.55 else '#151515'
     table+=f'<td style="text-align:center;background:rgba({rgb},{0.06+0.9*frac:.2f});color:{fg};font-weight:700">{html.escape(str(c))}</td>'
   table+='</tr>'
  st.markdown(table+'</table>',unsafe_allow_html=True)
 else:
  st.info('Confusion matrix: Not evaluated')
 st.markdown('<div class="eyebrow" style="margin-top:22px">PERFORMANCE BY LANGUAGE</div>',unsafe_allow_html=True)
 def nval(v):
  if v is None: return 'Not evaluated'
  if isinstance(v,str): return v
  try: f=float(v)
  except Exception: return str(v)
  if abs(f-round(f))<1e-9: return str(int(round(f)))
  return f'{f:g}'
 by_lang=perf.get('by_language')
 if not isinstance(by_lang,dict) or not by_lang:
  st.info('Per-language evaluation: Not evaluated')
 else:
  order=[c for c in LANG_CODES if c in by_lang]+[k for k in by_lang if k not in LANG_CODES]
  table='<table class="admin-table"><tr><th>Language</th><th>Accuracy</th><th>Precision</th><th>Recall</th><th>F1</th><th>Support</th></tr>'
  for code in order:
   row=by_lang.get(code)
   if not isinstance(row,dict):
    cells=['Not evaluated']*5
   else:
    cells=[mval(row.get('accuracy')),mval(row.get('precision')),mval(row.get('recall')),mval(row.get('f1')),nval(row.get('support'))]
   label=f'{lang_flag(code)} {html.escape(LANG_NAMES.get(str(code),str(code)))} ({html.escape(str(code))})'
   table+=f'<tr><td>{label}</td>'+''.join(f'<td>{html.escape(str(c))}</td>' for c in cells)+'</tr>'
  st.markdown(table+'</table>',unsafe_allow_html=True)
 st.markdown('<div class="eyebrow" style="margin-top:26px">MODEL COMPARISON</div>',unsafe_allow_html=True)
 cmp_rows=compare_rows(api('/models/compare'))
 if not cmp_rows:
  st.info('No model comparison is available yet.')
 else:
  table='<table class="admin-table"><tr><th>Metric</th><th>Baseline</th><th>Improved</th></tr>'
  for name,base,imp in cmp_rows: table+=f'<tr><td>{html.escape(str(name))}</td><td>{html.escape(str(base))}</td><td>{html.escape(str(imp))}</td></tr>'
  st.markdown(table+'</table>',unsafe_allow_html=True)
 phase2_model_section()

def model_versions_page():
 st.markdown('<div class="eyebrow">ADMIN · MODEL REGISTRY</div><div class="display-medium">MODEL VERSIONS.</div>',unsafe_allow_html=True)
 out=api('/models')
 versions=[]
 if isinstance(out,dict): versions=out.get('versions') or []
 elif isinstance(out,list): versions=out
 if not isinstance(versions,list): versions=[]
 versions=[v for v in versions if isinstance(v,dict)]
 if not versions:
  st.markdown('<div class="surface">No model versions have been registered yet.</div>',unsafe_allow_html=True)
  return
 view=[]
 for v in versions:
  m=v.get('metrics')
  if isinstance(m,(dict,list)):
   try: mtxt=json.dumps(m)[:150]
   except Exception: mtxt=str(m)[:150]
  else:
   mtxt=str(m or '')
  view.append({'model_name':str(v.get('model_name') or ''),'model_version':str(v.get('model_version') or ''),'dataset_version':str(v.get('dataset_version') or ''),'training_date':str(v.get('training_date') or ''),'metrics':mtxt,'status':str(v.get('status') or ''),'created_at':str(v.get('created_at') or '')})
 st.dataframe(pd.DataFrame(view),use_container_width=True)
 st.markdown('<div class="eyebrow" style="margin-top:24px">VERSION METRICS</div>',unsafe_allow_html=True)
 opts=[f'{i} · {v["model_name"]} {v["model_version"]}' for i,v in enumerate(view)]
 choice=st.selectbox('Model version',opts,key='mv_pick')
 try: idx=int(str(choice).split(' · ')[0])
 except Exception: idx=0
 if 0<=idx<len(versions):
  metrics=versions[idx].get('metrics')
  if isinstance(metrics,(dict,list)): st.json(metrics)
  elif metrics is None: st.info('No metrics were recorded for this version.')
  else: st.code(str(metrics))
 else:
  st.info('Select a version to inspect its metrics.')

def training_page():
 st.markdown('<div class="eyebrow">ADMIN · ML OPS</div><div class="display-medium">TRAINING.</div>',unsafe_allow_html=True)
 split=api('/models/split')
 if isinstance(split,dict):
  vals=[('SEED',split.get('seed')),('TRAIN',split.get('train')),('VALIDATION',split.get('validation')),('TEST',split.get('test'))]
  cs=st.columns(4)
  for col,(a,b) in zip(cs,vals):
   col.markdown(f'<div class="metric"><div class="metric-label">{a}</div><div class="metric-value">{"—" if b is None else html.escape(str(b))}</div></div>',unsafe_allow_html=True)
 else:
  st.info('Dataset split information is unavailable right now.')
 st.markdown('<div class="eyebrow" style="margin-top:22px">TRAINING RUN</div>',unsafe_allow_html=True)
 variant=st.selectbox('Variant',['baseline','improved'],key='train_variant')
 if st.button('START TRAINING',use_container_width=True,key='train_start'):
  out=api('/models/train','POST',{'variant':variant,'config':{'variant':variant}})
  job=(out.get('job_id') or out.get('id')) if isinstance(out,dict) else None
  if job:
   st.session_state['train_job']=str(job)
   st.session_state['train_checks']=0
   st.session_state['train_final']=None
   st.success(f'Training job started: {job} ({variant} variant)')
  else:
   st.error('The training job could not be started.')
 job=st.session_state.get('train_job')
 if not job:
  st.markdown('<div class="surface">No training job yet. Choose a variant and press START TRAINING.</div>',unsafe_allow_html=True)
  return
 terminal={'completed','complete','finished','success','succeeded','done','failed','error','cancelled','canceled'}
 checks=int(st.session_state.get('train_checks') or 0)
 final=st.session_state.get('train_final') if isinstance(st.session_state.get('train_final'),dict) else None
 status_now=str((final or {}).get('status') or '').lower()
 timed_out=False
 if status_now not in terminal:
  if checks>=30:
   timed_out=True
  else:
   deadline=time.time()+45.0
   with st.spinner('Training in progress - polling the backend every second...'):
    while checks<30 and time.time()<deadline:
     res=api(f'/models/train/{job}')
     checks+=1
     if isinstance(res,dict):
      final=res
      status_now=str(res.get('status') or '').lower()
     if status_now in terminal: break
     if checks<30 and time.time()<deadline: time.sleep(1)
   st.session_state['train_checks']=checks
   st.session_state['train_final']=final
   if status_now not in terminal: timed_out=True
 if not isinstance(final,dict):
  st.error('Training status could not be read for this job.')
  if timed_out:
   st.warning('Polling stopped after 30 checks (or about 45 seconds) while the job was still running or unreachable. The job continues on the server.')
   if st.button('CHECK STATUS',use_container_width=True,key='train_check'):
    st.session_state['train_checks']=0
    st.rerun()
  return
 prog=final.get('progress')
 try:
  pv=float(prog)
  if pv>1.0: pv=pv/100.0
  st.progress(max(0.0,min(1.0,pv)))
 except Exception:
  pass
 status_txt=str(final.get('status') or 'unknown')
 message=str(final.get('message') or '')
 st.markdown(
  f'<div class="surface"><b>Status:</b> {html.escape(status_txt)} · <b>Progress:</b> {html.escape("—" if prog is None else str(prog))}'
  f'{"<br><b>Message:</b> "+html.escape(message) if message else ""}</div>',
  unsafe_allow_html=True
 )
 if final.get('error'): st.error(f"Training error: {final.get('error')}")
 metrics=final.get('metrics')
 if isinstance(metrics,(dict,list)):
  st.markdown('<div class="eyebrow" style="margin-top:14px">METRICS</div>',unsafe_allow_html=True)
  st.json(metrics)
 if timed_out:
  st.warning('Training is taking longer than expected: polling stopped after 30 checks. Press CHECK STATUS to keep polling.')
  if st.button('CHECK STATUS',use_container_width=True,key='train_check'):
   st.session_state['train_checks']=0; st.rerun()
 elif status_now in {'failed','error','cancelled','canceled'}:
  st.error('Training did not complete. See the error above.')
 elif status_now in {'completed','complete','finished','success','succeeded','done'}:
  st.success('Training finished. Review the metrics above.')

def settings_page():
 st.markdown('<div class="eyebrow">ADMIN · CONFIGURATION</div><div class="display-medium">SYSTEM SETTINGS.</div>',unsafe_allow_html=True)
 if not st.session_state.get('settings_loaded'):
  loaded=0.5
  res=api('/settings')
  if isinstance(res,dict):
   try: loaded=float(res.get('toxicity_threshold'))
   except Exception: loaded=0.5
  st.session_state['aura_threshold']=max(0.0,min(1.0,loaded))
  st.session_state['settings_saved']=st.session_state['aura_threshold']
  st.session_state['settings_loaded']=True
 if 'aura_threshold' not in st.session_state: st.session_state['aura_threshold']=0.5
 if 'settings_saved' not in st.session_state: st.session_state['settings_saved']=st.session_state['aura_threshold']
 st.markdown('<div class="surface"><b>TOXICITY THRESHOLD</b><div class="subtle">Predictions whose confidence is at or above this value are labelled <b>toxic</b>; below it they are labelled <b>non_toxic</b>. This changes the overall_label classification for text, batch, voice and live predictions.</div></div>',unsafe_allow_html=True)
 thr=st.slider('Toxicity threshold',0.0,1.0,step=0.01,format='%.2f',key='aura_threshold')
 flash=None
 if st.button('SAVE SETTINGS',use_container_width=True,key='settings_save'):
  out=api('/settings','PUT',{'toxicity_threshold':float(thr)})
  if out is None: st.error('Settings could not be saved.')
  else:
   st.session_state['settings_saved']=float(thr)
   flash='Settings saved.'
 if flash: st.success(flash)
 saved=st.session_state.get('settings_saved')
 try: saved_txt=f'{float(saved):.2f}'
 except Exception: saved_txt='—'
 st.markdown(f'<div class="subtle" style="margin-top:14px">Current persisted threshold: <b>{saved_txt}</b> · Slider value: <b>{float(thr):.2f}</b></div>',unsafe_allow_html=True)

def main():
 if not st.session_state.user or not st.session_state.token: auth_page(); return
 sidebar()
 page=st.session_state.page
 user=st.session_state.user if isinstance(st.session_state.user,dict) else {}
 role=user.get('role') or 'user'
 shared={'safety':safety_page,'text':safety_page,'batch':batch_page,'voice':voice_page,'live':live_page,'analytics':analytics_page,'history':history_page}
 admin_only={'dashboard':admin_dashboard,'review':admin_review,'comments':admin_comments,'users':admin_users,'dataset':dataset_page,'model_perf':model_perf_page,'models':model_versions_page,'training':training_page,'settings':settings_page}
 if role=='admin':
  (shared.get(page) or admin_only.get(page) or admin_dashboard)()
 else:
  if page in admin_only:
   st.session_state.page='safety'; page='safety'
  (shared.get(page) or safety_page)()
if __name__=='__main__': main()
