"""Same-CPU readiness gate, NOT protection against loss of the CPU host."""
import json
import importlib
import math
import os
from pathlib import Path
import tempfile
import time
import re

from security import runtime_file

ROOT=Path(__file__).resolve().parent.parent


def build_sessions(root,binding):
    """Audited provider plug-in + existing HTTPS worker; construction is offline."""
    from gpu_session import Sessions
    from worker_link import HTTPSWorker
    if (not isinstance(binding,dict) or set(binding)-{'providerFactory','providerBinding','workerOrigin','workerTokenFile','workerCaFile','workerCertificateSha256'} or
            not {'providerFactory','providerBinding','workerOrigin','workerTokenFile','workerCaFile'}<=set(binding) or
            not isinstance(binding['providerFactory'],str) or
            not re.fullmatch(r'[a-zA-Z_][a-zA-Z0-9_.]*:[a-zA-Z_][a-zA-Z0-9_]*',binding['providerFactory']) or
            not isinstance(binding['providerBinding'],dict)):
        raise ValueError('EXPLICIT_PROVIDER_AND_WORKER_BINDING_REQUIRED')
    token=runtime_file(binding['workerTokenFile'],ROOT,4096).decode('utf-8').strip()
    ca=binding['workerCaFile']
    if ca is not None:runtime_file(ca,ROOT,65536)
    pin=binding.get('workerCertificateSha256')
    if binding['providerFactory']=='nebius_provider:build' and pin is None:
        raise ValueError('NEBIUS_WORKER_CERTIFICATE_PIN_REQUIRED')
    worker=HTTPSWorker(binding['workerOrigin'],token,ca_file=ca,timeout=5,certificate_sha256=pin)
    module,symbol=binding['providerFactory'].split(':')
    provider=getattr(importlib.import_module(module),symbol)(binding['providerBinding'])
    if any(not callable(getattr(provider,n,None)) for n in ('preflight','observe','start','stop')):
        raise ValueError('BOUNDED_PROVIDER_INTERFACE_REQUIRED')
    if hasattr(provider,'root') and provider.root.resolve()!=Path(root).resolve():
        raise ValueError('NEBIUS_PROVIDER_GUARD_ROOT_MISMATCH')
    # load_control installs the local readiness gate only after explicit CPU policy.
    return Sessions(root,provider,worker,None,protection_mode='cpu-only')


class CPUHostSupervisor:
    simulation=False
    protection_mode='cpu-only'

    def __init__(self, root, resource, *, risk_accepted=False, clock=time.time):
        self.root=Path(root)
        if (risk_accepted is not True or not self.root.is_absolute() or
                self.root.resolve().is_relative_to(ROOT) or
                any(p.is_symlink() for p in (self.root,*self.root.parents)) or
                not isinstance(resource,str) or not resource):
            raise ValueError('EXPLICIT_CPU_HOST_RISK_AND_PRIVATE_BINDING_REQUIRED')
        self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.resource,self.clock=resource,clock
        self.path=self.root/'cpu-guard-ready.json'
        self.lock=None

    def acquire(self):
        if self.lock is not None:raise ValueError('GUARD_ALREADY_ACQUIRED')
        p=self.root/'cpu-guard.lock'
        if p.is_symlink():raise ValueError('GUARD_LOCK_SYMLINK_FORBIDDEN')
        handle=p.open('a+b');handle.write(b'0');handle.flush();handle.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            handle.close();raise ValueError('CPU_GUARD_ALREADY_RUNNING') from None
        self.lock=handle

    def publish(self, observation=None):
        if self.lock is None:raise ValueError('GUARD_LOCK_REQUIRED')
        if self.path.is_symlink():raise ValueError('GUARD_RECEIPT_SYMLINK_FORBIDDEN')
        if isinstance(observation,dict):
            # Never persist raw provider payloads, tokens, IPs or arbitrary fields.
            observation={'resourceId':observation.get('resourceId'),'state':observation.get('state'),
                         'independent':observation.get('independent') is True,
                         'simulation':observation.get('simulation') is True,
                         'instances':[] if observation.get('instances')==[] else ['non-empty-or-unknown']}
        value={'mode':'cpu-only','independentHost':False,'resourceId':self.resource,
               'guardRoot':str(self.root.resolve()),'pid':os.getpid(),'at':self.clock(),
               'observation':observation}
        fd,name=tempfile.mkstemp(prefix='.guard-ready-',dir=self.root)
        try:
            with os.fdopen(fd,'w',encoding='utf-8') as f:
                json.dump(value,f);f.flush();os.fsync(f.fileno())
            os.replace(name,self.path)
        finally:
            if os.path.exists(name):os.unlink(name)

    def receipt(self):
        value=json.loads(runtime_file(self.path,ROOT,16384).decode('utf-8'))
        stamp=value.get('at')
        if (value.get('mode')!='cpu-only' or value.get('independentHost') is not False or
                value.get('resourceId')!=self.resource or value.get('guardRoot')!=str(self.root.resolve()) or
                type(stamp) not in (int,float) or not math.isfinite(stamp) or not 0<=self.clock()-stamp<=15 or
                not self.process_alive(value.get('pid'))):
            raise ValueError('CPU_GUARD_NOT_READY')
        return value

    @staticmethod
    def process_alive(pid):
        if type(pid) is not int or pid<=0:return False
        try:
            if os.name=='nt':
                import ctypes
                k=ctypes.WinDLL('kernel32',use_last_error=True)
                k.OpenProcess.restype=ctypes.c_void_p
                k.GetExitCodeProcess.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_ulong)]
                k.CloseHandle.argtypes=[ctypes.c_void_p]
                handle=k.OpenProcess(0x1000,False,pid)
                if not handle:return False
                try:
                    code=ctypes.c_ulong()
                    return bool(k.GetExitCodeProcess(handle,ctypes.byref(code))) and code.value==259
                finally:k.CloseHandle(handle)
            os.kill(pid,0);return True
        except (OSError,ValueError):return False

    def arm(self,sid,resource,deadline,lease_seconds):
        self.receipt()
        if resource!=self.resource:raise ValueError('GUARD_RESOURCE_MISMATCH')
        return {'sessionId':sid,'resourceId':resource,'deadline':deadline,'leaseSeconds':lease_seconds,
                'independentHost':False,'protectionMode':'cpu-only','cpuHostRiskAccepted':True,
                'ready':True,'simulation':False}

    def heartbeat(self,sid,resource,now):
        # Sessions already persisted CPU liveness. No third-host lease exists.
        if resource!=self.resource:raise ValueError('GUARD_RESOURCE_MISMATCH')

    def snapshot(self):
        try:
            receipt=self.receipt();value=receipt['observation']
            if not isinstance(value,dict) or value.get('independent') is not True or value.get('resourceId')!=self.resource:
                raise ValueError('UNVERIFIED_RESOURCE')
            stopped=value.get('state')=='STOPPED' and value.get('instances')==[]
            return {'state':'STOPPED' if stopped else 'UNKNOWN','label':'停止' if stopped else '异常待核实',
                    'providerState':value.get('state'),'verifiedStopped':stopped,'instancesEmpty':stopped,
                    'resourceId':self.resource,'configured':True,'simulation':value.get('simulation') is True,
                    'lastObservedAt':receipt['at'],'protectionMode':'cpu-only','independentHost':False}
        except Exception:
            return {'state':'UNKNOWN','label':'异常待核实','verifiedStopped':False,
                    'resourceId':self.resource,'configured':True,'protectionMode':'cpu-only','independentHost':False}

    def close(self):
        if self.lock is not None:
            try:
                if not self.path.is_symlink():self.path.unlink(missing_ok=True)
            finally:self.lock.close();self.lock=None
