"""Offline verification of diagnostic comparisons; no provider calls."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PRODUCT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRODUCT))
sys.path.insert(0, str(PRODUCT / 'tests'))
from language import LanguageAdapter, LanguageError, response_audit
import diagnose_language_protocol as diagnostic


class ProtocolTests(unittest.TestCase):
    def test_plain_conversation_is_opt_in_and_cannot_create_tool_parameters(self):
        from types import SimpleNamespace
        presets=json.loads((PRODUCT/'data/catalog.json').read_text(encoding='utf-8'))['presets']
        adapter=LanguageAdapter(presets,enabled=True,model='nvidia/Nemotron-3_5-Lightning',key='SYNTHETIC_SECRET',output_mode='tool')
        def invoke(message,finish='stop',enabled=True):
            body=json.dumps({'choices':[{'finish_reason':finish,'message':message}]}).encode()
            class Response:
                fp=SimpleNamespace(raw=SimpleNamespace(_sock=SimpleNamespace(settimeout=lambda _:None)))
                def __enter__(self):return self
                def __exit__(self,*args):pass
                def read1(self,n):return body
                def isclosed(self):return True
            adapter.allow_chat_text=enabled
            with patch('language.urllib.request.build_opener',return_value=SimpleNamespace(open=lambda *a,**k:Response())):
                return adapter._request({'model':adapter.model},5)
        text='当然可以聊聊。\n今天有什么想法？'
        reply=json.loads(invoke({'content':text}))
        self.assertEqual(reply['reason'],text);self.assertIsNone(reply['parameters']);self.assertEqual(reply['status'],'explanation')
        # Text that resembles a control payload is still inert conversation.
        reply=json.loads(invoke({'content':'{"status":"ready","parameters":{"strength":4}}'}))
        self.assertEqual(reply['status'],'explanation');self.assertIsNone(reply['parameters'])
        for message,finish,enabled in [({'content':text},'stop',False),({'content':text},'length',True),
            ({'content':text,'tool_calls':[{'type':'function','function':{'name':'execute','arguments':'{}'}}]},'tool_calls',True)]:
            with self.assertRaises(LanguageError):invoke(message,finish,enabled)

    def test_opt_in_plain_preamble_never_replaces_actual_single_tool(self):
        from types import SimpleNamespace
        presets=json.loads((PRODUCT/'data/catalog.json').read_text(encoding='utf-8'))['presets']
        adapter=LanguageAdapter(presets,enabled=True,model='nvidia/Nemotron-3_5-Lightning',key='SYNTHETIC_SECRET',output_mode='tool')
        tool={'type':'function','function':{'name':'propose_lighting_plan','arguments':'{"actualToolArgument":true}'}}
        def invoke(content,calls,opt_in):
            body=json.dumps({'choices':[{'finish_reason':'tool_calls','message':{'content':content,'tool_calls':calls}}]}).encode()
            class Response:
                fp=SimpleNamespace(raw=SimpleNamespace(_sock=SimpleNamespace(settimeout=lambda _:None)))
                def __enter__(self):return self
                def __exit__(self,*a):pass
                def read1(self,n):return body
                def isclosed(self):return True
            adapter.allow_tool_preamble=opt_in
            with patch('language.urllib.request.build_opener',return_value=SimpleNamespace(open=lambda *a,**k:Response())):
                return adapter._request({'model':adapter.model},5)
        self.assertEqual(invoke('下面是结构化建议。',[tool],True),tool['function']['arguments'])
        self.assertEqual(adapter.last_response_audit['ignoredSupplementalContentChars'],len('下面是结构化建议。'))
        for text in ['{"fake":true}','```json','<tool_call>']:
            self.assertEqual(invoke(text,[tool],True),tool['function']['arguments'])
        for text,calls,opt in [('说明',[tool],False),('SYNTHETIC_SECRET',[tool],True),('x'*1025,[tool],True),('说明',[],True),('说明',[tool,tool],True)]:
            with self.subTest(content=text[:30],calls=len(calls),opt=opt):
                with self.assertRaises(LanguageError):invoke(text,calls,opt)
    def adapter(self, transport):
        presets = json.loads((PRODUCT / 'data/catalog.json').read_text(encoding='utf-8'))['presets']
        return LanguageAdapter(presets, enabled=True, model='nvidia/Nemotron-3_5-Lightning',
                               key='SYNTHETIC_SECRET', transport=transport)

    def test_comparisons_change_only_declared_controls(self):
        cases = dict(diagnostic.payloads(self.adapter(lambda *args: None)))
        forced = cases['minimal-forced-top']
        auto = cases['minimal-auto-top']
        self.assertEqual({k: v for k, v in forced.items() if k != 'tool_choice'},
                         {k: v for k, v in auto.items() if k != 'tool_choice'})
        nested = cases['minimal-forced-nested']
        self.assertNotIn('chat_template_kwargs', nested)
        self.assertEqual(nested['extra_body']['chat_template_kwargs'], forced['chat_template_kwargs'])
        self.assertTrue(cases['minimal-forced-nonempty']['chat_template_kwargs']['force_nonempty_content'])
        for payload in cases.values():
            self.assertEqual(payload['max_tokens'], 1000)
            self.assertIs(payload['store'], False)
            self.assertNotIn('SYNTHETIC_SECRET', json.dumps(payload))

    def test_shape_summary_does_not_copy_content_reasoning_or_keys(self):
        secret = 'SYNTHETIC_SECRET'
        audit = response_audit({'choices': [{'finish_reason': 'length', 'message': {
            'content': secret, 'reasoning_content': secret, 'tool_calls': [{'function': {
                'name': secret, 'arguments': json.dumps({secret: secret, 'reasons': [secret]})}}]}}],
            'usage': {'completion_tokens_details': {'reasoning_tokens': 12}}})
        self.assertNotIn(secret, json.dumps(audit))
        self.assertEqual(audit['contentChars'], len(secret))
        self.assertEqual(audit['reasoningChars'], len(secret))
        self.assertEqual(audit['argumentShapes'][0]['unknownFieldCount'], 1)
        self.assertEqual(audit['argumentShapes'][0]['reasonLengths'], [len(secret)])
        self.assertEqual(audit['usage']['reasoning_tokens'], 12)

    def test_six_calls_reserved_before_send_and_no_repeated_run(self):
        self.run_fixture(auth_failure=False)

    def test_auth_error_stops_after_one_without_retry(self):
        self.run_fixture(auth_failure=True)

    def run_fixture(self, auth_failure):
        calls = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'data').mkdir()
            (root / 'data/catalog.json').write_bytes((PRODUCT / 'data/catalog.json').read_bytes())
            folder = root / 'qa/language-real-20261011'
            folder.mkdir(parents=True)
            (folder / 'bounded-suite.json').write_text(json.dumps({
                'totalRequestsReserved': 8, 'status': 'stopped-on-error'}), encoding='utf-8')
            def transport(payload, remaining):
                saved = json.loads((folder / 'protocol-matrix.json').read_text(encoding='utf-8'))
                self.assertEqual(saved['requestsThisRun'], len(calls) + 1)
                calls.append(payload)
                if auth_failure:
                    raise LanguageError('LANGUAGE_AUTH', 'fixed message')
                if len(calls) <= 4:
                    return '{"presetId":"sunny"}'
                # Full response credential echo must never be persisted.
                return json.dumps({'status': 'ready', 'presetIds': ['sunny'], 'reasons': ['SYNTHETIC_SECRET'],
                                   'excludedIds': [], 'unsupported': [], 'question': ''})
            adapter = self.adapter(transport)
            with patch.object(diagnostic, 'ROOT', root), patch.object(diagnostic.LanguageAdapter, 'from_env', return_value=adapter), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(diagnostic.run(), 1 if auth_failure else 0)
                self.assertEqual(diagnostic.run(), 2)
            report = json.loads((folder / 'protocol-matrix.json').read_text(encoding='utf-8'))
            self.assertEqual(len(calls), 1 if auth_failure else 6)
            self.assertEqual(report['totalRequestsReserved'], 8 + len(calls))
            self.assertLess(report['planningCostReservedUSD'], .10)
            self.assertNotIn('SYNTHETIC_SECRET', json.dumps(report))
            if not auth_failure:
                self.assertEqual(report['cases'][-1]['errorCode'], 'INVALID_MODEL_OUTPUT')


if __name__ == '__main__':
    unittest.main()
