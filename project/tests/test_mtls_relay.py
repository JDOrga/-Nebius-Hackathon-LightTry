import sys,time,threading,ssl,hashlib,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_mtls import MutualTLSTests
from mtls_relay import create_relay
from worker_link import HTTPSWorker,LinkUncertain
class RelayTests(unittest.TestCase):
 def test_actual_mtls_relay_health_and_blob_no_model(self):
  f=MutualTLSTests();f.setUp()
  try:
   # Existing fixture upstream needs CPU identity; use a separate private TLS server without client auth.
   from worker_tls import create_server
   upstream=create_server(f.ledger,f.root/'server.crt',f.root/'server.key',Path(__file__).resolve().parents[2],bind='127.0.0.1',port=0)
   thread=threading.Thread(target=upstream.serve_forever,daemon=True);thread.start()
   cfg={'bind':'127.0.0.1','port':0,'serverCertificate':str(f.root/'server.crt'),'serverKey':str(f.root/'server.key'),'clientCa':str(f.root/'cpu-ca.crt'),'workerCa':str(f.root/'server.crt'),'workerIp':'127.0.0.1','workerPort':upstream.server_port,'workerName':'127.0.0.1','deadline':time.time()+60}
   relay=create_relay(cfg,Path(__file__).resolve().parents[2]);rt=threading.Thread(target=relay.serve_forever,daemon=True);rt.start()
   try:
    kwargs={'ca_file':str(f.root/'server.crt'),'certificate_sha256':hashlib.sha256(ssl.PEM_cert_to_DER_cert((f.root/'server.crt').read_text())).hexdigest()}
    client=HTTPSWorker('https://127.0.0.1:'+str(relay.server_port),f.ledger.token,client_certificate=str(f.root/'cpu.crt'),client_key=str(f.root/'cpu.key'),**kwargs)
    self.assertEqual(client.health()['sessionId'],'a'*32);blob=client.upload(b'SYNTHETIC_RELAY_BYTES');self.assertEqual(client.download(blob['sha256']),b'SYNTHETIC_RELAY_BYTES')
    calls=f.calls
    with self.assertRaises(LinkUncertain):HTTPSWorker('https://127.0.0.1:'+str(relay.server_port),f.ledger.token,**kwargs).health()
    self.assertEqual(f.calls,calls);self.assertIsNone(f.ledger.executor)
   finally:relay.shutdown();rt.join(timeout=2);relay.server_close()
  finally:
   if 'upstream' in locals():upstream.shutdown();thread.join(timeout=2);upstream.server_close()
   f.doCleanups()
if __name__=='__main__':unittest.main()
