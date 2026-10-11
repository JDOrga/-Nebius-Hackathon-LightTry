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
