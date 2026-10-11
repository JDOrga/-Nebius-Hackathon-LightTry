"""Offline verification of the shared CLI/browser authorization boundary."""
import contextlib
import io
import json
import multiprocessing
import sys
import tempfile
import unittest
from urllib.request import Request,urlopen
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
from language import LanguageError
from freeze_language_candidate import snapshot
from candidate_budget import AuthorizedAdapter,BudgetLedger,RESERVE,verify_adapter
from authorized_candidate_run import build_body,read_cases,files_hashes,run_cli,BrowserService,run_server
from serve_language_fixture import ScriptedLanguage


def competing_begin(path,manifest,queue):
    try:
        ledger=BudgetLedger(path,manifest,{'cli':['last-cli'],'browser':['last-web']})
        ledger.begin('cli','last-cli')
        queue.put('accepted')
    except LanguageError:
        queue.put('rejected')


class SharedBudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name)
        self.manifest=snapshot()
        self.cases,self.browser=read_cases()
        self.allowed={'cli':[c['id'] for c in self.cases],'browser':[c['id'] for c in self.browser]}
        self.ledger=BudgetLedger(self.folder/'ledger.json',self.manifest,self.allowed,create=True,mode='offline')
        self.presets=json.loads((ROOT/'data/catalog.json').read_text(encoding='utf-8'))['presets']

    def adapter(self,source='cli',responses=None,missing=False):
        script=ScriptedLanguage(self.presets)
        iterator=iter(responses) if responses else None
        def transport(payload,remaining):
            data=self.ledger.read()
            active=data['operations'][adapter.context]
            self.assertEqual(active['calls'][-1]['status'],'reserved-before-send')
            self.assertEqual(data['requestsReserved'],sum(len(o['calls']) for o in data['operations'].values()))
            adapter.last_response_audit={'usage':{} if missing else {'prompt_tokens':1200,'completion_tokens':120},'toolCallCount':1}
            answer=next(iterator) if iterator else script.script(payload,remaining)
            if isinstance(answer,LanguageError):raise answer
            return answer
        adapter=AuthorizedAdapter(self.presets,self.ledger,source,self.manifest,key='OFFLINE_SYNTHETIC_KEY',
            audit_path=self.folder/(source+'.jsonl'),offline_transport=transport)
        return adapter

    def arm(self):
        with self.ledger.transaction() as data:
            data['browserArmed']=True

    def test_full_32_cli_and_6_browser_share_one_76_counter(self):
        adapter=self.adapter()
        with contextlib.redirect_stdout(io.StringIO()):run_cli(adapter,self.cases,self.ledger)
        data=self.ledger.read()
        self.assertTrue(data['cliExecutionCompleted']);self.assertEqual(data['requestsReserved'],32)
        self.arm()
        web=self.adapter('browser')
        current={'presetIds':[],'excludedIds':[]}
        service=BrowserService(web,self.browser,self.ledger)
        for case in self.browser:
            value=service.recommend({'text':case['text'],'currentPlan':current,'compareThree':False,'responseLanguage':case['language']})
            current={'presetIds':value['presetIds'],'excludedIds':value['excludedIds']}
        self.assertEqual(self.ledger.read()['requestsReserved'],38)
        self.assertNotIn('OFFLINE_SYNTHETIC_KEY',self.ledger.path.read_text())

    def test_format_repair_uses_same_counter_and_preserves_first_failure(self):
        plan=json.dumps({'status':'ready','presetIds':['sunny'],'reasons':['自然日光氛围。'],
                         'excludedIds':[],'unsupported':[],'question':''})
        adapter=self.adapter(responses=['{}',plan])
        body,case=build_body(self.cases[0])
        adapter.recommend_case(case,body)
        op=self.ledger.read()['operations']['cli:explicit-zh']
        self.assertEqual(len(op['calls']),2);self.assertTrue(op['calls'][1]['isRepair'])
        self.assertEqual(op['adapterAudit']['attempts'][0]['errorCode'],'INVALID_MODEL_OUTPUT')

    def test_real_loopback_browser_route_and_cli_use_same_ledger_gpu_is_off(self):
        import threading
        cli=self.adapter()
        body,case=build_body(self.cases[0]);cli.recommend_case(case,body)
        self.arm()
        web=self.adapter('browser')
        assets=str(ROOT.parent/'.local/demo-candidate-20261010/demo-assets')
        http=run_server(web,self.browser,self.ledger,{'presets':self.presets},assets,0)
        thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
        base=f'http://127.0.0.1:{http.server_port}'
        try:
            request=Request(base+'/api/language/recommend',data=json.dumps(body).encode(),headers={
                'Content-Type':'application/json','Origin':base,'X-LightTry-Token':http.RequestHandlerClass.csrf_token})
            with urlopen(request) as response:self.assertEqual(json.load(response)['presetIds'],['sunny'])
            with urlopen(base+'/api/inference') as response:self.assertFalse(json.load(response)['enabled'])
            self.assertEqual(self.ledger.read()['requestsReserved'],2)
        finally:
            http.shutdown();http.server_close();thread.join(2)

    def test_actual_runtime_config_drift_does_not_get_new_budget(self):
        adapter=self.adapter()
        self.assertEqual(verify_adapter(adapter,self.manifest)['maxTokens'],40960)
        adapter.timeout=59
        with self.assertRaises(LanguageError):verify_adapter(adapter,self.manifest)
        self.assertEqual(self.ledger.read()['requestsReserved'],0)

    def test_unknown_usage_retains_call_reserve_and_blocks_repair(self):
        adapter=self.adapter(responses=['{}'],missing=True)
        body,case=build_body(self.cases[0])
        with self.assertRaises(LanguageError) as error:adapter.recommend_case(case,body)
        data=self.ledger.read()
        self.assertEqual(error.exception.code,'ACCEPTANCE_MISSING_USAGE')
        self.assertEqual(data['requestsReserved'],1);self.assertEqual(data['status'],'stopped')
        self.assertAlmostEqual(BudgetLedger.committed_cost(data),RESERVE)

    def test_auth_error_stops_and_is_counted_even_with_usage(self):
        adapter=self.adapter(responses=[LanguageError('LANGUAGE_AUTH','fixed')])
        body,case=build_body(self.cases[0])
        with self.assertRaises(LanguageError):adapter.recommend_case(case,body)
        data=self.ledger.read()
        self.assertEqual(data['requestsReserved'],1);self.assertEqual(data['stopReason'],'LANGUAGE_AUTH')

    def test_crash_before_response_stays_counted_after_reopen(self):
        key=self.ledger.begin('cli','explicit-zh');self.ledger.before_send(key)
        reopened=BudgetLedger(self.ledger.path,self.manifest,self.allowed)
        self.assertEqual(reopened.read()['requestsReserved'],1)
        self.assertAlmostEqual(BudgetLedger.committed_cost(reopened.read()),RESERVE)
        with self.assertRaises(LanguageError):reopened.begin('cli','explicit-zh')

    def test_browser_cannot_get_independent_extra_budget(self):
        self.arm()
        with self.ledger.transaction() as data:data['requestsReserved']=75
        with self.assertRaises(LanguageError):self.ledger.begin('browser','browser-explicit-zh')
        self.assertEqual(self.ledger.read()['requestsReserved'],75)

    def test_fee_guard_blocks_before_sending(self):
        with self.ledger.transaction() as data:
            data['operations']['prior']={'heldSlots':0,'calls':[{'reportedPretaxUSD':1.1}]}
        with self.assertRaises(LanguageError):self.ledger.begin('cli','explicit-zh')
        self.assertEqual(self.ledger.read()['requestsReserved'],0)

    def test_restart_cannot_overwrite_authorization_or_reset_counter(self):
        with self.assertRaises(LanguageError):
            BudgetLedger(self.ledger.path,self.manifest,self.allowed,create=True,mode='offline')

    def test_two_consecutive_independent_failures_stop_systematic_run(self):
        adapter=self.adapter(responses=['{}']*4)
        for source in self.cases[:2]:
            body,case=build_body(source)
            with self.assertRaises(LanguageError):adapter.recommend_case(case,body)
        data=self.ledger.read()
        self.assertEqual(data['requestsReserved'],4);self.assertEqual(data['stopReason'],'SYSTEMATIC_ACCEPTANCE_FAILURE')

    def test_drift_in_request_is_rejected_without_outbound_count(self):
        adapter=self.adapter()
        adapter.context=self.ledger.begin('cli','explicit-zh')
        with self.assertRaises(LanguageError):adapter.counted({'model':'different'},60)
        self.assertEqual(self.ledger.read()['requestsReserved'],0)

    def test_multiprocess_duplicate_cannot_reserve_twice(self):
        path=self.folder/'concurrent.json'
        ledger=BudgetLedger(path,self.manifest,{'cli':['last-cli'],'browser':['last-web']},create=True,mode='offline')
        with ledger.transaction() as data:data['requestsReserved']=74
        ctx=multiprocessing.get_context('spawn');queue=ctx.Queue()
        processes=[ctx.Process(target=competing_begin,args=(str(path),self.manifest,queue)) for _ in range(2)]
        for process in processes:process.start()
        for process in processes:process.join(15);self.assertEqual(process.exitcode,0)
        self.assertEqual(sorted([queue.get(timeout=2),queue.get(timeout=2)]),['accepted','rejected'])


if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(SharedBudgetTests)
    result=unittest.TextTestRunner(verbosity=1).run(suite)
    if result.wasSuccessful():
        folder=ROOT.parent/'.local/language-real-r2-20261011'
        folder.mkdir(parents=True,exist_ok=True)
        proof={'status':'passed','candidateSHA256':snapshot()['candidateSHA256'],
               'harnessSHA256':files_hashes(),'offlineTestsPassed':result.testsRun,'realRequests':0,
               'coverage':['shared-cli-browser','repair-counting','unknown-usage','pre-send-reservation',
                           'tax-fee-envelope','76-limit','crash-reopen','multiprocess-race','systematic-stop']}
        (folder/'budget-preflight.json').write_text(json.dumps(proof,indent=2),encoding='utf-8')
    raise SystemExit(0 if result.wasSuccessful() else 1)
