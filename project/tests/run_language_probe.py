"""Explicit paid, text-only protocol probe. Uses the existing private shell env.

One request, no repair. Does not start a server, GPU, task, or image operation.
The 2026-10-11 HTTP attempt already reserves two of the authorized 40 calls.
"""
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from language import LanguageAdapter, LanguageError


def case_check(case, plan):
    selected = plan['presetIds']
    check = case['check']
    if check == 'sunny':
        return plan['status'] == 'ready' and selected == ['sunny']
    if check == 'bounded':
        return True  # Schema passed; subjective reasons require human review.
    if check == 'clarification':
        return plan['status'] == 'clarification'
    if check == 'no-night':
        return plan['status'] == 'ready' and 'street' not in selected and 'street' in plan['excludedIds']
    if check == 'first-only':
        return selected == case['current'][:1]
    if check == 'different':
        return plan['status'] == 'ready' and bool(selected) and not set(selected) & set(case['current'])
    if check == 'three':
        return plan['status'] == 'ready' and set(selected) == {'sunny', 'sunrise', 'street'}
    if check in ('precision', 'unrelated'):
        return check in plan['unsupported']
    return False


def direct_suite(single_tool=False, bounded=False, reviewed=False, auto_suite=False, thinking_suite=False):
    """One initial protocol case, then the other 19 only if protocol succeeds."""
    output = ROOT / ('qa/language-real-20261011/thinking-suite.json' if thinking_suite else
                     'qa/language-real-20261011/auto-suite.json' if auto_suite else
                     'qa/language-real-20261011/reviewed-suite.json' if reviewed else
                     'qa/language-real-20261011/bounded-suite.json' if bounded else
                     'qa/language-real-20261011/single-tool-suite.json' if single_tool else
                     'qa/language-real-20261011/direct-suite.json')
    prior_file = output.with_name('reviewed-suite.json' if auto_suite or thinking_suite else 'protocol-matrix.json' if reviewed else 'single-tool-suite.json' if bounded else 'direct-suite.json' if single_tool else 'protocol-probe.json')
    if output.exists():
        print('Suite already recorded; do not delete reports to repeat paid requests.')
        return 2
    if not prior_file.exists():
        print('Missing prior probe ledger; stop.')
        return 2
    prior = json.loads(prior_file.read_text(encoding='utf-8'))
    if auto_suite or thinking_suite:
        if thinking_suite and output.with_name('auto-suite.json').exists():
            print('Another paid run was recorded after this budget baseline; review it first.')
            return 2
        previous_cases = prior.get('cases', [])
        reviewed_ok = (prior.get('totalRequestsReserved') == 17 and prior.get('requestsThisRun') == 3 and
                       prior.get('status') == 'stopped-on-error' and len(previous_cases) == 3 and
                       previous_cases[-1].get('errorCode') == 'LANGUAGE_OUTPUT_TRUNCATED')
    elif reviewed:
        reviewed_ok = (prior.get('totalRequestsReserved') == 14 and prior.get('requestsThisRun') == 6 and
                       prior.get('status') == 'comparison-completed-requires-review' and
                       len(prior.get('cases', [])) == 6 and all(c.get('status') == 'valid' for c in prior['cases']))
    elif bounded:
        previous_cases = prior.get('cases', [])
        reviewed_ok = (prior.get('totalRequestsReserved') == 7 and prior.get('requestsThisRun') == 2 and
                    prior.get('status') == 'stopped-on-error' and len(previous_cases) == 2 and
                    previous_cases[-1].get('errorCode') == 'LANGUAGE_OUTPUT_TRUNCATED')
    elif single_tool:
        previous_cases = prior.get('cases', [])
        reviewed_ok = (prior.get('totalRequestsReserved') == 5 and prior.get('requestsThisRun') == 2 and
                    prior.get('status') == 'stopped-on-error' and len(previous_cases) == 2 and
                    previous_cases[-1].get('protocol', {}).get('toolCallCount') == 2)
    else:
        reviewed_ok = prior.get('totalRequestsReserved') == 3 and prior.get('protocol', {}).get('finishReason') == 'length'
    if not reviewed_ok:
        print('Prior report differs from the reviewed diagnosis; stop.')
        return 2
    prior_count = 17 if auto_suite or thinking_suite else 14 if reviewed else 7 if bounded else 5 if single_tool else 3
    presets = json.loads((ROOT / 'data/catalog.json').read_text(encoding='utf-8'))['presets']
    adapter = LanguageAdapter.from_env(presets)
    if not adapter.enabled:
        print('LANGUAGE_NOT_CONFIGURED: use the same privately configured PowerShell.')
        return 2
    if (adapter.model != 'nvidia/Nemotron-3_5-Lightning' or
            adapter.endpoint != 'https://api.tokenfactory.nebius.com/v1/chat/completions' or
            adapter.output_mode != 'tool' or adapter.max_tokens > (40960 if thinking_suite else 4096 if auto_suite else 1000 if bounded or reviewed else 600) or (not thinking_suite and adapter.thinking_mode == 'on')):
        print('Configuration differs from the authorized direct-answer plan; stop.')
        return 2
    adapter.repair_attempts = 0
    if bounded or reviewed or auto_suite:
        # Explicit evaluation mode only; normal product default remains 600.
        adapter.max_tokens = 1000
    if auto_suite:
        adapter.tool_selection = 'auto'
        adapter.max_tokens = 4096
        adapter.timeout = 20
    if thinking_suite:
        adapter.tool_selection = 'auto'
        adapter.thinking_mode = 'on'
        adapter.max_tokens = 40960
        adapter.timeout = 60
    cases = json.loads((ROOT / 'tests/language_cases.json').read_text(encoding='utf-8'))
    if len(cases) != 20:
        print('Expected exactly 20 reviewed cases; stop.')
        return 2
    if single_tool or bounded:
        # Keep the accepted Chinese result; probe the failed English case first,
        # then evaluate the 18 cases not yet sent. Avoid paying to repeat success.
        cases = cases[1:]
    if thinking_suite:
        wanted = ('explicit-en', 'mood-zh', 'mood-en', 'negation-zh', 'remove-en', 'precision-zh')
        cases = [next(c for c in cases if c['id'] == key) for key in wanted]
    reserve = (15000 * .06 + adapter.max_tokens * .24) / 1000000
    # Conservative reserve for prior calls under the earlier <=4096 budget;
    # do not multiply already-completed calls by the newly increased cap.
    prior_reserve = prior_count * (15000 * .06 + 4096 * .24) / 1000000 if thinking_suite else prior_count * reserve
    report = {'date': '2026-10-11', 'model': adapter.model, 'thinking': adapter.thinking_mode == 'on',
              'gpuEnabled': False, 'parallelToolCalls': False, 'maxTokens': adapter.max_tokens,
              'toolChoice': adapter.tool_selection,
              'timeoutSeconds': adapter.timeout,
              'priorRequestsReserved': prior_count, 'requestsThisRun': 0,
              'priorPlanningCostReservedUSD': round(prior_reserve, 8),
              'totalRequestsReserved': prior_count, 'reportedTokenCostEstimateThisRunUSD': 0,
              'status': 'started', 'cases': []}
    output.parent.mkdir(parents=True, exist_ok=True)
    def save():
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    save()
    original = adapter.transport
    def counted(payload, remaining):
        # Guard immediately before each outbound request; never log payload/key.
        if (report['totalRequestsReserved'] >= 40 or (thinking_suite and report['requestsThisRun'] >= 6) or
                prior_reserve + (report['requestsThisRun'] + 1) * reserve > .10 or
                len(json.dumps(payload, ensure_ascii=False).encode('utf-8')) > 10000):
            raise LanguageError('ACCEPTANCE_BUDGET_STOP', '验收预算边界，停止调用。')
        report['requestsThisRun'] += 1
        report['totalRequestsReserved'] += 1
        report['planningCostReservedUSD'] = round(prior_reserve + report['requestsThisRun'] * reserve, 8)
        save()  # Persist reservation before calling, including timeout/crash cases.
        return original(payload, remaining)
    adapter.transport = counted
    for case in cases:
        item = {'id': case['id'], 'status': 'started'}
        report['cases'].append(item)
        save()
        started = time.monotonic()
        try:
            plan = adapter.recommend({'text': case['text'], 'currentPlan': {
                'presetIds': case['current'], 'excludedIds': []},
                'compareThree': case['check'] == 'three'})
            item.update(status='valid', plan=plan, constraintCheck=case_check(case, plan),
                        explanationReview='pending-human-review')
            explanation = ' '.join(plan['reasons'] + [plan['question']]).strip()
            expected_chinese = bool(re.search(r'[\u4e00-\u9fff]', case['text']))
            item['languageShapeCheck'] = (not explanation or
                bool(re.search(r'[\u4e00-\u9fff]', explanation)) == expected_chinese)
        except LanguageError as error:
            item.update(status='failed', errorCode=error.code)
        item['elapsedSeconds'] = round(time.monotonic() - started, 3)
        item['protocol'] = adapter.last_response_audit
        usage = item['protocol'].get('usage', {})
        if 'prompt_tokens' in usage and 'completion_tokens' in usage:
            amount = (usage['prompt_tokens'] * .06 + usage['completion_tokens'] * .24) / 1000000
            item['reportedTokenCostEstimateUSD'] = round(amount, 8)
            report['reportedTokenCostEstimateThisRunUSD'] = round(
                report['reportedTokenCostEstimateThisRunUSD'] + amount, 8)
        save()
        print(case['id'], item['status'], item.get('constraintCheck', item.get('errorCode')), flush=True)
        if item['status'] == 'failed':
            report['status'] = 'stopped-on-error'
            break
    else:
        report['status'] = 'completed-requires-human-review'
    save()
    print('Report:', output)
    print('Reserved requests:', report['totalRequestsReserved'], '/ 40; GPU remains disabled.')
    return 0 if report['status'].startswith('completed') else 1


def main():
    if sys.argv[1:] == ['--direct-suite']:
        return direct_suite()
    if sys.argv[1:] == ['--single-tool-suite']:
        return direct_suite(single_tool=True)
    if sys.argv[1:] == ['--bounded-suite']:
        return direct_suite(bounded=True)
    if sys.argv[1:] == ['--reviewed-suite']:
        return direct_suite(reviewed=True)
    if sys.argv[1:] == ['--auto-suite']:
        return direct_suite(auto_suite=True)
    if sys.argv[1:] == ['--thinking-suite']:
        return direct_suite(thinking_suite=True)
    if sys.argv[1:]:
        print('Usage: run_language_probe.py [--direct-suite | --single-tool-suite | --bounded-suite | --reviewed-suite | --auto-suite | --thinking-suite]')
        return 2
    output = ROOT / 'qa/language-real-20261011/protocol-probe.json'
    if output.exists():
        print('Probe already recorded. Stop; review the saved report before another paid call.')
        return 2
    presets = json.loads((ROOT / 'data/catalog.json').read_text(encoding='utf-8'))['presets']
    try:
        adapter = LanguageAdapter.from_env(presets)
    except LanguageError as error:
        print(error.code)
        return 2
    if not adapter.enabled:
        print('LANGUAGE_NOT_CONFIGURED: run in the shell where the server key was privately configured.')
        return 2
    if (adapter.model != 'nvidia/Nemotron-3_5-Lightning' or
            adapter.endpoint != 'https://api.tokenfactory.nebius.com/v1/chat/completions' or
            adapter.output_mode != 'tool' or adapter.max_tokens > 600):
        print('Stop: model, endpoint, tool mode or token cap differs from the authorized plan.')
        return 2
    adapter.repair_attempts = 0
    # Fixed tiny context; conservative planning reservation (not metered usage).
    reserve = (15000 * .06 + 600 * .24) / 1000000
    report = {'date': '2026-10-11', 'case': 'explicit-zh-protocol',
              'model': adapter.model, 'maximumRequestsThisProbe': 1,
              'priorRequestsReserved': 2, 'totalRequestsReserved': 3,
              'planningCostReservedUSD': round(3 * reserve, 8),
              'gpuEnabled': False, 'status': 'started'}
    output.parent.mkdir(parents=True, exist_ok=True)
    # Write before sending: a crash must not allow an unnoticed repeat.
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    started = time.monotonic()
    try:
        report['plan'] = adapter.recommend({'text': '晴日公园',
            'currentPlan': {'presetIds': [], 'excludedIds': []}, 'compareThree': False})
        report['status'] = 'valid'
    except LanguageError as error:
        report['status'] = 'failed'
        report['errorCode'] = error.code
    report['elapsedSeconds'] = round(time.monotonic() - started, 3)
    report['protocol'] = adapter.last_response_audit
    usage = report['protocol'].get('usage', {})
    if 'prompt_tokens' in usage and 'completion_tokens' in usage:
        report['reportedTokenCostEstimateUSD'] = round(
            (usage['prompt_tokens'] * .06 + usage['completion_tokens'] * .24) / 1000000, 8)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print('Stopped after this probe. Review before resuming the remaining suite; no automatic retries.')
    return 0 if report['status'] == 'valid' else 1


if __name__ == '__main__':
    raise SystemExit(main())
