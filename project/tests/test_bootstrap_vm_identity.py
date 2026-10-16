"""Execute actual composed remote program locally with VM-local effects stubbed."""
import contextlib,io,json,sys,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
ROOT=Path(__file__).resolve().parents[2]

def program(path=None):
 prelude=(ROOT/'cloud/remote_probe.py').read_text();prelude=prelude[:prelude.index('\nif __name__')]
 source=(path or ROOT/'project/gpu_bootstrap_vm.py').read_text();scope={'__name__':'offline_composed_vm'}
 exec(compile(prelude+'\n'+source,'composed-remote-stdin','exec'),scope)
 return scope

class VMIdentityTests(unittest.TestCase):
 def test_metadata_request_is_exact_private_bounded_no_iam_or_redirect(self):
  scope=program();response=Mock(status=200);response.read.return_value=b'computeinstance-fixture\n';conn=Mock();conn.getresponse.return_value=response
  with patch('http.client.HTTPConnection',return_value=conn) as connect:
   self.assertEqual(scope['metadata_vm_id'](time.time()+20),'computeinstance-fixture')
  connect.assert_called_once();self.assertEqual(connect.call_args.args[0],'metadata.nebius.internal');self.assertLessEqual(connect.call_args.kwargs['timeout'],2)
  conn.request.assert_called_once_with('GET','/v1/instance-data/id',headers={'Metadata':'true'});response.read.assert_called_once_with(129);conn.close.assert_called_once()
 def test_no_fallback_on_redirect_malformed_timeout_or_metadata_failure(self):
  for status,raw in [(302,b'computeinstance-fixture'),(403,b'denied'),(200,b'x'*129),(200,b'hostname-only'),(200,b'computeinstance-fixture extra')]:
   scope=program();conn=Mock();conn.getresponse.return_value=Mock(status=status,read=Mock(return_value=raw))
   with patch('http.client.HTTPConnection',return_value=conn):
    with self.assertRaisesRegex(ValueError,'METADATA_UNAVAILABLE'):scope['metadata_vm_id'](time.time()+10)
   conn.close.assert_called_once()
 def exercise(self,metadata):
  scope=program();scope['metadata_vm_id']=Mock(return_value=metadata);scope['docker']=Mock(side_effect=['a'*64,json.dumps([{'Id':'a'*64,'State':{'Running':True},'Config':{'Image':'fixture','User':'jovyan'},'Mounts':[{'Destination':'/home','RW':True}],'HostConfig':{'NetworkMode':'host'}}])])
  q=dict(hostIdentity={'sshUser':'nebius','vmId':'computeinstance-fixture'},deadline=time.time()+20,sessionId='b'*32,image='fixture',operation='prepare')
  with patch.dict(sys.modules,{'pwd':SimpleNamespace(getpwuid=lambda _:SimpleNamespace(pw_name='nebius'))}),patch('os.getuid',return_value=1000,create=True),patch('os.mkdir') as mkdir,contextlib.redirect_stdout(io.StringIO()) as output:
   try:scope['main'](q);return json.loads(output.getvalue()),mkdir.call_count,scope['docker'].call_count
   except ValueError as error:return str(error),mkdir.call_count,scope['docker'].call_count
 def test_current_vm_metadata_succeeds_independent_of_os_hostname(self):
  result,mkdir,docker=self.exercise('computeinstance-fixture');self.assertEqual(result['tlsBind'],'127.0.0.1');self.assertEqual(mkdir,1);self.assertEqual(docker,2)
 def test_wrong_vm_rejected_before_any_docker_or_files(self):
  result,mkdir,docker=self.exercise('computeinstance-other');self.assertEqual(result,'VM_METADATA_ID_MISMATCH');self.assertEqual((mkdir,docker),(0,0))

if __name__=='__main__':unittest.main()
