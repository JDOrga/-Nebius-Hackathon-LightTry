"""Explicit GPU worker lifecycle for two resident model phases; no automatic reboot."""
import os
from pathlib import Path
import signal
import subprocess
import threading
import time

from gpu_model import CosmosWorkerExecutor,ROOT
from inference.jobs import atomic,read
from gpu_monitoring import phase_loading,clean_loading
from model_contract import unpack_input


class ResidentCosmosExecutor(CosmosWorkerExecutor):
    execution_mode='resident'

    def __init__(self,ledger,config_file):
        super().__init__(ledger,config_file)
        if self.config.get('executionMode')!='resident':raise ValueError('EXPLICIT_RESIDENT_ENABLE_REQUIRED')
        self.config_file=Path(config_file).resolve()
        self.phases={};self.phase_logs=[];self.boot_sent=False

    @property
    def loading_progress(self):
        try:
            if not self.boot_sent or self.grant()!=self.boot_grant:return None
            return clean_loading({'version':1,'phases':[
                phase_loading(self.ledger.root,phase,child.pid,self.ledger.session_id,
                              self.ledger.resource_id,child.poll() is None)
                for phase,child in tuple(self.phases.items())]})
        except Exception:return None  # telemetry cannot break health/readiness or reload anything

    @property
    def model_loaded(self):
        if not self.boot_sent or len(self.phases)!=2:return False
        try:
            grant=self.grant()
            if grant!=self.boot_grant:return False
            for phase,child in self.phases.items():
                if child.poll() is not None:return False
                state=read(self.ledger.root/'resident'/phase/'state.json')
                if (state.get('pid')!=child.pid or state.get('sessionId')!=self.ledger.session_id or
                    state.get('resourceId')!=self.ledger.resource_id or state.get('phase')!=phase or
                    state.get('modelLoaded') is not True or state.get('state') not in ('ready','busy')):
                    return False
            return time.time()<grant['expiresAt']
        except Exception:return False

    def boot(self):
        if self.boot_sent:raise ValueError('RESIDENT_BOOT_ALREADY_ATTEMPTED')
        if os.name!='posix' or self.stopped.is_set():raise ValueError('LIVE_LINUX_GPU_EXECUTION_WINDOW_REQUIRED')
        self.boot_grant=self.grant()
        root=self.ledger.root/'resident';root.mkdir(mode=0o700,exist_ok=True)
        if root.is_symlink():raise ValueError('PRIVATE_RESIDENT_ROOT_REQUIRED')
        with (root/'boot-attempt').open('x'):pass
        self.boot_sent=True
        env=os.environ.copy();env.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',PYTHONDONTWRITEBYTECODE='1')
        for phase in ('inverse','forward'):
            log=(root/(phase+'.log')).open('xb');self.phase_logs.append(log)
            self.phases[phase]=subprocess.Popen([self.config['python'],'-u','-B',str(ROOT/'start.py'),
                '--model-phase',phase,'--worker-config',str(self.config_file),'--data-root',str(self.ledger.root),
                '--session-id',self.ledger.session_id,'--resource-id',self.ledger.resource_id],
                stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,env=env,
                shell=False,start_new_session=True)

    def prepare(self,envelope):
        if not self.model_loaded:raise ValueError('RESIDENT_MODEL_NOT_READY')
        prep,deadline=super().prepare(envelope)
        runtime=read(prep/'runtime.json')
        atomic(prep/'runtime.json',{**runtime,'executionMode':'resident','phaseRuntimeRoot':str(self.ledger.root/'resident')})
        return prep,deadline

    def authorize(self,envelope):
        grant=super().authorize(envelope)
        request,_=unpack_input(self.ledger.blob(envelope['artifactSha256']))
        if request['runConfig'].get('modelExecutionMode')!='resident-v1':
            raise ValueError('EXPLICIT_RESIDENT_REQUEST_REQUIRED')
        return grant

    def stop_phases(self):
        for child in self.phases.values():
            if child.poll() is None:
                try:os.killpg(child.pid,signal.SIGTERM)
                except ProcessLookupError:pass
        for child in self.phases.values():
            try:child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:os.killpg(child.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                child.wait(timeout=3)
        for log in self.phase_logs:log.close()

    def start(self):
        def run():
            self.ledger.model_state='loading'
            try:
                self.boot()
                while not self.stopped.is_set():
                    g=self.grant()
                    if g!=self.boot_grant:raise ValueError('RESIDENT_GRANT_CHANGED')
                    self.ledger.max_jobs=g['maxJobs']
                    if any(child.poll() is not None for child in self.phases.values()):raise OSError('RESIDENT_PROCESS_EXITED')
                    self.ledger.model_state='ready' if self.model_loaded else 'loading'
                    if self.model_loaded:self.ledger.run_one()
                    self.stopped.wait(.2)
            except Exception:self.ledger.model_state='failed'
            finally:self.stop_phases();self.ledger.model_state='failed'
        if self.thread is not None:raise ValueError('RESIDENT_BOOT_ALREADY_ATTEMPTED')
        self.thread=threading.Thread(target=run,name='resident-cosmos-dispatch',daemon=True);self.thread.start()

    def close(self):
        self.stopped.set();self.terminate_child()
        if self.thread:
            self.thread.join(timeout=18)
            if self.thread.is_alive():raise RuntimeError('GPU_EXECUTOR_NOT_STOPPED')
        else:self.stop_phases()
