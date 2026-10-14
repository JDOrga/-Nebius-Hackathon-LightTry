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
    def __init__(self, url, token, *, ca_file=None, timeout=5, connection_factory=None):
        endpoint=urlsplit(url)
        if (endpoint.scheme!='https' or not endpoint.hostname or endpoint.username or
                endpoint.password or endpoint.query or endpoint.fragment or endpoint.path not in ('','/')):
            raise ValueError('EXACT_HTTPS_WORKER_ORIGIN_REQUIRED')
        if not isinstance(token,str) or not 32<=len(token)<=4096 or any(ord(c)<33 or ord(c)>126 for c in token):
            raise ValueError('RUNTIME_WORKER_TOKEN_REQUIRED')
        if not 0<timeout<=10:raise ValueError('BOUNDED_WORKER_TIMEOUT_REQUIRED')
        self.endpoint,self.token,self.timeout=endpoint,token,timeout
        self.simulation=connection_factory is not None
        self.context=ssl.create_default_context(cafile=ca_file)
        self.factory=connection_factory or http.client.HTTPSConnection

    def request(self, method, path, body=None):
        if not re.fullmatch(r'/v1/(?:health|jobs|jobs/[a-f0-9]{32}|blobs/[a-f0-9]{64})',path):
            raise ValueError('WORKER_ROUTE_NOT_ALLOWED')
        payload=canonical(body).encode() if isinstance(body,dict) else body
        if payload is not None and len(payload)>MAX_BODY:raise ValueError('WORKER_BODY_TOO_LARGE')
        connection=self.factory(self.endpoint.hostname,self.endpoint.port or 443,
                                timeout=self.timeout,context=self.context)
        try:
            connection.request(method,path,body=payload,headers={'Authorization':'Bearer '+self.token,
                'Content-Type':'application/json' if isinstance(body,dict) else 'application/octet-stream'})
            response=connection.getresponse();raw=response.read(1024*1024+1)
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


class WorkerLedger:
    simulation=True
    """Worker-side durable idempotency and one execution lane; GET has no effects."""
    def __init__(self, root, token, session_id, resource_id):
        source=Path(root)
        if not source.is_absolute() or any(x.is_symlink() for x in (source,*source.parents)):raise ValueError('PRIVATE_WORKER_ROOT_REQUIRED')
        self.root=source.resolve();self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        if not ID.fullmatch(session_id) or len(token)<32:raise ValueError('WORKER_RUNTIME_IDENTITY_REQUIRED')
        self.token,self.session_id,self.resource_id=token,session_id,resource_id
        self.lock=threading.RLock();self.model_state='loading';self.executor=None
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
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,fingerprint TEXT NOT NULL,body TEXT NOT NULL,state TEXT NOT NULL)')
            # Crash during invocation is not evidence that it never ran.
            db.execute("UPDATE jobs SET state='uncertain' WHERE state='dispatching'")

    @contextmanager
    def db(self):
        db=sqlite3.connect(self.root/'worker.sqlite3',timeout=5)
        db.execute('PRAGMA synchronous=FULL')
        (self.root/'worker.sqlite3').chmod(0o600)
        try:
            with db:yield db
        finally:db.close()

    def close(self):self.lockfile.close()

    def health(self):return {'sessionId':self.session_id,'resourceId':self.resource_id,'modelState':self.model_state}

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
            else:db.execute('INSERT INTO jobs VALUES (?,?,?,?)',(value['jobId'],fingerprint,canonical(value),'queued'))
        return self.query(value['jobId'])

    def query(self, job_id):
        if not ID.fullmatch(job_id):raise JobError('JOB_NOT_FOUND','Job not found.',404)
        with self.db() as db:row=db.execute('SELECT body,state FROM jobs WHERE id=?',(job_id,)).fetchone()
        if not row:return {'status':'not_found'}
        return {**json.loads(row[0]),'status':row[1]}

    def run_one(self):
        with self.lock,self.db() as db:
            if self.executor is None or self.model_state!='ready':return
            if db.execute("SELECT 1 FROM jobs WHERE state IN ('dispatching','uncertain')").fetchone():return
            row=db.execute("SELECT id,body FROM jobs WHERE state='queued' ORDER BY rowid LIMIT 1").fetchone()
            if not row:return
            db.execute("UPDATE jobs SET state='dispatching' WHERE id=?",(row[0],));db.commit()
            try:
                outcome=self.executor(json.loads(row[1]))
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
