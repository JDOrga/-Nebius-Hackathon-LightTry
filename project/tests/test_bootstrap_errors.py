import errno
import json
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parent))
import test_gpu_bootstrap_link as fixtures
from bootstrap_errors import classify,public_error,stderr_code
from gpu_monitoring import public_failure


class ClassificationTests(unittest.TestCase):
 def test_exception_classes_and_secret_redaction(self):
  secret='PRIVATE_TOKEN_AUTH_URL_KEY_PATH'
  errors=[(subprocess.TimeoutExpired([secret],20,output=secret.encode(),stderr=secret.encode()),'SSH_COMMAND_TIMEOUT'),
   (json.JSONDecodeError(secret,secret,0),'REMOTE_JSON_INVALID'),(FileNotFoundError(secret),'LOCAL_FILE_NOT_FOUND'),
   (PermissionError(secret),'LOCAL_PERMISSION_DENIED'),(OSError(errno.EADDRINUSE,secret),'LOCAL_PORT_BUSY'),
   (KeyError(secret),'LOCAL_PROGRAM_ERROR'),(ValueError('FROZEN_BOOTSTRAP_CODE_CHANGED'),'FROZEN_MATERIAL_CHANGED'),
   (ValueError(secret),'SESSION_OR_BINDING_REJECTED'),(RuntimeError(secret),'BOOTSTRAP_UNCLASSIFIED')]
  for error,code in errors:
   info=classify(error,'prepare');self.assertEqual(info['code'],code);self.assertNotIn(secret,json.dumps(info));self.assertFalse(info['retryAllowed'])
 def test_local_json_is_not_misreported_as_remote(self):
  self.assertEqual(classify(json.JSONDecodeError('x','x',0),'preflight')['code'],'LOCAL_JSON_INVALID')
 def test_bounded_stderr_patterns_only_expose_codes(self):
  for text,code in [(b'Permission denied (publickey).','SSH_AUTH_FAILED'),(b'Host key verification failed.','SSH_HOST_KEY_REJECTED'),
    (b'connect: Connection timed out','SSH_NETWORK_UNAVAILABLE'),(b'Connection reset by peer','SSH_CONNECTION_CLOSED'),
    (b'PRIVATE_TOKEN','REMOTE_COMMAND_FAILED')]:self.assertEqual(stderr_code(text),code)
 def test_public_schema_drops_arbitrary_fields_and_unknown_codes(self):
  self.assertIsNone(public_error({'code':'SECRET'}))
  info=public_error({'code':'SSH_COMMAND_TIMEOUT','stage':'SECRET','stderr':'PRIVATE_TOKEN','exceptionType':'PRIVATE_TOKEN'})
  self.assertEqual(info['stage'],'unknown');self.assertNotIn('PRIVATE_TOKEN',json.dumps(info))
 def test_ui_stage_reason_and_cost(self):
  info=classify(subprocess.TimeoutExpired('SECRET',20),'prepare')
  result=public_failure({'state':'LOADING'},{'stage':'uncertain','failure':info},True)
  self.assertEqual(result['stage'],'prepare');self.assertIn('SSH远程准备',result['title']);self.assertIn('超',result['detail']);self.assertIn('计费',result['cost'])
  old=public_failure({'state':'LOADING'},{'stage':'uncertain','error':'BOOTSTRAP_UNCERTAIN'},True)
  self.assertIn('不能追溯',old['detail'])


class PipelineDiagnosticsTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):fixtures.BootstrapTests.setUpClass()
 @classmethod
 def tearDownClass(cls):fixtures.BootstrapTests.tearDownClass()
 def setUp(self):
  self.f=fixtures.BootstrapTests();self.f.setUp();self.addCleanup(self.f.tearDown)
 def test_prepare_timeout_persists_stage_type_and_never_retries(self):
  f=self.f;f.confirmed();f.bootstrap.runner=Mock(side_effect=subprocess.TimeoutExpired(['SECRET_KEY_PATH'],20,stderr=b'SECRET_TOKEN'))
  f.bootstrap.step(f.value);f.bootstrap.thread.join(3)
  folder=f.bootstrap.directory(f.sid);info=json.loads((folder/'failure-info.json').read_text())
  self.assertEqual((info['code'],info['stage'],info['exceptionType']),('SSH_COMMAND_TIMEOUT','prepare','TimeoutExpired'))
  self.assertTrue((folder/'prepare-attempt').exists());self.assertFalse((folder/'upload-attempt').exists())
  for name in ['failure-info.json','failed.json','status.json']:self.assertNotIn('SECRET_', (folder/name).read_text())
  public=f.bootstrap.public(f.value);self.assertEqual(public['failure']['stage'],'prepare')
  f.bootstrap.step(f.value);f.bootstrap.runner.assert_called_once();f.bootstrap.spawn.assert_not_called()
 def test_invalid_remote_json_after_success_exit_is_classified(self):
  f=self.f;f.confirmed();f.bootstrap.runner=Mock(return_value=SimpleNamespace(returncode=0,stdout=b'not JSON SECRET_TOKEN',stderr=b''))
  f.bootstrap.step(f.value);f.bootstrap.thread.join(3);info=json.loads((f.bootstrap.directory(f.sid)/'failure-info.json').read_text())
  self.assertEqual((info['code'],info['stage']),('REMOTE_JSON_INVALID','prepare'));self.assertNotIn('SECRET',json.dumps(info))
 def test_nonzero_auth_error_keeps_exit_code_without_raw_output(self):
  f=self.f;f.confirmed();f.bootstrap.runner=Mock(return_value=SimpleNamespace(returncode=255,stdout=b'',stderr=b'Permission denied (publickey). SECRET_TOKEN'))
  f.bootstrap.step(f.value);f.bootstrap.thread.join(3);info=json.loads((f.bootstrap.directory(f.sid)/'failure-info.json').read_text())
  self.assertEqual((info['code'],info['stage'],info['exitCode']),('SSH_AUTH_FAILED','prepare',255));self.assertNotIn('SECRET',json.dumps(info))

if __name__=='__main__':unittest.main()
