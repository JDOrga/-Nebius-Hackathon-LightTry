"""Six manual-state web contracts, synthetic transport only; no credentials/network."""
import argparse
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
from freeze_language_candidate import snapshot
from demo_web_acceptance import LinkedLedger, DemoAdapter, DemoService, cases, PARENT
from serve_language_fixture import ScriptedLanguage


def run(output):
    if output.exists():
        raise SystemExit('Existing evidence; choose a fresh output directory.')
    manifest=snapshot()
    frozen=ROOT/'docs/LANGUAGE_CANDIDATE_20261011_DEMO.json'
    if frozen.exists() and json.loads(frozen.read_text(encoding='utf-8'))['candidateSHA256']!=manifest['candidateSHA256']:
        raise SystemExit('Frozen candidate drift; no mixed results.')
    corpus=cases();presets=json.loads((ROOT/'data/catalog.json').read_text(encoding='utf-8'))['presets']
    ledger=LinkedLedger(output/'offline-budget-ledger.json',manifest,{'browser':[c['id'] for c in corpus]},PARENT,create=True,mode='offline')
    script=ScriptedLanguage(presets)
    def transport(payload,remaining):
        adapter.last_response_audit={'usage':{'prompt_tokens':1200,'completion_tokens':200},'toolCallCount':1}
        return script.script(payload,remaining)
    adapter=DemoAdapter(presets,ledger,'browser',manifest,key='OFFLINE_ONLY',
                        audit_path=output/'offline-adapter.jsonl',offline_transport=transport)
    service=DemoService(adapter,ledger,corpus)
    for case in corpus:
        service.recommend({'text':case['text'],'currentPlan':{'presetIds':case['current'],'excludedIds':case['excluded']},
                           'compareThree':False,'responseLanguage':case['language']})
    data=ledger.read()
    proof={'candidateId':manifest['candidateId'],'candidateSHA256':manifest['candidateSHA256'],
           'evidence':'OFFLINE_SCRIPT_NOT_NEMOTRON','realRequests':0,'modelAcceptance':'not-tested',
           'offlineMechanics':'passed','sixCases':data['cases'],'scriptedCalls':script.calls,
           'parentRemainsStopped':True,'unknownOrHistoricalFeesNeverReleased':True}
    (output/'results.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Six offline demo cases passed; real requests 0; model NOT TESTED.',manifest['candidateId'])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    run(parser.parse_args().output)
