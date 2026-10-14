"""Six browser operations only. --check is offline; --serve needs explicit renewal.

One canonical child record links to the immutable stopped R2 authorization.
No CLI model probes, photo upload, task executor, GPU, or automatic continuation.
"""
import argparse
import copy
import hashlib
import json
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'tests'))
import shared_http as server
from language import LanguageError
from language_contract import language_review
from candidate_budget import BudgetLedger, AuthorizedAdapter, verify_candidate
from demo_policy import demo_case_check, safety_review

MANIFEST = ROOT/'docs/LANGUAGE_CANDIDATE_20261011_DEMO.json'
PARENT = REPO/'.local/language-real-r2-20261011/budget-ledger.json'
RUN = REPO/'.local/language-demo-real-20261011'
RUN_CAP = .18


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def cases():
    return json.loads((ROOT/'tests/language_demo_cases.json').read_text(encoding='utf-8'))


class LinkedLedger(BudgetLedger):
    def __init__(self, path, manifest, allowed, parent, *, create=False, approval=None, mode='real'):
        self.parent = Path(parent)
        baseline = json.loads(self.parent.read_text(encoding='utf-8'))
        baseline_sha = sha(self.parent)
        if create:
            if mode == 'real' and (Path(path).resolve() != (RUN/'budget-ledger.json').resolve() or
                    self.parent.resolve() != PARENT.resolve()):
                raise LanguageError('ACCEPTANCE_BUDGET_STOP', '真实复验只能使用唯一关联记录，不能另起预算。')
            if (baseline.get('status') != 'stopped' or baseline.get('requestsReserved') != 20 or
                    baseline.get('authorization', {}).get('newCalls') != 76 or
                    baseline['authorization'].get('taxInclusiveFeeCapUSD') != 1.10):
                raise LanguageError('ACCEPTANCE_BUDGET_STOP', '原 R2 授权/停止/计数不符，未恢复。')
            if mode == 'real' and (not isinstance(approval, dict) or approval.get('approved') is not True or
                    approval.get('approvedBy') != 'WJX' or not approval.get('explicitUserMessage') or
                    approval.get('candidateSHA256') != manifest['candidateSHA256'] or
                    approval.get('parentLedgerSHA256') != baseline_sha or
                    approval.get('maxCalls') != 12 or approval.get('feeCapUSD') != RUN_CAP):
                raise LanguageError('ACCEPTANCE_BUDGET_STOP', '缺少本轮明确恢复授权；原剩余额度不能自动使用。')
        super().__init__(path, manifest, allowed, create=create, mode=mode)
        if create:
            with self.transaction() as data:
                data.update(parentAuthorization={'runId':baseline['runId'], 'ledgerPath':str(self.parent.resolve()),
                    'ledgerSHA256':baseline_sha, 'candidateId':baseline['candidateId'],
                    'stopReason':baseline['stopReason']}, priorRequestsReserved=baseline['requestsReserved'],
                    requestsReserved=baseline['requestsReserved'], priorCommittedPretaxUSD=BudgetLedger.committed_cost(baseline),
                    resumeApproval=copy.deepcopy(approval) if mode=='real' else 'OFFLINE TEST ONLY',
                    browserArmed=True, status='awaiting-browser', stopOnConsecutiveFailure=False,
                    protocolFailureStopAfter=2)
                data['authorization'] = {**baseline['authorization'], 'cumulativeCallLimit':76,
                    'runCallLimit':12, 'runFeeCapUSD':RUN_CAP, 'initialOperations':6,
                    'scope':'Six listed browser text operations only; no CLI probes; GPU/photos/tasks off'}
        self.parent_sha = self.read()['parentAuthorization']['ledgerSHA256']
        self.check_parent()

    def check_parent(self):
        if sha(self.parent) != self.parent_sha:
            self.stop('ACCEPTANCE_CONFIG_DRIFT')
            raise LanguageError('ACCEPTANCE_CONFIG_DRIFT', '原账本发生变化；停止，保留未知费用。')

    def begin(self, source, case_id):
        self.check_parent()
        return super().begin(source, case_id)

    def before_send(self, key):
        self.check_parent()
        return super().before_send(key)

    def finish(self, key, item):
        super().finish(key, item)
        # State/safety failures are critical. Wording quality remains for human
        # review; repeated protocol failure retains the shared automatic stop.
        if item.get('checks', {}).get('selectionExclusions') == 'fail' or item.get('errorCode') == 'LANGUAGE_CONSTRAINT_VIOLATION':
            self.stop('CRITICAL_STATE_OR_REDIRECT_FAILURE')


class DemoAdapter(AuthorizedAdapter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.record_plans = True
        self.case_dimensions = lambda case, plan: {
            'protocolStructure':'pass', 'selectionExclusions':safety_review(case,plan) if case['check']=='safe-redirect' else
                'pass' if demo_case_check(case,plan) else 'fail',
            'replyLanguage':language_review(plan,case['language']), 'presetCapabilityReasons':'pending-human-review',
            'interaction':'not-tested'}

    def recommend_case(self, case, body):
        # Guard runs inside LanguageAdapter's single repair / shared 60s loop.
        self.response_guard = lambda plan: safety_review(case,plan) != 'fail' if case['check']=='safe-redirect' else demo_case_check(case, plan)
        try:
            return super().recommend_case(case, body)
        finally:
            self.response_guard = None


class DemoService:
    development_test_mode = False
    def __init__(self, adapter, ledger, corpus):
        self.adapter, self.ledger, self.corpus = adapter, ledger, corpus
        self.lock = threading.Lock()

    def capabilities(self):
        return {'enabled':self.ledger.read()['status'] != 'stopped', 'developmentTestMode':False,
                'message':'限定网页文字复验：六项，最多 12 次；累计扣除原授权，生成关闭。'}

    def recommend(self, body):
        if not self.lock.acquire(blocking=False):
            raise LanguageError('LANGUAGE_BUSY', '正在推荐；重复点击未发送。', 409)
        try:
            data = self.ledger.read()
            remaining = [c for c in self.corpus if 'browser:'+c['id'] not in data['operations']]
            if not remaining:
                raise LanguageError('ACCEPTANCE_UNPLANNED_OPERATION', '六项已完成；不追加推荐。')
            case = remaining[0]
            if data['cases'] and data.get('evidenceMode')=='real':
                observation_path = self.ledger.path.parent/'browser-observations.json'
                observations = json.loads(observation_path.read_text(encoding='utf-8')) if observation_path.exists() else {}
                last_case = next(reversed(data['cases']))
                if observations.get(last_case,{}).get('safeToContinue') is not True:
                    raise LanguageError('ACCEPTANCE_BUDGET_STOP', '上一项实际页面与安全状态尚未记录复核；未发送。')
            expected_body = {'text':case['text'], 'currentPlan':{'presetIds':case['current'], 'excludedIds':case['excluded']},
                             'compareThree':False, 'responseLanguage':case['language']}
            if body != expected_body:
                raise LanguageError('ACCEPTANCE_UNPLANNED_OPERATION', '请先用手动控件准备本项状态、文字和语言；未发送。')
            plan, _ = self.adapter.recommend_case(case, body)
            return plan
        finally:
            self.lock.release()


def make_server(service, catalog, assets, port):
    class DemoHandler(server.Handler):
        task_store = None  # No executor and no upload/task submit route.
        language_service = service
        def do_GET(self):
            if urlsplit(self.path).path == '/api/acceptance/status':
                if not self.valid_host():
                    return self.json_response({'error':'invalid host'},403)
                data = service.ledger.read()
                remaining = [c for c in service.corpus if 'browser:'+c['id'] not in data['operations']]
                return self.json_response({'candidateId':data['candidateId'], 'status':data['status'],
                    'cumulativeRequests':data['requestsReserved'], 'requestsThisRun':data['requestsReserved']-data['priorRequestsReserved'],
                    'nextCase':remaining[0] if remaining else None, 'gpuEnabled':False})
            return super().do_GET()
    DemoHandler.catalog, DemoHandler.assets_dir = catalog, server.resolve_assets_dir(assets)
    return ThreadingHTTPServer(('127.0.0.1',port), DemoHandler)


def export_report(ledger):
    data = ledger.read()
    observation_path = ledger.path.parent/'browser-observations.json'
    report = {**data, 'R2Acceptance':'failed-unchanged', 'requestsThisRun':data['requestsReserved']-data['priorRequestsReserved'],
              'modelAcceptance':'failed' if data['status']=='stopped' else 'pending-human-review',
              'browserObservations':json.loads(observation_path.read_text(encoding='utf-8')) if observation_path.exists() else {},
              'browserObservationFile':'browser-observations.json',
              'requiredHumanEvidence':['click-to-final wait','rendered final selection/exclusions','language',
                  'feature-grounded reasons','safe redirect without unrelated continuation','no new task/photo/GPU'],
              'fullStabilityAcceptance':False}
    (ledger.path.parent/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--check',action='store_true')
    action.add_argument('--serve',action='store_true')
    parser.add_argument('--port',type=int,default=8791)
    args = parser.parse_args()
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    verify_candidate(manifest)
    baseline = json.loads(PARENT.read_text(encoding='utf-8'))
    print('R2 remains',baseline['status'],'used',baseline['requestsReserved'],'remaining',76-baseline['requestsReserved'])
    if args.check:
        print('OFFLINE ONLY; six browser cases / <=12 calls / proposed $0.18; explicit renewal still required.')
        return 0
    approval_path = RUN/'approval.json'
    if not approval_path.exists():
        raise LanguageError('ACCEPTANCE_BUDGET_STOP', '未获本轮明确同意，文字服务保持关闭。')
    if (RUN/'budget-ledger.json').exists():
        raise LanguageError('ACCEPTANCE_BUDGET_STOP', '已有本轮运行账本；禁止覆盖、清零或自动续跑。')
    corpus = cases()
    catalog = server.load_catalog(str(REPO/'.local/demo-candidate-20261010/demo-assets'))
    # Read just the already privately configured key; all nonsecret settings
    # come from the frozen manifest, so stale environment options cannot drift.
    import os
    key = os.environ.get('LIGHTTRY_TOKEN_FACTORY_KEY','').strip()
    if not key:
        raise LanguageError('LANGUAGE_NOT_CONFIGURED', '请在原私下配置 Key 的终端运行。')
    ledger = LinkedLedger(RUN/'budget-ledger.json',manifest,{'browser':[c['id'] for c in corpus]},PARENT,
                          create=True,approval=json.loads(approval_path.read_text(encoding='utf-8')))
    adapter = DemoAdapter(catalog['presets'],ledger,'browser',manifest,key=key,audit_path=RUN/'adapter-browser.jsonl')
    service = DemoService(adapter,ledger,corpus)
    http = make_server(service,catalog,str(REPO/'.local/demo-candidate-20261010/demo-assets'),args.port)
    thread = threading.Thread(target=http.serve_forever,daemon=True)
    thread.start()
    print(f'Only six manually prepared browser operations: http://127.0.0.1:{args.port}',flush=True)
    try:
        while True:
            data = ledger.read()
            if data['status']=='stopped':
                return 1
            if len(data['cases'])==6:
                with ledger.transaction() as current:
                    current['status']='execution-completed-requires-human-review'
                return 3
            threading.Event().wait(.5)
    except KeyboardInterrupt:
        ledger.stop('OPERATOR_INTERRUPTED')
        return 1
    finally:
        http.shutdown(); http.server_close(); thread.join(2)
        export_report(ledger)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except LanguageError as error:
        print(error.code+': '+error.message)
        raise SystemExit(2)
