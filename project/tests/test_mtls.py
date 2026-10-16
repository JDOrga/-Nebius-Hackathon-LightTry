"""Real local mutual TLS handshake tests; no GPU/cloud/model."""
import sys,unittest,tempfile,subprocess,threading,hashlib,ssl,shutil
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from worker_tls import create_server
from worker_link import WorkerLedger,HTTPSWorker,LinkUncertain

class MutualTLSTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
  self.openssl=shutil.which('openssl') or 'C:/Program Files/Git/usr/bin/openssl.exe'
  if not Path(self.openssl).is_file():self.skipTest('OpenSSL unavailable')
  def run(args):
   p=subprocess.run([self.openssl,*args],capture_output=True,timeout=15);self.assertEqual(p.returncode,0,'Synthetic certificate generation failed')
  for name,subject,ext in [('server','127.0.0.1','subjectAltName=IP:127.0.0.1'),('cpu-ca','FixtureCPUCA','basicConstraints=critical,CA:TRUE'),('wrong','WrongCPU','extendedKeyUsage=clientAuth')]:
   run(['req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(self.root/(name+'.key')),'-out',str(self.root/(name+'.crt')),'-days','1','-subj','/CN='+subject,'-addext',ext])
  run(['req','-new','-newkey','rsa:2048','-nodes','-keyout',str(self.root/'cpu.key'),'-out',str(self.root/'cpu.csr'),'-subj','/CN=CPUFixture'])
  (self.root/'client.ext').write_text('basicConstraints=critical,CA:FALSE\nextendedKeyUsage=clientAuth\nkeyUsage=digitalSignature\n')
  run(['x509','-req','-in',str(self.root/'cpu.csr'),'-CA',str(self.root/'cpu-ca.crt'),'-CAkey',str(self.root/'cpu-ca.key'),'-set_serial','2','-days','1','-extfile',str(self.root/'client.ext'),'-out',str(self.root/'cpu.crt')])
  self.ledger=WorkerLedger(self.root/'data','SYNTHETIC_MTLS_TOKEN_'+'x'*40,'a'*32,'FIXTURE');self.calls=0
  original=self.ledger.health
  def health():self.calls+=1;return original()
  self.ledger.health=health
  self.server=create_server(self.ledger,self.root/'server.crt',self.root/'server.key',Path(__file__).resolve().parents[2],bind='127.0.0.1',port=0,client_ca=self.root/'cpu-ca.crt')
  self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.addCleanup(self.close)
 def close(self):self.server.shutdown();self.thread.join(timeout=2);self.server.server_close();self.ledger.close()
 def client(self,name=None,*,pin=None):
  return HTTPSWorker('https://127.0.0.1:'+str(self.server.server_port),self.ledger.token,ca_file=str(self.root/'server.crt'),certificate_sha256=pin or hashlib.sha256(ssl.PEM_cert_to_DER_cert((self.root/'server.crt').read_text())).hexdigest(),client_certificate=str(self.root/(name+'.crt')) if name else None,client_key=str(self.root/(name+'.key')) if name else None)
 def test_reconnect_with_valid_cpu_identity_and_no_model(self):
  client=self.client('cpu');self.assertEqual(client.health()['sessionId'],'a'*32);self.assertEqual(client.health()['sessionId'],'a'*32);self.assertEqual(self.calls,2);self.assertIsNone(self.ledger.executor)
 def test_no_client_certificate_rejected_before_http(self):
  with self.assertRaises(LinkUncertain):self.client().health()
  self.assertEqual(self.calls,0)
 def test_untrusted_client_certificate_rejected_before_http(self):
  with self.assertRaises(LinkUncertain):self.client('wrong').health()
  self.assertEqual(self.calls,0)
 def test_server_pin_still_required_with_valid_client_certificate(self):
  with self.assertRaises(LinkUncertain):self.client('cpu',pin='0'*64).health()
  self.assertEqual(self.calls,0)
if __name__=='__main__':unittest.main()
