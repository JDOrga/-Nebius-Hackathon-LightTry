"""Explicit local WSL read-only Nebius observer. Never starts/stops a resource."""
import json
import os
from pathlib import Path
import subprocess
import threading
import time


class NebiusStatus:
    def __init__(self, settings, runner=subprocess.run, clock=time.time):
        self.settings=Path(settings).resolve(strict=True)
        self.config=json.loads(self.settings.read_text(encoding='utf-8-sig'))
        self.runner,self.clock=runner,clock
        self.lock=threading.Lock()
        self.value=None
        self.error=None
        self.stopped=threading.Event();self.thread=None

    def refresh(self):
        def wsl_path(p):
            p=Path(p).resolve()
            if not p.drive or not str(p).startswith(p.drive+'\\'):
                raise ValueError('WINDOWS_DRIVE_REQUIRED')
            return '/mnt/'+p.drive[0].lower()+'/'+str(p)[3:].replace('\\','/')
        try:
            bridge=Path(__file__).resolve().parent.parent/'cloud/cli_bridge.py'
            p=self.runner(['wsl.exe','-d',self.config['wsl_distro'],'--','python3',
                wsl_path(bridge),'--settings',wsl_path(self.settings),'--action','status',
                '--execute','--timeout-seconds','25'],capture_output=True,text=True,
                encoding='utf-8',timeout=30,shell=False)
            if p.returncode:raise ValueError('NEBIUS_STATUS_READ_FAILED')
            v=json.loads(p.stdout)
            if (v.get('id')!=self.config['devlab_id'] or
                v.get('project_id')!=self.config['project_id'] or
                v.get('tenant_id')!=self.config['tenant_id'] or
                v.get('project_ownership_verified') is not True or
                not isinstance(v.get('instances'),list) or
                v.get('state') not in {'STOPPED','RUNNING','STARTING','PROVISIONING','IMAGE_PULLING','STOPPING'}):
                raise ValueError('NEBIUS_STATUS_IDENTITY_UNVERIFIED')
            safe={'providerState':v['state'],'resourceId':v['id'],
                  'verifiedStopped':v['state']=='STOPPED' and v['instances']==[],
                  'observedAt':self.clock()}
            with self.lock:self.value,self.error=safe,None
        except Exception:
            # Never retain credentials, raw CLI stderr, browser URLs or responses.
            with self.lock:self.error='NEBIUS_STATUS_UNAVAILABLE'

    def snapshot(self):
        with self.lock:v=dict(self.value or {});error=self.error
        fresh=bool(v) and not error and 0<=self.clock()-v['observedAt']<=90
        provider=v.get('providerState') if fresh else None
        state={'STOPPED':'STOPPED','RUNNING':'LOADING','STOPPING':'STOPPING',
               'STARTING':'STARTING','PROVISIONING':'STARTING','IMAGE_PULLING':'STARTING'}.get(provider,'UNKNOWN')
        return {**v,'providerState':provider,'state':state,'providerConnected':fresh,
                'configured':False,'canStart':False,'active':False,'stale':not fresh,
                'verifiedStopped':bool(fresh and v.get('verifiedStopped')),
                'simulation':False,'controlConfigured':False,'workerConnected':False,
                'message':'已连接 Nebius 状态服务；尚未启用远程启动和模型服务。' if fresh else
                          'Nebius 状态暂不可用，请检查本机认证与网络。'}

    def start(self):
        if self.thread is not None:return
        def run():
            while not self.stopped.is_set():
                self.refresh()
                self.stopped.wait(60)
        self.thread=threading.Thread(target=run,name='nebius-read-only-status',daemon=True);self.thread.start()

    def close(self):
        self.stopped.set()
        if self.thread:self.thread.join(timeout=1)


def from_environment():
    path=os.environ.get('LIGHTTRY_NEBIUS_STATUS_SETTINGS')
    if not path:return None
    observer=NebiusStatus(path)
    observer.start()
    return observer
