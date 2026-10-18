"""Real WSGI authentication/queue wiring with synthetic private profiles; no cloud."""
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace
from urllib.parse import urlencode
from unittest.mock import Mock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from local_cpu import LocalApplication,options
from security import password_record

KEY='SYNTHETIC_LOCAL_OPERATOR_'+'X'*32


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.accounts=self.root/'accounts.json'
        self.accounts.write_text(json.dumps({'schemaVersion':1,'accounts':{'lighttry':password_record(KEY,role='operator')}}));self.accounts.chmod(0o600)
        self.profile=self.root/'profile.json'
        self.value={'schemaVersion':1,'publicOrigin':'http://127.0.0.1:8785','accountsFile':str(self.accounts),
            'dataRoot':str(self.root/'private'),'statusSettingsFile':None,'gpuControlConfig':None,'modelGrantFile':None}
        self.paths={'local_cpu_config':str(self.profile),'assets_dir':None,'tasks_dir':str(self.root/'original-tasks'),
                    'accepted_packages':[]}
        self.write_profile();self.app=LocalApplication(options(self.paths))
    def write_profile(self):self.profile.write_text(json.dumps(self.value));self.profile.chmod(0o600)
    def tearDown(self):self.app.close();self.tmp.cleanup()
    def request(self,path,method='GET',body=b'',cookie='',extra=None):
        env={'REQUEST_METHOD':method,'PATH_INFO':path,'wsgi.input':io.BytesIO(body),'HTTP_HOST':'127.0.0.1:8785',
             'REMOTE_ADDR':'127.0.0.1','CONTENT_LENGTH':str(len(body)),'CONTENT_TYPE':'application/json','HTTP_COOKIE':cookie,
             'HTTP_ACCEPT_LANGUAGE':'zh-CN'}
        if method!='GET':env.update(HTTP_ORIGIN=self.app.origin,HTTP_X_LIGHTTRY_TOKEN=self.app.handler.csrf_token)
        if path=='/auth/login':env['CONTENT_TYPE']='application/x-www-form-urlencoded'
        env.update(extra or {});response=[]
        out=b''.join(self.app(env,lambda status,headers:response.append((int(status.split()[0]),dict(headers)))))
        return *response[0],out
    def login(self):
        status,headers,_=self.request('/auth/login','POST',urlencode({'accessKey':KEY}).encode())
        self.assertEqual(status,303);return headers['Set-Cookie'].split(';')[0]
    def test_original_task_root_retained_and_no_provider_enabled(self):
        self.assertEqual(self.app.handler.task_store.root,Path(self.paths['tasks_dir']))
        self.assertIsNone(self.app.gpu_control);self.assertIsNone(self.app.model_executor)
        self.assertIsNone(self.app.handler.local_cpu_api)
    def test_anonymous_cannot_read_or_start_but_can_open_login(self):
        for path in ['/','/api/health','/workbench.js','/api/gpu/entry-status','/api/gpu/connection-readiness']:
            self.assertEqual(self.request(path)[0],401)
        self.assertEqual(self.request('/api/gpu/entry-start','POST',b'{}')[0],401)
        status,headers,body=self.request('/login');self.assertEqual(status,200)
        self.assertIn(b'accessKey',body);self.assertEqual(headers['Referrer-Policy'],'same-origin')
    def test_login_retains_single_owner_browser_namespace_and_private_status(self):
        cookie=self.login();me=json.loads(self.request('/api/me',cookie=cookie)[2])
        self.assertTrue(me['localWorkspace']);self.assertEqual(me['role'],'operator')
        health=json.loads(self.request('/api/health',cookie=cookie)[2]);self.assertTrue(health['authenticated'])
        self.assertFalse(health['paidServices'])
        ready=json.loads(self.request('/api/gpu/connection-readiness',cookie=cookie)[2])
        self.assertFalse(ready['canStart']);self.assertTrue(ready['authenticated'])
        self.assertNotIn('AUTHENTICATED_CONTROL_BINDING_REQUIRED',ready['blockers'])
        self.assertEqual(self.request('/api/workspace',cookie=cookie)[0],200)
        self.assertEqual(self.request('/api/inference/capabilities',cookie=cookie)[0],200)
    def test_real_start_route_fails_closed_without_current_binding(self):
        cookie=self.login()
        status,_,body=self.request('/api/gpu/entry-start','POST',json.dumps({'requestId':'a'*32}).encode(),cookie)
        self.assertEqual(status,503);self.assertEqual(json.loads(body)['error']['code'],'CONTROL_NOT_CONFIGURED')
        self.assertNotIn(KEY,body.decode())
    def test_operator_start_uses_same_once_only_production_controller(self):
        cookie=self.login();sessions=Mock();sessions.latest.return_value={'state':'STOPPED','verifiedStopped':True,'lastObservedAt':time.time()}
        sessions.start.return_value={'state':'STARTING'}
        self.app.gpu_sessions=sessions;self.app.gpu_scope={'scopeId':'a'*32,'expiresAt':time.time()+60,'budgetApproved':True}
        for _ in range(2):
            status,_,_=self.request('/api/gpu/entry-start','POST',json.dumps({'requestId':'b'*32}).encode(),cookie)
            self.assertEqual(status,202)
        self.app.entry_thread.join(timeout=2);sessions.start.assert_called_once()
    def test_csrf_foreign_origin_and_user_still_need_configured_gpu_control(self):
        cookie=self.login();body=json.dumps({'requestId':'a'*32}).encode()
        self.assertEqual(self.request('/api/gpu/entry-start','POST',body,cookie,{'HTTP_X_LIGHTTRY_TOKEN':'BAD'})[0],403)
        self.assertEqual(self.request('/api/gpu/entry-start','POST',body,cookie,{'HTTP_ORIGIN':'https://evil.test'})[0],403)
        self.app.accounts.users['lighttry']['role']='user'
        self.assertEqual(self.request('/api/gpu/entry-start','POST',body,cookie)[0],503)
    def test_private_profile_rejects_public_origin_and_environment_cannot_enable_paid(self):
        with patch.dict(os.environ,{'LIGHTTRY_GPU_CONTROL_CONFIG':'UNTRUSTED_ENV','LIGHTTRY_MODEL_GRANT_FILE':'UNTRUSTED_ENV'}):
            opt=options(self.paths);self.assertIsNone(opt.gpu_control_config);self.assertIsNone(opt.model_grant_file)
        self.value['publicOrigin']='http://0.0.0.0:8785';self.write_profile()
        with self.assertRaisesRegex(ValueError,'EXACT_LOOPBACK_HTTP_ORIGIN_REQUIRED'):options(self.paths)
    def test_budget_preference_is_visible_but_not_start_authorization(self):
        self.app.start_policy={'budgetUsdIncludingTax':3}
        cookie=self.login()
        info=json.loads(self.request('/api/gpu/entry-status',cookie=cookie)[2])
        self.assertEqual(info['budgetUsdIncludingTax'],3);self.assertFalse(info['canStart'])
        self.assertFalse(info['budgetHardCap'])
        status,_,html=self.request('/gpu-entry',cookie=cookie)
        self.assertEqual(status,200);self.assertIn('3.00 美元'.encode(),html)
    def test_current_fingerprint_is_required_and_stop_is_bound_to_same_session(self):
        cookie=self.login();sid='b'*32;host={'vmId':'SYNTHETIC_VM','ip':'203.0.113.1'}
        snapshot={'sessionId':sid,'scopeId':'a'*32,'resourceId':'RESOURCE_FIXTURE','state':'LOADING','lastObservedAt':time.time(),
                  'hostIdentity':host,'hostConfirmed':False,'verifiedStopped':False,'stopSent':False}
        sessions=Mock();sessions.latest.return_value=snapshot
        sessions.protection_mode='cpu-only'
        sessions.confirm_host.return_value={**snapshot,'hostConfirmed':True}
        sessions.request_stop.return_value={**snapshot,'stopSent':True,'state':'STOPPING'}
        bootstrap=Mock();bootstrap.public.return_value={'stage':'awaiting_host_confirmation','canConfirm':True,
            'sessionId':sid,'hostIdentity':host,'fingerprint':'SHA256:SYNTHETIC'}
        self.app.gpu_sessions=sessions;self.app.gpu_scope={'scopeId':'a'*32,'resourceId':'RESOURCE_FIXTURE','expiresAt':time.time()+60}
        self.app.gpu_control=SimpleNamespace(bootstrap=bootstrap,close=lambda:None)
        status,_,raw=self.request('/api/gpu/entry-status',cookie=cookie);self.assertEqual(status,200,raw)
        info=json.loads(raw);self.assertTrue(info['canStop'])
        self.assertTrue(info['hostConfirmation']['canConfirm'])
        body={'sessionId':sid,'hostIdentity':host}
        self.assertEqual(self.request('/api/gpu/confirm-host','POST',json.dumps(body).encode(),cookie)[0],422)
        bootstrap.confirm.assert_not_called()
        body['fingerprint']='SHA256:SYNTHETIC'
        self.assertEqual(self.request('/api/gpu/confirm-host','POST',json.dumps(body).encode(),cookie)[0],200)
        bootstrap.confirm.assert_called_once_with(sid,host,'SHA256:SYNTHETIC')
        self.assertEqual(self.request('/api/gpu/stop','POST',json.dumps({'sessionId':'c'*32}).encode(),cookie)[0],404)
        sessions.request_stop.assert_not_called()
        self.assertEqual(self.request('/api/gpu/stop','POST',json.dumps({'sessionId':sid}).encode(),cookie)[0],202)
        sessions.request_stop.assert_called_once_with(sid)

    def test_owner_auto_trust_hides_browser_confirmation_and_rejects_manual_post(self):
        cookie=self.login();sid='b'*32;host={'vmId':'SYNTHETIC_VM','ip':'203.0.113.1'}
        snapshot={'sessionId':sid,'scopeId':'a'*32,'resourceId':'RESOURCE_FIXTURE','state':'LOADING',
                  'lastObservedAt':time.time(),'hostIdentity':host,'hostConfirmed':False,
                  'verifiedStopped':False,'stopSent':False}
        sessions=Mock();sessions.latest.return_value=snapshot;sessions.protection_mode='cpu-only'
        bootstrap=Mock();bootstrap.public.return_value={'stage':'awaiting_host_confirmation','canConfirm':True,
            'sessionId':sid,'hostIdentity':host,'fingerprint':'SHA256:SYNTHETIC'}
        self.app.gpu_sessions=sessions
        self.app.gpu_scope={'scopeId':'a'*32,'resourceId':'RESOURCE_FIXTURE','expiresAt':time.time()+60}
        self.app.gpu_control=SimpleNamespace(bootstrap=bootstrap,auto_host_trust=True,close=lambda:None)
        status,_,raw=self.request('/api/gpu/entry-status',cookie=cookie)
        self.assertEqual(status,200,raw);info=json.loads(raw)
        self.assertFalse(info['hostConfirmation']['canConfirm'])
        self.assertTrue(info['hostConfirmation']['automatic'])
        self.assertIn('自动绑定',info['message'])
        body={'sessionId':sid,'hostIdentity':host,'fingerprint':'SHA256:SYNTHETIC'}
        status,_,raw=self.request('/api/gpu/confirm-host','POST',json.dumps(body).encode(),cookie)
        self.assertEqual(status,409,raw)
        bootstrap.confirm.assert_not_called();sessions.confirm_host.assert_not_called()


class WSLTests(unittest.TestCase):
    def test_native_call_is_bounded_shell_free_and_only_cli_crosses_wsl(self):
        from nebius_wsl import WSLNebiusProvider
        provider=WSLNebiusProvider.__new__(WSLNebiusProvider)
        provider.cli=Path('/FIXTURE/wsl.exe');provider.settings={'configFile':'UNC_FIXTURE','profile':'PROFILE_FIXTURE'}
        provider.wsl={'wslDistro':'UBUNTU_FIXTURE','linuxCliPath':'/home/FIXTURE/nebius','linuxConfigFile':'/home/FIXTURE/config.yaml'}
        provider.clock=lambda:100;provider.runner=Mock(return_value=SimpleNamespace(returncode=0,stdout='{}',stderr=''))
        provider._call(['ai','devlab','get','--id','RESOURCE_FIXTURE'],deadline=103)
        args,kw=provider.runner.call_args
        self.assertEqual(args[0][:5],[str(provider.cli),'-d','UBUNTU_FIXTURE','--','/home/FIXTURE/nebius'])
        self.assertIn('/home/FIXTURE/config.yaml',args[0]);self.assertNotIn('UNC_FIXTURE',args[0])
        self.assertFalse(kw['shell']);self.assertEqual(kw['timeout'],3)
        self.assertNotIn('sessions.sqlite3',' '.join(args[0]))


if __name__=='__main__':unittest.main()
