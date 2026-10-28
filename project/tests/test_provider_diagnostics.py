"""Offline only: no real adapter construction, WSL, or cloud access."""
from contextlib import closing
import sys,json,sqlite3,subprocess,tempfile,time,unittest
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from nebius_provider import NebiusProvider

class DiagnosticTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.a=object.__new__(NebiusProvider);self.a.root=Path(self.tmp.name);self.a.clock=lambda:100
  self.a._command=lambda args,j:['OFFLINE'];self.a.runner=Mock()
 def rows(self):
  with closing(sqlite3.connect(self.a.root/'provider-diagnostics.sqlite3')) as db:return [json.loads(x[0]) for x in db.execute('SELECT body FROM diagnostics')]
 def test_nonzero_retains_exit_stage_and_redacts(self):
  self.a.runner.return_value=subprocess.CompletedProcess([],2,'SECRET_STDOUT','permission denied Bearer SECRET_TOKEN '+('x'*9000))
  with self.assertRaises(RuntimeError) as e:self.a._call(['ai','devlab','restart','--id','SECRET_RESOURCE'])
  d=e.exception.diagnostic;self.assertEqual(d['exitCode'],2);self.assertEqual(d['stage'],'restart');self.assertEqual(d['stderrSummary'],['permission']);self.assertTrue(d['stderrTruncated']);self.assertTrue(d['persisted'])
  self.assertNotIn('rawStderr',d)
  rows=self.rows();self.assertEqual(rows[0]['rawStderr'],'permission denied Bearer SECRET_TOKEN '+('x'*9000))
  self.assertFalse(rows[0]['rawStderrTruncated']);self.assertNotIn('SECRET_STDOUT',json.dumps(rows));self.assertNotIn('SECRET_RESOURCE',json.dumps(rows));self.assertEqual(self.a.runner.call_count,1)
 def test_failed_mutation_raw_is_bounded_and_request_id_is_strict(self):
  stderr='rpc error: code = FailedPrecondition\nx-request-id: 123e4567-e89b-12d3-a456-426614174000\nBearer SECRET_TOKEN\n'+('x'*17000)
  self.a.runner.return_value=subprocess.CompletedProcess([],17,'',stderr)
  with self.assertRaisesRegex(RuntimeError,'NEBIUS_COMMAND_FAILED') as e:self.a._call(['ai','devlab','restart'])
  self.assertEqual(e.exception.diagnostic['failureClass'],'grpc_failedprecondition')
  self.assertEqual(e.exception.diagnostic['providerRequestId'],'123e4567-e89b-12d3-a456-426614174000')
  self.assertNotIn('rawStderr',e.exception.diagnostic)
  row=self.rows()[0];self.assertEqual(row['rawStderr'],stderr[:16384]);self.assertTrue(row['rawStderrTruncated'])
  self.a.runner.return_value=subprocess.CompletedProcess([],17,'','request-id: SECRET_TOKEN\nBearer SECRET_TOKEN')
  with self.assertRaisesRegex(RuntimeError,'NEBIUS_COMMAND_FAILED') as e:self.a._call(['ai','devlab','get'])
  self.assertNotIn('providerRequestId',e.exception.diagnostic);self.assertNotIn('rawStderr',self.rows()[-1])
 def test_auth_timeout_json_deadline(self):
  self.a.runner.return_value=subprocess.CompletedProcess([],7,'','invalid token SECRET')
  with self.assertRaisesRegex(RuntimeError,'NEBIUS_AUTH_REQUIRED'):self.a._call(['ai','devlab','get'])
  self.a.runner.side_effect=subprocess.TimeoutExpired(['SECRET'],6,stderr=b'SECRET')
  with self.assertRaisesRegex(RuntimeError,'NEBIUS_TIMEOUT'):self.a._call(['ai','devlab','get'])
  self.a.runner.side_effect=None;self.a.runner.return_value=subprocess.CompletedProcess([],0,'bad json SECRET','')
  with self.assertRaisesRegex(RuntimeError,'NEBIUS_INVALID_JSON'):self.a._call(['ai','devlab','get'])
  with self.assertRaisesRegex(RuntimeError,'NEBIUS_DEADLINE_EXPIRED'):self.a._call(['ai','devlab','get'],deadline=99)
  self.assertEqual(self.a.runner.call_count,3);self.assertEqual(len(self.rows()),4)
 def test_closed_failure_classes_do_not_persist_stderr(self):
  cases=(('rpc error: code = Unavailable desc = Bearer SECRET_TOKEN','grpc_unavailable'),
         ('grpc-status: 14 SECRET_TOKEN','grpc_unavailable'),
         ('HTTP 503 SECRET_TOKEN','http_503'),
         ('x509: certificate verify failed SECRET_TOKEN','tls_certificate'),
         ('no such host SECRET_TOKEN','dns'),
         ('internal server error SECRET_TOKEN','server'),
         ('opaque SECRET_TOKEN','unclassified'))
  for stderr,expected in cases:
   self.a.runner.return_value=subprocess.CompletedProcess([],20,'',stderr)
   with self.assertRaisesRegex(RuntimeError,'NEBIUS_COMMAND_FAILED') as raised:
    self.a._call(['iam','v2','project','get'])
   self.assertEqual(raised.exception.diagnostic['failureClass'],expected)
  persisted=json.dumps(self.rows())
  self.assertNotIn('SECRET',persisted)
  self.assertNotIn('Bearer',persisted)
  self.assertEqual(self.a.runner.call_count,len(cases))
 def test_success_and_retention(self):
  self.a.runner.return_value=subprocess.CompletedProcess([],0,'{}','')
  for _ in range(260):self.assertEqual(self.a._call(['ai','devlab','get']),{})
  self.assertEqual(len(self.rows()),256)
 def test_diagnostic_failure_preserves_outcome(self):
  (self.a.root/'provider-diagnostics.sqlite3').mkdir()
  self.a.runner.return_value=subprocess.CompletedProcess([],2,'','SECRET')
  with self.assertRaises(RuntimeError) as e:self.a._call(['ai','devlab','restart'])
  self.assertEqual(str(e.exception),'NEBIUS_COMMAND_FAILED');self.assertFalse(e.exception.diagnostic['persisted']);self.assertEqual(self.a.runner.call_count,1)
 def test_instance_binding_failure_retains_only_states_without_extra_queries(self):
  self.a._read=Mock(return_value=({}, {}, {'state':'RUNNING','image':'image','instances':[
   {'state':'IMAGE_PULLING','compute_instance_state':'RUNNING','public_ip':'SECRET_IP','compute_instance_id':'SECRET_VM'},
   {'state':'SECRET_UNKNOWN','compute_instance_state':'SECRET_UNKNOWN'}]}))
  self.a._read.return_value[1]['status']={'instances':[]}
  with self.assertRaisesRegex(ValueError,'NEBIUS_CURRENT_VM_NOT_UNIQUE'):self.a.observe('fixture')
  d=self.rows()[0];self.assertEqual(d['activeCount'],0);self.assertEqual(d['instanceCount'],2)
  self.assertEqual(d['instances'][0],{'state':'IMAGE_PULLING','computeState':'RUNNING'})
  self.assertNotIn('SECRET',json.dumps(d));self.a.runner.assert_not_called();self.a._read.assert_called_once()
 def test_start_failure_persists_without_repeat(self):
  from test_worker_guard import GuardTests
  f=GuardTests();f.setUp();self.addCleanup(f.tearDown)
  error=RuntimeError('NEBIUS_COMMAND_FAILED');error.diagnostic={'stage':'restart','exitCode':2,'durationMs':12,'raw':'SECRET'}
  f.provider.start=Mock(side_effect=error)
  v=f.sessions.start(f.scope);self.assertEqual(v['error'],'START_OR_PREFLIGHT_UNCERTAIN');self.assertEqual(v['startFailure'],{'stage':'provider_start','code':'NEBIUS_COMMAND_FAILED','providerStage':'restart','exitCode':2,'durationMs':12})
  f.sessions.start(f.scope);self.assertEqual(f.provider.start.call_count,1);self.assertNotIn('SECRET',json.dumps(v))
if __name__=='__main__':unittest.main()
