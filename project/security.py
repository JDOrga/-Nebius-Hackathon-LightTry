"""Runtime-only accounts/secrets and bounded persistent request budgets."""
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import stat
import threading
import time

from inference.jobs import JobError

USERNAME = re.compile(r'^[a-zA-Z0-9_-]{1,32}$')


def password_record(password, *, expires_at=None, role='user'):
    salt = secrets.token_bytes(16)
    key = hashlib.scrypt(password.encode(), salt=salt, n=32768, r=8, p=1,
                         maxmem=64*1024*1024, dklen=32)
    return {'salt': salt.hex(), 'hash': key.hex(), 'role': role, 'expiresAt': expires_at}


def runtime_file(path, code_root, maximum=65536):
    p = Path(path).expanduser()
    if (not p.is_absolute() or p.resolve().is_relative_to(Path(code_root).resolve()) or
            any(x.is_symlink() for x in (p,*p.parents)) or not p.is_file() or
            p.stat().st_size > maximum):
        raise ValueError('PRIVATE_RUNTIME_FILE_REQUIRED')
    if os.name != 'nt' and stat.S_IMODE(p.stat().st_mode) & 0o077:
        raise ValueError('RUNTIME_SECRET_FILE_MUST_BE_0600')
    return p.read_bytes()


class Accounts:
    def __init__(self, path, code_root, legacy_password=None):
        if path:
            value = json.loads(runtime_file(path, code_root).decode('utf-8'))
            if set(value) != {'schemaVersion','accounts'} or value['schemaVersion'] != 1:
                raise ValueError('RUNTIME_ACCOUNTS_SCHEMA_INVALID')
            self.users = value['accounts']
        elif legacy_password:
            if (len(legacy_password) < 24 or len(legacy_password) > 256 or
                    legacy_password == 'REPLACE_WITH_A_NEW_PRIVATE_PASSWORD' or
                    any(ord(c)<33 or ord(c)>126 for c in legacy_password)):
                raise ValueError('LIGHTTRY_ACCESS_PASSWORD_24_TO_256_ASCII_REQUIRED')
            self.users = {'lighttry': password_record(legacy_password)}
        else:
            raise ValueError('RUNTIME_LOGIN_ACCOUNT_REQUIRED')
        if not isinstance(self.users,dict) or not 1 <= len(self.users) <= 16:
            raise ValueError('BOUNDED_RUNTIME_ACCOUNTS_REQUIRED')
        for name, record in self.users.items():
            if (not USERNAME.fullmatch(name) or not isinstance(record,dict) or
                    set(record) != {'salt','hash','role','expiresAt'} or
                    not re.fullmatch('[a-f0-9]{32}',record['salt']) or
                    not re.fullmatch('[a-f0-9]{64}',record['hash']) or
                    record['role'] not in ('user','operator') or
                    (record['expiresAt'] is not None and type(record['expiresAt']) not in (int,float))):
                raise ValueError('RUNTIME_ACCOUNT_INVALID')
        self.dummy = password_record(secrets.token_urlsafe(32))
        self.cache = {}; self.lock = threading.Lock(); self.cache_key = secrets.token_bytes(32)

    def authenticate(self, header):
        if not isinstance(header,str) or not header.startswith('Basic ') or len(header)>1024:
            return None
        try:
            name, password = base64.b64decode(header[6:],validate=True).decode('utf-8').split(':',1)
        except (ValueError,UnicodeError):
            return None
        if not USERNAME.fullmatch(name) or not 1<=len(password)<=256:
            return None
        record=self.users.get(name,self.dummy);now=time.time()
        if record['expiresAt'] is not None and now>=record['expiresAt']:
            return None
        key=hmac.digest(self.cache_key,header.encode(),'sha256')
        with self.lock:
            if self.cache.get(key,0)>now:return name
        derived=hashlib.scrypt(password.encode(),salt=bytes.fromhex(record['salt']),
                              n=32768,r=8,p=1,maxmem=64*1024*1024,dklen=32)
        if name not in self.users or not hmac.compare_digest(derived.hex(),record['hash']):return None
        with self.lock:
            self.cache={k:expiry for k,expiry in self.cache.items() if expiry>now}
            if len(self.cache)>=256:self.cache.clear()
            self.cache[key]=min(now+60,record['expiresAt'] or now+60)
        return name


    def authenticate_key(self, access_key):
        """One opaque access key, never a username/password pair. Ambiguity fails closed."""
        if (not isinstance(access_key, str) or not 24 <= len(access_key) <= 256 or
                any(ord(c) < 33 or ord(c) > 126 for c in access_key)):
            return None
        now = time.time()
        matches = []
        for name, record in self.users.items():
            derived = hashlib.scrypt(access_key.encode(), salt=bytes.fromhex(record['salt']),
                                     n=32768, r=8, p=1, maxmem=64*1024*1024, dklen=32)
            valid = hmac.compare_digest(derived.hex(), record['hash'])
            if valid and (record['expiresAt'] is None or now < record['expiresAt']):
                matches.append(name)
        return matches[0] if len(matches) == 1 else None


class LoginSessions:
    """Bounded in-memory sessions; plaintext browser tokens are never persisted."""
    def __init__(self, accounts, clock=time.time):
        self.accounts, self.clock = accounts, clock
        self.sessions = {}
        self.lock = threading.Lock()

    def issue(self, owner):
        now = self.clock()
        record = self.accounts.users[owner]
        expiry = min(now + 8*3600, record['expiresAt'] or now + 8*3600)
        if expiry <= now:
            raise ValueError('ACCESS_KEY_EXPIRED')
        token = secrets.token_urlsafe(32)
        digest = hashlib.sha256(token.encode()).hexdigest()
        with self.lock:
            self.sessions = {k:v for k,v in self.sessions.items() if v[1] > now}
            if len(self.sessions) >= 256:
                raise JobError('LOGIN_BUSY', '登录人数已达上限，请稍后重试。', 429)
            self.sessions[digest] = (owner, expiry, record['hash'])
        return token, max(1, int(expiry-now))

    def authenticate(self, token):
        if not isinstance(token,str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
            return None
        digest = hashlib.sha256(token.encode()).hexdigest()
        with self.lock:
            value = self.sessions.get(digest)
            if not value:
                return None
            owner, expiry, fingerprint = value
            record = self.accounts.users.get(owner)
            now = self.clock()
            if (expiry <= now or not record or record['hash'] != fingerprint or
                    (record['expiresAt'] is not None and record['expiresAt'] <= now)):
                self.sessions.pop(digest,None)
                return None
            return owner

    def revoke(self, token):
        with self.lock:
            self.sessions.pop(hashlib.sha256(token.encode()).hexdigest(),None)


class RateLimiter:
    def __init__(self, workspace, clock=time.time):
        self.workspace,self.clock=workspace,clock
        self.limits={'ip':240,'user':120,'login':10,'upload':8,'write':30,'generate':3}
        with workspace.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS rate_windows (key TEXT PRIMARY KEY,bucket INTEGER NOT NULL,count INTEGER NOT NULL)')

    def check(self,category,identity):
        bucket=int(self.clock()//60)
        key=hashlib.sha256((category+':'+identity[:256]).encode()).hexdigest()
        with self.workspace.connect() as db:
            row=db.execute('SELECT bucket,count FROM rate_windows WHERE key=?',(key,)).fetchone()
        if row and row[0]==bucket and row[1]>=self.limits[category]:
            raise JobError('RATE_LIMITED','请求过于频繁，请稍后重试。',429)

    def consume(self, category, identity):
        bucket=int(self.clock()//60)
        key=hashlib.sha256((category+':'+identity[:256]).encode()).hexdigest()
        with self.workspace.lock,self.workspace.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT bucket,count FROM rate_windows WHERE key=?',(key,)).fetchone()
            count=old[1] if old and old[0]==bucket else 0
            if count>=self.limits[category]:
                raise JobError('RATE_LIMITED','请求过于频繁，请稍后重试。',429)
            db.execute('INSERT OR REPLACE INTO rate_windows VALUES (?,?,?)',(key,bucket,count+1))
            db.execute('DELETE FROM rate_windows WHERE bucket<?',(bucket-1,))
            if db.execute('SELECT count(*) FROM rate_windows').fetchone()[0]>4096:
                raise JobError('RATE_LIMITED','服务请求预算已满，请稍后重试。',429)


class ProviderSecrets:
    """Read only explicit server runtime bindings. Never serialize or log values."""
    def __init__(self, code_root):
        self.code_root=code_root

    def get(self, provider):
        names={'nemotron':('LIGHTTRY_NEMOTRON_KEY_FILE','NEMOTRON_API_KEY'),
               'nebius':('LIGHTTRY_NEBIUS_CREDENTIAL_FILE','NEBIUS_IAM_TOKEN')}
        file_key,env_key=names[provider]
        path=os.environ.get(file_key)
        value=runtime_file(path,self.code_root,16384).decode('utf-8').strip() if path else os.environ.get(env_key,'')
        if not value or len(value)>16384:
            raise ValueError('SERVER_PROVIDER_CREDENTIAL_NOT_CONFIGURED')
        return value


def create_temporary_account(root, output, code_root, days=7):
    root=Path(root).expanduser();output=Path(output).expanduser()
    for p in (root,output):
        if not p.is_absolute() or p.resolve().is_relative_to(Path(code_root).resolve()) or any(x.is_symlink() for x in (p,*p.parents)):
            raise ValueError('ACCOUNT_OUTPUT_MUST_BE_PRIVATE_OUTSIDE_CODE')
    root.mkdir(parents=True,exist_ok=True,mode=0o700)
    account=root/'auth/accounts.json';account.parent.mkdir(exist_ok=True,mode=0o700)
    if account.exists() or output.exists():raise ValueError('ACCOUNT_FILES_EXIST_REFUSE_OVERWRITE')
    output.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    password=secrets.token_urlsafe(32);expiry=time.time()+days*86400
    value={'schemaVersion':1,'accounts':{'lighttry':password_record(password,expires_at=expiry)}}
    with account.open('x',encoding='utf-8') as stream:json.dump(value,stream);stream.flush();os.fsync(stream.fileno())
    account.chmod(0o600)
    with output.open('x',encoding='utf-8') as stream:
        stream.write('accessKey='+password+'\nexpiresAt='+str(expiry)+'\n');stream.flush();os.fsync(stream.fileno())
    output.chmod(0o600)
    return {'username':'lighttry','role':'user','expiresAt':expiry,'accountsFile':str(account),'privateCredentialsFile':str(output)}
