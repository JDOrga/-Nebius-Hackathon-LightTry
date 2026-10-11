"""Offline successor policy, linked budget and actual loopback web regressions."""
import copy
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import Request, urlopen
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT)); sys.path.insert(0,str(ROOT/'tests'))
from language import LanguageError
from freeze_language_candidate import snapshot
from candidate_budget import BudgetLedger, RESERVE
from demo_web_acceptance import LinkedLedger, DemoAdapter, DemoService, cases, make_server
from demo_policy import demo_case_check, lighting_question, safety_review
from serve_language_fixture import ScriptedLanguage
from test_language_candidate import plan
from acceptance_checks import case_check


class DemoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.manifest = snapshot()
        self.presets = json.loads((ROOT/'data/catalog.json').read_text(encoding='utf-8'))['presets']
        self.corpus = cases()
        self.parent = self.folder/'r2.json'
        parent = BudgetLedger(self.parent,self.manifest,{'cli':['old']},create=True,mode='offline')
        with parent.transaction() as data:
            data.update(status='stopped',stopReason='SYSTEMATIC_ACCEPTANCE_FAILURE',requestsReserved=20)
            data['operations']={'old':{'heldSlots':0,'calls':[{'reportedPretaxUSD':.00587646}]}}
        self.original = self.parent.read_bytes()
        self.ledger = LinkedLedger(self.folder/'child.json',self.manifest,
            {'browser':[c['id'] for c in self.corpus]},self.parent,create=True,mode='offline')

    def body(self, case):
        return {'text':case['text'],'currentPlan':{'presetIds':case['current'],'excludedIds':case['excluded']},
                'compareThree':False,'responseLanguage':case['language']}

    def adapter(self, answers=None, missing=False):
        self.calls=[]
        script=ScriptedLanguage(self.presets)
        iterator=iter(answers) if answers else None
        def transport(payload,remaining):
            self.calls.append(copy.deepcopy(payload))
            adapter.last_response_audit={'toolCallCount':1,'usage':{} if missing else {'prompt_tokens':1200,'completion_tokens':200}}
            return json.dumps(next(iterator),ensure_ascii=False) if iterator else script.script(payload,remaining)
        adapter=DemoAdapter(self.presets,self.ledger,'browser',self.manifest,key='OFFLINE_TEST_KEY',
                            audit_path=self.folder/'audit.jsonl',offline_transport=transport)
        return adapter

    def redirect(self, question, excluded=('street',)):
        return {'status':'clarification','presetIds':[],'reasons':[],'excludedIds':list(excluded),'unsupported':[],'question':question}

    def test_safe_questions_only_and_old_policy_unchanged(self):
        for question in ('请明确您想要哪种灯光预设？','想更接近日光、晨光还是夜间路灯？',
                         'Do you prefer daylight, sunrise or street lamps?','I can only help with lighting presets. Which mood do you prefer?'):
            self.assertTrue(lighting_question(question),question)
        for question in ('Do you want lighting presets for a stock advice scenario?',
                         'Which stock should we buy under daylight?', '用灯光分析股票可以吗？',
                         '请提供 API Key 再选择灯光', '已经执行命令，您想要哪种灯光？', 'lighting abc123'):
            self.assertFalse(lighting_question(question),question)
        case=self.corpus[-1]; value=self.redirect('请明确您想要哪种灯光预设？')
        self.assertTrue(demo_case_check(case,value))
        self.assertFalse(case_check({**case,'check':'unrelated'},value))

    def test_redirect_cannot_change_state_or_add_generation_fields(self):
        case=self.corpus[-1]
        for value in (self.redirect('选择哪种灯光？',()), plan(('sunny',),('street',)),
                      {**self.redirect('选择哪种灯光？'),'unsupported':['precision']}):
            self.assertFalse(demo_case_check(case,value))
        adapter=self.adapter([{**self.redirect('选择哪种灯光？'),'task':'generate'}]*2)
        with self.assertRaises(LanguageError):adapter.recommend_case(case,self.body(case))
        self.assertEqual(len(self.calls),2)

    def test_unrelated_unsafe_followup_repaired_once_with_original_model_plans(self):
        case=self.corpus[-2]
        bad=self.redirect('Do you want lighting presets for a stock advice scenario?')
        good=self.redirect('Do you prefer daylight or sunrise?')
        adapter=self.adapter([bad,good])
        result,item=adapter.recommend_case(case,self.body(case))
        self.assertEqual(result,good)
        self.assertEqual(len(self.calls),2)
        attempts=item['operationAudit']['attempts']
        self.assertEqual(attempts[0]['plan'],bad); self.assertEqual(attempts[1]['plan'],good)
        self.assertEqual(attempts[0]['errorCode'],'LANGUAGE_CONSTRAINT_VIOLATION')
        self.assertEqual(item['checks']['selectionExclusions'],'pass')
        self.assertEqual(self.ledger.read()['requestsReserved'],22)

    def test_all_six_loopback_operations_share_parent_budget_no_gpu(self):
        adapter=self.adapter();service=DemoService(adapter,self.ledger,self.corpus)
        assets=str(ROOT.parent/'.local/demo-candidate-20261010/demo-assets')
        http=make_server(service,{'presets':self.presets},assets,0)
        thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
        base=f'http://127.0.0.1:{http.server_port}'
        try:
            for case in self.corpus:
                request=Request(base+'/api/language/recommend',data=json.dumps(self.body(case)).encode(),headers={
                    'Content-Type':'application/json','Origin':base,'X-LightTry-Token':http.RequestHandlerClass.csrf_token})
                with urlopen(request) as response:
                    self.assertTrue(demo_case_check(case,json.load(response)))
            with urlopen(base+'/api/inference') as response:self.assertFalse(json.load(response)['enabled'])
            self.assertEqual(self.ledger.read()['requestsReserved'],26)
            self.assertEqual(self.parent.read_bytes(),self.original)
            with self.assertRaises(LanguageError):service.recommend(self.body(self.corpus[-1]))
            self.assertEqual(len(self.calls),6)
        finally:
            http.shutdown();http.server_close();thread.join(2)

    def test_wrong_manual_prestate_never_sends_or_consumes_case(self):
        adapter=self.adapter();service=DemoService(adapter,self.ledger,self.corpus)
        body=self.body(self.corpus[0]);body['currentPlan']['excludedIds']=[]
        with self.assertRaises(LanguageError):service.recommend(body)
        self.assertEqual(self.calls,[]);self.assertEqual(self.ledger.read()['requestsReserved'],20)

    def test_cli_cannot_add_probes_to_browser_round(self):
        with self.assertRaises(LanguageError):self.ledger.begin('cli',self.corpus[0]['id'])
        self.assertEqual(self.ledger.read()['requestsReserved'],20)

    def test_twelve_cap_is_additional_to_prior_twenty(self):
        with self.ledger.transaction() as data:data['requestsReserved']=31
        with self.assertRaises(LanguageError):self.ledger.begin('browser',self.corpus[0]['id'])
        self.assertEqual(self.ledger.read()['requestsReserved'],31)

    def test_unknown_fee_never_released_by_new_candidate_or_restart(self):
        adapter=self.adapter(missing=True)
        case=self.corpus[0]
        with self.assertRaises(LanguageError):adapter.recommend_case(case,self.body(case))
        data=self.ledger.read()
        self.assertEqual(data['requestsReserved'],21)
        self.assertAlmostEqual(BudgetLedger.committed_cost(data),.00587646+RESERVE)
        reopened=LinkedLedger(self.ledger.path,self.manifest,self.ledger.allowed,self.parent)
        with self.assertRaises(LanguageError):reopened.begin('browser',self.corpus[1]['id'])
        self.assertEqual(self.parent.read_bytes(),self.original)

    def test_parent_unknown_fee_is_carried_into_child(self):
        unknown=self.folder/'unknown-parent.json'
        data=json.loads(self.original)
        data['operations']['old']['calls'].append({'billing':'unknown','pretaxReserveUSD':RESERVE})
        unknown.write_text(json.dumps(data),encoding='utf-8')
        child=LinkedLedger(self.folder/'unknown-child.json',self.manifest,self.ledger.allowed,unknown,create=True,mode='offline')
        self.assertAlmostEqual(BudgetLedger.committed_cost(child.read()),.00587646+RESERVE)

    def test_parent_drift_cannot_resume_or_reset(self):
        self.parent.write_bytes(self.original+b' ')
        with self.assertRaises(LanguageError):self.ledger.begin('browser',self.corpus[0]['id'])
        self.assertEqual(self.ledger.read()['status'],'stopped')

    def test_no_explicit_approval_cannot_create_real_record(self):
        path=self.folder/'unapproved.json'
        with self.assertRaises(LanguageError):LinkedLedger(path,self.manifest,self.ledger.allowed,self.parent,create=True)
        self.assertFalse(path.exists())

    def test_state_violation_stops_after_one_shared_repair(self):
        case=self.corpus[1]
        adapter=self.adapter([plan(('sunny',),()),plan(('sunny',),('street','sunrise'))])
        with self.assertRaises(LanguageError):adapter.recommend_case(case,self.body(case))
        self.assertEqual(len(self.calls),2);self.assertEqual(self.ledger.read()['status'],'stopped')

    def test_simple_warm_reason_is_not_replaced_or_failed_for_missing_disclaimer(self):
        case=self.corpus[3]; value=plan(('sunrise',),('street',)); value['reasons']=['粉色日出氛围，带一点暖感。']
        adapter=self.adapter([value]);result,item=adapter.recommend_case(case,self.body(case))
        self.assertEqual(result,value);self.assertEqual(item['checks']['replyLanguage'],'pass')
        self.assertEqual(item['checks']['presetCapabilityReasons'],'pending-human-review')

    def test_unknown_clarification_is_pending_never_automatic_pass(self):
        case=self.corpus[-1];value=self.redirect('请说说你期望的照明效果？')
        self.assertFalse(demo_case_check(case,value))
        self.assertEqual(safety_review(case,value),'pending-human-review')
        adapter=self.adapter([value]);_,item=adapter.recommend_case(case,self.body(case))
        self.assertEqual(item['checks']['selectionExclusions'],'pending-human-review')
        self.assertEqual(len(self.calls),1)

    def test_run_fee_and_cumulative_parent_caps_both_apply(self):
        with self.ledger.transaction() as data:
            data['operations']['prior-child']={'heldSlots':0,'calls':[{'reportedPretaxUSD':.13}]}
        with self.assertRaises(LanguageError):self.ledger.begin('browser',self.corpus[0]['id'])
        with self.ledger.transaction() as data:
            data['operations']={};data['priorCommittedPretaxUSD']=.81
        with self.assertRaises(LanguageError):self.ledger.begin('browser',self.corpus[0]['id'])

    def test_repeated_protocol_fault_stops_but_wording_errors_are_collected(self):
        for case in self.corpus[:2]:
            key=self.ledger.begin('browser',case['id'])
            self.ledger.finish(key,{'status':'failed','elapsedSeconds':0,'errorCode':'LANGUAGE_WRONG_LANGUAGE',
                'checks':{'replyLanguage':'fail'},'operationAudit':{}})
        self.assertNotEqual(self.ledger.read()['status'],'stopped')
        for case in self.corpus[2:4]:
            key=self.ledger.begin('browser',case['id'])
            self.ledger.finish(key,{'status':'failed','elapsedSeconds':0,'errorCode':'INVALID_MODEL_OUTPUT',
                'checks':{'protocolStructure':'fail'},'operationAudit':{'attempts':[{'errorCode':'INVALID_MODEL_OUTPUT'}]}})
        self.assertEqual(self.ledger.read()['status'],'stopped')

    def test_canonical_path_also_requires_actual_explicit_renewal(self):
        with patch('demo_web_acceptance.RUN',self.folder),patch('demo_web_acceptance.PARENT',self.parent):
            with self.assertRaises(LanguageError):
                LinkedLedger(self.folder/'budget-ledger.json',self.manifest,self.ledger.allowed,self.parent,create=True,approval={'approved':False})
        self.assertFalse((self.folder/'budget-ledger.json').exists())

    def test_each_real_page_result_requires_recorded_observation_before_next(self):
        adapter=self.adapter();service=DemoService(adapter,self.ledger,self.corpus)
        service.recommend(self.body(self.corpus[0]))
        with self.ledger.transaction() as data:data['evidenceMode']='real'
        with self.assertRaises(LanguageError):service.recommend(self.body(self.corpus[1]))
        self.assertEqual(len(self.calls),1)
        (self.folder/'browser-observations.json').write_text(json.dumps({
            'browser:'+self.corpus[0]['id']:{'safeToContinue':True}}),encoding='utf-8')
        service.recommend(self.body(self.corpus[1]))
        self.assertEqual(len(self.calls),2)


if __name__=='__main__':unittest.main()
