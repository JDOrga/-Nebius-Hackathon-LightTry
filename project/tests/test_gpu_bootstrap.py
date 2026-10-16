"""Offline control wiring, synthetic adapters only. No cloud credentials/network."""
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'project'))
from gpu_bootstrap import ControlBinding,load_control
from gpu_session import Sessions
from service import parser


class ControlTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.scope={'scopeId':'a'*32,'resourceId':'SYNTHETIC_RESOURCE','expiresAt':200,
                    'budgetApproved':True,'idleSeconds':60,'simulation':True}
        self.value={'schemaVersion':1,'enabled':True,'factory':'audited_fixture:create',
                    'guardRoot':str(self.root/'guard'),'scopeFile':str(self.root/'scope.json'),'binding':{}}
        self.sessions=Sessions.__new__(Sessions)
        self.sessions.provider=SimpleNamespace(simulation=True)
        self.sessions.worker=SimpleNamespace(simulation=True)
        self.sessions.fallback=SimpleNamespace(simulation=True)
        self.sessions.latest=Mock(return_value={})
        self.sessions.heartbeat=Mock()
        self.sessions.start=Mock(side_effect=AssertionError('NO START IN BOOTSTRAP'))
        self.factory=Mock(return_value=self.sessions)
        self.module=patch('gpu_bootstrap.importlib.import_module',return_value=SimpleNamespace(create=self.factory))
        self.module.start()

    def tearDown(self):
        self.module.stop();self.tmp.cleanup()

    def load(self):
        for name,value in (('scope.json',self.scope),('control.json',self.value)):
            p=self.root/name;p.write_text(json.dumps(value));p.chmod(0o600)
        return load_control(self.root/'control.json',ROOT,clock=lambda:100)

    def test_default_off_and_explicit_parser(self):
        self.assertIsNone(load_control(None,ROOT));self.factory.assert_not_called()
        self.assertEqual(str(parser().parse_args(['--gpu-control-config',str(self.root/'control.json')]).gpu_control_config),str(self.root/'control.json'))
    def test_unreviewed_bootstrap_factory_never_runs(self):
        self.value['bootstrap']={'factory':'arbitrary_plugin:execute','binding':{}}
        with self.assertRaisesRegex(ValueError,'AUDITED_SSH_BOOTSTRAP_FACTORY_REQUIRED'):self.load()
        self.sessions.start.assert_not_called()

    def test_bind_without_observe_start_or_heartbeat(self):
        control=self.load()
        self.assertIs(control.sessions,self.sessions)
        self.assertEqual(control.scope,self.scope)
        self.sessions.latest.assert_not_called();self.sessions.start.assert_not_called()
        self.sessions.heartbeat.assert_not_called()

    def test_actual_application_registers_binding_without_start(self):
        import test_key_login as login
        self.scope['expiresAt']=time.time()+120
        self.load()
        harness=login.KeyLoginTests(methodName='test_page_and_no_basic_auth')
        with patch.dict(os.environ,{'LIGHTTRY_GPU_CONTROL_CONFIG':str(self.root/'control.json')}):
            harness.setUp()
            try:
                self.assertIs(harness.app.gpu_sessions,self.sessions)
                self.assertEqual(harness.app.gpu_scope,self.scope)
                self.assertIsNone(harness.app.gpu_control.thread)
                self.sessions.start.assert_not_called()
                self.sessions.heartbeat.assert_not_called()
            finally:
                harness.tearDown()

    def test_invalid_scope_rejected_before_factory(self):
        for field,value in (('expiresAt',99),('expiresAt',float('nan')),('budgetApproved',False),
                            ('idleSeconds',True),('scopeId','old'),('simulation','false')):
            old=self.scope[field];self.scope[field]=value
            with self.assertRaises(ValueError):self.load()
            self.scope[field]=old
        self.factory.assert_not_called()

    def test_unknown_configuration_and_in_code_paths_rejected(self):
        self.value['extra']='not allowed'
        with self.assertRaises(ValueError):self.load()
        del self.value['extra'];self.value['guardRoot']=str(ROOT/'.local/guard')
        with self.assertRaises(ValueError):self.load()
        self.factory.assert_not_called()

    def test_real_scope_rejects_simulation_and_wrong_factory(self):
        self.scope['simulation']=False
        with self.assertRaisesRegex(ValueError,'SIMULATION'):self.load()
        self.factory.return_value=object()
        with self.assertRaisesRegex(ValueError,'SESSIONS'):self.load()

    def test_cpu_policy_requires_explicit_risk_and_matching_root(self):
        self.value['protection']={'mode':'cpu-only','cpuHostRiskAccepted':False}
        with self.assertRaises(ValueError):self.load()
        self.factory.assert_not_called()
        self.value['protection']['cpuHostRiskAccepted']=True
        self.sessions.root=self.root/'guard'
        control=self.load()
        self.assertEqual(control.sessions.protection_mode,'cpu-only')
        self.assertFalse(control.sessions.fallback.simulation)
        self.assertEqual(control.sessions.fallback.protection_mode,'cpu-only')
        self.sessions.root=self.root/'OTHER'
        with self.assertRaisesRegex(ValueError,'ROOT_MISMATCH'):self.load()

    def test_expired_revoked_scope_can_only_load_stop_observer(self):
        self.scope['expiresAt']=99;self.scope['budgetApproved']=False
        self.value['enabled']=False
        with self.assertRaises(ValueError):self.load()
        control=load_control(self.root/'control.json',ROOT,clock=lambda:100,observer=True)
        self.assertEqual(control.scope['expiresAt'],99)
        self.sessions.start.assert_not_called()

    def test_heartbeat_only_current_live_binding(self):
        control=self.load()
        state={'scopeId':self.scope['scopeId'],'resourceId':self.scope['resourceId'],
               'sessionId':'b'*32,'verifiedStopped':False}
        self.sessions.latest.return_value=state
        control.heartbeat_once();self.sessions.heartbeat.assert_called_once_with('b'*32)
        for change in ({'scopeId':'c'*32},{'resourceId':'OTHER'},{'verifiedStopped':True},{'sessionId':None}):
            self.sessions.heartbeat.reset_mock();self.sessions.latest.return_value={**state,**change}
            control.heartbeat_once();self.sessions.heartbeat.assert_not_called()
        control.clock=lambda:201;self.sessions.latest.return_value=state
        control.heartbeat_once();self.sessions.heartbeat.assert_not_called()
        self.sessions.start.assert_not_called()

    def test_failure_stops_renewal_no_retry(self):
        control=self.load();entered=threading.Event()
        def fail():entered.set();raise RuntimeError('PRIVATE_SECRET_NOT_LOGGED')
        control.heartbeat_once=fail
        with self.assertLogs('lighttry.service',level='ERROR') as logs:
            control.start_heartbeat();first=control.thread;control.start_heartbeat()
            self.assertTrue(entered.wait(1));first.join(1)
        self.assertIs(first,control.thread);self.assertFalse(first.is_alive())
        self.assertNotIn('PRIVATE_SECRET',str(logs.output));control.close()

    @unittest.skipIf(os.name=='nt','POSIX private-file mode enforcement')
    def test_world_readable_config_rejected(self):
        self.load();p=self.root/'control.json';p.chmod(0o644)
        with self.assertRaises(ValueError):load_control(p,ROOT)


if __name__=='__main__':unittest.main()
