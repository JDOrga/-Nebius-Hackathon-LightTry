"""Synthetic monitor/progress acceptance; no provider, SSH, CUDA or model calls."""
import copy,json,sys,tempfile,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from gpu_monitoring import clean_loading,phase_loading,execution_progress,public_monitor,LOAD_STAGES
from inference.jobs import atomic,read
from model_contract import request_sha
from worker_link import WorkerLedger
import test_worker_guard as guard_fixture
import test_real_links as model_fixture
import test_service_security as service_fixture


class TelemetryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.folder=self.root/'resident/inverse';self.folder.mkdir(parents=True)
        self.state={'pid':321,'sessionId':'a'*32,'resourceId':'FIXTURE','phase':'inverse','state':'loading'}
        atomic(self.folder/'state.json',self.state)
    def write_events(self,events,tail=b''):
        (self.folder/'loading-timing.jsonl').write_bytes(b''.join(json.dumps(e).encode()+b'\n' for e in events)+tail)
    def event(self,stage,event,identity=1,**extra):
        return dict({'pid':321,'phase':'inverse','at':100,'stage':stage,'event':event,'spanId':identity},**extra)
    def snapshot(self,**changes):
        args=dict(root=self.root,phase='inverse',pid=321,session='a'*32,resource='FIXTURE',alive=True,now=110)
        args.update(changes);return phase_loading(**args)
    def test_partial_file_reports_inflight_stage_not_completion(self):
        self.write_events([self.event('preload_total','started'),self.event('module_import','started',2),
            self.event('module_import','finished',2),self.event('checkpoint_read','started',3)],b'{"partial"')
        value=self.snapshot();self.assertEqual(value['state'],'loading');self.assertEqual(value['activeStage'],'checkpoint_read')
        self.assertEqual(value['completedStages'],['module_import']);self.assertNotIn('SECRET',json.dumps(value))
    def test_finished_preload_cannot_promote_ready_and_pid_change_discards_log(self):
        self.write_events([self.event('preload_total','started'),self.event('preload_total','finished',elapsedMs=500)])
        self.assertEqual(self.snapshot()['state'],'loading');self.assertEqual(self.snapshot(pid=999)['state'],'unknown')
        self.assertEqual(self.snapshot(alive=False)['state'],'failed')
    def test_missing_or_oversized_telemetry_never_breaks_phase_status(self):
        self.assertEqual(self.snapshot()['state'],'loading')
        (self.folder/'loading-timing.jsonl').write_bytes(b'x'*65537)
        self.assertEqual(self.snapshot()['completedStages'],[])
    def test_closed_whitelist_numeric_validation_and_malformed_values(self):
        raw={'version':1,'secret':'SECRET','phases':[{'phase':'inverse','state':'loading','activeStage':[],
            'completedStages':['SECRET',*LOAD_STAGES],'elapsedMs':float('nan'),'cpuMs':-1,'ioReadBytes':True,'raw':'SECRET'}]}
        value=clean_loading(raw);self.assertNotIn('SECRET',json.dumps(value));self.assertIsNone(value['phases'][0]['activeStage'])
        self.assertIsNone(value['phases'][0]['elapsedMs']);self.assertIsNone(value['phases'][0]['cpuMs'])
        self.assertIsNone(value['phases'][0]['ioReadBytes']);self.assertEqual(value['phases'][0]['completed'],9)
        self.assertIsNone(clean_loading('SECRET'))
    def test_completion_requires_matched_start_and_future_or_wrong_pid_rejected(self):
        self.write_events([self.event('checkpoint_read','finished'),self.event('parameter_apply','started',2,pid=999),
                           self.event('checkpoint_read','started',3,at=200)])
        self.assertEqual(self.snapshot()['completedStages'],[])
    def test_public_monitor_removes_credentials_and_marks_old_worker_snapshot(self):
        snapshot={'hostIdentity':{'vmId':'VM_FIXTURE','ip':'127.0.0.1','token':'SECRET'},'providerState':'RUNNING',
            'workerTelemetry':{'observedAt':1,'modelState':'loading','modelLoaded':False,'loadingProgress':None,'raw':'SECRET'},
            'workDeadline':float('inf'),'hostConfirmed':True,'raw':'SECRET'}
        value=public_monitor(snapshot,True,100);self.assertTrue(value['workerStale'])
        self.assertNotIn('SECRET',json.dumps(value));self.assertIsNone(value['deadlines']['workDeadline'])
    def test_exact_task_identity_and_hash_required_for_running_stage(self):
        identity='b'*32;folder=self.root/'executions'/identity;(folder/'run').mkdir(parents=True)
        request={'taskId':identity,'nonce':'c'*32,'input':{}}
        envelope={'jobId':identity,'requestSha256':request_sha(request)}
        atomic(folder/'request.json',request);event={**request,'status':'running','stage':'inverse','raw':'SECRET'}
        atomic(folder/'run/execution.json',event)
        self.assertEqual(execution_progress(self.root,envelope),{'status':'running','stage':'inverse'})
        self.assertIsNone(execution_progress(self.root,{**envelope,'requestSha256':'d'*64}))
        atomic(folder/'run/execution.json',{**event,'nonce':'e'*32});self.assertIsNone(execution_progress(self.root,envelope))
        self.assertIsNone(execution_progress(self.root,{'jobId':'../../secret'}))
    def test_unknown_stage_or_terminal_event_not_running_progress(self):
        identity='b'*32;folder=self.root/'executions'/identity;(folder/'run').mkdir(parents=True)
        request={'taskId':identity,'nonce':'c'*32,'input':{}};atomic(folder/'request.json',request)
        envelope={'jobId':identity,'requestSha256':request_sha(request)}
        for status,stage in [('succeeded','inverse'),('running','SECRET')]:
            atomic(folder/'run/execution.json',{**request,'status':status,'stage':stage})
            self.assertIsNone(execution_progress(self.root,envelope))


class BridgeTests(unittest.TestCase):
    def test_remote_phase_reaches_existing_task_public_api_without_claiming_success(self):
        from test_https_result_path import ResultPathTests
        f=ResultPathTests();f.setUp();self.addCleanup(f.tearDown);remote=f.f
        remote.cpu.submit(remote.folder,remote.request);envelope=read(remote.folder/'https-binding.json')['envelope']
        remote.worker.query.return_value={**envelope,'status':'dispatching','progress':{'status':'running','stage':'inverse'}}
        remote.cpu.reconcile(remote.folder);value=f.store.get(remote.request['taskId'])
        self.assertEqual(value['status'],'running');self.assertEqual(value['stage'],'inverse');self.assertIsNone(value['result'])
        self.assertEqual(remote.worker.submit.call_count,0)  # submission is through Sessions, not a second worker POST

    def test_guard_caches_health_without_extra_calls_or_deadline_changes(self):
        f=guard_fixture.GuardTests();f.setUp();self.addCleanup(f.tearDown);value=f.running()
        original=f.peer.health;calls=[]
        def health():
            calls.append(1);return {**original(),'loadingProgress':{'version':1,'phases':[
                {'phase':'inverse','state':'loading','activeStage':'checkpoint_read','completedStages':['module_import'],'raw':'SECRET'}]}}
        f.peer.health=health;value=f.sessions.poll(value['sessionId'])
        self.assertEqual(len(calls),1);self.assertNotIn('SECRET',json.dumps(value['workerTelemetry']))
        self.assertEqual(value['workDeadline'],f.sessions.get(value['sessionId'])['workDeadline'])
        before=len(calls)
        for _ in range(5):public_monitor(f.sessions.latest(),True,f.clock())
        self.assertEqual(len(calls),before);self.assertEqual(f.provider.starts,1);self.assertEqual(f.peer.posts,0)
    def test_running_progress_reaches_cpu_existing_event_without_post(self):
        f=model_fixture.ModelTests();f.setUp();self.addCleanup(f.tearDown)
        f.cpu.submit(f.folder,f.request);envelope=read(f.folder/'https-binding.json')['envelope'];posts=f.worker.submit.call_count
        f.worker.query.return_value={**envelope,'status':'dispatching','progress':{'status':'running','stage':'inverse','secret':'SECRET'}}
        f.cpu.reconcile(f.folder);event=read(f.folder/'execution.json')
        self.assertEqual(event['status'],'running');self.assertEqual(event['stage'],'inverse')
        self.assertEqual(event['nonce'],f.request['nonce']);self.assertNotIn('SECRET',json.dumps(event))
        self.assertEqual(f.worker.submit.call_count,posts)
        f.worker.query.return_value={**envelope,'requestSha256':'f'*64,'progress':{'status':'running','stage':'forward'}}
        f.cpu.reconcile(f.folder);self.assertEqual(read(f.folder/'execution.json')['stage'],'inverse')
    def test_worker_query_only_exposes_progress_for_dispatching_lane(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger=WorkerLedger(Path(tmp).resolve(),'X'*32,'a'*32,'FIXTURE')
            body={'jobId':'b'*32,'sessionId':'a'*32,'resourceId':'FIXTURE','artifactSha256':'c'*64,'requestSha256':'d'*64}
            with ledger.db() as db:db.execute('INSERT INTO jobs VALUES (?,?,?,?)',('b'*32,'F',json.dumps(body),'dispatching'))
            ledger.executor=SimpleNamespace(task_progress=lambda unused:{'status':'running','stage':'forward','secret':'SECRET'})
            self.assertEqual(ledger.query('b'*32)['progress'],{'status':'running','stage':'forward'})
            with ledger.db() as db:db.execute("UPDATE jobs SET state='queued'")
            self.assertNotIn('progress',ledger.query('b'*32))
            ledger.close()
    def test_actual_authenticated_status_get_is_snapshot_only_and_asset_served(self):
        f=service_fixture.ServiceSecurityTests();f.setUp();self.addCleanup(f.tearDown)
        snapshot={'state':'LOADING','lastObservedAt':time.time(),'hostIdentity':{'vmId':'VM_FIXTURE','ip':'127.0.0.1'},
            'workerTelemetry':{'observedAt':time.time(),'modelState':'loading','loadingProgress':{'version':1,'phases':[]}}}
        f.app.gpu_sessions=SimpleNamespace(latest=Mock(return_value=snapshot))
        for _ in range(2):
            status,raw,_=service_fixture.request(f.app,'/api/gpu/entry-status');self.assertEqual(status,200)
            self.assertEqual(json.loads(raw)['monitor']['host']['vmId'],'VM_FIXTURE')
        self.assertEqual(f.app.gpu_sessions.latest.call_count,2)
        status,raw,_=service_fixture.request(f.app,'/gpu-monitor.js');self.assertEqual(status,200)
        self.assertIn(b'paintGenerationButton',raw)
        status,_,_=service_fixture.request(f.app,'/gpu-monitor.js',user=None);self.assertNotEqual(status,200)


if __name__=='__main__':unittest.main()
