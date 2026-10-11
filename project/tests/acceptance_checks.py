"""Separate evidence dimensions. Passing schema is never a quality verdict."""
import re
from language_contract import language_review


def case_check(case, plan):
    selected, check = plan['presetIds'], case['check']
    old_excluded = set(case.get('excluded', []))
    expected_excluded = old_excluded | {'street'} if check == 'no-night' else set(case.get('expectedExcluded', old_excluded))
    if set(plan['excludedIds']) != expected_excluded:
        return False
    if 'expected' in case:
        return selected == case['expected'] and plan['status'] == case.get('expectedStatus', 'ready')
    if check == 'sunny':
        return plan['status'] == 'ready' and selected == ['sunny']
    if check == 'bounded':
        # Several moods are acceptable; capability honesty is a separate review.
        return plan['status'] == 'ready' and 1 <= len(selected) <= 2
    if check == 'clarification':
        question = plan['question']
        return (plan['status'] == 'clarification' and not selected and bool(question.strip()) and
                bool(re.search(r'日光|晨光|夜|氛围|daylight|sunrise|street|mood|prefer', question, re.I)))
    if check == 'no-night':
        return plan['status'] == 'ready' and 'street' not in selected and bool(selected)
    if check == 'first-only':
        return plan['status'] == 'ready' and selected == case['current'][:1]
    if check == 'different':
        return plan['status'] == 'ready' and bool(selected) and not set(selected) & set(case['current'])
    if check == 'three':
        return plan['status'] == 'ready' and set(selected) == {'sunny', 'sunrise', 'street'}
    if check in ('precision', 'unrelated'):
        return plan['status'] == 'unsupported' and not selected and plan['unsupported'] == [check]
    return False


def dimensions(case, plan):
    return {'protocolStructure': 'pass',
            'selectionExclusions': 'pass' if case_check(case, plan) else 'fail',
            'replyLanguage': language_review(plan, case.get('language', 'zh' if case['id'].endswith('-zh') else 'en')),
            'presetCapabilityReasons': 'pending-human-review',
            'interaction': 'not-tested'}


def failure_dimensions(adapter, error):
    attempts = adapter.last_operation_audit.get('attempts', [])
    last = attempts[-1] if attempts else {}
    return {'protocolStructure': 'pass' if last.get('structure') else
                'fail' if error.code in ('INVALID_MODEL_OUTPUT', 'LANGUAGE_OUTPUT_TRUNCATED') else 'not-tested',
            'selectionExclusions': 'pass' if last.get('constraints') else
                'fail' if error.code == 'LANGUAGE_CONSTRAINT_VIOLATION' else 'not-tested',
            'replyLanguage': last.get('language', 'not-tested'),
            'presetCapabilityReasons': 'pending-human-review' if last.get('structure') else 'not-tested',
            'interaction': 'not-tested'}


def verdict(results, expected_count):
    # 0 means every dimension reviewed and passed. 1 completed with failure;
    # 2 preflight/refused; 3 incomplete or pending review. Never conflate them.
    if any(item.get('status') == 'failed' or item.get('constraintCheck') is False or
           'fail' in item.get('checks', {}).values() for item in results):
        return 'failed', 1
    if len(results) != expected_count or any(set(item.get('checks', {})) != {
            'protocolStructure', 'selectionExclusions', 'replyLanguage', 'presetCapabilityReasons', 'interaction'} or
            any(item['checks'][k] != 'pass' for k in ('protocolStructure', 'selectionExclusions', 'interaction')) or
            any(v not in ('pass', 'not-applicable') for v in item['checks'].values()) or
            (item['checks']['replyLanguage'] == 'not-applicable' and
             (item.get('plan', {}).get('reasons') or item.get('plan', {}).get('question') or not item.get('plan'))) or
            (item['checks']['presetCapabilityReasons'] == 'not-applicable' and
             (item.get('plan', {}).get('reasons') or not item.get('plan'))) for item in results):
        return 'incomplete-or-pending-review', 3
    return 'passed', 0
