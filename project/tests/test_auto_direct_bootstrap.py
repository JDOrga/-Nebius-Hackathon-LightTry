import unittest,sys,tempfile,json,time,ast,subprocess,shutil
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from direct_bootstrap import DirectBootstrap

class AutoDirectTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.sid='a'*32;self.directory=self.root/self.sid;self.directory.mkdir();self.direct=self.root/'direct.json';self.direct.write_text('{"schemaVersion":1,"enabled":false}')
  self.exe=shutil.which('openssl') or 'C:/Program Files/Git/usr/bin/openssl.exe'
  if not Path(self.exe).is_file():self.skipTest('OpenSSL unavailable')
  self.control=SimpleNamespace(sessions=SimpleNamespace(worker=SimpleNamespace(direct_file=self.direct)))
  self.helper=DirectBootstrap(self.control,{'enabled':True,'opensslExecutable':self.exe});self.state={'sessionId':self.sid,'resourceId':'FIXTURE','hostIdentity':{'vmId':'VM_FIXTURE','ip':'203.0.113.7','sshUser':'nebius'},'hostConfirmed':True,'stopSent':False};self.control.sessions.change=lambda sid,event,fn,**kwargs:fn(self.state);self.deadline=time.time()+1000
  token=self.root/'token';token.write_text('x'*48);cert=self.root/'worker.crt';cert.write_text('PUBLIC_CERT_FIXTURE')
  self.bootstrap=SimpleNamespace(check=lambda sid,confirmed:self.state,directory=lambda sid:self.directory,clock=time.time,settings={'workerCertificateFile':str(cert),'workerTokenFile':str(token),'sshExecutable':'SSH_FIXTURE'},ssh_args=lambda sid:['STRICT_CURRENT_PIN'])
  self.bootstrap.attempt=lambda sid,name:(self.directory/(name+'-attempt')).open('x').close()
  self.bootstrap.write=lambda path,value:Path(path).write_text(json.dumps(value))
  self.remote_calls=0
  def remote(sid,args,input):
   self.remote_calls+=1;self.assertEqual(args[-1],'python3 -B -');tree=ast.parse(input.decode());q=ast.literal_eval(next(n.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='q' for t in n.targets)))
   self.assertEqual(set(q['files']),{'server.crt','server.key','cpu-ca.crt','worker-ca.crt'});self.assertEqual(q['archiveSha'],'b'*64)
   return json.dumps({'sessionId':sid,'relayExitedEarly':None,'deadline':self.deadline}).encode()
  self.bootstrap.run=remote;self.client=Mock();self.client.health.return_value={k:self.state[k] for k in ['sessionId','resourceId','hostIdentity']};self.helper.factory=lambda *a,**k:self.client
 def deploy(self):return self.helper.deploy(self.bootstrap,self.sid,{'sha256':'b'*64},{'tlsBind':'172.18.0.3','tlsPort':9443},self.deadline)
 def test_constructor_has_no_process_or_cloud_actions(self):
  with patch('subprocess.run',side_effect=AssertionError()),patch('subprocess.Popen',side_effect=AssertionError()):DirectBootstrap(self.control,{'enabled':True,'opensslExecutable':self.exe})
 def test_approved_deploy_publishes_only_after_live_bound_health_once(self):
  self.deploy();v=json.loads(self.direct.read_text());self.assertTrue(v['enabled']);self.assertEqual(v['sessionId'],self.sid);self.assertEqual(self.remote_calls,1)
  with self.assertRaises(FileExistsError):self.deploy()
  self.assertEqual(self.remote_calls,1);self.helper.revoke(self.sid);self.assertEqual(json.loads(self.direct.read_text()),{'schemaVersion':1,'enabled':False})
 def test_wrong_health_never_publishes_or_renews(self):
  self.client.health.return_value={**self.client.health.return_value,'sessionId':'c'*32}
  with self.assertRaisesRegex(ValueError,'DIRECT_HEALTH_BINDING_MISMATCH'):self.deploy()
  self.assertFalse(json.loads(self.direct.read_text())['enabled']);self.assertEqual(self.remote_calls,1)
 def test_stop_race_never_publishes(self):
  def stopped(sid,event,fn,**kwargs):self.state['stopSent']=True;return fn(self.state)
  self.control.sessions.change=stopped
  with self.assertRaisesRegex(ValueError,'DIRECT_SESSION_CHANGED_BEFORE_PUBLISH'):self.deploy()
  self.assertFalse(json.loads(self.direct.read_text())['enabled'])
 def test_failed_remote_never_publishes_and_not_retried(self):
  self.bootstrap.run=Mock(side_effect=OSError('UNCERTAIN'))
  with self.assertRaises(OSError):self.deploy()
  self.assertFalse(json.loads(self.direct.read_text())['enabled'])
  with self.assertRaises(FileExistsError):self.deploy()
  self.bootstrap.run.assert_called_once()
if __name__=='__main__':unittest.main()
