"""Offline fee-reservation checks, never model evaluation."""
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
from language import LanguageAdapter
import finish_language_acceptance as finish


class FinishTests(unittest.TestCase):
    def test_release_completed_reserves_and_stop_at_forty(self):
        self.fixture(missing=False)

    def test_missing_usage_keeps_full_reserve_and_stops(self):
        self.fixture(missing=True)

    def test_remaining_seven_fill_coverage_without_retrying_failed_case(self):
        self.fixture(missing=False, remaining=True)

    def fixture(self, missing, remaining=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('data/catalog.json', 'tests/language_cases.json'):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes((PRODUCT / name).read_bytes())
            folder = root / 'qa/language-real-20261011'
            folder.mkdir(parents=True)
            names = ('protocol-probe.json', 'direct-suite.json', 'single-tool-suite.json',
                     'bounded-suite.json', 'protocol-matrix.json', 'reviewed-suite.json', 'thinking-suite.json')
            for name in names:
                record = {'reportedTokenCostEstimateUSD': .0001, 'reportedTokenCostEstimateThisRunUSD': .0001}
                if name == 'thinking-suite.json':
                    record.update(totalRequestsReserved=23, requestsThisRun=6,
                        status='completed-requires-human-review', cases=[{'id': key} for key in (
                            'explicit-en', 'mood-zh', 'mood-en', 'negation-zh', 'remove-en', 'precision-zh')])
                (folder / name).write_text(json.dumps(record), encoding='utf-8')
            if remaining:
                (folder / 'completion-suite.json').write_text(json.dumps({
                    'totalRequestsReserved': 33, 'requestsThisRun': 10, 'inFlightReserveUSD': 0,
                    'status': 'stopped-on-error-or-missing-usage',
                    'reportedTokenCostEstimateThisRunUSD': .001,
                    'unknownCostReserveUSD': .00376608,
                    'cases': [{'id': key} for key in ('precision-zh', 'mood-zh', 'mood-en', 'explicit-zh',
                        'vague-zh', 'vague-en', 'negation-en', 'remove-zh', 'replace-zh')] +
                        [{'id': 'replace-en', 'errorCode': 'INVALID_MODEL_OUTPUT'}]}), encoding='utf-8')
            filename = 'final-coverage.json' if remaining else 'completion-suite.json'
            calls = []
            def transport(payload, remaining):
                before = json.loads((folder / filename).read_text(encoding='utf-8'))
                self.assertGreater(before['inFlightReserveUSD'], 0)
                self.assertEqual(before['requestsThisRun'], len(calls) + 1)
                self.assertTrue(payload['chat_template_kwargs']['enable_thinking'])
                self.assertEqual(payload['max_tokens'], 40960)
                calls.append(1)
                adapter.last_response_audit = {'usage': {} if missing else {'prompt_tokens': 1000, 'completion_tokens': 1200}}
                return json.dumps({'status': 'ready', 'presetIds': ['sunny'], 'reasons': ['Daylight.'],
                                   'excludedIds': [], 'unsupported': [], 'question': ''})
            presets = json.loads((root / 'data/catalog.json').read_text(encoding='utf-8'))['presets']
            adapter = LanguageAdapter(presets, enabled=True, model='nvidia/Nemotron-3_5-Lightning',
                                      key='SYNTHETIC_SECRET', transport=transport)
            with patch.object(finish, 'ROOT', root), patch.object(finish.LanguageAdapter, 'from_env', return_value=adapter), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(finish.run(remaining=remaining), 1 if missing else 0)
                self.assertEqual(finish.run(remaining=remaining), 2)
            report = json.loads((folder / filename).read_text(encoding='utf-8'))
            expected = 1 if missing else 7 if remaining else 17
            self.assertEqual(len(calls), expected)
            self.assertEqual(report['totalRequestsReserved'], 24 if missing else 40)
            self.assertEqual(report['inFlightReserveUSD'], 0)
            self.assertNotIn('SYNTHETIC_SECRET', json.dumps(report))
            if missing:
                self.assertGreater(report['unknownCostReserveUSD'], .01)
            else:
                self.assertAlmostEqual(report['reportedTokenCostEstimateThisRunUSD'], expected * .000348)
            if remaining:
                self.assertNotIn('replace-en', [c['id'] for c in report['cases']])


if __name__ == '__main__':
    unittest.main()
