"""Offline tests of the explicit paid runner's request ledger and stop rules."""
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
from language import LanguageAdapter, LanguageError
import run_language_probe as runner


class RunnerTests(unittest.TestCase):
    def test_one_call_per_case_and_report_prevents_repeat(self):
        self.run_fixture(fail=False)

    def test_protocol_failure_stops_suite(self):
        self.run_fixture(fail=True)

    def test_single_tool_suite_carries_prior_budget_and_stops(self):
        self.run_fixture(fail=True, single_tool=True)

    def test_single_tool_suite_does_not_repeat_accepted_case(self):
        self.run_fixture(fail=False, single_tool=True)

    def test_bounded_suite_reserves_prior_calls_and_1000_token_cap(self):
        self.run_fixture(fail=False, bounded=True)

    def run_fixture(self, fail, single_tool=False, bounded=False):
        calls = []
        def transport(*args):
            calls.append(1)
            if fail:
                raise LanguageError('LANGUAGE_OUTPUT_TRUNCATED', 'fixed message')
            return json.dumps({'status': 'ready', 'presetIds': ['sunny'], 'reasons': ['Natural daylight.'],
                               'excludedIds': [], 'unsupported': [], 'question': ''})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for filename in ('data/catalog.json', 'tests/language_cases.json'):
                target = root / filename
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((PRODUCT / filename).read_bytes())
            report_dir = root / 'qa/language-real-20261011'
            report_dir.mkdir(parents=True)
            (report_dir / 'protocol-probe.json').write_text(json.dumps({
                'totalRequestsReserved': 3, 'protocol': {'finishReason': 'length'}}), encoding='utf-8')
            if single_tool:
                (report_dir / 'direct-suite.json').write_text(json.dumps({
                    'totalRequestsReserved': 5, 'requestsThisRun': 2, 'status': 'stopped-on-error',
                    'cases': [{'status': 'valid'}, {'protocol': {'toolCallCount': 2}}]}), encoding='utf-8')
            if bounded:
                (report_dir / 'single-tool-suite.json').write_text(json.dumps({
                    'totalRequestsReserved': 7, 'requestsThisRun': 2, 'status': 'stopped-on-error',
                    'cases': [{'status': 'valid'}, {'errorCode': 'LANGUAGE_OUTPUT_TRUNCATED'}]}), encoding='utf-8')
            presets = json.loads((root / 'data/catalog.json').read_text(encoding='utf-8'))['presets']
            adapter = LanguageAdapter(presets, enabled=True, model='nvidia/Nemotron-3_5-Lightning',
                                      key='OFFLINE_SYNTHETIC_KEY', transport=transport)
            with patch.object(runner, 'ROOT', root), patch.object(runner.LanguageAdapter, 'from_env', return_value=adapter), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(runner.direct_suite(single_tool=single_tool, bounded=bounded), 1 if fail else 0)
                self.assertEqual(runner.direct_suite(single_tool=single_tool, bounded=bounded), 2)
            report = json.loads((report_dir / ('bounded-suite.json' if bounded else 'single-tool-suite.json' if single_tool else 'direct-suite.json')).read_text(encoding='utf-8'))
            expected = 1 if fail else (19 if single_tool or bounded else 20)
            self.assertEqual(len(calls), expected)
            self.assertEqual(report['requestsThisRun'], expected)
            self.assertEqual(report['totalRequestsReserved'], (7 if bounded else 5 if single_tool else 3) + expected)
            self.assertLess(report['planningCostReservedUSD'], .10)
            self.assertNotIn('OFFLINE_SYNTHETIC_KEY', json.dumps(report))
            self.assertFalse(report['gpuEnabled'])
            if single_tool or bounded:
                self.assertEqual(report['cases'][0]['id'], 'explicit-en')
            if bounded:
                self.assertEqual(report['maxTokens'], 1000)
                self.assertEqual(adapter.max_tokens, 1000)


if __name__ == '__main__':
    unittest.main()
