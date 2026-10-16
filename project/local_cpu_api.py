"""Local development HTTP binding; never grants unauthenticated paid controls."""
import threading
from types import SimpleNamespace

from inference.jobs import JobError


class LocalCPUAPI:
    controls={'/api/gpu/start','/api/gpu/entry-start','/api/gpu/stop','/api/gpu/confirm-host'}

    def __init__(self,simulation=False):
        # Load the SAME production adapter classes, without constructing provider,
        # credentials, cloud sessions, model executors, timers or subprocesses.
        from service import Application
        from nebius_provider import NebiusProvider
        from worker_link import HTTPSWorker
        from https_executor import HTTPSCosmosExecutor
        self.adapters=(NebiusProvider,HTTPSWorker,HTTPSCosmosExecutor)
        self.info_method=Application.gpu_entry_info
        self.view=SimpleNamespace(gpu_sessions=None,gpu_scope=None,entry_lock=threading.Lock(),entry_start=None)
        self.simulation=simulation
        from nebius_status import from_environment
        self.observer=from_environment() if not simulation else None

    def info(self):
        return {**self.info_method(self.view),**(self.observer.snapshot() if self.observer else {}),'mode':'local-development','adaptersLoaded':True,
                'protectionMode':'cpu-only','hostLossProtected':False}

    def connection_readiness(self):
        info=self.info()
        return {'providerConnected':info.get('providerConnected',False),'controlConfigured':False,
                'httpsWorkerDeployed':False,'residentModelConfigured':False,'residentModelImplemented':True,'canStart':False,'canGenerate':False,
                'blockers':['AUTHENTICATED_CONTROL_BINDING_REQUIRED','CURRENT_START_SCOPE_REQUIRED',
                            'GPU_HTTPS_DEPLOYMENT_REQUIRED','RESIDENT_MODEL_DEPLOYMENT_REQUIRED',
                            'CURRENT_HOST_ENROLLMENT_REQUIRED'],
                'realEndToEndVerified':False}

    def get(self,h,route):
        if route=='/api/health':
            h.json_response({'status':'ready','mode':'local-development','localCPUApi':True,
                'paidServices':bool(h.task_store.executor or h.recipe_language) and not self.simulation,
                'gpuControlConfigured':False,'modelAdapterConfigured':False,'adaptersLoaded':True})
        elif route=='/api/gpu/entry-status':h.json_response(self.info())
        elif route=='/api/gpu/connection-readiness':h.json_response(self.connection_readiness())
        elif route=='/api/gpu/status':
            h.json_response({'state':'UNKNOWN','configured':False,'providerState':None,
                'verifiedStopped':False,'simulation':False,'protectionMode':'cpu-only','hostLossProtected':False,
                **(self.observer.snapshot() if self.observer else {})})
        elif route=='/api/inference/capabilities':
            h.json_response({**h.task_store.capabilities(),'csrfToken':h.csrf_token})
        elif route in self.controls:
            h.job_error(JobError('METHOD_NOT_ALLOWED','启动与停止不能通过 GET 触发。',405))
        else:return False
        return True

    def post(self,h,route):
        if route not in self.controls:return False
        h.close_connection=True  # Refuse without parsing/retaining the untrusted body.
        if not h.valid_host() or not h.valid_origin() or h.headers.get('X-LightTry-Token')!=h.csrf_token:
            h.job_error(JobError('INVALID_ORIGIN','请从当前本机应用提交。',403))
        else:
            h.job_error(JobError('AUTHENTICATED_GPU_SERVICE_REQUIRED',
                '本地开发入口未连接远程 GPU；启停需要已配置且经过密钥认证的 CPU 服务。',503))
        return True
