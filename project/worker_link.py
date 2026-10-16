"""Authenticated HTTPS worker protocol. No redirects/retries, shell or cloud SDK."""
from contextlib import contextmanager
import hashlib
import os
import hmac
import http.client
import io
import json
from pathlib import Path
import re
import sqlite3
import ssl
import threading
from urllib.parse import urlsplit

from inference.jobs import ID, JobError
from lighting import canonical

MAX_BODY = 32 * 1024 * 1024


class LinkUncertain(Exception):
    """Opaque network/protocol failure; never expose runtime credentials."""


class HTTPSWorker:
    def __init__(self, url, token, *, ca_file=None, timeout=5, connection_factory=None, certificate_sha256=None, client_certificate=None, client_key=None):
        endpoint=urlsplit(url)
        if (endpoint.scheme!='https' or not endpoint.hostname or endpoint.username or
                endpoint.password or endpoint.query or endpoint.fragment or endpoint.path not in ('','/')):
            raise ValueError('EXACT_HTTPS_WORKER_ORIGIN_REQUIRED')
        if not isinstance(token,str) or not 32<=len(token)<=4096 or any(ord(c)<33 or ord(c)>126 for c in token):
            raise ValueError('RUNTIME_WORKER_TOKEN_REQUIRED')
        if not 0<timeout<=10:raise ValueError('BOUNDED_WORKER_TIMEOUT_REQUIRED')
        if certificate_sha256 is not None and (not isinstance(certificate_sha256,str) or not re.fullmatch('[a-f0-9]{64}',certificate_sha256)):
            raise ValueError('WORKER_CERTIFICATE_PIN_INVALID')
        self.certificate_sha256=certificate_sha256
        self.endpoint,self.token,self.timeout=endpoint,token,timeout
        self.simulation=connection_factory is not None
        self.context=ssl.create_default_context(cafile=ca_file)
        if bool(client_certificate)!=bool(client_key):raise ValueError('CLIENT_CERTIFICATE_AND_KEY_REQUIRED')
        if client_certificate:
            from security import runtime_file
            root=Path(__file__).resolve().parent.parent
            runtime_file(client_certificate,root);runtime_file(client_key,root)
            self.context.load_cert_chain(str(client_certificate),str(client_key))
        self.factory=connection_factory or http.client.HTTPSConnection

    def request(self, method, path, body=None):
        if not re.fullmatch(r'/v1/(?:health|jobs|jobs/[a-f0-9]{32}|blobs/[a-f0-9]{64})',path):
            raise ValueError('WORKER_ROUTE_NOT_ALLOWED')
        payload=canonical(body).encode() if isinstance(body,dict) else body
        if payload is not None and len(payload)>MAX_BODY:raise ValueError('WORKER_BODY_TOO_LARGE')
        connection=self.factory(self.endpoint.hostname,self.endpoint.port or 443,
                                timeout=self.timeout,context=self.context)
        try:
            if self.certificate_sha256:
                connection.connect()
                if not hmac.compare_digest(hashlib.sha256(connection.sock.getpeercert(binary_form=True)).hexdigest(),self.certificate_sha256):
                    raise LinkUncertain()
            connection.request(method,path,body=payload,headers={'Authorization':'Bearer '+self.token,
                'Content-Type':'application/json' if isinstance(body,dict) else 'application/octet-stream'})
            response=connection.getresponse()
            if method=='GET' and path.startswith('/v1/blobs/'):
                raw=response.read(MAX_BODY+1)
                if response.status!=200 or len(raw)>MAX_BODY or hashlib.sha256(raw).hexdigest()!=path.rsplit('/',1)[1]:raise LinkUncertain()
                return raw
            raw=response.read(1024*1024+1)
            if len(raw)>1024*1024 or response.status not in (200,201,202,404):raise LinkUncertain()
            value=json.loads(raw)
            if not isinstance(value,dict):raise LinkUncertain()
            if response.status==404:return {'status':'not_found'}
            return value
        except Exception:
            raise LinkUncertain('WORKER_RESPONSE_UNCERTAIN') from None
        finally:connection.close()

    def health(self):return self.request('GET','/v1/health')
    def query(self, job_id):
        if not ID.fullmatch(job_id):raise ValueError('JOB_ID_REQUIRED')
        return self.request('GET','/v1/jobs/'+job_id)
    def submit(self, envelope):return self.request('POST','/v1/jobs',envelope)
    def upload(self, payload):
        sha=hashlib.sha256(payload).hexdigest()
        return self.request('PUT','/v1/blobs/'+sha,payload)

    def download(self,sha):return self.request('GET','/v1/blobs/'+sha)


class WorkerLedger:
    simulation=True
    """Worker-side durable idempotency and one execution lane; GET has no effects."""
    def __init__(self, root, token, session_id, resource_id):
        source=Path(root)
        if not source.is_absolute() or any(x.is_symlink() for x in (source,*source.parents)):raise ValueError('PRIVATE_WORKER_ROOT_REQUIRED')
        self.root=source.resolve();self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        if (not isinstance(session_id,str) or not ID.fullmatch(session_id) or not isinstance(resource_id,str) or not resource_id or
                not isinstance(token,str) or not 32<=len(token)<=4096 or any(ord(c)<33 or ord(c)>126 for c in token)):
            raise ValueError('WORKER_RUNTIME_IDENTITY_REQUIRED')
        self.token,self.session_id,self.resource_id=token,session_id,resource_id
        self.lock=threading.RLock();self.model_state='loading';self.executor=None;self.max_jobs=None
        if (self.root/'blobs').is_symlink() or (self.root/'worker.sqlite3').is_symlink():raise ValueError('WORKER_PATH_SYMLINK_FORBIDDEN')
        (self.root/'blobs').mkdir(exist_ok=True,mode=0o700)
        self.lockfile=(self.root/'.worker.lock').open('a+b');self.lockfile.write(b'0');self.lockfile.flush();self.lockfile.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(self.lockfile.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.lockfile,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            self.lockfile.close();raise ValueError('WORKER_STORE_IN_USE')
        try:
            with self.db() as db:
                db.execute('CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,fingerprint TEXT NOT NULL,body TEXT NOT NULL,state TEXT NOT NULL)')
                db.execute('CREATE TABLE IF NOT EXISTS results(id TEXT PRIMARY KEY,sha TEXT NOT NULL)')
                db.execute('CREATE TABLE IF NOT EXISTS worker_identity(singleton INTEGER PRIMARY KEY,session TEXT,resource TEXT)')
                identity=db.execute('SELECT session,resource FROM worker_identity WHERE singleton=1').fetchone()
                if identity and identity!=(session_id,resource_id):raise ValueError('WORKER_STORE_SESSION_MISMATCH')
                for row in db.execute('SELECT body FROM jobs'):
                    old=json.loads(row[0])
                    if (old.get('sessionId'),old.get('resourceId'))!=(session_id,resource_id):raise ValueError('WORKER_STORE_SESSION_MISMATCH')
                db.execute('INSERT OR IGNORE INTO worker_identity VALUES (1,?,?)',(session_id,resource_id))
                # Crash during invocation is not evidence that it never ran.
                db.execute("UPDATE jobs SET state='uncertain' WHERE state='dispatching'")
        except BaseException:
            self.lockfile.close();raise

    @contextmanager
    def db(self):
        db=sqlite3.connect(self.root/'worker.sqlite3',timeout=5)
        db.execute('PRAGMA synchronous=FULL')
        (self.root/'worker.sqlite3').chmod(0o600)
        try:
            with db:yield db
        finally:db.close()

    def close(self):self.lockfile.close()

    def health(self):
        value={'sessionId':self.session_id,'resourceId':self.resource_id,'modelState':self.model_state,
                             'simulation':self.simulation,'modelLoaded':getattr(self.executor,'model_loaded',False) is True,
                             'executionMode':getattr(self.executor,'execution_mode','per-job'),
                             'hostIdentity':getattr(self,'host_identity',None)}
        try:
            from gpu_monitoring import clean_loading
            progress=clean_loading(getattr(self.executor,'loading_progress',None))
            if progress is not None:value['loadingProgress']=progress
        except Exception:pass
        return value

    def blob(self,sha):
        if not re.fullmatch('[a-f0-9]{64}',sha):raise JobError('ARTIFACT_INVALID','Invalid artifact.',422)
        path=self.root/'blobs'/sha
        if path.is_symlink() or not path.is_file() or path.stat().st_size>MAX_BODY:raise JobError('ARTIFACT_MISSING','Missing artifact.',404)
        raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=sha:raise JobError('ARTIFACT_CHANGED','Artifact changed.',409)
        return raw

    def upload(self, sha, data):
        if not re.fullmatch('[a-f0-9]{64}',sha) or not 0<len(data)<=MAX_BODY or hashlib.sha256(data).hexdigest()!=sha:
            raise JobError('ARTIFACT_INVALID','Artifact identity invalid.',422)
        path=self.root/'blobs'/sha
        if path.is_symlink():raise JobError('UNSAFE_PATH','Artifact path invalid.',422)
        with self.lock:
            if path.exists() and path.read_bytes()!=data:raise JobError('ARTIFACT_CONFLICT','Artifact changed.',409)
            if not path.exists():
                temp=path.with_suffix('.tmp');temp.write_bytes(data);temp.replace(path)
        return {'sha256':sha,'bytes':len(data)}

    def accept(self, value):
        required={'jobId','sessionId','resourceId','artifactSha256','requestSha256'}
        if (not isinstance(value,dict) or set(value)!=required or not ID.fullmatch(value.get('jobId','')) or
                value['sessionId']!=self.session_id or value['resourceId']!=self.resource_id or
                any(not isinstance(value[k],str) or not re.fullmatch('[a-f0-9]{64}',value[k]) for k in ('artifactSha256','requestSha256'))):
            raise JobError('JOB_INVALID','Worker job identity invalid.',422)
        path=self.root/'blobs'/value['artifactSha256']
        if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=value['artifactSha256']:
            raise JobError('ARTIFACT_MISSING','Verified artifact required.',422)
        fingerprint=hashlib.sha256(canonical(value).encode()).hexdigest()
        with self.lock,self.db() as db:
            old=db.execute('SELECT fingerprint FROM jobs WHERE id=?',(value['jobId'],)).fetchone()
            if old:
                if old[0]!=fingerprint:raise JobError('JOB_CONFLICT','Job id already binds other input.',409)
            else:
                if self.executor and callable(getattr(self.executor,'authorize',None)):
                    self.executor.authorize(value)
                if self.max_jobs is not None and db.execute('SELECT count(*) FROM jobs').fetchone()[0]>=self.max_jobs:
                    raise JobError('WORKER_SCOPE_EXHAUSTED','Authorized job limit reached.',403)
                db.execute('INSERT INTO jobs VALUES (?,?,?,?)',(value['jobId'],fingerprint,canonical(value),'queued'))
        return self.query(value['jobId'])

    def query(self, job_id):
        if not ID.fullmatch(job_id):raise JobError('JOB_NOT_FOUND','Job not found.',404)
        with self.db() as db:row=db.execute('SELECT body,state FROM jobs WHERE id=?',(job_id,)).fetchone()
        if not row:return {'status':'not_found'}
        with self.db() as db:result=db.execute('SELECT sha FROM results WHERE id=?',(job_id,)).fetchone()
        envelope=json.loads(row[0]);value={**envelope,'status':row[1],**({'resultSha256':result[0]} if result else {})}
        if row[1]=='dispatching':
            try:
                from gpu_monitoring import TASK_STAGES
                progress=self.executor.task_progress(envelope)
                if isinstance(progress,dict) and progress.get('status')=='running' and progress.get('stage') in TASK_STAGES:
                    value['progress']={'status':'running','stage':progress['stage']}
            except Exception:pass
        return value

    def run_one(self):
        with self.lock,self.db() as db:
            if self.executor is None or self.model_state!='ready':return
            if db.execute("SELECT 1 FROM jobs WHERE state IN ('dispatching','uncertain')").fetchone():return
            row=db.execute("SELECT id,body FROM jobs WHERE state='queued' ORDER BY rowid LIMIT 1").fetchone()
            if not row:return
            db.execute("UPDATE jobs SET state='dispatching' WHERE id=?",(row[0],));db.commit()
            try:
                outcome=self.executor(json.loads(row[1]))
                if isinstance(outcome,dict):
                    if set(outcome)!={'status','resultSha256'} or outcome['status']!='succeeded':raise ValueError()
                    self.blob(outcome['resultSha256'])
                    db.execute('INSERT INTO results VALUES (?,?)',(row[0],outcome['resultSha256']))
                    outcome=outcome['status']
                if outcome not in ('succeeded','failed'):raise ValueError()
                db.execute('UPDATE jobs SET state=? WHERE id=?',(outcome,row[0]))
            except Exception:db.execute("UPDATE jobs SET state='uncertain' WHERE id=?",(row[0],))


class WorkerApplication:
    """Bind only behind TLS ingress. Authentication covers every worker route."""
    def __init__(self, ledger):self.ledger=ledger
    def __call__(self,environ,start_response):
        status=200;value={}
        try:
            auth=environ.get('HTTP_AUTHORIZATION','')
            if not hmac.compare_digest(auth,'Bearer '+self.ledger.token):raise JobError('AUTH_REQUIRED','Authentication required.',401)
            method,path=environ['REQUEST_METHOD'],environ.get('PATH_INFO','/')
            if method=='GET' and path=='/v1/health':value=self.ledger.health()
            elif method=='GET' and re.fullmatch('/v1/blobs/[a-f0-9]{64}',path):
                raw=self.ledger.blob(path.rsplit('/',1)[1])
                start_response('200 OK',[('Content-Type','application/octet-stream'),('Content-Length',str(len(raw))),('Cache-Control','no-store')])
                return [raw]
            elif method=='GET' and re.fullmatch('/v1/jobs/[a-f0-9]{32}',path):
                value=self.ledger.query(path.rsplit('/',1)[1]);status=404 if value['status']=='not_found' else 200
            elif (method=='POST' and path=='/v1/jobs') or (method=='PUT' and re.fullmatch('/v1/blobs/[a-f0-9]{64}',path)):
                limit=1024*1024 if method=='POST' else MAX_BODY
                size=int(environ.get('CONTENT_LENGTH','0'))
                if not 0<size<=limit or environ.get('HTTP_TRANSFER_ENCODING'):raise JobError('BODY_INVALID','Body limit exceeded.',413)
                raw=environ['wsgi.input'].read(size)
                if len(raw)!=size:raise JobError('BODY_INVALID','Truncated body.',400)
                value=self.ledger.accept(json.loads(raw)) if method=='POST' else self.ledger.upload(path.rsplit('/',1)[1],raw)
                status=202 if method=='POST' else 201
            else:raise JobError('ROUTE_NOT_FOUND','Route not found.',404)
        except JobError as error:status=error.http;value={'error':{'code':error.code}}
        except Exception:status=422;value={'error':{'code':'WORKER_REQUEST_INVALID'}}
        raw=json.dumps(value).encode()
        from http import HTTPStatus
        start_response(f'{status} {HTTPStatus(status).phrase}',[('Content-Type','application/json'),('Content-Length',str(len(raw))),('Cache-Control','no-store')])
        return [raw]
