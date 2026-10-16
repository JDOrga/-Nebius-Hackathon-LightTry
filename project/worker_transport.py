"""Optional session-bound direct HTTPS, SSH HTTPS fallback; never replay writes."""
import json
import time
import threading
from pathlib import Path
from urllib.parse import urlsplit
from security import runtime_file
from worker_link import HTTPSWorker,LinkUncertain

ROOT=Path(__file__).resolve().parent.parent

class DualHTTPSWorker:
    def __init__(self,ssh,direct_file,*,clock=time.time,factory=HTTPSWorker):
        self.lock=threading.RLock();self.ssh=ssh;self.direct_file=Path(direct_file);self.clock=clock;self.factory=factory
        self.simulation=ssh.simulation;self.direct=None;self.active=None;self.binding=None;self.state=None;self.direct_available=False;self.valid_session=False

    # Bootstrap validates the SSH endpoint, never the public direct endpoint.
    @property
    def endpoint(self):return self.ssh.endpoint
    @property
    def certificate_sha256(self):return self.ssh.certificate_sha256
    @property
    def token(self):return self.ssh.token

    def bind_session(self,value):
        with self.lock:return self._bind_session(value)

    def _bind_session(self,value):
        binding={k:value.get(k) for k in ('sessionId','resourceId','hostIdentity')}
        if binding!=self.binding:self.active=None;self.direct=None
        self.binding=binding;self.direct_available=False;self.valid_session=False
        if not value.get('hostConfirmed') or value.get('stopSent') or self.clock()>=min(value.get('workDeadline') or 0,value.get('absoluteDeadline') or 0):
            self.active=None;self.direct=None;return
        self.valid_session=True
        raw=runtime_file(self.direct_file,ROOT,65536);cfg=json.loads(raw)
        if cfg=={'schemaVersion':1,'enabled':False}:
            if self.active and self.active[0]=='direct_https':self.active=None
            self.direct=None;return
        required={'schemaVersion','enabled','sessionId','resourceId','hostIdentity','origin','tokenFile','caFile','certificateSha256','clientCertificateFile','clientKeyFile'}
        if set(cfg)!=required or cfg['schemaVersion']!=1 or cfg['enabled'] is not True or any(cfg[k]!=binding[k] for k in binding):raise ValueError('DIRECT_CURRENT_SESSION_BINDING_REQUIRED')
        if any(not isinstance(cfg[k],str) or not cfg[k] for k in ('clientCertificateFile','clientKeyFile')):raise ValueError('DIRECT_MTLS_CLIENT_IDENTITY_REQUIRED')
        if urlsplit(cfg['origin']).hostname!=binding['hostIdentity']['ip']:raise ValueError('DIRECT_CURRENT_IP_REQUIRED')
        identity=json.dumps(cfg,sort_keys=True)
        if self.direct is None or getattr(self,'direct_identity',None)!=identity:
            self.active=None;self.direct=self.factory(cfg['origin'],runtime_file(cfg['tokenFile'],ROOT,4096).decode().strip(),ca_file=cfg['caFile'],certificate_sha256=cfg['certificateSha256'],client_certificate=cfg['clientCertificateFile'],client_key=cfg['clientKeyFile'],timeout=5);self.direct_identity=identity
        self.direct_available=True

    def health(self):
        with self.lock:return self._health()

    def _health(self):
        if self.state:self.bind_session(self.state())
        if not self.valid_session:raise LinkUncertain('CURRENT_SESSION_NOT_ACTIVE')
        self.active=None
        for name,client in [('direct_https',self.direct),('ssh_https',self.ssh)]:
            if client is None:continue
            try:h=client.health()
            except LinkUncertain:continue
            if self.binding is None or any(h.get(k)!=v for k,v in self.binding.items()):raise ValueError('WORKER_SESSION_MISMATCH')
            self.active=(name,client);return h
        raise LinkUncertain('ALL_WORKER_TRANSPORTS_UNAVAILABLE')

    @property
    def active_transport(self):return self.active[0] if self.active else None

    def _call(self,method,*args):
        with self.lock:return self._locked_call(method,*args)

    def _locked_call(self,method,*args):
        # A failed mutation is uncertain. Caller queries the SAME job id, never retries POST.
        if self.state:self.bind_session(self.state())
        if self.active is None:self.health()
        return getattr(self.active[1],method)(*args)

    def submit(self,envelope):return self._call('submit',envelope)
    def upload(self,payload):return self._call('upload',payload)
    def query(self,job_id):return self._call('query',job_id)
    def download(self,sha):return self._call('download',sha)
