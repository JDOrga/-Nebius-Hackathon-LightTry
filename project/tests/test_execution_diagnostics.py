"""Hermetic failure evidence transport, without network/model/launch operations."""
import json,sys,tempfile,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from gpu_monitoring import clean_failure
from gpu_model import CosmosWorkerExecutor
from worker_link import WorkerLedger
from https_executor import HTTPSCosmosExecutor
from model_contract import request_sha
from inference.jobs import atomic,read


class FailureTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.request={'taskId':'a'*32,'nonce':'b'*32,
            'input':{},'original':{},'preset':{}}
        self.envelope={'jobId':'a'*32,'requestSha256':request_sha(self.request)}
        self.prep=self.root/'executions'/('a'*32);(self.prep/'run').mkdir(parents=True)
        atomic(self.prep/'request.json',self.request)
        self.event={'taskId':'a'*32,'nonce':'b'*32,'status':'failed','executionStopped':True,'stage':'preflight',
                    'diagnostic':{'code':'SECRET','exception':'UnboundLocalError','trace':'SECRET'}}
        atomic(self.prep/'run/execution.json',self.event)
        self.executor=CosmosWorkerExecutor.__new__(CosmosWorkerExecutor)
        self.executor.ledger=SimpleNamespace(root=self.root)
    def test_exact_failed_task_gets_closed_diagnostic(self):
        value=self.executor.task_failure(self.envelope)
        self.assertEqual(value,{'code':'WORKER_EXECUTION_FAILED','stage':'preflight','exception':'UnboundLocalError'})
        self.assertNotIn('SECRET',json.dumps(value))
    def test_wrong_nonce_hash_and_unproven_stop_are_not_diagnostics(self):
        for change in [{'nonce':'c'*32},{'executionStopped':False},{'status':'succeeded'}]:
            atomic(self.prep/'run/execution.json',{**self.event,**change})
            self.assertIsNone(self.executor.task_failure(self.envelope))
        atomic(self.prep/'run/execution.json',self.event)
        self.assertIsNone(self.executor.task_failure({**self.envelope,'requestSha256':'0'*64}))
        self.assertIsNone(self.executor.task_failure({'jobId':'../SECRET'}))
    def test_oversized_and_missing_file_is_best_effort(self):
        (self.prep/'run/execution.json').write_bytes(b'x'*65537)
        self.assertIsNone(self.executor.task_failure(self.envelope))
        (self.prep/'run/execution.json').unlink()
        self.assertIsNone(self.executor.task_failure(self.envelope))
    def test_malformed_fields_cannot_escape_closed_schema(self):
        for raw in [None,[],{'exception':[]},{'exception':'SECRET','stage':'SECRET'}]:
            value=clean_failure(raw,['SECRET'])
            self.assertEqual(value['exception'],'UnknownError')
            self.assertEqual(value['stage'],'unknown')
            self.assertNotIn('SECRET',json.dumps(value))
    def test_worker_failed_query_has_no_execution_side_effect(self):
        ledger=WorkerLedger(self.root/'ledger','T'*32,'c'*32,'FIXTURE')
        try:
            with ledger.db() as db:
                db.execute('INSERT INTO jobs VALUES (?,?,?,?)',('a'*32,'FIXTURE',json.dumps(self.envelope),'failed'))
            ledger.executor=Mock();ledger.executor.task_failure.return_value=self.executor.task_failure(self.envelope)
            result=ledger.query('a'*32)
            self.assertEqual(result['diagnostic']['stage'],'preflight')
            ledger.executor.assert_not_called()
            self.assertEqual(ledger.query('d'*32),{'status':'not_found'})
        finally:ledger.close()
    def test_cpu_failure_stage_not_fabricated_and_no_download_or_retry(self):
        folder=self.root/('a'*32);folder.mkdir();atomic(folder/'request.json',self.request)
        atomic(folder/'https-binding.json',{'envelope':self.envelope,'deadline':time.time()+60})
        remote={**self.envelope,'status':'failed','diagnostic':self.executor.task_failure(self.envelope)}
        worker=Mock();worker.query.return_value=remote
        cpu=HTTPSCosmosExecutor(SimpleNamespace(sessions=SimpleNamespace(worker=worker)),None,self.root)
        cpu.reconcile(folder);cpu.reconcile(folder)
        event=read(folder/'execution.json')
        self.assertEqual(event['stage'],'preflight')
        self.assertEqual(event['diagnostic']['exception'],'UnboundLocalError')
        worker.query.assert_called_once();worker.submit.assert_not_called();worker.download.assert_not_called()
    def test_cpu_wrong_identity_is_not_published(self):
        folder=self.root/('a'*32);folder.mkdir();atomic(folder/'request.json',self.request)
        atomic(folder/'https-binding.json',{'envelope':self.envelope,'deadline':time.time()+60})
        worker=Mock();worker.query.return_value={**self.envelope,'requestSha256':'0'*64,'status':'failed'}
        cpu=HTTPSCosmosExecutor(SimpleNamespace(sessions=SimpleNamespace(worker=worker)),None,self.root)
        cpu.reconcile(folder);self.assertFalse((folder/'execution.json').exists())
    def test_public_task_retains_only_safe_diagnostic_without_resubmission(self):
        from inference.jobs import TaskStore
        from inference_fixture import OfflineExecutor,image_bytes
        import uuid
        presets=json.loads((Path(__file__).resolve().parents[1]/'data/catalog.json').read_text(encoding='utf-8'))['presets']
        executor=OfflineExecutor();store=TaskStore(self.root/'tasks',presets,executor)
        try:
            task=store.submit(image_bytes(),{'inputId':uuid.uuid4().hex,'requestId':uuid.uuid4().hex,
                'presetId':'sunny','name':'SYNTHETIC'},'image/png')
            folder,request=executor.calls[0]
            atomic(folder/'execution.json',{'taskId':request['taskId'],'nonce':request['nonce'],
                'status':'failed','stage':'preflight','executionStopped':True,
                'diagnostic':{'exception':'UnboundLocalError','message':'SECRET'}})
            result=store.get(task['taskId'])
            self.assertEqual(result['executionDiagnostic']['exception'],'UnboundLocalError')
            self.assertEqual(result['status'],'failed');self.assertFalse(result['executionUncertain'])
            self.assertNotIn('SECRET',json.dumps(result));self.assertEqual(len(executor.calls),1)
        finally:store.close()


if __name__=='__main__':unittest.main()
