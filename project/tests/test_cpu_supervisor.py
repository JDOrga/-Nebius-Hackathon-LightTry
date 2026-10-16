"""CPU-only protection tests: synthetic provider, no credentials or cloud calls."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch,Mock

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'project'))
from cpu_supervisor import CPUHostSupervisor,build_sessions
from gpu_session import Sessions
from gpu_bootstrap import ControlBinding,load_control
from guard_runtime import cpu_guard_step
from test_worker_guard import Clock,Peer,Provider


class CPUOnlyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)/'guard'
        self.clock=Clock();self.peer=Peer();self.provider=Provider(self.peer)
        self.gate=CPUHostSupervisor(self.root,'RESOURCE_FIXTURE',risk_accepted=True,clock=self.clock)
        self.sessions=Sessions(self.root,self.provider,self.peer,self.gate,self.clock,protection_mode='cpu-only')
        self.scope={'scopeId':'a'*32,'resourceId':'RESOURCE_FIXTURE','expiresAt':self.clock()+2400,
                    'budgetApproved':True,'idleSeconds':300,'simulation':True}
        self.control=ControlBinding(self.sessions,self.scope,self.clock)

    def tearDown(self):self.gate.close();self.tmp.cleanup()

    def ready(self):
        self.gate.acquire();cpu_guard_step(self.control)

    def test_no_implicit_risk_acceptance_and_one_guard(self):
        with self.assertRaises(ValueError):CPUHostSupervisor(self.root,'RESOURCE_FIXTURE')
        self.ready()
        other=CPUHostSupervisor(self.root,'RESOURCE_FIXTURE',risk_accepted=True,clock=self.clock)
        with self.assertRaises(ValueError):other.acquire()
        self.assertEqual(self.provider.starts,0)

    def test_missing_stale_wrong_resource_dead_pid_receipt_blocks_start(self):
        with self.assertRaises(Exception):self.gate.arm('b'*32,'RESOURCE_FIXTURE',100500,30)
        self.ready();original=self.gate.path.read_bytes()
        for change in ({'at':self.clock()-16},{'at':self.clock()+1},{'resourceId':'OTHER'},{'pid':0},
                       {'independentHost':True},{'guardRoot':'OTHER'}):
            value=json.loads(original);value.update(change);self.gate.path.write_text(json.dumps(value));self.gate.path.chmod(0o600)
            with self.assertRaises(ValueError):self.gate.arm('b'*32,'RESOURCE_FIXTURE',100500,30)
        self.gate.path.write_bytes(original)
        with self.assertRaises(ValueError):self.gate.arm('b'*32,'OTHER',100500,30)
        self.assertEqual(self.provider.starts,0)

    def test_idle_snapshot_read_only_unknown_not_stopped(self):
        self.assertEqual(self.sessions.latest()['state'],'UNKNOWN')
        self.ready()
        self.assertTrue(self.sessions.latest()['verifiedStopped'])
        self.assertTrue(self.sessions.latest()['simulation'])
        for _ in range(5):self.sessions.latest()
        self.assertEqual(self.provider.starts,0)
        self.provider.offline=True;cpu_guard_step(self.control)
        self.assertEqual(self.sessions.latest()['state'],'UNKNOWN')

    def test_cpu_policy_allows_same_host_but_never_claims_independence(self):
        self.ready();value=self.sessions.start(self.scope)
        self.assertEqual(value['state'],'STARTING');self.assertEqual(value['protectionMode'],'cpu-only')
        self.assertEqual(self.provider.starts,1)
        proof=self.gate.arm(value['sessionId'],'RESOURCE_FIXTURE',value['absoluteDeadline'],30)
        self.assertFalse(proof['independentHost']);self.assertFalse(proof['simulation'])
        self.sessions.start(self.scope);self.assertEqual(self.provider.starts,1)

    def test_default_off_host_policy_still_rejects_same_host(self):
        self.ready();self.sessions.protection_mode='off-host'
        self.assertEqual(self.sessions.start(self.scope)['state'],'UNKNOWN')
        self.assertEqual(self.provider.starts,0)

    def test_cpu_web_lease_loss_stops_and_guard_stays_idle_after_release(self):
        self.ready();value=self.sessions.start(self.scope);sid=value['sessionId']
        self.provider.state='RUNNING';self.sessions.poll(sid)
        original=self.sessions.get(sid);self.control.heartbeat_once();self.control.close()
        self.clock.step(31);cpu_guard_step(self.control)
        value=self.sessions.get(sid)
        self.assertTrue(value['stopSent']);self.assertEqual(self.provider.stops,1)
        self.assertEqual(value['absoluteDeadline'],original['absoluteDeadline'])
        self.assertEqual(value['workDeadline'],original['workDeadline'])
        self.provider.state='STOPPED';cpu_guard_step(self.control);cpu_guard_step(self.control)
        self.assertTrue(self.sessions.latest()['verifiedStopped'])
        self.assertIsNotNone(self.gate.lock)  # Persistent supervisor, not a false exit proof.
        self.assertEqual(self.provider.starts,1)

    def test_guard_restart_does_not_reset_deadlines_or_restart_gpu(self):
        self.ready();value=self.sessions.start(self.scope);sid=value['sessionId']
        self.gate.close();self.gate.acquire();cpu_guard_step(self.control)
        self.assertEqual(self.sessions.get(sid)['absoluteDeadline'],value['absoluteDeadline'])
        self.assertEqual(self.provider.starts,1)

    def test_gate_close_and_host_loss_are_not_stopped_proofs(self):
        self.ready();self.gate.close()
        self.assertEqual(self.sessions.latest()['state'],'UNKNOWN')
        self.assertFalse(self.sessions.latest()['verifiedStopped'])
        self.assertEqual(self.provider.stops,0)

    def test_ready_receipt_does_not_persist_provider_secrets(self):
        self.ready();value=self.provider.preflight('RESOURCE_FIXTURE');value['token']='PRIVATE_SYNTHETIC_SECRET'
        self.gate.publish(value)
        self.assertNotIn('PRIVATE_SYNTHETIC_SECRET',self.gate.path.read_text())

    def test_factory_builds_without_cloud_or_worker_requests(self):
        token=self.root/'worker-token';token.write_text('SYNTHETIC_'+'X'*40);token.chmod(0o600)
        binding={'providerFactory':'audited_provider:build','providerBinding':{},'workerOrigin':'https://worker.invalid',
                 'workerTokenFile':str(token),'workerCaFile':None}
        factory=Mock(return_value=self.provider)
        with patch('cpu_supervisor.importlib.import_module',return_value=type('M',(),{'build':factory})):
            sessions=build_sessions(self.root,binding)
        self.assertEqual(sessions.protection_mode,'cpu-only');factory.assert_called_once_with({})
        self.assertEqual(self.provider.starts,0)

    def test_deployment_is_same_host_and_templates_cannot_authorize_start(self):
        web=(ROOT/'deploy/lighttry.service').read_text()
        guard=(ROOT/'deploy/lighttry-guard.service').read_text()
        self.assertIn('Wants=lighttry-guard.service',web)
        self.assertNotIn('\nRequires=',web);self.assertNotIn('\nPartOf=',guard);self.assertNotIn('\nBindsTo=',guard)
        self.assertIn('--gpu-control-config /etc/lighttry/gpu-control.json',guard)
        value=json.loads((ROOT/'deploy/gpu-control.example.json').read_text())
        scope=json.loads((ROOT/'deploy/gpu-scope.example.json').read_text())
        self.assertIs(value['enabled'],False);self.assertIs(scope['budgetApproved'],False)
        self.assertEqual(scope['expiresAt'],0)
        self.assertEqual(value['protection']['mode'],'cpu-only')


class SeparateProcessTests(unittest.TestCase):
    @staticmethod
    def stop_child(process):
        if process is None or process.poll() is not None:return
        if os.name=='nt':
            # Windows venv python.exe is a launcher; terminate its OWN process
            # tree, not just the launcher (never kill processes by image name).
            result=subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True,timeout=5)
            if result.returncode and process.poll() is None:raise RuntimeError('SYNTHETIC_CHILD_TREE_NOT_STOPPED')
        else:process.terminate()
        process.wait(timeout=5)

    def test_real_local_guard_process_never_autostarts_and_survives_web_lease_loss(self):
        from guard_process_fixture import create
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);guard_root=root/'guard';guard_root.mkdir()
            (guard_root/'fixture-clock').write_text('100000')
            state_file=guard_root/'fixture-provider.json'
            state_file.write_text(json.dumps({'state':'STOPPED','sid':None,'starts':0,'stops':0}))
            scope={'scopeId':'a'*32,'resourceId':'RESOURCE_FIXTURE','expiresAt':time.time()+120,
                   'budgetApproved':True,'idleSeconds':300,'simulation':True}
            scope_path=root/'scope.json';scope_path.write_text(json.dumps(scope));scope_path.chmod(0o600)
            config=root/'control.json';config.write_text(json.dumps({'schemaVersion':1,'enabled':True,
                'factory':'guard_process_fixture:create','guardRoot':str(guard_root),'scopeFile':str(scope_path),'binding':{},
                'protection':{'mode':'cpu-only','cpuHostRiskAccepted':True}}));config.chmod(0o600)
            env=os.environ.copy();env['PYTHONPATH']=str(ROOT/'project/tests')+os.pathsep+str(ROOT/'project')
            control=load_control(config,ROOT)
            guard=None;web=None
            with (root/'guard.log').open('wb') as log:
                try:
                    guard=subprocess.Popen([sys.executable,'-X','utf8','-B',str(ROOT/'start.py'),'--guard',
                        '--data-root',str(guard_root),'--gpu-control-config',str(config)],env=env,stdout=log,stderr=subprocess.STDOUT)
                    def wait_for(predicate):
                        end=time.monotonic()+15
                        while time.monotonic()<end:
                            if predicate():return
                            if guard.poll() is not None:self.fail((root/'guard.log').read_text())
                            time.sleep(.1)
                        self.fail('local synthetic guard timeout')
                    wait_for(lambda:control.sessions.latest().get('verifiedStopped'))
                    self.assertEqual(json.loads(state_file.read_text())['starts'],0)
                    value=control.sessions.start(scope);sid=value['sessionId']
                    wait_for(lambda:control.sessions.get(sid)['state']=='LOADING')
                    deadlines=control.sessions.get(sid)
                    script="from gpu_bootstrap import load_control;from pathlib import Path;import time; c=load_control(Path(__import__('sys').argv[1]),Path(__import__('sys').argv[2]));c.start_heartbeat();time.sleep(60)"
                    web=subprocess.Popen([sys.executable,'-X','utf8','-B','-c',script,str(config),str(ROOT)],env=env,stdout=log,stderr=subprocess.STDOUT)
                    # Child represents only CPU/Web heartbeat, not HTTP acceptance.
                    time.sleep(.5);self.assertIsNone(web.poll());self.stop_child(web)
                    temp=guard_root/'clock-new';temp.write_text('100031');temp.replace(guard_root/'fixture-clock')
                    wait_for(lambda:control.sessions.get(sid)['stopSent'])
                    self.assertIsNone(guard.poll());self.assertEqual(json.loads(state_file.read_text())['starts'],1)
                    self.assertEqual(control.sessions.get(sid)['absoluteDeadline'],deadlines['absoluteDeadline'])
                    self.assertFalse(control.sessions.get(sid)['verifiedStopped'])
                finally:
                    self.stop_child(web)
                    self.stop_child(guard)
                    control.close()


if __name__=='__main__':unittest.main()
