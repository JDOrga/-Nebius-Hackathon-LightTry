"""Explicit bounded real-provider diagnostic rounds; NO apply/GPU/lifecycle."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from inference.jobs import atomic,read
from recipe_language import RecipeLanguage,MODEL
from runtime.joint_language import FIRST,SECOND,semantic
from light_console import initial
from lighting import normalize_scheme


def scope(root,priors,approval):
    if not approval or len(priors)!=2:raise ValueError('EXPLICIT_ADDITIONAL_20_CALL_SCOPE_REQUIRED')
    entries=[]
    for path in priors:
        path=path.resolve();v=read(path)
        if v['mode']!='REAL_PROVIDER' or v['model']!=MODEL:raise ValueError('REAL_PRIOR_LEDGER_REQUIRED')
        entries.append({'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'calls':v['calls'],'reserved':v['chargedOrReservedEnvelopeUsd']})
    prior_cost=sum(x['reserved'] for x in entries)
    if sum(x['calls'] for x in entries)!=5 or not 0<=prior_cost<.08:raise ValueError('EXACT_PRIOR_FIVE_CALL_SCOPE_REQUIRED')
    value={'approvalReference':approval,'priorLedgers':entries,'additionalCalls':20,'aggregateCallsMax':25,
        'sharedBudgetEnvelopeUsd':.08,'newBudgetEnvelopeUsd':.08-prior_cost,
        'mode':'REAL_DIAGNOSTIC_NO_BUSINESS_APPLICATION','repairsPerRequest':0,
        'twoRoundReference':'round2 uses round1 proposed recipe as a labelled diagnostic snapshot, NOT an applied business state'}
    path=root/'authorization.json'
    if path.exists():
        if read(path)!=value:raise ValueError('PRESERVE_ITERATION_AUTHORIZATION_SCOPE')
    else:atomic(path,value)
    return value


def execute(options):
    root=options.state.resolve();root.mkdir(parents=True,exist_ok=True)
    authorization=scope(root,options.prior_ledger,options.approval_reference)
    resume=getattr(options,'resume_after_fix',False)
    if (root/'run-attempt.json').exists():
        proof_path=getattr(options,'exit_proof',None) or root/'controller-exit-proof.json'
        if not resume or not (root/'halt.json').exists() or not proof_path.exists():raise ValueError('EXPLICIT_NO_REPLAY_OF_ITERATION_RUN')
        proof=read(proof_path)
        if proof.get('exitCode')!=0 or proof.get('ownedProcessExited') is not True:raise ValueError('PRIOR_CONTROLLER_EXIT_UNCONFIRMED')
        ledger=read(root/'provider-ledger.json');last=ledger['records'][-1]
        if proof.get('lastObservedCalls')!=ledger['calls']:raise ValueError('STALE_CONTROLLER_EXIT_PROOF')
        if not any(hashlib.sha256(Path(p).read_bytes()).hexdigest()!=digest for p,digest in last['sourceHashes'].items()):
            raise ValueError('CONCRETE_SOURCE_FIX_REQUIRED_BEFORE_RESUME')
        preserved=root/f"halt-before-resume-{ledger['calls']+1:02d}.json"
        if preserved.exists():raise ValueError('PRESERVE_PREVIOUS_RESUME_EVENT')
        (root/'halt.json').rename(preserved)
        atomic(root/f"resume-{ledger['calls']+1:02d}.json",{'approvalReference':options.approval_reference,'priorCallsPreserved':ledger['calls'],
            'unknownTimeoutReservationNotReleased':True,'sourceChanged':True,'priorControllerExitProof':proof})
    else:atomic(root/'run-attempt.json',{'approvalReference':options.approval_reference,'epoch':time.time()})
    envs={e['id']:e for e in read(Path(__file__).with_name('environments.json'))}
    policy=read(Path(__file__).with_name('policy.json'))
    reference=read(options.reference)
    key_path=os.environ.get('LIGHTTRY_KEY_FILE')
    key=os.environ.get('LIGHTTRY_TOKEN_FACTORY_KEY','')
    if not key and key_path:key=Path(key_path).read_text(encoding='utf-8-sig').strip()
    if not key:raise ValueError('EXISTING_SERVICE_KEY_REQUIRED')
    baseline=initial(envs['sunny']);first=read(root/'first-proposal.json') if (root/'first-proposal.json').exists() else None
    feedback='';phase='second' if first else 'first';trace=read(root/'trace.json') if (root/'trace.json').exists() else []
    prior_calls=read(root/'provider-ledger.json')['calls'] if (root/'provider-ledger.json').exists() else 0
    for ordinal in range(prior_calls+1,21):
        before=baseline if phase=='first' else first['parameters']
        request_text=FIRST if phase=='first' else SECOND
        if feedback:request_text+=' 上一次校验拒绝：'+feedback+'。修正该项，仍返回完整程序化配方，不省略字段。'
        if len(request_text)>600:raise ValueError('BOUNDED_REQUEST_TEXT_REQUIRED')
        scheme=normalize_scheme(dict(schemaVersion=1,planId=reference['planId'],version=1 if phase=='first' else 2,
            name='真实两轮诊断参照（未应用）',parameters=before,inputId=reference['inputId'],parentVersion=None if phase=='first' else 1),envs,policy)
        body={'currentScheme':{k:v for k,v in scheme.items() if k!='recipeKey'},
            'currentResult':{'status':'diagnostic-not-generated','kind':'none','artifactId':None},
            'text':request_text,'history':[],'replyLanguage':'zh'}
        service=RecipeLanguage(list(envs.values()),policy,key,root/'provider-ledger.json',max_calls=20,
            budget=authorization['newBudgetEnvelopeUsd'],repair_limit=0,full_procedural_recipe=True,
            thinking_mode='off',max_tokens=2048,
            acceptance_validator=lambda value: semantic(before,value['parameters'],phase,envs) if value['status']=='ready' else None)
        ledger=read(root/'provider-ledger.json')
        if ledger['calls']>=20:break
        atomic(root/(f'{ordinal:02d}-{phase}-request.json'),body)
        timer=time.perf_counter();record={'ordinal':ordinal,'phase':phase,'source':'REAL_PROVIDER','before':before,'businessApplied':False}
        try:
            result=service.recommend(body)
            if not result.get('modelCalled') or result.get('source')!='Nemotron' or result['status']!='ready':raise ValueError('REAL_READY_PROPOSAL_REQUIRED')
            parameters,delta=semantic(before,result['parameters'],phase,envs)
            candidate={**result,'parameters':parameters,'before':before,'phase':phase,'delta':delta,
                'confirmed':False,'model':MODEL,'photoBinding':reference,'providerLedger':read(root/'provider-ledger.json'),
                'diagnosticSnapshotOnly':True,'requiresExplicitApplication':True,'automaticGPU':False}
            atomic(root/(phase+'-proposal.json'),candidate)
            record.update(outcome='passed',operationId=result['operationId'],delta=delta)
            print('REAL_PASS',phase,result['operationId'],flush=True)
            if phase=='first':first=candidate;phase='second';feedback=''
            else:
                atomic(root/'two-round-result.json',{'status':'REAL_TWO_ROUND_STRUCTURE_AND_SEMANTICS_PASSED',
                    'first':read(root/'first-proposal.json'),'second':candidate,'diagnosticOnly':True,
                    'businessApplication':'WAITING_CONFIRMATION','GPUExecuted':False,
                    'observedNewCalls':read(root/'provider-ledger.json')['calls']})
                print('TWO_ROUND_PASS_WAITING_APPLICATION_CONFIRMATION',flush=True);return
        except Exception as error:
            record.update(outcome=getattr(error,'code',type(error).__name__))
            ledger=read(root/'provider-ledger.json');last=ledger['records'][-1] if ledger['records'] else {}
            record['diagnosis']={k:last[k] for k in ('validationDiagnosis','parameterValidationDetail','acceptanceDiagnosis','protocol') if k in last}
            diagnosis=last.get('parameterValidationDetail') or last.get('acceptanceDiagnosis') or getattr(error,'code','TASK_SEMANTICS_REJECTED')
            feedback=diagnosis
            print('REAL_REJECT',ordinal,phase,record['outcome'],diagnosis,flush=True)
            if record['outcome'] in ('LANGUAGE_AUTH','LANGUAGE_TIMEOUT','LANGUAGE_UPSTREAM','LANGUAGE_RATE_LIMIT','LANGUAGE_BUDGET_EXHAUSTED'):
                atomic(root/'halt.json',{'reason':record['outcome'],'noAutomaticReissue':True});return
        finally:
            record['seconds']=time.perf_counter()-timer;trace.append(record)
            atomic(root/(f'{ordinal:02d}-result.json'),record);atomic(root/'trace.json',trace)
    atomic(root/'halt.json',{'reason':'ADDITIONAL_20_CALL_LIMIT_REACHED','noAutomaticReissue':True})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--state',type=Path,required=True);p.add_argument('--reference',type=Path,required=True)
    p.add_argument('--prior-ledger',type=Path,action='append',required=True);p.add_argument('--approval-reference',required=True);p.add_argument('--execute',action='store_true')
    p.add_argument('--resume-after-fix',action='store_true')
    p.add_argument('--exit-proof',type=Path)
    options=p.parse_args()
    if options.execute:execute(options)
    else:print('LOCAL_PLAN_ONLY; no key read/provider call/GPU')
