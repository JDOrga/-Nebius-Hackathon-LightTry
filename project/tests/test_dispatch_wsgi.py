"""Local diagnostic redaction and actual WSGI header boundary tests."""
import sys,json,tempfile,io,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from inference.jobs import dispatch_diagnostic,JobError
from https_executor import HTTPSCosmosExecutor
from service import wsgi_response_headers
import test_inference as jobs_fixture
import test_service_security as service_fixture

class DispatchDiagnosticTests(unittest.TestCase):
 def test_unknown_exception_never_leaks_credentials(self):
  e=RuntimeError('https://secret-host/?token=SECRET_PASSWORD Bearer SECRET_TOKEN')
  e.code={'token':'SECRET'};e.diagnostic={'raw':'SECRET'}
  d=dispatch_diagnostic(e,'a'*32,'SECRET_STAGE');self.assertNotIn('SECRET',json.dumps(d));self.assertEqual(d['code'],'UNCLASSIFIED_DISPATCH_FAILURE');self.assertEqual(d['stage'],'adapter_submit');self.assertFalse(d['retryPermitted'])
 def test_receipt_records_exact_task_and_reviewed_cause_once(self):
  f=jobs_fixture.JobTests();f.setUp();self.addCleanup(f.tearDown)
  error=JobError('SESSION_CHANGED','SECRET_MESSAGE',409);error.dispatch_stage='session_dispatch'
  f.executor.submit=Mock(side_effect=error)
  result=f.submit();tid=result['taskId'];folder=f.store.directory(tid)
  d=json.loads((folder/'dispatch-failure.json').read_text());self.assertEqual(d['taskId'],tid);self.assertEqual(d['stage'],'session_dispatch');self.assertEqual(d['code'],'SESSION_CHANGED');self.assertNotIn('SECRET',json.dumps(d));self.assertEqual(result['error']['code'],'DISPATCH_FAILED');self.assertTrue(result['executionUncertain'])
  f.submit();self.assertEqual(f.executor.submit.call_count,1)
 def test_sidecar_write_failure_does_not_mask_task_failure(self):
  f=jobs_fixture.JobTests();f.setUp();self.addCleanup(f.tearDown);f.executor.submit=Mock(side_effect=TimeoutError('SECRET'))
  from inference import jobs
  real=jobs.atomic
  def atomic(path,data):
   if Path(path).name=='dispatch-failure.json':raise OSError('SECRET_DISK')
   return real(path,data)
  with patch.object(jobs,'atomic',side_effect=atomic):result=f.submit()
  task=json.loads((f.store.directory(result['taskId'])/'task.json').read_text());self.assertEqual(task['dispatchDiagnostic']['category'],'timeout');self.assertEqual(result['status'],'failed');self.assertEqual(f.executor.submit.call_count,1)
 def adapter(self):
  temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);root=Path(temp.name)
  state={'sessionId':'a'*32,'resourceId':'RESOURCE','hostIdentity':'HOST'};worker=SimpleNamespace(health=Mock(return_value=state),upload=Mock(side_effect=TimeoutError('SECRET_TOKEN')))
  sessions=SimpleNamespace(worker=worker,submit=Mock());a=object.__new__(HTTPSCosmosExecutor);a.control=SimpleNamespace(sessions=sessions);a.current=Mock(return_value=(state,{'schemaVersion':1,'expiresAt':123}));return a,worker,sessions,root
 def test_upload_failure_has_stage_and_no_retry(self):
  a,w,s,root=self.adapter()
  with patch('https_executor.check_request'),patch('https_executor.model_ready',return_value=True),patch('https_executor.pack_input',return_value=b'fixture'),patch('https_executor.request_sha',return_value='b'*64):
   with self.assertRaises(TimeoutError) as exc:a.submit(root,{'taskId':'c'*32})
  d=dispatch_diagnostic(exc.exception,'c'*32);self.assertEqual(d['stage'],'artifact_upload');self.assertEqual(d['category'],'timeout');self.assertNotIn('SECRET',json.dumps(d));self.assertEqual(w.upload.call_count,1);s.submit.assert_not_called()
 def test_session_failure_retains_safe_error_code(self):
  import hashlib
  a,w,s,root=self.adapter();w.upload.side_effect=None;w.upload.return_value={'sha256':hashlib.sha256(b'fixture').hexdigest(),'bytes':7};s.submit.side_effect=JobError('SESSION_CHANGED','SECRET_MESSAGE',409)
  with patch('https_executor.check_request'),patch('https_executor.model_ready',return_value=True),patch('https_executor.pack_input',return_value=b'fixture'),patch('https_executor.request_sha',return_value='b'*64):
   with self.assertRaises(JobError) as exc:a.submit(root,{'taskId':'c'*32})
  d=dispatch_diagnostic(exc.exception,'c'*32);self.assertEqual((d['stage'],d['code']),('session_dispatch','SESSION_CHANGED'));self.assertEqual(s.submit.call_count,1)

class WSGIHeaderTests(unittest.TestCase):
 def test_all_hop_and_connection_nominated_headers_removed(self):
  headers=[('Connection','Keep-Alive, X-Private-Hop'),('cOnNeCtIoN','X-Second'),('X-Private-Hop','secret'),('x-second','secret'),('Keep-Alive','timeout=5'),('TE','trailers'),('Trailer','X-Foo'),('Transfer-Encoding','chunked'),('Upgrade','websocket'),('Proxy-Authenticate','secret'),('Proxy-Authorization','secret'),('Proxy-Connection','keep-alive'),('Content-Type','text/plain'),('Set-Cookie','one=1'),('Set-Cookie','two=2')]
  self.assertEqual(wsgi_response_headers(headers),headers[-3:])
 def test_actual_application_error_response_validates_as_wsgi(self):
  from wsgiref.validate import validator
  from wsgiref.util import setup_testing_defaults
  f=service_fixture.ServiceSecurityTests();f.setUp();self.addCleanup(f.tearDown)
  def page(h):
   h.send_response(404);h.send_header('Connection','close, X-Hop');h.send_header('X-Hop','DROP');h.send_header('Content-Type','text/plain');h.end_headers();h.wfile.write(b'not found')
  env={};setup_testing_defaults(env);env.update(REQUEST_METHOD='GET',PATH_INFO='/favicon.ico',QUERY_STRING='',CONTENT_LENGTH='0',**{'wsgi.input':io.BytesIO(b'')})
  env['HTTP_HOST']='localhost:8080';env['HTTP_ORIGIN']='http://localhost:8080'
  token,_=f.app.login_sessions.issue('lighttry');env['HTTP_COOKIE']='lighttry_session='+token;captured=[]
  with patch.object(f.app.handler,'do_GET',page):
   iterator=validator(f.app)(env,lambda status,headers:captured.append((status,headers)))
   try:body=b''.join(iterator)
   finally:iterator.close()
  self.assertEqual(captured[0][0],'404 Not Found');self.assertEqual(body,b'not found');self.assertNotIn('connection',{k.lower() for k,v in captured[0][1]});self.assertNotIn('x-hop',{k.lower() for k,v in captured[0][1]})
if __name__=='__main__':unittest.main()
