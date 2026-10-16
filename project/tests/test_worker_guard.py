"""Hermetic CPU→GPU simulations: network/cost adapters are explicit test doubles."""
import concurrent.futures
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import ssl
import subprocess
import time
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'project'))
from gpu_session import Sessions,Deadman,STATES
from worker_link import HTTPSWorker,WorkerLedger,WorkerApplication,LinkUncertain
from inference.jobs import JobError


class Clock:
    def __init__(self):self.now=100000
    def __call__(self):return self.now
    def step(self,n):self.now+=n


class Peer:
    simulation=True
    def __init__(self):self.sid=None;self.model='loading';self.posts=0;self.queries=0;self.jobs={};self.drop=None;self.offline=False
    def health(self):
        if self.offline:raise LinkUncertain()
        return {'sessionId':self.sid,'resourceId':'RESOURCE_FIXTURE','modelState':self.model}
    def query(self,job):
        self.queries+=1
        if self.offline:raise LinkUncertain()
        return copy.deepcopy(self.jobs.get(job,{'status':'not_found'}))
    def submit(self,body):
        self.posts+=1
        if self.drop=='before':raise LinkUncertain()
        self.jobs[body['jobId']]={**body,'status':'queued'}
        if self.drop=='after':raise LinkUncertain()
        return self.query(body['jobId'])


class Provider:
    simulation=True
    def __init__(self,peer):self.peer=peer;self.state='STOPPED';self.starts=0;self.stops=0;self.offline=False;self.drop_start=False;self.keys=set()
    def preflight(self,resource):return self.observe(resource)
    def start(self,resource,key,deadline):
        if key not in self.keys:self.starts+=1;self.keys.add(key)
        self.state='STARTING';self.peer.sid=key
        if self.drop_start:raise LinkUncertain()
    def stop(self,resource,key):self.stops+=1;self.state='STOPPING'
    def observe(self,resource):
        if self.offline:raise LinkUncertain()
        return {'resourceId':resource,'state':self.state,'instances':[] if self.state=='STOPPED' else ['INSTANCE_FIXTURE'],
                'independent':True,'hostIdentity':'HOST_FIXTURE_CURRENT'}


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir='/var/tmp' if os.name!='nt' else None);self.root=Path(self.tmp.name)
        self.clock=Clock();self.peer=Peer();self.provider=Provider(self.peer)
        self.fallback=Deadman(self.root/'OFF_HOST_FIXTURE',self.provider,self.clock)
        self.sessions=Sessions(self.root/'cpu-guard',self.provider,self.peer,self.fallback,self.clock)
        self.scope={'scopeId':'a'*32,'resourceId':'RESOURCE_FIXTURE','expiresAt':self.clock()+2400,
                    'budgetApproved':True,'idleSeconds':300,'simulation':True}
    def tearDown(self):self.tmp.cleanup()
    def running(self):
        value=self.sessions.start(self.scope);self.provider.state='RUNNING'
        value=self.sessions.poll(value['sessionId']);self.assertEqual(value['state'],'LOADING')
        self.sessions.confirm_host(value['sessionId'],'HOST_FIXTURE_CURRENT');self.peer.model='ready'
        value=self.sessions.poll(value['sessionId']);self.assertEqual(value['state'],'READY');return value
    def job(self,sid):return {'jobId':'b'*32,'sessionId':sid,'resourceId':'RESOURCE_FIXTURE','artifactSha256':'c'*64,'requestSha256':'d'*64}

    def test_duplicate_start_many_tabs_refresh_and_application_restart_one_attempt(self):
        def click(_):return Sessions(self.root/'cpu-guard',self.provider,self.peer,self.fallback,self.clock).start(self.scope)['sessionId']
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:ids=list(pool.map(click,range(24)))
        self.assertEqual(len(set(ids)),1);self.assertEqual(self.provider.starts,1)
        original=self.sessions.get(ids[0]);self.clock.step(5)
        reboot=Sessions(self.root/'cpu-guard',self.provider,self.peer,self.fallback,self.clock)
        for _ in range(10):self.assertEqual(reboot.latest()['startupDeadline'],original['startupDeadline'])
        self.assertEqual(reboot.start(self.scope)['absoluteDeadline'],original['absoluteDeadline'])
        self.assertEqual(self.provider.starts,1)

    def test_start_ack_lost_disconnect_keeps_latch_then_query_never_start_again(self):
        self.provider.drop_start=True;value=self.sessions.start(self.scope)
        self.assertEqual(value['state'],'UNKNOWN');self.assertTrue(value['startSent'])
        self.provider.offline=True;value=self.sessions.poll(value['sessionId']);self.assertEqual(value['state'],'UNKNOWN')
        self.provider.offline=False;self.provider.state='RUNNING'
        value=self.sessions.poll(value['sessionId']);self.assertEqual(value['state'],'LOADING')
        self.sessions.start(self.scope);self.assertEqual(self.provider.starts,1)

    def test_disconnect_before_host_confirmation_returns_loading_without_restarting(self):
        value=self.sessions.start(self.scope);self.provider.state='RUNNING'
        self.sessions.poll(value['sessionId']);self.provider.offline=True
        self.assertEqual(self.sessions.poll(value['sessionId'])['state'],'UNKNOWN')
        self.provider.offline=False
        self.assertEqual(self.sessions.poll(value['sessionId'])['state'],'LOADING')
        self.sessions.confirm_host(value['sessionId'],'HOST_FIXTURE_CURRENT')
        self.assertEqual(self.provider.starts,1)

    def test_running_epoch_deadlines_and_idle_survive_reboot_and_heartbeat(self):
        value=self.running();original={k:value[k] for k in ('createdAt','startupDeadline','runningAt','workDeadline','stopDeadline','verifyDeadline','absoluteDeadline','idleDeadline')}
        self.clock.step(20);self.sessions.heartbeat(value['sessionId'])
        reboot=Sessions(self.root/'cpu-guard',self.provider,self.peer,self.fallback,self.clock)
        self.assertEqual({k:reboot.latest()[k] for k in original},original)
        self.clock.now=original['idleDeadline'];reboot.heartbeat(value['sessionId'])
        self.assertEqual(reboot.poll(value['sessionId'])['state'],'STOPPING');self.assertEqual(self.provider.stops,1)

    def test_startup_limit_600_and_absolute_limit_not_reset(self):
        value=self.sessions.start(self.scope);self.assertEqual(value['startupDeadline']-value['createdAt'],600)
        self.clock.step(600);self.sessions.heartbeat(value['sessionId'])
        value=self.sessions.poll(value['sessionId']);self.assertEqual(value['state'],'STOPPING')
        self.assertLessEqual(value['stopWaitDeadline'],value['absoluteDeadline'])

    def test_task_response_lost_then_query_after_restart_no_duplicate_execution(self):
        value=self.running();body=self.job(value['sessionId']);self.peer.drop='after'
        result=self.sessions.submit(value['sessionId'],body);self.assertEqual(result['status'],'uncertain');self.assertEqual(self.peer.posts,1)
        reboot=Sessions(self.root/'cpu-guard',self.provider,self.peer,self.fallback,self.clock)
        result=reboot.submit(value['sessionId'],body);self.assertEqual(result['status'],'queued');self.assertEqual(self.peer.posts,1)
        self.peer.jobs[body['jobId']]['status']='succeeded'
        self.assertEqual(reboot.poll(value['sessionId'])['state'],'READY')

    def test_job_absent_or_query_down_after_unknown_never_blindly_resubmit(self):
        value=self.running();body=self.job(value['sessionId']);self.peer.drop='before'
        self.assertEqual(self.sessions.submit(value['sessionId'],body)['status'],'uncertain')
        for _ in range(3):self.assertEqual(self.sessions.submit(value['sessionId'],body)['status'],'uncertain')
        self.assertEqual(self.peer.posts,1)
        self.peer.offline=True;self.sessions.submit(value['sessionId'],body);self.assertEqual(self.peer.posts,1)

    def test_stopping_bounded_wait_then_stop_only_observation_can_confirm_later(self):
        value=self.running();value=self.sessions.request_stop(value['sessionId'])
        bound=value['stopWaitDeadline'];self.clock.now=bound
        value=self.sessions.poll(value['sessionId']);self.assertEqual(value['state'],'UNKNOWN')
        self.assertEqual(value['error'],'STOPPING_BOUND_EXCEEDED');self.assertEqual(self.provider.stops,1)
        self.provider.state='STOPPED';value=self.sessions.poll(value['sessionId'])
        self.assertEqual(value['state'],'STOPPED');self.assertTrue(value['instancesEmpty'])
        self.assertFalse(value['guardExited'])
        with self.assertRaises(JobError):self.sessions.record_guard_exit(value['sessionId'],False,True)
        self.sessions.record_guard_exit(value['sessionId'],True,True)
        self.assertEqual(self.sessions.get(value['sessionId'])['stopWaitDeadline'],bound)

    def test_cpu_entire_host_lost_management_host_deadman_stops_without_cpu(self):
        value=self.running();self.clock.step(31)
        # No CPU guard/heartbeat method is called after machine-loss simulation.
        fallback_reboot=Deadman(self.root/'OFF_HOST_FIXTURE',self.provider,self.clock)
        fallback_reboot.tick();self.assertEqual(self.provider.stops,1)
        fallback_reboot.tick();self.assertEqual(self.provider.stops,1)
        self.provider.state='STOPPED';fallback_reboot.tick()
        with fallback_reboot.db() as db:self.assertEqual(db.execute('SELECT stopped FROM leases').fetchone()[0],1)
        with self.assertRaises(ValueError):fallback_reboot.arm(value['sessionId'],value['resourceId'],value['absoluteDeadline']+1,30)

    def test_guard_not_ready_bad_resource_clock_rollback_or_real_scope_fail_closed(self):
        self.fallback.arm=lambda *args:{'ready':False}
        value=self.sessions.start(self.scope);self.assertEqual(self.provider.starts,0);self.assertEqual(value['state'],'UNKNOWN')
        self.clock.step(-1);self.assertEqual(self.sessions.poll(value['sessionId'])['error'],'CLOCK_REGRESSED')
        with self.assertRaises(JobError):self.sessions.start({**self.scope,'scopeId':'e'*32,'simulation':False})

    def test_all_seven_states_observed_and_no_real_cloud_acceptance(self):
        states={'STOPPED'};value=self.sessions.start(self.scope);states.add(value['state'])
        self.provider.state='RUNNING';value=self.sessions.poll(value['sessionId']);states.add(value['state'])
        self.sessions.confirm_host(value['sessionId'],'HOST_FIXTURE_CURRENT');self.peer.model='ready'
        value=self.sessions.poll(value['sessionId']);states.add(value['state'])
        self.sessions.submit(value['sessionId'],self.job(value['sessionId']));states.add(self.sessions.latest()['state'])
        self.peer.offline=True;states.add(self.sessions.poll(value['sessionId'])['state'])
        states.add(self.sessions.request_stop(value['sessionId'])['state']);self.provider.state='STOPPED'
        states.add(self.sessions.poll(value['sessionId'])['state'])
        self.assertEqual(states,STATES)
        print(json.dumps({'states':sorted(states),'simulation':True,'realCloudAcceptance':False,'realGPUStarts':0,'provider':'explicit offline double'}))


class IndependentProcessTests(unittest.TestCase):
    @unittest.skipIf(os.name=='nt','Linux independent process acceptance')
    def test_separate_guard_survives_actual_cpu_http_process_exit(self):
        import base64
        from urllib.request import Request,urlopen
        from guard_process_fixture import create
        with tempfile.TemporaryDirectory(dir='/var/tmp') as directory:
            root=Path(directory);guard_root=root/'guard';guard_root.mkdir()
            (guard_root/'fixture-clock').write_text('100000')
            (guard_root/'fixture-provider.json').write_text(json.dumps({'state':'STOPPED','sid':None,'starts':0,'stops':0}))
            config=root/'guard.json';config.write_text(json.dumps({'schemaVersion':1,'enabled':True,'factory':'guard_process_fixture:create','simulation':True}));config.chmod(0o600)
            store=create(guard_root,{})
            scope={'scopeId':'a'*32,'resourceId':'RESOURCE_FIXTURE','expiresAt':102400,'budgetApproved':True,'idleSeconds':300,'simulation':True}
            initial=store.start(scope)
            environment=os.environ.copy();password='SYNTHETIC_CPU_PROCESS_PASSWORD_'+'X'*30
            environment['LIGHTTRY_ACCESS_PASSWORD']=password;environment.pop('LIGHTTRY_ACCOUNTS_FILE',None)
            environment['PYTHONPATH']=str(ROOT/'project/tests')
            cpu=None;guard=None
            with (root/'cpu.log').open('wb') as cpu_log,(root/'guard.log').open('wb') as guard_log:
                try:
                    cpu=subprocess.Popen([sys.executable,'-X','utf8','-B',str(ROOT/'start.py'),'--service','--data-root',str(root/'cpu')],env=environment,stdout=cpu_log,stderr=subprocess.STDOUT)
                    auth='Basic '+base64.b64encode(('lighttry:'+password).encode()).decode()
                    deadline=time.monotonic()+20
                    while True:
                        try:
                            with urlopen(Request('http://localhost:8080/api/health',headers={'Authorization':auth}),timeout=1) as response:
                                if response.status==200:break
                        except OSError:pass
                        if cpu.poll() is not None:self.fail((root/'cpu.log').read_text())
                        if time.monotonic()>deadline:self.fail('CPU ready timeout')
                        time.sleep(.1)
                    guard=subprocess.Popen([sys.executable,'-X','utf8','-B',str(ROOT/'start.py'),'--guard','--data-root',str(guard_root),'--guard-config',str(config)],env=environment,stdout=guard_log,stderr=subprocess.STDOUT)
                    def wait_state(expected):
                        end=time.monotonic()+15
                        while time.monotonic()<end:
                            if store.latest()['state']==expected:return store.latest()
                            if guard.poll() is not None:self.fail((root/'guard.log').read_text())
                            time.sleep(.1)
                        self.fail('Guard state timeout: '+expected)
                    state=wait_state('LOADING');running=state['runningAt'];work=state['workDeadline']
                    cpu.terminate();cpu.wait(timeout=10);self.assertEqual(cpu.returncode,0)
                    self.assertIsNone(guard.poll())
                    clock_file=guard_root/'fixture-clock';temporary=guard_root/'clock-update';temporary.write_text('100031');temporary.replace(clock_file)
                    state=wait_state('STOPPING');bound=state['stopWaitDeadline']
                    self.assertEqual(state['runningAt'],running);self.assertEqual(state['workDeadline'],work)
                    temporary.write_text(str(bound));temporary.replace(clock_file)
                    state=wait_state('UNKNOWN');self.assertEqual(state['error'],'STOPPING_BOUND_EXCEEDED')
                    provider=json.loads((guard_root/'fixture-provider.json').read_text());self.assertEqual(provider['starts'],1);self.assertEqual(provider['stops'],1)
                    provider['state']='STOPPED';(guard_root/'fixture-provider.json').write_text(json.dumps(provider))
                    guard.wait(timeout=15);self.assertEqual(guard.returncode,0)
                    self.assertTrue(store.latest()['verifiedStopped']);self.assertFalse(store.latest()['guardExited'])
                    store.record_guard_exit(initial['sessionId'],guard.poll()==0,True)
                    print(json.dumps({'independentGuardProcess':'PASS','cpuExited':True,'guardSurvivedCpu':True,'unchangedRunningEpoch':True,'stoppingBoundObserved':True,'simulation':True,'realCloudAcceptance':False}))
                finally:
                    for process in (cpu,guard):
                        if process and process.poll() is None:process.terminate();process.wait(timeout=10)


class WorkerProtocolTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir='/var/tmp' if os.name!='nt' else None)
        self.ledger=WorkerLedger(Path(self.tmp.name),'SYNTHETIC_RUNTIME_WORKER_TOKEN_'+'X'*32,'a'*32,'RESOURCE_FIXTURE')
        self.app=WorkerApplication(self.ledger);self.sent=[]
    def tearDown(self):self.ledger.close();self.tmp.cleanup()
    def client(self,status_override=None):
        parent=self
        class Connection:
            def __init__(self,host,port,timeout,context):
                parent.assertTrue(context.check_hostname);parent.assertEqual(context.verify_mode,ssl.CERT_REQUIRED);self.body=None
            def request(self,method,path,body=None,headers=None):
                parent.sent.append((method,path));self.body=body or b'';self.method=method;self.path=path;self.headers=headers
            def getresponse(self):
                responses=[]
                env={'REQUEST_METHOD':self.method,'PATH_INFO':self.path,'HTTP_AUTHORIZATION':self.headers['Authorization'],
                     'CONTENT_LENGTH':str(len(self.body)),'wsgi.input':io.BytesIO(self.body)}
                data=b''.join(parent.app(env,lambda status,headers:responses.append(int(status.split()[0]))))
                return type('Response',(),{'status':status_override or responses[0],'read':lambda _,n:data[:n]})()
            def close(self):pass
        return HTTPSWorker('https://WORKER_FIXTURE',self.ledger.token,connection_factory=Connection)
    def test_authenticated_https_upload_idempotent_submit_and_get_cannot_execute(self):
        client=self.client();artifact=client.upload(b'OFFLINE_ARTIFACT')
        body={'jobId':'b'*32,'sessionId':'a'*32,'resourceId':'RESOURCE_FIXTURE','artifactSha256':artifact['sha256'],'requestSha256':'d'*64}
        self.assertEqual(client.query(body['jobId'])['status'],'not_found')
        client.submit(body);client.submit(body);self.assertEqual(client.query(body['jobId'])['status'],'queued')
        calls=[];self.ledger.model_state='ready';self.ledger.executor=lambda job:calls.append(job) or 'succeeded'
        client.health();client.query(body['jobId']);self.assertEqual(calls,[])
        self.ledger.run_one();self.ledger.run_one();self.assertEqual(len(calls),1)
        self.assertEqual(client.query(body['jobId'])['status'],'succeeded')
    def test_auth_path_https_redirect_and_worker_restart_uncertainty(self):
        response=[]
        self.app({'REQUEST_METHOD':'GET','PATH_INFO':'/v1/health','wsgi.input':io.BytesIO()},lambda status,headers:response.append(status))
        self.assertTrue(response[0].startswith('401'))
        for url in ('http://worker','https://user:password@worker','https://worker/path'):
            with self.assertRaises(ValueError):HTTPSWorker(url,self.ledger.token)
        with self.assertRaises(LinkUncertain):self.client(302).health()
        self.assertEqual(len(self.sent),1)  # No redirect or automatic retry.
        sha=self.ledger.upload(hashlib.sha256(b'x').hexdigest(),b'x')['sha256']
        body={'jobId':'b'*32,'sessionId':'a'*32,'resourceId':'RESOURCE_FIXTURE','artifactSha256':sha,'requestSha256':'d'*64}
        self.ledger.accept(body)
        with self.ledger.db() as db:db.execute("UPDATE jobs SET state='dispatching'")
        self.ledger.close();self.ledger=WorkerLedger(Path(self.tmp.name),self.ledger.token,'a'*32,'RESOURCE_FIXTURE')
        self.assertEqual(self.ledger.query('b'*32)['status'],'uncertain')


if __name__=='__main__':unittest.main()
