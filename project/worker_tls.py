"""Bounded private TLS ingress for the GPU container; no public bind or model imports."""
import ipaddress
from socketserver import ThreadingMixIn,TCPServer
import ssl
import threading
from wsgiref.simple_server import WSGIServer,WSGIRequestHandler

from security import runtime_file
from worker_link import WorkerApplication


def private_bind(value):
    ip=ipaddress.ip_address(value)
    networks=('127.0.0.0/8','10.0.0.0/8','172.16.0.0/12','192.168.0.0/16')
    if ip.version!=4 or not any(ip in ipaddress.ip_network(n) for n in networks):
        raise ValueError('PRIVATE_GPU_TLS_BIND_REQUIRED')
    return str(ip)


class PrivateTLS( ThreadingMixIn, WSGIServer):
    daemon_threads=True
    request_queue_size=8
    def server_bind(self):
        TCPServer.server_bind(self)
        self.server_name='localhost';self.server_port=self.server_address[1]
        self.setup_environ()  # Never perform a reverse-DNS lookup during startup.
    def __init__(self,*args,**kw):
        self.slots=threading.BoundedSemaphore(2)
        super().__init__(*args,**kw)
    def process_request(self,request,client_address):
        request.settimeout(10)
        if not self.slots.acquire(blocking=False):self.close_request(request);return
        try:super().process_request(request,client_address)
        except BaseException:self.slots.release();raise
    def process_request_thread(self,request,client_address):
        try:
            request.do_handshake()
            super().process_request_thread(request,client_address)
        except (OSError,ssl.SSLError):self.shutdown_request(request)
        finally:self.slots.release()
    def handle_error(self,*args):pass  # Never log credentials/raw request targets.


class SilentHandler(WSGIRequestHandler):
    def log_message(self,*args):pass
    def get_environ(self):
        env=super().get_environ();env['HTTPS']='on';return env
    def parse_request(self):
        if not super().parse_request():return False
        if sum(len(k)+len(v)+4 for k,v in self.headers.items())>8192:
            self.send_error(431);return False
        return True


def create_server(ledger,certificate,key,code_root,*,bind='127.0.0.1',port=9443):
    bind=private_bind(bind)
    if type(port) is not int or not 0<=port<=65535:raise ValueError('TLS_PORT_INVALID')
    runtime_file(certificate,code_root);runtime_file(key,code_root)
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.minimum_version=ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(str(certificate),str(key))
    server=PrivateTLS((bind,port),SilentHandler)
    try:
        server.set_app(WorkerApplication(ledger))
        server.socket=context.wrap_socket(server.socket,server_side=True,do_handshake_on_connect=False)
        return server
    except BaseException:server.server_close();raise
