"""Current-host bootstrap doubles + real local TLS. ZERO real SSH/cloud/model calls."""
import base64
import copy
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import sys
import tarfile
import tempfile
import threading
import struct
import time
import unittest
from types import SimpleNamespace
from urllib.parse import urlsplit
from unittest.mock import Mock,patch

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'project'))
from gpu_bootstrap_package import build,archive
from gpu_bootstrap_ssh import SSHBootstrap,host_key
from gpu_bootstrap_container import unpack,install_files
from worker_tls import create_server,private_bind
from worker_link import WorkerLedger,HTTPSWorker,LinkUncertain
from inference.jobs import atomic,read,JobError


class TLSFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        openssl=shutil.which('openssl') or ('C:/Program Files/Git/usr/bin/openssl.exe' if Path('C:/Program Files/Git/usr/bin/openssl.exe').is_file() else None)
        if not openssl:raise unittest.SkipTest('Local OpenSSL unavailable')
        cls.cert_tmp=tempfile.TemporaryDirectory();r=Path(cls.cert_tmp.name);cls.cert=r/'cert.pem';cls.key=r/'key.pem'
        result=subprocess.run([openssl,'req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(cls.key),'-out',str(cls.cert),
            '-days','1','-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost'],capture_output=True,timeout=15)
        if result.returncode:raise RuntimeError('SYNTHETIC_CERTIFICATE_CREATION_FAILED')
        cls.cert.chmod(0o600);cls.key.chmod(0o600)
        cls.pin=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cls.cert.read_text())).hexdigest()
    @classmethod
    def tearDownClass(cls):cls.cert_tmp.cleanup()


class BootstrapTests(TLSFixture):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);(self.root/'guard').mkdir(mode=0o700)
        self.sid='b'*32;self.host={'resourceId':'RESOURCE_FIXTURE','vmId':'computeinstance-fixture','ip':'203.0.113.77',
            'sshUser':'nebius','authorizedKeySha256':'f'*64}
        self.value={'sessionId':self.sid,'scopeId':'a'*32,'resourceId':'RESOURCE_FIXTURE','state':'LOADING','hostIdentity':self.host,
            'hostConfirmed':False,'lastObservedAt':100,'workDeadline':300,'absoluteDeadline':400,'stopSent':False,
            'verifiedStopped':False,'image':'FIXTURE/image:1'}
        self.token='SYNTHETIC_BOOTSTRAP_TOKEN_'+'X'*40
        worker=SimpleNamespace(endpoint=urlsplit('https://localhost:19080'),certificate_sha256=self.pin,token=self.token)
        self.sessions=SimpleNamespace(root=self.root/'guard',worker=worker,get=lambda sid:copy.deepcopy(self.value))
        self.control=SimpleNamespace(sessions=self.sessions,scope={'scopeId':'a'*32,'resourceId':'RESOURCE_FIXTURE','expiresAt':400},clock=lambda:100)
        self.bundle=build(self.root/'package')
        self.cfg={'schemaVersion':1,'enabled':True,'executionMode':'resident','python':'/home/jovyan/model/bin/python',
            'repo':'/home/jovyan/model/source','checkpointDir':'/home/jovyan/model/checkpoints','cudaHome':'/home/jovyan/model',
            'grantFile':str(self.root/'grant.json')}
        self.grant={'schemaVersion':1,'sessionId':self.sid,'resourceId':'RESOURCE_FIXTURE','hostIdentity':self.host,
            'hostConfirmed':True,'modelLicenseAck':True,'expiresAt':200,'budgetUsdIncludingTax':3,'approvalReference':'SYNTHETIC_ONLY',
            'maxJobs':1,'allowedOriginalSha256':['c'*64],'allowedRecipeKeys':['d'*64],
            'allowedMetadata':[{'owner':'lighttry','fingerprint':'e'*64}]}
        for name,data in [('client.key',b'SYNTHETIC_CLIENT_KEY'),('token',self.token.encode()),('worker.json',json.dumps(self.cfg).encode()),('grant.json',json.dumps(self.grant).encode())]:
            path=self.root/name;path.write_bytes(data);path.chmod(0o600)
        self.binding={'sshExecutable':sys.executable,'scpExecutable':sys.executable,'keyscanExecutable':sys.executable,
            'keyFile':str(self.root/'client.key'),'bundleManifestFile':str(self.root/'package/bundle.json'),
            'workerConfigFile':str(self.root/'worker.json'),'modelGrantFile':str(self.root/'grant.json'),
            'workerTokenFile':str(self.root/'token'),'workerCertificateFile':str(self.cert),'workerKeyFile':str(self.key),
            'tunnelPort':19080,'workerPort':9443,'expectedImage':'FIXTURE/image:1'}
        self.bootstrap=SSHBootstrap(self.control,self.binding)
        self.key_data=base64.b64encode(b'\0\0\0\x0bssh-ed25519\0\0\0 '+b'x'*32).decode()
        self.calls=[];self.bootstrap.runner=Mock(side_effect=self.fake_run)
        self.child=Mock(pid=333);self.child.poll.return_value=None;self.bootstrap.spawn=Mock(return_value=self.child)
    def tearDown(self):self.bootstrap.close();self.tmp.cleanup()
    def fake_run(self,command,**kw):
        self.calls.append(command)
        self.assertFalse(kw['shell']);self.assertLessEqual(kw['timeout'],20)
        if '-T' in command:raw=(self.host['ip']+' ssh-ed25519 '+self.key_data+'\n').encode()
        elif command[-1].startswith('python3 -B - '):
            q=json.loads(base64.b64decode(command[-1].split()[-1]))
            self.assertIn('StrictHostKeyChecking=yes',command)
            self.assertNotIn(self.token,' '.join(command))
            if q['operation']=='prepare':raw=json.dumps({'sessionId':self.sid,'containerId':'1'*64,'tlsBind':'172.17.0.2',
                'uploadDirectory':'/home/nebius/lighttry-bootstrap-'+self.sid,'observedAt':100}).encode()
            else:raw=json.dumps({'sessionId':self.sid,'resourceId':'RESOURCE_FIXTURE','codeSha256':q['codeSha256'],
                'launchRequested':True,'workerPid':123,'tlsBind':q['tlsBind']}).encode()
        else:raw=b''
        return SimpleNamespace(returncode=0,stdout=raw,stderr=b'')
    def capture(self):
        self.bootstrap.step(copy.deepcopy(self.value));self.bootstrap.thread.join(3)
        result=self.bootstrap.public(self.value);self.assertTrue(result['canConfirm']);return result
    def confirmed(self):
        candidate=self.capture();self.bootstrap.confirm(self.sid,self.host,candidate['fingerprint']);self.value['hostConfirmed']=True
    def test_previous_session_deadline_does_not_block_new_host_capture(self):
        self.bootstrap.deploy_deadline=99
        self.bootstrap.deployment_session='9'*32
        candidate=self.capture()
        self.assertTrue(candidate['canConfirm']);self.assertEqual(len(self.calls),1)
        self.assertLessEqual(self.bootstrap.runner.call_args.kwargs['timeout'],20)
    def test_same_session_expired_deploy_deadline_still_blocks(self):
        self.bootstrap.deploy_deadline=99;self.bootstrap.deployment_session=self.sid
        self.bootstrap.step(self.value);self.bootstrap.thread.join(3)
        self.bootstrap.runner.assert_not_called()
        self.assertEqual(read(self.bootstrap.directory(self.sid)/'status.json')['stage'],'uncertain')

    def test_confirmation_state_race_is_explicit_conflict_and_never_pins_or_deploys(self):
        candidate=self.capture();self.value['state']='UNKNOWN'
        with self.assertRaises(JobError) as caught:self.bootstrap.confirm(self.sid,self.host,candidate['fingerprint'])
        self.assertEqual(caught.exception.http,409);self.assertEqual(caught.exception.code,'CURRENT_HOST_STATE_UNAVAILABLE')
        self.assertFalse((self.bootstrap.directory(self.sid)/'known_hosts').exists())
        self.assertFalse((self.bootstrap.directory(self.sid)/'prepare-attempt').exists());self.bootstrap.spawn.assert_not_called()

    def test_construct_and_get_are_passive_and_require_exact_pin(self):
        self.bootstrap.public(self.value);self.bootstrap.runner.assert_not_called();self.bootstrap.spawn.assert_not_called()
        self.sessions.worker.certificate_sha256='0'*64
        with self.assertRaisesRegex(ValueError,'BOOTSTRAP_HTTPS_BINDING_MISMATCH'):SSHBootstrap(self.control,self.binding)
    def test_capture_requires_current_manual_confirmation_before_any_deployment(self):
        result=self.capture();self.assertEqual(len(self.calls),1)
        self.bootstrap.step(self.value);self.bootstrap.thread.join(3);self.assertEqual(len(self.calls),1)
        with self.assertRaises(JobError):self.bootstrap.confirm(self.sid,self.host,'SHA256:WRONG')
        self.assertFalse((self.bootstrap.directory(self.sid)/'known_hosts').exists())
        self.bootstrap.confirm(self.sid,self.host,result['fingerprint']);self.assertEqual(len(self.calls),1)
        self.assertIn('lighttry-'+self.sid,(self.bootstrap.directory(self.sid)/'known_hosts').read_text())
    def test_deploy_and_tunnel_each_once_then_dead_tunnel_never_reconnects(self):
        self.confirmed();self.bootstrap.step(self.value);self.bootstrap.thread.join(5)
        state=read(self.bootstrap.directory(self.sid)/'status.json');self.assertEqual(state['stage'],'deployed',state)
        self.assertEqual(len(self.calls),4);self.bootstrap.spawn.assert_called_once()
        self.assertTrue(self.bootstrap.connected(self.sid))
        self.bootstrap.step(self.value);self.assertEqual(len(self.calls),4)
        self.child.poll.return_value=255;self.bootstrap.step(self.value)
        self.assertEqual(read(self.bootstrap.directory(self.sid)/'status.json')['stage'],'uncertain')
        self.bootstrap.spawn.assert_called_once();self.assertFalse(self.bootstrap.connected(self.sid))
    def test_auto_direct_hook_is_after_worker_once_and_revoked_at_stop(self):
        self.confirmed();direct=Mock();self.control.direct_bootstrap=direct
        self.bootstrap.step(self.value);self.bootstrap.thread.join(5)
        direct.deploy.assert_called_once();self.bootstrap.spawn.assert_called_once()
        self.bootstrap.step(self.value);direct.deploy.assert_called_once()
        self.bootstrap.write(self.bootstrap.directory(self.sid)/'direct-ready.json',{'sessionId':self.sid})
        self.sessions.worker.direct_available=True;self.child.poll.return_value=255
        self.bootstrap.step(self.value)
        self.assertEqual(read(self.bootstrap.directory(self.sid)/'status.json')['stage'],'direct_https_configured_ssh_unavailable')
        self.value['stopSent']=True;self.bootstrap.step(self.value);direct.revoke.assert_called_once_with(self.sid)
    def test_failed_install_ack_is_not_reissued_after_restart(self):
        self.confirmed()
        original=self.bootstrap.runner.side_effect
        def fail(command,**kw):
            if command[-1].startswith('python3 -B - '):
                q=json.loads(base64.b64decode(command[-1].split()[-1]))
                if q['operation']=='install':self.calls.append(command);raise subprocess.TimeoutExpired('SYNTHETIC',1)
            return original(command,**kw)
        self.bootstrap.runner.side_effect=fail;self.bootstrap.step(self.value);self.bootstrap.thread.join(5)
        self.assertEqual(len(self.calls),4);self.bootstrap.spawn.assert_not_called()
        restarted=SSHBootstrap(self.control,self.binding);restarted.runner=Mock();restarted.spawn=Mock()
        try:restarted.step(self.value);restarted.runner.assert_not_called();restarted.spawn.assert_not_called()
        finally:restarted.close()
    def test_reviewed_remote_error_label_is_retained_without_raw_credentials(self):
        self.confirmed()
        self.bootstrap.runner=Mock(return_value=SimpleNamespace(returncode=3,stdout=b'',stderr=b'CURRENT_VM_IDENTITY_MISMATCH\n'))
        self.bootstrap.step(self.value);self.bootstrap.thread.join(3)
        detail=read(self.bootstrap.directory(self.sid)/'remote-error.json')
        self.assertEqual(detail['safeLabel'],'CURRENT_VM_IDENTITY_MISMATCH');self.assertEqual(detail['exitCode'],3)
        self.assertFalse(detail['stderrRecorded']);self.bootstrap.spawn.assert_not_called()
    def test_arbitrary_remote_stderr_never_enters_receipt_or_error(self):
        self.confirmed();secret=b'PRIVATE_TOKEN_OR_AUTH_URL current-host-error'
        self.bootstrap.runner=Mock(return_value=SimpleNamespace(returncode=255,stdout=b'',stderr=secret))
        self.bootstrap.step(self.value);self.bootstrap.thread.join(3)
        raw=(self.bootstrap.directory(self.sid)/'remote-error.json').read_bytes()
        self.assertNotIn(secret,raw);self.assertEqual(json.loads(raw)['safeLabel'],'UNRECOGNIZED_REMOTE_ERROR')
        self.bootstrap.step(self.value);self.bootstrap.runner.assert_called_once();self.bootstrap.spawn.assert_not_called()

    def test_changed_host_stop_scope_or_stale_snapshot_rejects_before_ssh(self):
        for key,value in [('stopSent',True),('lastObservedAt',50),('scopeId','c'*32),('image','OTHER')]:
            with self.subTest(key=key):
                prior=self.value[key];self.value[key]=value
                with self.assertRaises(ValueError):self.bootstrap.capture(self.sid)
                self.value[key]=prior
        self.bootstrap.runner.assert_not_called()
    def test_changed_token_blocks_upload_before_any_remote_mutation(self):
        self.confirmed();(self.root/'token').write_text('CHANGED')
        self.bootstrap.step(self.value);self.bootstrap.thread.join(5)
        self.assertEqual(len(self.calls),1);self.bootstrap.spawn.assert_not_called()
        self.assertEqual(read(self.bootstrap.directory(self.sid)/'failed.json')['error'],'FROZEN_BOOTSTRAP_BINDING_CHANGED')


class PackageTests(unittest.TestCase):
    def test_remote_container_install_is_one_launch_with_explicit_tls_and_no_model_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);bundle=build(root/'package');code=Path(bundle['archive']).read_bytes()
            sid='a'*32;host={'vmId':'SYNTHETIC_VM'}
            grant={'sessionId':sid,'resourceId':'RESOURCE_FIXTURE','hostIdentity':host,'hostConfirmed':True,
                   'modelLicenseAck':True,'expiresAt':time.time()+60}
            cfg={'enabled':True,'executionMode':'resident','python':'SYNTHETIC_MODEL_PYTHON'}
            files={'worker.json':json.dumps(cfg).encode(),'model-grant.json':json.dumps(grant).encode(),
                'tls.crt':b'SYNTHETIC_CERT','tls.key':b'SYNTHETIC_KEY','worker.token':b'SYNTHETIC_TOKEN','launch.json':b'{}'}
            secret=archive(files)
            q={'sessionId':sid,'resourceId':'RESOURCE_FIXTURE','hostIdentity':host,'deadline':time.time()+120,
               'codeSha256':hashlib.sha256(code).hexdigest(),'secretSha256':hashlib.sha256(secret).hexdigest(),
               'tlsBind':'127.0.0.1','tlsPort':0}
            stream=lambda:io.BytesIO(struct.pack('!Q',len(code))+code+struct.pack('!Q',len(secret))+secret)
            with patch('gpu_bootstrap_container.subprocess.Popen',return_value=SimpleNamespace(pid=12345)) as spawn:
                receipt=install_files(q,stream(),root/'deployed')
                self.assertTrue(receipt['launchRequested']);spawn.assert_called_once()
                command=spawn.call_args.args[0]
                self.assertIn('--worker-tls-cert',command);self.assertIn('--worker-tls-bind',command)
                self.assertIn('--worker-config',command);self.assertFalse(spawn.call_args.kwargs['shell'])
                with self.assertRaises(FileExistsError):install_files(q,stream(),root/'deployed')
                spawn.assert_called_once()
            self.assertTrue((root/'deployed'/sid/'launch-attempt').exists())

    def test_reviewed_container_selector_rejects_foreign_image_and_public_network(self):
        namespace={'__name__':'bootstrap_fixture'}
        probe=(ROOT/'cloud/remote_probe.py').read_text();exec(probe[:probe.index('\nif __name__')],namespace)
        vm=(ROOT/'project/gpu_bootstrap_vm.py').read_text();exec(vm[:vm.index('\nif __name__')],namespace)
        item={'Id':'1'*64,'State':{'Running':True},'Config':{'Image':'FIXTURE_IMAGE','User':'jovyan'},
              'Mounts':[{'Destination':'/home','RW':True}],'HostConfig':{'NetworkMode':'bridge'},
              'NetworkSettings':{'Networks':{'bridge':{'IPAddress':'172.17.0.2'}}}}
        choose=namespace['private_container']
        self.assertEqual(choose([item],'FIXTURE_IMAGE'),('1'*64,'172.17.0.2'))
        with self.assertRaises(ValueError):choose([item],'FOREIGN_IMAGE')
        item['HostConfig']['NetworkMode']='macvlan'
        with self.assertRaises(ValueError):choose([item],'FIXTURE_IMAGE')
        item['HostConfig']['NetworkMode']='bridge';item['NetworkSettings']['Networks']['bridge']['IPAddress']='8.8.8.8'
        with self.assertRaises(ValueError):choose([item],'FIXTURE_IMAGE')
    def test_source_bundle_deterministic_and_has_no_secret_or_weight_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);one=build(root/'one');two=build(root/'two')
            self.assertEqual(one['sha256'],two['sha256'])
            self.assertFalse(one['containsCredentials']);self.assertFalse(one['containsWeights'])
            self.assertTrue(any(v['path']=='project/worker_tls.py' for v in one['files']))
            for v in one['files']:self.assertFalse(v['path'].endswith(('.key','.pem','.pt','.pth','.ckpt','.safetensors')))
            contents=unpack(Path(one['archive']).read_bytes(),root/'unpacked')
            self.assertIn('start.py',contents);self.assertIn('project/resident_model.py',contents)
    def test_tar_links_traversal_and_expansion_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with self.assertRaises(ValueError):unpack(archive({'../escape.py':b'BAD'}),root/'escape')
            with self.assertRaisesRegex(ValueError,'BOOTSTRAP_EXPANSION_LIMIT'):
                unpack(gzip.compress(b'X'*(2*1024**2)),root/'large',limit=10)
    def test_current_ed25519_key_only(self):
        key=base64.b64encode(b'\0\0\0\x0bssh-ed25519\0\0\0 '+b'x'*32).decode()
        self.assertTrue(host_key('203.0.113.1 ssh-ed25519 '+key,'203.0.113.1')[1].startswith('SHA256:'))
        with self.assertRaises(ValueError):host_key('203.0.113.2 ssh-ed25519 '+key,'203.0.113.1')


class TLSIngressTests(TLSFixture):
    def test_actual_local_tls_auth_pin_blob_and_health_never_load_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger=WorkerLedger(Path(tmp)/'worker','SYNTHETIC_TLS_TOKEN_'+'X'*40,'a'*32,'RESOURCE_FIXTURE')
            server=create_server(ledger,self.cert,self.key,ROOT,port=0)
            thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.05},daemon=True);thread.start()
            try:
                url='https://localhost:'+str(server.server_port)
                client=HTTPSWorker(url,ledger.token,ca_file=str(self.cert),certificate_sha256=self.pin)
                self.assertFalse(client.health()['modelLoaded'])
                result=client.upload(b'SYNTHETIC_BYTES');self.assertEqual(client.download(result['sha256']),b'SYNTHETIC_BYTES')
                with self.assertRaises(LinkUncertain):HTTPSWorker(url,'SYNTHETIC_WRONG_'+'Y'*40,ca_file=str(self.cert)).health()
                with self.assertRaises(LinkUncertain):HTTPSWorker(url,ledger.token,ca_file=str(self.cert),certificate_sha256='0'*64).health()
                self.assertIsNone(ledger.executor)
            finally:server.shutdown();server.server_close();thread.join(3);ledger.close()
    def test_public_bind_forbidden(self):
        for host in ('0.0.0.0','8.8.8.8','::'):
            with self.assertRaises(ValueError):private_bind(host)


class GuardIdentityTests(unittest.TestCase):
    def test_running_and_freshness_use_response_time_and_startup_bound_is_not_extended(self):
        import test_worker_guard as fixtures
        f=fixtures.GuardTests();f.setUp()
        try:
            value=f.sessions.start(f.scope);f.provider.state='RUNNING';observe=f.provider.observe
            def slow(resource):f.clock.step(10);return observe(resource)
            f.provider.observe=slow
            running=f.sessions.poll(value['sessionId'])
            self.assertEqual(running['runningAt'],f.clock());self.assertEqual(running['lastObservedAt'],f.clock())
            self.assertEqual(running['startupDeadline'],value['startupDeadline'])
            self.assertEqual(running['absoluteDeadline'],value['absoluteDeadline'])
        finally:f.tearDown()
        f=fixtures.GuardTests();f.setUp()
        try:
            value=f.sessions.start(f.scope);f.provider.state='RUNNING';observe=f.provider.observe
            f.clock.step(value['startupDeadline']-f.clock()-10);f.sessions.heartbeat(value['sessionId'])
            def late(resource):f.clock.step(20);return observe(resource)
            f.provider.observe=late
            stopped=f.sessions.poll(value['sessionId'])
            self.assertTrue(stopped['stopSent']);self.assertIsNone(stopped['runningAt'])
            self.assertEqual(f.provider.stops,1);self.assertEqual(stopped['startupDeadline'],value['startupDeadline'])
        finally:f.tearDown()
    def test_heartbeat_during_slow_provider_observation_does_not_drop_guard_progress(self):
        import test_worker_guard as fixtures
        from gpu_session import Sessions
        f=fixtures.GuardTests();f.setUp();entered=threading.Event();release=threading.Event();errors=[];result=[]
        worker=None
        try:
            value=f.running();observe=f.provider.observe
            def slow(resource):entered.set();release.wait(3);return observe(resource)
            f.provider.observe=slow
            def poll():
                try:result.append(f.sessions.poll(value['sessionId']))
                except Exception as error:errors.append(error)
            worker=threading.Thread(target=poll);worker.start();self.assertTrue(entered.wait(2))
            f.clock.step(1)
            app=Sessions(f.sessions.root,f.provider,f.peer,f.fallback,f.clock)
            app.heartbeat(value['sessionId']);release.set();worker.join(3)
            self.assertEqual(errors,[]);self.assertEqual(result[0]['state'],'READY')
            self.assertEqual(app.get(value['sessionId'])['cpuHeartbeatAt'],f.clock())
        finally:
            release.set()
            if worker:worker.join(3)
            f.tearDown()
    def test_bootstrap_preflight_failure_cuts_off_start_before_provider_mutation(self):
        import test_worker_guard as fixtures
        f=fixtures.GuardTests();f.setUp()
        try:
            f.sessions.bootstrap=SimpleNamespace(preflight=Mock(side_effect=ValueError('FROZEN_PREPARATION_INVALID')))
            result=f.sessions.start(f.scope)
            self.assertEqual(f.provider.starts,0);self.assertFalse(result['startSent'])
            self.assertEqual(result['state'],'UNKNOWN')
        finally:f.tearDown()
    def test_new_vm_stops_and_unowned_tunnel_cannot_mark_ready(self):
        import test_worker_guard as fixtures
        f=fixtures.GuardTests();f.setUp()
        try:
            value=f.running();b=Mock();b.connected.return_value=False;f.sessions.bootstrap=b
            value=f.sessions.poll(value['sessionId']);self.assertEqual(value['state'],'LOADING')
            b.connected.return_value=True;self.assertEqual(f.sessions.poll(value['sessionId'])['state'],'READY')
            original=f.provider.observe
            def foreign(resource):return {**original(resource),'hostIdentity':'FOREIGN_CURRENT_VM'}
            f.provider.observe=foreign
            stopped=f.sessions.poll(value['sessionId']);self.assertTrue(stopped['stopSent']);self.assertEqual(f.provider.stops,1)
        finally:f.tearDown()


if __name__=='__main__':unittest.main()
