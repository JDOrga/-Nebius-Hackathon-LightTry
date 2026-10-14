"""Explicit paid two-round gate. Default CLI never reads credentials or sends."""
import argparse
import copy
import os
from pathlib import Path
import sys
import uuid
import hashlib
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from inference.jobs import atomic,read
from recipe_language import RecipeLanguage,MODEL
from runtime.joint import changes
from light_console import normalize,initial
from lighting import normalize_scheme,identity

FIRST='请给出一套完整程序化布光配方，不使用 operations，不省略任何字段：schemaVersion=2，mode 必须是 procedural，environmentId 和 environmentSha256 必须是 null。一盏主光和一盏补光，光区 ID 按顺序为 key 和 fill，均启用。具体给出方向、强度、白色颜色、角尺寸；补光强度小于主光。保持整体旋转、整体强度和底光不变。完整保留所选参照中的 synthesizerVersion、preprocessingVersion、colorConvention。每个光区包含 id、name、enabled、azimuthDeg、elevationDeg、strength、color、sizeDeg 八个字段。仅提出建议，不生成图片。名称和理由必须使用简短中文。'
SECOND='补光弱一点，主光不动，其余参数保持。只降低 fill 的 strength，保留光区 ID 和顺序；不要改变颜色、方向、角尺寸、底光、整体旋转或整体强度。'

def semantic(before,after,phase,envs):
    value=normalize(after,envs)
    if value['mode']!='procedural':raise ValueError('PROCEDURAL_MODE_REQUIRED')
    if [z['id'] for z in value['zones']]!=['key','fill'] or not all(z['enabled'] for z in value['zones']):
        raise ValueError('EXACT_STABLE_KEY_FILL_REQUIRED')
    delta=changes(before,value)
    if phase=='first':
        if not 0<value['zones'][1]['strength']<value['zones'][0]['strength']:
            raise ValueError('EXPLICIT_KEY_FILL_INTENSITIES_REQUIRED')
        for name in ('offsetDeg','strength','ambient'):
            if before[name]!=value[name]:raise ValueError('FIRST_UNREQUESTED_GLOBAL_CHANGE')
    elif len(delta)!=1 or delta[0]['field']!='/zones/1/strength' or not 0<=value['zones'][1]['strength']<before['zones'][1]['strength']:
        raise ValueError('FOLLOWUP_MUST_ONLY_REDUCE_FILL_STRENGTH')
    return value,delta

def verify_applied(value):
    envs={e['id']:e for e in read(Path(__file__).with_name('environments.json'))}
    if value.get('confirmed') is not True or value.get('modelCalled') is not True or value.get('model')!=MODEL or value.get('source')!='Nemotron':
        raise ValueError('REAL_CONFIRMED_PROVIDER_APPLICATION_REQUIRED')
    ledger=value['providerLedger'];records=[r for r in ledger['records'] if r['operationId']==value['operationId'] and r['outcome']=='accepted']
    if ledger['mode']!='REAL_PROVIDER' or ledger['model']!=MODEL or len(records)!=1 or records[0]['proposal']['parameters']!=value['parameters']:
        raise ValueError('PROVIDER_PROVENANCE_MISMATCH')
    selected=records[0]['selectedReference']
    if selected['parameters']!=value['before'] or selected['inputId']!=value.get('photoBinding',{}).get('inputId'):
        raise ValueError('PROVIDER_SELECTED_REFERENCE_MISMATCH')
    semantic(value['before'],value['parameters'],value['phase'],envs)

def continuation_scope(root,prior,approval):
    """Append a separately authorized two-call ledger, never reset old counters."""
    prior=prior.resolve();path=prior/'provider-ledger.json';ledger=read(path)
    if prior==root or ledger.get('mode')!='REAL_PROVIDER' or ledger.get('model')!=MODEL or ledger.get('calls')!=4 or ledger.get('maxCalls')!=4 or ledger.get('status')!='stopped-count':
        raise ValueError('EXACT_EXHAUSTED_PRIOR_SCOPE_REQUIRED')
    reserved=ledger['chargedOrReservedEnvelopeUsd']
    if type(reserved) not in (int,float) or not 0<=reserved<.08:raise ValueError('NO_SHARED_TEXT_BUDGET_REMAINING')
    scope={'priorLedgerPath':str(path),'priorLedgerSha256':hashlib.sha256(path.read_bytes()).hexdigest(),
        'priorCalls':4,'additionalCalls':2,'aggregateCallsMax':6,'sharedBudgetEnvelopeUsd':.08,
        'priorReservedEnvelopeUsd':reserved,'newBudgetEnvelopeUsd':.08-reserved,'repairs':0}
    receipt=root/'continuation-authorization.json'
    if receipt.exists():
        old=read(receipt)
        if any(old[k]!=v for k,v in scope.items()):raise ValueError('CONTINUATION_SCOPE_CHANGED')
    else:
        if not approval:raise ValueError('NEW_TWO_CALL_AUTHORIZATION_REQUIRED')
        atomic(receipt,{**scope,'approvalReference':approval})
        reference=read(prior/'selected-reference.json')
        atomic(root/'selected-reference.json',reference)
    return 2,scope['newBudgetEnvelopeUsd']

def run(options):
    root=options.state.resolve();root.mkdir(parents=True,exist_ok=True)
    envs={e['id']:e for e in read(Path(__file__).with_name('environments.json'))}
    if options.apply:
        proposal=read(root/(options.phase+'-proposal.json'))
        if not options.confirm_operation or options.confirm_operation!=proposal['operationId']:
            raise ValueError('CONFIRM_EXACT_DISPLAYED_OPERATION_REQUIRED')
        value={**proposal,'confirmed':True,'confirmationReference':options.confirm_operation}
        verify_applied(value);atomic(root/(options.phase+'-applied.json'),value)
        print('APPLIED_PARAMETERS_ONLY; GPU_NOT_STARTED',str((root/(options.phase+'-applied.json')).resolve()));return
    if not options.execute:
        atomic(root/'requests.json',{'model':MODEL,'service':'https://api.tokenfactory.nebius.com/v1/chat/completions',
            'first':FIRST,'second':SECOND,'initialMax':1,'followupMax':1,'repairMaxPerRound':1,'totalMax':4,
            'budgetEnvelopeUsd':.08,'secretRead':False,'providerCalls':0,'autoGPU':False})
        print('LOCAL_REQUESTS_PREPARED; no provider calls');return
    if not options.approval_reference:raise ValueError('NEW_TEXT_BUDGET_APPROVAL_REQUIRED')
    max_calls,budget=4,.08
    if getattr(options,'prior_state',None):max_calls,budget=continuation_scope(root,options.prior_state,options.approval_reference)
    retry_first=getattr(options,'retry_failed_first',False)
    mode_repair=getattr(options,'repair_first_semantic',False)
    if retry_first and mode_repair:raise ValueError('ONE_EXPLICIT_RECOVERY_ACTION_ONLY')
    attempt_path=root/(options.phase+'-attempt.json')
    if retry_first:
        if options.phase!='first' or not attempt_path.exists() or not (root/'first-failure.json').exists() or (root/'first-proposal.json').exists() or (root/'first-applied.json').exists():
            raise ValueError('EXPLICIT_FAILED_FIRST_RETEST_ONLY')
        ledger=read(root/'provider-ledger.json')
        if ledger['mode']!='REAL_PROVIDER' or ledger['calls']!=2 or ledger['maxCalls']!=4 or ledger['status']!='active':
            raise ValueError('EXACT_REMAINING_TWO_CALL_SCOPE_REQUIRED')
        attempt_path=root/'first-retry-attempt.json'
    if mode_repair:
        ledger=read(root/'provider-ledger.json')
        if options.phase!='first' or not (root/'first-retry-failure.json').exists() or (root/'first-proposal.json').exists() or ledger['calls']!=3 or ledger['maxCalls']!=4 or ledger['status']!='active':
            raise ValueError('EXPLICIT_LAST_CALL_SEMANTIC_REPAIR_SCOPE_REQUIRED')
        last=ledger['records'][-1]
        if last['outcome']!='accepted' or last['proposal']['parameters']['mode']!='environment':
            raise ValueError('EXACT_RECORDED_MODE_FAILURE_REQUIRED')
        attempt_path=root/'first-mode-repair-attempt.json'
    if attempt_path.exists():raise ValueError('NO_AUTOMATIC_REISSUE_OR_LEDGER_RESET')
    if options.phase=='second':
        applied=read(root/'first-applied.json');verify_applied(applied);before=applied['parameters']
    else:before=initial(envs['sunny'])
    # Only explicit execution accesses the already configured process secret.
    key=os.environ.get('LIGHTTRY_TOKEN_FACTORY_KEY','')
    if not key and os.environ.get('LIGHTTRY_KEY_FILE'):
        key=Path(os.environ['LIGHTTRY_KEY_FILE']).read_text(encoding='utf-8-sig').strip()
    if not key:raise ValueError('EXISTING_PROCESS_SERVICE_CONFIGURATION_REQUIRED')
    # Explicit retest spends ONE remaining call; reserve the last for follow-up.
    # The persistent ledger and all prior failures remain unchanged.
    remaining=max_calls-read(root/'provider-ledger.json')['calls'] if (root/'provider-ledger.json').exists() else max_calls
    repair_limit=0 if getattr(options,'prior_state',None) or retry_first or mode_repair or remaining<=1 else 1
    service=RecipeLanguage(list(envs.values()),read(Path(__file__).with_name('policy.json')),key,
        root/'provider-ledger.json',max_calls=max_calls,budget=budget,repair_limit=repair_limit,
        acceptance_validator=lambda v: semantic(before,v['parameters'],options.phase,envs) if v['status']=='ready' else None,
        full_procedural_recipe=True)
    reference_path=root/'selected-reference.json'
    if reference_path.exists():reference=read(reference_path)
    else:
        packet=options.packet.resolve() if options.packet else Path(__file__).resolve().parents[2]/'.local/lighttry-joint-20261012/manual-package-release/packet'
        from runtime.joint import verify_joint
        prepared=verify_joint(packet)
        reference={'planId':uuid.uuid4().hex,'inputId':prepared['input']['sha256'][:32],
            'inputSha256':prepared['input']['sha256'],'preparationTaskId':prepared['taskId']}
        atomic(reference_path,reference)
    scheme=normalize_scheme(dict(schemaVersion=1,planId=reference['planId'],version=1 if options.phase=='first' else 2,
        name='联合验收',parameters=before,inputId=reference['inputId'],parentVersion=None if options.phase=='first' else 1),envs,service.policy)
    body=dict(currentScheme={k:v for k,v in scheme.items() if k!='recipeKey'},
        currentResult=dict(status='not-generated',kind='none',artifactId=None),text=FIRST if options.phase=='first' else SECOND,
        history=[],replyLanguage='zh')
    if retry_first:body['text']+=' 名称和理由必须使用简短中文，不写英文句子；key、fill 仅保留为光区标识。'
    if mode_repair:
        body['text']+=' 上轮建议未应用，因为保留了 environment 模式，光区不会成为程序化输入。现在只允许一次结构化修正：必须改为 procedural 并将两个环境身份字段设为 null；不要仅添加光区。所选参照仍是原方案，不是上轮未应用建议。'
        body['history']=['上轮未应用建议未切换程序化模式，已拒绝；这不是当前已应用状态。']
    atomic(attempt_path,{'approvalReference':options.approval_reference,'request':body,'automaticGeneration':False,
        'explicitFailedFirstRetest':retry_first,'explicitLastCallSemanticRepair':mode_repair,'maxRepairs':repair_limit,'priorCallsPreserved':max_calls-remaining,
        'continuationScope':read(root/'continuation-authorization.json') if getattr(options,'prior_state',None) else None})
    try:
        result=service.recommend(body)
        if result.get('modelCalled') is not True or result.get('source')!='Nemotron' or result['status']!='ready':
            raise ValueError('REAL_READY_STRUCTURED_MODEL_RESPONSE_REQUIRED')
        params,delta=semantic(before,result['parameters'],options.phase,envs)
        value={**result,'parameters':params,'before':before,'phase':options.phase,'delta':delta,'confirmed':False,'photoBinding':reference,
            'model':MODEL,'providerLedger':read(root/'provider-ledger.json'),'applicationDoesNotGenerate':True}
        atomic(root/(options.phase+'-proposal.json'),value)
        print('WAITING_EXPLICIT_APPLICATION',result['operationId']);print(__import__('json').dumps(delta,ensure_ascii=False,indent=2))
    except BaseException as error:
        failure_path=root/(options.phase+('-mode-repair' if mode_repair else '-retry' if retry_first else '')+'-failure.json')
        atomic(failure_path,{'error':getattr(error,'code',type(error).__name__),
            'semanticCode':str(error) if isinstance(error,ValueError) else None,'noFallback':True,
            'providerLedger':read(root/'provider-ledger.json')});raise

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--state',type=Path,required=True);p.add_argument('--phase',choices=('first','second'),default='first')
    p.add_argument('--packet',type=Path)
    p.add_argument('--prior-state',type=Path,help='Explicit separately authorized two-call continuation; shared USD0.08 budget minus prior reservations')
    p.add_argument('--retry-failed-first',action='store_true',help='Explicit one-call retest after local fix; preserves ledger, reserves last call for follow-up')
    p.add_argument('--repair-first-semantic',action='store_true',help='Explicit last authorized call for recorded wrong-mode failure; no retries, no reserved follow-up call afterward')
    p.add_argument('--execute',action='store_true');p.add_argument('--approval-reference');p.add_argument('--apply',action='store_true');p.add_argument('--confirm-operation')
    run(p.parse_args())
