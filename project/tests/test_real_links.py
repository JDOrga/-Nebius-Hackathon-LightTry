"""Real adapter code exercised only with synthetic CLI/model and loopback TLS."""
import copy
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
import gzip
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'project'))
from nebius_provider import NebiusProvider
from gpu_session import Sessions
from worker_link import WorkerLedger,WorkerApplication,HTTPSWorker,LinkUncertain
from gpu_model import CosmosWorkerExecutor
from https_executor import HTTPSCosmosExecutor
from model_contract import grant_file,check_request,pack_input,unpack_input,request_sha,validate_result_archive
from inference.jobs import RUN_CONFIG,JobError,atomic
from inference_fixture import image_bytes


class NebiusTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        for name,data in [('nebius','SYNTHETIC_NON_EXECUTED_CLI'),('config.yaml','profiles: {}'),('key.pub','ssh-ed25519 SYNTHETIC_PUBLIC_KEY')]:
            p=self.root/name;p.write_text(data);p.chmod(0o600)
        self.binding={'cliPath':str(self.root/'nebius'),'configFile':str(self.root/'config.yaml'),'profile':'fixture',
            'tenantId':'tenant-fixture','projectId':'project-fixture','resourceId':'devlab-fixture',
            'publicKeyFile':str(self.root/'key.pub'),'guardRoot':str(self.root/'guard')}
        self.provider=NebiusProvider(self.binding);self.provider.clock=lambda:100
        self.raw={'metadata':{'id':'devlab-fixture','parent_id':'project-fixture'},
                  'spec':{'image':'SYNTHETIC_IMAGE','workspace':{'container_path':'/home'},'ssh_authorized_keys':['ssh-ed25519 SYNTHETIC_PUBLIC_KEY']},
                  'status':{'state':'STOPPED','instances':[]}}
        def run(cmd,**kwargs):
            self.assertFalse(kwargs['shell']);self.assertLessEqual(kwargs['timeout'],6)
            self.assertIn('--no-browser',cmd);self.assertIn('--retries=1',cmd)
            if cmd[1:4]==['iam','v2','project']:
                value={'metadata':{'id':'project-fixture','parent_id':'tenant-fixture'}}
            elif cmd[1:4]==['ai','devlab','get']:value=self.raw
            else:return SimpleNamespace(returncode=0,stdout='SYNTHETIC_OPERATION_ID',stderr='')
            return SimpleNamespace(returncode=0,stdout=json.dumps(value),stderr='')
        self.provider.runner=Mock(side_effect=run)

    def tearDown(self):self.tmp.cleanup()

    def session(self):
        class Ready:
            simulation=False
            def arm(inner,sid,r,d,l):return {'sessionId':sid,'resourceId':r,'deadline':d,'leaseSeconds':l,
                'ready':True,'independentHost':False,'protectionMode':'cpu-only','cpuHostRiskAccepted':True,'simulation':False}
        return Sessions(self.root/'guard',self.provider,SimpleNamespace(simulation=False),Ready(),lambda:100,protection_mode='cpu-only')

    def test_constructor_is_offline(self):self.provider.runner.assert_not_called()

    def test_stopped_requires_project_key_and_explicit_empty_instances(self):
        value=self.provider.observe('devlab-fixture');self.assertEqual(value['state'],'STOPPED');self.assertTrue(value['independent'])
        self.raw['status']['instances']=None
        with self.assertRaises(ValueError):self.provider.observe('devlab-fixture')

    def test_wrong_project_key_resource_and_failed_state_fail_closed(self):
        with self.assertRaises(ValueError):self.provider.observe('OTHER')
        self.provider.runner.assert_not_called()
        self.raw['metadata']['parent_id']='OTHER'
        with self.assertRaises(ValueError):self.provider.observe('devlab-fixture')
        self.raw['metadata']['parent_id']='project-fixture';self.raw['spec']['ssh_authorized_keys']=[]
        with self.assertRaises(ValueError):self.provider.observe('devlab-fixture')
        self.raw['spec']['ssh_authorized_keys']=['ssh-ed25519 SYNTHETIC_PUBLIC_KEY'];self.raw['status']['state']='FAILED'
        with self.assertRaises(RuntimeError):self.provider.observe('devlab-fixture')

    def test_start_and_stop_each_latched_once_across_adapter_restart(self):
        session=self.session();scope={'scopeId':'a'*32,'resourceId':'devlab-fixture','expiresAt':2500,'budgetApproved':True,'idleSeconds':60,'simulation':False}
        value=session.start(scope);self.assertEqual(value['state'],'STARTING')
        other=NebiusProvider(self.binding);other.clock=lambda:100;other.runner=self.provider.runner
        other.start('devlab-fixture',value['sessionId'],value['absoluteDeadline'])
        session.request_stop(value['sessionId']);session.request_stop(value['sessionId'])
        operations=[c.args[0][3] for c in self.provider.runner.call_args_list if c.args[0][1:3]==['ai','devlab']]
        self.assertEqual(operations.count('restart'),1);self.assertEqual(operations.count('stop'),1)

    def test_uncertain_start_is_not_retried_and_stderr_is_not_exposed(self):
        original=self.provider.runner.side_effect
        def fail(cmd,**kwargs):
            if 'restart' in cmd:return SimpleNamespace(returncode=7,stdout='',stderr='PRIVATE_SECRET_AUTH_URL')
            return original(cmd,**kwargs)
        self.provider.runner.side_effect=fail
        session=self.session();scope={'scopeId':'a'*32,'resourceId':'devlab-fixture','expiresAt':2500,'budgetApproved':True,'idleSeconds':60,'simulation':False}
        value=session.start(scope);self.assertEqual(value['state'],'UNKNOWN')
        session.start(scope)
        self.assertEqual(sum('restart' in c.args[0] for c in self.provider.runner.call_args_list),1)
        with self.assertRaisesRegex(RuntimeError,'NEBIUS_AUTH_REQUIRED'):
            self.provider._call(['ai','devlab','restart'])

    def test_mutation_without_durable_session_never_calls_cli(self):
        with self.assertRaises(ValueError):self.provider.start('devlab-fixture','a'*32,200)
        self.provider.runner.assert_not_called()

    def test_current_running_vm_identity_is_api_bound_and_rechecked(self):
        self.raw['status']={'state':'RUNNING','instances':[{'compute_instance_id':'computeinstance-fixture',
            'state':'RUNNING','compute_instance_state':'RUNNING','public_ip':'203.0.113.77','private_ip':'192.0.2.5'}]}
        vm={'metadata':{'id':'computeinstance-fixture','parent_id':'project-fixture'},
            'spec':{'cloud_init_user_data':'users:\n  - name: fixture\n    ssh_authorized_keys:\n      - ssh-ed25519 SYNTHETIC_PUBLIC_KEY\n'},
            'status':{'state':'RUNNING','network_interfaces':[{'public_ip_address':{'address':'203.0.113.77'}}]}}
        original=self.provider.runner.side_effect
        def run(cmd,**kwargs):
            if cmd[1:4]==['compute','instance','get']:return SimpleNamespace(returncode=0,stdout=json.dumps(vm),stderr='')
            return original(cmd,**kwargs)
        self.provider.runner.side_effect=run
        value=self.provider.observe('devlab-fixture')
        self.assertEqual(value['hostIdentity']['vmId'],'computeinstance-fixture')
        self.assertEqual(value['hostIdentity']['ip'],'203.0.113.77')
        vm['status']['network_interfaces'][0]['public_ip_address']['address']='203.0.113.78'
        with self.assertRaises(ValueError):self.provider.observe('devlab-fixture')


class ModelTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.ledger=WorkerLedger(self.root/'gpu','SYNTHETIC_WORKER_TOKEN_'+'X'*40,'a'*32,'RESOURCE_FIXTURE')
        self.photo=image_bytes((1280,704));sha=hashlib.sha256(self.photo).hexdigest()
        self.request={'taskId':'b'*32,'nonce':'c'*32,'input':{'id':'e'*32,'sha256':sha},'original':{'sha256':sha},
            'runConfig':{**RUN_CONFIG,'weightVerification':'full','weightContentHashesChecked':True,'lightingAdapterVersion':'single-scheme-hdr-adapter-v1'},
            'preset':{'id':'fixture','recipeKey':hashlib.sha256(b'{}').hexdigest(),'parameters':{}}}
        self.request['presets']=[copy.deepcopy(self.request['preset'])]
        self.grant={'schemaVersion':1,'sessionId':'a'*32,'resourceId':'RESOURCE_FIXTURE','hostIdentity':{'vmId':'SYNTHETIC_VM'},
            'hostConfirmed':True,'modelLicenseAck':True,'expiresAt':time.time()+100,'budgetUsdIncludingTax':1,
            'approvalReference':'SYNTHETIC_TEST_ONLY','maxJobs':1,'allowedOriginalSha256':[sha],'allowedRecipeKeys':[hashlib.sha256(b'{}').hexdigest()],
            'allowedMetadata':[{'owner':'lighttry','fingerprint':'e'*64}]}
        self.grant_path=self.root/'grant.json';self.write_grant()
        self.folder=self.root/'cpu'/self.request['taskId'];(self.folder/'inputs').mkdir(parents=True)
        (self.folder/'inputs/photo.png').write_bytes(self.photo);atomic(self.folder/'request.json',self.request)
        self.config=self.root/'worker.json';self.config.write_text(json.dumps({'schemaVersion':1,'enabled':True,
            'python':sys.executable,'repo':str(self.root),'checkpointDir':str(self.root),'cudaHome':str(self.root),'grantFile':str(self.grant_path)}));self.config.chmod(0o600)
        self.state={'sessionId':'a'*32,'resourceId':'RESOURCE_FIXTURE','scopeId':'f'*32,'state':'READY','hostConfirmed':True,
            'hostIdentity':self.grant['hostIdentity'],'lastObservedAt':time.time(),'workDeadline':self.grant['expiresAt'],'absoluteDeadline':self.grant['expiresAt']}
        self.worker=Mock();self.worker.health.return_value={'sessionId':'a'*32,'resourceId':'RESOURCE_FIXTURE','hostIdentity':self.grant['hostIdentity'],
            'modelState':'ready','modelLoaded':True,'simulation':False,'executionMode':'resident'}  # Synthetic report, not a real loaded model.
        self.worker.upload.side_effect=lambda raw:{'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}
        self.control=SimpleNamespace(scope={'scopeId':'f'*32,'resourceId':'RESOURCE_FIXTURE','expiresAt':self.grant['expiresAt']},sessions=Mock())
        self.control.sessions.latest.side_effect=lambda:copy.deepcopy(self.state);self.control.sessions.worker=self.worker
        self.cpu=HTTPSCosmosExecutor(self.control,self.grant_path,self.folder.parent)

    def write_grant(self):self.grant_path.write_text(json.dumps(self.grant));self.grant_path.chmod(0o600)
    def test_cold_model_report_blocks_before_upload_or_dispatch(self):
        self.worker.health.return_value['modelLoaded']=False
        with self.assertRaisesRegex(ValueError,'RESIDENT_MODEL_NOT_READY'):self.cpu.submit(self.folder,self.request)
        self.worker.upload.assert_not_called();self.control.sessions.submit.assert_not_called()
        self.assertFalse((self.folder/'https-binding.json').exists())

    def tearDown(self):self.ledger.close();self.tmp.cleanup()
    def envelope(self,request=None):
        request=request or self.request;raw=pack_input(self.folder,request);sha=hashlib.sha256(raw).hexdigest();self.ledger.upload(sha,raw)
        return {'jobId':request['taskId'],'sessionId':'a'*32,'resourceId':'RESOURCE_FIXTURE','artifactSha256':sha,'requestSha256':request_sha(request)}

    def test_construction_and_preparation_do_not_load_or_launch_model(self):
        with patch('subprocess.Popen') as launch:
            executor=CosmosWorkerExecutor(self.ledger,self.config);envelope=self.envelope()
            prep,_=executor.prepare(envelope)
            self.assertTrue((prep/'project/runtime/worker.py').is_file());launch.assert_not_called()
            with self.assertRaises(FileExistsError):executor.prepare(envelope)

    def test_grant_expiry_license_input_recipe_and_seed_are_enforced(self):
        for key,value in [('expiresAt',0),('modelLicenseAck',False),('budgetUsdIncludingTax',0),('hostConfirmed',False)]:
            old=self.grant[key];self.grant[key]=value;self.write_grant()
            with self.assertRaises(ValueError):CosmosWorkerExecutor(self.ledger,self.config)
            self.grant[key]=old
        self.write_grant()
        for field,value in [('seed',123),('weightVerification','historical_metadata')]:
            request=copy.deepcopy(self.request);request['runConfig'][field]=value
            with self.assertRaises(ValueError):check_request(request,self.grant)
        request=copy.deepcopy(self.request);request['preset']['recipeKey']='0'*64
        with self.assertRaises(ValueError):check_request(request,self.grant)
        request=copy.deepcopy(self.request);request['preset']['parameters']={'strength':4}
        with self.assertRaises(ValueError):check_request(request,self.grant)

    def test_untrusted_tar_paths_code_and_symlinks_are_rejected(self):
        for name,kind in [('../escape',tarfile.REGTYPE),('project/runtime/worker.py',tarfile.REGTYPE),('request.json',tarfile.SYMTYPE)]:
            buffer=io.BytesIO()
            with tarfile.open(fileobj=buffer,mode='w:gz') as archive:
                member=tarfile.TarInfo(name);member.type=kind;member.size=0;archive.addfile(member,io.BytesIO())
            with self.assertRaises(ValueError):unpack_input(buffer.getvalue())

    def test_expansion_is_bounded_before_pax_or_member_parsing(self):
        payload=gzip.compress(b'\0'*(2*1024*1024+3000))
        with patch('model_contract.MAX',1000):
            with self.assertRaises(ValueError):validate_result_archive(payload)

    def test_artifact_request_hash_mismatch_cannot_dispatch(self):
        executor=CosmosWorkerExecutor(self.ledger,self.config);body=self.envelope();body['requestSha256']='0'*64
        with self.assertRaises(ValueError):executor.authorize(body)

    def test_worker_max_jobs_is_durable_and_duplicate_job_is_idempotent(self):
        executor=CosmosWorkerExecutor(self.ledger,self.config);self.ledger.executor=executor
        body=self.envelope();self.ledger.accept(body);self.ledger.accept(body)
        other=copy.deepcopy(self.request);other['taskId']='9'*32
        with self.assertRaises(JobError):self.ledger.accept(self.envelope(other))
        self.assertEqual(self.ledger.query(body['jobId'])['status'],'queued')

    def test_revoked_queued_job_becomes_uncertain_without_launch(self):
        executor=CosmosWorkerExecutor(self.ledger,self.config);self.ledger.executor=executor;self.ledger.model_state='ready'
        body=self.envelope();self.ledger.accept(body)
        self.grant['expiresAt']=0;self.write_grant()
        with patch('subprocess.Popen') as launch:self.ledger.run_one();launch.assert_not_called()
        self.assertEqual(self.ledger.query(body['jobId'])['status'],'uncertain')

    def test_known_model_failure_has_no_fake_success(self):
        executor=CosmosWorkerExecutor(self.ledger,self.config);self.ledger.executor=executor;self.ledger.model_state='ready'
        body=self.envelope();self.ledger.accept(body)
        def fail(prep,deadline):
            (prep/'run').mkdir();atomic(prep/'run/execution.json',{'taskId':self.request['taskId'],'nonce':self.request['nonce'],
                'status':'failed','executionStopped':True});return 1
        executor.launch=fail;self.ledger.run_one()
        self.assertEqual(self.ledger.query(body['jobId'])['status'],'failed')

    def test_cpu_owner_fingerprint_host_and_deadline_gate(self):
        self.assertTrue(self.cpu.authorize_job('lighttry',{},'e'*64));self.assertFalse(self.cpu.authorize_job('other',{},'e'*64))
        self.state['hostConfirmed']=False;self.assertFalse(self.cpu.authorize_job('lighttry',{},'e'*64))
        self.state['hostConfirmed']=True;self.state['workDeadline']=time.time()-1
        self.assertFalse(self.cpu.authorize_job('lighttry',{},'e'*64));self.worker.health.assert_not_called()

    def test_cpu_guard_loss_blocks_new_model_dispatch(self):
        self.control.sessions.protection_mode='cpu-only'
        self.control.sessions.fallback.receipt.side_effect=ValueError('CPU_GUARD_NOT_READY')
        self.assertFalse(self.cpu.authorize_job('lighttry',{},'e'*64))
        self.worker.health.assert_not_called()

    def test_cpu_submit_health_binding_and_durable_marker_prevent_repost(self):
        self.cpu.submit(self.folder,self.request)
        self.assertTrue((self.folder/'https-binding.json').is_file());self.control.sessions.submit.assert_called_once()
        with self.assertRaises(FileExistsError):self.cpu.submit(self.folder,self.request)
        self.control.sessions.submit.assert_called_once()

    def test_upload_lost_ack_and_404_recovery_never_reposts(self):
        self.worker.upload.side_effect=LinkUncertain('uncertain')
        with self.assertRaises(LinkUncertain):self.cpu.submit(self.folder,self.request)
        self.worker.query.return_value={'status':'not_found'};self.cpu.reconcile(self.folder)
        self.worker.upload.assert_called_once();self.control.sessions.submit.assert_not_called()

    def test_wrong_worker_host_blocks_photo_upload(self):
        self.worker.health.return_value['sessionId']='0'*32
        with self.assertRaises(ValueError):self.cpu.submit(self.folder,self.request)
        self.worker.upload.assert_not_called()

    def test_result_archive_traversal_is_not_published(self):
        self.cpu.submit(self.folder,self.request);body=json.loads((self.folder/'https-binding.json').read_text())['envelope']
        buffer=io.BytesIO()
        with tarfile.open(fileobj=buffer,mode='w:gz') as archive:
            member=tarfile.TarInfo('../escape');member.size=1;archive.addfile(member,io.BytesIO(b'x'))
        self.worker.query.return_value={**body,'status':'succeeded','resultSha256':hashlib.sha256(buffer.getvalue()).hexdigest()}
        self.worker.download.return_value=buffer.getvalue()
        with self.assertRaises(ValueError):self.cpu.reconcile(self.folder)
        self.assertFalse((self.folder/'execution.json').exists());self.assertFalse((self.root/'escape').exists())
        self.cpu.reconcile(self.folder);self.worker.query.assert_called_once()

    def test_worker_success_reference_is_persisted_not_inferred_from_time(self):
        body=self.envelope();self.ledger.accept(body);self.ledger.model_state='ready'
        raw=b'SYNTHETIC_RESULT_NOT_A_MODEL_IMAGE';sha=hashlib.sha256(raw).hexdigest()
        def fake(job):self.ledger.upload(sha,raw);return {'status':'succeeded','resultSha256':sha}
        self.ledger.executor=fake;self.ledger.run_one()
        self.assertEqual(self.ledger.query(body['jobId'])['resultSha256'],sha)
        self.assertEqual(self.ledger.blob(sha),raw)
        self.ledger.close();self.ledger=WorkerLedger(self.root/'gpu','SYNTHETIC_WORKER_TOKEN_'+'X'*40,'a'*32,'RESOURCE_FIXTURE')
        self.assertEqual(self.ledger.query(body['jobId'])['status'],'succeeded')

    def test_worker_store_cannot_be_rebound_to_another_session(self):
        self.ledger.close()
        with self.assertRaises(ValueError):WorkerLedger(self.root/'gpu','SYNTHETIC_WORKER_TOKEN_'+'X'*40,'9'*32,'RESOURCE_FIXTURE')
        self.ledger=WorkerLedger(self.root/'gpu','SYNTHETIC_WORKER_TOKEN_'+'X'*40,'a'*32,'RESOURCE_FIXTURE')


class LoopbackTLSTests(unittest.TestCase):
    def test_real_local_tls_ca_hostname_pin_and_blob_roundtrip_no_model(self):
        openssl=shutil.which('openssl') or ('C:/Program Files/Git/usr/bin/openssl.exe' if Path('C:/Program Files/Git/usr/bin/openssl.exe').is_file() else None)
        if not openssl:self.skipTest('Local OpenSSL unavailable')
        from wsgiref.simple_server import make_server,WSGIRequestHandler
        class Silent(WSGIRequestHandler):
            def log_message(self,*args):pass
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);cert=root/'cert.pem';key=root/'key.pem'
            p=subprocess.run([openssl,'req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(key),'-out',str(cert),
                '-days','1','-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost'],capture_output=True,timeout=15)
            self.assertEqual(p.returncode,0,'Synthetic certificate creation failed')
            ledger=WorkerLedger(root/'worker','SYNTHETIC_TLS_TOKEN_'+'X'*40,'a'*32,'RESOURCE_FIXTURE')
            called=[];ledger.executor=lambda job:called.append(job) or 'succeeded';ledger.model_state='ready'
            server=make_server('127.0.0.1',0,WorkerApplication(ledger),handler_class=Silent)
            context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(cert,key);server.socket=context.wrap_socket(server.socket,server_side=True)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            pin=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cert.read_text())).hexdigest()
            try:
                url='https://localhost:'+str(server.server_port)
                client=HTTPSWorker(url,ledger.token,ca_file=str(cert),certificate_sha256=pin)
                uploaded=client.upload(b'SYNTHETIC_BLOB');self.assertEqual(client.download(uploaded['sha256']),b'SYNTHETIC_BLOB')
                self.assertEqual(client.health()['sessionId'],'a'*32);self.assertFalse(client.health()['modelLoaded']);self.assertEqual(called,[])
                bad=HTTPSWorker(url,ledger.token,ca_file=str(cert),certificate_sha256='0'*64)
                with self.assertRaises(LinkUncertain):bad.health()
                untrusted=HTTPSWorker(url,ledger.token)
                with self.assertRaises(LinkUncertain):untrusted.health()
                wrong_host=HTTPSWorker('https://127.0.0.1:'+str(server.server_port),ledger.token,ca_file=str(cert))
                with self.assertRaises(LinkUncertain):wrong_host.health()
                wrong=HTTPSWorker(url,'SYNTHETIC_WRONG_TOKEN_'+'Y'*40,ca_file=str(cert))
                with self.assertRaises(LinkUncertain):wrong.health()
            finally:
                server.shutdown();server.server_close();thread.join(3);ledger.close()


if __name__=='__main__':unittest.main()
