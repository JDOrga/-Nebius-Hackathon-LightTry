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
    if not isinstance(value,dict) or set(value)-required-{'startPolicyFile'} or not required<=set(value) or value['schemaVersion']!=1:
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
        gpu_control_config=value['gpuControlConfig'],model_grant_file=value['modelGrantFile'])


class LocalApplication(Application):
    def __init__(self,opts):
        self.observer=None
        super().__init__(opts)
        if 'lighttry' not in self.accounts.users:
            super().close();raise ValueError('LOCAL_LEGACY_OWNER_REQUIRED')
        self.operator_recipe_language=None
        # Explicit, bounded server-only text scope; never inferred from a key alone.
        text_config=os.environ.get('LIGHTTRY_RECIPE_LANGUAGE_CONFIG_FILE')
        if text_config:
            try:
                from recipe_language import RecipeLanguage
                from studio import measured_context
                cfg=json.loads(runtime_file(text_config,ROOT).decode('utf-8'))
                legacy=set(cfg)=={'schemaVersion','ledgerFile','maxCalls','budgetUsd'} and cfg['schemaVersion']==1
                tiered=set(cfg)=={'schemaVersion','user','operator'} and cfg['schemaVersion']==2
                if not (legacy or tiered):raise ValueError('EXPLICIT_LOCAL_TEXT_SCOPE_REQUIRED')
                key=self.provider_secrets.get('nemotron').lstrip('\ufeff')
                if not key.isascii() or not 20<=len(key)<=4096 or any(c.isspace() for c in key):
                    raise ValueError('KEY_FILE_FORMAT_INVALID_NO_REQUEST')
                def private_ledger(raw):
                    ledger=Path(raw)
                    if (not ledger.is_absolute() or ledger.resolve().is_relative_to(ROOT.resolve())
                            or any(p.is_symlink() for p in (ledger,*ledger.parents))):
                        raise ValueError('PRIVATE_TEXT_LEDGER_REQUIRED')
                    return ledger
                measured=measured_context(self.handler.studies)
                if legacy:
                    self.handler.recipe_language=RecipeLanguage(self.handler.catalog['presets'],
                        self.handler.lighting_capabilities,key,private_ledger(cfg['ledgerFile']),
                        max_calls=cfg['maxCalls'],budget=cfg['budgetUsd'],repair_limit=0,measured_cases=measured)
                    self.handler.task_store.approved_language_operation=self.handler.recipe_language.approved_operation
                else:
                    user,operator=cfg['user'],cfg['operator']
                    if ((user is not None and (not isinstance(user,dict) or set(user)!={'ledgerFile','maxCalls','budgetUsd'})) or
                            not isinstance(operator,dict) or set(operator)!={'ledgerFile','unbounded','operatorAcceptsUnboundedCost'} or
                            operator['unbounded'] is not True or operator['operatorAcceptsUnboundedCost'] is not True):
                        raise ValueError('EXPLICIT_ROLE_TEXT_POLICY_REQUIRED')
                    operator_ledger=private_ledger(operator['ledgerFile'])
                    user_ledger=private_ledger(user['ledgerFile']) if user is not None else None
                    if user_ledger is not None and user_ledger.resolve()==operator_ledger.resolve():raise ValueError('ROLE_TEXT_LEDGERS_MUST_DIFFER')
                    self.handler.recipe_language=(RecipeLanguage(self.handler.catalog['presets'],
                        self.handler.lighting_capabilities,key,user_ledger,max_calls=user['maxCalls'],
                        budget=user['budgetUsd'],repair_limit=0,measured_cases=measured,ledger_scope='user')
                        if user is not None else None)
                    self.operator_recipe_language=RecipeLanguage(self.handler.catalog['presets'],
                        self.handler.lighting_capabilities,key,operator_ledger,max_calls=None,budget=None,
                        repair_limit=0,measured_cases=measured,unbounded=True,ledger_scope='operator')
                    from language import LanguageError
                    def verify_operation(operation_id,input_id,parameters):
                        for language in (self.handler.recipe_language,self.operator_recipe_language):
                            if language is None:continue
                            try:return language.approved_operation(operation_id,input_id,parameters)
                            except LanguageError as error:
                                if error.code!='INVALID_LANGUAGE_PROVENANCE':raise
                        raise LanguageError('INVALID_LANGUAGE_PROVENANCE','该建议未被正式服务接受。',422)
                    self.handler.task_store.approved_language_operation=verify_operation
            except Exception:
                super().close()
                raise
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

    def language_for(self, owner):
        if self.is_operator(owner) and self.operator_recipe_language is not None:
            return self.operator_recipe_language
        return self.handler.recipe_language

    def start_background(self):
        self.queue.start()
        if self.gpu_control:self.gpu_control.start_heartbeat()
        if self.model_executor:self.model_executor.start()
        if self.observer:self.observer.start()

    def gpu_entry_info(self,owner=None):
        info=super().gpu_entry_info(owner)
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
