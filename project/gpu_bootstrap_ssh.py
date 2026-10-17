"""Guard-owned, single-attempt current-host SSH deployment and private TLS tunnel."""
import base64
import hashlib
import ipaddress
import json
import os
from pathlib import Path,PurePosixPath
import re
import ssl
import stat
import socket
import subprocess
import threading
import time

from inference.jobs import atomic,read,ID,JobError
from security import runtime_file
from model_contract import grant_file
from gpu_bootstrap_package import helper_sha,archive,ROOT
from bootstrap_errors import classify,public_error,stderr_code,CommandFailure,STAGES


def build(control,binding):return SSHBootstrap(control,binding)


def host_key(raw,address):
    """Only one current ed25519 host key, never a permissive known-hosts scan."""
    keys=set()
    for line in raw.splitlines():
        if not line or line.startswith('#'):continue
        parts=line.split()
        if len(parts)!=3 or parts[0] not in (address,'['+address+']:22') or parts[1]!='ssh-ed25519':
            raise ValueError('SSH_HOST_KEY_INVALID')
        key=base64.b64decode(parts[2],validate=True)
        if key[:4]!=b'\0\0\0\x0b' or key[4:15]!=b'ssh-ed25519' or key[15:19]!=b'\0\0\0 ' or len(key)!=51:
            raise ValueError('SSH_HOST_KEY_INVALID')
        keys.add(parts[2])
    if len(keys)!=1:raise ValueError('SSH_HOST_KEY_NOT_UNIQUE')
    value=next(iter(keys));fingerprint='SHA256:'+base64.b64encode(hashlib.sha256(base64.b64decode(value)).digest()).decode().rstrip('=')
    return value,fingerprint


class SSHBootstrap:
    def __init__(self,control,binding):
        required={'sshExecutable','scpExecutable','keyscanExecutable','keyFile','bundleManifestFile','workerConfigFile',
                  'modelGrantFile','workerTokenFile','workerCertificateFile','workerKeyFile','tunnelPort','workerPort','expectedImage'}
        if not isinstance(binding,dict) or set(binding)!=required:raise ValueError('EXPLICIT_SSH_BOOTSTRAP_BINDING_REQUIRED')
        self.control,self.settings,self.clock=control,dict(binding),control.clock
        self.root=control.sessions.root/'bootstrap'
        if os.name!='nt' and stat.S_IMODE(control.sessions.root.stat().st_mode)&0o077:
            raise ValueError('PRIVATE_GUARD_DIRECTORY_REQUIRED')
        for name in ('sshExecutable','scpExecutable','keyscanExecutable'):
            p=Path(binding[name])
            if not p.is_absolute() or not p.is_file() or any(x.is_symlink() for x in (p,*p.parents)):raise ValueError('EXPLICIT_SSH_EXECUTABLE_REQUIRED')
        for name in ('keyFile','bundleManifestFile','workerConfigFile','workerTokenFile','workerCertificateFile','workerKeyFile'):
            runtime_file(binding[name],ROOT,1024*1024)
        for name in ('tunnelPort','workerPort'):
            if type(binding[name]) is not int or not 1024<=binding[name]<=65535:raise ValueError('BOOTSTRAP_PORT_INVALID')
        if not isinstance(binding['expectedImage'],str) or not re.fullmatch('[A-Za-z0-9./:@_-]{1,256}',binding['expectedImage']):raise ValueError('EXPECTED_CONTAINER_IMAGE_REQUIRED')
        model=Path(binding['modelGrantFile'])
        if not model.is_absolute() or model.resolve().is_relative_to(ROOT) or any(p.is_symlink() for p in (model,*model.parents)):
            raise ValueError('PRIVATE_MODEL_GRANT_FILE_REQUIRED')
        worker=control.sessions.worker
        certificate=runtime_file(binding['workerCertificateFile'],ROOT).decode('ascii')
        pin=hashlib.sha256(ssl.PEM_cert_to_DER_cert(certificate)).hexdigest()
        token=runtime_file(binding['workerTokenFile'],ROOT).decode().strip()
        if worker.endpoint.hostname!='localhost' or worker.endpoint.port!=binding['tunnelPort'] or worker.certificate_sha256!=pin or worker.token!=token:
            raise ValueError('BOOTSTRAP_HTTPS_BINDING_MISMATCH')
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(binding['workerCertificateFile'],binding['workerKeyFile'])
        self.frozen={name:hashlib.sha256(runtime_file(binding[name],ROOT,1024*1024)).hexdigest() for name in
            ('keyFile','bundleManifestFile','workerConfigFile','workerTokenFile','workerCertificateFile','workerKeyFile')}
        self.runner=subprocess.run;self.spawn=subprocess.Popen
        self.lock=threading.RLock();self.thread=None;self.tunnel=None;self.stopped=threading.Event()

    def directory(self,sid):
        if not isinstance(sid,str) or not ID.fullmatch(sid):raise ValueError('SESSION_INVALID')
        p=self.root/sid
        if any(x.is_symlink() for x in (p,*p.parents)):raise ValueError('BOOTSTRAP_PATH_UNSAFE')
        return p

    def write(self,path,value):atomic(path,value);path.chmod(0o600)

    def status(self,sid,stage,**extra):
        self.write(self.directory(sid)/'status.json',{'sessionId':sid,'stage':stage,'at':self.clock(),**extra})

    def record_failure(self,sid,error,duration_ms=None):
        cached=getattr(self,'_last_diagnostic',None)
        if cached and cached[0]==sid and cached[1] is error:
            info=cached[2]
        else:
            info=classify(error,getattr(self,'current_stage','unknown'),duration_ms)
            info['at']=self.clock()
            self._last_diagnostic=(sid,error,info)
        self.write(self.directory(sid)/'failure-info.json',info)
        return info

    def check(self,sid,*,confirmed=False):
        if self.stopped.is_set():raise ValueError('BOOTSTRAP_CLOSED')
        value=self.control.sessions.get(sid);now=self.clock()
        if (value['scopeId']!=self.control.scope['scopeId'] or value['resourceId']!=self.control.scope['resourceId'] or
            value.get('state') not in ('LOADING','READY','EXECUTING') or value.get('stopSent') or not value.get('hostIdentity') or
            type(value.get('lastObservedAt')) not in (int,float) or not 0<=now-value['lastObservedAt']<=30 or
            not value.get('workDeadline') or now>=min(value['workDeadline'],value['absoluteDeadline'],self.control.scope['expiresAt']) or
            value.get('image')!=self.settings['expectedImage']):raise ValueError('CURRENT_RUNNING_HOST_REQUIRED')
        if not value.get('recoveryMode') and value.get('idleDeadline') is not None and value['state'] in ('LOADING','READY') and now>=value['idleDeadline']:
            raise ValueError('CURRENT_RUNNING_HOST_REQUIRED')
        host=value['hostIdentity']
        if ipaddress.ip_address(host['ip']).version!=4:raise ValueError('BOOTSTRAP_IPV4_REQUIRED')
        if not re.fullmatch('[a-z_][a-z0-9_-]{0,31}',host['sshUser']):raise ValueError('SSH_USER_INVALID')
        if confirmed:
            candidate=read(self.directory(sid)/'candidate.json')
            pin=self.directory(sid)/'known_hosts'
            expected='lighttry-'+sid+' ssh-ed25519 '+candidate['keyData']+'\n'
            if not value['hostConfirmed'] or candidate['hostIdentity']!=host or runtime_file(pin,ROOT).decode()!=expected:
                raise ValueError('CURRENT_SSH_PIN_REQUIRED')
        if getattr(self,'deployment_session',sid)==sid and hasattr(self,'deployment_grant') and grant_file(self.settings['modelGrantFile'],sid,value['resourceId'],clock=self.clock)!=self.deployment_grant:
            raise ValueError('MODEL_GRANT_CHANGED_DURING_BOOTSTRAP')
        return value

    def public(self,value):
        sid=value.get('sessionId')
        if not sid:return {'stage':'pending','canConfirm':False}
        try:
            state=read(self.directory(sid)/'status.json')
        except (OSError,ValueError,KeyError):return {'stage':'pending','canConfirm':False}
        result={'stage':state.get('stage','uncertain'),'canConfirm':False}
        info=public_error(state.get('failure'))
        if info:result['failure']=info
        if state.get('error') in ('BOOTSTRAP_REMOTE_UNCERTAIN','BOOTSTRAP_UNCERTAIN','SSH_TUNNEL_NOT_LIVE_NO_RECONNECT','FIRST_CONNECT_UNCERTAIN_NO_RETRY'):
            result['error']=state['error']
        try:
            self.check(sid)
            candidate=read(self.directory(sid)/'candidate.json')
            matches=candidate['hostIdentity']==value.get('hostIdentity') and candidate['sessionId']==sid
            return {**result,'canConfirm':bool(matches and not value.get('hostConfirmed') and state['stage']=='awaiting_host_confirmation' and value.get('state')=='LOADING'),
                    'fingerprint':candidate['fingerprint'] if matches else None,'sessionId':sid,
                    'hostIdentity':candidate['hostIdentity'] if matches else None}
        except (OSError,ValueError,KeyError):return result

    def confirm(self,sid,host,fingerprint):
        with self.lock:
            try:value=self.check(sid)
            except ValueError:
                raise JobError('CURRENT_HOST_STATE_UNAVAILABLE','当前主机状态尚未重新核实，未确认连接；请等待状态恢复后再确认，或停止本轮。',409) from None
            candidate=read(self.directory(sid)/'candidate.json')
            if host!=value['hostIdentity'] or candidate['hostIdentity']!=host or candidate['fingerprint']!=fingerprint:
                raise JobError('CURRENT_SSH_HOST_CONFIRMATION_REQUIRED','请确认本次服务器的主机身份与指纹。',409)
            path=self.directory(sid)/'known_hosts';raw=('lighttry-'+sid+' ssh-ed25519 '+candidate['keyData']+'\n').encode()
            try:
                with path.open('xb') as stream:stream.write(raw)
                path.chmod(0o600)
            except FileExistsError:
                if path.read_bytes()!=raw:raise ValueError('SSH_PIN_CHANGED')

    def attempt(self,sid,stage):
        self.current_stage='install' if stage=='launch' else 'direct_https' if stage=='direct' else stage if stage in STAGES else 'unknown'
        path=self.directory(sid)/(stage+'-attempt')
        try:
            with path.open('x'):pass
            path.chmod(0o600)
        except FileExistsError:raise ValueError('BOOTSTRAP_ATTEMPT_ALREADY_LATCHED')

    def preflight(self,observation):
        if observation.get('image')!=self.settings['expectedImage']:raise ValueError('BOOTSTRAP_IMAGE_MISMATCH')
        if any(hashlib.sha256(runtime_file(self.settings[name],ROOT,1024*1024)).hexdigest()!=sha for name,sha in self.frozen.items()):
            raise ValueError('FROZEN_BOOTSTRAP_BINDING_CHANGED')
        metadata=json.loads(runtime_file(self.settings['bundleManifestFile'],ROOT,1024*1024))
        code=runtime_file(metadata['archive'],ROOT,8*1024**2)
        if Path(metadata['archive']).name!='gpu-service.tar.gz' or hashlib.sha256(code).hexdigest()!=metadata['sha256'] or helper_sha()!=metadata['helperSha256']:
            raise ValueError('FROZEN_BOOTSTRAP_CODE_CHANGED')
        cfg=json.loads(runtime_file(self.settings['workerConfigFile'],ROOT))
        if (set(cfg)!={'schemaVersion','enabled','executionMode','python','repo','checkpointDir','cudaHome','grantFile'} or
            cfg.get('schemaVersion')!=1 or cfg.get('executionMode')!='resident' or cfg.get('enabled') is not True):raise ValueError('RESIDENT_ENABLE_REQUIRED')
        for key in ('python','repo','checkpointDir','cudaHome'):
            if not isinstance(cfg.get(key),str) or not PurePosixPath(cfg[key]).is_absolute() or '..' in PurePosixPath(cfg[key]).parts:
                raise ValueError('EXPLICIT_GPU_CONTAINER_RUNTIME_REQUIRED')
        with socket.socket() as probe:probe.bind(('127.0.0.1',self.settings['tunnelPort']))
        return metadata,code,cfg

    def run(self,sid,command,*,input=None,confirmed=True):
        value=self.check(sid,confirmed=confirmed)
        deployment_deadline=(self.deploy_deadline if getattr(self,'deployment_session',None)==sid else value['workDeadline'])
        bound=min(20,value['workDeadline']-self.clock(),value['absoluteDeadline']-self.clock(),
                  deployment_deadline-self.clock(),self.control.scope['expiresAt']-self.clock())
        if bound<=0:raise ValueError('BOOTSTRAP_DEADLINE')
        kw={'input':input} if input is not None else {'stdin':subprocess.DEVNULL}
        started=self.clock()
        try:result=self.runner(command,capture_output=True,timeout=bound,shell=False,**kw)
        except Exception as error:
            self.record_failure(sid,error,(self.clock()-started)*1000)
            raise
        if result.returncode or len(result.stdout)>1024*1024:
            # Accept only one exact reviewed helper label. Never persist raw SSH
            # stderr/stdout, command argv, token, key paths or remote environment.
            allowed={'CONTAINER_NETWORK_REFERENCE_CYCLE','CONTAINER_NETWORK_REFERENCE_INVALID','CONTAINER_NETWORK_REFERENCE_NOT_UNIQUE',
                'CONTAINER_NETWORK_REFERENCE_LIMIT','CONTAINER_NETWORK_IDENTITY_MISMATCH','CONTAINER_NETWORK_DRIVER_UNSUPPORTED',
                'CONTAINER_NETWORK_SUBNET_MISMATCH','VM_METADATA_UNAVAILABLE','VM_METADATA_ID_MISMATCH','CURRENT_VM_IDENTITY_MISMATCH','BOOTSTRAP_DEADLINE','SESSION_INVALID',
                'NO_VALID_RUNNING_CONTAINERS','CONTAINER_MATCH_NOT_UNIQUE','INVALID_CONTAINER_ID',
                'DOCKER_QUERY_FAILED','CONTAINER_NETWORK_NOT_PRIVATE_BRIDGE','CONTAINER_NETWORK_NOT_UNIQUE',
                'CONTAINER_NETWORK_NOT_PRIVATE','CONTAINER_CHANGED_DURING_BOOTSTRAP','BOOTSTRAP_UPLOAD_UNSAFE',
                'VM_ARCHIVE_HASH_MISMATCH','CONTAINER_INSTALL_UNCERTAIN','BOOTSTRAP_OPERATION_NOT_ALLOWED',
                'BOOTSTRAP_VM_FAILED'}
            stderr=result.stderr
            label=stderr.decode('ascii',errors='replace').strip() if isinstance(stderr,bytes) and len(stderr)<=256 else ''
            if label not in allowed:label='UNRECOGNIZED_REMOTE_ERROR'
            code='REMOTE_OUTPUT_TOO_LARGE' if len(result.stdout)>1024*1024 else 'REMOTE_HELPER_FAILED' if label!='UNRECOGNIZED_REMOTE_ERROR' else stderr_code(result.stderr)
            error=CommandFailure(code,'BOOTSTRAP_REMOTE_'+label if label!='UNRECOGNIZED_REMOTE_ERROR' else 'BOOTSTRAP_REMOTE_UNCERTAIN',result.returncode)
            info=self.record_failure(sid,error,(self.clock()-started)*1000)
            self.write(self.directory(sid)/'remote-error.json',{'sessionId':sid,'exitCode':result.returncode,
                'safeLabel':label,'stdoutBytes':len(result.stdout),'stderrRecorded':False,'at':self.clock()})
            raise error
        return result.stdout

    def capture(self,sid):
        value=self.check(sid);self.attempt(sid,'capture')
        output=self.run(sid,[self.settings['keyscanExecutable'],'-T','3','-t','ed25519',value['hostIdentity']['ip']],confirmed=False)
        key,fingerprint=host_key(output.decode('ascii'),value['hostIdentity']['ip'])
        self.write(self.directory(sid)/'candidate.json',{'sessionId':sid,'hostIdentity':value['hostIdentity'],
            'keyData':key,'fingerprint':fingerprint,'capturedAt':self.clock()})
        self.status(sid,'awaiting_host_confirmation')

    def ssh_args(self,sid):
        return ['-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','StrictHostKeyChecking=yes',
            '-o','UserKnownHostsFile="'+(self.directory(sid)/'known_hosts').as_posix()+'"','-o','GlobalKnownHostsFile='+('NUL' if os.name=='nt' else '/dev/null'),
            '-o','HostKeyAlias=lighttry-'+sid,'-o','ConnectTimeout=5','-o','ConnectionAttempts=1','-i',self.settings['keyFile']]

    def vm(self,sid,q):
        value=self.check(sid,confirmed=True)
        probe=(ROOT/'cloud/remote_probe.py').read_text(encoding='utf-8');probe=probe[:probe.index("\nif __name__")]
        program=(probe+'\n'+(ROOT/'project/gpu_bootstrap_vm.py').read_text(encoding='utf-8')).encode('utf-8')
        data=base64.b64encode(json.dumps(q,separators=(',',':')).encode()).decode()
        host=value['hostIdentity'];target=host['sshUser']+'@'+host['ip']
        raw=self.run(sid,[self.settings['sshExecutable'],*self.ssh_args(sid),target,'python3 -B - '+data],input=program)
        result=json.loads(raw)
        if not isinstance(result,dict):raise CommandFailure('REMOTE_JSON_INVALID','BOOTSTRAP_RESPONSE_INVALID')
        if result.get('sessionId')!=sid:raise ValueError('BOOTSTRAP_ACK_MISMATCH')
        return result

    def deploy(self,sid):
        value=self.check(sid,confirmed=True)
        self.current_stage='preflight'
        metadata,code,cfg=self.preflight({'image':value['image']})
        grant=grant_file(self.settings['modelGrantFile'],sid,value['resourceId'],clock=self.clock)
        deadline=min(value['workDeadline'],value['absoluteDeadline'],self.control.scope['expiresAt'])
        if grant['hostIdentity']!=value['hostIdentity'] or grant['expiresAt']>deadline:raise ValueError('BOOTSTRAP_MODEL_GRANT_MISMATCH')
        deadline=min(deadline,grant['expiresAt']);self.deploy_deadline=deadline
        self.deployment_grant=grant;self.deployment_session=sid
        secrets={'worker.json':json.dumps(cfg).encode(),'model-grant.json':json.dumps(grant).encode(),
            'tls.crt':runtime_file(self.settings['workerCertificateFile'],ROOT),'tls.key':runtime_file(self.settings['workerKeyFile'],ROOT),
            'worker.token':runtime_file(self.settings['workerTokenFile'],ROOT),'launch.json':json.dumps({'sessionId':sid,'deadline':deadline}).encode()}
        secret=archive(secrets);path=self.directory(sid)/'session-secrets.tar.gz'
        with path.open('xb') as stream:stream.write(secret)
        path.chmod(0o600)
        common={'sessionId':sid,'resourceId':value['resourceId'],'hostIdentity':value['hostIdentity'],
            'deadline':deadline,'image':self.settings['expectedImage'],'tlsPort':self.settings['workerPort'],
            'containerPython':cfg['python'],'codeSha256':metadata['sha256'],'secretSha256':hashlib.sha256(secret).hexdigest(),
            'installer':base64.b64encode((ROOT/'project/gpu_bootstrap_container.py').read_bytes()).decode()}
        self.attempt(sid,'prepare');remote=self.vm(sid,{**common,'operation':'prepare'})
        directory='/home/'+value['hostIdentity']['sshUser']+'/lighttry-bootstrap-'+sid
        if (remote.get('uploadDirectory')!=directory or not re.fullmatch('[a-f0-9]{64}',remote.get('containerId','')) or
            type(remote.get('observedAt')) not in (int,float) or not abs(remote['observedAt']-self.clock())<=15):
            raise ValueError('BOOTSTRAP_UPLOAD_TARGET_MISMATCH')
        # One planned upload, never retry after an uncertain ACK.
        self.attempt(sid,'upload')
        target=value['hostIdentity']['sshUser']+'@'+value['hostIdentity']['ip']+':'+directory+'/'
        self.run(sid,[self.settings['scpExecutable'],*self.ssh_args(sid),metadata['archive'],str(path),target])
        self.attempt(sid,'launch')
        receipt=self.vm(sid,{**common,'operation':'install','containerId':remote['containerId'],'tlsBind':remote['tlsBind']})
        if (receipt.get('resourceId')!=value['resourceId'] or receipt.get('codeSha256')!=metadata['sha256'] or
            receipt.get('launchRequested') is not True or receipt.get('tlsBind')!=remote['tlsBind']):raise ValueError('BOOTSTRAP_LAUNCH_ACK_MISMATCH')
        from worker_tls import private_bind
        bind=private_bind(remote['tlsBind']);self.check(sid,confirmed=True);self.attempt(sid,'tunnel')
        command=[self.settings['sshExecutable'],*self.ssh_args(sid),'-o','ExitOnForwardFailure=yes','-o','ServerAliveInterval=5',
            '-o','ServerAliveCountMax=1','-N','-L','127.0.0.1:'+str(self.settings['tunnelPort'])+':'+bind+':'+str(self.settings['workerPort']),
            value['hostIdentity']['sshUser']+'@'+value['hostIdentity']['ip']]
        self.tunnel=self.spawn(command,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                               shell=False,start_new_session=os.name!='nt')
        self.tunnel_sid=sid
        if self.stopped.is_set():self.close_tunnel();raise ValueError('BOOTSTRAP_CLOSED')
        try:self.check(sid,confirmed=True)
        except Exception:self.close_tunnel();raise
        self.write(self.directory(sid)/'deployed.json',receipt)
        direct=getattr(self.control,'direct_bootstrap',None)
        if direct:
            self.current_stage='direct_https'
            self.status(sid,'deploying_direct_https')
            direct.deploy(self,sid,metadata,receipt,deadline)
        self.status(sid,'deployed')  # This is NOT model READY; only authenticated health can prove that.

    def step(self,value):
        sid=value.get('sessionId')
        if not sid:return
        if value.get('verifiedStopped') or value.get('stopSent'):
            self.close_tunnel()
            direct=getattr(self.control,'direct_bootstrap',None)
            if direct:direct.revoke(sid)
            return
        if value.get('state') not in ('LOADING','READY','EXECUTING'):return
        with self.lock:
            if self.thread and self.thread.is_alive():return
            directory=self.directory(sid);directory.mkdir(parents=True,exist_ok=True,mode=0o700)
            if (directory/'deployed.json').exists():
                if self.tunnel is None or self.tunnel.poll() is not None:
                    if (directory/'direct-ready.json').is_file() and getattr(self.control.sessions.worker,'direct_available',False) is True:self.status(sid,'direct_https_configured_ssh_unavailable')
                    else:self.status(sid,'uncertain',error='SSH_TUNNEL_NOT_LIVE_NO_RECONNECT')
                return
            if (directory/'failed.json').exists():return
            def run():
                try:
                    self.current_stage='state_check'
                    if not (directory/'candidate.json').exists():self.capture(sid);return
                    if not value.get('hostConfirmed'):return
                    issuer=getattr(self.control,'model_grant_issuer',None)
                    if issuer:
                        self.current_stage='authorize'
                        self.check(sid,confirmed=True)
                        issuer.ensure(sid)
                    if not Path(self.settings['modelGrantFile']).is_file():self.status(sid,'waiting_authorization');return
                    self.status(sid,'deploying');self.deploy(sid)
                except Exception as error:
                    info=self.record_failure(sid,error)
                    legacy={'FROZEN_BOOTSTRAP_BINDING_CHANGED','FROZEN_BOOTSTRAP_CODE_CHANGED','BOOTSTRAP_DEADLINE','CURRENT_RUNNING_HOST_REQUIRED','BOOTSTRAP_ACK_MISMATCH','SSH_HOST_KEY_INVALID','SSH_HOST_KEY_NOT_UNIQUE'}
                    label=str(error) if str(error) in legacy else info['code']
                    self.write(directory/'failed.json',{'error':label,'failure':info});self.status(sid,'uncertain',error=label,failure=info)
            self.thread=threading.Thread(target=run,name='gpu-ssh-bootstrap',daemon=True);self.thread.start()

    def close_tunnel(self):
        if self.tunnel and self.tunnel.poll() is None:
            self.tunnel.terminate()
            try:self.tunnel.wait(timeout=3)
            except subprocess.TimeoutExpired:self.tunnel.kill();self.tunnel.wait(timeout=3)
    def connected(self,sid):
        return bool(self.tunnel and getattr(self,'tunnel_sid',None)==sid and self.tunnel.poll() is None and
                    (self.directory(sid)/'deployed.json').is_file())
    def close(self):
        self.stopped.set();self.close_tunnel()
        if self.thread:self.thread.join(timeout=1)
