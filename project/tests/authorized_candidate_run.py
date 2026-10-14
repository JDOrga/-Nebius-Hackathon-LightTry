"""Authorized frozen R2 CLI + browser acceptance, one shared budget ledger.

Run --check without credentials/network, or --execute only in the privately
configured original shell. No GPU, upload, inference executor or dependency
installation. Product sources, prompt, schema and corpus remain unchanged.
"""
import argparse
import hashlib
import json
import os
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]
REPO=ROOT.parent
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'tests'))
import shared_http as server
from language import LanguageAdapter,LanguageError
from candidate_budget import AuthorizedAdapter,BudgetLedger,verify_candidate,verify_adapter

MANIFEST=ROOT/'docs/LANGUAGE_CANDIDATE_20261011_R2.json'
DEFAULT_RUN=REPO/'.local/language-real-r2-20261011'
HARNESS_FILES=['project/tests/candidate_budget.py','project/tests/authorized_candidate_run.py',
               'project/tests/test_candidate_budget.py','project/tests/start_authorized_r2.py']


def files_hashes():
    return {p:hashlib.sha256((REPO/p).read_bytes()).hexdigest() for p in HARNESS_FILES}


def read_cases():
    cases=json.loads((ROOT/'tests/language_cases.json').read_text(encoding='utf-8'))
    cases+=json.loads((ROOT/'tests/language_regressions.json').read_text(encoding='utf-8'))
    browser=json.loads((ROOT/'tests/language_browser_cases.json').read_text(encoding='utf-8'))
    if len(cases)!=32 or len(browser)!=6 or len({c['id'] for c in cases+browser})!=38:
        raise LanguageError('ACCEPTANCE_CONFIG_DRIFT','冻结用例计数不一致。')
    return cases,browser


def build_body(case,previous=None):
    current={'presetIds':previous['presetIds'][:] if previous else case.get('current',[])[:],
             'excludedIds':previous['excludedIds'][:] if previous else case.get('excluded',[])[:]}
    language=case.get('language','zh' if case['id'].endswith('-zh') else 'en')
    body={'text':case['text'],'currentPlan':current,'compareThree':case.get('check')=='three',
          'responseLanguage':case.get('productLanguage',language)}
    if 'operation' in case:
        body['operation']=case['operation']
    evaluated={**case,'current':current['presetIds'],'excluded':current['excludedIds'],'language':language}
    return body,evaluated


def run_cli(adapter,cases,ledger):
    plans={}
    completed=True
    for case in cases:
        if ledger.read()['status']=='stopped':
            completed=False
            break
        previous=plans.get(case.get('after'))
        if case.get('after') and previous is None:
            ledger.skip('cli',case['id'])
            completed=False
            continue
        body,evaluated=build_body(case,previous)
        try:
            plan,item=adapter.recommend_case(evaluated,body)
            if 'fail' not in item['checks'].values():
                plans[case['id']]=plan
        except LanguageError:
            item=ledger.read()['cases'].get('cli:'+case['id'],{'status':'preflight-failed'})
        print(case['id'],item['status'],'calls',ledger.read()['requestsReserved'],flush=True)
    with ledger.transaction() as data:
        data['cliExecutionCompleted']=completed and len([k for k in data['cases'] if k.startswith('cli:')])==32
        if data['status']!='stopped':
            data['status']='awaiting-browser-arm-and-review'


class BrowserService:
    development_test_mode=False
    def __init__(self,adapter,cases,ledger):
        self.adapter,self.cases,self.ledger=adapter,cases,ledger
        self.lock=threading.Lock()

    def capabilities(self):
        return {'enabled':True,'developmentTestMode':False,
                'message':'R2 已授权真实 Token Factory 文字复验；共用 76 次 / $1.10 账本，GPU 关闭。'}

    def recommend(self,body):
        if not self.lock.acquire(blocking=False):
            raise LanguageError('LANGUAGE_BUSY','正在推荐；重复点击未计入上游调用。',409)
        try:
            data=self.ledger.read()
            remaining=[c for c in self.cases if 'browser:'+c['id'] not in data['operations']]
            if not remaining:
                raise LanguageError('ACCEPTANCE_UNPLANNED_OPERATION','6 项网页操作已结束，不追加调用。')
            case=remaining[0]
            if not isinstance(body,dict) or body.get('text','').strip()!=case['text'] or body.get('responseLanguage')!=case['language']:
                raise LanguageError('ACCEPTANCE_UNPLANNED_OPERATION','请只执行已计划的下一项网页文字及语言设置。')
            checks={'browser-explicit-zh':'sunny','browser-three-zh':'three','browser-remove-zh':'first-only',
                    'browser-replace-en':'different','browser-exclude-zh':'no-night','browser-unexclude-zh':'exact'}
            current=body['currentPlan']
            evaluated={**case,'check':checks[case['id']],'current':current['presetIds'],
                       'excluded':current['excludedIds']}
            if case['id']=='browser-unexclude-zh':
                evaluated.update(expected=current['presetIds'],expectedExcluded=[p for p in current['excludedIds'] if p!='street'])
            plan,_=self.adapter.recommend_case(evaluated,body)
            return plan
        except LanguageError as error:
            if error.code=='ACCEPTANCE_UNPLANNED_OPERATION':
                self.ledger.stop(error.code)
            raise
        finally:
            self.lock.release()


def run_server(adapter,browser_cases,ledger,catalog,assets,port):
    service=BrowserService(adapter,browser_cases,ledger)
    class AcceptanceHandler(server.Handler):
        task_store=None
        language_service=service
        def do_GET(self):
            if urlsplit(self.path).path=='/api/acceptance/status':
                if not self.valid_host():
                    return self.json_response({'error':'invalid host'},403)
                data=ledger.read()
                remaining=[c for c in browser_cases if 'browser:'+c['id'] not in data['operations']]
                return self.json_response({'candidateId':data['candidateId'],'status':data['status'],
                    'requestsReserved':data['requestsReserved'],'browserArmed':data['browserArmed'],
                    'nextBrowserCase':remaining[0] if remaining else None,'gpuEnabled':False})
            return super().do_GET()
    AcceptanceHandler.catalog=catalog
    AcceptanceHandler.assets_dir=server.resolve_assets_dir(assets)
    return ThreadingHTTPServer(('127.0.0.1',port),AcceptanceHandler)


def checks(args,manifest):
    verify_candidate(manifest)
    read_cases()
    catalog=server.load_catalog(args.assets_dir)
    proof=args.run_dir/'budget-preflight.json'
    if not proof.exists():
        raise LanguageError('ACCEPTANCE_BUDGET_STOP','缺少统一账本离线预检证明，不能发送真实请求。')
    preflight=json.loads(proof.read_text(encoding='utf-8'))
    if (preflight.get('status')!='passed' or preflight.get('candidateSHA256')!=manifest['candidateSHA256'] or
        preflight.get('harnessSHA256')!=files_hashes() or preflight.get('realRequests')!=0):
        raise LanguageError('ACCEPTANCE_CONFIG_DRIFT','预算预检证明与当前启动器不一致。')
    return catalog


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    actions=parser.add_mutually_exclusive_group(required=True)
    actions.add_argument('--check',action='store_true')
    actions.add_argument('--execute',action='store_true')
    actions.add_argument('--arm-browser',action='store_true')
    actions.add_argument('--stop',action='store_true')
    parser.add_argument('--run-dir',type=Path,default=DEFAULT_RUN)
    parser.add_argument('--assets-dir',default=str(REPO/'.local/demo-candidate-20261010/demo-assets'))
    parser.add_argument('--port',type=int,default=8790)
    args=parser.parse_args()
    manifest=json.loads(MANIFEST.read_text(encoding='utf-8'))
    cases,browser=read_cases()
    allowed={'cli':[c['id'] for c in cases],'browser':[c['id'] for c in browser]}
    path=args.run_dir/'budget-ledger.json'
    if args.stop or args.arm_browser:
        ledger=BudgetLedger(path,manifest,allowed)
        if args.stop:
            ledger.stop('OPERATOR_STOP')
            print('Stopped; no budget reset.')
            return 0
        checks(args,manifest)
        with ledger.transaction() as data:
            if data['status']=='stopped' or not data['cliExecutionCompleted']:
                print('CLI incomplete/stopped; browser stays blocked.')
                return 2
            data['browserArmed']=True
            data['status']='awaiting-browser'
        print('Six planned browser operations armed; same ledger.')
        return 0
    catalog=checks(args,manifest)
    if args.check:
        print('Frozen R2 + shared budget offline proof verified. No real API calls.')
        return 0
    configured=LanguageAdapter.from_env(json.loads((ROOT/'data/catalog.json').read_text(encoding='utf-8'))['presets'])
    verify_adapter(configured,manifest)
    if path.exists():
        print('Existing ledger; do not execute again. Inspect report or stop.')
        return 2
    ledger=BudgetLedger(path,manifest,allowed,create=True,harness_hashes=files_hashes())
    cli=AuthorizedAdapter(catalog['presets'],ledger,'cli',manifest,key=configured._key,audit_path=args.run_dir/'adapter-cli.jsonl')
    web=AuthorizedAdapter(catalog['presets'],ledger,'browser',manifest,key=configured._key,audit_path=args.run_dir/'adapter-browser.jsonl')
    http=run_server(web,browser,ledger,catalog,args.assets_dir,args.port)
    thread=threading.Thread(target=http.serve_forever,daemon=True)
    thread.start()
    print('REAL R2 TEXT ACCEPTANCE; GPU OFF; no photos:',f'http://127.0.0.1:{args.port}',flush=True)
    try:
        run_cli(cli,cases,ledger)
        state=ledger.read()
        print('CLI phase:',state['status'],'reserved requests:',state['requestsReserved'],flush=True)
        if state['status']=='stopped':
            return 1
        print('Browser remains blocked until operator reviews CLI and --arm-browser. Ctrl+C closes this service.',flush=True)
        while not (args.run_dir/'close-service').exists():
            if ledger.read()['status']=='stopped':
                return 1
            if len([k for k in ledger.read()['cases'] if k.startswith('browser:')])==6:
                with ledger.transaction() as data:
                    data['status']='execution-completed-requires-human-review'
                return 3
            threading.Event().wait(.5)
        return 3
    except KeyboardInterrupt:
        ledger.stop('OPERATOR_INTERRUPTED')
        return 1
    finally:
        http.shutdown();http.server_close();thread.join(timeout=2)


if __name__=='__main__':
    try:
        raise SystemExit(main())
    except LanguageError as error:
        print(error.code+': '+error.message)
        raise SystemExit(2)
