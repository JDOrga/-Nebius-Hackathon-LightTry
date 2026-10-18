"""Synthetic local key-login integration: no cloud or real credentials."""
import base64
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import threading
import unittest
from urllib.parse import urlencode
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'project'))
from security import password_record, LoginSessions
from service import Application,parser
KEY='SYNTHETIC_LOGIN_KEY_'+'A'*32
OTHER='SYNTHETIC_LOGIN_KEY_'+'B'*32
class KeyLoginTests(unittest.TestCase):
 def setUp(self):
  self.oldtmp=tempfile.tempdir;self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
  f=self.root/'accounts.json';f.write_text(json.dumps({'schemaVersion':1,'accounts':{'lighttry':password_record(KEY),'other':password_record(OTHER)}}));f.chmod(0o600)
  self.env=patch.dict(os.environ,{'LIGHTTRY_LEGACY_OWNER':'lighttry'});self.env.start()
  self.app=Application(parser().parse_args(['--data-root',str(self.root/'state'),'--accounts-file',str(f)]))
 def tearDown(self):
  self.app.close();tempfile.tempdir=self.oldtmp;self.env.stop();self.tmp.cleanup()
 def req(self,path,method='GET',body=b'',cookie='',origin='http://localhost:8080',extra=None):
  env={'REQUEST_METHOD':method,'PATH_INFO':path,'wsgi.input':io.BytesIO(body),'CONTENT_LENGTH':str(len(body)),'CONTENT_TYPE':'application/x-www-form-urlencoded','HTTP_HOST':'localhost:8080','REMOTE_ADDR':'127.0.0.1','HTTP_ORIGIN':origin,'HTTP_COOKIE':cookie};env.update(extra or {});got=[]
  out=b''.join(self.app(env,lambda status,headers:got.append((int(status.split()[0]),dict(headers)))))
  return got[0][0],got[0][1],out
 def login(self,key=KEY):
  status,headers,body=self.req('/auth/login','POST',urlencode({'accessKey':key}).encode());self.assertEqual(status,303)
  return headers['Set-Cookie'].split(';')[0],headers
 def test_page_and_no_basic_auth(self):
  status,h,b=self.req('/login');self.assertEqual(status,200);self.assertEqual(h['Referrer-Policy'],'same-origin');self.assertIn(b'name="accessKey"',b);self.assertNotIn(b'name="username"',b);self.assertNotIn(b'WWW-Authenticate',str(h).encode())
  basic='Basic '+base64.b64encode(('lighttry:'+KEY).encode()).decode()
  self.assertEqual(self.req('/api/me',extra={'HTTP_AUTHORIZATION':basic})[0],401)
  self.assertEqual(self.req('/api/catalog')[0],401);self.assertEqual(self.req('/workbench.js')[0],401)
 def test_login_cookie_identity_and_private_routes(self):
  cookie,h=self.login();self.assertIn('HttpOnly',h['Set-Cookie']);self.assertIn('SameSite=Strict',h['Set-Cookie']);self.assertIn('Max-Age=',h['Set-Cookie']);self.assertNotIn(KEY,h['Set-Cookie'])
  self.assertEqual(json.loads(self.req('/api/me',cookie=cookie)[2])['username'],'lighttry')
  self.assertEqual(self.req('/',cookie=cookie)[0],200)
  self.assertEqual(self.req('/api/photos/'+'a'*32,cookie=cookie)[0],404)
  self.assertIn('Secure',self.app.session_cookie('x',60).replace('SameSite=Strict','') if self.app.origin.startswith('https') else self._secure_cookie())
 def _secure_cookie(self):
  self.app.origin='https://example.test';value=self.app.session_cookie('x',60);self.app.origin='http://localhost:8080';return value
 def test_wrong_expired_and_ambiguous_keys(self):
  self.assertEqual(self.req('/auth/login','POST',urlencode({'accessKey':'SYNTHETIC_WRONG_'+'Z'*32}).encode())[0],401)
  self.app.accounts.users['lighttry']['expiresAt']=time.time()-1
  self.assertIsNone(self.app.accounts.authenticate_key(KEY));self.app.accounts.users['lighttry']['expiresAt']=None
  self.app.accounts.users['other']=password_record(KEY)
  self.assertIsNone(self.app.accounts.authenticate_key(KEY))
 def test_cross_origin_and_bad_body(self):
  body=urlencode({'accessKey':KEY}).encode()
  self.assertEqual(self.req('/auth/login','POST',body,origin='https://evil.test')[0],403)
  self.assertEqual(self.req('/auth/login','POST',body,origin='')[0],403)
  self.assertEqual(self.req('/auth/login','POST',b'accessKey=x&accessKey=y')[0],400)
  self.assertEqual(self.req('/auth/login','POST',body,extra={'CONTENT_LENGTH':'4097'})[0],413)
 def test_logout_requires_csrf_and_revokes(self):
  cookie,_=self.login();self.assertEqual(self.req('/auth/logout','POST',cookie=cookie)[0],403)
  status,h,b=self.req('/auth/logout','POST',cookie=cookie,extra={'HTTP_X_LIGHTTRY_TOKEN':self.app.handler.csrf_token});self.assertEqual(status,200);self.assertIn('Max-Age=0',h['Set-Cookie'])
  self.assertEqual(self.req('/api/me',cookie=cookie)[0],401)
 def test_session_expiry_and_key_revocation(self):
  now=[100.];sessions=LoginSessions(self.app.accounts,clock=lambda:now[0]);token,_=sessions.issue('lighttry');self.assertEqual(sessions.authenticate(token),'lighttry');now[0]+=8*3600;self.assertIsNone(sessions.authenticate(token))
  token,_=sessions.issue('lighttry');self.app.accounts.users['lighttry']['hash']='0'*64;self.assertIsNone(sessions.authenticate(token))
 def test_login_rate_limit_and_no_secret_leak(self):
  cookie,_=self.login()
  for i in range(11):last=self.req('/auth/login','POST',b'accessKey=invalid')
  self.assertEqual(last[0],429);self.assertEqual(last[1]['Retry-After'],'60')
  self.assertEqual(self.req('/api/me',cookie=cookie)[0],200)
  text=(self.root/'state/logs/service.log').read_text();self.assertNotIn(KEY,text);self.assertNotIn('accessKey=',text)
 def test_stale_session_reads_do_not_exhaust_actual_login_attempts(self):
  for _ in range(15):self.assertEqual(self.req('/api/lighting')[0],401)
  self.assertEqual(self.req('/auth/login','POST',urlencode({'accessKey':KEY}).encode())[0],303)
 def gpu_fixture(self,state='STOPPED',age=0):
  class FakeGPU:
   def __init__(self):self.calls=0;self.entered=threading.Event();self.release=threading.Event()
   def latest(inner):return {'state':state,'lastObservedAt':time.time()-age,'verifiedStopped':state=='STOPPED','simulation':True}
   def start(inner,scope):
    inner.calls+=1;inner.entered.set();inner.release.wait(2);return {'state':'STARTING'}
  gpu=FakeGPU();self.app.gpu_sessions=gpu;self.app.gpu_scope={'scopeId':'a'*32,'resourceId':'fixture','expiresAt':time.time()+60,'budgetApproved':True,'idleSeconds':60,'simulation':True};return gpu
 def operator_cookie(self):
  self.app.accounts.users['lighttry']['role']='operator';return self.login()[0]
 def test_gpu_active_skips_interstitial_without_start(self):
  gpu=self.gpu_fixture('READY');cookie,h=self.login();self.assertEqual(h['Location'],'/');self.assertEqual(gpu.calls,0)
  self.assertEqual(self.req('/gpu-entry',cookie=cookie)[0],303)
 def test_gpu_stopped_shows_choice_and_skip_is_readonly(self):
  gpu=self.gpu_fixture();cookie,h=self.login();self.assertEqual(h['Location'],'/gpu-entry');status,_,body=self.req('/gpu-entry',cookie=cookie);self.assertEqual(status,200);self.assertIn('暂不启动，直接进入'.encode(),body);self.assertIn(b'disabled',body)
  self.assertEqual(self.req('/',cookie=cookie)[0],200);self.assertEqual(gpu.calls,0)
 def test_gpu_unknown_and_stale_are_not_called_stopped(self):
  cookie,h=self.login();self.assertEqual(h['Location'],'/gpu-entry');self.assertIn('暂时无法确认'.encode(),self.req('/gpu-entry',cookie=cookie)[2])
  gpu=self.gpu_fixture('READY',age=120);self.assertEqual(self.app.gpu_login_destination(),'/gpu-entry');self.assertFalse(self.app.gpu_entry_info('lighttry')['canStart']);self.assertEqual(gpu.calls,0)
 def test_gpu_start_is_background_and_once_per_scope(self):
  gpu=self.gpu_fixture();cookie=self.operator_cookie();headers={'CONTENT_TYPE':'application/json','HTTP_X_LIGHTTRY_TOKEN':self.app.handler.csrf_token};body=json.dumps({'requestId':'b'*32}).encode()
  try:
   status,_,out=self.req('/api/gpu/entry-start','POST',body,cookie=cookie,extra=headers);self.assertEqual(status,202);self.assertTrue(gpu.entered.wait(1));self.assertFalse(gpu.release.is_set());self.assertEqual(self.req('/',cookie=cookie)[0],200)
   self.assertEqual(self.req('/api/gpu/entry-start','POST',body,cookie=cookie,extra=headers)[0],202);self.assertEqual(gpu.calls,1)
  finally:gpu.release.set();self.app.entry_thread.join(2)
 def test_gpu_start_requires_auth_csrf_and_valid_scope_for_both_roles(self):
  gpu=self.gpu_fixture();body=json.dumps({'requestId':'c'*32}).encode();headers={'CONTENT_TYPE':'application/json','HTTP_X_LIGHTTRY_TOKEN':self.app.handler.csrf_token};cookie,_=self.login()
  self.assertEqual(self.req('/api/gpu/entry-start','POST',body,extra=headers)[0],401)
  self.assertEqual(self.req('/api/gpu/entry-start','POST',body,cookie=cookie,extra=headers)[0],202)
  gpu.release.set();self.app.entry_thread.join(2);self.app.entry_start=None;gpu.calls=0
  cookie=self.operator_cookie();self.assertEqual(self.req('/api/gpu/entry-start','POST',body,cookie=cookie,extra={'CONTENT_TYPE':'application/json'})[0],403)
  self.app.gpu_scope['expiresAt']=time.time()-1;self.assertEqual(self.req('/api/gpu/entry-start','POST',body,cookie=cookie,extra=headers)[0],409);self.assertEqual(gpu.calls,0)
 def test_gpu_entry_get_does_not_start_and_failure_is_not_retried(self):
  gpu=self.gpu_fixture();cookie=self.operator_cookie();self.assertIn(self.req('/api/gpu/entry-start',cookie=cookie)[0],(404,405));self.assertEqual(gpu.calls,0)
  def fail(scope):gpu.calls+=1;raise RuntimeError('synthetic failure')
  gpu.start=fail;body=json.dumps({'requestId':'d'*32}).encode();headers={'CONTENT_TYPE':'application/json','HTTP_X_LIGHTTRY_TOKEN':self.app.handler.csrf_token}
  self.assertEqual(self.req('/api/gpu/entry-start','POST',body,cookie=cookie,extra=headers)[0],202);self.app.entry_thread.join(2)
  self.assertEqual(self.req('/api/gpu/entry-start','POST',body,cookie=cookie,extra=headers)[0],202);self.assertEqual(gpu.calls,1);self.assertEqual(self.app.gpu_entry_info('lighttry')['startStatus'],'failed')
 def test_monitor_snapshot_metadata_and_start_latch(self):
  gpu=self.gpu_fixture();cookie=self.operator_cookie();status,_,body=self.req('/api/gpu/entry-status',cookie=cookie);info=json.loads(body);self.assertEqual(status,200);self.assertTrue(info['configured']);self.assertFalse(info['stale']);self.assertTrue(info['canStart']);self.assertGreater(info['observedAt'],0);self.assertEqual(gpu.calls,0)
  self.app.entry_start={'scopeId':self.app.gpu_scope['scopeId'],'status':'requested'};self.assertFalse(self.app.gpu_entry_info('lighttry')['canStart'])
  self.app.entry_start={'scopeId':'e'*32,'status':'failed'};info=self.app.gpu_entry_info('lighttry');self.assertIsNone(info['startStatus']);self.assertTrue(info['canStart'])
if __name__=='__main__':unittest.main(verbosity=2)
