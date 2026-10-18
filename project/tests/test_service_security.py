"""Security acceptance uses synthetic executors/keys only. No provider/network calls."""
import base64
import copy
import io
import json
import os
from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'project'));sys.path.insert(0,str(ROOT/'project/tests'))
from service import Application,parser
from security import password_record,create_temporary_account,ProviderSecrets
from inference.jobs import JobError
from inference_fixture import OfflineExecutor,image_bytes
from gpu_queue import GPUQueue
from light_console import encode_hdr
import numpy as np

PASS='SYNTHETIC_TEST_PASSWORD_'+'X'*24
OTHER='SYNTHETIC_OTHER_PASSWORD_'+'Y'*24
AUTH=lambda user,password:'Basic '+base64.b64encode((user+':'+password).encode()).decode()


def request(app,path,method='GET',body=b'',user='lighttry',password=PASS,extra=None):
    env={'REQUEST_METHOD':method,'PATH_INFO':path,'wsgi.input':io.BytesIO(body),'CONTENT_LENGTH':str(len(body)),
         'CONTENT_TYPE':'application/json','HTTP_HOST':'localhost:8080','REMOTE_ADDR':'127.0.0.1',
         'HTTP_AUTHORIZATION':AUTH(user,password) if user else '',
         'HTTP_ORIGIN':'http://localhost:8080','HTTP_X_LIGHTTRY_TOKEN':app.handler.csrf_token}
    if user and app.accounts.authenticate(AUTH(user,password)) == user:
        token,_=app.login_sessions.issue(user);env['HTTP_COOKIE']='lighttry_session='+token
    env.update(extra or {});captured=[]
    value=b''.join(app(env,lambda status,headers:captured.append((int(status.split()[0]),dict(headers)))))
    return captured[0][0],value,captured[0][1]


class ApprovedOfflineExecutor(OfflineExecutor):
    def __init__(self):super().__init__();self.approved=True
    def authorize_job(self,owner,metadata,fingerprint):return self.approved


class ServiceSecurityTests(unittest.TestCase):
    def setUp(self):
        self.old_tmp=tempfile.tempdir
        self.tmp=tempfile.TemporaryDirectory(dir='/var/tmp' if os.name!='nt' else None)
        self.root=Path(self.tmp.name)
        account=self.root/'accounts.json'
        account.write_text(json.dumps({'schemaVersion':1,'accounts':{
            'lighttry':password_record(PASS),'other':password_record(OTHER),
            'operator':password_record(OTHER,role='operator')}}))
        account.chmod(0o600)
        self.options=parser().parse_args(['--data-root',str(self.root/'state'),'--accounts-file',str(account)])
        self.env=patch.dict(os.environ,{'LIGHTTRY_LEGACY_OWNER':'lighttry'});self.env.start()
        self.app=Application(self.options)

    def tearDown(self):
        self.app.close();tempfile.tempdir=self.old_tmp;self.env.stop();self.tmp.cleanup()

    def test_browser_language_and_manual_cookie_localize_entry_without_auth_change(self):
        status,body,_=request(self.app,'/login',user=None,extra={'HTTP_ACCEPT_LANGUAGE':'en-US,en;q=0.8'})
        self.assertEqual(status,200)
        self.assertIn(b'<html lang="en">',body)
        self.assertIn(b'Enter your access key',body)
        status,body,_=request(self.app,'/login',user=None,extra={'HTTP_ACCEPT_LANGUAGE':'en-US','HTTP_COOKIE':'lighttry_lang=zh'})
        self.assertEqual(status,200)
        self.assertIn(b'<html lang="zh-CN">',body)
        status,_,headers=request(self.app,'/lang/en',user=None,extra={'HTTP_ACCEPT_LANGUAGE':'zh-CN'})
        self.assertEqual(status,303)
        self.assertIn('lighttry_lang=en',headers['Set-Cookie'])
        status,body,_=request(self.app,'/gpu-entry',extra={'HTTP_ACCEPT_LANGUAGE':'en-US'})
        self.assertEqual(status,200)
        self.assertIn(b'<html lang="en">',body)
        self.assertIn(b'Enter without starting',body)
        self.app.handler.task_store.executor=ApprovedOfflineExecutor()
        metadata={'inputId':'a'*32,'requestId':'c'*32,'presetId':'sunny','name':'test'}
        headers={'CONTENT_TYPE':'image/jpeg','HTTP_ACCEPT_LANGUAGE':'en-US',
                 'HTTP_X_LIGHTTRY_REQUEST':base64.b64encode(json.dumps(metadata).encode()).decode()}
        status,body,_=request(self.app,'/api/tasks','POST',image_bytes(),extra=headers)
        self.assertEqual(status,422)
        self.assertEqual(json.loads(body)['error']['code'],'INVALID_IMAGE')
        self.assertIn('JPG',json.loads(body)['error']['message'])
        self.assertEqual(request(self.app,'/i18n.js')[0],200)
        self.assertEqual(request(self.app,'/i18n-en.js')[0],200)

    def submit(self,request_id,input_id='a'*32):
        metadata={'inputId':input_id,'requestId':request_id,'presetId':'sunny','name':'离线测试'}
        headers={'CONTENT_TYPE':'image/png','HTTP_X_LIGHTTRY_REQUEST':base64.b64encode(json.dumps(metadata).encode()).decode()}
        return request(self.app,'/api/tasks','POST',image_bytes(),extra=headers)

    def test_unauthenticated_every_surface_and_paid_routes_are_blocked(self):
        executor=ApprovedOfflineExecutor();self.app.handler.task_store.executor=executor
        photo=self.app.workspace.save_photo('a'*32,'私有照片',image_bytes(),'image/png')
        routes=['/','/index.html','/workbench.js','/i18n.js','/i18n-en.js','/api/catalog','/api/inference','/api/workspace',
                '/api/photos/'+'a'*32,'/api/tasks/'+'b'*32+'/download']
        for route in routes:
            self.assertEqual(request(self.app,route,user=None)[0],401)
        # Separate peer avoids sharing the failed-login lockout; auth still fails.
        for route in ('/api/tasks','/api/lighting/recommend','/api/gpu/start','/api/gpu/stop'):
            self.assertIn(request(self.app,route,'POST',b'{}',user=None,extra={'REMOTE_ADDR':'192.0.2.22'})[0],(401,429))
        self.assertEqual(executor.calls,[])
        with self.app.workspace.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM gpu_queue').fetchone()[0],0)

    def test_abandon_unaccepted_request_blocks_late_submit_without_paid_dispatch(self):
        self.app.handler.task_store.executor=ApprovedOfflineExecutor()
        rid='e'*32
        metadata={'inputId':'a'*32,'requestId':rid,'presetId':'sunny','name':'错标照片'}
        headers={'CONTENT_TYPE':'image/jpeg','HTTP_X_LIGHTTRY_REQUEST':base64.b64encode(json.dumps(metadata).encode()).decode()}
        status,body,_=request(self.app,'/api/tasks','POST',image_bytes(),extra=headers)
        self.assertEqual(status,422)
        self.assertEqual(json.loads(body)['error']['code'],'INVALID_IMAGE')
        path='/api/requests/'+rid+'/abandon'
        status,body,_=request(self.app,path,'POST')
        self.assertEqual(status,200)
        self.assertEqual(json.loads(body),{'requestId':rid,'abandoned':True})
        self.assertEqual(request(self.app,path,'POST')[0],200)  # Idempotent.
        status,body,_=self.submit(rid)
        self.assertEqual(status,409)
        self.assertEqual(json.loads(body)['error']['code'],'REQUEST_ABANDONED')
        with self.app.workspace.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM gpu_queue').fetchone()[0],0)

    def test_abandon_rejects_an_already_accepted_request(self):
        self.app.handler.task_store.executor=ApprovedOfflineExecutor()
        rid='f'*32
        status,body,_=self.submit(rid)
        self.assertEqual(status,202)
        identity=json.loads(body)['taskId']
        status,body,_=request(self.app,'/api/requests/'+rid+'/abandon','POST')
        self.assertEqual(status,409)
        self.assertEqual(json.loads(body)['error']['code'],'REQUEST_ALREADY_ACCEPTED')
        self.assertEqual(json.loads(request(self.app,'/api/requests/'+rid)[1])['taskId'],identity)

    def test_get_never_dispatches_and_both_roles_require_configured_gpu_control(self):
        executor=ApprovedOfflineExecutor();self.app.handler.task_store.executor=executor
        for route in ('/api/generate','/api/gpu/start','/api/gpu/stop','/api/tasks/start','/api/tasks/stop'):
            self.assertIn(request(self.app,route)[0],(404,405))
        for route in ('/api/gpu/start','/api/gpu/stop'):
            self.assertEqual(request(self.app,route,'POST',b'{}')[0],503)
            self.assertEqual(request(self.app,route,'POST',b'{}',user='operator',password=OTHER)[0],503)
        self.assertEqual(executor.calls,[])

    def test_foreign_photo_plan_task_request_and_download_are_not_visible(self):
        self.app.workspace.save_photo('a'*32,'私有图',image_bytes(),'image/png')
        scheme={'schemaVersion':1,'planId':'b'*32,'version':1,'parentVersion':None,'inputId':'a'*32,'name':'私有方案',
                'parameters':{'environmentId':'sunny','offsetDeg':0,'strength':1}}
        self.app.workspace.save_library({'schemaVersion':1,'schemes':[scheme]})
        executor=ApprovedOfflineExecutor();self.app.handler.task_store.executor=executor
        status,body,_=self.submit('d'*32);self.assertEqual(status,202);identity=json.loads(body)['taskId']
        for route in ('/api/photos/'+'a'*32,'/api/tasks/'+identity,'/api/tasks/'+identity+'/download','/api/requests/'+'d'*32):
            self.assertEqual(request(self.app,route,user='other',password=OTHER)[0],404)
        public=json.loads(request(self.app,'/api/workspace',user='other',password=OTHER)[1])
        self.assertEqual(public['photos'],[]);self.assertEqual(public['schemes'],[]);self.assertEqual(public['taskIds'],[])
        status=request(self.app,'/api/workspace','POST',json.dumps({'schemaVersion':1,'schemes':[scheme]}).encode(),user='other',password=OTHER)[0]
        self.assertEqual(status,404)

    def test_rate_limits_are_persistent_and_retry_after_is_present(self):
        self.app.limiter.limits['user']=3
        for _ in range(3):self.assertEqual(request(self.app,'/api/me')[0],200)
        status,_,headers=request(self.app,'/api/me');self.assertEqual(status,429);self.assertEqual(headers['Retry-After'],'60')
        self.app.close();self.app=Application(self.options);self.app.limiter.limits['user']=3
        self.assertEqual(request(self.app,'/api/me')[0],429)

    def test_upload_size_decode_path_and_hdr_ownership_guards(self):
        meta=base64.b64encode(json.dumps({'name':'原照片'}).encode()).decode()
        headers={'CONTENT_TYPE':'image/png','HTTP_X_LIGHTTRY_PHOTO':meta}
        self.assertEqual(request(self.app,'/api/photos/'+'a'*32,'POST',b'bad image',extra=headers)[0],422)
        self.assertEqual(request(self.app,'/api/photos/'+'a'*32,'POST',b'x',extra={**headers,'CONTENT_LENGTH':str(20*1024*1024+1)})[0],413)
        self.assertEqual(request(self.app,'/api/photos/'+'a'*32,'POST',image_bytes(),extra=headers)[0],201)
        for route in ('/api/photos/../../workspace.sqlite3','/api/tasks/%2e%2e%2fsecret','/photos/x','/auth/accounts.json'):
            self.assertEqual(request(self.app,route)[0],404)
        hdr=encode_hdr(np.ones((32,64,3),dtype=np.float32))
        status,body,_=request(self.app,'/api/environments/import','POST',hdr,extra={'CONTENT_TYPE':'application/octet-stream'})
        self.assertEqual(status,200);env=json.loads(body)
        self.assertEqual(request(self.app,env['thumbnail'],user='other',password=OTHER)[0],404)
        foreign=json.loads(request(self.app,'/api/environments',user='other',password=OTHER)[1])
        self.assertFalse(any(e['id']==env['id'] for e in foreign['environments']))
        if os.name!='nt':
            file=self.app.workspace.root/'photos'/self.app.workspace.photo('a'*32)[0]['originalSha']
            saved=file.read_bytes();file.unlink();outside=self.root/'outside';outside.write_bytes(saved);file.symlink_to(outside)
            self.assertEqual(request(self.app,'/api/photos/'+'a'*32)[0],409)

    def test_serial_fifo_idempotency_scope_revocation_and_get_readonly(self):
        executor=ApprovedOfflineExecutor();self.app.handler.task_store.executor=executor
        status,a,_=self.submit('d'*32);self.assertEqual(status,202);a=json.loads(a)
        status,again,_=self.submit('d'*32);self.assertEqual(json.loads(again)['taskId'],a['taskId'])
        status,b,_=self.submit('e'*32,'b'*32);self.assertEqual(status,202);b=json.loads(b)
        self.assertEqual(executor.calls,[])  # Admission is not a GPU dispatch.
        request(self.app,'/api/tasks/'+a['taskId']);self.assertEqual(executor.calls,[])
        self.app.queue.tick();self.assertEqual(len(executor.calls),1)
        self.app.queue.tick();self.assertEqual(len(executor.calls),1)
        executor.succeed();self.app.queue.tick();self.assertEqual(len(executor.calls),2)
        self.assertEqual(self.app.queue.get(a['taskId'],'lighttry')['status'],'succeeded')
        self.assertEqual(executor.calls[1][1]['taskId'],b['taskId'])
        print(json.dumps({'serialQueue':'PASS','dispatches':2,'getDispatches':0,'anonymousDispatches':0,'executor':'offline synthetic; no provider calls'}))

    def test_uncertain_dispatch_blocks_lane_and_is_not_retried(self):
        executor=ApprovedOfflineExecutor();self.app.handler.task_store.executor=executor
        status,raw,_=self.submit('d'*32);self.assertEqual(status,202);identity=json.loads(raw)['taskId']
        with self.app.workspace.connect() as db:db.execute("UPDATE gpu_queue SET state='dispatching' WHERE id=?",(identity,))
        self.app.queue.tick();self.app.queue.tick();self.assertEqual(executor.calls,[])
        self.assertTrue(self.app.queue.get(identity,'lighttry')['executionUncertain'])
        executor.approved=False
        self.assertEqual(self.submit('e'*32)[0],403)

    def test_runtime_credentials_and_login_password_never_appear_in_response_or_logs(self):
        secret='SYNTHETIC_PROVIDER_SECRET_'+'Z'*30
        with patch.dict(os.environ,{'NEMOTRON_API_KEY':secret,'NEBIUS_IAM_TOKEN':secret}):
            self.assertEqual(self.app.provider_secrets.get('nemotron'),secret)
            self.assertEqual(self.app.provider_secrets.get('nebius'),secret)
            for route in ('/api/me','/api/inference','/api/lighting','/api/workspace/export'):
                raw=request(self.app,route)[1].decode();self.assertNotIn(secret,raw);self.assertNotIn(PASS,raw)
        log=(self.app.workspace.root/'logs/service.log').read_text();self.assertNotIn(secret,log);self.assertNotIn(PASS,log);self.assertNotIn(AUTH('lighttry',PASS),log)
        with self.assertRaises(ValueError):self.app.provider_secrets.get('nemotron')
        result=create_temporary_account(self.root/'new-runtime',self.root/'private-login.txt',ROOT)
        self.assertEqual(result['role'],'user')
        self.assertNotIn('password',result)
        record=json.loads(Path(result['accountsFile']).read_text())['accounts']['lighttry']
        self.assertNotIn('password',record);self.assertTrue(record['expiresAt']>0)


if __name__=='__main__':unittest.main()
