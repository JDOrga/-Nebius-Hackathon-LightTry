"""Authenticated loopback profile of the SAME production service, not a second API."""
import json
import os
from pathlib import Path
import signal
import math
from types import SimpleNamespace
from urllib.parse import urlsplit

from service import Application,ROOT
from security import runtime_file
from nebius_status import NebiusStatus


def options(paths):
    value=json.loads(runtime_file(paths['local_cpu_config'],ROOT).decode('utf-8'))
    required={'schemaVersion','publicOrigin','accountsFile','dataRoot','statusSettingsFile','gpuControlConfig','modelGrantFile'}
    if not isinstance(value,dict) or set(value)-required-{'startPolicyFile','sessionScopedAccounts'} or not required<=set(value) or value['schemaVersion']!=1:
        raise ValueError('EXPLICIT_PRIVATE_LOCAL_CPU_PROFILE_REQUIRED')
    origin=urlsplit(value['publicOrigin'])
    if (origin.scheme!='http' or origin.hostname!='127.0.0.1' or not origin.port or
        not 1024<=origin.port<=65535 or origin.username or origin.password or origin.path or origin.query or origin.fragment):
        raise ValueError('EXACT_LOOPBACK_HTTP_ORIGIN_REQUIRED')
    if os.environ.get('LIGHTTRY_LEGACY_OWNER','lighttry')!='lighttry':raise ValueError('LOCAL_WORKSPACE_OWNER_MISMATCH')
    # Explicit null is OFF; do not inherit unrelated paid environment defaults.
    return SimpleNamespace(public_origin=value['publicOrigin'],accounts_file=value['accountsFile'],
        data_root=value['dataRoot'],assets_dir=paths['assets_dir'],evidence_config=Path(paths['evidence_config']) if paths.get('evidence_config') else None,
        accepted_package=[Path(p) for p in paths['accepted_packages']],local_task_root=Path(paths['tasks_dir']),
        local_loopback=True,status_settings_file=value['statusSettingsFile'],start_policy_file=value.get('startPolicyFile'),
        gpu_control_config=value['gpuControlConfig'],model_grant_file=value['modelGrantFile'],
        language_config=paths.get('language_config'),session_scoped_accounts=value.get('sessionScopedAccounts',[]))


class LocalApplication(Application):
    def __init__(self,opts):
        self.observer=None
        if not getattr(opts,'language_config',None):
            opts.language_config=os.environ.get('LIGHTTRY_RECIPE_LANGUAGE_CONFIG_FILE')
        super().__init__(opts)
        if 'lighttry' not in self.accounts.users:
            super().close();raise ValueError('LOCAL_LEGACY_OWNER_REQUIRED')
        self.start_policy=None
        if getattr(opts,'start_policy_file',None):
            policy=json.loads(runtime_file(opts.start_policy_file,ROOT).decode())
            budget=policy.get('budgetUsdIncludingTax')
            if (policy.get('schemaVersion')!=1 or policy.get('approvalMode')!='per-click' or
                type(budget) not in (int,float) or not math.isfinite(budget) or not 0<budget<=1000 or
                policy.get('scopeCreated') is not False):
                super().close();raise ValueError('EXPLICIT_PER_CLICK_BUDGET_PREFERENCE_REQUIRED')
            self.start_policy=policy
        # Paid guard owns observations if configured. Never run two cloud observers.
        if not self.gpu_control and opts.status_settings_file:
            self.observer=NebiusStatus(opts.status_settings_file)

    def language_for(self, owner, owner_scope=None):
        if self.is_operator(owner) and self.operator_recipe_language is not None:
            return self.operator_recipe_language
        return self.handler.recipe_language

    def start_background(self):
        self.queue.start()
        if self.gpu_control:self.gpu_control.start_heartbeat()
        if self.model_executor:self.model_executor.start()
        if self.observer:self.observer.start()

    def gpu_entry_info(self,owner=None,owner_scope=None):
        info=super().gpu_entry_info(owner,owner_scope)
        if self.observer and not self.gpu_control:info.update(self.observer.snapshot())
        if self.start_policy:info.update(budgetUsdIncludingTax=self.start_policy['budgetUsdIncludingTax'],budgetHardCap=False)
        if not self.gpu_control:info['message']='GPU控制当前未启用（维护中），不能从网页启动；这不代表已确认GPU停机。文字对话与本地编辑仍可使用。'
        return {**info,'mode':'local-authenticated'}

    def private_route(self,h):
        from urllib.parse import urlsplit
        route=urlsplit(h.path).path
        if h.command=='GET' and route=='/api/me':
            h.json_response({'username':h.user,'role':self.accounts.users[h.user]['role'],
                             'localWorkspace':True})
        elif h.command=='GET' and route=='/api/health':
            h.json_response({'status':'ready','mode':'local-authenticated','localCPUApi':True,
                'authenticated':True,'paidServices':self.model_executor is not None,
                'gpuControlConfigured':self.gpu_control is not None,'modelAdapterConfigured':self.model_executor is not None})
        elif h.command=='GET' and route=='/api/inference/capabilities':
            h.json_response({**h.task_store.capabilities(),'csrfToken':h.csrf_token})
        elif h.command=='GET' and route=='/api/gpu/status' and not self.gpu_control:
            h.json_response(self.gpu_entry_info(h.user))
        elif h.command=='GET' and route=='/api/gpu/connection-readiness':
            info=self.gpu_entry_info(h.user);snapshot=self.gpu_sessions.latest() if self.gpu_sessions else {}
            ready=info['state']=='READY' and not info['stale']
            blockers=[]
            if not self.gpu_control:blockers+=['GPU_CONTROL_BINDING_REQUIRED','CURRENT_START_SCOPE_REQUIRED']
            if not ready:blockers+=['GPU_HTTPS_DEPLOYMENT_REQUIRED','RESIDENT_MODEL_DEPLOYMENT_REQUIRED']
            if not snapshot.get('hostConfirmed'):blockers+=['CURRENT_HOST_ENROLLMENT_REQUIRED']
            h.json_response({'authenticated':True,'providerConnected':info.get('providerConnected',bool(self.gpu_control)),
                'controlConfigured':bool(self.gpu_control),'httpsWorkerDeployed':ready,'residentModelImplemented':True,
                'residentModelConfigured':self.model_executor is not None,'canStart':info['canStart'],
                'canGenerate':bool(ready and self.model_executor),'budgetUsdIncludingTax':info.get('budgetUsdIncludingTax'),
                'budgetHardCap':False,'blockers':blockers,'realEndToEndVerified':False})
        else:return super().private_route(h)
        return True

    def close(self):
        if self.observer:self.observer.close()
        super().close()


def main(paths):
    opts=options(paths);os.umask(0o077)
    app=LocalApplication(opts)
    try:
        from waitress import serve
        def stop(*_):raise KeyboardInterrupt()
        signal.signal(signal.SIGTERM,stop)
        app.start_background()
        print('LightTry authenticated local CPU: '+app.origin+'; GPU mutations require explicit current control scope.',flush=True)
        serve(app,listen='127.0.0.1:'+str(urlsplit(app.origin).port),threads=16,connection_limit=64,
            max_request_header_size=16384,max_request_body_size=32*1024*1024,channel_timeout=30,
            channel_request_lookahead=1,expose_tracebacks=False,clear_untrusted_proxy_headers=True)
    finally:app.close()
