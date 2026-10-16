"""Real Cosmos subprocess bridge. No CUDA/model import or execution at construction."""
import io
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tarfile
import threading
import time

from model_contract import grant_file,check_request,unpack_input,request_sha,MAX,verify_job_authorization
from security import runtime_file
from inference.jobs import atomic,read
from runtime.driver import BUNDLE_FILES

ROOT=Path(__file__).resolve().parent.parent


class CosmosWorkerExecutor:
    simulation=False
    execution_mode='per-job'
    model_loaded=False
    def task_progress(self,envelope):
        from gpu_monitoring import execution_progress
        return execution_progress(self.ledger.root,envelope)

    def task_failure(self,envelope):
        from inference.jobs import ID
        from gpu_monitoring import small_json,clean_failure
        job=envelope.get('jobId')
        if not isinstance(job,str) or not ID.fullmatch(job):return None
        try:
            prep=self.ledger.root/'executions'/job
            request=small_json(prep/'request.json')
            event=small_json(prep/'run/execution.json')
            if (request_sha(request)!=envelope.get('requestSha256') or
                request.get('taskId')!=job or
                (event.get('taskId'),event.get('nonce'),event.get('status'),event.get('executionStopped'))!=
                (job,request.get('nonce'),'failed',True)):return None
            return clean_failure(event.get('diagnostic'),event.get('stage'))
        except (OSError,ValueError,TypeError,KeyError):return None

    def __init__(self,ledger,config_file):
        value=json.loads(runtime_file(config_file,ROOT).decode('utf-8'))
        required={'schemaVersion','enabled','python','repo','checkpointDir','cudaHome','grantFile'}
        if not isinstance(value,dict) or set(value)-required-{'executionMode'} or not required<=set(value) or value['schemaVersion']!=1 or value['enabled'] is not True:
            raise ValueError('EXPLICIT_GPU_EXECUTOR_ENABLE_REQUIRED')
        for name in ('python','repo','checkpointDir','cudaHome'):
            p=Path(value[name])
            if not p.is_absolute() or not p.exists() or any(x.is_symlink() for x in (p,*p.parents)):
                raise ValueError('EXPLICIT_EXISTING_GPU_RUNTIME_PATH_REQUIRED')
        self.ledger,self.config=ledger,value
        if value.get('executionMode','per-job') not in ('resident','per-job'):raise ValueError('UNKNOWN_MODEL_EXECUTION_MODE')
        self.child=None;self.stopped=threading.Event();self.thread=None
        grant=self.grant()  # Only private local files, no probes/install/model load.
        ledger.max_jobs=grant['maxJobs'];ledger.host_identity=grant['hostIdentity']

    def grant(self):return grant_file(self.config['grantFile'],self.ledger.session_id,self.ledger.resource_id)

    def authorize(self,envelope):
        grant=self.grant();request,files=unpack_input(self.ledger.blob(envelope['artifactSha256']))
        if request['taskId']!=envelope['jobId'] or request_sha(request)!=envelope['requestSha256']:
            raise ValueError('MODEL_ENVELOPE_REQUEST_MISMATCH')
        check_request(request,grant)
        if grant.get('schemaVersion')==2:
            try:authorization=json.loads(files.get('authorization.json',b'null'))
            except (ValueError,UnicodeError):raise ValueError('SIGNED_JOB_AUTHORIZATION_REQUIRED')
            verify_job_authorization(request,grant,authorization)
        elif 'authorization.json' in files:raise ValueError('UNEXPECTED_JOB_AUTHORIZATION')
        self.ledger.max_jobs=grant['maxJobs']
        return grant

    def prepare(self,envelope):
        grant=self.authorize(envelope)
        request,files=unpack_input(self.ledger.blob(envelope['artifactSha256']))
        jobs=self.ledger.root/'executions'
        if jobs.is_symlink():raise ValueError('EXECUTION_ROOT_UNSAFE')
        jobs.mkdir(exist_ok=True,mode=0o700)
        prep=jobs/envelope['jobId'];prep.mkdir(mode=0o700)  # Never resume/relaunch a prior attempt.
        for rel in BUNDLE_FILES:
            source=ROOT/rel
            if any(p.is_symlink() for p in (source,*source.parents)):raise ValueError('TRUSTED_CODE_SYMLINK_FORBIDDEN')
            target=prep/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
        for rel,raw in files.items():
            target=prep/rel;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
        from datetime import datetime,timezone
        deadline=datetime.fromtimestamp(grant['expiresAt'],timezone.utc).isoformat()
        runtime={'repo':self.config['repo'],'checkpoint_dir':self.config['checkpointDir'],'cuda_home':self.config['cudaHome'],
                 'deadline_utc':deadline,'model_license_ack':True,'weights_mode':'full'}
        budget={'offline':False,'single_run':True,'approval_reference':grant['approvalReference'],
                'budget_usd_including_tax':grant['budgetUsdIncludingTax'],'deadline_utc':deadline}
        atomic(prep/'runtime.json',runtime);atomic(prep/'guard-receipt.json',budget)
        return prep,grant['expiresAt']

    def terminate_child(self):
        child=self.child
        if child is None or child.poll() is not None:return
        # Let the reviewed worker interrupt run_bounded and clean its own model
        # process groups. A forced parent exit is uncertainty, never proof of stop.
        try:
            if os.name=='posix':os.killpg(child.pid,signal.SIGINT)
            else:child.terminate()
        except ProcessLookupError:
            child.wait(timeout=3);return
        try:child.wait(timeout=8)
        except subprocess.TimeoutExpired:
            try:
                if os.name=='posix':os.killpg(child.pid,signal.SIGKILL)
                else:child.kill()
            except ProcessLookupError:pass
            child.wait(timeout=3)

    def launch(self,prep,deadline):
        if os.name!='posix' or self.stopped.is_set() or time.time()>=deadline:
            raise ValueError('LIVE_LINUX_GPU_EXECUTION_WINDOW_REQUIRED')
        env=os.environ.copy();env.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',PYTHONDONTWRITEBYTECODE='1')
        with (prep/'executor.log').open('xb') as log:
            self.child=subprocess.Popen([self.config['python'],'-u','-B',str(prep/'project/runtime/worker.py'),
                '--request',str(prep/'request.json'),'--runtime',str(prep/'runtime.json'),
                '--receipt',str(prep/'guard-receipt.json')],cwd=prep,env=env,
                stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,shell=False,start_new_session=True)
            # Cleanup grace is NOT a compute extension: worker commands still use
            # the original absolute deadline; their timeout cleanup gets to run.
            try:return self.child.wait(timeout=max(.001,deadline-time.time())+7)
            except BaseException:
                self.terminate_child();raise

    def __call__(self,envelope):
        prep,deadline=self.prepare(envelope)
        code=self.launch(prep,deadline)
        event=read(prep/'run/execution.json')
        request=read(prep/'request.json')
        if (event.get('taskId'),event.get('nonce'))!=(request['taskId'],request['nonce']) or event.get('executionStopped') is not True:
            raise ValueError('MODEL_EXECUTION_UNCERTAIN')
        if code or event.get('status')!='succeeded':return 'failed'
        if time.time()>deadline:raise ValueError('MODEL_COMPLETED_OUTSIDE_WINDOW')
        buffer=io.BytesIO();total=0;count=0
        with tarfile.open(fileobj=buffer,mode='w:gz') as archive:
            for path in sorted((prep/'run').rglob('*')):
                if path.is_symlink():raise ValueError('MODEL_RESULT_SYMLINK_FORBIDDEN')
                if not path.is_file() or path.suffix not in ('.json','.jpg','.jsonl','.log','.txt'):continue
                total+=path.stat().st_size;count+=1
                if total>2*MAX or path.stat().st_size>MAX or count>1024:raise ValueError('MODEL_RESULT_TOO_LARGE')
                archive.add(path,arcname=path.relative_to(prep/'run').as_posix(),recursive=False)
        raw=buffer.getvalue()
        if len(raw)>MAX:raise ValueError('MODEL_RESULT_TOO_LARGE')
        import hashlib
        sha=hashlib.sha256(raw).hexdigest();self.ledger.upload(sha,raw)
        return {'status':'succeeded','resultSha256':sha}

    def start(self):
        def run():
            while not self.stopped.is_set():
                try:
                    g=self.grant();self.ledger.max_jobs=g['maxJobs'];self.ledger.host_identity=g['hostIdentity']
                    # A valid grant is not evidence of a loaded model. This
                    # legacy subprocess executor is deliberately NOT advertised
                    # as resident/ready for the one-click startup workflow.
                    self.ledger.model_state='cold'
                except Exception:self.ledger.model_state='loading'
                self.stopped.wait(.5)
        self.thread=threading.Thread(target=run,name='cosmos-worker-dispatch',daemon=True);self.thread.start()

    def close(self):
        self.stopped.set();self.terminate_child()
        if self.thread:
            self.thread.join(timeout=8)
            if self.thread.is_alive():raise RuntimeError('GPU_EXECUTOR_NOT_STOPPED')
