"""Image-started mTLS bootstrap, independent of SSH. No cloud credentials.

Must be provisioned in the GPU image/startup configuration BEFORE first boot.
Only the authenticated CPU may submit the fixed installer envelope, once.
"""
import hashlib
import io
import json
import sqlite3
import ssl
import struct
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from gpu_bootstrap_container import install_files, unpack
from gpu_bootstrap_vm import metadata_vm_id
from inference.jobs import ID
from worker_tls import PrivateTLS, SilentHandler
from security import runtime_file

MAX = 10 * 1024**2


class Agent:
    def __init__(self, root, resource, worker_runtime, identity=metadata_vm_id,
                 installer=install_files, clock=time.time, relay=None):
        self.root = Path(root)
        if not self.root.is_absolute() or any(p.is_symlink() for p in (self.root, *self.root.parents)):
            raise ValueError('PRIVATE_AGENT_ROOT_REQUIRED')
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.resource, self.runtime, self.identity = resource, worker_runtime, identity
        self.installer, self.clock, self.relay = installer, clock, relay
        self.lock = threading.Lock()
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS attempts(sid TEXT PRIMARY KEY, vm TEXT NOT NULL, fingerprint TEXT, body TEXT)')

    @contextmanager
    def db(self):
        p = self.root/'attempts.sqlite3'
        if p.is_symlink():raise ValueError('AGENT_DATABASE_SYMLINK')
        db = sqlite3.connect(p, timeout=5)
        db.execute('PRAGMA synchronous=FULL');p.chmod(0o600)
        try:
            with db:yield db
        finally:db.close()

    def public_identity(self):
        return {'protocol':1, 'resourceId':self.resource, 'vmId':self.identity(self.clock()+2)}

    def status(self, sid):
        if not ID.fullmatch(sid):raise ValueError('SESSION_INVALID')
        with self.db() as db:row=db.execute('SELECT body FROM attempts WHERE sid=?',(sid,)).fetchone()
        return json.loads(row[0]) if row else {'status':'not_found'}

    def install(self, q, code, secret):
        required={'sessionId','resourceId','hostIdentity','deadline','tlsBind','tlsPort','codeSha256','secretSha256'}
        now=self.clock()
        if not isinstance(q,dict) or set(q)!=required or not ID.fullmatch(q.get('sessionId','')):
            raise ValueError('INSTALL_ENVELOPE_INVALID')
        if q['resourceId']!=self.resource or q['hostIdentity'].get('vmId')!=self.public_identity()['vmId']:
            raise ValueError('CURRENT_VM_IDENTITY_MISMATCH')
        if type(q['deadline']) not in (int,float) or not now<q['deadline']<=now+3600:
            raise ValueError('FIXED_AGENT_WINDOW_REQUIRED')
        if q['tlsBind']!='127.0.0.1' or q['tlsPort']!=9443:
            raise ValueError('PRIVATE_WORKER_BINDING_REQUIRED')
        if len(code)>8*1024**2 or len(secret)>1024**2 or any(hashlib.sha256(raw).hexdigest()!=q[key] for raw,key in [(code,'codeSha256'),(secret,'secretSha256')]):
            raise ValueError('AGENT_ARCHIVE_HASH_MISMATCH')
        # Check runtime paths and current manual host approval BEFORE reserving an install.
        import tempfile
        with tempfile.TemporaryDirectory(dir=self.root) as td:
            files=unpack(secret,Path(td)/'checked',{'worker.json','model-grant.json','tls.crt','tls.key','worker.token','launch.json'},limit=1024**2)
            w=json.loads(files['worker.json']);g=json.loads(files['model-grant.json'])
            if any(w.get(k)!=v for k,v in self.runtime.items()) or w.get('enabled') is not True or w.get('executionMode')!='resident':
                raise ValueError('PROVISIONED_RUNTIME_MISMATCH')
            if (g.get('sessionId')!=q['sessionId'] or g.get('resourceId')!=self.resource or
                g.get('hostIdentity')!=q['hostIdentity'] or g.get('hostConfirmed') is not True or
                g.get('modelLicenseAck') is not True or not now<g.get('expiresAt',0)<=q['deadline']):
                raise ValueError('CURRENT_MANUAL_GRANT_REQUIRED')
        sid=q['sessionId'];vm=q['hostIdentity']['vmId'];fingerprint=hashlib.sha256(json.dumps(q,sort_keys=True).encode()).hexdigest()
        with self.lock:
            with self.db() as db:
                db.execute('BEGIN IMMEDIATE')
                old=db.execute('SELECT fingerprint,body FROM attempts WHERE sid=?',(sid,)).fetchone()
                if old:
                    if old[0]!=fingerprint:raise ValueError('INSTALL_CONFLICT')
                    return json.loads(old[1])
                if db.execute('SELECT 1 FROM attempts WHERE vm=? LIMIT 1',(vm,)).fetchone():raise ValueError('NODE_ALREADY_USED')
                db.execute('INSERT INTO attempts VALUES (?,?,?,?)',(sid,vm,fingerprint,json.dumps({'status':'uncertain'})))
            # Durable latch before installation. Never replay after a lost ACK/restart.
            stream=io.BytesIO(struct.pack('!Q',len(code))+code+struct.pack('!Q',len(secret))+secret)
            result=self.installer(q,stream,self.root/'sessions')
            if not self.relay:raise ValueError('PROVISIONED_RELAY_REQUIRED')
            self.relay(q,self.root/'sessions'/sid/'secrets')
            result={**result,'status':'installed'}
            with self.db() as db:db.execute('UPDATE attempts SET body=? WHERE sid=?',(json.dumps(result),sid))
            return result

    def __call__(self, e, start):
        try:
            path=e.get('PATH_INFO','');method=e.get('REQUEST_METHOD')
            if e.get('QUERY_STRING'):raise ValueError('QUERY_FORBIDDEN')
            if method=='GET' and path=='/bootstrap/v1/identity':value=self.public_identity()
            elif method=='GET' and path.startswith('/bootstrap/v1/status/'):
                value=self.status(path.rsplit('/',1)[1])
            elif method=='POST' and path=='/bootstrap/v1/install':
                if e.get('CONTENT_TYPE')!='application/json':raise ValueError('JSON_REQUIRED')
                n=e.get('CONTENT_LENGTH','')
                if not n.isdecimal() or not 0<int(n)<=14*1024**2:raise ValueError('BODY_LIMIT')
                raw=e['wsgi.input'].read(int(n))
                if len(raw)!=int(n):raise ValueError('TRUNCATED_BODY')
                import base64
                body=json.loads(raw)
                if set(body)!={'request','code','secret'}:raise ValueError('ENVELOPE_INVALID')
                value=self.install(body['request'],base64.b64decode(body['code'],validate=True),base64.b64decode(body['secret'],validate=True))
            else:start('404 Not Found',[]);return [b'']
            raw=json.dumps(value).encode();start('200 OK',[('Content-Type','application/json')]);return [raw]
        except Exception:
            # No raw errors, paths, payloads, tokens or private keys over the wire.
            start('409 Conflict',[('Content-Type','application/json')]);return [b'{"error":"BOOTSTRAP_REJECTED_OR_UNCERTAIN"}']


def main():
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);args=p.parse_args()
    root=Path(__file__).resolve().parents[1];cfg=json.loads(runtime_file(args.config,root))
    required={'schemaVersion','enabled','dataRoot','resourceId','bind','port','serverCertificate','serverKey','clientCa','workerRuntime','relayPort'}
    if set(cfg)!=required or cfg['schemaVersion']!=1 or cfg['enabled'] is not True or cfg['port']!=8443 or cfg['relayPort']!=443 or cfg['bind'] not in ('0.0.0.0','127.0.0.1'):
        raise ValueError('EXPLICIT_IMAGE_AGENT_CONFIG_REQUIRED')
    if set(cfg['workerRuntime'])!={'python','repo','checkpointDir','cudaHome'}:raise ValueError('EXPLICIT_WORKER_RUNTIME_REQUIRED')
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.minimum_version=ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(cfg['serverCertificate'],cfg['serverKey']);context.load_verify_locations(cfg['clientCa']);context.verify_mode=ssl.CERT_REQUIRED
    relays=[]
    def relay(q,secrets):
        from mtls_relay import create_relay
        server=create_relay(dict(bind=cfg['bind'],port=443,serverCertificate=cfg['serverCertificate'],serverKey=cfg['serverKey'],clientCa=cfg['clientCa'],workerCa=str(secrets/'tls.crt'),workerIp='127.0.0.1',workerPort=9443,workerName='localhost',deadline=q['deadline']),root)
        t=threading.Thread(target=server.serve_forever,daemon=True);t.start();relays.append(server)
        timer=threading.Timer(max(.01,q['deadline']-time.time()),server.shutdown);timer.daemon=True;timer.start()
    agent=Agent(cfg['dataRoot'],cfg['resourceId'],cfg['workerRuntime'],relay=relay)
    server=PrivateTLS((cfg['bind'],8443),SilentHandler);server.set_app(agent)
    server.socket=context.wrap_socket(server.socket,server_side=True,do_handshake_on_connect=False)
    try:server.serve_forever(poll_interval=.2)
    finally:
        server.server_close()
        for item in relays:item.shutdown();item.server_close()
