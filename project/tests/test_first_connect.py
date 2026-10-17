"""Offline tests: no cloud, SSH process, GPU, or model invocation."""
import hashlib
import io
import json
import ssl
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from first_connect_agent import Agent
from first_connect import FirstConnect
from gpu_bootstrap_package import archive


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.calls=0;self.relays=0
        self.runtime={'python':'/env/python','repo':'/model','checkpointDir':'/weights','cudaHome':'/env'}
        self.host={'vmId':'computeinstance-fixture','ip':'127.0.0.1'}
        self.q={'sessionId':'a'*32,'resourceId':'fixture','hostIdentity':self.host,'deadline':time.time()+300,'tlsBind':'127.0.0.1','tlsPort':9443}
        self.code=b'CODE';self.secret=self.make_secret()
        self.q.update(codeSha256=hashlib.sha256(self.code).hexdigest(),secretSha256=hashlib.sha256(self.secret).hexdigest())
        self.agent=self.new_agent()
    def make_secret(self,confirmed=True):
        grant=dict(sessionId='a'*32,resourceId='fixture',hostIdentity=self.host,expiresAt=self.q['deadline'],hostConfirmed=confirmed,modelLicenseAck=True)
        return archive({'worker.json':json.dumps({**self.runtime,'enabled':True,'executionMode':'resident'}).encode(),'model-grant.json':json.dumps(grant).encode(),'tls.crt':b'x','tls.key':b'x','worker.token':b'x','launch.json':b'{}'})
    def install(self,q,stream,root):
        self.calls+=1
        return dict(sessionId=q['sessionId'],resourceId=q['resourceId'],codeSha256=q['codeSha256'],launchRequested=True)
    def relay(self,*_):self.relays+=1
    def new_agent(self):return Agent(self.root/'agent','fixture',self.runtime,identity=lambda _:self.host['vmId'],installer=self.install,relay=self.relay)
    def test_identity_and_status_read_do_not_install(self):
        self.assertEqual(self.agent.public_identity()['vmId'],self.host['vmId'])
        self.assertEqual(self.agent.status('a'*32),{'status':'not_found'});self.assertEqual(self.calls,0)
    def test_first_install_without_ssh_and_persistent_replay(self):
        self.assertEqual(self.agent.install(self.q,self.code,self.secret)['status'],'installed')
        self.assertEqual(self.new_agent().install(self.q,self.code,self.secret)['status'],'installed')
        self.assertEqual((self.calls,self.relays),(1,1))
    def test_lost_ack_cannot_relaunch(self):
        def fail(*_):self.calls+=1;raise TimeoutError()
        self.agent.installer=fail
        with self.assertRaises(TimeoutError):self.agent.install(self.q,self.code,self.secret)
        self.assertEqual(self.new_agent().install(self.q,self.code,self.secret),{'status':'uncertain'})
        self.assertEqual(self.calls,1)
    def test_changed_payload_cannot_replay(self):
        self.agent.install(self.q,self.code,self.secret)
        with self.assertRaisesRegex(ValueError,'CONFLICT'):self.agent.install({**self.q,'deadline':self.q['deadline']+1},self.code,self.secret)
    def test_wrong_vm_rejected_before_side_effect(self):
        with self.assertRaisesRegex(ValueError,'IDENTITY'):self.agent.install({**self.q,'hostIdentity':{'vmId':'OTHER'}},self.code,self.secret)
        self.assertEqual(self.calls,0)
    def test_expired_or_extended_window_rejected(self):
        for deadline in (time.time()-1,time.time()+4000):
            with self.assertRaisesRegex(ValueError,'WINDOW'):self.agent.install({**self.q,'deadline':deadline},self.code,self.secret)
    def test_unconfirmed_host_rejected(self):
        secret=self.make_secret(False)
        with self.assertRaisesRegex(ValueError,'MANUAL'):self.agent.install({**self.q,'secretSha256':hashlib.sha256(secret).hexdigest()},self.code,secret)
        self.assertEqual(self.calls,0)
    def test_hash_or_runtime_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError,'HASH'):self.agent.install(self.q,b'changed',self.secret)
        self.agent.runtime={'python':'/different'}
        with self.assertRaisesRegex(ValueError,'RUNTIME'):self.agent.install(self.q,self.code,self.secret)
    def test_wsgi_limits_and_unknown_route(self):
        statuses=[];start=lambda status,headers:statuses.append(status)
        self.agent({'REQUEST_METHOD':'POST','PATH_INFO':'/bootstrap/v1/install','CONTENT_TYPE':'application/json','CONTENT_LENGTH':str(20*1024**2),'wsgi.input':io.BytesIO()},start)
        self.assertTrue(statuses[-1].startswith('409'));self.assertEqual(self.calls,0)


class RouteTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)
        self.ssh_calls=0;self.v={'hostIdentity':{'vmId':'VM'},'resourceId':'fixture'}
        def capture(sid):self.ssh_calls+=1
        self.ssh=SimpleNamespace(check=lambda sid,**_:self.v,directory=lambda sid:self.path,
            write=lambda path,obj:path.write_text(json.dumps(obj)),status=lambda *_,**__:None,capture=capture)
        self.router=FirstConnect.__new__(FirstConnect);self.router.ssh=self.ssh;self.router.config={'certificateSha256':'b'*64}
    def test_tls_identity_succeeds_with_ssh_fully_unavailable(self):
        self.router.request=lambda *_:{'protocol':1,'vmId':'VM','resourceId':'fixture'}
        self.router.capture('a'*32)
        self.assertEqual(self.router.route('a'*32),'mtls_image_agent');self.assertEqual(self.ssh_calls,0)
    def test_unreachable_agent_uses_only_one_ssh_capture(self):
        def fail(*_):raise ConnectionRefusedError()
        self.router.request=fail;self.router.capture('a'*32)
        self.assertEqual(self.router.route('a'*32),'ssh');self.assertEqual(self.ssh_calls,1)
    def test_certificate_failure_never_downgrades(self):
        def fail(*_):raise ssl.SSLError('invalid peer')
        self.router.request=fail
        with self.assertRaises(ssl.SSLError):self.router.capture('a'*32)
        self.assertEqual(self.ssh_calls,0)
    def test_wrong_vm_never_downgrades(self):
        self.router.request=lambda *_:{'protocol':1,'vmId':'OTHER','resourceId':'fixture'}
        with self.assertRaisesRegex(ValueError,'IDENTITY'):self.router.capture('a'*32)
        self.assertEqual(self.ssh_calls,0)

if __name__=='__main__':unittest.main()
