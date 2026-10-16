"""CPU product adapter: exact approval -> HTTPS worker -> existing result validators."""
import copy
import hashlib
import json
from pathlib import Path
import threading
import time

from model_contract import grant_file,check_request,pack_input,request_sha,validate_result_archive,job_authorization
from inference.jobs import atomic,read,ID
from inference.images import digest
from model_readiness import ready as model_ready
from runtime.driver import extract_result,extract_stage_evidence


class HTTPSCosmosExecutor:
    supports_lighting_parameters=True
    requires_gpu_ready=True
    def __init__(self,control,grant_path,tasks_root):
        self.control,self.grant_path,self.tasks_root=control,grant_path,Path(tasks_root)
        self.stop=threading.Event();self.thread=None

    def current(self):
        if getattr(self.control.sessions,'protection_mode',None)=='cpu-only':
            self.control.sessions.fallback.receipt()
        state=self.control.sessions.latest()
        if (state.get('scopeId')!=self.control.scope['scopeId'] or state.get('state')!='READY' or
                state.get('resourceId')!=self.control.scope['resourceId'] or not state.get('hostConfirmed') or
                type(state.get('lastObservedAt')) not in (int,float) or not 0<=time.time()-state['lastObservedAt']<=30):
            raise ValueError('CURRENT_CONFIRMED_READY_GPU_REQUIRED')
        grant=grant_file(self.grant_path,state['sessionId'],state['resourceId'])
        if (grant['hostIdentity']!=state.get('hostIdentity') or grant['expiresAt']>min(state['workDeadline'],state['absoluteDeadline'],self.control.scope['expiresAt'])):
            raise ValueError('MODEL_GRANT_HOST_OR_DEADLINE_MISMATCH')
        return state,grant

    def authorize_job(self,owner,metadata,fingerprint):
        try:
            _,g=self.current()
            if g.get('schemaVersion')==2:return owner==g['jobAuthorization']['owner']
            return {'owner':owner,'fingerprint':fingerprint} in g['allowedMetadata']
        except Exception:return False

    def check_ready(self):self.current()
    def run_config(self):return {'weightVerification':'full','weightContentHashesChecked':True,'lightingAdapterVersion':'single-scheme-hdr-adapter-v1','modelExecutionMode':'resident-v1'}

    def prepare_request(self,folder,request):
        _,grant=self.current();check_request(request,grant)
        p=request['preset']
        if p.get('derivedHdrSha256'):
            from light_console import EnvironmentLibrary
            library=EnvironmentLibrary(Path(folder).parent.parent/'environments-v2',[])
            data=library.derived(p['parameters'])
            if digest(data)!=p['derivedHdrSha256']:raise ValueError('DERIVED_HDR_IDENTITY_MISMATCH')
            target=Path(folder)/'inputs/lighting.hdr'
            if target.is_symlink() or (target.exists() and target.read_bytes()!=data):raise ValueError('DERIVED_HDR_CHANGED')
            target.write_bytes(data)

    def submit(self,folder,request):
        state,grant=self.current();check_request(request,grant)
        worker=self.control.sessions.worker
        health=worker.health()
        if (health.get('sessionId'),health.get('resourceId'),health.get('hostIdentity'))!=(state['sessionId'],state['resourceId'],state['hostIdentity']):
            raise ValueError('HTTPS_WORKER_CURRENT_HOST_MISMATCH')
        if not model_ready(health,state,simulation=grant.get('simulation',False)):
            raise ValueError('RESIDENT_MODEL_NOT_READY')
        authorization=job_authorization(request,grant) if grant.get('schemaVersion')==2 else None
        raw=pack_input(folder,request,authorization);sha=hashlib.sha256(raw).hexdigest()
        envelope={'jobId':request['taskId'],'sessionId':state['sessionId'],'resourceId':state['resourceId'],
                  'artifactSha256':sha,'requestSha256':request_sha(request)}
        binding=Path(folder)/'https-binding.json'
        # Durable marker before ANY upload/submit. Recovery only queries the original job.
        with binding.open('x',encoding='utf-8') as stream:json.dump({'envelope':envelope,'deadline':grant['expiresAt']},stream)
        uploaded=worker.upload(raw)
        if uploaded.get('sha256')!=sha or uploaded.get('bytes')!=len(raw):raise ValueError('HTTPS_UPLOAD_RECEIPT_MISMATCH')
        self.control.sessions.submit(state['sessionId'],envelope)

    def reconcile(self,folder):
        folder=Path(folder);binding=read(folder/'https-binding.json');envelope=binding['envelope'];request=read(folder/'request.json')
        if envelope['jobId']!=folder.name or envelope['requestSha256']!=request_sha(request):raise ValueError('HTTPS_BINDING_CHANGED')
        if (folder/'https-result-rejected.json').exists():return
        existing=folder/'execution.json'
        if existing.exists() and read(existing).get('status') in ('succeeded','failed'):return
        # This is the dedicated background transport loop, NEVER a page GET.
        remote=self.control.sessions.worker.query(envelope['jobId'])
        if any(remote.get(k)!=v for k,v in envelope.items()):return  # 404/missing ACK is not a retry grant.
        if remote.get('status')=='succeeded':
            if time.time()>binding['deadline']:return  # Never reverse an expired product task.
            raw=self.control.sessions.worker.download(remote['resultSha256'])
            archive=folder/'https-result.tar.gz'
            if archive.is_symlink() or (archive.exists() and archive.read_bytes()!=raw):raise ValueError('HTTPS_RESULT_CHANGED')
            archive.write_bytes(raw)
            try:
                validate_result_archive(raw)
                event=extract_result(archive,folder,require_gbuffers=True)
                extract_stage_evidence(archive,folder,request)
                if (event.get('taskId'),event.get('nonce'),event.get('status'),event.get('executionStopped'))!=(request['taskId'],request['nonce'],'succeeded',True):
                    raise ValueError('HTTPS_RESULT_IDENTITY_MISMATCH')
            except Exception:
                atomic(folder/'https-result-rejected.json',{'sha256':remote['resultSha256'],'error':'RESULT_VALIDATION_FAILED'})
                raise  # Retain the rejected immutable artifact; never re-download/re-run it automatically.
            atomic(folder/'execution.json',event)  # Existing TaskStore/SchemeStore still validates receipt + proof.
        elif remote.get('status')=='failed':
            atomic(existing,{'taskId':request['taskId'],'nonce':request['nonce'],'status':'failed','stage':'validating',
                             'executionStopped':True,'observedAt':time.time()})

    def confirmed_stopped(self,folder):
        try:
            value=self.control.sessions.latest();binding=read(Path(folder)/'https-binding.json')['envelope']
            return value.get('sessionId')==binding['sessionId'] and value.get('resourceId')==binding['resourceId'] and value.get('verifiedStopped') is True
        except Exception:return False

    def start(self):
        def run():
            while not self.stop.is_set():
                for folder in self.tasks_root.iterdir():
                    if self.stop.is_set():return
                    if not ID.fullmatch(folder.name) or folder.is_symlink() or not folder.is_dir() or not (folder/'https-binding.json').is_file():continue
                    try:self.reconcile(folder)
                    except Exception:pass  # Preserve uncertainty; never upload/start/POST here.
                self.stop.wait(2)
        self.thread=threading.Thread(target=run,name='https-model-reconcile',daemon=True);self.thread.start()

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=15)
            if self.thread.is_alive():raise RuntimeError('HTTPS_RECONCILER_NOT_STOPPED')
