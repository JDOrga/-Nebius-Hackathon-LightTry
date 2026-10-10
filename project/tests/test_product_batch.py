"""Isolated local contract tests; historical copies and doubles, never GPU/cloud."""
import copy
import io
import json
import shutil
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch
from PIL import Image, ImageChops

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from inference.jobs import TaskStore, JobError, read, atomic
from inference import product_results as product
from inference_fixture import OfflineExecutor, image_bytes
from inference.driver import build_bundle

PRESETS=read(ROOT/'data/catalog.json')['presets']
RUN='cdbca2ab59bb44e39537d8d14f2d3552'
SOURCE='6d541112fa164c099d9fc06c560b464d'
TASK='73edd6656f9e47db85578d93e42c1e8b'
JOB='reuse-benchmark-20261010-retry1/private-job'


class SubmissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.executor=OfflineExecutor()
        self.store=TaskStore(self.tmp.name,PRESETS,self.executor,clock=lambda:100)
        self.meta={'inputId':uuid.uuid4().hex,'requestId':uuid.uuid4().hex,'presetIds':['sunny','sunrise','sunny']}
    def tearDown(self): self.store.close();self.tmp.cleanup()
    def test_one_dispatch_dedup_and_idempotency(self):
        task=self.store.submit(image_bytes(),self.meta,'image/png')
        self.assertEqual([p['id'] for p in task['presets']],['sunny','sunrise'])
        folder,request=self.executor.calls[0]
        self.assertEqual(request['presets'],task['presets'])
        self.assertEqual(self.store.submit(image_bytes(),self.meta,'image/png')['taskId'],task['taskId'])
        self.assertEqual(len(self.executor.calls),1)
        with self.assertRaises(JobError) as e:
            self.store.submit(image_bytes(),{**self.meta,'presetIds':['sunny','street']},'image/png')
        self.assertEqual(e.exception.code,'IDEMPOTENCY_CONFLICT')
    def test_invalid_presets_and_busy(self):
        for ids in ([],['unknown'],['../sunny'],['sunny']*4,'sunny',[{}]):
            with self.assertRaises(JobError):self.store.submit(image_bytes(),{**self.meta,'presetIds':ids},'image/png')
        self.store.submit(image_bytes(),self.meta,'image/png')
        with self.assertRaises(JobError) as e:self.store.submit(image_bytes(),{**self.meta,'requestId':uuid.uuid4().hex},'image/png')
        self.assertEqual(e.exception.code,'TASK_BUSY')
    def test_batch_reaches_real_bundle_request_without_execution(self):
        self.store.submit(image_bytes(),self.meta,'image/png')
        folder,request=self.executor.calls[0]
        target=Path(self.tmp.name)/'bundle';target.mkdir()
        build_bundle(folder,target,{'weights_mode':'full','reuse_inverse':False})
        import tarfile
        with tarfile.open(target/'inference-code.tar.gz') as tar:
            archived=json.load(tar.extractfile('request.json'))
        self.assertEqual(archived['presets'],request['presets'])
    def test_batch_timeout_then_late_event_does_not_publish(self):
        task=self.store.submit(image_bytes(),self.meta,'image/png')
        self.store.clock=lambda:2000
        failed=self.store.get(task['taskId'])
        self.assertEqual(failed['error']['code'],'TASK_TIMEOUT')
        self.assertTrue(all(i['status']=='failed' and i['result'] is None for i in failed['presetResults'].values()))
        self.executor.event('succeeded','validating',True)
        late=self.store.get(task['taskId'])
        self.assertEqual(late['status'],'failed');self.assertFalse(late['executionUncertain'])


@unittest.skipUnless((ROOT.parent/'.local'/JOB).exists(),'local real evidence fixture absent')
class RegistrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.workspace=Path(self.tmp.name)
        shutil.copytree(ROOT.parent/'.local'/JOB,self.workspace/'.local'/JOB)
        shutil.copytree(ROOT.parent/'manifests',self.workspace/'manifests')
        run=self.workspace/'cloud-runs'/RUN;run.mkdir(parents=True)
        for name in ('bundle.json','inference-code.tar.gz','launch-result.json'):
            shutil.copyfile(ROOT.parent/'cloud-runs'/RUN/name,run/name)
        self.store=TaskStore(self.workspace/'tasks',PRESETS,clock=lambda:200)
        origin=self.store.root/SOURCE;origin.mkdir()
        shutil.copyfile(ROOT/'.tasks'/SOURCE/'original',origin/'original')
        self.patch=patch.object(product,'WORKSPACE',self.workspace);self.patch.start()
        self.source=self.workspace/'.local'/JOB
    def tearDown(self):self.patch.stop();self.store.close();self.tmp.cleanup()
    def register(self):return self.store.register_execution(JOB,RUN,SOURCE)
    def test_register_repeat_restore_download_and_exact_crops(self):
        task=self.register();before=(self.store.root/TASK/'task.json').read_bytes()
        self.assertEqual(task['taskId'],TASK)
        self.assertEqual(self.register()['registeredAt'],task['registeredAt'])
        self.assertEqual((self.store.root/TASK/'task.json').read_bytes(),before)
        for p in ('sunny','sunrise'):
            item=task['presetResults'][p]
            jpg,mime,filename=self.store.file(TASK,'download',p)
            from inference.images import digest
            self.assertEqual(digest(jpg),item['result']['sha256']);self.assertIn(p+'_full',filename)
            png,_,filename=self.store.file(TASK,'download-region',p)
            with Image.open(io.BytesIO(jpg)) as full,Image.open(io.BytesIO(png)) as crop:
                self.assertIsNone(ImageChops.difference(full.crop(tuple(task['input']['canvas']['validRegion'])),crop).getbbox())
            self.assertIn(p+'_photo-region',filename)
        with self.assertRaises(JobError):self.store.file(TASK,'download','street')
        self.assertEqual(self.store.get(TASK)['status'],'succeeded')
        self.store.close();self.store=TaskStore(self.workspace/'tasks',PRESETS,clock=lambda:201)
        self.assertEqual(self.store.get(TASK)['presetResults']['sunrise']['status'],'succeeded')
    def test_registration_hash_missing_preset_and_path_rejections(self):
        for relative in ('../'+JOB,str(self.source),'../outside'):
            with self.assertRaises(ValueError):self.store.register_execution(relative,RUN,SOURCE)
        marker=self.source/'remote-evidence/presets/1/complete.json'
        record=read(marker);record['identity']['hdr']['id']='street';atomic(marker,record)
        with self.assertRaises(ValueError):self.register()
        self.assertFalse((self.store.root/TASK).exists())
    def test_batch_http_results_and_no_local_path_endpoint(self):
        import server,threading
        from http.server import ThreadingHTTPServer
        from urllib.request import urlopen
        from urllib.error import HTTPError
        self.register()
        handler=type('ProductBatchTestHandler',(server.Handler,),{'task_store':self.store})
        http=ThreadingHTTPServer(('127.0.0.1',0),handler)
        thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
        base=f'http://127.0.0.1:{http.server_port}'
        try:
            for preset in ('sunny','sunrise'):
                with urlopen(base+f'/api/tasks/{TASK}/presets/{preset}/download') as response:
                    self.assertEqual(response.read(),self.store.file(TASK,'download',preset)[0])
            for path in (f'/api/tasks/{TASK}/presets/street/download',f'/api/tasks/{TASK}/presets/sunny/request.json',
                         '/register?path='+str(self.source),'/api/tasks/'+TASK+'/presets/..%2F..%2Fconfig/download'):
                with self.assertRaises(HTTPError):urlopen(base+path)
        finally:http.shutdown();http.server_close();thread.join()
    def test_hash_mismatch_and_missing_output(self):
        record=read(self.source/'remote-evidence/presets/1/complete.json')
        path=self.source/'remote-evidence/presets/1'/record['attempt']/record['result']['path']
        path.write_bytes(b'corrupt')
        with self.assertRaises(ValueError):self.register()
        path.unlink()
        with self.assertRaises(ValueError):self.register()
    def test_run_and_identity_conflict(self):
        self.register()
        record=read(self.source/'remote-evidence/presets/1/complete.json');record['completedEpoch']+=1
        atomic(self.source/'remote-evidence/presets/1/complete.json',record)
        with self.assertRaisesRegex(ValueError,'CONFLICT'):self.register()
    def test_configuration_and_run_checks(self):
        request=read(self.source/'request.json');request['runConfig']['width']=1024
        atomic(self.source/'request.json',request)
        with self.assertRaisesRegex(ValueError,'CONFIG'):self.register()
        request['runConfig']['width']=1280;atomic(self.source/'request.json',request)
        launch=self.workspace/'cloud-runs'/RUN/'launch-result.json'
        entry=read(launch);entry['output']=json.dumps({'prep':'/home/preview-'+'a'*32});atomic(launch,entry)
        with self.assertRaisesRegex(ValueError,'DESTINATION'):self.register()
    def test_decode_dimensions_and_nonconstant_checks(self):
        from inference.images import digest
        marker=self.source/'remote-evidence/presets/1/complete.json';record=read(marker)
        output=marker.parent/record['attempt']/record['result']['path']
        for size in ((640,704),(1280,704)):
            stream=io.BytesIO();Image.new('RGB',size,'red').save(stream,format='JPEG');payload=stream.getvalue()
            output.write_bytes(payload);record['result'].update(sha256=digest(payload),bytes=len(payload));atomic(marker,record)
            with self.assertRaises(ValueError):self.register()
    def test_partial_registration_without_whole_batch_receipt(self):
        (self.source/'receipt.json').unlink()
        event=read(self.source/'execution.json');event['status']='failed';atomic(self.source/'execution.json',event)
        item=self.source/'remote-evidence/presets/1'
        (item/'complete.json').unlink();atomic(item/'state.json',{'status':'pending'})
        task=self.register()
        self.assertEqual(task['status'],'partial');self.assertEqual(task['presetResults']['sunrise']['status'],'pending')
        self.store.file(TASK,'download','sunny')
    def test_result_missing_only_invalidates_own_preset_and_expires(self):
        self.register();(self.store.root/TASK/'results/sunrise.jpg').unlink()
        task=self.store.get(TASK)
        self.assertEqual(task['status'],'partial');self.assertEqual(task['presetResults']['sunny']['status'],'succeeded')
        self.assertEqual(task['presetResults']['sunrise']['error']['code'],'RESULT_INVALID')
        self.store.file(TASK,'download','sunny')
        self.store.clock=lambda:1000000
        self.assertEqual(self.store.get(TASK)['status'],'expired')
        with self.assertRaises(JobError) as e:self.store.file(TASK,'download','sunny')
        self.assertEqual(e.exception.http,410)
    def test_partial_executor_failure_and_late_timeout(self):
        self.register();folder=self.store.root/TASK;task=read(folder/'task.json')
        task.pop('registration');task.update(status='running',deadline=300,executionUncertain=False,result=None)
        atomic(folder/'task.json',task);atomic(folder/'runtime-binding.json',{'guardRunId':RUN})
        (folder/'remote-evidence/presets/1/complete.json').unlink()
        atomic(folder/'remote-evidence/presets/1/state.json',{'status':'failed','error':'OFFLINE_TEST_SECOND_FAILURE'})
        atomic(folder/'execution.json',{'taskId':TASK,'nonce':task['nonce'],'status':'failed','executionStopped':True})
        got=self.store.get(TASK)
        self.assertEqual(got['status'],'partial');self.assertEqual(got['presetResults']['sunny']['status'],'succeeded')
        self.assertEqual(got['presetResults']['sunrise']['status'],'failed')
        self.store.file(TASK,'download','sunny')
        # Different isolated record: a late completion cannot reverse timeout.
        got.update(status='failed',error={'code':'TASK_TIMEOUT','message':'offline timeout'},executionUncertain=True)
        atomic(folder/'task.json',got)
        atomic(folder/'execution.json',{'taskId':TASK,'nonce':task['nonce'],'status':'succeeded','executionStopped':True})
        self.assertEqual(self.store.get(TASK)['status'],'failed')
