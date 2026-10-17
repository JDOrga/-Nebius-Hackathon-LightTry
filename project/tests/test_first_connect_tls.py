"""Real loopback mTLS bootstrap; installer/model/cloud are explicit test doubles."""
import base64
import hashlib
import http.client
import ssl
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parent))
import test_mtls
import test_first_connect
from first_connect import FirstConnect
from worker_tls import PrivateTLS,SilentHandler


class FirstConnectTLS(unittest.TestCase):
    def setUp(self):
        f=test_mtls.MutualTLSTests();f.setUp();self.f=f
        self.addCleanup(f.doCleanups);self.addCleanup(f.tearDown)
        core=test_first_connect.AgentTests();core.setUp();self.core=core
        self.addCleanup(core.doCleanups)
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.minimum_version=ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(f.root/'server.crt',f.root/'server.key');context.load_verify_locations(f.root/'cpu-ca.crt');context.verify_mode=ssl.CERT_REQUIRED
        self.server=PrivateTLS(('127.0.0.1',0),SilentHandler);self.server.set_app(core.agent)
        self.server.socket=context.wrap_socket(self.server.socket,server_side=True,do_handshake_on_connect=False)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.close)
        self.router=FirstConnect.__new__(FirstConnect)
        self.router.config={'certificateSha256':hashlib.sha256(ssl.PEM_cert_to_DER_cert((f.root/'server.crt').read_text())).hexdigest()}
        self.router.context=ssl.create_default_context(cafile=f.root/'server.crt');self.router.context.load_cert_chain(f.root/'cpu.crt',f.root/'cpu.key')
        self.router.control=type('Control',(),{'scope':{'expiresAt':time.time()+500}})()
        self.value={'workDeadline':time.time()+400,'absoluteDeadline':time.time()+500,'hostIdentity':{'ip':'127.0.0.1'}}
        self.real_connection=http.client.HTTPSConnection
    def close(self):self.server.shutdown();self.server.server_close();self.thread.join()
    def request(self,method,path,body=None):
        def connection(host,port,**kw):
            self.assertEqual(port,8443)
            return self.real_connection(host,self.server.server_port,**kw)
        with patch('first_connect.http',SimpleNamespace(client=SimpleNamespace(HTTPSConnection=connection))):
            return self.router.request(self.value,method,path,body)
    def test_authenticated_https_identity_without_ssh(self):
        self.assertEqual(self.request('GET','/bootstrap/v1/identity')['vmId'],'computeinstance-fixture')
        self.assertEqual(self.core.calls,0)
    def test_missing_cpu_certificate_rejected_before_http(self):
        self.router.context=ssl.create_default_context(cafile=self.f.root/'server.crt')
        with self.assertRaises((ssl.SSLError,OSError)):self.request('GET','/bootstrap/v1/identity')
        self.assertEqual(self.core.calls,0)
    def test_wrong_server_pin_rejected_before_identity(self):
        self.router.config['certificateSha256']='0'*64
        with self.assertRaisesRegex(ValueError,'CERTIFICATE'):self.request('GET','/bootstrap/v1/identity')
        self.assertEqual(self.core.calls,0)
    def test_install_and_status_over_real_mtls_single_side_effect(self):
        c=self.core;body={'request':c.q,'code':base64.b64encode(c.code).decode(),'secret':base64.b64encode(c.secret).decode()}
        self.assertEqual(self.request('POST','/bootstrap/v1/install',body)['status'],'installed')
        self.assertEqual(self.request('GET','/bootstrap/v1/status/'+'a'*32)['status'],'installed')
        self.assertEqual(self.request('POST','/bootstrap/v1/install',body)['status'],'installed')
        self.assertEqual(c.calls,1)

if __name__=='__main__':unittest.main()
