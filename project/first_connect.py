"""Optional preprovisioned mTLS first connection; SSH is a separate fallback.

Identity reads may fail over; an attempted install NEVER fails over or retries.
"""
import base64
import hashlib
import http.client
import json
from pathlib import Path
import ssl
import threading
import time

from gpu_bootstrap_package import archive, ROOT
from inference.jobs import JobError
from model_contract import grant_file
from security import runtime_file


class FirstConnect:
    def __init__(self, control, ssh, config):
        if set(config)!={'enabled','caFile','certificateSha256','clientCertificateFile','clientKeyFile'} or config['enabled'] is not True:
            raise ValueError('PREPROVISIONED_FIRST_CONNECT_REQUIRED')
        import re
        if not re.fullmatch('[a-f0-9]{64}',config['certificateSha256']):raise ValueError('FIRST_CONNECT_PIN_REQUIRED')
        self.control,self.ssh,self.config=control,ssh,dict(config)
        self.context=ssl.create_default_context(cafile=config['caFile'])
        self.context.load_cert_chain(config['clientCertificateFile'],config['clientKeyFile'])
        self.thread=None;self.lock=threading.Lock()

    def __getattr__(self,name):return getattr(self.ssh,name)

    def route(self,sid):
        try:return json.loads((self.directory(sid)/'first-route.json').read_text())['transport']
        except FileNotFoundError:return None

    def request(self,value,method,path,payload=None):
        if value.get('stopSent') or time.time()>=min(value['workDeadline'],value['absoluteDeadline'],self.control.scope['expiresAt']):
            raise ValueError('FIRST_CONNECT_WINDOW_CLOSED')
        connection=http.client.HTTPSConnection(value['hostIdentity']['ip'],8443,context=self.context,timeout=5)
        try:
            connection.connect()
            pin=hashlib.sha256(connection.sock.getpeercert(binary_form=True)).hexdigest()
            if pin!=self.config['certificateSha256']:raise ValueError('FIRST_CONNECT_CERTIFICATE_MISMATCH')
            raw=json.dumps(payload).encode() if payload is not None else None
            connection.request(method,path,body=raw,headers={'Content-Type':'application/json'})
            response=connection.getresponse();body=response.read(1024**2+1)
            if response.status!=200 or len(body)>1024**2:raise ValueError('FIRST_CONNECT_RESPONSE_UNCERTAIN')
            return json.loads(body)
        finally:connection.close()

    def check(self,sid,confirmed=False):
        if self.route(sid)!='mtls_image_agent':return self.ssh.check(sid,confirmed=confirmed)
        v=self.control.sessions.get(sid)
        if (self.ssh.stopped.is_set() or v.get('stopSent') or v.get('verifiedStopped') or
            v['state'] not in ('LOADING','READY','EXECUTING') or not 0<=time.time()-v['lastObservedAt']<=30 or
            time.time()>=min(v['workDeadline'],v['absoluteDeadline'],self.control.scope['expiresAt'])):
            raise ValueError('CURRENT_RUNNING_HOST_REQUIRED')
        q=json.loads((self.directory(sid)/'first-identity.json').read_text())
        if q['hostIdentity']!=v['hostIdentity'] or q['sessionId']!=sid:raise ValueError('FIRST_CONNECT_HOST_CHANGED')
        if confirmed and not v.get('hostConfirmed'):raise ValueError('CURRENT_HOST_CONFIRMATION_REQUIRED')
        return v

    def capture(self,sid):
        v=self.ssh.check(sid)
        # No writes/launches. Only a pinned mTLS identity GET before SSH fallback.
        try:
            identity=self.request(v,'GET','/bootstrap/v1/identity')
            if (identity.get('protocol')!=1 or identity.get('resourceId')!=v['resourceId'] or
                identity.get('vmId')!=v['hostIdentity']['vmId']):
                raise ValueError('FIRST_CONNECT_VM_IDENTITY_MISMATCH')
        except ssl.SSLError:
            raise  # Certificate/authentication failures are never downgraded to SSH.
        except (OSError,TimeoutError):
            self.ssh.write(self.directory(sid)/'first-route.json',{'transport':'ssh'})
            return self.ssh.capture(sid)
        # TLS/identity mismatches fail closed, not a reason to downgrade transport.
        self.ssh.write(self.directory(sid)/'first-identity.json',{'sessionId':sid,'hostIdentity':v['hostIdentity'],'fingerprint':'TLS-SHA256:'+self.config['certificateSha256']})
        self.ssh.write(self.directory(sid)/'first-route.json',{'transport':'mtls_image_agent'})
        self.ssh.status(sid,'awaiting_host_confirmation')

    def public(self,value):
        sid=value.get('sessionId')
        if not sid or self.route(sid)!='mtls_image_agent':return self.ssh.public(value)
        result={'stage':'uncertain','canConfirm':False,'transport':'mtls_image_agent'}
        try:
            v=self.check(sid);q=json.loads((self.directory(sid)/'first-identity.json').read_text())
            status=json.loads((self.directory(sid)/'status.json').read_text())
            return {**result,'stage':status['stage'],'canConfirm':not v.get('hostConfirmed') and status['stage']=='awaiting_host_confirmation',**q}
        except (OSError,ValueError,KeyError):return result

    def confirm(self,sid,host,fingerprint):
        if self.route(sid)!='mtls_image_agent':return self.ssh.confirm(sid,host,fingerprint)
        v=self.check(sid);q=json.loads((self.directory(sid)/'first-identity.json').read_text())
        if host!=v['hostIdentity'] or fingerprint!=q['fingerprint']:
            raise JobError('CURRENT_TLS_HOST_CONFIRMATION_REQUIRED','请核对本次主机与TLS指纹。',409)

    def deploy(self,sid):
        v=self.check(sid,confirmed=True)
        self.control.model_grant_issuer.ensure(sid)
        m,code,cfg=self.ssh.preflight({'image':v['image']})
        grant=grant_file(self.settings['modelGrantFile'],sid,v['resourceId'])
        deadline=min(v['workDeadline'],v['absoluteDeadline'],self.control.scope['expiresAt'],grant['expiresAt'])
        if grant['hostIdentity']!=v['hostIdentity']:raise ValueError('CURRENT_GRANT_HOST_MISMATCH')
        secret=archive({'worker.json':json.dumps(cfg).encode(),'model-grant.json':json.dumps(grant).encode(),
            'tls.crt':runtime_file(self.settings['workerCertificateFile'],ROOT),'tls.key':runtime_file(self.settings['workerKeyFile'],ROOT),
            'worker.token':runtime_file(self.settings['workerTokenFile'],ROOT),'launch.json':json.dumps({'sessionId':sid,'deadline':deadline}).encode()})
        q={'sessionId':sid,'resourceId':v['resourceId'],'hostIdentity':v['hostIdentity'],'deadline':deadline,'tlsBind':'127.0.0.1','tlsPort':9443,'codeSha256':m['sha256'],'secretSha256':hashlib.sha256(secret).hexdigest()}
        self.ssh.attempt(sid,'first-install')
        # Any lost ACK remains uncertain. No SSH deployment or second POST afterward.
        result=self.request(v,'POST','/bootstrap/v1/install',{'request':q,'code':base64.b64encode(code).decode(),'secret':base64.b64encode(secret).decode()})
        if (result.get('status')!='installed' or result.get('sessionId')!=sid or
            result.get('resourceId')!=v['resourceId'] or result.get('codeSha256')!=m['sha256'] or result.get('launchRequested') is not True):
            raise ValueError('FIRST_CONNECT_INSTALL_UNCERTAIN')
        self.check(sid,confirmed=True)
        worker={'schemaVersion':1,'enabled':True,'sessionId':sid,'resourceId':v['resourceId'],'hostIdentity':v['hostIdentity'],
            'origin':'https://'+v['hostIdentity']['ip']+':443','tokenFile':self.settings['workerTokenFile'],
            'caFile':self.config['caFile'],'certificateSha256':self.config['certificateSha256'],
            'clientCertificateFile':self.config['clientCertificateFile'],'clientKeyFile':self.config['clientKeyFile']}
        self.ssh.write(self.control.sessions.worker.direct_file,worker)
        self.ssh.write(self.directory(sid)/'first-deployed.json',{'sessionId':sid,'codeSha256':m['sha256']})
        self.ssh.status(sid,'deployed_direct_https')

    def connected(self,sid):
        if self.route(sid)=='mtls_image_agent':return (self.directory(sid)/'first-deployed.json').is_file()
        return self.ssh.connected(sid)

    def step(self,value):
        sid=value.get('sessionId')
        if not sid:return
        if value.get('stopSent') or value.get('verifiedStopped'):return self.ssh.step(value)
        if value['state'] not in ('LOADING','READY','EXECUTING'):return
        if self.route(sid)=='ssh':return self.ssh.step(value)
        directory=self.directory(sid);directory.mkdir(mode=0o700,parents=True,exist_ok=True)
        with self.lock:
            if self.thread and self.thread.is_alive() or (directory/'first-failed.json').exists() or (directory/'first-deployed.json').exists():return
            def run():
                try:
                    if self.route(sid) is None:self.capture(sid)
                    elif value.get('hostConfirmed'):self.deploy(sid)
                except Exception:
                    self.ssh.write(directory/'first-failed.json',{'error':'FIRST_CONNECT_UNCERTAIN_NO_RETRY'})
                    self.ssh.status(sid,'uncertain',error='FIRST_CONNECT_UNCERTAIN_NO_RETRY')
            self.thread=threading.Thread(target=run,daemon=True);self.thread.start()

    def close(self):
        self.ssh.close()
        if self.thread:self.thread.join(timeout=1)
