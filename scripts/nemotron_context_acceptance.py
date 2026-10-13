"""Independent new two-round scope; default only prepares, never reads credentials."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import uuid
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'project'))
from inference.jobs import atomic,read
from next.language import RecipeLanguage,MODEL
from next.accepted import load_accepted,measured_context
from next.runtime.joint import changes
from lighting import normalize_scheme
from light_console import normalize

FIRST='以明确选中的 F 实测配方为当前方案。依据所提供的实验记录，提出一项改善主体暗面的修改：仅增加 fill.strength，保持主光、其他补光字段和全局参数不变。理由明确引用 F 的补光抬亮暗面实测记录；记录不是照片像素，你没有看过照片。不得承诺保色或物理精确效果。返回完整结构化配方，稳定光区 ID 为 key、fill；先建议，确认后才应用，不启动 GPU。'
SECOND='以第一轮已经确认应用的真实配方为当前方案，只降低补光 fill.strength。保持主光、其他补光字段、稳定 ID 与顺序及全部全局参数不变。依据当前已应用值给出完整配方和简短中文解释，不把未应用建议当成当前方案；不生成照片。'


def semantic(before, proposal, phase, environments):
    after=normalize(proposal['parameters'],environments);delta=changes(before,after)
    if [z['id'] for z in after['zones']]!=['key','fill']:raise ValueError('STABLE_ZONE_IDS_REQUIRED')
    if len(delta)!=1 or delta[0]['field']!='/zones/1/strength':raise ValueError('ONLY_FILL_STRENGTH_CHANGE_REQUIRED')
    old=before['zones'][1]['strength'];new=after['zones'][1]['strength']
    if not (new>old if phase=='first' else new<old):raise ValueError('REQUESTED_FILL_DIRECTION_REQUIRED')
    reason=proposal['reason']
    if phase=='first' and not ('F' in reason and '暗' in reason and any(s in reason for s in ('记录','实测'))):
        raise ValueError('F_MEASURED_DARK_FACE_BASIS_REQUIRED')
    return delta


def prepare(state,package):
    import server
    catalog=server.load_catalog(ROOT/'.local/demo-candidate-20261010/demo-assets')
    studies,_,schemes=load_accepted(package,catalog);cases=measured_context(studies)
    if len(cases)!=7:raise ValueError('SEVEN_MEASURED_OBSERVATIONS_REQUIRED')
    f=next(s for s in schemes if s['provenance']['caseId']=='F')
    scheme={k:f[k] for k in ('schemaVersion','planId','version','name','parameters','inputId','parentVersion')}
    scope={'version':'nemotron-context-independent-v1','model':MODEL,'selectedCase':'F',
        'scheme':scheme,'cases':cases,'historicalFOutputSha256':f['importedResultSha256'],
        'first':FIRST,'second':SECOND,'initialRequests':2,'repairMaxPerRound':1,'maxCalls':4,
        'budgetEnvelopeUsd':.08,'inputTokenEstimateUpper':15000,'inputPayloadBytesMax':15000,
        'outputTokensMax':40960,'thinking':'on','priceInputPerMillionProvisional':.06,
        'priceOutputPerMillionProvisional':.24,'priceVerifiedThisTurn':False,
        'providerCalls':0,'photosReceived':False,'automaticGPU':False,
        'status':'PREPARED_WAITING_NEW_AUTHORIZATION','oldAdditionalScopeInherited':False}
    state.mkdir(parents=True,exist_ok=True)
    if (state/'scope.json').exists():
        if read(state/'scope.json')!=scope:raise ValueError('PRESERVE_INDEPENDENT_SCOPE')
    else:atomic(state/'scope.json',scope)
    return scope


def confirmed(state,phase,value=None):
    value=read(state/(phase+'-applied.json')) if value is None else value
    ledger=read(state/'provider-ledger.json')
    scope=read(state/'scope.json')
    records=[r for r in ledger['records'] if r.get('operationId')==value['operationId'] and r.get('outcome')=='accepted']
    if ledger['mode']!='REAL_PROVIDER' or ledger.get('model')!=MODEL or value.get('source')!='Nemotron' or value.get('modelCalled') is not True or not value.get('confirmed') or len(records)!=1:
        raise ValueError('REAL_CONFIRMED_CONTEXT_OPERATION_REQUIRED')
    if value.get('phase')!=phase or value.get('contextScopeSha256')!=hashlib.sha256((state/'scope.json').read_bytes()).hexdigest():
        raise ValueError('CONTEXT_SCOPE_IDENTITY_MISMATCH')
    reference=records[0]['selectedReference']
    if reference['inputId']!=scope['scheme']['inputId'] or reference['planId']!=scope['scheme']['planId']:
        raise ValueError('CONTEXT_PHOTO_PLAN_MISMATCH')
    if records[0]['proposal']['parameters']!=value['parameters'] or records[0]['selectedReference']['parameters']!=value['before']:
        raise ValueError('ACTUAL_DIFF_PROVIDER_REFERENCE_MISMATCH')
    before=scope['scheme']['parameters'] if phase=='first' else confirmed(state,'first')['parameters']
    if before!=value['before']:raise ValueError('CONFIRMED_APPLICATION_REFERENCE_MISMATCH')
    return value


def run(o):
    state=o.state.resolve();scope=read(state/'scope.json')
    envs={e['id']:e for e in read(ROOT/'project/next/runtime/environments.json')}
    if o.apply:
        value=read(state/(o.phase+'-proposal.json'))
        if not o.confirm_operation or o.confirm_operation!=value['operationId']:raise ValueError('CONFIRM_EXACT_OPERATION_REQUIRED')
        semantic(value['before'],value,o.phase,envs)
        path=state/(o.phase+'-applied.json')
        if path.exists():raise ValueError('PRESERVE_EXISTING_APPLICATION')
        candidate={**value,'confirmed':True};confirmed(state,o.phase,candidate)
        atomic(path,candidate)
        print('CONFIRMED_PARAMETERS_ONLY; GPU_NOT_STARTED');return
    if not o.execute:
        ledger=read(state/'provider-ledger.json') if (state/'provider-ledger.json').exists() else None
        calls=ledger['calls'] if ledger else 0
        print('LOCAL_CONTEXT_STATUS; recordedCalls='+str(calls)+'; mode='+str(ledger['mode'] if ledger else 'NOT_CALLED')+'; F selected; C/F references; 7 observations; independent maxCalls=4');return
    if not o.approval_reference or not o.price_confirmed:raise ValueError('NEW_SCOPE_AND_CURRENT_PRICE_CONFIRMATION_REQUIRED')
    # Existing provider accounting is pinned to these rates. Never silently use
    # its old numbers for a more expensive current model or account price.
    if o.input_price is None or o.output_price is None or not 0<=o.input_price<=.06 or not 0<=o.output_price<=.24:
        raise ValueError('CURRENT_PRICE_EXCEEDS_PINNED_ACCOUNTING_REAUTHORIZE_AND_REPRICE')
    if o.phase=='second':
        first=confirmed(state,'first');before=first['parameters']
    else:before=scope['scheme']['parameters']
    attempt=state/(o.phase+'-attempt.json')
    if attempt.exists():raise ValueError('NO_AUTOMATIC_REPLAY_OR_ADDITIONAL_ALLOWANCE')
    key=os.environ.get('LIGHTTRY_TOKEN_FACTORY_KEY','')
    if not key and os.environ.get('LIGHTTRY_KEY_FILE'):key=Path(os.environ['LIGHTTRY_KEY_FILE']).read_text(encoding='utf-8-sig').strip()
    if not key:raise ValueError('EXISTING_KEY_REQUIRED')
    policy=read(ROOT/'project/next/runtime/policy.json');policy['parameterized']=True
    ledger=state/'provider-ledger.json'
    if ledger.exists() and read(ledger)['calls']> (0 if o.phase=='first' else 2):raise ValueError('NO_OLD_ADDITIONAL_SCOPE')
    service=RecipeLanguage(list(envs.values()),policy,key,ledger,max_calls=4,budget=.08,
        repair_limit=1,full_procedural_recipe=True,thinking_mode='on',max_tokens=40960,
        measured_cases=scope['cases'],acceptance_validator=lambda p: semantic(before,p,o.phase,envs) if p['status']=='ready' else None)
    scheme={**scope['scheme'],'version':1 if o.phase=='first' else 2,'parentVersion':None if o.phase=='first' else 1,'parameters':before}
    body={'currentScheme':scheme,'currentResult':{'status':'historical-F' if o.phase=='first' else 'parameters-applied-no-render',
        'kind':'study' if o.phase=='first' else 'none','artifactId':scope['historicalFOutputSha256'] if o.phase=='first' else None},
        'text':scope[o.phase],'history':[] if o.phase=='first' else ['第一轮真实建议经准确 operationId 确认应用；未生成新照片。'], 'replyLanguage':'zh'}
    atomic(attempt,{'request':body,'approvalReference':o.approval_reference,'currentPriceConfirmation':o.price_confirmed,
        'actualConfirmedInputPerMillion':o.input_price,'actualConfirmedOutputPerMillion':o.output_price,'oldAllowanceInherited':False})
    try:
        result=service.recommend(body)
        if result.get('source')!='Nemotron' or result.get('modelCalled') is not True or result['status']!='ready':raise ValueError('REAL_MODEL_READY_REQUIRED')
        delta=semantic(before,result,o.phase,envs)
        atomic(state/(o.phase+'-proposal.json'),{**result,'before':before,'delta':delta,'confirmed':False,'phase':o.phase,'contextScopeSha256':hashlib.sha256((state/'scope.json').read_bytes()).hexdigest()})
        print('WAITING_CONFIRMATION',result['operationId']);print(json.dumps(delta,ensure_ascii=False,indent=2))
    except BaseException as e:
        atomic(state/(o.phase+'-failure.json'),{'error':str(e),'automaticRetry':False,'automaticGPU':False});raise


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--state',type=Path,required=True);p.add_argument('--prepare-from',type=Path)
    p.add_argument('--phase',choices=('first','second'),default='first');p.add_argument('--execute',action='store_true')
    p.add_argument('--approval-reference');p.add_argument('--price-confirmed',help='new authorization confirming current price fits USD0.08 envelope')
    p.add_argument('--input-price',type=float);p.add_argument('--output-price',type=float)
    p.add_argument('--apply',action='store_true');p.add_argument('--confirm-operation');o=p.parse_args()
    if o.prepare_from:prepare(o.state.resolve(),o.prepare_from.resolve())
    run(o)
