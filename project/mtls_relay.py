"""Bounded mTLS HTTP relay to a private TLS worker; no model/cloud/SSH actions."""
import http.client,ipaddress,json,re,socket,ssl,threading,time
from worker_tls import PrivateTLS,SilentHandler,private_bind
from security import runtime_file

MAX=32*1024*1024
class Relay:
 def __init__(self,target,port,context,name,deadline):self.target,self.port,self.context,self.name,self.deadline=target,port,context,name,deadline
 def __call__(self,environ,start_response):
  if time.time()>=self.deadline:start_response('503 Service Unavailable',[]);return [b'']
  method=environ.get('REQUEST_METHOD');path=environ.get('PATH_INFO','')
  if method not in ('GET','POST','PUT') or not re.fullmatch(r'/v1/(?:health|jobs|jobs/[a-f0-9]{32}|blobs/[a-f0-9]{64})',path) or environ.get('QUERY_STRING'):
   start_response('404 Not Found',[]);return [b'']
  length=environ.get('CONTENT_LENGTH') or '0'
  if not length.isdecimal() or int(length)>MAX:start_response('413 Payload Too Large',[]);return [b'']
  conn=http.client.HTTPSConnection(self.name,self.port,timeout=5,context=self.context)
  try:
   raw=socket.create_connection((self.target,self.port),timeout=3)
   try:conn.sock=self.context.wrap_socket(raw,server_hostname=self.name)
   except BaseException:raw.close();raise
   data=environ['wsgi.input'].read(int(length))
   if len(data)!=int(length):raise ValueError('INCOMPLETE_BODY')
   conn.request(method,path,body=data if data else None,headers={'Authorization':environ.get('HTTP_AUTHORIZATION',''),'Content-Type':environ.get('CONTENT_TYPE','application/octet-stream')})
   response=conn.getresponse();body=response.read(MAX+1)
   if len(body)>MAX or response.status not in (200,201,202,400,401,403,404,409,413,422,429,500,503):raise ValueError('UPSTREAM_RESPONSE_REJECTED')
   start_response(str(response.status)+' '+http.client.responses.get(response.status,'Error'),[('Content-Type',response.getheader('Content-Type','application/octet-stream')),('Content-Length',str(len(body)))]);return [body]
  except Exception:start_response('503 Service Unavailable',[('Content-Length','0')]);return [b'']
  finally:conn.close()

def create_relay(cfg,code_root):
 required={'bind','port','serverCertificate','serverKey','clientCa','workerCa','workerIp','workerPort','workerName','deadline'}
 if set(cfg)!=required:raise ValueError('EXPLICIT_RELAY_BINDING_REQUIRED')
 if cfg['bind'] not in ('0.0.0.0','127.0.0.1'):raise ValueError('EXPLICIT_RELAY_LISTENER_REQUIRED')
 target=private_bind(cfg['workerIp'])
 if cfg['workerName'] not in ('localhost','127.0.0.1'):raise ValueError('PRIVATE_WORKER_TLS_NAME_REQUIRED')
 if any(type(cfg[k]) is not int or not 0<=cfg[k]<=65535 for k in ('port','workerPort')) or cfg['workerPort']==0:raise ValueError('PORT_INVALID')
 if not time.time()<cfg['deadline']<=time.time()+3600:raise ValueError('FIXED_RELAY_WINDOW_REQUIRED')
 for k in ('serverCertificate','serverKey','clientCa','workerCa'):runtime_file(cfg[k],code_root)
 server_context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);server_context.minimum_version=ssl.TLSVersion.TLSv1_2;server_context.load_cert_chain(cfg['serverCertificate'],cfg['serverKey']);server_context.load_verify_locations(cfg['clientCa']);server_context.verify_mode=ssl.CERT_REQUIRED;server_context.options|=ssl.OP_NO_TICKET
 upstream=ssl.create_default_context(cafile=cfg['workerCa'])
 server=PrivateTLS((cfg['bind'],cfg['port']),SilentHandler)
 try:server.set_app(Relay(target,cfg['workerPort'],upstream,cfg['workerName'],cfg['deadline']));server.socket=server_context.wrap_socket(server.socket,server_side=True,do_handshake_on_connect=False);return server
 except BaseException:server.server_close();raise

def main():
 import argparse
 from pathlib import Path
 p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True);args=p.parse_args();root=Path(__file__).resolve().parent.parent;cfg=json.loads(runtime_file(args.config,root));server=create_relay(cfg,root)
 timer=threading.Timer(max(.01,cfg['deadline']-time.time()),server.shutdown);timer.daemon=True;timer.start()
 try:server.serve_forever(poll_interval=.2)
 finally:timer.cancel();server.server_close()
if __name__=='__main__':main()
