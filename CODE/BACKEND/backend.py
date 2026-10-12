from __future__ import annotations
import base64, getpass, hashlib, io, json, os, re, secrets, sqlite3, sys, threading, uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / 'aura.db'
app = FastAPI(title='AURA — Intelligent Content Safety', version='2.0.0')
app.add_middleware(CORSMiddleware, allow_origins=['http://127.0.0.1:8501','http://localhost:8501'], allow_credentials=True, allow_methods=['*'], allow_headers=['*'])
SESSIONS: dict[str, dict[str, Any]] = {}
# ---------------------------------------------------------------------------
# AURA 4.17 - session lifetime & login throttling
# ---------------------------------------------------------------------------
# Sessions live in memory only, so an application restart invalidates ALL of
# them. That is deliberate and documented (PHASE417_SESSION_SECURITY_EVIDENCE.md).
# A token is additionally bound to the user's credential_version, so rotating a
# password invalidates every token minted before the rotation.
SESSION_TTL_SECONDS = 12 * 3600
# Login throttling. PROPOSED DEFAULTS, not an approved policy - see
# PHASE417_REPORT.md Task 3. Delays are used instead of a hard lockout so an
# unauthenticated attacker cannot deny service to the sole administrator by
# simply triggering failures.
LOGIN_BACKOFF_BASE_SECONDS = 30
LOGIN_BACKOFF_MAX_SECONDS = 900
LOGIN_FAILURE_WINDOW_SECONDS = 900
LABELS=['toxic','severe_toxic','obscene','threat','insult','identity_hate']
SOURCES=('text','batch','voice','live')
# Dataset provenance tags are free-form (demo, manual, feedback, ...) but still validated.
DATASET_SOURCE_RE=re.compile(r'^[A-Za-z0-9][A-Za-z0-9 _-]{0,39}$')
# Dataset storage + training live in ml_service.  Import defensively so the
# backend still boots (and every other endpoint still works) when it is absent.
try:
 import ml_service
except Exception:
 ml_service=None

# Multilingual lexicon engine (language detection + data/lexicons matching).
# Defensive import: the backend must still boot when the module is absent.
try:
 import mlexicon
except Exception:
 mlexicon=None

# Phase 2: modular pretrained-model adapter (Hugging Face, lazy single load).
# Defensive import: when the adapter or its dependencies are absent, the
# backend boots normally and every request keeps using the legacy engine.
try:
 import model_adapter
except Exception:
 model_adapter=None

ENGINE_MODES=('legacy','auto','hf')
ENGINE_DEFAULT='legacy'

# Multilingual safety lexicon.  English behaviour is preserved; these additions
# make the same six safety signals understandable in Indian scripts, Romanized
# Indian speech (Tanglish/Hinglish/etc.), and mixed-language comments.
LEX={
 'toxic':[
  # English
  'idiot','moron','dumb','stupid','shut up','useless','trash','garbage','loser','fool','jerk','clown','pathetic',
  # Tamil + Tanglish
  'பைத்தியம்','முட்டாள்','மூடன்','அறிவில்லாத','உபயோகமில்லை','வேஸ்ட்','கேவலமானவன்','கேவலமானவள்','கேவலமான ஆள்','அசிங்கமானவன்','அசிங்கமானவள்','கிறுக்கன்','முட்டாள்தனமாக',
  'paithiyam','muttal','muttal','moodan','arivillatha','use illa','useless','kevalamanavan','kevalamana aal','asingamanavan','asingamanaval','kirukkan',
  # Telugu + Tenglish
  'పిచ్చివాడు','పిచ్చిదానివి','మూర్ఖుడు','వెధవ','దరిద్రుడు','నీచుడు','పిచ్చి','వెధవా','వెధవుడు',
  'pichivadu','pichhodu','murkhudu','vedhava','daridrudu','nichudu','vedhavodini',
  # Kannada + Kanglish
  'ಹುಚ್ಚ','ಮೂರ್ಖ','ದಡ್ಡ','ಬೇವಕೂಫ್','ಕೆಟ್ಟವನು','ನೀಚ','ಹುಚ್ಚನ',
  'huchcha','moorkha','dadda','bevakuf','kettavanu','neech','huchchan',
  # Malayalam + Manglish
  'ഭ്രാന്തൻ','മണ്ടൻ','മണ്ടി','വിഡ്ഢി','നീചൻ','വൃത്തികെട്ടവൻ','പൊട്ടൻ',
  'bhranthan','mandan','mandi','viddhi','neechan','vrithikettavan','pottan',
  # Hindi + Hinglish
  'बेवकूफ','मूर्ख','गधा','पागल','निकम्मा','नालायक','घटिया','बदतमीज',
  'bewakoof','bewaqoof','moorkh','gadha','pagal','nikamma','nalayak','ghatiya','badtameez',
  # Bengali + Banglish
  'বোকা','মূর্খ','গাধা','পাগল','অযোগ্য','নিকম্মা','জঘন্য','অসভ্য',
  'boka','murkho','gadha','pagol','ojoggo','nikamma','joghonyo','oshobbo'
 ],
 'severe_toxic':[
  'kill yourself','die','go die','suicide','சாக','செத்துப் போ','சாவு','உன்னை சாக','saagu','seththu po','savu',
  'చచ్చిపో','చావు','నువ్వు చచ్చిపో','chachipo','chavu',
  'ಸಾಯು','ಸತ್ತು ಹೋಗು','saayu','sattu hogu',
  'ചാവൂ','ചത്തുപോ','chaavu','chathupo',
  'मर जा','मर जाओ','आत्महत्या','mar ja','mar jao','aatmahatya',
  'মরে যাও','মর','আত্মহত্যা','more jao','mor','atmohotya'
 ],
 'obscene':[
  'fuck','fucking','shit','bastard','asshole','what the fuck','damn',
  'புண்டை','தேவடியா','ஒழி','கேவலம்','போய் தொலை','போய்த்தொலை','மயிர்','மைரு','பொறுக்கி',
  'pundai','thevadiya','ozhi','kevalam','po tholai','poy tholai',
  'దరిద్రం','దెంగు','దెంగ','దెంగేయ్','చెత్త','వెధవ','daridram','dengu','denga','chetta',
  'ಕೊಳಕು','ಕೆಟ್ಟ ಪದ','ಹೋಗು','ನಾಯಿ','kolaku','kettu pada','hogu',
  'പന്നി','പന്നിയാണ്','തെറി','അശ്ലീലം','മൈര്','മൈരേ','myre','panni','theri','ashleelam',
  'भाड़ में जाओ','गाली','बकवास','भोसड़ी','चूत','गंदी गाली','fuck you','bhaad mein jao','gaali','bakwaas','bhosdi','choot',
  'চোদ','চোদা','গালি','নোংরা','বাজে কথা','জঘন্য গালি','chod','gali','nongra','baje kotha'
 ],
 'threat':[
  'i will find you','i will hurt you',"i'll hurt you",'hurt you','kill you','i will kill',"i'll kill",'beat you','attack you','you will regret',"you'll regret",'find you and hurt',
  'உன்னை கண்டுபிடித்து','உன்னை காயப்படுத்துவேன்','கொன்று விடுவேன்','உன்னை கொல்வேன்','தாக்குவேன்','அடிப்பேன்','காயப்படுத்துவேன்',
  'unnai kandupidiththu','unnai kaayapaduththuven','unnai kolven','kondru viduven','thaakkuven','adippen','kaayapaduththuven',
  'నిన్ను కనుక్కొని','నిన్ను చంపుతాను','నిన్ను కొడతాను','నిన్ను గాయపరుస్తాను','దాడి చేస్తాను',
  'ninnu kanukkoni','ninnu champuthanu','ninnu kodathanu','ninnu gayaparusthanu','dadi chestanu',
  'ನಿನ್ನನ್ನು ಹುಡುಕಿ','ನಿನ್ನನ್ನು ಕೊಲ್ಲುತ್ತೇನೆ','ನಿನ್ನನ್ನು ಹೊಡೆಯುತ್ತೇನೆ','ನಿನ್ನನ್ನು ಗಾಯಗೊಳಿಸುತ್ತೇನೆ','ದಾಳಿ ಮಾಡುತ್ತೇನೆ',
  'ninnannu huduki','ninnannu kolluttene','ninnannu hodeyuttene','ninnannu gayagolisuttene','daali maduttene',
  'നിന്നെ കണ്ടെത്തി','നിന്നെ കൊല്ലും','നിന്നെ അടിക്കും','നിന്നെ ഉപദ്രവിക്കും',
  'ninne kandethi','ninne kollum','ninne adikkum','ninne upadravikkum',
  'मैं तुम्हें ढूंढूंगा','मैं तुम्हें मार दूंगा','तुम्हें चोट पहुंचाऊंगा','तुम्हें पीटूंगा','तुम पर हमला करूंगा',
  'main tumhe dhundhunga','main tumhe maar dunga','tumhe chot pahuchaunga','tumhe peetunga','tum par hamla karunga',
  'আমি তোমাকে খুঁজে বের করব','আমি তোমাকে মেরে ফেলব','আমি তোমাকে আঘাত করব','তোমাকে মারব',
  'ami tomake khuje ber korbo','ami tomake mere felbo','ami tomake aghat korbo','tomake marbo'
 ],
 'insult':[
  'idiot','stupid','moron','loser','fool','dumb','jerk','clown','pathetic','asshole',
  'முட்டாள்','மூடன்','அறிவில்லாத','கேவலமானவன்','அசிங்கமானவன்','முட்டாள்தனமாக','முட்டாளே',
  'muttal','moodan','arivillatha','kevalamanavan','asingamanavan','muttale',
  'వెధవ','మూర్ఖుడు','పిచ్చివాడు','దద్దమ్మ','vedhava','murkhudu','pichivadu','daddamma',
  'ದಡ್ಡ','ಮೂರ್ಖ','ಹುಚ್ಚ','ಬೇವಕೂಫ್','dadda','moorkha','huchcha','bevakuf',
  'മണ്ടൻ','വിഡ്ഢി','ഭ്രാന്തൻ','പൊട്ടൻ','mandan','viddhi','bhranthan','pottan',
  'बेवकूफ','मूर्ख','गधा','पागल','नालायक','बदतमीज','bewakoof','moorkh','gadha','pagal','nalayak','badtameez',
  'বোকা','মূর্খ','গাধা','পাগল','অসভ্য','boka','murkho','gadha','pagol','oshobbo'
 ],
 'identity_hate':[
  'racist','race','religion','caste','ethnic','community','ஜாதி','மதம்','இனம்','சாதி','जाति','धर्म','नस्ल','समुदाय',
  'ജാതി','മതം','വംശം','ജാതിവെറി','ಜಾತಿ','ಧರ್ಮ','ವಂಶ','జాతి','మతం','కులం','জাতি','ধর্ম','বর্ণ'
 ]
}
POS=['great work','good work','well done','excellent','nice','thank you','thanks','awesome','good job','keep it up','அருமை','நல்ல வேலை','மிகவும் நன்று','நன்றி','சிறப்பு','வாழ்த்துகள்','చాలా బాగుంది','ధన్యవాదాలు','ಅದ್ಭುತ','ಧನ್ಯವಾದಗಳು','വളരെ നന്നായി','നന്ദി','बहुत अच्छा','धन्यवाद','খুব ভালো','ধন্যবাদ']

class MessageIn(BaseModel):
 text: Optional[str]=None; message: Optional[str]=None; context: str=''; context_messages:list[str]=Field(default_factory=list); user_id:str='anonymous'; conversation_id:str='default'; source:Optional[str]='text'
 def get_text(self): return (self.text if self.text is not None else self.message or '').strip()
 def get_context(self): return [str(x).strip() for x in self.context_messages if str(x).strip()] or [x.strip() for x in self.context.splitlines() if x.strip()]
class LoginIn(BaseModel): username:str; password:str; role:Optional[str]=None
class RegisterIn(BaseModel): username:str; password:str
class HumanDecisionIn(BaseModel): decision:str; note:str=''
class BlockIn(BaseModel): username:str
class BatchIn(BaseModel):
 comments:list[str]=Field(default_factory=list); source:Optional[str]='batch'
class FeedbackIn(BaseModel):
 prediction_id:Optional[int]=None; correct:bool; corrected_label:Optional[str]=None; comment:Optional[str]=None
class SettingsIn(BaseModel):
 toxicity_threshold:float=Field(...,ge=0.0,le=1.0)
class EngineIn(BaseModel):
 engine:str=Field(...,min_length=1,max_length=32)
class TrainIn(BaseModel):
 config:Optional[dict]=None
class VerifyIn(BaseModel):
 verified:bool; corrected_label:Optional[str]=None; add_to_dataset:bool=False
class LiveChunkIn(BaseModel):
 session_id:str; transcript:str; elapsed_s:Optional[float]=None
class LiveStopIn(BaseModel):
 session_id:str
class VoicePredictIn(BaseModel):
 transcript:str
class DatasetIn(BaseModel):
 comment:str
 toxic:int=Field(...,ge=0,le=1); severe_toxic:int=Field(...,ge=0,le=1); obscene:int=Field(...,ge=0,le=1)
 threat:int=Field(...,ge=0,le=1); insult:int=Field(...,ge=0,le=1); identity_hate:int=Field(...,ge=0,le=1)
 source:Optional[str]='text'
class DatasetPatch(BaseModel):
 comment:Optional[str]=None
 toxic:Optional[int]=Field(None,ge=0,le=1); severe_toxic:Optional[int]=Field(None,ge=0,le=1); obscene:Optional[int]=Field(None,ge=0,le=1)
 threat:Optional[int]=Field(None,ge=0,le=1); insult:Optional[int]=Field(None,ge=0,le=1); identity_hate:Optional[int]=Field(None,ge=0,le=1)
 source:Optional[str]=None
VALID_LABELS=tuple(list(LABELS)+['non_toxic'])

def now(): return datetime.now(timezone.utc).isoformat()
def db():
 c=sqlite3.connect(DB_PATH); c.row_factory=sqlite3.Row; return c
def hash_password(password,salt=None):
 salt=salt or secrets.token_hex(16); return hashlib.pbkdf2_hmac('sha256',password.encode(),salt.encode(),150000).hex(),salt
def verify_password(password,stored,salt): return secrets.compare_digest(hash_password(password,salt)[0],stored)
# ---------------------------------------------------------------------------
# AURA 4.16 — explicit administrator provisioning & credential rotation
# ---------------------------------------------------------------------------
# B17/B18 remediation. Start-up no longer seeds or rewrites credentials.
# Nothing in this block executes on import: functions are defined, not called.
DEFAULT_ADMIN_USERNAME = (os.environ.get('AURA_ADMIN_USER') or 'admin').strip()
MIN_ADMIN_PASSWORD_LENGTH = 12
# Shape-based rejection of the retired demo-style credential (InitialCaps@NNNN)
# WITHOUT retaining that literal anywhere in this file.
_WEAK_CREDENTIAL_RE = re.compile(r'^[A-Za-z]+[@!#$%]\d{3,}$')


class ProvisioningError(ValueError):
 """Raised for any refused provisioning or rotation attempt."""


def _refuse_insecure_password(password, username):
 """Reject empty, short, username-derived or legacy-shaped credentials."""
 if not isinstance(password, str) or not password:
  raise ProvisioningError('A password is required.')
 if len(password) < MIN_ADMIN_PASSWORD_LENGTH:
  raise ProvisioningError(f'Password must be at least {MIN_ADMIN_PASSWORD_LENGTH} characters.')
 if password.strip().lower() == str(username).strip().lower():
  raise ProvisioningError('Password must not equal the username.')
 if _WEAK_CREDENTIAL_RE.match(password.strip()):
  raise ProvisioningError('That password matches a retired demo-credential shape and is refused.')
 if len(set(password)) < 5:
  raise ProvisioningError('Password has too little variety.')


def provision_admin(username=None, password=None, interactive=None):
 """Create the administrator account EXPLICITLY. Never overwrites.

 Guarantees:
  - Refuses to touch an account that already exists. Changing an existing
    administrator's credential requires rotate_credential(), never this path.
  - The password is supplied interactively via getpass (not echoed, not in argv,
    not in shell history) or explicitly by the caller.
  - No default or hard-coded credential exists anywhere in this module.
  - Never logs the password, its hash or its salt.
 """
 username = (username or DEFAULT_ADMIN_USERNAME).strip()
 if not username:
  raise ProvisioningError('username is required.')
 if interactive is None:
  interactive = password is None
 if password is None:
  if not interactive:
   raise ProvisioningError('No password supplied.')
  password = getpass.getpass(f'Password for administrator "{username}": ')
  confirm = getpass.getpass('Confirm password: ')
  if not secrets.compare_digest(password.encode(), confirm.encode()):
   raise ProvisioningError('Passwords did not match.')
 _refuse_insecure_password(password, username)
 c = db()
 try:
  existing = c.execute('SELECT id FROM users WHERE lower(username)=lower(?)', (username,)).fetchone()
  if existing:
   raise ProvisioningError(f'Account {username!r} already exists; start-up and provisioning never overwrite an existing account. Use rotate_credential() to change its password.')
  h, s = hash_password(password)
  c.execute('INSERT INTO users(username,password_hash,salt,role,blocked,created_at) VALUES(?,?,?,?,?,?)',
            (username, h, s, 'admin', 0, now()))
  c.commit()
 finally:
  c.close()
 audit_log(username, 'ADMIN_PROVISIONED', {'role': 'admin', 'rows_affected': 1})
 return {'status': 'created', 'username': username, 'role': 'admin'}


def rotate_credential(username, current_password, new_password, actor=None):
 """The ONLY sanctioned way to change an existing credential.

 Requires the current password, so an unauthenticated caller cannot rotate.
 Refuses policy violations, never touches role or blocked (rotation is not
 authorisation), and audits without secret material.
 """
 username = (username or '').strip()
 if not username:
  raise ProvisioningError('username is required.')
 if not isinstance(current_password, str) or not current_password:
  raise ProvisioningError('The current password is required to rotate a credential.')
 _refuse_insecure_password(new_password, username)
 c = db()
 try:
  row = c.execute('SELECT id,password_hash,salt,role FROM users WHERE lower(username)=lower(?)', (username,)).fetchone()
  if not row:
   raise ProvisioningError(f'No such account: {username!r}.')
  if not verify_password(current_password, row['password_hash'], row['salt']):
   audit_log(actor or username, 'CREDENTIAL_ROTATION_DENIED', {'target_user_id': row['id'], 'reason': 'current_password_mismatch'})
   raise ProvisioningError('Current password is incorrect.')
  if secrets.compare_digest(current_password.encode(), new_password.encode()):
   raise ProvisioningError('The new password must differ from the current one.')
  h, s = hash_password(new_password)
  # Deliberately does NOT touch role or blocked. Bumping credential_version is
  # what invalidates every token minted before this rotation.
  cur = c.execute('UPDATE users SET password_hash=?, salt=?, credential_version=COALESCE(credential_version,0)+1 WHERE id=?', (h, s, row['id']))
  c.commit()
  result = {'status': 'rotated', 'target_user_id': row['id'], 'rows_affected': cur.rowcount}
 finally:
  c.close()
 # Rotation revokes outstanding sessions: a token captured before the rotation
 # must not survive it.
 result['sessions_revoked'] = purge_user_sessions(username)
 audit_log(actor or username, 'CREDENTIAL_ROTATION', {'target_user_id': result['target_user_id'], 'rows_affected': result['rows_affected'], 'role': row['role'], 'sessions_revoked': result['sessions_revoked']})
 return result


def _cli(argv=None):
 """Explicit operator entry point. Importing this module does NOT run it."""
 import argparse
 parser = argparse.ArgumentParser(prog='backend.py', description='AURA backend operator commands.')
 sub = parser.add_subparsers(dest='command')
 p = sub.add_parser('provision-admin', help='Create the administrator account (refuses if one already exists).')
 p.add_argument('--username', default=None, help=f'Administrator username (default: {DEFAULT_ADMIN_USERNAME}).')
 p.add_argument('--password', default=None, help='Prefer the interactive prompt; do not place secrets on the command line.')
 s = sub.add_parser('status', help='Report whether an administrator account exists (no secrets shown).')
 s.add_argument('--username', default=None)
 args = parser.parse_args(argv)
 if args.command == 'provision-admin':
  try:
   result = provision_admin(args.username, args.password, args.password is None)
  except ProvisioningError as exc:
   print(f'[provision-admin] refused: {exc}', file=sys.stderr)
   return 2
  print(f"[provision-admin] {result['status']}: user={result['username']} role={result['role']}")
  return 0
 if args.command == 'status':
  c = db()
  try:
   n = c.execute('SELECT COUNT(*) FROM users WHERE role=?', ('admin',)).fetchone()[0]
  finally:
   c.close()
  print(f'administrator accounts: {n}' + ('' if n else '  -> run `python backend.py provision-admin`'))
  return 0
 parser.print_help()
 return 1


def init_db():
 c=db(); c.executescript('''CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,username TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,salt TEXT NOT NULL,role TEXT NOT NULL DEFAULT 'user',blocked INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL);CREATE TABLE IF NOT EXISTS moderation_results(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id TEXT NOT NULL,conversation_id TEXT NOT NULL,message TEXT NOT NULL,result_json TEXT NOT NULL,created_at TEXT NOT NULL);CREATE TABLE IF NOT EXISTS audit_logs(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id TEXT,action TEXT NOT NULL,details TEXT,created_at TEXT NOT NULL);CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);CREATE TABLE IF NOT EXISTS feedback(id INTEGER PRIMARY KEY AUTOINCREMENT,prediction_id INTEGER,username TEXT NOT NULL,input_text TEXT,predicted_label TEXT,confidence REAL,categories_json TEXT,correct INTEGER NOT NULL DEFAULT 0,corrected_label TEXT,note TEXT,created_at TEXT NOT NULL);CREATE TABLE IF NOT EXISTS live_sessions(session_id TEXT PRIMARY KEY,username TEXT NOT NULL,started_at TEXT NOT NULL,ended_at TEXT,status TEXT NOT NULL DEFAULT 'active');CREATE TABLE IF NOT EXISTS live_events(id INTEGER PRIMARY KEY AUTOINCREMENT,session_id TEXT NOT NULL,transcript TEXT NOT NULL,label TEXT,confidence REAL,categories_json TEXT,elapsed_s REAL,created_at TEXT NOT NULL);CREATE TABLE IF NOT EXISTS training_runs(job_id TEXT PRIMARY KEY,status TEXT NOT NULL,config_json TEXT,started_at TEXT,finished_at TEXT,metrics_json TEXT,error TEXT);''')
 # AURA 4.16 (B17): start-up NEVER creates or rewrites credentials. The previous
 # implementation unconditionally overwrote password_hash, salt, role='admin' and
 # blocked=0 for the admin account on every service start, which silently reverted
 # any operator-chosen password, unblocked a blocked administrator and
 # re-escalated a demoted one. Provisioning is now an explicit operator action —
 # see provision_admin() and `python backend.py provision-admin`.
 admin_row=c.execute('SELECT id FROM users WHERE lower(username)=lower(?)',(DEFAULT_ADMIN_USERNAME,)).fetchone()
 if not admin_row:
  print('[startup] no administrator account present; create one explicitly with `python backend.py provision-admin`.', file=sys.stderr)
 # Safe, idempotent migration: add the prediction columns used by the newer
 # endpoints only when they are missing. Existing rows are never rewritten.
 present={row['name'] for row in c.execute('PRAGMA table_info(moderation_results)').fetchall()}
 for col,ddl in (('source',"TEXT DEFAULT 'text'"),('overall_label','TEXT'),('confidence','REAL'),('categories_json','TEXT'),('verified','INTEGER DEFAULT 0'),('language','TEXT'),('language_name','TEXT'),('processing_mode','TEXT')):
  if col not in present:
   c.execute(f'ALTER TABLE moderation_results ADD COLUMN {col} {ddl}')
 # AURA 4.17: session revocation needs a persistent credential version, and
 # login throttling needs a durable attempt counter. Both are additive, and
 # existing rows are never rewritten.
 user_cols={row['name'] for row in c.execute('PRAGMA table_info(users)').fetchall()}
 if 'credential_version' not in user_cols:
  c.execute('ALTER TABLE users ADD COLUMN credential_version INTEGER NOT NULL DEFAULT 0')
 c.execute('CREATE TABLE IF NOT EXISTS login_attempts(username TEXT PRIMARY KEY, fail_count INTEGER NOT NULL DEFAULT 0, first_fail_at TEXT, last_fail_at TEXT, locked_until TEXT)')
 c.commit(); c.close()

def _user_credential_version(c, username):
 row=c.execute('SELECT credential_version FROM users WHERE lower(username)=lower(?)',(username,)).fetchone()
 return None if row is None else int(row[0] or 0)

def purge_user_sessions(username):
 """Drop every in-memory session entry for a user. Returns the count dropped."""
 low=(username or '').strip().lower()
 dropped=0
 for t in [k for k,v in SESSIONS.items() if str(v.get('username','')).lower()==low]:
  SESSIONS.pop(t,None); dropped+=1
 return dropped

def token_for(username,role,credential_version=0):
 """Mint a session token bound to the user's credential_version.

 Binding the version is what makes revocation work: bumping
 users.credential_version (on password rotation or explicit revocation) makes
 every previously minted token fail validation, immediately and permanently.
 """
 t=hashlib.sha256(f'{username}:{role}:{int(credential_version)}:{secrets.token_hex(16)}'.encode()).hexdigest()
 SESSIONS[t]={'username':username,'role':role,'credential_version':int(credential_version),'created_at':now()}
 return t

def revoke_sessions(username, reason='manual'):
 """Persistently invalidate every live session for a user.

 Bumps users.credential_version so tokens issued before this moment can never
 be replayed - not even after a restart - then drops the in-memory entries.
 """
 username=(username or '').strip()
 c=db()
 try:
  c.execute('UPDATE users SET credential_version=COALESCE(credential_version,0)+1 WHERE lower(username)=lower(?)',(username,))
  c.commit()
  version=_user_credential_version(c,username)
 finally:
  c.close()
 dropped=purge_user_sessions(username)
 audit_log(username,'SESSIONS_REVOKED',{'reason':reason,'dropped':dropped,'credential_version':version})
 return {'dropped':dropped,'credential_version':version}

def current(auth):
 if not auth or not auth.startswith('Bearer '): raise HTTPException(401,'Authentication required.')
 token=auth.split(' ',1)[1].strip()
 u=SESSIONS.get(token)
 if not u: raise HTTPException(401,'Session expired. Please sign in again.')
 created=u.get('created_at')
 # Fail CLOSED: a session whose timestamp is missing or unparseable must be
 # rejected, never granted an unbounded lifetime.
 try:
  age=(datetime.now(timezone.utc)-datetime.fromisoformat(created)).total_seconds()
 except Exception:
  SESSIONS.pop(token,None); raise HTTPException(401,'Session expired. Please sign in again.')
 if age>SESSION_TTL_SECONDS:
  SESSIONS.pop(token,None); raise HTTPException(401,'Session expired. Please sign in again.')
 c=db()
 try:
  version=_user_credential_version(c,u['username'])
 finally:
  c.close()
 if version is None:
  SESSIONS.pop(token,None); raise HTTPException(401,'Session expired. Please sign in again.')
 if int(u.get('credential_version',0))!=int(version):
  SESSIONS.pop(token,None); raise HTTPException(401,'Session revoked. Please sign in again.')
 return u

def admin(auth):
 u=current(auth)
 if u['role']!='admin': raise HTTPException(403,'Admin access required.')
 return u

def _backoff_seconds(fail_count):
 """PROPOSED DEFAULT: 0 before 5 failures, then 30s doubling, capped at 900s."""
 if fail_count < 5: return 0
 return min(LOGIN_BACKOFF_BASE_SECONDS * (2 ** (fail_count - 5)), LOGIN_BACKOFF_MAX_SECONDS)

def is_login_locked(c, username):
 """True while the account is inside a backoff window.

 Deliberately a *delay* rather than a hard lockout: a permanent freeze would
 let any unauthenticated caller deny service to the sole administrator merely by
 triggering failed logins.
 """
 row=c.execute('SELECT locked_until FROM login_attempts WHERE lower(username)=lower(?)',(username,)).fetchone()
 if not row or not row['locked_until']: return False
 try: return datetime.now(timezone.utc) < datetime.fromisoformat(row['locked_until'])
 except Exception: return False

def prune_login_attempts(c=None, cutoff_iso=None):
 """Delete failure counters whose window has expired.

 Bounds table growth from attacker-chosen usernames: without this, every
 distinct name an attacker tries leaves a permanent row. Purely a cleanup of
 *expired* counters, so it never forgives a live failure.
 """
 own = c is None
 if own: c = db()
 try:
  if cutoff_iso is None: cutoff_iso = (datetime.now(timezone.utc)-timedelta(seconds=LOGIN_FAILURE_WINDOW_SECONDS)).isoformat()
  n = c.execute('DELETE FROM login_attempts WHERE last_fail_at IS NOT NULL AND last_fail_at < ?', (cutoff_iso,)).rowcount
  if own: c.commit()
  return n
 finally:
  if own: c.close()

def record_login_failure(username):
 """Durable per-account failure counter with an expiring window."""
 c=db()
 try:
  now_iso=now()
  row=c.execute('SELECT fail_count,first_fail_at FROM login_attempts WHERE lower(username)=lower(?)',(username,)).fetchone()
  if row and row['first_fail_at']:
   try: age=(datetime.now(timezone.utc)-datetime.fromisoformat(row['first_fail_at'])).total_seconds()
   except Exception: age=None
   if age is not None and age>LOGIN_FAILURE_WINDOW_SECONDS: row=None
  count=(row['fail_count'] if row else 0)+1
  delay=_backoff_seconds(count)
  locked=(datetime.now(timezone.utc)+timedelta(seconds=delay)).isoformat() if delay else None
  first=row['first_fail_at'] if row else now_iso
  c.execute('INSERT INTO login_attempts(username,fail_count,first_fail_at,last_fail_at,locked_until) VALUES(?,?,?,?,?) ON CONFLICT(username) DO UPDATE SET fail_count=excluded.fail_count,first_fail_at=excluded.first_fail_at,last_fail_at=excluded.last_fail_at,locked_until=excluded.locked_until',(username,count,first,now_iso,locked))
  # Opportunistically bound table growth from attacker-chosen usernames.
  c.execute('DELETE FROM login_attempts WHERE last_fail_at IS NOT NULL AND last_fail_at < ?',((datetime.now(timezone.utc)-timedelta(seconds=LOGIN_FAILURE_WINDOW_SECONDS)).isoformat(),))
  c.commit()
  return {'fail_count':count,'locked_seconds':delay}
 finally:
  c.close()

def clear_login_failures(username):
 c=db()
 try:
  c.execute('DELETE FROM login_attempts WHERE lower(username)=lower(?)',(username,))
  c.commit()
 finally:
  c.close()
def lang(text):
    scripts={
        'Tamil': r'[\u0B80-\u0BFF]', 'Telugu': r'[\u0C00-\u0C7F]',
        'Kannada': r'[\u0C80-\u0CFF]', 'Malayalam': r'[\u0D00-\u0D7F]',
        'Hindi': r'[\u0900-\u097F]', 'Bengali': r'[\u0980-\u09FF]'
    }
    counts={k:len(re.findall(v,text)) for k,v in scripts.items()}
    found=[k for k,v in counts.items() if v]
    latin=len(re.findall(r'[A-Za-z]',text))
    if len(found)==1:
        return found[0] + (' + English' if latin else '')
    if len(found)>1:
        return 'Mixed Indian Languages' + (' + English' if latin else '')
    low=norm(text)
    roman_markers={
      'Tamil':['muttal','moodan','kevalam','kevalamanavan','asingam','paithiyam','savu','seththu','unnai','po tholai'],
      'Telugu':['pichivadu','murkhudu','vedhava','chachipo','ninnu','dengu'],
      'Kannada':['huchcha','moorkha','dadda','saayu','ninnannu','hogu'],
      'Malayalam':['mandan','viddhi','bhranthan','chaavu','ninne','upadravikkum'],
      'Hindi':['bewakoof','moorkh','gadha','pagal','nalayak','mar ja','tumhe','dhundhunga'],
      'Bengali':['boka','murkho','gadha','pagol','more jao','tomake','khujе']
    }
    scores={k:sum(1 for m in ms if m in low) for k,ms in roman_markers.items()}
    best=max(scores,key=scores.get) if scores else 'English'
    return best if scores.get(best,0)>0 else 'English'

def norm(s):
    # Normalize whitespace and common punctuation; preserve native Unicode.
    s=s.lower().replace('’',"'").replace('“','"').replace('”','"')
    return re.sub(r'\s+',' ',s).strip()

def hits(text,terms):
    low=norm(text)
    # Word/phrase matching for Latin text plus direct Unicode phrase matching.
    out=[]
    for x in terms:
        term=norm(x)
        if not term: continue
        if re.search(r'[a-z0-9]',term):
            if re.search(r'(?<![a-z0-9])'+re.escape(term)+r'(?![a-z0-9])',low): out.append(x)
        elif term in low:
            out.append(x)
    return out

# WARN calibration: only mild insults/toxicity are lowered into the WARN band.
# Strong profanity, threats, identity hate and severe toxicity keep their existing rules.
MILD_TERMS = {
    'stupid','idiot','dumb','fool','jerk','clown','silly','annoying','rude','disrespectful',
    'முட்டாள்','மூடன்','அறிவில்லாத'
}
MILD_TOXIC_SCORE = 42.0
MILD_INSULT_SCORE = 45.0

# RESTRICT calibration: explicit repeated/targeted harassment is restricted even
# when individual insult words are mild. This is isolated from other decisions.
RESTRICT_PATTERNS = (
    # English
    r'\brepeatedly\b.*\b(target|targeting|targeted|harass|harassing|harassed|insult|insulting|attack|attacking)\b',
    r'\b(keep|keeps|kept|continue|continues|continued)\b.*\b(target|targeting|harass|harassing|insult|insulting|attack|attacking)\b',
    r'\b(every|multiple|several)\b.*\b(conversation|discussion|discussions|post|posts|message|messages)\b.*\b(target|targeting|harass|harassing|insult|insulting)\b',
    r'\basked\b.*\bstop\b.*\b(continue|continues|continued|keep|keeps|kept)\b.*\b(harass|harassing|target|targeting|insult|insulting)\b',
    r'\b(stop|leave me alone)\b.*\b(harass|harassing|target|targeting)\b.*\b(again|again and again|repeatedly)\b',
    # Tamil / Tanglish
    r'(தொடர்ந்து|மீண்டும் மீண்டும்|ஒவ்வொரு).*(குறிவைத்து|துன்புறுத்தி|அவமதித்து|தாக்கி)',
    r'(நிறுத்தச் சொன்ன|நிறுத்த சொன்ன|விட்டுவிடச் சொன்ன).*(தொடர்ந்து|மீண்டும்).*(துன்புறுத்த|அவமதிக்க|குறிவைக்க)',
    r'\b(continue|keep|repeatedly|again and again)\b.*\b(harass|target|insult)\b.*\b(ennai|unnai)\b',
    # Telugu / Tenglish
    r'(ప్రతిసారి|మళ్లీ మళ్లీ|తరచుగా).*(లక్ష్యంగా|వేధిస్తూ|అవమానిస్తూ|దాడి)',
    r'\b(pratisari|malli malli|tarachuga)\b.*\b(target|vedhistu|avamanistu|harass)\b',
    # Kannada / Kanglish
    r'(ಪ್ರತಿ ಬಾರಿ|ಮತ್ತೆ ಮತ್ತೆ|ಪದೇ ಪದೇ).*(ಗುರಿಯಾಗಿಸಿ|ಕಿರುಕುಳ|ಅವಮಾನಿಸಿ|ದಾಳಿ)',
    r'\b(prati bari|matte matte|pade pade)\b.*\b(target|kirukula|avamana|harass)\b',
    # Malayalam / Manglish
    r'(എപ്പോഴും|വീണ്ടും വീണ്ടും|തുടർച്ചയായി).*(ലക്ഷ്യമാക്കി|ഉപദ്രവിച്ച്|അപമാനിച്ച്|ആക്രമിച്ച്)',
    r'\b(eppozhum|veendum veendum|thudarccayayi)\b.*\b(target|upadrav|apaman|harass)\b',
    # Hindi / Hinglish
    r'(बार बार|लगातार|हर बातचीत).*(निशाना|परेशान|अपमान|हमला)',
    r'\b(bar bar|lagatar|har baat)\b.*\b(target|pareshan|apman|harass)\b',
    # Bengali / Banglish
    r'(বার বার|বারবার|প্রতিবার|ক্রমাগত).*(লক্ষ্য|হয়রানি|অপমান|আক্রমণ)',
    r'\b(bar bar|barbar|protibar|kromagoto)\b.*\b(target|hoyrani|opoman|harass)\b',
)

# ---------------------------------------------------------------------------
# Multilingual decision calibration
# ---------------------------------------------------------------------------
# The English rules above are intentionally left unchanged.  These rules add
# high-precision phrase coverage for Indian-script languages and their common
# Romanized/mixed forms.  They are decision cues, not a claim of model training.
MULTI_DECISION_PATTERNS = {
    'WARN': [
        # Tamil
        r'(நீ|நீங்கள்).*(முட்டாள்|மூடன்|முட்டாளே)',
        r'\bnee\b.*\b(muttal|moodan|muttale)\b',
        # Telugu
        r'(నువ్వు|నీవు).*(మూర్ఖుడు|మూర్ఖుడివి|వెధవ|వెధవా|వెధవుడివి|దద్దమ్మ)',
        r'\b(nuvvu|neevu)\b.*\b(murkhudu|murkhudivi|vedhava|vedhavodivi|daddamma)\b',
        # Kannada
        r'(ನೀನು|ನೀವು).*(ಮೂರ್ಖ|ದಡ್ಡ|ಬೇವಕೂಫ್)',
        r'\b(neenu|neevu)\b.*\b(moorkha|dadda|bevakuf)\b',
        # Malayalam
        r'(നീ|നിങ്ങൾ).*(മണ്ടൻ|മണ്ടനാണ്|വിഡ്ഢി|വിഡ്ഢിയാണ്|പൊട്ടൻ|പൊട്ടനാണ്)',
        r'\b(nee|ningal)\b.*\b(mandan|mandananu|viddhi|viddhiyanu|pottan|pottananu)\b',
        # Hindi
        r'(तुम|आप).*(बेवकूफ|मूर्ख|गधा|नालायक)',
        r'\b(tum|aap)\b.*\b(bewakoof|moorkh|gadha|nalayak)\b',
        # Bengali
        r'(তুমি|আপনি).*(বোকা|মূর্খ|গাধা)',
        r'\b(tumi|apni)\b.*\b(boka|murkho|gadha)\b',
    ],
    'QUARANTINE': [
        # Tamil
        r'(கேவலமானவன்|கேவலமானவள்|அசிங்கமானவன்|அசிங்கமானவள்|தேவடியா|புண்டை|பொறுக்கி|போய் தொலை)',
        r'\b(romba|miga|migavum)?\s*(kevalama|asingama)\s*(pesura|irukka|irukkiya)\b',
        r'\b(kevalamanavan|asingamanavan|thevadiya|pundai|porukki)\b',
        # Telugu
        r'(దరిద్రం|దెంగు|దెంగేయ్|చెత్త|నీచుడు|దరిద్రుడు|అసహ్యంగా)',
        r'\b(chala|chaala)\b.*\b(disgusting|daridram|dengu|chetta|asahyam|asahyanga)\b',
        r'\b(daridram|dengu|denga|chetta)\b',
        # Kannada
        r'(ಕೊಳಕು|ಅಸಹ್ಯ|ನೀಚ|ಕೆಟ್ಟವನು)',
        r'\b(tumba|thumba)\b.*\b(asahya|kolaku|neech)\b',
        r'\b(asahya|asahya|asahyakar|kolaku|neech)\b',
        # Malayalam
        r'(വൃത്തികെട്ടവൻ|വൃത്തികെട്ടവനാണ്|വൃത്തികെട്ടവൾ|തെറി|മൈര്|മൈരേ|അശ്ലീലം)',
        r'\b(valare)\b.*\b(disgusting|vrithikettavan|vrithikettavananu|vrithikettavanan|myre)\b',
        r'\b(vrithikettavan|myre|theri)\b',
        # Hindi
        r'(भोसड़ी|चूत|भाड़ में जाओ|गंदी गाली|घटिया|जघन्य)',
        r'\b(bahut)\b.*\b(disgusting|ghatiya|bhosdi|choot)\b',
        r'\b(bhosdi|choot|ghatiya|ghatiya|bakwaas)\b',
        # Bengali
        r'(চোদা|চোদ|নোংরা|জঘন্য গালি|গালাগালি)',
        r'\b(choda|chod|nongra|joghonyo)\b',
        # Strong mixed profanity
        r'\b(fucking|fuck|shit)\b.*\b(kevalam|asingam|daridram|disgusting|ghatiya|myre)\b',
    ],
    'RESTRICT': [
        # Tamil / Tanglish
        r'(தொடர்ந்து|மீண்டும் மீண்டும்|பதிலுக்கு பதில்|ஒவ்வொரு முறையும்).*(துன்புறுத்த|அவமதிக்க|குறிவைக்க|தாக்க)',
        r'(என்னை|உன்னை).*(தொடர்ந்து|மீண்டும் மீண்டும்).*(துன்புறுத்த|அவமதிக்க|குறிவைக்க)',
        r'\b(nee|neenga)\b.*\b(ennai|enna|unnai|unna)\b.*\b(thodarnthu|meendum meendum|thodarchiyaga)\b.*\b(harass|target|insult|torture|panra|seyyura)\b',
        r'\b(thodarnthu|meendum meendum|thodarchiyaga)\b.*\b(ennai|enna|unnai|unna)\b.*\b(harass|target|insult|panra|seyyura)\b',
        # Telugu / Tenglish
        r'(ప్రతిసారి|మళ్లీ మళ్లీ|పదే పదే|తరచుగా).*(వేధ|అవమాన|లక్ష్య|దాడి)',
        r'(నన్ను|నిన్ను).*(మళ్లీ మళ్లీ|తరచుగా).*(వేధ|అవమాన|లక్ష్య)',
        r'\b(nuvvu|neevu)\b.*\b(nannu|ninnu)\b.*\b(malli malli|padhe padhe|tarachuga)\b.*\b(vedhi|vedhistu|harass|target|insult)\w*\b',
        r'\b(malli malli|padhe padhe|tarachuga)\b.*\b(nannu|ninnu)\b.*\b(harass|target|insult)\w*\b',
        # Kannada / Kanglish
        r'(ಪ್ರತಿ ಬಾರಿ|ಮತ್ತೆ ಮತ್ತೆ|ಪದೇ ಪದೇ|ನಿರಂತರವಾಗಿ).*(ಕಿರುಕುಳ|ಅವಮಾನ|ಗುರಿ|ದಾಳಿ)',
        r'(ನನ್ನನ್ನು|ನಿನ್ನನ್ನು).*(ಮತ್ತೆ ಮತ್ತೆ|ಪದೇ ಪದೇ).*(ಕಿರುಕುಳ|ಅವಮಾನ|ಗುರಿ)',
        r'\b(neenu|neevu)\b.*\b(nannannu|ninnannu)\b.*\b(matte matte|pade pade|nirantaravagi)\b.*\b(kirukula|harass|target|insult)\w*\b',
        # Malayalam / Manglish
        r'(വീണ്ടും വീണ്ടും|തുടർച്ചയായി|എപ്പോഴും).*(ഉപദ്രവ|അപമാന|ലക്ഷ്യമാക്കി|ആക്രമ)',
        r'(എന്നെ|നിന്നെ).*(വീണ്ടും വീണ്ടും|തുടർച്ചയായി).*(ഉപദ്രവ|അപമാന|ലക്ഷ്യ)',
        r'\b(nee|ningal)\b.*\b(enne|ninne)\b.*\b(veendum veendum|thudarccayayi|eppozhum)\b.*\b(upadrav|harass|target|insult)\w*\b',
        # Hindi / Hinglish
        r'(बार बार|बार-बार|लगातार|हर बार).*(परेशान|अपमान|निशाना|हमला)',
        r'(मुझे|तुम्हें).*(बार बार|लगातार).*(परेशान|अपमान|निशाना)',
        r'\b(tum|aap)\b.*\b(mujhe|tumhe)\b.*\b(bar bar|baar baar|lagatar|har baar)\b.*\b(pareshan|harass|target|insult)\w*\b',
        r'\b(tum|aap)\b.*\b(mujhe|mujhko|tumhe)\b.*\b(bar bar|baar baar|barbar|lagatar|har baar)\b.*\b(pareshan|harass|target|insult)\w*\b',
        r'\b(tumi|apni)\b.*\b(amake|tomake)\b.*\b(bar bar|barbar|protibar|kromagoto)\b.*\b(harass|target|insult)\w*\b',
        # Bengali / Banglish
        r'(বার বার|বারবার|প্রতিবার|ক্রমাগত).*(হয়রানি|অপমান|লক্ষ্য|আক্রমণ)',
        r'\b(tumi|apni)\b.*\b(amake|tomake)\b.*\b(bar bar|barbar|protibar|kromagoto)\b.*\b(harass|target|insult)\w*\b',
    ],
    'TEMPORARY_BLOCK': [
        # Native-script direct threats
        r'(நான்|நீ).*(காயப்படுத்துவேன்|கொன்றுவிடுவேன்|கொல்வேன்|தாக்குவேன்|அடிப்பேன்)',
        r'(నేను|నువ్వు).*(గాయపరుస్తాను|చంపుతాను|కొడతాను|దాడి చేస్తాను)',
        r'(ನಾನು|ನೀನು).*(ಗಾಯಗೊಳಿಸುತ್ತೇನೆ|ಕೊಲ್ಲುತ್ತೇನೆ|ಹೊಡೆಯುತ್ತೇನೆ|ದಾಳಿ ಮಾಡುತ್ತೇನೆ)',
        r'(ഞാൻ|നീ).*(പരിക്കേൽപ്പിക്കും|കൊല്ലും|അടിക്കും|ആക്രമിക്കും)',
        r'(मैं|तुम).*(मार दूंगा|मार दूँगा|चोट पहुँचाऊंगा|हमला करूंगा|पीटूंगा)',
        r'(আমি|তুমি).*(মেরে ফেলব|আঘাত করব|মারব|হামলা করব)',
        # Romanized
        r'\b(naan|nenu|nanu|njān|main|ami)\b.*\b(unnai|ninnu|ninnannu|ninne|tumhe|tomake)\b.*\b(kayapaduththuven|champuthanu|gayagolisuttene|kollum|maar dunga|hurt|kill|attack|marbo)\b',
        r'\b(i will|i am going to)\b.*\b(hurt|kill|attack|beat)\b',
    ],
    'HUMAN_REVIEW': [
        # Ambiguous, consequential but non-explicit statements
        r'(ஏதாவது|ஏதோ).*(நடக்கலாம்|நடக்கும்|நடக்குமோ)',
        r'(இப்படியே|தொடர்ந்தால்).*(ஏதாவது|ஏதோ).*(நடக்கலாம்|நடக்கும்)',
        r'\b(edhavadhu|edho)\b.*\b(nadakkalam|nadakkum|nadakkumo)\b',
        r'(ఏదైనా|ఏదో).*(జరగొచ్చు|జరగవచ్చు|జరుగుతుంది)',
        r'\b(edaina|edo)\b.*\b(jaragochu|jaragavachu|jarugutundi)\b',
        r'(ಏನಾದರೂ|ಏನೋ).*(ಆಗಬಹುದು|ನಡೆಯಬಹುದು|ನಡೆಯುತ್ತದೆ)',
        r'\b(enadaru|eno)\b.*\b(agabahudu|nadeyabahudu|nadeyutte)\b',
        r'(എന്തെങ്കിലും|എന്തോ).*(സംഭവിക്കാം|സംഭവിക്കും)',
        r'\b(enthenkilum|entho)\b.*\b(sambhavikkam|sambhavikkum)\b',
        r'(ശായദ്|शायद|कुछ).*(हो सकता है|होगा|हो जाए)',
        r'\b(shayad|kuch)\b.*\b(ho sakta hai|hoga|ho jaye)\b',
        r'(হয়তো|কিছু).*(ঘটতে পারে|হবে)',
        r'\b(hoyto|kichu)\b.*\b(ghotbe|hobe|ghot te pare)\b',
    ],
}

def multilingual_decision(text):
    """Return a high-confidence non-English decision cue, if present."""
    t=norm(text)
    # Do not alter the already-working English-only behaviour.
    native_scripts = bool(re.search(r'[\u0900-\u0DFF]', t))
    roman_markers = (
        'muttal','moodan','kevalam','kevalama','kevalamanavan','asingam','thodarnthu','meendum meendum',
        'ennai','unnai','harass','thodarchiyaga',
        'vedhava','pichivadu','nuvvu','nannu','ninnu','malli malli','tarachuga','asahya','disgusting',
        'moorkha','dadda','neenu','nannannu','ninnannu','matte matte','pade pade',
        'mandan','mandananu','viddhi','nee','enne','ninne','veendum veendum','thudarccayayi','valare',
        'bewakoof','moorkh','gadha','ghatiya','tum','mujhe','tumhe','bar bar','baar baar','lagatar',
        'boka','murkho','gadha','tumi','amake','tomake','barbar'
    )
    if not native_scripts and not any(m in t for m in roman_markers):
        return None
    for decision in ('TEMPORARY_BLOCK','RESTRICT','QUARANTINE','WARN','HUMAN_REVIEW'):
        if any(re.search(p,t) for p in MULTI_DECISION_PATTERNS[decision]):
            return decision
    return None

def classify(text):
    found={}; scores={x:0.0 for x in LABELS}
    base={'toxic':72,'severe_toxic':92,'obscene':82,'threat':98,'insult':78,'identity_hate':88}
    low=norm(text)
    for label in LABELS:
        h=hits(text,LEX[label])
        if not h:
            continue
        found[label]=h
        if label in {'toxic','insult'} and all(term.lower() in MILD_TERMS for term in h):
            scores[label]=min(100.0, (MILD_TOXIC_SCORE if label=='toxic' else MILD_INSULT_SCORE) + max(0,len(h)-1)*3)
        else:
            scores[label]=min(100.0,base[label]+max(0,len(h)-1)*4)
    return scores,found

def is_ambiguous_for_review(text, scores):
    # Human review is reserved for vague statements that imply a possible
    # consequence but do not contain an explicit harmful signal.
    if max(scores.values()) > 0:
        return False
    t=norm(text)
    ambiguous_patterns=(
        # English
        r'\bmaybe\b.*\b(happen|happens|something|consequence|result)\b',
        r'\b(might|could|may|probably)\b.*\b(happen|happens|something|consequence|result)\b',
        r'\b(something|something bad)\b.*\b(will|might|could|may)\b',
        r'\b(we\s+will\s+see|you\s+will\s+see)\s+what\s+happens\b',
        # Tamil / Tanglish
        r'(ஏதாவது|ஏதோ).*(நடக்கலாம்|நடக்கும்|நடக்குமோ)',
        r'(இப்படியே|தொடர்ந்தால்).*(ஏதாவது|ஏதோ).*(நடக்கலாம்|நடக்கும்)',
        r'(இப்படி தொடர்ந்தால்).*(ஏதாவது).*(நடக்கும்)',
        r'\b(edhavadhu|edho).*(nadakkalam|nadakkum)',
        r'\b(ipadiye|thodarnthal).*(edhavadhu|edho).*(nadakkalam|nadakkum)',
        # Telugu / Tenglish
        r'(ఏదైనా|ఏదో).*(జరగొచ్చు|జరుగుతుంది)',
        r'(ఇలాగే|కొనసాగితే).*(ఏదైనా|ఏదో).*(జరగొచ్చు)',
        r'\b(edaina|edo).*(jaragochu|jarugutundi)',
        # Kannada / Kanglish
        r'(ಏನಾದರೂ|ಏನೋ).*(ಆಗಬಹುದು|ನಡೆಯಬಹುದು|ನಡೆಯುತ್ತದೆ)',
        r'\b(enadaru|eno).*(agabahudu|nadeyabahudu|nadeyutte)',
        # Malayalam / Manglish
        r'(എന്തെങ്കിലും|എന്തോ).*(സംഭവിക്കാം|സംഭവിക്കും)',
        r'\b(enthenkilum|entho).*(sambhavikkam|sambhavikkum)',
        # Hindi / Hinglish
        r'(शायद|कुछ).*(हो सकता है|होगा|हो जाए)',
        r'(ऐसा ही चलता रहा|जारी रहा).*(कुछ|कुछ न कुछ).*(हो सकता है|होगा)',
        r'\b(shayad|kuch).*(ho sakta hai|hoga|ho jaye)',
        r'\b(tum|aap)\b.*\b(mujhe|mujhko|tumhe)\b.*\b(bar bar|baar baar|barbar|lagatar|har baar)\b.*\b(pareshan|harass|target|insult)\w*\b',
        r'\b(tumi|apni)\b.*\b(amake|tomake)\b.*\b(bar bar|barbar|protibar|kromagoto)\b.*\b(harass|target|insult)\w*\b',
        # Bengali / Banglish
        r'(হয়তো|কিছু).*(ঘটতে পারে|হবে)',
        r'\b(hoyto|kichu).*(ghot te pare|ghotbe|hobe)',
    )
    return any(re.search(p,t) for p in ambiguous_patterns)

def analyse(req):
 text=req.get_text(); ctx=req.get_context(); language=lang(text); scores,found=classify(text)
 multilingual_cue=multilingual_decision(text)
 if multilingual_cue:
  # Raise only the corresponding signal enough to land in its intended band.
  if multilingual_cue=='WARN':
   scores['toxic']=max(scores['toxic'],42.0); scores['insult']=max(scores['insult'],45.0)
  elif multilingual_cue=='QUARANTINE':
   scores['toxic']=max(scores['toxic'],72.0); scores['obscene']=max(scores['obscene'],82.0)
  elif multilingual_cue=='RESTRICT':
   scores['toxic']=max(scores['toxic'],72.0); scores['insult']=max(scores['insult'],78.0)
  elif multilingual_cue=='TEMPORARY_BLOCK':
   scores['threat']=max(scores['threat'],98.0)
  elif multilingual_cue=='HUMAN_REVIEW':
   scores={k:0.0 for k in LABELS}; found={}
 positive=hits(text,POS)
 if positive and not found: scores={x:0.0 for x in LABELS}
 repeated=sum(norm(x)==norm(text) for x in ctx)
 previous=sum(bool(hits(x,LEX['threat']) or hits(x,LEX['insult'])) for x in ctx)
 behaviour=min(100.0,previous*35+max(0,len(ctx)-5)*4)
 harassment=90.0 if scores['threat']>0 else (82.0 if scores['insult']>0 and previous else (60.0 if previous else 0.0))
 escalation=min(100.0,harassment+len(ctx)*2)
 safety=max(scores.values())
 confidence=96.0 if safety>=90 else (93.0 if safety>0 else (86.0 if len(text.split())<=2 else 91.0)); confidence-=2.0 if language=='Tamil + English' else 0
 context=min(100.0,repeated*35.0)
 score=safety*.72+context*.06+behaviour*.08+harassment*.10+escalation*.04
 if safety==0: score=min(14.0,context*.15+behaviour*.10)
 restrict_match=any(re.search(p, norm(text)) for p in RESTRICT_PATTERNS)
 if restrict_match: score=max(score,76.0)
 if multilingual_cue=='HUMAN_REVIEW': decision=('HUMAN_REVIEW','Human Review','Uncertain')
 elif multilingual_cue=='TEMPORARY_BLOCK': decision=('TEMPORARY_BLOCK','Temporary Block','Critical')
 elif multilingual_cue=='RESTRICT': decision=('RESTRICT','Restrict','High')
 elif multilingual_cue=='QUARANTINE': decision=('QUARANTINE','Quarantine','High')
 elif multilingual_cue=='WARN': decision=('WARN','Warn','Medium')
 elif is_ambiguous_for_review(text, scores): decision=('HUMAN_REVIEW','Human Review','Uncertain')
 elif scores['threat']>=90 or scores['severe_toxic']>=90: decision=('TEMPORARY_BLOCK','Temporary Block','Critical')
 elif restrict_match or scores['identity_hate']>=85 or score>=75: decision=('RESTRICT','Restrict','High')
 elif score>=55: decision=('QUARANTINE','Quarantine','High')
 elif score>=30: decision=('WARN','Warn','Medium')
 else: decision=('ALLOW','Allow','Safe' if score==0 else 'Low')
 action,label,rlevel=decision
 evidence=[f'{k.replace("_"," ").title()}: {v:.1f}%' for k,v in sorted(scores.items(),key=lambda x:x[1],reverse=True) if v>0][:3] or ['No harmful safety signal detected.']
 action_public = {'ALLOW':'ALLOW','WARN':'WARN','QUARANTINE':'QUARANTINE','RESTRICT':'RESTRICT','TEMPORARY_BLOCK':'TEMPORARY_BLOCK','HUMAN_REVIEW':'HUMAN_REVIEW'}[action]
 probabilities={k:round(v,1) for k,v in scores.items()}
 confidence_data={'confidence':round(max(0,confidence),1),'uncertainty':round(100-max(0,confidence),1)}
 return {'language':language,'classification':scores,'classification_matches':found,'context_analysis':{'message_count':len(ctx),'repeated_current_message':repeated>0,'context_risk':round(context,1)},'behavioural_analysis':{'previous_violations':previous,'recent_frequency':len(ctx),'behavioural_risk':round(behaviour,1)},'harassment_escalation':{'harassment_risk':round(harassment,1),'escalation_risk':round(escalation,1),'repeated_targeting':bool(previous)},'behaviour':{'risk':round(behaviour,1),'previous_violations':previous,'recent_frequency':len(ctx)},'harassment_analysis':{'harassment_risk':round(harassment,1),'escalation_risk':round(escalation,1),'repeated_targeting':bool(previous)},'escalation_analysis':{'risk':round(escalation,1)},'confidence_uncertainty':{'confidence':round(max(0,confidence),1),'uncertainty':round(100-max(0,confidence),1),'uncertain':False},'risk':{'score':round(min(100,score),1),'overall':round(min(100,score),1),'context':round(context,1),'behavioural':round(behaviour,1),'harassment':round(harassment,1),'escalation':round(escalation,1),'confidence':round(max(0,confidence),1)},'risk_score':round(min(100,score),1),'risk_level':rlevel,'decision':{'action':action,'label':label,'risk_level':rlevel},'moderation':{'action':action,'label':label,'risk_level':rlevel},'action':action,'probabilities':probabilities,'confidence':round(max(0,confidence),1),'uncertainty':round(100-max(0,confidence),1),'xai':{'important_evidence':'; '.join(evidence),'summary':f'AURA selected {label} from safety signals, context, behaviour and confidence.','reason':'No harmful signal was detected, so the comment can be posted.' if action=='ALLOW' else ('A direct threat or severe harmful signal was detected, so the account action is strengthened.' if action=='TEMPORARY_BLOCK' else f'The combined risk score is {score:.1f}/100, leading to {label}.')},'explainable_ai':{'important_evidence':'; '.join(evidence),'summary':f'AURA selected {label} from safety signals, context, behaviour and confidence.','reason':'No harmful signal was detected, so the comment can be posted.' if action=='ALLOW' else ('A direct threat or severe harmful signal was detected, so the account action is strengthened.' if action=='TEMPORARY_BLOCK' else f'The combined risk score is {score:.1f}/100, leading to {label}.')}}

def result(req,model_cache=None):
 if not req.get_text(): raise HTTPException(400,'Please enter a comment before running the safety check.')
 r=analyse(req); r=apply_language_engine(r,req.get_text(),model_cache); action=r['decision']['action']; r.update({'message_id':hashlib.sha256(f'{req.user_id}|{req.conversation_id}|{req.get_text()}'.encode()).hexdigest()[:16],'user_id':req.user_id,'conversation_id':req.conversation_id,'original_message':req.get_text(),'preprocessed_message':req.get_text(),'publication':{'status':'POSTED' if action=='ALLOW' else ('HUMAN_REVIEW' if action=='HUMAN_REVIEW' else 'NOT_POSTED'),'posted':action=='ALLOW','flagged':action not in {'ALLOW','HUMAN_REVIEW'},'needs_human':action=='HUMAN_REVIEW'},'created_at':now()}); return r

# ---------------------------------------------------------------------------
# Shared prediction pipeline: /moderate, /predict, /predict/batch,
# /voice/predict and /live/chunk all run through run_engine() so the rule
# engine, threshold handling and persistence are implemented exactly once.
# ---------------------------------------------------------------------------
def ml_module():
 global ml_service
 if ml_service is None:
  try:
   import ml_service as _ml
   ml_service=_ml
  except Exception:
   return None
 return ml_service

def ml_fn(name):
 m=ml_module(); fn=getattr(m,name,None) if m is not None else None
 return fn if callable(fn) else None

def require_ml(*names):
 m=ml_module()
 if m is None: raise HTTPException(503,'ML service (ml_service) is unavailable.')
 for n in names:
  if not callable(getattr(m,n,None)): raise HTTPException(503,f'ML service (ml_service) does not provide {n}().')
 return m

def get_threshold():
 # Toxicity threshold (0..1) stored in the settings table; 0.5 is the default.
 try:
  c=db(); row=c.execute("SELECT value FROM settings WHERE key='toxicity_threshold'").fetchone(); c.close()
  if row is not None and row['value'] is not None: return max(0.0,min(1.0,float(row['value'])))
 except Exception:
  pass
 return 0.5

def set_threshold(value):
 v=max(0.0,min(1.0,float(value)))
 c=db()
 try:
  c.execute("CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT)")
  c.execute("INSERT INTO settings(key,value) VALUES('toxicity_threshold',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(str(v),))
  c.commit()
 except Exception:
  c.rollback(); c.close(); raise
 c.close(); return v

def categories_from(scores):
 cats={}
 for k in LABELS:
  try: val=float((scores or {}).get(k,0) or 0)
  except (TypeError,ValueError): val=0.0
  cats[k]=round(max(0.0,min(100.0,val))/100.0,4)
 cats['non_toxic']=round(max(0.0,1.0-cats.get('toxic',0.0)),4)
 return cats

def toxic_terms_from(matches):
 out=[]
 for k in LABELS:
  for t in (matches or {}).get(k) or []:
   s=str(t).strip()
   if s and s not in out: out.append(s)
 return out

def derived_overall(risk_score,threshold):
 try: risk=float(risk_score or 0)
 except (TypeError,ValueError): risk=0.0
 return 'toxic' if (risk/100.0)>=threshold else 'non_toxic'

def load_result_json(raw):
 try:
  d=json.loads(raw) if raw else {}
  return d if isinstance(d,dict) else {}
 except Exception: return {}

def row_overall(stored,res,threshold):
 if stored: return stored
 if isinstance(res,dict) and res.get('overall_label'): return str(res['overall_label'])
 return derived_overall(res.get('risk_score') if isinstance(res,dict) else 0,threshold)

def row_confidence(stored,res):
 if stored is not None:
  try: return round(max(0.0,min(1.0,float(stored))),4)
  except (TypeError,ValueError): pass
 try: val=float((res or {}).get('confidence') or 0)
 except (TypeError,ValueError): val=0.0
 return round(max(0.0,min(1.0,val/100.0)),4)

def row_categories(stored_json,res):
 if stored_json:
  try:
   d=json.loads(stored_json)
   if isinstance(d,dict) and d: return d
  except Exception: pass
 return categories_from((res or {}).get('classification'))

def store_moderation(username,conversation_id,message,r,source,overall,conf1,cats):
 cols=['user_id','conversation_id','message','result_json','created_at','source','overall_label','confidence','categories_json','language','language_name','processing_mode']
 vals=[username,conversation_id,message,json.dumps(r,ensure_ascii=False),r['created_at'],source,overall,conf1,json.dumps(cats,ensure_ascii=False),r.get('language_code'),r.get('language_name'),r.get('processing_mode')]
 c=db()
 try:
  present={row['name'] for row in c.execute('PRAGMA table_info(moderation_results)').fetchall()}
  use=[(cl,v) for cl,v in zip(cols,vals) if cl in present]
  sql='INSERT INTO moderation_results ('+', '.join(cl for cl,_ in use)+') VALUES ('+', '.join('?' for _ in use)+')'
  cur=c.execute(sql,[v for _,v in use])
  mid=cur.lastrowid
  c.execute('INSERT INTO audit_logs(user_id,action,details,created_at) VALUES(?,?,?,?)',(username,'MODERATION_DECISION',json.dumps({'moderation_id':mid,'decision':r['decision']}),now()))
  c.commit()
 except Exception:
  c.rollback(); c.close(); raise
 c.close(); return mid

# ---------------------------------------------------------------------------
# Multilingual pipeline
# ---------------------------------------------------------------------------
# mlexicon.detect() tells us which language/script the comment uses.  Three
# processing modes follow from it:
#   existing_model  - English: the original AURA rule engine, unchanged.
#   language_lexicon- supported non-English language with a data/lexicons file.
#   fallback        - detected but unsupported (or undetectable): conservative
#                     neutral scores, never a fabricated precision.
SUPPORTED_LEX_LANGUAGES=('ta','ta-Latn','hi','te','ml','kn','bn','mr','gu','pa','ur')
LANG_NAMES={'en':'English','ta':'Tamil','ta-Latn':'Tanglish','hi':'Hindi','te':'Telugu','ml':'Malayalam','kn':'Kannada','bn':'Bengali','mr':'Marathi','gu':'Gujarati','pa':'Punjabi','ur':'Urdu','und':'Unknown'}
LANG_SCRIPTS={'en':'Latin','ta':'Tamil','ta-Latn':'Latin','hi':'Devanagari','te':'Telugu','ml':'Malayalam','kn':'Kannada','bn':'Bengali','mr':'Devanagari','gu':'Gujarati','pa':'Gurmukhi','ur':'Arabic','und':'Unknown'}
SCRIPT_NAMES={'Latin','Tamil','Devanagari','Telugu','Malayalam','Kannada','Bengali','Gujarati','Gurmukhi','Arabic','Mixed','Unknown'}
# Fallback mapping used only when the mlexicon module itself is unavailable.
NAME_TO_CODE={'English':'en','Tamil':'ta','Tamil + English':'ta','Tanglish':'ta-Latn','Hindi':'hi','Hindi + English':'hi','Telugu':'te','Telugu + English':'te','Malayalam':'ml','Malayalam + English':'ml','Kannada':'kn','Kannada + English':'kn','Bengali':'bn','Bengali + English':'bn','Marathi':'mr','Gujarati':'gu','Punjabi':'pa','Urdu':'ur'}

def detect_language(text):
 """Return {'code','name','script'} for one comment (heuristic detection)."""
 mod=mlexicon
 if mod is not None:
  try:
   info=mod.detect(text)
  except Exception:
   info=None
  if isinstance(info,dict) and info.get('code'):
   code=str(info.get('code'))
   if code not in LANG_NAMES: code='und'
   script=str(info.get('script') or '')
   if script not in SCRIPT_NAMES: script='Unknown'
   # The shared API exposes "Unknown" for every undetectable/mixed input;
   # "Mixed" survives through the script field.
   name='Unknown' if code=='und' else LANG_NAMES[code]
   if code!='und': script=LANG_SCRIPTS.get(code,script)
   return {'code':code,'name':name,'script':script}
 # Conservative fallback: reuse the original script detector.
 legacy=lang(text)
 if legacy.startswith('Mixed'):
  return {'code':'und','name':'Unknown','script':'Mixed'}
 base=NAME_TO_CODE.get(legacy.split(' + ')[0].strip())
 if not base:
  return {'code':'und','name':'Unknown','script':'Unknown'}
 return {'code':base,'name':LANG_NAMES.get(base,'Unknown'),'script':LANG_SCRIPTS.get(base,'Unknown')}

def apply_lexicon_result(r,text,code,name):
 """Re-score the response from the language lexicon (heuristic, 0..1 terms)."""
 mod=mlexicon
 try:
  m=mod.match(text,code) or {}
 except Exception:
  m={}
 raw=m.get('category_scores') or {}
 matched=[str(t) for t in (m.get('matched_terms') or [])]
 try:
  lex=(mod.load_lexicons().get(code) or {}).get('categories') or {}
 except Exception:
  lex={}
 matched_set=set(matched)
 classification={k:0.0 for k in LABELS}
 matches={}
 for k in LABELS:
  try: val=float(raw.get(k,0) or 0)
  except (TypeError,ValueError): val=0.0
  classification[k]=round(max(0.0,min(1.0,val))*100.0,1)
  terms=[t for t in (lex.get(k) or []) if t in matched_set]
  if terms: matches[k]=terms
 active=[k for k in LABELS if matches.get(k)]
 risk=round(max(float(classification.get(k,0.0)) for k in ('toxic','insult','threat','obscene','severe_toxic')),1)
 if 'threat' in active or 'severe_toxic' in active: action,label,rlevel='TEMPORARY_BLOCK','Temporary Block','Critical'
 elif 'identity_hate' in active: action,label,rlevel='RESTRICT','Restrict','High'
 elif 'obscene' in active or len(active)>=2: action,label,rlevel='QUARANTINE','Quarantine','High'
 elif active: action,label,rlevel='WARN','Warn','Medium'
 else: action,label,rlevel='ALLOW','Allow','Safe' if risk<=0 else 'Low'
 if matched:
  evidence=', '.join(matched[:3])
  reason=f'Language lexicon matched: {", ".join(matched[:6])} ({name} safety lexicon, heuristic, not a calibrated model).'
 else:
  evidence=f'No {name} lexicon term matched'
  reason=f'No {name} safety lexicon term matched this comment, so the score stays neutral (lexicon-based heuristic, not a calibrated model).'
 summary=f'AURA selected {label} from the {name} safety lexicon (lexicon-based heuristic, not a calibrated model).'
 r['classification']=classification
 r['classification_matches']=matches
 r['probabilities']={k:classification[k] for k in LABELS}
 r['risk_score']=risk
 if isinstance(r.get('risk'),dict):
  r['risk']['score']=risk; r['risk']['overall']=risk
 r['risk_level']=rlevel
 r['decision']={'action':action,'label':label,'risk_level':rlevel}
 r['moderation']={'action':action,'label':label,'risk_level':rlevel}
 r['action']=action
 xai={'important_evidence':evidence,'summary':summary,'reason':reason}
 r['xai']=xai
 r['explainable_ai']=dict(xai)
 return r

def apply_fallback_result(r,code,name,script):
 """Conservative neutral scores for detected-but-unsupported languages."""
 classification={k:0.0 for k in LABELS}
 classification['toxic']=5.0
 r['classification']=classification
 r['classification_matches']={}
 r['probabilities']={k:classification[k] for k in LABELS}
 r['risk_score']=5.0
 if isinstance(r.get('risk'),dict):
  r['risk']['score']=5.0; r['risk']['overall']=5.0
 r['risk_level']='Low'
 r['decision']={'action':'ALLOW','label':'Allow','risk_level':'Low'}
 r['moderation']={'action':'ALLOW','label':'Allow','risk_level':'Low'}
 r['action']='ALLOW'
 reason=(f'Limited language support: {name} (script {script}) was detected but no safety lexicon is available for it, '
         'so AURA used a conservative fallback with neutral scores (heuristic, not a calibrated model).')
 xai={'important_evidence':f'Language: {name} | script: {script} | fallback path',
      'summary':'AURA kept the score neutral because this language is not covered by a safety lexicon yet.',
      'reason':reason}
 r['xai']=xai
 r['explainable_ai']=dict(xai)
 return r

def apply_language_engine(r,text,model_cache=None):
 """Attach language metadata and, when needed, re-score from the lexicon."""
 det=detect_language(text)
 code=det['code']; name=det['name']; script=det['script']
 r['language_code']=code
 r['language_name']=name
 r['language']=name          # legacy key held a NAME; keep it a NAME.
 r['script']=script
 r['confidence_kind']='heuristic'
 # language_confidence is a deterministic script-share heuristic (NOT a
 # probability); Latin-script languages and und return None + explicit kind.
 lc,lck=language_confidence_for(text,code,script)
 r['language_confidence']=lc
 r['language_confidence_kind']=lck
 mode=None
 if model_selected(code):
  # Pretrained model overlay: on adapter failure apply_model_result leaves the
  # analyse() result untouched, records decision_status='fallback' + a
  # sanitised model_error, and we continue into the legacy path below.
  if apply_model_result(r,text,code,name,script,model_cache):
   mode='pretrained_model'
   r['confidence_kind']='model'
 if mode is None:
  if code=='en' or (code=='und' and script=='Latin'):
   # Phase 4.1 (C-F-2): unsupported Latin-script text is now honestly
   # reported as language 'und'/'Unknown', but it is still scored by the
   # default (English) safety lexicon that analyse() already applied.
   # Sending it to the neutral fallback instead silently downgraded known
   # toxic terms ("idiot") to a neutral ALLOW - a protection regression
   # caught by tests_word_input. C-F-2 asked us to stop faking the language
   # disclosure, not to weaken the scoring; non-Latin 'und' still uses the
   # conservative neutral fallback below.
   mode='existing_model'
  else:
   available=False
   if code in SUPPORTED_LEX_LANGUAGES and mlexicon is not None:
    try: available=bool(mlexicon.lexicon_available(code))
    except Exception: available=False
   if available:
    mode='language_lexicon'
    apply_lexicon_result(r,text,code,name)
   else:
    mode='fallback'
    apply_fallback_result(r,code,name,script)
 r['processing_mode']=mode
 try: risk=float(r.get('risk_score') or 0)
 except (TypeError,ValueError): risk=0.0
 r['score']=round(max(0.0,min(100.0,risk))/100.0,4)
 return r

# ---------------------------------------------------------------------------
# Phase 2 — pretrained model engine (opt-in).  The legacy engine stays the
# default; the model only decides when AURA_PREDICTION_ENGINE (env) or the
# admin 'prediction_engine' setting selects it, and only for languages the
# engine gate allows.  Every adapter failure falls back to the legacy result
# with an explicit decision_status='fallback' — never a stack trace.
# ---------------------------------------------------------------------------
def engine_mode_info():
 """Effective prediction engine as (mode, source).

 Precedence: settings table 'prediction_engine' (admin, persisted) >
 AURA_PREDICTION_ENGINE env (deployment switch) > 'legacy'.
 The chosen value is mirrored into the process env so
 model_adapter.engine_mode()/should_try_model() stay in sync.
 """
 v=None; src='default'
 try:
  c=db(); row=c.execute("SELECT value FROM settings WHERE key='prediction_engine'").fetchone(); c.close()
  if row is not None and row['value'] and str(row['value']).strip().lower() in ENGINE_MODES:
   v=str(row['value']).strip().lower(); src='settings'
 except Exception:
  pass
 if v is None:
  env=(os.environ.get('AURA_PREDICTION_ENGINE') or '').strip().lower()
  if env in ENGINE_MODES: v=env; src='env'
 if v is None: v=ENGINE_DEFAULT
 os.environ['AURA_PREDICTION_ENGINE']=v
 return v,src

def engine_mode():
 """Effective prediction engine (see engine_mode_info for precedence)."""
 return engine_mode_info()[0]

def audit_log(user_id, action, details):
 """Best-effort audit_logs row using the table's existing schema/conventions.

 Columns (identical to every other audit write in this file):
   user_id   - actor username, NULL when unknown
   action    - SCREAMING_SNAKE action name
   details   - json.dumps(...) payload
   created_at- now() (UTC ISO-8601)
 Never raises: an audit write must not change API behaviour."""
 c=None
 try:
  c=db(); c.execute('INSERT INTO audit_logs(user_id,action,details,created_at) VALUES(?,?,?,?)',(user_id,action,json.dumps(details),now())); c.commit(); c.close()
 except Exception as e:
  if c is not None:
   try: c.close()
   except Exception: pass
  print(f'[audit] failed to write {action} row: {type(e).__name__}: {e}', file=sys.stderr)

def set_engine(mode, actor=None):
 """Persist the engine choice (settings row) and mirror it into the env.

 Writes EXACTLY ONE audit_logs row per change attempt (C-F-6) recording the
 previous engine, requested engine, resulting engine, actor and success flag.
 A failed change is never recorded as a success."""
 prev=engine_mode()
 v=str(mode or '').strip().lower()
 if v not in ENGINE_MODES:
  audit_log(actor,'ENGINE_CHANGE',{'previous_engine':prev,'requested_engine':v,'resulting_engine':prev,'success':False,'error':'unsupported engine'})
  raise HTTPException(400,'Unsupported prediction engine. Expected one of: '+', '.join(ENGINE_MODES)+'.')
 c=db()
 try:
  c.execute("CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT)")
  c.execute("INSERT INTO settings(key,value) VALUES('prediction_engine',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(v,))
  c.commit()
 except Exception as e:
  c.rollback(); c.close()
  audit_log(actor,'ENGINE_CHANGE',{'previous_engine':prev,'requested_engine':v,'resulting_engine':engine_mode(),'success':False,'error':f'{type(e).__name__}: {e}'[:200]})
  raise
 c.close()
 os.environ['AURA_PREDICTION_ENGINE']=v
 audit_log(actor,'ENGINE_CHANGE',{'previous_engine':prev,'requested_engine':v,'resulting_engine':v,'success':True})
 return v

def model_selected(code):
 """True when the configured engine should decide this language.

 Delegates the language gate to model_adapter.should_try_model() (legacy ->
 never; hf -> always; auto -> only languages AURA measured or the model card
 claims).  engine_mode() has already mirrored the choice into the env, so the
 adapter and the backend always agree on one source of truth."""
 if model_adapter is None: return False
 if engine_mode()=='legacy': return False
 try:
  return bool(model_adapter.should_try_model(code))
 except Exception:
  return False

_SCRIPT_RANGES={'ta':(0x0B80,0x0BFF),'hi':(0x0900,0x097F),'mr':(0x0900,0x097F),'bn':(0x0980,0x09FF),'ur':(0x0600,0x06FF),'te':(0x0C00,0x0C7F),'ml':(0x0D00,0x0D7F),'kn':(0x0C80,0x0CFF),'gu':(0x0A80,0x0AFF),'pa':(0x0A00,0x0A7F)}

def language_confidence_for(text,code,script):
 """Deterministic script-share heuristic (0..1): fraction of alphabetic chars
 written in the detected language's native script.  This is NOT a calibrated
 probability.  Latin-script inputs (en, ta-Latn) cannot be confirmed by script
 and unknown/mixed text has no signal, so those return None with an explicit
 kind instead of a fabricated number."""
 letters=[ch for ch in text if ch.isalpha()]
 if not letters: return None,'no_signal'
 if code=='und': return None,'no_signal'
 if script=='Latin': return None,'script_ambiguous'
 rng=_SCRIPT_RANGES.get(code) or _SCRIPT_RANGES.get(code.split('-')[0])
 if not rng: return None,'no_signal'
 lo,hi=rng
 inside=sum(1 for ch in letters if lo<=ord(ch)<=hi)
 return round(inside/len(letters),4),'script_share'

def _mask_paths(msg):
 """Mask local filesystem paths and flatten to one safe line."""
 msg=str(msg) or ''
 msg=re.sub(r'[A-Za-z]:\\[^\s\'"]+','<path>',msg)          # C:\...
 msg=re.sub(r'/(?:home|usr|var|tmp|Users|opt)[^\s\'"]*','<path>',msg)
 msg=msg.splitlines()[0] if msg.splitlines() else msg
 msg=re.sub(r'\s+',' ',msg).strip()
 return msg

def _safe_model_error(e):
 """One-line error text for API clients: exception type + message, local
 filesystem paths masked, never a stack trace (single line only)."""
 msg=_mask_paths(e)
 return (f'{type(e).__name__}: {msg}' if msg else type(e).__name__)[:200]

def _safe_adapter_info(info):
 """Adapter info safe for API responses: mask any path in `error` and drop
 internal fields (cache location) that clients never need."""
 if not isinstance(info,dict): return {'status':'unknown'}
 info=dict(info)
 if info.get('error'):
  info['error']=_mask_paths(info['error'])[:200] or None
 info.pop('cache_dir',None)
 return info

def apply_model_result(r,text,code,name,script,model_cache=None):
 """Score `text` with the pretrained model and overlay the decision on `r`.

 Returns True when the model produced the decision.  On ANY adapter failure
 the legacy result already computed for `r` stands untouched and only
 decision_status='fallback' (plus a sanitised model_error) is recorded, so a
 missing/broken model degrades cleanly instead of erroring the request.
 `model_cache` (batch path) maps text -> a pre-computed predict() payload.
 """
 if model_adapter is None:
  r['decision_status']='fallback'
  r['model_error']='model adapter unavailable (module not loaded)'
  return False
 try:
  out=None
  if model_cache is not None:
   out=model_cache.get(text)
  if out is None:
   out=model_adapter.ADAPTER.predict([text])
  scores=(out.get('scores') or [{}])[0] or {}
  # per-language decision threshold (tuned on validation) beats the global one
  per=out.get('per_language_thresholds') or {}
  thr=per.get(code)
  if thr is None: thr=per.get(code.split('-')[0])
  if thr is None: thr=float(out.get('threshold') or 0.5)
  thr=float(thr)
  dec=model_adapter.categorise(scores,thr)
  cov_status,cov_note=model_adapter.coverage_for(code)
 except Exception as e:
  r['decision_status']='fallback'
  r['model_error']=_safe_model_error(e)
  return False
 tox=float(dec.get('toxicity_score') or 0.0)
 classification={k:0.0 for k in LABELS}
 for ml,al in model_adapter.MODEL_LABEL_MAP.items():
  try: classification[al]=round(min(100.0,max(0.0,float(scores.get(ml,0.0))*100.0)),1)
  except (TypeError,ValueError): classification[al]=0.0
 risk=round(tox*100.0,1)
 r['classification']=classification
 # keep only term matches whose category the model also flags (>= threshold)
 r['classification_matches']={k:v for k,v in (r.get('classification_matches') or {}).items() if float(classification.get(k,0.0))>=thr*100.0}
 r['probabilities']={k:classification[k] for k in LABELS}
 r['risk_score']=risk
 if isinstance(r.get('risk'),dict):
  r['risk']['score']=risk; r['risk']['overall']=risk
 # decision ladder mirrors the legacy engine's bands, on the model's scores
 if classification['threat']>=90.0 or classification['severe_toxic']>=90.0:
  action,label,rlevel='TEMPORARY_BLOCK','Temporary Block','Critical'
 elif classification['identity_hate']>=85.0 or risk>=75.0:
  action,label,rlevel='RESTRICT','Restrict','High'
 elif risk>=55.0: action,label,rlevel='QUARANTINE','Quarantine','High'
 elif risk>=30.0: action,label,rlevel='WARN','Warn','Medium'
 else: action,label,rlevel='ALLOW','Allow','Safe' if risk<=0 else 'Low'
 # explicit uncertainty / coverage honesty: never present a guess as definitive
 margin=abs(tox-thr)
 status='predicted'
 if margin<0.05: status='uncertain'
 if cov_status in ('unmeasured','model_card_claimed'): status='experimental'
 if status=='experimental':
  action,label,rlevel='HUMAN_REVIEW','Human Review','Uncertain'
 elif status=='uncertain' and action not in ('RESTRICT','TEMPORARY_BLOCK'):
  action,label,rlevel='HUMAN_REVIEW','Human Review','Uncertain'
 r['risk_level']=rlevel
 r['decision']={'action':action,'label':label,'risk_level':rlevel}
 r['moderation']={'action':action,'label':label,'risk_level':rlevel}
 r['action']=action
 # model confidence = the model's own conviction on the binary decision
 conf=round(max(tox,1.0-tox)*100.0,1)
 r['confidence']=conf
 r['uncertainty']=round(100.0-conf,1)
 if isinstance(r.get('confidence_uncertainty'),dict):
  r['confidence_uncertainty']={'confidence':conf,'uncertainty':round(100.0-conf,1),'uncertain':status!='predicted'}
 r['confidence_kind']='model'
 # xai straight from the model's sigmoid heads
 flagged=[f'{k}: {classification[k]:.1f}%' for k in LABELS if classification[k]>=thr*100.0]
 evidence=', '.join(flagged[:3]) if flagged else 'No model category above threshold.'
 reason=f'Model toxicity score {tox:.3f} vs threshold {thr:.2f} ({code}, {cov_status} coverage).'
 if status=='uncertain': reason+=' Score is within 0.05 of the threshold, so the decision is uncertain.'
 if status=='experimental': reason+=' This language is not independently validated for this model, so the decision is routed to human review.'
 summary=f'AURA selected {label} from {out.get("model_id")} (multilingual toxicity model, sigmoid multi-label heads).'
 xai={'important_evidence':evidence,'summary':summary,'reason':reason}
 r['xai']=xai
 r['explainable_ai']=dict(xai)
 # prediction contract fields
 r['label']=dec.get('label') or 'non_toxic'
 r['toxicity_score']=round(tox,4)
 r['threshold']=round(thr,4)
 r['model_name']=out.get('model_id')
 r['model_version']=out.get('model_version')
 r['decision_status']=status
 r['model_coverage']=cov_status
 r['model_coverage_note']=cov_note
 r['model_categories']=dec.get('categories') or {}
 r['model_latency_ms']=out.get('latency_ms')
 return True

def row_language(row,res):
 """Null-safe (language code, language name, processing mode) for one row."""
 code=None; name=None; mode=None
 try:
  keys=row.keys()
 except Exception:
  keys=[]
 try:
  if 'language' in keys: code=row['language'] or None
  if 'language_name' in keys: name=row['language_name'] or None
  if 'processing_mode' in keys: mode=row['processing_mode'] or None
 except Exception:
  pass
 if not code: code=res.get('language_code') or None
 if not code:
  legacy=res.get('language')
  if legacy: code=NAME_TO_CODE.get(str(legacy))
 if not name: name=res.get('language_name') or None
 if not name and code: name=LANG_NAMES.get(str(code))
 if not mode: mode=res.get('processing_mode') or None
 return code,name,mode

def run_engine(req,source='text',model_cache=None):
 """Evaluate one comment, persist it, and return (result, extras)."""
 r=result(req,model_cache)
 src=source if source in SOURCES else 'text'
 # decision threshold: the model overlay sets its own tuned per-language
 # threshold on r['threshold']; otherwise the admin-configured one applies.
 thr=r.get('threshold')
 if not isinstance(thr,(int,float)): thr=get_threshold()
 thr=max(0.0,min(1.0,float(thr)))
 # model mode: reuse the model's own label (exact score-vs-threshold comparison);
 # legacy: derive from the (possibly rounded) risk score as before.
 if r.get('decision_status') in ('predicted','uncertain','experimental') and r.get('label') in ('toxic','non_toxic'):
  overall=r['label']
 else:
  overall=derived_overall(r.get('risk_score'),thr)
 try: conf1=round(max(0.0,min(1.0,float(r.get('confidence') or 0)/100.0)),4)
 except (TypeError,ValueError): conf1=0.0
 cats=categories_from(r.get('classification'))
 r['text']=req.get_text()
 r['source']=src
 r['overall_label']=overall
 r['label']=overall          # prediction-contract alias of overall_label
 r['categories']=cats
 r['toxic_terms']=toxic_terms_from(r.get('classification_matches'))
 r['highlighting_method']='heuristic'
 r.setdefault('confidence_kind','heuristic')
 r.setdefault('model_name','aura-legacy-rules-lexicon')
 r.setdefault('model_version',app.version)
 r.setdefault('decision_status','legacy')
 r.setdefault('threshold',thr)
 try: r['score']=round(max(0.0,min(100.0,float(r.get('risk_score') or 0)))/100.0,4)
 except (TypeError,ValueError): r['score']=0.0
 mid=store_moderation(req.user_id,req.conversation_id,req.get_text(),r,src,overall,conf1,cats)
 r['moderation_id']=mid
 return r,{'prediction_id':mid,'confidence':conf1}

def check_source(source):
 src=source or 'text'
 if isinstance(src,str): src=src.strip().lower()
 if src not in SOURCES: raise HTTPException(400,'Unsupported source. Expected one of: '+', '.join(SOURCES)+'.')
 return src

@app.on_event('startup')
def startup():
 init_db()
 # Phase 2: warm the pretrained model in the background when it is the
 # configured engine (or explicitly requested) so the first request does not
 # pay the full cold load cost. A failure here is silent — the request path
 # falls back to the legacy engine with decision_status='fallback'.
 try:
  if model_adapter is not None and (os.environ.get('AURA_MODEL_EAGER_LOAD','0')=='1' or engine_mode()!='legacy'):
   def _warm_model():
    try: model_adapter.ADAPTER.predict(['warm up'])
    except Exception: pass
   threading.Thread(target=_warm_model,daemon=True).start()
 except Exception:
  pass
@app.get('/')
def root(): return {'name':'AURA','status':'online','version':app.version}
@app.get('/health')
def health(): return {'status':'healthy','service':'aura-backend'}
@app.post('/auth/login')
def login(req:LoginIn):
 username=(req.username or '').strip()
 # Throttling is checked BEFORE credential verification so a locked-out caller
 # cannot burn PBKDF2 CPU, and the response is byte-identical to every other
 # failure so it does not reveal whether the account exists.
 c=db()
 try:
  row=c.execute('SELECT * FROM users WHERE lower(username)=lower(?)',(username,)).fetchone()
  throttled=is_login_locked(c,username)
 finally:
  c.close()
 if throttled:
  audit_log(username,'LOGIN_FAILED',{'reason':'throttled'})
  raise HTTPException(401,'Invalid credentials.')
 expected_role=req.role or ('admin' if username.lower()=='admin' else 'user')
 if not row or row['blocked'] or row['role']!=expected_role or not verify_password(req.password,row['password_hash'],row['salt']):
  reason=('unknown_user' if not row else 'blocked' if row['blocked'] else 'role_mismatch' if row['role']!=expected_role else 'bad_password')
  record_login_failure(username)
  # Counts and a machine-readable reason only - never the attempted password.
  audit_log(username,'LOGIN_FAILED',{'reason':reason})
  raise HTTPException(401,'Invalid credentials.')
 clear_login_failures(username)
 version=int(row['credential_version'] or 0) if 'credential_version' in row.keys() else 0
 tok=token_for(row['username'],row['role'],version)
 audit_log(row['username'],'LOGIN_SUCCESS',{'role':row['role']})
 return {'token':tok,'access_token':tok,'user':{'id':row['id'],'username':row['username'],'role':row['role']}}
@app.post('/auth/register')
def register(req:RegisterIn):
 u=req.username.strip()
 if len(u)<3: raise HTTPException(400,'Username must contain at least 3 characters.')
 if len(req.password)<6: raise HTTPException(400,'Password must contain at least 6 characters.')
 h,s=hash_password(req.password); c=db()
 try: c.execute('INSERT INTO users(username,password_hash,salt,role,created_at) VALUES(?,?,?,?,?)',(u,h,s,'user',now())); c.commit()
 except sqlite3.IntegrityError: c.close(); raise HTTPException(409,'Username already exists.')
 c.close(); tok=token_for(u,'user'); return {'message':'Account created successfully.','access_token':tok,'token':tok,'user':{'username':u,'role':'user'}}
@app.post('/moderate')
def moderate(req:MessageIn,authorization:Optional[str]=Header(default=None)):
 u=current(authorization); req.user_id=u['username']; src=check_source(req.source); r,_=run_engine(req,src); return r
@app.get('/history')
def history(authorization:Optional[str]=Header(default=None),q:Optional[str]=None,label:Optional[str]=None,category:Optional[str]=None,source:Optional[str]=None,language:Optional[str]=None,from_date:Optional[str]=None,to_date:Optional[str]=None,min_conf:Optional[float]=None,max_conf:Optional[float]=None,limit:int=50):
 u=current(authorization)
 VALID_LANG_CODES=('en','ta','ta-Latn','hi','te','ml','kn','bn','mr','gu','pa','ur','und')
 if label is not None and label!='' and label not in ('toxic','non_toxic'): raise HTTPException(400,'Unsupported label filter. Use toxic or non_toxic.')
 if category is not None and category!='' and category not in VALID_LABELS: raise HTTPException(400,'Unsupported category filter.')
 if source is not None and source!='' and source not in SOURCES: raise HTTPException(400,'Unsupported source filter.')
 if language is not None and language!='' and language not in VALID_LANG_CODES: raise HTTPException(400,'Unsupported language filter.')
 if limit<1 or limit>1000: raise HTTPException(400,'limit must be between 1 and 1000.')
 if min_conf is not None: min_conf=max(0.0,min(1.0,float(min_conf)))
 if max_conf is not None: max_conf=max(0.0,min(1.0,float(max_conf)))
 if min_conf is not None and max_conf is not None and min_conf>max_conf: raise HTTPException(400,'min_conf cannot be greater than max_conf.')
 def _date_bound(value, end_of_day):
  try:
   dt=datetime.fromisoformat(str(value).replace('Z','+00:00'))
  except Exception:
   try: dt=datetime.strptime(str(value)[:10],'%Y-%m-%d')
   except Exception: raise HTTPException(400,'Dates must be ISO formatted, for example 2026-01-31.')
  if len(str(value))<=10 and end_of_day: dt=dt+timedelta(days=1)
  return dt.isoformat()
 thr=get_threshold()
 c=db()
 present={row['name'] for row in c.execute('PRAGMA table_info(moderation_results)').fetchall()}
 lang_cols=[cl for cl in ('language','language_name','processing_mode') if cl in present]
 sql='SELECT id,conversation_id,message,result_json,created_at,source,overall_label,confidence,categories_json'
 if lang_cols: sql+=','+','.join(lang_cols)
 sql+=' FROM moderation_results WHERE user_id=?'
 params=[u['username']]
 if q is not None and str(q).strip():
  sql+=' AND message LIKE ?'; params.append('%'+str(q).strip()+'%')
 if from_date: sql+=' AND created_at>=?'; params.append(_date_bound(from_date,False))
 if to_date: sql+=' AND created_at<?'; params.append(_date_bound(to_date,True))
 sql+=' ORDER BY id DESC'
 rows=c.execute(sql,params).fetchall(); c.close()
 out=[]
 for row in rows:
  res=load_result_json(row['result_json'])
  lang_code,lang_name,lang_mode=row_language(row,res)
  src=row['source'] or res.get('source') or 'text'
  if source and src!=source: continue
  if language and lang_code!=language: continue
  overall=row_overall(row['overall_label'],res,thr)
  if label and overall!=label: continue
  cats=row_categories(row['categories_json'],res)
  if category and float(cats.get(category,0) or 0)<0.5: continue
  conf=row_confidence(row['confidence'],res)
  if min_conf is not None and conf<min_conf: continue
  if max_conf is not None and conf>max_conf: continue
  out.append({'id':row['id'],'conversation_id':row['conversation_id'],'message':row['message'],'result':res,'created_at':row['created_at'],'source':src,'overall_label':overall,'confidence':conf,'categories':cats,'language':lang_name,'language_code':lang_code,'language_name':lang_name,'processing_mode':lang_mode})
  if len(out)>=limit: break
 return out
@app.get('/comments/me')
def comments_me(authorization:Optional[str]=Header(default=None)):
 u=current(authorization); c=db(); rows=c.execute('SELECT id,message,result_json,created_at FROM moderation_results WHERE user_id=? ORDER BY id DESC LIMIT 50',(u['username'],)).fetchall(); c.close()
 out=[]
 for r in rows:
  x=json.loads(r['result_json']); out.append({'id':r['id'],'text':r['message'],'action':x['decision']['action'],'status':x['publication']['status'],'risk_score':x['risk_score'],'created_at':r['created_at']})
 return out

@app.get('/admin/overview')
def admin_overview(authorization:Optional[str]=Header(default=None)):
 admin(authorization)
 c=db(); users_rows=c.execute('SELECT id,username,role,blocked,created_at FROM users ORDER BY id').fetchall(); event_rows=c.execute('SELECT id,user_id,message,result_json,created_at FROM moderation_results ORDER BY id DESC LIMIT 100').fetchall(); c.close()
 events=[{'moderation_id':r['id'],'user_id':r['user_id'],'message':r['message'],'result':json.loads(r['result_json']),'created_at':r['created_at']} for r in event_rows]
 pending=sum(1 for e in events if e['result'].get('publication',{}).get('needs_human'))
 return {'users':[dict(r) for r in users_rows],'events':events,'pending_human_reviews':pending}

def admin_rows():
 c=db(); rows=c.execute('SELECT id,user_id,message,result_json,created_at FROM moderation_results ORDER BY id DESC LIMIT 100').fetchall(); c.close(); return [{'moderation_id':r['id'],'user_id':r['user_id'],'message':r['message'],'result':json.loads(r['result_json']),'created_at':r['created_at']} for r in rows]
@app.get('/admin/comments')
def comments(authorization:Optional[str]=Header(default=None)): admin(authorization); return admin_rows()
@app.get('/admin/human-review')
def review(authorization:Optional[str]=Header(default=None)): admin(authorization); return [x for x in admin_rows() if x['result']['publication']['needs_human']]
@app.post('/admin/human-review/{mid}')
def human(mid:int,req:HumanDecisionIn,authorization:Optional[str]=Header(default=None)):
 a=admin(authorization); d=req.decision.upper(); c=db(); row=c.execute('SELECT result_json FROM moderation_results WHERE id=?',(mid,)).fetchone()
 if not row: c.close(); raise HTTPException(404,'Moderation item not found.')
 r=json.loads(row['result_json'])
 if d=='APPROVE': r['decision']={'action':'ALLOW','label':'Allow','risk_level':r['risk_level']}; r['publication']={'status':'POSTED','posted':True,'flagged':False,'needs_human':False}
 elif d=='RESTRICT': r['decision']={'action':'RESTRICT','label':'Restrict','risk_level':'High'}; r['publication']={'status':'NOT_POSTED','posted':False,'flagged':True,'needs_human':False}
 elif d in {'REJECT','BLOCK','DISMISS'}: r['decision']={'action':'TEMPORARY_BLOCK' if d=='BLOCK' else 'QUARANTINE','label':'Temporary Block' if d=='BLOCK' else 'Quarantine','risk_level':'Critical' if d=='BLOCK' else r['risk_level']}; r['publication']={'status':'NOT_POSTED','posted':False,'flagged':True,'needs_human':False}
 else: c.close(); raise HTTPException(400,'Unsupported human-review decision.')
 cur=c.execute('UPDATE moderation_results SET result_json=? WHERE id=?',(json.dumps(r,ensure_ascii=False),mid))
 if cur.rowcount != 1:
  c.rollback(); c.close(); raise HTTPException(500,'Unable to save the human-review decision.')
 c.execute('INSERT INTO audit_logs(user_id,action,details,created_at) VALUES(?,?,?,?)',(a['username'],'HUMAN_REVIEW',json.dumps({'moderation_id':mid,'decision':d}),now()))
 c.commit(); c.close(); return {'message':'Human decision saved.','moderation_id':mid,'result':r}
@app.get('/admin/users')
def users(authorization:Optional[str]=Header(default=None)):
 admin(authorization); c=db(); rows=c.execute('SELECT id,username,role,blocked,created_at FROM users ORDER BY id').fetchall(); c.close(); return [dict(r) for r in rows]
@app.post('/admin/block-user')
def block(req:BlockIn,authorization:Optional[str]=Header(default=None)):
 a=admin(authorization); u=req.username.strip()
 if u.lower()=='admin': raise HTTPException(400,'The admin account cannot be blocked.')
 c=db(); cur=c.execute('UPDATE users SET blocked=1 WHERE lower(username)=lower(?)',(u,));
 if cur.rowcount==0: c.close(); raise HTTPException(404,'User not found.')
 c.execute('INSERT INTO audit_logs(user_id,action,details,created_at) VALUES(?,?,?,?)',(a['username'],'BLOCK_USER',json.dumps({'username':u}),now())); c.commit(); c.close(); return {'message':f'User {u} blocked.'}

# ---------------------------------------------------------------------------
# Shared helpers for the upgraded API surface
# ---------------------------------------------------------------------------
def _jsonable(v):
 if v is None or isinstance(v,(str,int,float,bool)): return v
 if isinstance(v,dict): return {str(k):_jsonable(x) for k,x in v.items()}
 if isinstance(v,(list,tuple)): return [_jsonable(x) for x in v]
 try: return float(v)
 except Exception: return str(v)

def _ml_error(exc,msg):
 if isinstance(exc,KeyError): return HTTPException(404,'Dataset sample not found.')
 if isinstance(exc,ValueError): return HTTPException(400,str(exc))
 return HTTPException(500,f'{msg}: {exc}')

# ---------------------------------------------------------------------------
# 1) Predictions — /predict and /predict/batch
# ---------------------------------------------------------------------------
@app.post('/predict')
def predict(req:MessageIn,authorization:Optional[str]=Header(default=None)):
 u=current(authorization); req.user_id=u['username']; src=check_source(req.source)
 r,extra=run_engine(req,src)
 r['prediction_id']=extra['prediction_id']; r['confidence']=extra['confidence']
 return r

@app.post('/predict/batch')
def predict_batch(req:BatchIn,authorization:Optional[str]=Header(default=None)):
 u=current(authorization)
 if req.source not in (None,'','batch'): check_source(req.source)
 if not req.comments: raise HTTPException(400,'Provide at least one comment to analyse.')
 if len(req.comments)>500: raise HTTPException(400,'A batch can contain at most 500 comments.')
 # Phase 2: when the model engine is active, score the whole batch in ONE
 # adapter call and reuse per-comment results (never load/predict per comment).
 model_cache=None
 if model_adapter is not None and engine_mode()!='legacy':
  try:
   texts=[str(raw if raw is not None else '').strip() for raw in req.comments]
   texts=[t for t in texts if t]
   if texts:
    out=model_adapter.ADAPTER.predict(texts)
    rows=out.get('scores') or []
    model_cache={t:{**out,'scores':[row]} for t,row in zip(texts,rows)}
  except Exception:
   model_cache=None  # per-comment path will retry once and fall back cleanly
 results=[]
 for idx,raw in enumerate(req.comments):
  text=str(raw if raw is not None else '').strip()
  if not text: raise HTTPException(400,f'Comment {idx+1} in the batch is empty.')
  msg=MessageIn(text=text,user_id=u['username'],conversation_id='batch',source='batch')
  r,extra=run_engine(msg,'batch',model_cache)
  results.append({'comment':text,'text':r.get('text') or text,'language':r.get('language_name'),'language_code':r.get('language_code'),'language_name':r.get('language_name'),'script':r.get('script'),'processing_mode':r.get('processing_mode'),'confidence_kind':r.get('confidence_kind','heuristic'),'score':r.get('score'),'prediction_id':extra['prediction_id'],'overall_label':r['overall_label'],'label':r.get('label'),'confidence':extra['confidence'],'categories':r['categories'],'threshold':r.get('threshold'),'toxicity_score':r.get('toxicity_score'),'decision_status':r.get('decision_status','legacy'),'model_name':r.get('model_name'),'model_version':r.get('model_version'),'model_coverage':r.get('model_coverage'),'model_coverage_note':r.get('model_coverage_note'),'language_confidence':r.get('language_confidence'),'language_confidence_kind':r.get('language_confidence_kind'),'decision':r.get('decision'),'created_at':r['created_at']})
 return {'count':len(results),'results':results}

# ---------------------------------------------------------------------------
# 4) Analytics
# ---------------------------------------------------------------------------
@app.get('/analytics')
def analytics(authorization:Optional[str]=Header(default=None)):
 current(authorization)
 thr=get_threshold()
 c=db()
 lang_col='language' if 'language' in {r['name'] for r in c.execute('PRAGMA table_info(moderation_results)').fetchall()} else None
 rows=c.execute('SELECT result_json,created_at,source,overall_label,categories_json'+(',language' if lang_col else '')+' FROM moderation_results').fetchall()
 fb=c.execute('SELECT correct FROM feedback').fetchall()
 c.close()
 total=len(rows); toxic=0; non_toxic=0
 cat_dist={k:0 for k in LABELS}; daily={}; src_dist={k:0 for k in SOURCES}; decisions={}; lang_dist={}
 for row in rows:
  res=load_result_json(row['result_json'])
  lang_code,_,_=row_language(row,res)
  lang_key=lang_code if lang_code else 'und'
  lang_dist[lang_key]=lang_dist.get(lang_key,0)+1
  src=row['source'] or res.get('source') or 'text'
  if src not in src_dist: src='text'
  src_dist[src]+=1
  if row_overall(row['overall_label'],res,thr)=='toxic': toxic+=1
  else: non_toxic+=1
  cats=row_categories(row['categories_json'],res)
  for k in LABELS:
   if float(cats.get(k,0) or 0)>=0.5: cat_dist[k]+=1
  day=str(row['created_at'] or '')[:10]
  if day: daily[day]=daily.get(day,0)+1
  action=(res.get('decision') or {}).get('action') or res.get('action') or 'UNKNOWN'
  decisions[action]=decisions.get(action,0)+1
 feedback=None
 if fb:
  correct=sum(1 for x in fb if x['correct'])
  feedback={'total':len(fb),'correct':correct,'incorrect':len(fb)-correct,'accuracy':round(correct*100.0/len(fb),1)}
 return {'total':total,'toxic_count':toxic,'non_toxic_count':non_toxic,
  'toxic_pct':round(toxic*100.0/total,1) if total else 0.0,
  'non_toxic_pct':round(non_toxic*100.0/total,1) if total else 0.0,
  'category_distribution':cat_dist,
  'daily':[{'date':d,'count':daily[d]} for d in sorted(daily)],
  'source_distribution':src_dist,
  'language_distribution':lang_dist,
  'feedback':feedback,
  'decisions':decisions}

# ---------------------------------------------------------------------------
# 6) Feedback
# ---------------------------------------------------------------------------
@app.post('/feedback')
def feedback_create(req:FeedbackIn,authorization:Optional[str]=Header(default=None)):
 u=current(authorization)
 if req.corrected_label is not None and req.corrected_label not in VALID_LABELS:
  raise HTTPException(400,'Unsupported corrected label.')
 thr=get_threshold(); pid=req.prediction_id
 input_text=''; predicted=None; conf=None; cats_json=None
 if pid is not None:
  c=db(); row=c.execute('SELECT message,result_json,overall_label,confidence,categories_json FROM moderation_results WHERE id=?',(pid,)).fetchone(); c.close()
  if not row: raise HTTPException(404,'Prediction not found.')
  res=load_result_json(row['result_json'])
  input_text=row['message']; predicted=row_overall(row['overall_label'],res,thr)
  conf=row_confidence(row['confidence'],res)
  cats_json=json.dumps(row_categories(row['categories_json'],res),ensure_ascii=False)
 c=db()
 try:
  c.execute('INSERT INTO feedback(prediction_id,username,input_text,predicted_label,confidence,categories_json,correct,corrected_label,note,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(pid,u['username'],input_text,predicted,conf,cats_json,1 if req.correct else 0,req.corrected_label,req.comment,now()))
  c.commit()
 except Exception:
  c.rollback(); c.close(); raise HTTPException(500,'Unable to save the feedback.')
 c.close()
 return {'ok':True}

@app.get('/feedback')
def feedback_list(authorization:Optional[str]=Header(default=None)):
 admin(authorization)
 c=db(); rows=c.execute('SELECT * FROM feedback ORDER BY id DESC').fetchall(); c.close()
 items=[]
 for row in rows:
  d=dict(row); d['correct']=bool(d.get('correct')); d['categories']=row_categories(d.get('categories_json'),None)
  items.append(d)
 return {'items':items,'total':len(items)}

# ---------------------------------------------------------------------------
# 7) Admin verification of a moderation result
# ---------------------------------------------------------------------------
@app.post('/admin/verify/{mid}')
def verify(mid:int,req:VerifyIn,authorization:Optional[str]=Header(default=None)):
 a=admin(authorization)
 if req.corrected_label is not None and req.corrected_label not in VALID_LABELS:
  raise HTTPException(400,'Unsupported corrected label.')
 c=db(); row=c.execute('SELECT * FROM moderation_results WHERE id=?',(mid,)).fetchone()
 if not row: c.close(); raise HTTPException(404,'Moderation item not found.')
 res=load_result_json(row['result_json']); cats=row_categories(row['categories_json'],res)
 added=False
 if req.add_to_dataset:
  fn=require_ml('add_sample').add_sample
  comment=str(row['message'] or '').strip()
  if not comment: raise HTTPException(400,'This comment cannot be added to the dataset because it is empty.')
  labels={k:0 for k in LABELS}
  if req.corrected_label in LABELS: labels[req.corrected_label]=1
  elif req.corrected_label!='non_toxic':
   for k in LABELS:
    if float(cats.get(k,0) or 0)>=0.5: labels[k]=1
  payload={'comment':comment,'source':row['source'] or 'text'}
  payload.update(labels)
  try: fn(payload)
  except HTTPException: raise
  except Exception as e: raise _ml_error(e,'Unable to add the sample to the dataset')
  added=True
 try:
  if req.corrected_label is not None:
   c.execute('UPDATE moderation_results SET verified=?,overall_label=? WHERE id=?',(1 if req.verified else 0,req.corrected_label,mid))
  else:
   c.execute('UPDATE moderation_results SET verified=? WHERE id=?',(1 if req.verified else 0,mid))
  c.execute('INSERT INTO audit_logs(user_id,action,details,created_at) VALUES(?,?,?,?)',(a['username'],'ADMIN_VERIFY',json.dumps({'moderation_id':mid,'verified':bool(req.verified),'corrected_label':req.corrected_label,'add_to_dataset':bool(req.add_to_dataset)}),now()))
  c.commit()
 except Exception:
  c.rollback(); c.close(); raise HTTPException(500,'Unable to save the verification.')
 c.close()
 return {'ok':True,'moderation_id':mid,'verified':bool(req.verified),'added_to_dataset':added}

# ---------------------------------------------------------------------------
# 8) Settings — toxicity threshold
# ---------------------------------------------------------------------------
@app.get('/settings')
def settings_get(authorization:Optional[str]=Header(default=None)):
 current(authorization)
 return {'toxicity_threshold':get_threshold()}

@app.put('/settings')
def settings_put(req:SettingsIn,authorization:Optional[str]=Header(default=None)):
 admin(authorization)
 try: v=set_threshold(req.toxicity_threshold)
 except Exception as e: raise HTTPException(500,f'Unable to save the settings: {e}')
 return {'ok':True,'toxicity_threshold':v}

# ---------------------------------------------------------------------------
# 5) Dataset management — storage lives in ml_service
# ---------------------------------------------------------------------------
@app.get('/dataset')
def dataset_list(authorization:Optional[str]=Header(default=None),limit:int=50,offset:int=0,q:Optional[str]=None):
 admin(authorization)
 if limit<1 or limit>500: raise HTTPException(400,'limit must be between 1 and 500.')
 if offset<0: raise HTTPException(400,'offset must be 0 or greater.')
 fn=require_ml('list_samples').list_samples
 try: data=fn(limit,offset,q or '')
 except HTTPException: raise
 except Exception as e: raise _ml_error(e,'Unable to read the dataset')
 if not isinstance(data,dict): raise HTTPException(500,'Dataset service returned an invalid response.')
 items=data.get('items') if isinstance(data.get('items'),list) else []
 total=data.get('total') if isinstance(data.get('total'),int) else len(items)
 return {'items':items,'total':total}

@app.post('/dataset')
def dataset_create(req:DatasetIn,authorization:Optional[str]=Header(default=None)):
 admin(authorization)
 comment=str(req.comment or '').strip()
 if not comment: raise HTTPException(400,'Comment cannot be empty.')
 src=req.source or 'text'
 if not DATASET_SOURCE_RE.match(src): raise HTTPException(400,'Unsupported source. Use letters, digits, spaces, _ or - (max 40 chars).')
 fn=require_ml('add_sample').add_sample
 payload={'comment':comment,'toxic':req.toxic,'severe_toxic':req.severe_toxic,'obscene':req.obscene,'threat':req.threat,'insult':req.insult,'identity_hate':req.identity_hate,'source':src}
 try: item=fn(payload)
 except HTTPException: raise
 except Exception as e: raise _ml_error(e,'Unable to add the dataset sample')
 if item is None: raise HTTPException(500,'Dataset service did not return the saved sample.')
 return item

@app.put('/dataset/{sample_id}')
def dataset_update(sample_id:int,req:DatasetPatch,authorization:Optional[str]=Header(default=None)):
 admin(authorization)
 payload={}
 if req.comment is not None:
  comment=str(req.comment).strip()
  if not comment: raise HTTPException(400,'Comment cannot be empty.')
  payload['comment']=comment
 for k in LABELS:
  v=getattr(req,k)
  if v is not None: payload[k]=v
 if req.source is not None:
  if not DATASET_SOURCE_RE.match(str(req.source)): raise HTTPException(400,'Unsupported source. Use letters, digits, spaces, _ or - (max 40 chars).')
  payload['source']=req.source
 if not payload: raise HTTPException(400,'No dataset fields were provided.')
 fn=require_ml('update_sample').update_sample
 try: item=fn(sample_id,payload)
 except HTTPException: raise
 except Exception as e: raise _ml_error(e,'Unable to update the dataset sample')
 if item is None: raise HTTPException(404,'Dataset sample not found.')
 return item

@app.delete('/dataset/{sample_id}')
def dataset_delete(sample_id:int,authorization:Optional[str]=Header(default=None)):
 admin(authorization)
 fn=require_ml('delete_sample').delete_sample
 try: ok=fn(sample_id)
 except HTTPException: raise
 except Exception as e: raise _ml_error(e,'Unable to delete the dataset sample')
 if not ok: raise HTTPException(404,'Dataset sample not found.')
 return {'ok':True}

@app.get('/dataset/stats')
def dataset_stats(authorization:Optional[str]=Header(default=None)):
 admin(authorization)
 m=require_ml('dataset_stats','class_distribution')
 try: stats=m.dataset_stats()
 except HTTPException: raise
 except Exception as e: raise _ml_error(e,'Unable to read the dataset statistics')
 try: dist=m.class_distribution()
 except HTTPException: raise
 except Exception as e: raise _ml_error(e,'Unable to read the class distribution')
 out=dict(stats) if isinstance(stats,dict) else {}
 out['class_distribution']=dict(dist) if isinstance(dist,dict) else {}
 return out

# ---------------------------------------------------------------------------
# 9) Model registry, comparison, performance, split and training jobs
# ---------------------------------------------------------------------------
def _load_versions():
 fn=ml_fn('list_model_versions'); versions=None
 if fn is not None:
  try: data=fn()
  except Exception as e: raise HTTPException(500,f'Unable to read the model registry: {e}')
  if isinstance(data,list): versions=[_jsonable(x) for x in data]
  elif isinstance(data,dict): versions=_jsonable(data.get('versions') or [])
 if versions is None:
  try:
   c=db(); rows=c.execute('SELECT * FROM model_versions ORDER BY id DESC').fetchall(); c.close()
   versions=[_jsonable(dict(r)) for r in rows]
  except Exception: versions=[]
 return versions

@app.get('/models')
def models_list(authorization:Optional[str]=Header(default=None)):
 admin(authorization)
 return {'versions':_load_versions()}

@app.get('/models/engine')
def get_engine(authorization:Optional[str]=Header(default=None)):
 admin(authorization)
 mode,src=engine_mode_info()
 out={'engine':mode,'modes':list(ENGINE_MODES),'default':ENGINE_DEFAULT,'source':src,
      'source_note':{'settings':'admin setting (settings table)','env':'AURA_PREDICTION_ENGINE environment variable','default':'built-in default'}.get(src,src)}
 out['adapter_available']=model_adapter is not None
 if model_adapter is not None:
  try: out['adapter']=_safe_adapter_info(model_adapter.ADAPTER.info())
  except Exception: out['adapter']={'status':'unknown'}
  try: out['coverage']={c:{'status':s,'note':n} for c,(s,n) in model_adapter.MODEL_COVERAGE.items()}
  except Exception: out['coverage']={}
 return out

@app.post('/models/engine')
def set_engine_endpoint(req:EngineIn,authorization:Optional[str]=Header(default=None)):
 a=admin(authorization)
 mode=set_engine(req.engine, actor=a.get('username'))   # validates against ENGINE_MODES (400 otherwise) + audits the change
 # kick off the background warm-up so the first hf request is not a cold load
 try:
  if mode!='legacy' and model_adapter is not None:
   def _warm_model():
    try: model_adapter.ADAPTER.predict(['warm up'])
    except Exception: pass
   threading.Thread(target=_warm_model,daemon=True).start()
 except Exception: pass
 return {'ok':True,'engine':mode}

@app.get('/models/adapter')
def get_adapter_info(authorization:Optional[str]=Header(default=None)):
 admin(authorization)
 out={'engine':engine_mode(),'adapter_available':model_adapter is not None,'adapter':None,'coverage':{},'claimed_languages':[],'benchmark':None}
 if model_adapter is not None:
  try: out['adapter']=_safe_adapter_info(model_adapter.ADAPTER.info())
  except Exception as e: out['adapter']={'status':'error','error':f'{type(e).__name__}'}
  try: out['coverage']={c:{'status':s,'note':n} for c,(s,n) in model_adapter.MODEL_COVERAGE.items()}
  except Exception: pass
  try: out['claimed_languages']=sorted(model_adapter.MODEL_CLAIMED_LANGUAGES)
  except Exception: pass
 # measured benchmark summary (Phase 2 held-out test split) — no internals
 try:
  bp=BASE_DIR/'models'/'phase2_benchmark.json'
  if bp.exists():
   d=json.loads(bp.read_text(encoding='utf-8'))
   groups=d.get('groups') or {}
   summary={'generated_at':d.get('generated_at'),'tuned_threshold':d.get('tuned_threshold'),'groups':{}}
   for g,e in groups.items():
    summary['groups'][g]={'n':e.get('test_rows'),'legacy':{k:(e.get('legacy') or {}).get(k) for k in ('accuracy','toxic_f1','toxic_recall','fpr')},'model':{k:(e.get('model') or {}).get(k) for k in ('accuracy','toxic_f1','toxic_recall','fpr','roc_auc','pr_auc','latency_ms_per_text')},'threshold_used':(e.get('model') or {}).get('threshold_used')}
   summary['memory_mb']=d.get('memory_mb')
   out['benchmark']=summary
 except Exception: out['benchmark']=None
 return out

@app.get('/models/compare')
def models_compare(authorization:Optional[str]=Header(default=None)):
 admin(authorization)
 fn=ml_fn('compare_models'); data=None
 if fn is not None:
  try: data=fn()
  except Exception as e: raise HTTPException(500,f'Unable to compare the models: {e}')
 if not isinstance(data,dict): data={}
 data=_jsonable(data)
 data.setdefault('metrics',[]); data.setdefault('notes',[])
 versions=_load_versions()
 data['versions']=versions; data['count']=len(versions); data['compared_at']=now()
 return data

@app.get('/models/performance')
def models_performance(authorization:Optional[str]=Header(default=None)):
 admin(authorization)
 fn=ml_fn('evaluate_report'); report=None
 if fn is not None:
  try: report=fn()
  except Exception as e: raise HTTPException(500,f'Unable to evaluate the model: {e}')
 if not isinstance(report,dict): report={}
 report=_jsonable(report)
 metrics={}
 for key in ('accuracy','precision','recall','f1','roc_auc'):
  val=report.get(key)
  metrics[key]='Not evaluated' if val is None else val
 report['metrics']=metrics
 report.setdefault('status','evaluated' if any(v!='Not evaluated' for v in metrics.values()) else 'not_evaluated')
 report['note']='Metrics that have never been measured are returned as the string "Not evaluated".'
 return report

@app.get('/models/split')
def models_split(authorization:Optional[str]=Header(default=None)):
 admin(authorization)
 fn=ml_fn('split_counts'); out=None
 if fn is not None:
  try: out=fn()
  except Exception as e: out={'error':f'{type(e).__name__}: {e}'}
 if not isinstance(out,dict): out={'error':'ML service (ml_service) is unavailable.'}
 out=_jsonable(out)
 for key in ('seed','train','validation','test'): out.setdefault(key,None)
 out['note']='Row counts of the train / validation / test split created by ml_service.' if out.get('train') is not None else 'No dataset split has been created yet.'
 return out

@app.post('/models/train')
def models_train(req:TrainIn,authorization:Optional[str]=Header(default=None)):
 admin(authorization)
 m=require_ml('start_training'); fn=m.start_training
 config=dict(req.config) if isinstance(req.config,dict) else {}
 variants=tuple(getattr(m,'VARIANTS',('baseline','improved')))
 variant=config.get('variant','improved')
 if variant not in variants: raise HTTPException(400,f"config['variant'] must be one of {list(variants)}.")
 if 'seed' in config and (isinstance(config['seed'],bool) or not isinstance(config['seed'],int)):
  raise HTTPException(400,"config['seed'] must be an integer.")
 job_id=uuid.uuid4().hex; started=now()
 c=db()
 try:
  c.execute("INSERT INTO training_runs(job_id,status,config_json,started_at) VALUES(?,?,?,?) ON CONFLICT(job_id) DO UPDATE SET status=excluded.status,config_json=excluded.config_json,started_at=excluded.started_at,finished_at=NULL,metrics_json=NULL,error=NULL",(job_id,'queued',json.dumps(config,ensure_ascii=False),started))
  c.commit()
 except Exception:
  c.rollback(); c.close(); raise HTTPException(500,'Unable to queue the training job.')
 c.close()
 def _run():
  try: fn(job_id,config)
  except Exception as e:
   cc=db()
   try:
    cc.execute("UPDATE training_runs SET status='failed',finished_at=?,error=? WHERE job_id=?",(now(),f'{type(e).__name__}: {e}',job_id)); cc.commit()
   except Exception: pass
   finally: cc.close()
 threading.Thread(target=_run,daemon=True,name=f'aura-train-{job_id}').start()
 return {'job_id':job_id,'status':'queued'}

@app.get('/models/train/{job_id}')
def models_train_status(job_id:str,authorization:Optional[str]=Header(default=None)):
 admin(authorization)
 jid=str(job_id or '').strip()
 job=None; g=ml_fn('get_job')
 if g is not None:
  try:
   d=g(jid)
   if isinstance(d,dict): job=_jsonable(d)
  except Exception: job=None
 c=db(); row=c.execute('SELECT * FROM training_runs WHERE job_id=?',(jid,)).fetchone()
 if row is None and job is None:
  c.close(); raise HTTPException(404,'Training job not found.')
 status=str((job or {}).get('status') or (row['status'] if row else 'queued'))
 progress=(job or {}).get('progress')
 try: progress=float(progress)
 except (TypeError,ValueError): progress=0.0
 message=str((job or {}).get('message') or '')
 metrics=(job or {}).get('metrics')
 if metrics is None and row is not None and row['metrics_json']:
  try:
   parsed=json.loads(row['metrics_json'])
   metrics=parsed if isinstance(parsed,(dict,list)) else None
  except Exception: metrics=None
 error=(job or {}).get('error')
 if error is None and row is not None: error=row['error']
 started_at=(job or {}).get('started_at') or (row['started_at'] if row else None)
 finished_at=(job or {}).get('finished_at') or (row['finished_at'] if row else None)
 config_json=row['config_json'] if row is not None else None
 try:
  c.execute("INSERT INTO training_runs(job_id,status,config_json,started_at,finished_at,metrics_json,error) VALUES(?,?,?,?,?,?,?) ON CONFLICT(job_id) DO UPDATE SET status=excluded.status,started_at=COALESCE(excluded.started_at,training_runs.started_at),finished_at=excluded.finished_at,metrics_json=COALESCE(excluded.metrics_json,training_runs.metrics_json),error=excluded.error",(jid,status,config_json,started_at,finished_at,json.dumps(metrics,ensure_ascii=False) if isinstance(metrics,(dict,list)) else None,error))
  c.commit()
 except Exception:
  c.rollback()
 c.close()
 return {'job_id':jid,'status':status,'progress':progress,'message':message,'metrics':metrics,'error':error,'started_at':started_at,'finished_at':finished_at}

# ---------------------------------------------------------------------------
# 10) Voice — transcription and voice prediction. Raw audio is never stored.
# ---------------------------------------------------------------------------
def _speech_language(raw):
 """Map an optional language hint to a Google STT locale (None = engine default)."""
 if raw is None: return None
 if not isinstance(raw,str): return None
 hint=str(raw).strip()
 if not hint: return None
 low=hint.lower()
 if low in ('auto','default','none','system','any'): return None
 mapped={'en':'en-IN','ta':'ta-IN','hi':'hi-IN','te':'te-IN','ml':'ml-IN','kn':'kn-IN',
         'bn':'bn-IN','mr':'mr-IN','gu':'gu-IN','pa':'pa-IN','ur':'ur-IN'}.get(low)
 if mapped: return mapped
 # Already a locale such as ta-IN / en-US: normalise and pass it through.
 m=re.fullmatch(r'([a-z]{2})-([a-z]{2,4})',hint,re.IGNORECASE)
 if m:
  region=m.group(2)
  region=region.upper() if len(region)==2 else region[0].upper()+region[1:].lower()
  return m.group(1).lower()+'-'+region
 if re.fullmatch(r'[a-z]{2}',low): return None
 return None

def _transcribe_audio(data,mime,language_hint=None):
 try:
  import speech_recognition as sr
 except Exception as e:
  return {'ok':False,'error':f'Speech recognition engine unavailable: {type(e).__name__}: {e}','transcript':''}
 try:
  recognizer=sr.Recognizer()
  with sr.AudioFile(io.BytesIO(data)) as source:
   audio=recognizer.record(source)
  locale=_speech_language(language_hint)
  text=recognizer.recognize_google(audio,language=locale) if locale else recognizer.recognize_google(audio)
  return {'ok':True,'transcript':str(text),'engine':'google'}
 except Exception as e:
  reason=str(e).strip() or type(e).__name__
  return {'ok':False,'error':reason,'transcript':''}

@app.post('/voice/transcribe')
async def voice_transcribe(request:Request,authorization:Optional[str]=Header(default=None)):
 current(authorization)
 ctype=(request.headers.get('content-type') or '').split(';')[0].strip().lower()
 data=None; mime='audio/wav'; lang_hint=None
 if ctype=='multipart/form-data':
  try: form=await request.form()
  except Exception: raise HTTPException(422,'Malformed multipart body. Send the audio in the "file" field.')
  lang_hint=form.get('language')
  f=form.get('file')
  if f is None: raise HTTPException(422,'Missing audio file field "file".')
  if not hasattr(f,'read'): raise HTTPException(422,'The "file" field must contain an uploaded audio file.')
  try: data=await f.read()
  except Exception: raise HTTPException(422,'Malformed multipart body.')
  if not data: raise HTTPException(422,'The uploaded audio file is empty.')
  name=str(getattr(f,'filename','') or '')
  ext=name.rsplit('.',1)[-1].lower() if '.' in name else ''
  mime={'wav':'audio/wav','flac':'audio/flac','aif':'audio/aiff','aiff':'audio/aiff','ogg':'audio/ogg','mp3':'audio/mpeg','webm':'audio/webm'}.get(ext,'audio/wav')
 elif ctype=='application/json':
  try: body=await request.json()
  except Exception: raise HTTPException(422,'Malformed JSON body.')
  if not isinstance(body,dict): raise HTTPException(422,'Expected a JSON object with audio_b64 and mime.')
  b64=body.get('audio_b64')
  if not isinstance(b64,str) or not b64.strip(): raise HTTPException(422,'Missing audio_b64.')
  raw=b64.strip()
  if raw.lower().startswith('data:') and ',' in raw: raw=raw.split(',',1)[1]
  raw=re.sub(r'\s+','',raw)
  try: data=base64.b64decode(raw,validate=True)
  except Exception: raise HTTPException(422,'audio_b64 is not valid base64 audio data.')
  if not data: raise HTTPException(422,'Decoded audio is empty.')
  mime=str(body.get('mime') or '').strip() or 'audio/wav'
  lang_hint=body.get('language')
 else:
  raise HTTPException(422,'Send multipart form-data with field "file" or JSON {audio_b64, mime}.')
 return _transcribe_audio(data,mime,lang_hint)

@app.post('/voice/predict')
def voice_predict(req:VoicePredictIn,authorization:Optional[str]=Header(default=None)):
 u=current(authorization)
 text=str(req.transcript or '').strip()
 if not text: raise HTTPException(400,'Transcript cannot be empty.')
 msg=MessageIn(text=text,user_id=u['username'],conversation_id='voice',source='voice')
 r,extra=run_engine(msg,'voice')
 r['prediction_id']=extra['prediction_id']; r['confidence']=extra['confidence']
 return r

# ---------------------------------------------------------------------------
# 11) Live Guard — streamed transcript sessions. No audio/video is stored.
# ---------------------------------------------------------------------------
@app.post('/live/start')
def live_start(authorization:Optional[str]=Header(default=None)):
 u=current(authorization)
 sid=uuid.uuid4().hex; started=now()
 c=db()
 try:
  c.execute('INSERT INTO live_sessions(session_id,username,started_at,status) VALUES(?,?,?,?)',(sid,u['username'],started,'active'))
  c.commit()
 except Exception:
  c.rollback(); c.close(); raise HTTPException(500,'Unable to start the live session.')
 c.close()
 return {'session_id':sid,'started_at':started}

@app.post('/live/chunk')
def live_chunk(req:LiveChunkIn,authorization:Optional[str]=Header(default=None)):
 u=current(authorization)
 text=str(req.transcript or '').strip()
 if not text: raise HTTPException(400,'Transcript cannot be empty.')
 if req.elapsed_s is not None and req.elapsed_s<0: raise HTTPException(400,'elapsed_s cannot be negative.')
 sid=str(req.session_id or '').strip()
 c=db(); sess=c.execute('SELECT * FROM live_sessions WHERE session_id=?',(sid,)).fetchone()
 if not sess or sess['status']!='active' or (sess['username']!=u['username'] and u['role']!='admin'):
  c.close(); raise HTTPException(404,'Live session not found or already ended.')
 c.close()
 msg=MessageIn(text=text,user_id=u['username'],conversation_id='live:'+sid,source='live')
 r,extra=run_engine(msg,'live')
 label=r['overall_label']; conf=extra['confidence']; created=r['created_at']
 elapsed=float(req.elapsed_s) if req.elapsed_s is not None else 0.0
 c=db()
 try:
  cur=c.execute('INSERT INTO live_events(session_id,transcript,label,confidence,categories_json,elapsed_s,created_at) VALUES(?,?,?,?,?,?,?)',(sid,text,label,conf,json.dumps(r['categories'],ensure_ascii=False),elapsed,created))
  eid=cur.lastrowid; c.commit()
 except Exception:
  c.rollback(); c.close(); raise HTTPException(500,'Unable to store the live event.')
 c.close()
 return {'event_id':eid,'session_id':sid,'label':label,'confidence':conf,'categories':r['categories'],'risk_score':r['risk_score'],'decision':r['decision'],'created_at':created,'elapsed_s':elapsed,'text':r.get('text') or text,'language':r.get('language_name'),'language_code':r.get('language_code'),'language_name':r.get('language_name'),'script':r.get('script'),'processing_mode':r.get('processing_mode'),'confidence_kind':r.get('confidence_kind','heuristic'),'score':r.get('score')}

@app.post('/live/stop')
def live_stop(req:LiveStopIn,authorization:Optional[str]=Header(default=None)):
 u=current(authorization)
 sid=str(req.session_id or '').strip()
 c=db(); sess=c.execute('SELECT * FROM live_sessions WHERE session_id=?',(sid,)).fetchone()
 if not sess or (sess['username']!=u['username'] and u['role']!='admin'):
  c.close(); raise HTTPException(404,'Live session not found.')
 count=c.execute('SELECT COUNT(*) AS n FROM live_events WHERE session_id=?',(sid,)).fetchone()
 events=int(count['n'] or 0)
 if sess['status']=='active':
  try:
   c.execute("UPDATE live_sessions SET status='ended', ended_at=? WHERE session_id=?",(now(),sid)); c.commit()
  except Exception:
   c.rollback(); c.close(); raise HTTPException(500,'Unable to stop the live session.')
 c.close()
 return {'ok':True,'events':events}

@app.get('/live/sessions')
def live_sessions(authorization:Optional[str]=Header(default=None)):
 u=current(authorization)
 c=db()
 if u['role']=='admin': rows=c.execute('SELECT * FROM live_sessions ORDER BY started_at DESC').fetchall()
 else: rows=c.execute('SELECT * FROM live_sessions WHERE username=? ORDER BY started_at DESC',(u['username'],)).fetchall()
 items=[]
 for s in rows:
  cnt=c.execute('SELECT COUNT(*) AS n FROM live_events WHERE session_id=?',(s['session_id'],)).fetchone()
  items.append({'session_id':s['session_id'],'started_at':s['started_at'],'ended_at':s['ended_at'],'status':s['status'],'event_count':int(cnt['n'] or 0)})
 c.close()
 return {'items':items}

@app.get('/live/{session_id}')
def live_session_detail(session_id:str,authorization:Optional[str]=Header(default=None)):
 u=current(authorization)
 sid=str(session_id or '').strip()
 c=db(); sess=c.execute('SELECT * FROM live_sessions WHERE session_id=?',(sid,)).fetchone()
 if not sess: c.close(); raise HTTPException(404,'Live session not found.')
 if sess['username']!=u['username'] and u['role']!='admin':
  c.close(); raise HTTPException(403,'You do not have access to this live session.')
 evs=c.execute('SELECT * FROM live_events WHERE session_id=? ORDER BY id',(sid,)).fetchall()
 events=[]
 for e in evs:
  events.append({'id':e['id'],'transcript':e['transcript'],'label':e['label'],'confidence':e['confidence'],'categories':row_categories(e['categories_json'],None),'elapsed_s':e['elapsed_s'],'created_at':e['created_at']})
 c.close()
 return {'session_id':sess['session_id'],'started_at':sess['started_at'],'ended_at':sess['ended_at'],'status':sess['status'],'events':events}


# ---------------------------------------------------------------------------
# AURA 4.16 - explicit CLI entry point.
#
# Importing this module (e.g. `uvicorn backend:app`, `import backend`, test
# collection, static analysis) does NOT execute this block and performs NO
# database write. All initialisation happens in the ASGI `startup` hook
# above, which only runs when the server begins serving.
# ---------------------------------------------------------------------------
if __name__ == '__main__':
 sys.exit(_cli())
