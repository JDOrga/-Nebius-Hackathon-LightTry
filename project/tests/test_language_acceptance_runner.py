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

    def test_reviewed_suite_reserves_fourteen_and_runs_all_twenty(self):
        self.run_fixture(fail=False, reviewed=True)

    def test_auto_suite_reserves_seventeen_and_runs_twenty_without_repair(self):
        self.run_fixture(fail=False, auto_suite=True)

    def test_thinking_suite_six_requests_stays_under_original_fee_cap(self):
        self.run_fixture(fail=False, thinking_suite=True)

    def run_fixture(self, fail, single_tool=False, bounded=False, reviewed=False, auto_suite=False, thinking_suite=False):
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
            if reviewed:
                (report_dir / 'protocol-matrix.json').write_text(json.dumps({
                    'totalRequestsReserved': 14, 'requestsThisRun': 6,
                    'status': 'comparison-completed-requires-review',
                    'cases': [{'status': 'valid'}] * 6}), encoding='utf-8')
            if auto_suite or thinking_suite:
                (report_dir / 'reviewed-suite.json').write_text(json.dumps({
                    'totalRequestsReserved': 17, 'requestsThisRun': 3, 'status': 'stopped-on-error',
                    'cases': [{'status': 'valid'}, {'status': 'valid'},
                              {'errorCode': 'LANGUAGE_OUTPUT_TRUNCATED'}]}), encoding='utf-8')
            presets = json.loads((root / 'data/catalog.json').read_text(encoding='utf-8'))['presets']
            adapter = LanguageAdapter(presets, enabled=True, model='nvidia/Nemotron-3_5-Lightning',
                                      key='OFFLINE_SYNTHETIC_KEY', max_tokens=600, thinking_mode='off', transport=transport)
            with patch.object(runner, 'ROOT', root), patch.object(runner.LanguageAdapter, 'from_env', return_value=adapter), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(runner.direct_suite(single_tool=single_tool, bounded=bounded, reviewed=reviewed, auto_suite=auto_suite, thinking_suite=thinking_suite), 1 if fail else 0)
                self.assertEqual(runner.direct_suite(single_tool=single_tool, bounded=bounded, reviewed=reviewed, auto_suite=auto_suite, thinking_suite=thinking_suite), 2)
            report = json.loads((report_dir / ('thinking-suite.json' if thinking_suite else 'auto-suite.json' if auto_suite else 'reviewed-suite.json' if reviewed else 'bounded-suite.json' if bounded else 'single-tool-suite.json' if single_tool else 'direct-suite.json')).read_text(encoding='utf-8'))
            expected = 1 if fail else (6 if thinking_suite else 19 if single_tool or bounded else 20)
            self.assertEqual(len(calls), expected)
            self.assertEqual(report['requestsThisRun'], expected)
            self.assertEqual(report['totalRequestsReserved'], (17 if auto_suite or thinking_suite else 14 if reviewed else 7 if bounded else 5 if single_tool else 3) + expected)
            self.assertLess(report['planningCostReservedUSD'], .10)
            self.assertNotIn('OFFLINE_SYNTHETIC_KEY', json.dumps(report))
            self.assertFalse(report['gpuEnabled'])
            if single_tool or bounded:
                self.assertEqual(report['cases'][0]['id'], 'explicit-en')
            if bounded:
                self.assertEqual(report['maxTokens'], 1000)
                self.assertEqual(adapter.max_tokens, 1000)
            if auto_suite:
                self.assertEqual(adapter.tool_selection, 'auto')
                self.assertEqual(adapter.repair_attempts, 0)
                self.assertEqual(adapter.max_tokens, 4096)
                self.assertEqual(adapter.timeout, 20)
                self.assertEqual(report['maxTokens'], 4096)
                self.assertEqual(report['totalRequestsReserved'], 37)
            if thinking_suite:
                self.assertTrue(report['thinking'])
                self.assertEqual(adapter.max_tokens, 40960)
                self.assertEqual(adapter.timeout, 60)
                self.assertEqual(adapter.thinking_mode, 'on')
                self.assertEqual(adapter.repair_attempts, 0)
                self.assertEqual(report['totalRequestsReserved'], 23)
                self.assertAlmostEqual(report['planningCostReservedUSD'], .09639408)


if __name__ == '__main__':
    unittest.main()
