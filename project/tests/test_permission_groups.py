"""Offline owner/ordinary-user authorization and rate policy; no cloud calls."""
import io
import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[2]
import sys
sys.path.insert(0,str(ROOT/'project'))
from service import Application,parser
from local_cpu import LocalApplication,options as local_options
from security import password_record


class PermissionGroupTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        account=self.root/'accounts.json'
        account.write_text(json.dumps({'schemaVersion':1,'accounts':{
            'lighttry':password_record('SYNTHETIC_ADMIN_'+'A'*32,role='operator'),
            'alice':password_record('SYNTHETIC_USER_'+'B'*32,role='user'),
            'bob':password_record('SYNTHETIC_USER_'+'C'*32,role='user')}}),encoding='utf-8')
        account.chmod(0o600)
        self.environment=patch.dict(os.environ,{'LIGHTTRY_LEGACY_OWNER':'lighttry'})
        self.environment.start();self.addCleanup(self.environment.stop)
        self.app=Application(parser().parse_args(['--data-root',str(self.root/'state'),'--accounts-file',str(account)]))
        self.addCleanup(self.app.close)
        self.sid='a'*32
        self.scope={'scopeId':'b'*32,'resourceId':'RESOURCE_FIXTURE','expiresAt':time.time()+600,
                    'budgetApproved':True,'idleSeconds':300,'simulation':True}
        self.snapshot={'sessionId':self.sid,'scopeId':self.scope['scopeId'],'resourceId':self.scope['resourceId'],
                       'state':'READY','lastObservedAt':time.time(),'verifiedStopped':False,'stopSent':False}
        self.sessions=Mock()
        self.sessions.latest.side_effect=lambda:dict(self.snapshot)
        self.sessions.request_stop.side_effect=lambda sid:{**self.snapshot,'stopSent':True,'state':'STOPPING'}
        self.sessions.start.side_effect=lambda scope:{**self.snapshot,'state':'STARTING'}
        self.app.gpu_sessions=self.sessions;self.app.gpu_scope=self.scope
        self.app.gpu_control=SimpleNamespace(bootstrap=None,auto_host_trust=False,close=lambda:None)

    def request(self,owner,path,method='GET',body=b'',ip='127.0.0.1',space=None):
        token,_=self.app.login_sessions.issue(owner)
        environ={'REQUEST_METHOD':method,'PATH_INFO':path,'wsgi.input':io.BytesIO(body),
                 'CONTENT_LENGTH':str(len(body)),'CONTENT_TYPE':'application/json',
                 'HTTP_HOST':'localhost:8080','HTTP_ORIGIN':'http://localhost:8080',
                 'HTTP_X_LIGHTTRY_TOKEN':self.app.handler.csrf_token,
                 'HTTP_COOKIE':'lighttry_session='+token+('; lighttry_space='+space if space else ''),'REMOTE_ADDR':ip}
        got=[];payload=b''.join(self.app(environ,lambda status,headers:got.append((int(status.split()[0]),dict(headers)))))
        return got[0][0],json.loads(payload) if payload.startswith(b'{') else payload

    def test_shared_key_browser_spaces_isolate_content_stop_and_rate(self):
        self.app.session_scoped_accounts=frozenset({'alice'})
        account_hash=self.app.accounts.users['alice']['hash']
        first=self.app.workspace.issue_browser_space('alice',account_hash)
        second=self.app.workspace.issue_browser_space('alice',account_hash)
        self.assertEqual(self.app.workspace.issue_browser_space('alice',account_hash,first),first)
        first_owner=self.app.workspace.browser_space('alice',account_hash,first)
        second_owner=self.app.workspace.browser_space('alice',account_hash,second)
        self.assertNotEqual(first_owner,second_owner)
        first_me=self.request('alice','/api/me',space=first)
        second_me=self.request('alice','/api/me',space=second)
        self.assertEqual(first_me[0],200);self.assertEqual(second_me[0],200)
        self.assertNotEqual(first_me[1]['workspaceId'],second_me[1]['workspaceId'])
        self.assertEqual(self.request('alice','/api/me',space=first)[1]['workspaceId'],first_me[1]['workspaceId'])
        self.assertEqual(self.request('alice','/api/me')[0],401)
        from PIL import Image
        picture=io.BytesIO();Image.new('RGB',(32,32),(72,109,84)).save(picture,format='PNG')
        photo_id='e'*32
        self.app.workspace.save_photo(photo_id,'private',picture.getvalue(),'image/png',first_owner)
        self.assertEqual([p['id'] for p in self.request('alice','/api/workspace',space=first)[1]['photos']],[photo_id])
        self.assertEqual(self.request('alice','/api/workspace',space=second)[1]['photos'],[])
        self.assertEqual(self.request('alice','/api/photos/'+photo_id,space=first)[0],200)
        self.assertEqual(self.request('alice','/api/photos/'+photo_id,space=second)[0],404)
        self.app.workspace.claim('plan','d'*32,first_owner)
        self.assertFalse(self.app.workspace.owned('plan','d'*32,second_owner))
        self.queued(first_owner,number=33)
        self.assertTrue(self.app.gpu_entry_info('alice',first_owner)['canStop'])
        self.assertFalse(self.app.gpu_entry_info('alice',second_owner)['canStop'])
        self.assertEqual(self.request('alice','/api/gpu/stop','POST',
            json.dumps({'sessionId':self.sid}).encode(),space=second)[0],403)
        now=[1000.];self.app.limiter.clock=lambda:now[0]
        for _ in range(10):
            self.assertNotEqual(self.request('alice','/api/language/recommend','POST',b'{}',space=first)[0],429)
        self.assertEqual(self.request('alice','/api/language/recommend','POST',b'{}',space=first)[0],429)
        self.assertNotEqual(self.request('alice','/api/language/recommend','POST',b'{}',space=second)[0],429)

    def test_standalone_deployment_requires_explicit_shared_account_opt_in(self):
        self.assertEqual(parser().parse_args([]).session_scoped_accounts,[])
        self.assertEqual(parser().parse_args(['--session-scoped-account','alice']).session_scoped_accounts,['alice'])

    def test_standalone_service_accepts_explicit_unbounded_role_policy(self):
        key_file=self.root/'provider-fixture.key'
        key_file.write_text('OFFLINE_SYNTHETIC_KEY_'+'X'*24);key_file.chmod(0o600)
        policy=self.root/'standalone-text-policy.json'
        policy.write_text(json.dumps({'schemaVersion':2,
            'user':{'ledgerFile':str(self.root/'standalone-user-ledger.json'),
                    'unbounded':True,'ownerAcceptsUnboundedCost':True},
            'operator':{'ledgerFile':str(self.root/'standalone-admin-ledger.json'),
                        'unbounded':True,'operatorAcceptsUnboundedCost':True}}))
        policy.chmod(0o600)
        args=parser().parse_args(['--data-root',str(self.root/'standalone-data'),
            '--accounts-file',str(self.root/'accounts.json'),'--language-config',str(policy),
            '--session-scoped-account','alice'])
        with patch.dict(os.environ,{'LIGHTTRY_NEMOTRON_KEY_FILE':str(key_file)}):
            app=Application(args)
            try:
                self.assertEqual(app.session_scoped_accounts,frozenset({'alice'}))
                self.assertTrue(app.language_for('alice').unbounded)
                self.assertIsNone(app.language_for('alice').budget)
                self.assertTrue(app.language_for('lighttry').unbounded)
                self.assertNotEqual(app.language_for('alice').ledger_path,
                                    app.language_for('lighttry').ledger_path)
            finally:app.close()

    def test_browser_space_persists_and_key_rotation_invalidates_old_space(self):
        self.app.session_scoped_accounts=frozenset({'alice'})
        account_hash=self.app.accounts.users['alice']['hash']
        token=self.app.workspace.issue_browser_space('alice',account_hash)
        scope=self.app.workspace.browser_space('alice',account_hash,token)
        from persistence import Workspace
        reopened=Workspace(self.app.workspace.root,self.app.handler.environment_library.environments,
            self.app.handler.lighting_capabilities,default_owner='lighttry')
        self.assertEqual(reopened.browser_space('alice',account_hash,token),scope)
        self.assertIsNone(reopened.browser_space('alice','a'*64,token))

    def test_shared_key_relogin_reuses_browser_cookie(self):
        from urllib.parse import urlencode
        self.app.session_scoped_accounts=frozenset({'alice'})
        def login(cookie=''):
            body=urlencode({'accessKey':'SYNTHETIC_USER_'+'B'*32}).encode()
            environ={'REQUEST_METHOD':'POST','PATH_INFO':'/auth/login','wsgi.input':io.BytesIO(body),
                'CONTENT_LENGTH':str(len(body)),'CONTENT_TYPE':'application/x-www-form-urlencoded',
                'HTTP_HOST':'localhost:8080','HTTP_ORIGIN':'http://localhost:8080',
                'HTTP_COOKIE':cookie,'REMOTE_ADDR':'127.0.0.1'}
            got=[];self.app(environ,lambda status,headers:got.append((status,headers)))
            self.assertTrue(got[0][0].startswith('303 '))
            return [v for k,v in got[0][1] if k=='Set-Cookie']
        first=login()
        self.assertEqual(len(first),2)
        space=next(v.split(';',1)[0] for v in first if v.startswith('lighttry_space='))
        session=next(v.split(';',1)[0] for v in first if v.startswith('lighttry_session='))
        second=login(space+'; '+session)
        self.assertIn(space,second[0])
        self.assertNotEqual(session,next(v.split(';',1)[0] for v in second if v.startswith('lighttry_session=')))

    def queued(self,owner,state='waiting',number=1):
        identity=('%032x'%number)
        with self.app.workspace.connect() as db:
            db.execute('INSERT INTO gpu_queue VALUES (?,?,?,?,?,?,?,?,?)',
                       (identity,owner,identity,'f'*64,'{}','image/png',state,time.time(),None))
        return identity

    def test_user_may_start_only_through_existing_safe_stopped_gate(self):
        self.snapshot.update(state='STOPPED',verifiedStopped=True)
        self.assertTrue(self.app.gpu_entry_info('alice')['canStart'])
        status,_=self.request('alice','/api/gpu/entry-start','POST',json.dumps({'requestId':'c'*32}).encode())
        self.assertEqual(status,202);self.app.entry_thread.join(2)
        self.sessions.start.assert_called_once()
        self.snapshot.update(state='UNKNOWN',verifiedStopped=False)
        self.assertFalse(self.app.gpu_entry_info('alice')['canStart'])

    def test_user_can_stop_empty_or_all_own_queue_but_not_foreign_work(self):
        status,_=self.request('alice','/api/gpu/stop','POST',json.dumps({'sessionId':self.sid}).encode())
        self.assertEqual(status,202)
        self.sessions.request_stop.reset_mock()
        self.queued('alice',number=1);self.queued('alice','active',number=2)
        self.assertTrue(self.app.gpu_entry_info('alice')['canStop'])
        status,_=self.request('alice','/api/gpu/stop','POST',json.dumps({'sessionId':self.sid}).encode())
        self.assertEqual(status,202)
        self.sessions.request_stop.reset_mock()
        self.queued('bob',number=3)
        info=self.app.gpu_entry_info('alice')
        self.assertFalse(info['canStop']);self.assertTrue(info['stopBlockedByOtherTasks'])
        status,body=self.request('alice','/api/gpu/stop','POST',json.dumps({'sessionId':self.sid}).encode())
        self.assertEqual(status,403);self.assertEqual(body['error']['code'],'FOREIGN_GPU_TASK')
        self.sessions.request_stop.assert_not_called()
        self.assertTrue(self.app.gpu_entry_info('lighttry')['canStop'])
        status,_=self.request('lighttry','/api/gpu/stop','POST',json.dumps({'sessionId':self.sid}).encode())
        self.assertEqual(status,202);self.sessions.request_stop.assert_called_once_with(self.sid)

    def test_foreign_blocked_dispatch_and_unknown_legacy_active_fail_closed(self):
        self.queued('bob','blocked',number=4)
        self.assertTrue(self.app.queue.foreign_in_flight('alice'))
        with self.app.workspace.connect() as db:db.execute("UPDATE gpu_queue SET state='done'")
        folder=self.app.handler.task_store.root/('5'*32);folder.mkdir()
        (folder/'task.json').write_text(json.dumps({'status':'running','executionUncertain':False}))
        self.assertTrue(self.app.queue.foreign_in_flight('alice'))

    def test_foreign_enqueue_before_stop_latch_is_rechecked_under_queue_lock(self):
        results=[]
        with self.app.queue.mutex:
            worker=threading.Thread(target=lambda:results.append(self.request(
                'alice','/api/gpu/stop','POST',json.dumps({'sessionId':self.sid}).encode())))
            worker.start()
            self.queued('bob',number=9)
        worker.join(2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(results[0][0],403)
        self.sessions.request_stop.assert_not_called()

    def test_admin_authenticated_requests_bypass_app_rate_but_login_remains_limited(self):
        self.app.limiter.limits.update(ip=1,user=1,write=1,generate=1,upload=1)
        for _ in range(4):self.assertEqual(self.request('lighttry','/api/me')[0],200)
        for _ in range(12):
            self.assertNotEqual(self.request('lighttry','/api/language/recommend','POST',b'{}')[0],429)
        self.assertEqual(self.request('alice','/api/me')[0],200)
        self.assertEqual(self.request('alice','/api/me')[0],429)

    def test_user_nemotron_has_rolling_ten_per_sixty_seconds(self):
        now=[1000.]
        self.app.limiter.clock=lambda:now[0]
        for _ in range(10):
            status,_=self.request('alice','/api/language/recommend','POST',b'{}')
            self.assertNotEqual(status,429)
        self.assertEqual(self.request('alice','/api/language/recommend','POST',b'{}')[0],429)
        self.assertNotEqual(self.request('bob','/api/language/recommend','POST',b'{}')[0],429)
        now[0]+=59
        self.assertEqual(self.request('alice','/api/language/recommend','POST',b'{}')[0],429)
        now[0]+=1
        self.assertNotEqual(self.request('alice','/api/language/recommend','POST',b'{}')[0],429)

    def test_local_profile_can_prepare_two_accounts_with_separate_text_ledgers(self):
        accounts=self.root/'accounts.json'
        key_file=self.root/'nemotron.key';key_file.write_text('OFFLINE_SYNTHETIC_KEY_'+'X'*24)
        key_file.chmod(0o600)
        text_config=self.root/'text-roles.json'
        text_config.write_text(json.dumps({'schemaVersion':2,
            'user':{'ledgerFile':str(self.root/'user-ledger.json'),'maxCalls':1,'budgetUsd':.02},
            'operator':{'ledgerFile':str(self.root/'operator-ledger.json'),
                        'unbounded':True,'operatorAcceptsUnboundedCost':True}}))
        text_config.chmod(0o600)
        profile=self.root/'local-profile.json'
        profile.write_text(json.dumps({'schemaVersion':1,'publicOrigin':'http://127.0.0.1:8785',
            'accountsFile':str(accounts),'dataRoot':str(self.root/'local-state'),
            'statusSettingsFile':None,'gpuControlConfig':None,'modelGrantFile':None}))
        profile.chmod(0o600)
        paths={'local_cpu_config':str(profile),'assets_dir':None,
               'tasks_dir':str(self.root/'local-tasks'),'accepted_packages':[],
               'language_config':str(text_config)}
        with patch.dict(os.environ,{'LIGHTTRY_RECIPE_LANGUAGE_CONFIG_FILE':str(self.root/'missing-text-policy.json'),
                                    'LIGHTTRY_NEMOTRON_KEY_FILE':str(key_file)}):
            app=LocalApplication(local_options(paths))
            try:
                self.assertEqual(set(app.accounts.users),{'lighttry','alice','bob'})
                self.assertEqual(app.language_for('alice').ledger_scope,'user')
                self.assertFalse(app.language_for('alice').unbounded)
                self.assertEqual(app.language_for('lighttry').ledger_scope,'operator')
                self.assertTrue(app.language_for('lighttry').unbounded)
                self.assertNotEqual(app.language_for('alice').ledger_path,
                                    app.language_for('lighttry').ledger_path)
            finally:app.close()
            policy=json.loads(text_config.read_text());policy['user']=None
            text_config.write_text(json.dumps(policy));text_config.chmod(0o600)
            app=LocalApplication(local_options(paths))
            try:
                self.assertIsNone(app.language_for('alice'))
                self.assertTrue(app.language_for('lighttry').unbounded)
            finally:app.close()
            policy['user']={'ledgerFile':str(self.root/'user-unbounded-ledger.json'),
                'unbounded':True,'ownerAcceptsUnboundedCost':True}
            text_config.write_text(json.dumps(policy));text_config.chmod(0o600)
            app=LocalApplication(local_options(paths))
            try:
                self.assertTrue(app.language_for('alice').unbounded)
                self.assertIsNone(app.language_for('alice').budget)
                self.assertIsNone(app.language_for('alice').max_calls)
                self.assertEqual(app.language_for('alice').ledger_scope,'user')
            finally:app.close()


if __name__=='__main__':unittest.main()
