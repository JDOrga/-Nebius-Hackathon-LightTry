import unittest,sys,json,tempfile,time
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from worker_transport import DualHTTPSWorker
from worker_link import LinkUncertain
from gpu_direct_https import render

class DirectTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
  self.file=self.root/'direct.json';token=self.root/'token';token.write_text('x'*48)
  self.value={'sessionId':'a'*32,'resourceId':'FIXTURE','hostIdentity':{'vmId':'VM_FIXTURE','ip':'203.0.113.9'},'hostConfirmed':True,'workDeadline':200,'absoluteDeadline':300}
  self.cfg={'schemaVersion':1,'enabled':True,**{k:self.value[k] for k in ['sessionId','resourceId','hostIdentity']},'origin':'https://203.0.113.9:443','tokenFile':str(token),'caFile':'CA_FIXTURE','certificateSha256':'b'*64,'clientCertificateFile':'CLIENT_CERT_FIXTURE','clientKeyFile':'CLIENT_KEY_FIXTURE'};self.write()
  self.health={k:self.value[k] for k in ['sessionId','resourceId','hostIdentity']};self.health.update(modelLoaded=True,modelState='ready',executionMode='resident',simulation=False)
  self.ssh=Mock(simulation=True);self.direct=Mock();self.ssh.health.return_value=self.health;self.direct.health.return_value=self.health
  self.worker=DualHTTPSWorker(self.ssh,self.file,clock=lambda:100,factory=lambda *a,**k:self.direct);self.worker.state=lambda:self.value
 def write(self):self.file.write_text(json.dumps(self.cfg))
 def test_cpu_factory_optional_route_is_offline(self):
  import types
  from unittest.mock import patch
  from cpu_supervisor import build_sessions
  module=types.ModuleType('direct_fixture_provider');module.build=lambda binding:types.SimpleNamespace(preflight=lambda *a:None,observe=lambda *a:None,start=lambda *a:None,stop=lambda *a:None)
  token=self.root/'factory-token';token.write_text('z'*48)
  self.file.write_text('{"schemaVersion":1,"enabled":false}')
  binding={'providerFactory':'direct_fixture_provider:build','providerBinding':{},'workerOrigin':'https://localhost:9443','workerTokenFile':str(token),'workerCaFile':None,'directWorkerFile':str(self.file)}
  with patch.dict(sys.modules,{'direct_fixture_provider':module}),patch('subprocess.run',side_effect=AssertionError('NO_CLOUD')),patch('subprocess.Popen',side_effect=AssertionError('NO_PROCESS')):
   result=build_sessions(self.root/'guard',binding)
   self.assertIsInstance(result.worker,DualHTTPSWorker);self.assertFalse(result.worker.direct_available)
 def test_direct_survives_dead_ssh(self):
  self.ssh.health.side_effect=LinkUncertain();self.assertEqual(self.worker.health(),self.health);self.assertEqual(self.worker.active_transport,'direct_https');self.ssh.health.assert_not_called()
 def test_read_health_can_fall_back_to_ssh(self):
  self.direct.health.side_effect=LinkUncertain();self.worker.health();self.assertEqual(self.worker.active_transport,'ssh_https')
 def test_failed_post_never_replayed(self):
  self.worker.health();self.direct.submit.side_effect=LinkUncertain()
  with self.assertRaises(LinkUncertain):self.worker.submit({'jobId':'c'*32})
  self.direct.submit.assert_called_once();self.ssh.submit.assert_not_called()
  self.direct.health.side_effect=LinkUncertain();self.worker.health();self.worker.query('c'*32);self.ssh.query.assert_called_once_with('c'*32);self.ssh.submit.assert_not_called()
 def test_missing_mtls_identity_cannot_enable_direct(self):
  self.cfg['clientCertificateFile']=None;self.cfg['clientKeyFile']=None;self.write()
  with self.assertRaisesRegex(ValueError,'DIRECT_MTLS_CLIENT_IDENTITY_REQUIRED'):self.worker.health()
  self.ssh.health.assert_not_called()
 def test_wrong_health_identity_not_fallback(self):
  self.direct.health.return_value={**self.health,'sessionId':'d'*32}
  with self.assertRaisesRegex(ValueError,'WORKER_SESSION_MISMATCH'):self.worker.health()
  self.ssh.health.assert_not_called()
 def test_old_scope_or_other_ip_rejected(self):
  self.cfg['sessionId']='d'*32;self.write()
  with self.assertRaises(ValueError):self.worker.health()
  self.cfg['sessionId']='a'*32;self.cfg['origin']='https://203.0.113.10';self.write()
  with self.assertRaises(ValueError):self.worker.health()
 def test_revocation_and_stop_clear_route(self):
  self.worker.health();self.file.write_text('{"schemaVersion":1,"enabled":false}');self.worker.query('c'*32);self.ssh.query.assert_called_once()
  self.value['stopSent']=True
  with self.assertRaises(LinkUncertain):self.worker.upload(b'bytes')
  self.direct.upload.assert_not_called();self.ssh.upload.assert_not_called()
 def test_no_session_no_health_or_mutation(self):
  self.value['hostConfirmed']=False
  with self.assertRaises(LinkUncertain):self.worker.health()
  self.direct.health.assert_not_called();self.ssh.health.assert_not_called()
 def test_expired_no_renewal(self):
  self.value['workDeadline']=99
  with self.assertRaises(LinkUncertain):self.worker.health()
 def test_guard_accepts_direct_health_without_ssh_process(self):
  from test_worker_guard import GuardTests
  from types import SimpleNamespace
  f=GuardTests();f.setUp();self.addCleanup(f.tearDown);value=f.running();sid=value['sessionId'];deadline=value['workDeadline']
  f.sessions.bootstrap=SimpleNamespace(connected=lambda sid:False)
  f.sessions.worker=SimpleNamespace(simulation=True,direct_available=True,bind_session=lambda value:None,health=lambda:{'sessionId':sid,'resourceId':value['resourceId'],'hostIdentity':value['hostIdentity'],'modelState':'ready'})
  result=f.sessions.poll(sid);self.assertEqual(result['state'],'READY');self.assertEqual(result['workDeadline'],deadline);self.assertEqual(f.provider.starts,1)
 def test_real_loopback_ip_san_tls_without_ssh_or_model(self):
  import ssl,hashlib,subprocess,shutil,threading
  from worker_link import WorkerLedger
  from worker_tls import create_server
  openssl=shutil.which('openssl') or 'C:/Program Files/Git/usr/bin/openssl.exe'
  if not Path(openssl).is_file():self.skipTest('OpenSSL unavailable')
  cert=self.root/'cert.pem';key=self.root/'key.pem'
  done=subprocess.run([openssl,'req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(key),'-out',str(cert),'-days','1','-subj','/CN=127.0.0.1','-addext','subjectAltName=IP:127.0.0.1'],capture_output=True,timeout=15)
  self.assertEqual(done.returncode,0)
  self.value['hostIdentity']['ip']='127.0.0.1';self.cfg['hostIdentity']=dict(self.value['hostIdentity'])
  ledger=WorkerLedger(self.root/'tls-data','x'*48,'a'*32,'FIXTURE');ledger.host_identity=self.value['hostIdentity']
  server=create_server(ledger,cert,key,Path(__file__).resolve().parents[2],bind='127.0.0.1',port=0)
  thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
  try:
   self.cfg.update(clientCertificateFile=str(cert),clientKeyFile=str(key),origin='https://127.0.0.1:'+str(server.server_port),caFile=str(cert),certificateSha256=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cert.read_text())).hexdigest());self.write()
   worker=DualHTTPSWorker(self.ssh,self.file,clock=lambda:100);worker.state=lambda:self.value
   self.ssh.health.side_effect=LinkUncertain();health=worker.health();self.assertEqual(worker.active_transport,'direct_https');self.assertFalse(health['modelLoaded'])
   blob=worker.upload(b'SYNTHETIC_DIRECT_TLS_BYTES');self.assertEqual(worker.download(blob['sha256']),b'SYNTHETIC_DIRECT_TLS_BYTES');self.ssh.health.assert_not_called();self.assertEqual(ledger.executor,None)
  finally:server.shutdown();thread.join(timeout=2);server.server_close();ledger.close()
 def test_proxy_mtls_without_source_whitelist(self):
  text=render(None,'172.18.0.3');self.assertIn('ssl_verify_client on;',text);self.assertIn('proxy_ssl_verify on;',text);self.assertIn('proxy_pass 172.18.0.3:9443;',text);self.assertNotIn('allow ',text);self.assertNotIn('http://',text)
  for cpu,target in [('198.51.100.5/32','172.18.0.3'),(None,'8.8.8.8')]:
   with self.assertRaises(ValueError):render(cpu,target)
if __name__=='__main__':unittest.main()
