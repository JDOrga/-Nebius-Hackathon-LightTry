"""Freeze/verify local source + actual prompt/schema hashes without network.

The synthetic builder return exists only to capture a request; it is never
used as model evidence. This program cannot send real requests.
"""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(ROOT))
from language import LanguageAdapter

FILES = [
    'project/language.py', 'project/language_contract.py', 'project/language.example.json',
    'project/server.py', 'project/web/app.js', 'project/web/plan.js', 'project/web/sources.js',
    'project/web/index.html', 'project/web/state.js', 'project/web/styles.css',
    'project/data/catalog.json', 'project/data/demo-package.json',
    'project/tests/language_cases.json', 'project/tests/language_regressions.json',
    'project/tests/language_browser_cases.json', 'project/tests/acceptance_checks.py',
    'project/tests/run_language_probe.py', 'project/tests/finish_language_acceptance.py',
    'project/tests/diagnose_language_protocol.py', 'project/tests/run_candidate_offline.py',
    'project/tests/serve_language_fixture.py', 'project/tests/test_language.py',
    'project/tests/test_language_candidate.py', 'project/tests/test_language_acceptance_runner.py',
    'project/tests/test_language_finish.py', 'project/tests/plan.test.js', 'project/tests/state.test.js',
    'project/tests/freeze_language_candidate.py', 'project/tests/language_demo_cases.json',
    'project/tests/demo_policy.py', 'project/tests/demo_web_acceptance.py',
    'project/tests/candidate_budget.py', 'project/tests/test_candidate_budget.py',
    'project/tests/test_demo_acceptance.py', 'project/tests/run_demo_offline.py']


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def snapshot():
    presets = json.loads((ROOT / 'data/catalog.json').read_text(encoding='utf-8'))['presets']
    captured = []
    builder = LanguageAdapter(presets, enabled=True, key='OFFLINE_BUILDER', model='nvidia/Nemotron-3_5-Lightning',
        transport=lambda payload, _: captured.append(payload) or json.dumps({'status':'ready','presetIds':['sunny'],
            'reasons':['离线构造，仅用于捕获请求。'],'excludedIds':[],'unsupported':[],'question':''}))
    builder.recommend({'text':'晴日公园','currentPlan':{'presetIds':[],'excludedIds':[]},'compareThree':False,'responseLanguage':'zh'})
    payload = captured[0]
    config = {'model':builder.model,'endpoint':builder.endpoint,'maxTokens':builder.max_tokens,
        'thinking':builder.thinking_mode,'toolChoice':builder.tool_selection,'outputMode':builder.output_mode,
        'timeoutSeconds':builder.timeout,'maxRepairs':builder.repair_attempts,'maxCallsPerOperation':2,
        'operationBudgetUSD':builder.operation_budget_usd,'frontendWaitMilliseconds':65000,
        'temperature':'provider-default-omitted','store':False,'parallelToolCalls':False,
        'productResponseLanguage':'zh; explicit text request wins; English cases explicitly en'}
    core = {'filesSHA256':{p:hashlib.sha256((REPO/p).read_bytes()).hexdigest() for p in FILES},
            'systemPromptSHA256':hashlib.sha256(payload['messages'][0]['content'].encode()).hexdigest(),
            'schemaSHA256':digest(payload['tools'][0]['function']['parameters']), 'config':config,
            'originalCases':20,'regressionCases':12,'browserOperations':6,
            'acceptancePolicy':'limited-demo-v1; unrelated/injection may safely redirect; human reasons review',
            'resumeAuthorizationRequired':{'maxInitialCalls':6,'maxRepairCalls':6,'maxTotalCalls':12,
                'proposedRunFeeCapUSD':.18,'parentCallLimit':76,'parentTaxInclusiveFeeCapUSD':1.10,
                'priorCalls':20,'remainingBeforeRun':56,'scope':'browser text only; no CLI probes'}}
    return {'candidateId':'lighttry-nemotron-'+digest(core)[:16], 'candidateSHA256':digest(core), **core,
            'sourceGitHead':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
            'committed':False,'modelAcceptance':'not-tested','freezeMechanism':'working-file SHA256; no commit'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'docs/LANGUAGE_CANDIDATE_20261011_DEMO.json')
    parser.add_argument('--verify',action='store_true')
    args = parser.parse_args()
    current = snapshot()
    if args.verify:
        saved = json.loads(args.output.read_text(encoding='utf-8'))
        same = saved['candidateSHA256'] == current['candidateSHA256']
        print('Candidate unchanged:' if same else 'CANDIDATE CHANGED; group results separately:',current['candidateId'])
        raise SystemExit(0 if same else 2)
    if args.output.exists():
        print('Manifest exists; verify it or freeze to a new filename, never overwrite a frozen candidate.')
        raise SystemExit(2)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(current,ensure_ascii=False,indent=2),encoding='utf-8')
    print(current['candidateId'],args.output)
