"""Per-session mTLS provisioning, invoked only after approved host+worker deployment."""
import base64,hashlib,ipaddress,json,ssl,subprocess
from pathlib import Path
from worker_link import HTTPSWorker
from security import runtime_file
from gpu_bootstrap_package import ROOT
REMOTE_PROGRAM="import sys,json,base64,hashlib,os,tarfile,subprocess,time,http.client\nfrom pathlib import Path\nq=PAYLOAD\nh=http.client.HTTPConnection('metadata.nebius.internal',timeout=2);h.request('GET','/v1/instance-data/id',headers={'Metadata':'true'});res=h.getresponse();assert res.status==200 and res.read(129).decode().strip()==q['vmId'];h.close()\nroot=Path(q['root']);root.mkdir(mode=0o700,exist_ok=False)\narchive=root.parent/'gpu-service.tar.gz';assert hashlib.sha256(archive.read_bytes()).hexdigest()==q['archiveSha']\ncode=root/'code';code.mkdir(mode=0o700)\nwith tarfile.open(archive) as t:\n members=t.getmembers();assert len(members)<160\n for m in members:\n  assert m.isfile() and not m.name.startswith('/') and '..' not in Path(m.name).parts\n  dest=code/m.name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(t.extractfile(m).read());dest.chmod(0o600)\nfor name,data in q['files'].items():\n p=root/name;p.write_bytes(base64.b64decode(data));p.chmod(0o600)\np=root/'relay.json';p.write_text(json.dumps(q['relay']));p.chmod(0o600)\nassert time.time()<q['relay']['deadline']\nwith (root/'launch-attempt').open('x'):pass\nwith (root/'relay.log').open('xb') as log:\n child=subprocess.Popen(['sudo','-n','python3','-u','-B',str(code/'project/mtls_relay.py'),'--config',str(p)],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)\ntime.sleep(.5)\nprint(json.dumps({'sessionId':q['sid'],'relayPid':child.pid,'relayExitedEarly':child.poll(),'publicPort':443,'clientCARequired':True,'deadline':q['relay']['deadline']}))\n"

class DirectBootstrap:
    def __init__(self,control,settings):
        if set(settings)!={'enabled','opensslExecutable'} or settings['enabled'] is not True:raise ValueError('EXPLICIT_DIRECT_BOOTSTRAP_ENABLE_REQUIRED')
        exe=Path(settings['opensslExecutable'])
        if not exe.is_absolute() or not exe.is_file() or any(p.is_symlink() for p in (exe,*exe.parents)):raise ValueError('EXPLICIT_OPENSSL_EXECUTABLE_REQUIRED')
        if not getattr(control.sessions.worker,'direct_file',None):raise ValueError('DIRECT_WORKER_FILE_REQUIRED')
        self.control=control;self.exe=str(exe);self.runner=subprocess.run;self.factory=HTTPSWorker

    def revoke(self,sid):
        path=self.control.sessions.worker.direct_file
        value=json.loads(runtime_file(path,ROOT))
        if value.get('enabled') is True and value.get('sessionId')==sid:
            from inference.jobs import atomic
            atomic(path,{'schemaVersion':1,'enabled':False})

    def deploy(self,bootstrap,sid,metadata,receipt,deadline):
        value=bootstrap.check(sid,confirmed=True);host=value['hostIdentity'];ip=str(ipaddress.ip_address(host['ip']))
        bootstrap.attempt(sid,'direct')
        secret=bootstrap.directory(sid)/'mtls';secret.mkdir(mode=0o700,exist_ok=False)
        def run(args):
            bootstrap.check(sid,confirmed=True)
            remaining=min(15,deadline-bootstrap.clock())
            if remaining<=0:raise ValueError('DIRECT_DEPLOY_DEADLINE')
            out=self.runner([self.exe,*args],capture_output=True,timeout=remaining,shell=False)
            if out.returncode:raise ValueError('DIRECT_CERTIFICATE_GENERATION_FAILED')
        for name,subject,extension in [('server',ip,'subjectAltName=IP:'+ip),('cpu-ca','LightTryCPU-'+sid,'basicConstraints=critical,CA:TRUE')]:
            run(['req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(secret/(name+'.key')),'-out',str(secret/(name+'.crt')),'-days','1','-subj','/CN='+subject,'-addext',extension])
        run(['req','-new','-newkey','rsa:2048','-nodes','-keyout',str(secret/'cpu.key'),'-out',str(secret/'cpu.csr'),'-subj','/CN=CPU-'+sid])
        (secret/'client.ext').write_text('basicConstraints=critical,CA:FALSE\nextendedKeyUsage=clientAuth\nkeyUsage=digitalSignature\n')
        run(['x509','-req','-in',str(secret/'cpu.csr'),'-CA',str(secret/'cpu-ca.crt'),'-CAkey',str(secret/'cpu-ca.key'),'-set_serial','2','-days','1','-extfile',str(secret/'client.ext'),'-out',str(secret/'cpu.crt')])
        for path in secret.iterdir():path.chmod(0o600)
        root='/home/'+host['sshUser']+'/lighttry-bootstrap-'+sid+'/mtls-relay'
        relay={'bind':'0.0.0.0','port':443,'serverCertificate':root+'/server.crt','serverKey':root+'/server.key','clientCa':root+'/cpu-ca.crt','workerCa':root+'/worker-ca.crt','workerIp':receipt['tlsBind'],'workerPort':receipt['tlsPort'],'workerName':'localhost','deadline':deadline}
        files={name:base64.b64encode((secret/name).read_bytes()).decode() for name in ['server.crt','server.key','cpu-ca.crt']}
        files['worker-ca.crt']=base64.b64encode(runtime_file(bootstrap.settings['workerCertificateFile'],ROOT)).decode()
        q={'sid':sid,'vmId':host['vmId'],'root':root,'archiveSha':metadata['sha256'],'files':files,'relay':relay}
        program=REMOTE_PROGRAM.replace('PAYLOAD',repr(q)).encode()
        result=json.loads(bootstrap.run(sid,[bootstrap.settings['sshExecutable'],*bootstrap.ssh_args(sid),host['sshUser']+'@'+ip,'python3 -B -'],input=program))
        if result.get('sessionId')!=sid or result.get('relayExitedEarly') is not None or result.get('deadline')!=deadline:raise ValueError('DIRECT_RELAY_ACK_MISMATCH')
        bootstrap.write(bootstrap.directory(sid)/'direct-relay.json',result)
        pin=hashlib.sha256(ssl.PEM_cert_to_DER_cert((secret/'server.crt').read_text())).hexdigest()
        cfg={'schemaVersion':1,'enabled':True,'sessionId':sid,'resourceId':value['resourceId'],'hostIdentity':host,'origin':'https://'+ip+':443','tokenFile':bootstrap.settings['workerTokenFile'],'caFile':str(secret/'server.crt'),'certificateSha256':pin,'clientCertificateFile':str(secret/'cpu.crt'),'clientKeyFile':str(secret/'cpu.key')}
        client=self.factory(cfg['origin'],runtime_file(cfg['tokenFile'],ROOT).decode().strip(),ca_file=cfg['caFile'],certificate_sha256=pin,client_certificate=cfg['clientCertificateFile'],client_key=cfg['clientKeyFile'])
        health=client.health()
        if any(health.get(k)!=cfg[k] for k in ['sessionId','resourceId','hostIdentity']):raise ValueError('DIRECT_HEALTH_BINDING_MISMATCH')
        bootstrap.check(sid,confirmed=True)
        if bootstrap.clock()>=deadline:raise ValueError('DIRECT_DEPLOY_DEADLINE')
        def publish(current):
            if current.get('stopSent') or not current.get('hostConfirmed') or current.get('hostIdentity')!=host or bootstrap.clock()>=deadline:raise ValueError('DIRECT_SESSION_CHANGED_BEFORE_PUBLISH')
            bootstrap.write(self.control.sessions.worker.direct_file,cfg)
            bootstrap.write(bootstrap.directory(sid)/'direct-ready.json',{'sessionId':sid,'certificateSha256':pin,'healthVerified':True,'deadline':deadline})
            return False
        self.control.sessions.change(sid,'DIRECT_HTTPS_PUBLISHED',publish,record_noop=True)
        return result
