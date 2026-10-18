"""Bounded read-only telemetry. Never imports CUDA or performs network operations."""
import json
import math
from pathlib import Path
import re
import time

LOAD_STAGES=('environment_setup','module_import','argument_setup','model_config',
             'network_setup','checkpoint_read','parameter_apply','tokenizer_load','cuda_synchronize')
ALL_LOAD_STAGES=set(LOAD_STAGES)|{'preload_total','pipeline_init','network_load','device_move',
                                 'tokenizer_setup','tokenizer_checkpoint_read'}
TASK_STAGES={'preflight','weights','inverse','forward','validating','transferring'}


def clean_failure(value,stage=None):
    """No messages, paths, commands, tracebacks, dynamic codes or extra fields."""
    value=value if isinstance(value,dict) else {}
    kind=value.get('exception')
    return {'code':'WORKER_EXECUTION_FAILED',
            'stage':stage if isinstance(stage,str) and stage in TASK_STAGES else 'unknown',
            'exception':kind if isinstance(kind,str) and kind in ('UnboundLocalError','ValueError',
                'TimeoutError','OSError','FileNotFoundError','RuntimeError','ModuleNotFoundError',
                'AssertionError','KeyboardInterrupt') else 'UnknownError'}


def number(value,maximum=10**15):
    return value if type(value) in (int,float) and math.isfinite(value) and 0<=value<=maximum else None


def small_json(path,limit=65536):
    path=Path(path)
    if any(p.is_symlink() for p in (path,*path.parents)):raise ValueError('UNSAFE_TELEMETRY')
    with path.open('rb') as stream:raw=stream.read(limit+1)
    if len(raw)>limit:raise ValueError('TELEMETRY_TOO_LARGE')
    return json.loads(raw)


def clean_segments(value):
    """Small completed spans from the EXISTING log, not another measurement pass."""
    result=[];seen=set()
    for item in value[:64] if isinstance(value,list) else []:
        if not isinstance(item,dict):continue
        identity=item.get('spanId');stage=item.get('stage');outcome=item.get('outcome')
        if (type(identity) is not int or not 1<=identity<=128 or identity in seen or
            not isinstance(stage,str) or stage not in ALL_LOAD_STAGES or outcome not in ('finished','failed')):continue
        seen.add(identity);parent=item.get('parentSpanId')
        result.append({'spanId':identity,'parentSpanId':parent if type(parent) is int and 1<=parent<=128 else None,
            'stage':stage,'outcome':outcome,**{name:number(item.get(name)) for name in
                ('startedAt','finishedAt','elapsedMs','cpuMs','ioReadBytes','ioRchar')}})
    return result


def clean_loading(value):
    if not isinstance(value,dict) or value.get('version')!=1 or not isinstance(value.get('phases'),list):return None
    phases=[];seen=set()
    for item in value['phases'][:2]:
        if not isinstance(item,dict) or item.get('phase') not in ('inverse','forward') or item['phase'] in seen:continue
        seen.add(item['phase'])
        completed=[s for s in LOAD_STAGES if s in item.get('completedStages',[]) ] if isinstance(item.get('completedStages'),list) else []
        phases.append({'phase':item['phase'],
            'state':item.get('state') if item.get('state') in ('loading','ready','busy','failed') else 'unknown',
            'activeStage':item.get('activeStage') if isinstance(item.get('activeStage'),str) and item['activeStage'] in ALL_LOAD_STAGES else None,
            'completedStages':completed,'completed':len(completed),'total':len(LOAD_STAGES),
            'updatedAt':number(item.get('updatedAt')),'elapsedMs':number(item.get('elapsedMs')),
            'cpuMs':number(item.get('cpuMs')),'ioReadBytes':number(item.get('ioReadBytes')),
            'segments':clean_segments(item.get('segments'))})
    return {'version':1,'phases':phases}


def remember_load_timing(previous,current):
    """Keep already-sanitized spans IN the existing session body/save transaction.

    Historical diagnostics only: never consulted by readiness or cloud control.
    Missing telemetry must not erase measurements already saved before shutdown.
    """
    if not current:return previous
    phases={p['phase']:p for p in previous['phases']} if previous else {}
    for phase in current['phases']:
        old=phases.get(phase['phase'],{})
        spans={s['spanId']:s for s in old.get('segments',[])}
        for span in phase.get('segments',[]):spans.setdefault(span['spanId'],span)
        if not spans:continue
        completed=[s for s in LOAD_STAGES if s in old.get('completedStages',[]) or s in phase.get('completedStages',[])]
        phases[phase['phase']]={**old,**{k:v for k,v in phase.items() if v is not None},
                                'completedStages':completed,'completed':len(completed),
                                'segments':list(spans.values())[:64]}
    return {'version':1,'phases':list(phases.values())[:2]} if phases else previous


def phase_loading(root,phase,pid,session,resource,alive,now=None):
    """Only current-process records in the already-private phase directory."""
    now=time.time() if now is None else now
    result={'phase':phase,'state':'unknown','activeStage':None,'completedStages':[]}
    try:
        folder=Path(root)/'resident'/phase
        state=small_json(folder/'state.json')
        if (state.get('pid'),state.get('sessionId'),state.get('resourceId'),state.get('phase'))!=(pid,session,resource,phase):return result
        result['state']=state.get('state') if alive else 'failed'
        path=folder/'loading-timing.jsonl'
        if any(p.is_symlink() for p in (path,*path.parents)):return result
        with path.open('rb') as stream:raw=stream.read(65537)
        if len(raw)>65536:return result
        events=[]
        for line in raw.splitlines()[:128]:
            try:event=json.loads(line)
            except (ValueError,UnicodeError):continue  # a flushed/partial trailing line is not success
            if (not isinstance(event,dict) or event.get('pid')!=pid or event.get('phase')!=phase or
                event.get('stage') not in ALL_LOAD_STAGES or event.get('event') not in ('started','finished','failed') or
                number(event.get('at')) is None or event['at']>now+5):continue
            events.append(event)
        opened={};completed=set();segments=[]
        for event in events:
            identity=event.get('spanId')
            if type(identity) is not int or not 1<=identity<=128:continue
            if event['event']=='started':opened[identity]=event
            else:
                start=opened.pop(identity,None)
                if start and start['stage']==event['stage']:
                    if event['event']=='finished':completed.add(event['stage'])
                    segments.append({'spanId':identity,'parentSpanId':start.get('parentSpanId'),
                        'stage':event['stage'],'outcome':event['event'],'startedAt':start['at'],'finishedAt':event['at'],
                        **{k:event.get(k) for k in ('elapsedMs','cpuMs','ioReadBytes','ioRchar')}})
        result['segments']=segments  # existing 128-record read; no extra file/probe/network call
        result['completedStages']=[stage for stage in LOAD_STAGES if stage in completed]
        # Prefer the deepest currently open span; total/pipeline parents are inclusive.
        active=list(opened.values())[-1] if opened else None
        if active:result['activeStage']=active['stage']
        if events:result['updatedAt']=events[-1]['at']
        total=next((e for e in reversed(events) if e['stage']=='preload_total' and e['event']!='started'),None)
        if total:
            for name in ('elapsedMs','cpuMs','ioReadBytes'):result[name]=number(total.get(name))
        elif events:
            start=next((e for e in events if e['stage']=='preload_total' and e['event']=='started'),None)
            if start:result['elapsedMs']=max(0,now-start['at'])*1000
    except (OSError,ValueError,KeyError,TypeError):pass
    return result


def execution_progress(root,envelope):
    """Read the exact already-running task's atomic event, never inspect raw logs."""
    try:
        identity=envelope['jobId']
        if not isinstance(identity,str) or not re.fullmatch('[a-f0-9]{32}',identity):return None
        folder=Path(root)/'executions'/identity
        request=small_json(folder/'request.json');event=small_json(folder/'run/execution.json')
        from model_contract import request_sha
        if request_sha(request)!=envelope.get('requestSha256'):return None
        if (request.get('taskId'),request.get('nonce'))!=(event.get('taskId'),event.get('nonce')) or request.get('taskId')!=identity:return None
        if event.get('status')!='running' or event.get('stage') not in TASK_STAGES:return None
        return {'status':'running','stage':event['stage']}
    except (OSError,ValueError,KeyError,TypeError):return None


def worker_telemetry(health,observed):
    """Diagnostics only; NEVER feed this sanitized display data into readiness."""
    return {'observedAt':observed,
            'modelState':health.get('modelState') if health.get('modelState') in ('loading','ready','cold','failed') else 'unknown',
            'modelLoaded':health.get('modelLoaded') is True,
            'loadingProgress':clean_loading(health.get('loadingProgress'))}


def public_failure(snapshot,enrollment,fresh):
    """Closed display schema: never return raw stderr, exception text or secrets."""
    released=fresh and snapshot.get('verifiedStopped') is True and snapshot.get('instancesEmpty') is True
    stage=enrollment.get('stage')
    failure=snapshot.get('startFailure') or {}
    title=None;detail=None;code=None
    reasons={
        'NO_CLIENT_CONNECTION_5_MIN':'连续5分钟未确认任何工作台连接',
        'CPU_HEARTBEAT_LOST':'后端CPU服务心跳中断，触发停机保护',
        'RUNNING_WINDOW_EXPIRED':'首次确认RUNNING后的一小时窗口到期',
        'STARTUP_TIMEOUT':'GPU启动等待超时',
        'SESSION_ABSOLUTE_DEADLINE':'本次授权或绝对保护窗口到期',
        'USER_REQUESTED_STOP':'用户请求停机',
        'USER_STOP_BEFORE_BOOTSTRAP_REPAIR':'用户要求修复前先停机',
        'USER_STOP_BEFORE_ERROR_CLASSIFICATION':'用户要求补全错误分类前先停机',
        'OPERATOR_STOP':'操作者请求停机',
        'AUTO_HOST_TRUST_FAILED':'本轮自动绑定主机失败；未继续部署',
        'BOOTSTRAP_FAILED':'GPU引导失败，触发停机保护',
        'DEADLINE_OR_CPU_LEASE':'触发旧版时间或心跳保护；旧记录未细分原因',
        'DEADLINE_DURING_OBSERVATION':'状态查询期间触发旧版时间或心跳保护；旧记录未细分原因'}
    reason=snapshot.get('stopReason') or snapshot.get('error')
    if snapshot.get('stopSent') and reason in reasons:
        manual=reason in {'USER_REQUESTED_STOP','USER_STOP_BEFORE_BOOTSTRAP_REPAIR','USER_STOP_BEFORE_ERROR_CLASSIFICATION','OPERATOR_STOP'}
        return {'code':reason,'severity':'info' if released else 'warning','title':'GPU已停止' if released else 'GPU正在停止' if manual else 'GPU停机保护已触发',
            'stage':'stop_guard','detail':'停机原因：'+reasons[reason]+'。',
            'cost':'已确认STOPPED且实例已释放。' if released else '停机请求已提交，但尚未确认实例释放，可能仍在计费。',
            'action':'恢复连接不会自动开机；如需使用，请手动重新启动。' if released else '等待释放确认，不要重复启动。','active':not released}
    if stage in ('uncertain','failed'):
        code='GPU_CONNECTION_FAILED';title='GPU连接准备失败'
        detail='服务器连接或部署未完成，模型尚不可用；不会自动重试。'
        if enrollment.get('error')=='BOOTSTRAP_REMOTE_UNCERTAIN':
            detail='读取主机指纹或远程连接失败；具体网络原因尚未确认，不是仍在正常加载。'
        from bootstrap_errors import public_error
        info=public_error(enrollment.get('failure'))
        if info:
            code=info['code'];title='GPU引导失败 · '+info['stageLabel']
            detail=info['message']+' 错误码：'+code+'；不会自动重试。'
            stage=info['stage']
        elif enrollment.get('error')=='BOOTSTRAP_UNCERTAIN':
            detail='旧版引导异常未记录具体类型，不能追溯判定为超时或解析失败；未继续正常加载。'
    elif snapshot.get('error') in ('START_OR_PREFLIGHT_UNCERTAIN','START_OR_PREFLIGHT_FAILED') or (failure and not released):
        code='GPU_START_FAILED';title='GPU启动或预检失败'
        stage=failure.get('stage') if failure.get('stage') in ('preflight','bootstrap_preflight','supervisor_arm','provider_start') else 'unknown'
        detail='启动流程已中断；不要重复点击启动，需要先核实和处理故障。'
    elif snapshot.get('state')=='UNKNOWN' or not fresh:
        code='GPU_STATUS_UNCERTAIN';title='GPU状态无法确认'
        detail='后端状态查询失败或快照已过期；旧状态不能证明服务器已停止。'
    elif isinstance(snapshot.get('workerTelemetry'),dict) and snapshot['workerTelemetry'].get('modelState')=='failed':
        code='GPU_MODEL_FAILED';title='模型加载失败';detail='模型进程报告加载失败，不能生成。'
    if not title:return None
    if released:
        return {'code':code,'severity':'warning','title':'上次故障 · '+title,'stage':stage if isinstance(stage,str) and stage in ('uncertain','failed','preflight','bootstrap_preflight','supervisor_arm','provider_start','state_check','capture','authorize','prepare','upload','install','tunnel','direct_https') else 'unknown',
                'detail':detail,'cost':'已确认GPU停止且实例已释放。','action':'故障处理后再手动启动，不会自动重试。','active':False}
    return {'code':code,'severity':'error','title':title,'stage':stage if isinstance(stage,str) and stage in ('uncertain','failed','preflight','bootstrap_preflight','supervisor_arm','provider_start','state_check','capture','authorize','prepare','upload','install','tunnel','direct_https') else 'unknown',
            'detail':detail,'cost':'尚未确认停机释放，GPU可能继续计费。','action':'不再使用时请点击“停止”；等待显示“已停止且实例已释放”，不要重复启动。','active':True}


def public_monitor(snapshot,fresh,now):
    telemetry=snapshot.get('workerTelemetry')
    telemetry=worker_telemetry(telemetry,number(telemetry.get('observedAt'))) if isinstance(telemetry,dict) else None
    host=snapshot.get('hostIdentity') or {}
    safe_host={key:value for key in ('vmId','ip','resourceId') if isinstance((value:=host.get(key)),str) and
               len(value)<=160 and re.fullmatch(r'[A-Za-z0-9_.:\-]+',value)} if isinstance(host,dict) else {}
    deadlines={key:number(snapshot.get(key)) for key in ('createdAt','runningAt','startupDeadline','workDeadline',
               'stopDeadline','verifyDeadline','absoluteDeadline')}
    return {'providerState':snapshot.get('providerState') if snapshot.get('providerState') in
            ('STOPPED','RUNNING','STARTING','STOPPING','PROVISIONING','IMAGE_PULLING') else 'UNKNOWN',
            'host':safe_host,'hostConfirmed':snapshot.get('hostConfirmed') is True,
            'hostTrustMethod':snapshot.get('hostTrustMethod') if snapshot.get('hostTrustMethod') in ('manual','guard-tofu') else None,
            'deadlines':deadlines,
            'clientLastSeenAt':number(snapshot.get('clientLastSeenAt')),'clientIdleDeadline':number(snapshot.get('idleDeadline')),
            'stopRequested':snapshot.get('stopSent') is True,'verifiedStopped':snapshot.get('verifiedStopped') is True,
            'instancesEmpty':snapshot.get('instancesEmpty') is True,'worker':telemetry,
            'historicalLoadTiming':clean_loading(snapshot.get('loadTiming')),
            'workerStale':not(fresh and telemetry and telemetry['observedAt'] is not None and 0<=now-telemetry['observedAt']<=60)}
