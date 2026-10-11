"""Shared, durable authorization ledger for the frozen R2 acceptance only.

No key, payload, invalid response or reasoning is persisted. This module never
changes the frozen adapter/prompt/schema. Every CLI/browser wire call crosses
the same ledger. Windows file locking also serializes separate processes.
"""
import contextlib
import copy
import hashlib
import json
import os
import threading
import time
import uuid
from pathlib import Path

from language import LanguageAdapter, LanguageError
from freeze_language_candidate import snapshot, digest

RESERVE = (15000 * .06 + 40960 * .24) / 1000000
FEE_FACTOR = 1.10 / (76 * RESERVE)  # Tax/uncertainty envelope, not an asserted tax rate.
FATAL = {'LANGUAGE_AUTH', 'LANGUAGE_RATE_LIMIT', 'LANGUAGE_TIMEOUT', 'LANGUAGE_UPSTREAM',
         'LANGUAGE_OUTPUT_TRUNCATED', 'LANGUAGE_AUDIT_FAILED', 'INVALID_LANGUAGE_REQUEST',
         'ACCEPTANCE_MISSING_USAGE', 'ACCEPTANCE_BUDGET_STOP', 'ACCEPTANCE_CONFIG_DRIFT',
         'ACCEPTANCE_USAGE_EXCEEDS_RESERVE', 'ACCEPTANCE_UNPLANNED_OPERATION'}


def verify_candidate(manifest):
    current = snapshot()
    if current['candidateSHA256'] != manifest['candidateSHA256']:
        raise LanguageError('ACCEPTANCE_CONFIG_DRIFT', '冻结候选已改变，停止真实调用。')
    return current


def verify_adapter(adapter, manifest):
    cfg = manifest['config']
    actual = {'model':adapter.model, 'endpoint':adapter.endpoint, 'maxTokens':adapter.max_tokens,
              'thinking':adapter.thinking_mode, 'toolChoice':adapter.tool_selection,
              'outputMode':adapter.output_mode, 'timeoutSeconds':adapter.timeout,
              'maxRepairs':adapter.repair_attempts, 'operationBudgetUSD':adapter.operation_budget_usd}
    if any(actual[k] != cfg[k] for k in actual):
        raise LanguageError('ACCEPTANCE_CONFIG_DRIFT', '实际进程配置与 R2 不一致，未发送请求。')
    if not adapter.enabled:
        raise LanguageError('LANGUAGE_NOT_CONFIGURED', '当前终端没有完整文字配置；请在原私下配置 Key 的终端执行。')
    return actual


class BudgetLedger:
    def __init__(self, path, manifest, allowed, *, create=False, mode='real', harness_hashes=None):
        self.path, self.manifest, self.allowed = Path(path), manifest, dict(allowed)
        self.mutex = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path = self.path.with_suffix('.lock')
        with self.lock_path.open('ab') as lock:
            if not self.lock_path.stat().st_size:
                lock.write(b'0')
        if create:
            with self.transaction() as data:
                if data:
                    raise LanguageError('ACCEPTANCE_BUDGET_STOP', '已有验收账本，不覆盖或自动重跑。')
                data.update(runId=uuid.uuid4().hex, candidateId=manifest['candidateId'],
                    candidateSHA256=manifest['candidateSHA256'], evidenceMode=mode,
                    authorization={'newCalls':76,'taxInclusiveFeeCapUSD':1.10,'initialOperations':38,
                                   'repairsPerOperation':1,'scope':'Token Factory text only; GPU off; no photos',
                                   'authorizedBy':'WJX explicit message 2026-10-11' if mode=='real' else 'OFFLINE TEST ONLY'},
                    harnessSHA256=harness_hashes or {}, status='prepared', stopReason=None,
                    requestsReserved=0, operations={}, cases={}, cliExecutionCompleted=False,
                    browserArmed=False, price={'inputPerMillionUSD':.06,'outputPerMillionUSD':.24,
                        'perCallPretaxReserveUSD':RESERVE,'taxAndUncertaintyFactor':FEE_FACTOR,
                        'actualTaxVerified':False}, createdAtUnix=time.time())
        else:
            data = self.read()
            if data.get('candidateSHA256') != manifest['candidateSHA256']:
                raise LanguageError('ACCEPTANCE_CONFIG_DRIFT', '账本候选不一致。')

    @contextlib.contextmanager
    def transaction(self):
        with self.mutex, self.lock_path.open('r+b') as lock:
            if os.name == 'nt':
                import msvcrt
                lock.seek(0); msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                data = json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else {}
                yield data
                temporary = self.path.with_name(self.path.name + '.' + uuid.uuid4().hex + '.tmp')
                with temporary.open('w', encoding='utf-8') as output:
                    json.dump(data, output, ensure_ascii=False, indent=2)
                    output.flush(); os.fsync(output.fileno())
                os.replace(temporary, self.path)
            finally:
                if os.name == 'nt':
                    lock.seek(0); msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def read(self):
        with self.transaction() as data:
            result = copy.deepcopy(data)
        return result

    @staticmethod
    def committed_cost(data):
        return data.get('priorCommittedPretaxUSD', 0) + sum(call.get('reportedPretaxUSD', RESERVE) for op in data['operations'].values()
                   for call in op['calls'])

    def stop(self, reason):
        with self.transaction() as data:
            data['status'], data['stopReason'] = 'stopped', reason

    def begin(self, source, case_id):
        with self.transaction() as data:
            key = source + ':' + case_id
            if data['status'] == 'stopped':
                raise LanguageError('ACCEPTANCE_BUDGET_STOP', '验收已停止；不得自动恢复或换版本重跑。')
            if source not in self.allowed or case_id not in self.allowed[source] or key in data['operations']:
                raise LanguageError('ACCEPTANCE_UNPLANNED_OPERATION', '重复或未计划的推荐已阻止。')
            if source == 'browser' and not data['browserArmed']:
                raise LanguageError('ACCEPTANCE_BUDGET_STOP', 'CLI 和人工复核尚未结束，网页调用未开放。')
            held = sum(op['heldSlots'] for op in data['operations'].values())
            auth = data['authorization']
            if (data['requestsReserved'] + held + 2 > auth.get('cumulativeCallLimit', 76) or
                    data['requestsReserved'] - data.get('priorRequestsReserved', 0) + held + 2 > auth.get('runCallLimit', 76) or
                    (self.committed_cost(data) + (held+2)*RESERVE)*FEE_FACTOR > auth['taxInclusiveFeeCapUSD'] + 1e-10 or
                    (self.committed_cost(data) - data.get('priorCommittedPretaxUSD', 0) + (held+2)*RESERVE)*FEE_FACTOR > auth.get('runFeeCapUSD', 1.10) + 1e-10):
                raise LanguageError('ACCEPTANCE_BUDGET_STOP', '完整操作及一次修复不能容纳在授权预算内。')
            op_id = uuid.uuid4().hex
            data['operations'][key] = {'operationId':op_id,'source':source,'caseId':case_id,
                'heldSlots':2,'status':'started','calls':[],'startedAtUnix':time.time()}
            data['status'] = 'running'
        return key

    def before_send(self, key):
        with self.transaction() as data:
            op = data['operations'][key]
            auth = data['authorization']
            if (data['status'] == 'stopped' or op['heldSlots'] < 1 or len(op['calls']) >= 2 or
                    data['requestsReserved'] >= auth.get('cumulativeCallLimit', 76) or
                    data['requestsReserved'] - data.get('priorRequestsReserved', 0) >= auth.get('runCallLimit', 76)):
                raise LanguageError('ACCEPTANCE_BUDGET_STOP', '调用次数或停止条件已到边界。')
            op['heldSlots'] -= 1
            data['requestsReserved'] += 1
            call = {'number':len(op['calls'])+1,'isRepair':bool(op['calls']),
                    'sequence':data['requestsReserved'],'status':'reserved-before-send',
                    'billing':'unknown','pretaxReserveUSD':RESERVE,'startedAtUnix':time.time()}
            op['calls'].append(call)
            return len(op['calls'])-1

    def after_send(self, key, index, protocol, elapsed, error_code=None):
        missing = False
        exceeded = False
        with self.transaction() as data:
            call = data['operations'][key]['calls'][index]
            call.update(protocol=copy.deepcopy(protocol), upstreamElapsedSeconds=round(elapsed,3),
                        status='wire-returned' if error_code is None else 'wire-error', errorCode=error_code)
            usage = protocol.get('usage', {})
            known = all(type(usage.get(k)) is int and usage[k]>=0 for k in ('prompt_tokens','completion_tokens'))
            if known:
                call['billing']='usage-reported'
                call['reportedPretaxUSD']=(usage['prompt_tokens']*.06+usage['completion_tokens']*.24)/1000000
                exceeded = usage['prompt_tokens']>15000 or usage['completion_tokens']>40960
            else:
                missing=True
            if missing or exceeded or error_code in FATAL:
                data['status']='stopped'
                data['stopReason']=('ACCEPTANCE_MISSING_USAGE' if missing else
                                    'ACCEPTANCE_USAGE_EXCEEDS_RESERVE' if exceeded else error_code)
        if missing:
            raise LanguageError('ACCEPTANCE_MISSING_USAGE', '供应商 usage 未知，保留计费预留并停止。')
        if exceeded:
            raise LanguageError('ACCEPTANCE_USAGE_EXCEEDS_RESERVE', '实际 token 用量超出预留假设，停止调用。')

    def finish(self, key, item):
        with self.transaction() as data:
            op=data['operations'][key]
            op.update(heldSlots=0,status=item['status'],elapsedSeconds=item['elapsedSeconds'])
            op['adapterAudit']=item.get('operationAudit',{})
            data['cases'][key]=copy.deepcopy(item)
            failed=item['status']=='failed' or 'fail' in item.get('checks',{}).values()
            code=item.get('errorCode','CASE_CONSTRAINT_FAILURE' if failed else None)
            history=[r for r in data['cases'].values() if r.get('status')!='skipped-dependency-failed']
            prior_bad=len(history)>=2 and all(r['status']=='failed' or 'fail' in r.get('checks',{}).values() for r in history[-2:])
            protocol_limit=data.get('protocolFailureStopAfter',3)
            repeated_format=(len(history)>=protocol_limit and all(any(a.get('errorCode')=='INVALID_MODEL_OUTPUT'
                for a in r.get('operationAudit',{}).get('attempts',[])) for r in history[-protocol_limit:]))
            if code in FATAL or (prior_bad and data.get('stopOnConsecutiveFailure',True)) or repeated_format:
                data['status']='stopped'
                data['stopReason']=code if code in FATAL else 'SYSTEMATIC_ACCEPTANCE_FAILURE'

    def skip(self, source, case_id):
        with self.transaction() as data:
            data['cases'][source+':'+case_id]={'id':case_id,'source':source,'status':'skipped-dependency-failed'}


class AuthorizedAdapter(LanguageAdapter):
    """Meter an unchanged frozen adapter; preserve real wall deadline behavior."""
    def __init__(self, presets, ledger, source, manifest, *, key, audit_path, offline_transport=None):
        cfg=manifest['config']
        super().__init__(presets,enabled=True,key=key,model=cfg['model'],endpoint=cfg['endpoint'],
            timeout=cfg['timeoutSeconds'],max_tokens=cfg['maxTokens'],repair_attempts=cfg['maxRepairs'],
            output_mode=cfg['outputMode'],thinking_mode=cfg['thinking'],tool_selection=cfg['toolChoice'],
            operation_budget_usd=cfg['operationBudgetUSD'],audit_path=audit_path)
        self.ledger,self.source,self.manifest=ledger,source,manifest
        self.admission=threading.Lock()
        self.context=None
        self.original_transport=offline_transport or self.transport
        self.transport=self.counted

    def counted(self, payload, remaining):
        verify_candidate(self.manifest)
        expected_harness=self.ledger.read().get('harnessSHA256',{})
        repo=Path(__file__).resolve().parents[2]
        if any(hashlib.sha256((repo/path).read_bytes()).hexdigest()!=sha for path,sha in expected_harness.items()):
            self.ledger.stop('ACCEPTANCE_CONFIG_DRIFT')
            raise LanguageError('ACCEPTANCE_CONFIG_DRIFT','验收启动器发生变化，未发送请求。')
        cfg=self.manifest['config']
        if (payload.get('model')!=cfg['model'] or payload.get('max_tokens')!=40960 or
            payload.get('tool_choice')!='auto' or payload.get('parallel_tool_calls') is not False or
            payload.get('store') is not False or payload.get('chat_template_kwargs')!={'enable_thinking':True} or
            'temperature' in payload or len(payload.get('tools',[]))!=1 or
            digest(payload['tools'][0]['function']['parameters'])!=self.manifest['schemaSHA256'] or
            hashlib.sha256(payload['messages'][0]['content'].encode()).hexdigest()!=self.manifest['systemPromptSHA256']):
            self.ledger.stop('ACCEPTANCE_CONFIG_DRIFT')
            raise LanguageError('ACCEPTANCE_CONFIG_DRIFT','实际请求与冻结协议不一致，未发送。')
        key=self.context
        index=self.ledger.before_send(key)
        started=time.monotonic()
        error=None
        try:
            return self.original_transport(payload,remaining)
        except LanguageError as caught:
            error=caught.code
            raise
        except Exception:
            error='LANGUAGE_UPSTREAM'
            raise LanguageError(error,'上游请求失败，已停止。') from None
        finally:
            self.ledger.after_send(key,index,self.last_response_audit,time.monotonic()-started,error)

    def recommend_case(self, case, body):
        from acceptance_checks import dimensions,failure_dimensions
        if not self.admission.acquire(blocking=False):
            raise LanguageError('LANGUAGE_BUSY','正在执行本次推荐。',409)
        key=None
        try:
            verify_candidate(self.manifest)
            verify_adapter(self,self.manifest)
            key=self.ledger.begin(self.source,case['id'])
            self.context=key
            started=time.monotonic()
            item={'id':case['id'],'source':self.source,'status':'started','candidateId':self.manifest['candidateId']}
            plan=None
            try:
                plan=super().recommend(body)
                item.update(status='valid',plan=plan,checks=getattr(self, 'case_dimensions', dimensions)(case,plan))
            except LanguageError as error:
                item.update(status='failed',errorCode=error.code,checks=failure_dimensions(self,error))
                failure=error
            item.update(elapsedSeconds=round(time.monotonic()-started,3),operationAudit=copy.deepcopy(self.last_operation_audit))
            self.ledger.finish(key,item)
            if plan is None:
                raise failure
            return plan,item
        except LanguageError as error:
            if error.code in FATAL:
                self.ledger.stop(error.code)
            raise
        finally:
            self.admission.release()
