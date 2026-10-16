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
            'host':safe_host,'hostConfirmed':snapshot.get('hostConfirmed') is True,'deadlines':deadlines,
            'stopRequested':snapshot.get('stopSent') is True,'verifiedStopped':snapshot.get('verifiedStopped') is True,
            'instancesEmpty':snapshot.get('instancesEmpty') is True,'worker':telemetry,
            'historicalLoadTiming':clean_loading(snapshot.get('loadTiming')),
            'workerStale':not(fresh and telemetry and telemetry['observedAt'] is not None and 0<=now-telemetry['observedAt']<=60)}
