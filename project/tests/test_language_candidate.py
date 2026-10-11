"""Offline adversarial responses and state/budget regression. No real API."""
import copy
import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
from language import LanguageAdapter, LanguageError
from language_contract import exact_operation, language_review, response_language
from acceptance_checks import case_check, dimensions, verdict
from run_candidate_offline import run

PRESETS = json.loads((ROOT / 'data/catalog.json').read_text(encoding='utf-8'))['presets']


def plan(selected=('sunny',), excluded=(), english=False):
    reasons = {'sunny': '自然日光氛围。', 'sunrise': '粉色晨光近似，不保证暖色。', 'street': '夜间街灯氛围。'}
    if english:
        reasons = {'sunny': 'Natural daylight.', 'sunrise': 'Pink sunrise, warmth not guaranteed.', 'street': 'Night street lamps.'}
    return {'status': 'ready', 'presetIds': list(selected), 'reasons': [reasons[i] for i in selected],
            'excludedIds': list(excluded), 'unsupported': [], 'question': ''}


class CandidateTests(unittest.TestCase):
    def adapter(self, responses, **options):
        self.calls = []
        iterator = iter(responses)
        def transport(payload, remaining):
            self.calls.append((copy.deepcopy(payload), remaining))
            response = next(iterator)
            if isinstance(response, Exception):
                raise response
            return json.dumps(response) if isinstance(response, dict) else response
        return LanguageAdapter(PRESETS, enabled=True, model='nvidia/Nemotron-3_5-Lightning',
                               key='OFFLINE_KEY', transport=transport, **options)

    def body(self, text, current=('sunny',), excluded=(), **extra):
        return {'text': text, 'currentPlan': {'presetIds': list(current), 'excludedIds': list(excluded)},
                'compareThree': False, 'responseLanguage': 'zh', **extra}

    def test_removal_cannot_create_exclusion_and_failed_attempt_is_retained(self):
        good = plan(('sunrise',), ('street',))
        bad = plan(('sunrise',), ('street', 'sunny'))
        adapter = self.adapter([bad, good])
        self.assertEqual(adapter.recommend(self.body('删掉第二项', ('sunrise', 'sunny'), ('street',))), good)
        self.assertEqual(adapter.last_operation_audit['attempts'][0]['errorCode'], 'LANGUAGE_CONSTRAINT_VIOLATION')
        self.assertEqual(len(self.calls), 2)

    def test_removed_preset_can_be_recommended_again(self):
        adapter = self.adapter([plan(('sunrise',)), plan()])
        previous = adapter.recommend(self.body('删掉第二项', ('sunrise', 'sunny')))
        self.assertEqual(adapter.recommend(self.body('只选 sunny', previous['presetIds'], previous['excludedIds'])), plan())

    def test_replacement_keeps_existing_exclusion(self):
        adapter = self.adapter([plan(('sunrise',), ('street',))])
        result = adapter.recommend(self.body('another one', ('sunny',), ('street',)))
        self.assertEqual(result['excludedIds'], ['street'])

    def test_structured_replace_validates_current_position(self):
        adapter = self.adapter([plan(('sunrise',), ('street',))])
        result = adapter.recommend(self.body('替换第一项', excluded=('street',), operation={'type':'replace','index':0,'id':'sunrise'}))
        self.assertEqual(result['presetIds'], ['sunrise'])
        with self.assertRaises(LanguageError):
            adapter.recommend(self.body('替换第一项', operation={'type':'replace','index':3,'id':'sunrise'}))
        self.assertEqual(len(self.calls), 1)

    def test_explicit_exclusion_and_revocation_are_distinct(self):
        adapter = self.adapter([plan(excluded=('street',)), plan()])
        first = adapter.recommend(self.body('不要再推荐夜景', ('street', 'sunny')))
        second = adapter.recommend(self.body('解除夜景排除', first['presetIds'], first['excludedIds']))
        self.assertEqual(second['excludedIds'], [])

    def test_no_general_keyword_parser_or_self_declared_operation(self):
        for text in ('不要移除夜景的解释', 'sunny 听起来如何', '不要再推荐夜景但也许明天再说'):
            self.assertIsNone(exact_operation(text))
        bad = plan(excluded=('street',))
        bad['operation'] = 'exclude'
        adapter = self.adapter([bad, bad])
        with self.assertRaises(LanguageError):
            adapter.recommend(self.body('聊聊夜景'))

    def test_unknown_exclusion_change_fails_instead_of_silent_rule_answer(self):
        bad = plan(excluded=('street',))
        adapter = self.adapter([bad, bad])
        with self.assertRaises(LanguageError) as error:
            adapter.recommend(self.body('我比较倾向于日光'))
        self.assertEqual(error.exception.code, 'LANGUAGE_CONSTRAINT_VIOLATION')
        self.assertEqual(len(self.calls), 2)

    def test_explicit_sunny_must_be_exact(self):
        adapter = self.adapter([plan(('sunrise',)), plan(('street',))])
        with self.assertRaises(LanguageError):
            adapter.recommend(self.body('只选 sunny'))
        self.assertEqual(len(self.calls), 2)

    def test_language_setting_mixed_input_and_explicit_override(self):
        self.assertEqual(response_language('只选 sunny', 'zh'), 'zh')
        self.assertEqual(response_language('只选 sunny', 'en'), 'en')
        self.assertEqual(response_language('sunny，用英文回复', 'zh'), 'en')
        adapter = self.adapter([plan(english=True)])
        adapter.recommend(self.body('sunny，用英文回复'))
        data = json.loads(self.calls[0][0]['messages'][1]['content'])
        self.assertEqual(data['responseLanguage'], 'English')
        self.assertEqual(data['serverConstraints']['presetIds'], ['sunny'])

    def test_reasons_checked_individually_and_not_replaced_with_templates(self):
        bad = plan(('sunny', 'sunrise')); bad['reasons'][1] = 'Pink sunrise.'
        adapter = self.adapter([bad, bad])
        with self.assertRaises(LanguageError) as error:
            adapter.recommend(self.body('给两个灯光'))
        self.assertEqual(error.exception.code, 'LANGUAGE_WRONG_LANGUAGE')
        self.assertEqual(len(self.calls), 2)

    def test_clarification_wrong_language_and_borderline_review(self):
        bad = {'status':'clarification','presetIds':[],'reasons':[],'excludedIds':[], 'unsupported':[], 'question':'Which mood do you prefer?'}
        adapter = self.adapter([bad, bad])
        with self.assertRaises(LanguageError) as error:
            adapter.recommend(self.body('随便'))
        self.assertEqual(error.exception.code, 'LANGUAGE_WRONG_LANGUAGE')
        mixed = plan(); mixed['reasons'] = ['日光 lighting 氛围']
        self.assertEqual(language_review(mixed, 'zh'), 'review')
        mixed['reasons'] = ['sunny 的 HDR 自然日光氛围']
        self.assertEqual(language_review(mixed, 'zh'), 'pass')
        unsupported = {**bad, 'status':'unsupported','unsupported':['precision'],'question':''}
        self.assertEqual(language_review(unsupported, 'zh'), 'not-applicable')

    def test_format_semantics_language_share_one_repair(self):
        for first, second in [('{}', plan(('sunrise',))),
                              (plan(('sunrise',)), plan(english=True)),
                              (plan(english=True), '{}')]:
            adapter = self.adapter([first, second])
            with self.assertRaises(LanguageError):
                adapter.recommend(self.body('只选 sunny'))
            self.assertEqual(len(self.calls), 2)

    def test_multi_tool_rejection_can_only_request_fresh_complete_response(self):
        error = LanguageError('INVALID_MODEL_OUTPUT', 'fixed')
        adapter = self.adapter([error, plan()])
        adapter.recommend(self.body('sunny'))
        self.assertEqual(len(self.calls), 2)
        self.assertIn('ONE fresh complete call', self.calls[1][0]['messages'][-1]['content'])
        self.assertEqual(adapter.last_operation_audit['attempts'][0]['status'], 'rejected')

    def test_wire_multiple_tools_repaired_by_full_new_envelope_with_both_usages(self):
        class Response:
            def __init__(self, value):
                self.raw = json.dumps(value).encode()
                self.fp = type('File', (), {'raw': type('Raw', (), {'_sock': type('Socket', (), {'settimeout':lambda *_:None})()})()})()
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read1(self, n):
                raw, self.raw = self.raw[:n], self.raw[n:]
                return raw
            def isclosed(self): return not self.raw
        good = {'choices':[{'finish_reason':'tool_calls','message':{'tool_calls':[
            {'type':'function','function':{'name':'propose_lighting_plan','arguments':json.dumps(plan())}}]}}],
            'usage':{'prompt_tokens':1200,'completion_tokens':100}}
        bad = copy.deepcopy(good); bad['choices'][0]['message']['tool_calls'] *= 2
        adapter = LanguageAdapter(PRESETS, enabled=True, model='nvidia/Nemotron-3_5-Lightning',key='OFFLINE_KEY')
        with patch('urllib.request.OpenerDirector.open', side_effect=[Response(bad),Response(good)]) as wire:
            self.assertEqual(adapter.recommend(self.body('sunny')), plan())
        self.assertEqual(wire.call_count, 2)
        attempts = adapter.last_operation_audit['attempts']
        self.assertEqual(attempts[0]['protocol']['toolCallCount'], 2)
        self.assertEqual(attempts[0]['status'], 'rejected')
        self.assertTrue(all(a['billing']=='usage-reported' for a in attempts))
        # A truncated envelope is rejected in full even if arguments are complete.
        bad['choices'][0]['finish_reason'] = 'length'
        with patch('urllib.request.OpenerDirector.open', return_value=Response(bad)) as wire:
            with self.assertRaises(LanguageError) as error:
                adapter.recommend(self.body('sunny'))
        self.assertEqual(wire.call_count, 1)
        self.assertEqual(error.exception.code, 'LANGUAGE_OUTPUT_TRUNCATED')

    def test_wall_timeout_keeps_adapter_busy_until_unknown_wire_finishes(self):
        release, finished = threading.Event(), threading.Event()
        def offline_stall(*args):
            release.wait(3)
            finished.set()
            return json.dumps(plan())
        adapter = LanguageAdapter(PRESETS, enabled=True, model='test', key='OFFLINE_KEY',
                                  timeout=1, transport=offline_stall)
        adapter._real_transport = True  # Exercise production wall-time wrapper, no network.
        started = time.monotonic()
        try:
            with self.assertRaises(LanguageError) as error:
                adapter.recommend(self.body('sunny'))
            self.assertEqual(error.exception.code, 'LANGUAGE_TIMEOUT')
            self.assertLess(time.monotonic()-started, 1.5)
            with self.assertRaises(LanguageError) as busy:
                adapter.recommend(self.body('sunny'))
            self.assertEqual(busy.exception.code, 'LANGUAGE_BUSY')
            self.assertEqual(adapter.last_operation_audit['attempts'][0]['billing'], 'unknown')
        finally:
            release.set()
            self.assertTrue(finished.wait(1))

    def test_repair_has_only_remaining_time_not_fresh_sixty_seconds(self):
        adapter = self.adapter(['{}', plan()])
        with patch('language.time.monotonic', side_effect=[100,100,140,145,150,150]):
            adapter.recommend(self.body('sunny'))
        self.assertEqual(self.calls[0][1], 60)
        self.assertEqual(self.calls[1][1], 15)
        self.assertEqual(adapter.last_operation_audit['elapsedSeconds'], 50)

    def test_insufficient_operation_budget_reserves_no_outbound_calls(self):
        adapter = self.adapter([plan()], operation_budget_usd=.01)
        with self.assertRaises(LanguageError) as error:
            adapter.recommend(self.body('sunny'))
        self.assertEqual(error.exception.code, 'LANGUAGE_BUDGET_STOP')
        self.assertEqual(self.calls, [])

    def test_timeout_unknown_billing_and_durable_pre_send_record(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'audit.jsonl'
            adapter = self.adapter([LanguageError('LANGUAGE_TIMEOUT', 'fixed')], audit_path=path)
            with self.assertRaises(LanguageError):
                adapter.recommend(self.body('sunny'))
            events = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertEqual(events[1]['attempts'][0]['status'], 'reserved-before-send')
            self.assertEqual(events[-1]['attempts'][0]['billing'], 'unknown')
            self.assertEqual(events[-1]['maxCalls'], 2)
            self.assertEqual(len(self.calls), 1)
            self.assertNotIn('OFFLINE_KEY', path.read_text())

    def test_audit_io_failure_stops_before_call_and_does_not_lock_future_operations(self):
        adapter = self.adapter([plan()], audit_path='offline-test.jsonl')
        with patch('language.Path.open', side_effect=OSError('fixed')):
            with self.assertRaises(LanguageError) as error:
                adapter.recommend(self.body('sunny'))
        self.assertEqual(error.exception.code, 'LANGUAGE_AUDIT_FAILED')
        self.assertEqual(self.calls, [])
        self.assertFalse(adapter.lock.locked())
        adapter.audit_path = None
        self.assertEqual(adapter.recommend(self.body('sunny')), plan())

    def test_state_does_not_leak_between_operations_or_photos(self):
        adapter = self.adapter([plan(excluded=('street',)), plan(('street',))])
        adapter.recommend(self.body('不要夜景', ('street', 'sunny')))
        other = adapter.recommend(self.body('street', (), ()))
        self.assertEqual(other['excludedIds'], [])
        self.assertEqual(len(adapter.last_operation_audit['attempts']), 1)

    def test_acceptance_dimensions_do_not_convert_false_or_unknown_to_pass(self):
        remove = {'id':'remove-zh','check':'first-only','current':['sunrise','sunny']}
        self.assertFalse(case_check(remove, plan(('sunrise',), ('sunny',))))
        checks = dimensions({'id':'mood-zh','check':'bounded','current':[]}, plan(('sunrise',)))
        self.assertEqual(checks['selectionExclusions'], 'pass')
        self.assertEqual(checks['presetCapabilityReasons'], 'pending-human-review')
        self.assertEqual(verdict([{'status':'valid','checks':checks}], 1)[1], 3)
        self.assertEqual(verdict([{'status':'valid','constraintCheck':False,'checks':checks}], 1)[1], 1)
        self.assertFalse(case_check({'id':'vague-en','check':'clarification','current':[]},
            {'status':'unsupported','presetIds':[],'excludedIds':[], 'question':'', 'unsupported':['unrelated']}))
        self.assertEqual(verdict([], 20)[1], 3)
        fake_checks = {k:'not-applicable' for k in checks}
        self.assertEqual(verdict([{'status':'valid','checks':fake_checks,'plan':plan()}], 1)[1], 3)
        reviewed = {k:'pass' for k in checks}
        self.assertEqual(verdict([{'status':'valid','checks':reviewed,'plan':plan()}], 1)[1], 0)

    def test_complete_32_case_offline_flow_never_means_model_passed(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'report.json'
            self.assertEqual(run(output), 0)
            report = json.loads(output.read_text(encoding='utf-8'))
            self.assertEqual(report['executedCases'], 32)
            self.assertEqual(report['modelAcceptance'], 'not-tested')
            self.assertEqual(report['realRequests'], 0)


if __name__ == '__main__':
    unittest.main()
