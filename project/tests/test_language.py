"""Offline transport/contract verification, not a Nemotron capability evaluation."""
import copy
import json
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from http.server import ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from language import LanguageAdapter, LanguageError, validate_plan, strict_json, response_audit
import server
PRESETS = json.loads((ROOT/'data/catalog.json').read_text(encoding='utf-8'))['presets']
PLAN = {'status':'ready','presetIds':['sunrise','sunny'], 'reasons':['粉色晨光的近似氛围，不保证暖色。','自然日光氛围。'], 'excludedIds':[], 'unsupported':[], 'question':''}
BODY = {'text':'想要温暖一点', 'currentPlan':{'presetIds':['sunny'], 'excludedIds':[]}, 'compareThree':False}


class AdapterTests(unittest.TestCase):
    def test_configured_40960_budget_and_hard_maximum(self):
        calls = []
        adapter = self.adapter(lambda payload, _: calls.append(payload) or json.dumps(PLAN),
                               max_tokens=40960, timeout=60)
        adapter.recommend(BODY)
        self.assertEqual(calls[0]['max_tokens'], 40960)
        with self.assertRaises(LanguageError):
            self.adapter(lambda *_: '', max_tokens=40961)

    def test_auto_tool_choice_still_offers_only_the_fixed_data_function(self):
        calls = []
        adapter = self.adapter(lambda payload, _: calls.append(payload) or json.dumps(PLAN), tool_selection='auto')
        self.assertEqual(adapter.recommend(BODY), PLAN)
        self.assertEqual(calls[0]['tool_choice'], 'auto')
        self.assertEqual(len(calls[0]['tools']), 1)
        self.assertEqual(calls[0]['tools'][0]['function']['name'], 'propose_lighting_plan')
        self.assertFalse(calls[0]['parallel_tool_calls'])
        with self.assertRaises(LanguageError):
            self.adapter(lambda *_: '', tool_selection='arbitrary-tool')

    def test_short_reasons_and_question_limits(self):
        valid = copy.deepcopy(PLAN)
        valid['reasons'] = ['x' * 60, 'y']
        validate_plan(valid, ['sunny', 'sunrise', 'street'])
        valid['reasons'][0] += 'x'
        with self.assertRaises(LanguageError):
            validate_plan(valid, ['sunny', 'sunrise', 'street'])
        question = {'status': 'clarification', 'presetIds': [], 'reasons': [],
                    'excludedIds': [], 'unsupported': [], 'question': 'x' * 100}
        validate_plan(question, ['sunny'])
        question['question'] += 'x'
        with self.assertRaises(LanguageError):
            validate_plan(question, ['sunny'])

    def test_lightning_direct_answer_keeps_token_cap(self):
        for model, mode, expected in [('nvidia/Nemotron-3_5-Lightning', 'auto', None),
                                       ('test-model', 'auto', None), ('test-model', 'off', False),
                                       ('test-model', 'on', True)]:
            calls = []
            adapter = LanguageAdapter(PRESETS, enabled=True, key='SYNTHETIC_PRIVATE_KEY',
                model=model, thinking_mode=mode, transport=lambda payload, _: calls.append(payload) or json.dumps(PLAN))
            adapter.recommend(BODY)
            self.assertEqual(calls[0]['max_tokens'], 40960)
            if expected is None:
                self.assertNotIn('chat_template_kwargs', calls[0])
            else:
                self.assertEqual(calls[0]['chat_template_kwargs'], {'enable_thinking': expected})

    def test_truncation_is_not_repaired(self):
        calls = []
        def truncated(*args):
            calls.append(1)
            raise LanguageError('LANGUAGE_OUTPUT_TRUNCATED', 'fixed safe message')
        with self.assertRaises(LanguageError) as caught:
            self.adapter(truncated).recommend(BODY)
        self.assertEqual(caught.exception.code, 'LANGUAGE_OUTPUT_TRUNCATED')
        self.assertEqual(len(calls), 1)

    def test_protocol_audit_never_copies_arbitrary_text(self):
        secret = 'SYNTHETIC_SECRET'
        audit = response_audit({'choices': [{'finish_reason': secret, 'message': {
            'content': secret, 'refusal': secret, 'tool_calls': [{'function': {
                'name': secret, 'arguments': secret}}]}}], 'usage': {
                    'prompt_tokens': 42, 'completion_tokens': 600, 'total_tokens': secret,
                    'private': secret}})
        self.assertNotIn(secret, json.dumps(audit))
        self.assertEqual(audit['finishReason'], 'other')
        self.assertEqual(audit['usage'], {'prompt_tokens': 42, 'completion_tokens': 600})
        self.assertFalse(audit['expectedFunction'])
        for value in (None, [], {}, {'choices': [None], 'usage': []}):
            self.assertIsInstance(response_audit(value), dict)

    def adapter(self, transport, **kwargs):
        return LanguageAdapter(PRESETS, enabled=True, key='SYNTHETIC_PRIVATE_KEY', model='test-model', transport=transport, **kwargs)

    def test_valid_schema_and_text_only_context(self):
        calls=[]
        def transport(payload, timeout):
            calls.append(copy.deepcopy(payload));self.assertGreater(timeout,0)
            return json.dumps(PLAN)
        self.assertEqual(self.adapter(transport).recommend(BODY), PLAN)
        payload=calls[0]
        self.assertEqual(set(json.loads(payload['messages'][1]['content'])), {'text','currentPlan','maximum','responseLanguage'})
        self.assertEqual(json.loads(payload['messages'][1]['content'])['responseLanguage'], 'Chinese')
        self.assertNotIn('SYNTHETIC_PRIVATE_KEY', json.dumps(payload))
        self.assertEqual(len(payload['tools']),1)
        self.assertEqual(payload['tools'][0]['function']['name'],'propose_lighting_plan')
        self.assertEqual(payload['tool_choice']['function']['name'],'propose_lighting_plan')
        self.assertIs(payload['parallel_tool_calls'], False)

    def test_schema_rejects_fields_ids_duplicates_counts_and_lengths(self):
        bad=[]
        for field,value in [('presetIds',['unknown']),('presetIds',['sunny','sunny']),('presetIds',['sunny','sunrise','street']),
                            ('presetIds',[]),('presetIds','sunny'),('reasons',['x'*181,'y']),('reasons',[]),
                            ('excludedIds',['sunny']),('unsupported',['shell']),('question','x'*181),('status','execute'),
                            ('reasons',['   '*100+'x','y']),('reasons',['C:/private/file','y']),('reasons',['bash run','y']),
                            ('question','https://example.invalid'),('reasons',['line\ncommand','y'])]:
            p=copy.deepcopy(PLAN);p[field]=value;bad.append(p)
        p=copy.deepcopy(PLAN);p['command']='echo';bad.append(p)
        bad.extend([{},[],None])
        for value in bad:
            with self.subTest(value=value), self.assertRaises(LanguageError): validate_plan(value,['sunny','sunrise','street'])
        with self.assertRaises(ValueError): strict_json('{"status":"ready","status":"ready"}')

    def test_empty_malformed_output_and_one_repair_limit(self):
        for raw in ('', 'not json', '[]', 'x'*4097):
            calls=[]
            def transport(payload, timeout):calls.append(copy.deepcopy(payload));return raw
            with self.subTest(raw=raw[:20]),self.assertRaises(LanguageError):self.adapter(transport).recommend(BODY)
            self.assertEqual(len(calls),2)
            self.assertEqual(len(calls[1]['messages']),3)
            self.assertNotIn(raw if raw else 'UNLIKELY',calls[1]['messages'][-1]['content'])

    def test_repair_can_succeed_and_can_be_disabled(self):
        answers=iter(['{}',json.dumps(PLAN)])
        self.assertEqual(self.adapter(lambda *a:next(answers)).recommend(BODY),PLAN)
        calls=[]
        with self.assertRaises(LanguageError):self.adapter(lambda *a:calls.append(1) or '{}',repair_attempts=0).recommend(BODY)
        self.assertEqual(calls,[1])

    def test_no_retry_auth_rate_limit_timeout_or_unknown_error(self):
        for code in ('LANGUAGE_AUTH','LANGUAGE_RATE_LIMIT','LANGUAGE_TIMEOUT','LANGUAGE_UPSTREAM'):
            calls=[]
            def transport(*a):calls.append(1);raise LanguageError(code,'safe')
            with self.assertRaises(LanguageError) as error:self.adapter(transport).recommend(BODY)
            self.assertEqual(error.exception.code,code);self.assertEqual(calls,[1])

    def test_total_deadline(self):
        adapter=self.adapter(lambda *a:json.dumps(PLAN),timeout=1)
        with patch('language.time.monotonic',side_effect=[0,0,2]):
            with self.assertRaises(LanguageError) as error:adapter.recommend(BODY)
        self.assertEqual(error.exception.code,'LANGUAGE_TIMEOUT')

    def test_stalled_wire_has_wall_timeout_and_blocks_overlapping_request(self):
        release=threading.Event()
        class Stalled(LanguageAdapter):
            def _request(self,*args):release.wait(3);return json.dumps(PLAN)
        adapter=Stalled(PRESETS,enabled=True,key='synthetic',model='test',timeout=1)
        started=time.monotonic()
        try:
            with self.assertRaises(LanguageError) as error:adapter.recommend(BODY)
            self.assertEqual(error.exception.code,'LANGUAGE_TIMEOUT')
            self.assertLess(time.monotonic()-started,2)
            with self.assertRaises(LanguageError) as error:adapter.recommend(BODY)
            self.assertEqual(error.exception.code,'LANGUAGE_BUSY')
        finally:release.set()

    def test_known_credential_in_user_text_never_reaches_transport(self):
        calls=[]
        with self.assertRaises(LanguageError):self.adapter(lambda *a:calls.append(1)).recommend({**BODY,'text':'SYNTHETIC_PRIVATE_KEY'})
        self.assertEqual(calls,[])

    def test_disabled_and_missing_configuration(self):
        with patch.dict('os.environ',{},clear=True):
            adapter=LanguageAdapter.from_env(PRESETS)
        self.assertFalse(adapter.capabilities()['enabled'])
        with self.assertRaises(LanguageError) as error:adapter.recommend(BODY)
        self.assertEqual(error.exception.code,'LANGUAGE_NOT_CONFIGURED')

    def test_credentials_are_not_returned_even_if_upstream_echoes(self):
        value=copy.deepcopy(PLAN);value['reasons'][0]='SYNTHETIC_PRIVATE_KEY'
        with self.assertRaises(LanguageError) as error:self.adapter(lambda *a:json.dumps(value)).recommend(BODY)
        self.assertNotIn('SYNTHETIC_PRIVATE_KEY',str(error.exception))

    def test_transport_http_errors_are_sanitized(self):
        adapter=self.adapter(None)
        for status,code in [(401,'LANGUAGE_AUTH'),(403,'LANGUAGE_AUTH'),(429,'LANGUAGE_RATE_LIMIT'),(500,'LANGUAGE_UPSTREAM')]:
            with patch('urllib.request.OpenerDirector.open',side_effect=HTTPError('https://example.invalid',status,'SYNTHETIC_PRIVATE_KEY',{},None)):
                with self.assertRaises(LanguageError) as error:adapter._request({},1)
                self.assertEqual(error.exception.code,code);self.assertNotIn('SYNTHETIC_PRIVATE_KEY',str(error.exception))

    def test_input_allowlist_and_explicit_three(self):
        for update in ({'photo':'secret'},{'text':''},{'text':'x'*601},{'compareThree':'true'},{'currentPlan':{'presetIds':['unknown'],'excludedIds':[]}}):
            body={**BODY,**update}
            with self.assertRaises(LanguageError):self.adapter(lambda *a:json.dumps(PLAN)).recommend(body)
        plan=copy.deepcopy(PLAN);plan['presetIds'].append('street');plan['reasons'].append('街灯氛围')
        for text,explicit in [('compare three presets',False),('比较三个',False),('任选',True)]:
            self.assertEqual(self.adapter(lambda *a:json.dumps(plan)).recommend({**BODY,'text':text,'compareThree':explicit}),plan)

    def test_busy_rejects_duplicate_without_transport(self):
        calls=[];adapter=self.adapter(lambda *a:calls.append(1))
        adapter.lock.acquire()
        try:
            with self.assertRaises(LanguageError) as error:adapter.recommend(BODY)
            self.assertEqual(error.exception.code,'LANGUAGE_BUSY');self.assertEqual(calls,[])
        finally:adapter.lock.release()

    def test_catalog_hdr_is_source_of_truth(self):
        presets=copy.deepcopy(PRESETS);presets[0]['hdr']='made-up.hdr'
        self.assertNotIn('sunny',self.adapter(lambda *a:'{}').__class__(presets).allowed)

    def test_fixed_bilingual_corpus_is_explicitly_offline(self):
        from serve_language_fixture import ScriptedLanguage
        server.Handler.catalog={'presets':PRESETS}
        adapter=ScriptedLanguage(PRESETS)
        self.assertTrue(adapter.capabilities()['developmentTestMode'])
        cases=json.loads((ROOT/'tests/language_cases.json').read_text(encoding='utf-8'))
        for case in cases:
            with self.subTest(case=case['id']):
                plan=adapter.recommend({'text':case['text'],'currentPlan':{'presetIds':case['current'],'excludedIds':[]},'compareThree':False})
                check=case['check']
                if check=='sunny':self.assertEqual(plan['presetIds'],['sunny'])
                elif check=='clarification':self.assertEqual(plan['status'],'clarification')
                elif check=='no-night':self.assertNotIn('street',plan['presetIds']);self.assertIn('street',plan['excludedIds'])
                elif check=='first-only':self.assertEqual(plan['presetIds'],case['current'][:1])
                elif check=='different':self.assertFalse(set(plan['presetIds']) & set(case['current']))
                elif check=='three':self.assertEqual(len(plan['presetIds']),3)
                elif check in ('precision','unrelated'):self.assertIn(check,plan['unsupported'])
                else:self.assertTrue(1<=len(plan['presetIds'])<=2)

    def test_wire_tool_arguments_are_data_not_executed(self):
        class Socket:
            def settimeout(self,value):pass
        class Response:
            def __init__(self,body):
                self.body=body
                self.fp=type('File',(),{'raw':type('Raw',(),{'_sock':Socket()})()})()
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read1(self,n):body,self.body=self.body[:n],self.body[n:];return body
            def isclosed(self):return not self.body
        good={'choices':[{'finish_reason':'tool_calls','message':{'tool_calls':[{'type':'function','function':{'name':'propose_lighting_plan','arguments':json.dumps(PLAN)}}]}}]}
        values=[good]
        bad=copy.deepcopy(good);bad['choices'][0]['message']['tool_calls'][0]['function']['name']='start_gpu';values.append(bad)
        bad=copy.deepcopy(good);bad['choices'][0]['message']['tool_calls']*=2;values.append(bad)
        bad=copy.deepcopy(good);bad['choices'][0]['finish_reason']='length';values.append(bad)
        for i,value in enumerate(values):
            with patch('urllib.request.OpenerDirector.open',return_value=Response(json.dumps(value).encode())):
                if i==0:self.assertEqual(self.adapter(None)._request({},1),json.dumps(PLAN))
                else:
                    with self.assertRaises(LanguageError):self.adapter(None)._request({},1)


class HTTPTests(unittest.TestCase):
    def test_recommendation_never_submits_task_and_requires_csrf(self):
        class TrapStore:
            executor=object()
            def submit(self,*args):raise AssertionError('Recommendation started generation')
        handler=type('TestHandler',(server.Handler,),{'language_service':LanguageAdapter(PRESETS,enabled=True,key='synthetic',model='test',transport=lambda *a:json.dumps(PLAN)), 'task_store':TrapStore()})
        http=ThreadingHTTPServer(('127.0.0.1',0),handler)
        thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
        base=f'http://127.0.0.1:{http.server_port}'
        try:
            req=Request(base+'/api/language/recommend',data=json.dumps(BODY).encode(),headers={'Content-Type':'application/json','X-LightTry-Token':handler.csrf_token,'Origin':base})
            with urlopen(req) as response:self.assertEqual(json.load(response),PLAN)
            with urlopen(base+'/api/language') as response:
                self.assertEqual(set(json.load(response)),{'enabled','developmentTestMode','message'})
            for headers in ({'Content-Type':'application/json'},{'Content-Type':'application/json','X-LightTry-Token':handler.csrf_token,'Origin':'https://evil.invalid'}):
                with self.assertRaises(HTTPError) as error:urlopen(Request(base+'/api/language/recommend',data=b'{}',headers=headers))
                self.assertEqual(error.exception.code,403)
        finally:http.shutdown();http.server_close();thread.join()


if __name__=='__main__':unittest.main()
