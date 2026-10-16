"""Hermetic lifecycle/IPC tests. No CUDA imports, model weights or cloud calls."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from resident_model import PipelineCache,serve,verify_runtime,execute
from model_readiness import resident_receipt
from resident_ipc import call,phase_command
from resident_executor import ResidentCosmosExecutor
from inference.jobs import atomic,read


class CacheTests(unittest.TestCase):
    def test_load_once_reuse_reset_and_reject_changed_settings(self):
        class Pipeline:
            loads=0
            def __init__(self,**kw):type(self).loads+=1
            def generate_video(self):return 'SYNTHETIC'
        cache=PipelineCache(Pipeline,{'seed':1000})
        try:
            one=Pipeline(seed=1000);two=Pipeline(seed=1000)
            self.assertIs(one,two);self.assertEqual(Pipeline.loads,1)
            one.generate_video=lambda:'OLD_USER_HOOK';cache.reset()
            self.assertEqual(two.generate_video(),'SYNTHETIC')
            with self.assertRaises(ValueError):Pipeline(seed=1)
        finally:cache.close()
        Pipeline(seed=1000);self.assertEqual(Pipeline.loads,2)


class IPCTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.prep=self.root/'executions'/('a'*32);(self.prep/'run').mkdir(parents=True)
        self.entry=self.prep/'project/inference/measured_entry.py';self.entry.parent.mkdir(parents=True);self.entry.write_text('# SYNTHETIC')
        self.command=[sys.executable,'-B',str(self.entry),'--phase','inverse']
        self.runtime=self.root/'resident';self.phase=self.runtime/'inverse';self.phase.mkdir(parents=True)
        (self.phase/'responses').mkdir()
        atomic(self.phase/'state.json',{'state':'ready','modelLoaded':True,'bootId':'BOOT_FIXTURE'})
        self.now=100
    def tearDown(self):self.tmp.cleanup()
    def clock(self):return self.now
    def test_one_request_and_exact_response(self):
        def respond(_):
            requests=list((self.phase/'requests').glob('*.json'));self.assertEqual(len(requests),1)
            v=read(requests[0]);atomic(self.phase/'responses'/requests[0].name,{'id':v['id'],'bootId':v['bootId'],'exitCode':0})
            self.now+=1
        call(self.runtime,'inverse',self.command,self.prep/'run/inverse.log',self.prep,105,clock=self.clock,sleep=respond)
        self.assertEqual(len(list((self.phase/'requests').glob('*.json'))),1)
    def test_timeout_does_not_resubmit(self):
        def tick(_):self.now+=1
        with self.assertRaises(TimeoutError):
            call(self.runtime,'inverse',self.command,self.prep/'run/inverse.log',self.prep,102,clock=self.clock,sleep=tick)
        self.assertEqual(len(list((self.phase/'requests').glob('*.json'))),1)
    def test_cold_and_wrong_entry_rejected(self):
        atomic(self.phase/'state.json',{'state':'loading','modelLoaded':False})
        with self.assertRaises(OSError):
            call(self.runtime,'inverse',self.command,self.prep/'run/inverse.log',self.prep,105,clock=self.clock)
        bad=self.command.copy();bad[2]=str(self.prep/'arbitrary.py')
        with self.assertRaises(ValueError):phase_command(bad,self.prep)
        self.assertIsNone(phase_command([sys.executable,'-B','preflight.py','--repo','FIXTURE'],self.prep))


class DaemonTests(unittest.TestCase):
    def test_daemon_dispatches_same_request_only_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);config=root/'config.json';config.write_text('{"grantFile":"SYNTHETIC"}')
            args=SimpleNamespace(worker_config=config,data_root=root,phase='inverse',session_id='a'*32,resource_id='FIXTURE')
            now=[100];calls=[];cache=Mock();cache.instance=object()
            def load(*unused):
                phase=root/'resident/inverse';state=read(phase/'state.json')
                atomic(phase/'requests'/('b'*32+'.json'),{'id':'b'*32,'bootId':state['bootId'],'deadline':102})
                return cache,Mock()
            with patch('resident_model.grant_file',return_value={'hostIdentity':{'vm':'FIXTURE'},'expiresAt':103}):
                serve(args,load=load,run=lambda *unused:calls.append('one'),clock=lambda:now[0],sleep=lambda _:now.__setitem__(0,now[0]+1))
            self.assertEqual(calls,['one']);self.assertEqual(len(list((root/'resident/inverse/responses').glob('*.json'))),1)

    def test_phase_executes_only_installed_entry_and_resets_hooks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);prep=root/'executions'/('a'*32);entry=prep/'project/inference/measured_entry.py'
            entry.parent.mkdir(parents=True);(prep/'run').mkdir()
            source=Path(__file__).resolve().parents[1]/'inference/measured_entry.py';entry.write_bytes(source.read_bytes())
            body={'id':'b'*32,'prep':str(prep),'argv':[sys.executable,'-B',str(entry),'--phase','inverse'],
                  'logfile':str(prep/'run/inverse.log'),'deadline':10**12,'bootId':'c'*32}
            cache=Mock();module=Mock()
            with patch('resident_model.runpy.run_path') as run:
                execute(body,{'python':sys.executable},'inverse',root,cache,module)
                run.assert_called_once();module.torch.cuda.synchronize.assert_called_once()
            self.assertEqual(cache.reset.call_count,2)
            entry.write_text('UNTRUSTED_LOCAL_REPLACEMENT')
            with self.assertRaisesRegex(ValueError,'RESIDENT_ENTRY_CHANGED'):
                execute(body,{'python':sys.executable},'inverse',root,cache,module)

    def test_preload_before_ready_once_and_no_generation_at_boot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);config=root/'config.json';config.write_text('{"grantFile":"SYNTHETIC"}')
            args=SimpleNamespace(worker_config=config,data_root=root,phase='inverse',session_id='a'*32,resource_id='FIXTURE')
            now=[100];calls=[];cache=Mock()
            grant={'hostIdentity':{'vm':'FIXTURE'},'expiresAt':103}
            def load(*unused):
                state=read(root/'resident/inverse/state.json');self.assertEqual(state['state'],'loading')
                calls.append('load');return cache,Mock()
            def tick(_):
                state=read(root/'resident/inverse/state.json');self.assertEqual(state['state'],'ready')
                now[0]+=1
            with patch('resident_model.grant_file',return_value=grant):
                serve(args,load=load,run=lambda *unused:calls.append('generate'),clock=lambda:now[0],sleep=tick)
                self.assertEqual(calls,['load']);cache.close.assert_called_once()
                with self.assertRaises(FileExistsError):serve(args,load=load)
            self.assertFalse(read(root/'resident/inverse/state.json')['modelLoaded'])
    def test_failed_load_never_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);config=root/'config.json';config.write_text('{"grantFile":"SYNTHETIC"}')
            args=SimpleNamespace(worker_config=config,data_root=root,phase='forward',session_id='a'*32,resource_id='FIXTURE')
            with patch('resident_model.grant_file',return_value={'expiresAt':103}):
                with self.assertRaises(RuntimeError):serve(args,load=Mock(side_effect=RuntimeError('SYNTHETIC_OOM')),clock=lambda:100)
            self.assertEqual(read(root/'resident/forward/state.json')['state'],'failed')
    def test_wrong_upstream_fails_before_import_or_load(self):
        with patch('resident_model.subprocess.run',return_value=SimpleNamespace(stdout='WRONG_COMMIT')):
            with self.assertRaisesRegex(ValueError,'UPSTREAM_COMMIT_MISMATCH'):
                verify_runtime({'repo':'FIXTURE','checkpointDir':'FIXTURE'},10**12)


class ExecutorTests(unittest.TestCase):
    def setUp(self):
        import test_real_links as fixtures
        self.fixture=fixtures.ModelTests();self.fixture.setUp()
        cfg=read(self.fixture.config);cfg['executionMode']='resident';atomic(self.fixture.config,cfg);self.fixture.config.chmod(0o600)
    def tearDown(self):self.fixture.tearDown()
    def test_construction_does_not_boot_and_cold_cannot_prepare(self):
        with patch('resident_executor.subprocess.Popen') as spawn:
            executor=ResidentCosmosExecutor(self.fixture.ledger,self.fixture.config)
            self.assertFalse(executor.model_loaded);spawn.assert_not_called()
            with self.assertRaisesRegex(ValueError,'RESIDENT_MODEL_NOT_READY'):executor.prepare(self.fixture.envelope())
    def test_both_phase_live_identity_required_and_health_reports_resident(self):
        executor=ResidentCosmosExecutor(self.fixture.ledger,self.fixture.config)
        executor.boot_sent=True;executor.boot_grant=self.fixture.grant
        for i,phase in enumerate(('inverse','forward')):
            child=Mock(pid=100+i);child.poll.return_value=None;executor.phases[phase]=child
            folder=self.fixture.ledger.root/'resident'/phase;folder.mkdir(parents=True)
            atomic(folder/'state.json',{'state':'ready','modelLoaded':True,'phase':phase,'pid':100+i,
                'sessionId':self.fixture.ledger.session_id,'resourceId':self.fixture.ledger.resource_id})
        self.assertTrue(executor.model_loaded)
        self.fixture.ledger.executor=executor;self.fixture.ledger.simulation=False
        self.assertTrue(self.fixture.ledger.health()['modelLoaded'])
        self.assertEqual(self.fixture.ledger.health()['executionMode'],'resident')
        executor.phases['inverse'].poll.return_value=1;self.assertFalse(executor.model_loaded)

    def test_boot_latched_across_restart_without_second_process_launch(self):
        executor=ResidentCosmosExecutor(self.fixture.ledger,self.fixture.config)
        fakeos=SimpleNamespace(name='posix',environ=os.environ)
        with patch('resident_executor.os',fakeos),patch('resident_executor.subprocess.Popen') as spawn:
            spawn.side_effect=[Mock(pid=101),Mock(pid=102)]
            executor.boot();self.assertEqual(spawn.call_count,2)
            with self.assertRaises(ValueError):executor.boot()
            other=ResidentCosmosExecutor(self.fixture.ledger,self.fixture.config)
            with self.assertRaises(FileExistsError):other.boot()
            self.assertEqual(spawn.call_count,2)
        for log in executor.phase_logs:log.close()


class ReceiptTests(unittest.TestCase):
    def test_resident_completion_does_not_forge_process_exit(self):
        proof={'version':1,'taskId':'a'*32,'nonce':'b'*32,'phases':[
            {'phase':phase,'id':str(i)*32,'bootId':'c'*32,'pid':100+i,'modelObjectId':'0xabcd',
             'exitCode':0,'cudaSynchronized':True,'completedAt':100}
            for i,phase in enumerate(('inverse','forward'),1)]}
        receipt={'executionMode':'resident','runConfig':{'modelExecutionMode':'resident-v1'},'processExitCodes':[None,None],'finishedAt':101,
                 'inverseReuse':{'reused':False},'residentExecution':proof}
        self.assertTrue(resident_receipt(receipt,'a'*32,'b'*32))
        self.assertFalse(resident_receipt(receipt,'e'*32,'b'*32))
        receipt['processExitCodes']=[0,0];self.assertFalse(resident_receipt(receipt,'a'*32,'b'*32))
        receipt['processExitCodes']=[None,None];proof['phases'][1]['cudaSynchronized']=False
        self.assertFalse(resident_receipt(receipt,'a'*32,'b'*32))

    def test_product_result_validator_accepts_real_phase_proof_not_fictional_exit(self):
        import test_inference as fixture
        job=fixture.JobTests();job.setUp()
        job.executor.run_config=lambda:{'modelExecutionMode':'resident-v1'}
        try:
            task=job.submit()
            receipt=job.executor.succeed();folder,request=job.executor.calls[-1]
            receipt.update(executionMode='resident',processExitCodes=[None,None],finishedAt=101,
                inverseReuse={'reused':False,'source':{'taskId':task['taskId']},'key':'d'*64},residentExecution={'version':1,'taskId':task['taskId'],'nonce':request['nonce'],
                    'phases':[{'phase':phase,'id':str(i)*32,'bootId':'c'*32,'pid':100+i,'modelObjectId':'0xabcd',
                               'exitCode':0,'cudaSynchronized':True,'completedAt':100}
                              for i,phase in enumerate(('inverse','forward'),1)]})
            # Job identity/hash/JPEG checks remain the original implementation.
            job.store._check_result(folder,read(folder/'task.json'),receipt)
            receipt['residentExecution']['nonce']='e'*32
            with self.assertRaisesRegex(ValueError,'RESIDENT_COMPLETION_UNPROVEN'):
                job.store._check_result(folder,read(folder/'task.json'),receipt)
        finally:job.tearDown()


if __name__=='__main__':unittest.main()
