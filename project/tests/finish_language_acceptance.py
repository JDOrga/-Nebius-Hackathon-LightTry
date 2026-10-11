"""Explicit thinking-on acceptance; <=17 calls, cumulative <=40 and <=$0.10.

Released planning reserves use reported token usage; unknown requests keep a
conservative reserve. No retries, images, tool execution, GPU or key logging.
"""
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
from language import LanguageAdapter, LanguageError
from run_language_probe import case_check


def run(remaining=False):
    folder = ROOT / 'qa/language-real-20261011'
    output = folder / ('final-coverage.json' if remaining else 'completion-suite.json')
    if output.exists():
        print('Report exists; stop. Do not delete reports to repeat paid calls.')
        return 2
    if (folder / 'auto-suite.json').exists():
        print('Unexpected additional paid run; review the ledger first.')
        return 2
    previous = json.loads((folder / 'thinking-suite.json').read_text(encoding='utf-8'))
    if (previous.get('totalRequestsReserved') != 23 or previous.get('requestsThisRun') != 6 or
            previous.get('status') != 'completed-requires-human-review'):
        print('Prior ledger differs from reviewed state; stop.')
        return 2
    completion = None
    if remaining:
        completion = json.loads((folder / 'completion-suite.json').read_text(encoding='utf-8'))
        if (completion.get('totalRequestsReserved') != 33 or completion.get('requestsThisRun') != 10 or
                completion.get('inFlightReserveUSD') != 0 or
                completion.get('status') != 'stopped-on-error-or-missing-usage' or
                completion.get('cases', [{}])[-1].get('errorCode') != 'INVALID_MODEL_OUTPUT'):
            print('Completion ledger differs from reviewed state; stop.')
            return 2
    # Every billable run is counted once. Initial HTTP has no provider usage;
    # keep its two possible calls at the conservative previous 4096-token cap.
    names = ('protocol-probe.json', 'direct-suite.json', 'single-tool-suite.json',
             'bounded-suite.json', 'protocol-matrix.json', 'reviewed-suite.json', 'thinking-suite.json')
    known = 0
    for name in names:
        record = json.loads((folder / name).read_text(encoding='utf-8'))
        known += record['reportedTokenCostEstimateUSD'] if name == 'protocol-probe.json' else record['reportedTokenCostEstimateThisRunUSD']
    unknown = 2 * (15000 * .06 + 4096 * .24) / 1000000
    if remaining:
        known += completion['reportedTokenCostEstimateThisRunUSD']
        unknown = completion['unknownCostReserveUSD']
    presets = json.loads((ROOT / 'data/catalog.json').read_text(encoding='utf-8'))['presets']
    adapter = LanguageAdapter.from_env(presets)
    if not adapter.enabled:
        print('LANGUAGE_NOT_CONFIGURED: use the privately configured PowerShell.')
        return 2
    if adapter.model != 'nvidia/Nemotron-3_5-Lightning' or adapter.endpoint != 'https://api.tokenfactory.nebius.com/v1/chat/completions':
        print('Model or endpoint differs from authorization; stop.')
        return 2
    adapter.max_tokens, adapter.timeout = 40960, 60
    adapter.thinking_mode, adapter.tool_selection = 'on', 'auto'
    adapter.output_mode, adapter.repair_attempts = 'tool', 0
    cases = json.loads((ROOT / 'tests/language_cases.json').read_text(encoding='utf-8'))
    if len(cases) != 20:
        print('Expected 20 reviewed cases; stop.')
        return 2
    prior_ids = {c['id'] for c in previous['cases']}
    regressions = ('precision-zh', 'mood-zh', 'mood-en')
    selected = [next(c for c in cases if c['id'] == key) for key in regressions]
    selected += [c for c in cases if c['id'] not in prior_ids]
    if remaining:
        prior_ids.update(c['id'] for c in completion['cases'])
        selected = [c for c in cases if c['id'] not in prior_ids]
    maximum = 7 if remaining else 17
    baseline = 33 if remaining else 23
    if len(selected) != maximum:
        print('Unexpected remaining case count; stop.')
        return 2
    reserve = (15000 * .06 + 40960 * .24) / 1000000
    report = {'date': '2026-10-11', 'model': adapter.model, 'thinking': True,
              'toolChoice': 'auto', 'maxTokens': 40960, 'timeoutSeconds': 60,
              'gpuEnabled': False, 'priorRequestsReserved': baseline, 'requestsThisRun': 0,
              'totalRequestsReserved': baseline, 'knownPriorTokenCostEstimateUSD': round(known, 8),
              'unknownCostReserveUSD': round(unknown, 8), 'inFlightReserveUSD': 0,
              'reportedTokenCostEstimateThisRunUSD': 0, 'feeLimitUSD': .10,
              'status': 'started', 'cases': []}
    def save():
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    save()
    original = adapter.transport
    def counted(payload, remaining):
        spent = known + report['reportedTokenCostEstimateThisRunUSD'] + report['unknownCostReserveUSD']
        if (report['requestsThisRun'] >= maximum or report['totalRequestsReserved'] >= 40 or
                spent + reserve > .10 or len(json.dumps(payload, ensure_ascii=False).encode('utf-8')) > 10000):
            raise LanguageError('ACCEPTANCE_BUDGET_STOP', '验收预算已到边界。')
        report['requestsThisRun'] += 1
        report['totalRequestsReserved'] += 1
        report['inFlightReserveUSD'] = reserve
        save()  # Charge/reserve before sending; a crash cannot erase the call.
        return original(payload, remaining)
    adapter.transport = counted
    for case in selected:
        item = {'id': case['id'], 'status': 'started'}
        report['cases'].append(item)
        adapter.last_response_audit = {}
        save()
        started = time.monotonic()
        try:
            plan = adapter.recommend({'text': case['text'], 'currentPlan': {
                'presetIds': case['current'], 'excludedIds': []}, 'compareThree': case['check'] == 'three'})
            text = ' '.join(plan['reasons'] + [plan['question']]).strip()
            item.update(status='valid', plan=plan, constraintCheck=case_check(case, plan),
                languageShapeCheck=not text or bool(re.search(r'[\u4e00-\u9fff]', text)) == bool(re.search(r'[\u4e00-\u9fff]', case['text'])),
                explanationReview='pending-human-review')
        except LanguageError as error:
            item.update(status='failed', errorCode=error.code)
        item['elapsedSeconds'] = round(time.monotonic() - started, 3)
        item['protocol'] = adapter.last_response_audit
        usage = item['protocol'].get('usage', {})
        if 'prompt_tokens' in usage and 'completion_tokens' in usage:
            amount = (usage['prompt_tokens'] * .06 + usage['completion_tokens'] * .24) / 1000000
            item['reportedTokenCostEstimateUSD'] = round(amount, 8)
            report['reportedTokenCostEstimateThisRunUSD'] = round(report['reportedTokenCostEstimateThisRunUSD'] + amount, 8)
            report['inFlightReserveUSD'] = 0  # Completed reservation released.
        elif report['inFlightReserveUSD']:
            report['unknownCostReserveUSD'] = round(report['unknownCostReserveUSD'] + reserve, 8)
            report['inFlightReserveUSD'] = 0
            item['usageMissing'] = True
        save()
        print(case['id'], item['status'], item.get('constraintCheck', item.get('errorCode')), flush=True)
        if ((item['status'] == 'failed' and (not remaining or item.get('errorCode') not in
                ('INVALID_MODEL_OUTPUT', 'LANGUAGE_OUTPUT_TRUNCATED'))) or item.get('usageMissing')):
            report['status'] = 'stopped-on-error-or-missing-usage'
            break
    else:
        report['status'] = 'completed-requires-human-review'
    save()
    print('Report:', output)
    print('Reserved request count:', report['totalRequestsReserved'], '/40; GPU disabled.')
    return 0 if report['status'].startswith('completed') else 1


if __name__ == '__main__':
    if sys.argv[1:] not in ([], ['--remaining']):
        print('Usage: finish_language_acceptance.py [--remaining]')
        raise SystemExit(2)
    raise SystemExit(run(remaining=sys.argv[1:] == ['--remaining']))
