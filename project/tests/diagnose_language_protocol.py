"""Explicit paid protocol comparison, <=6 calls, no images/GPU or tool execution.

Uses only the existing private server environment. Does not save raw replies.
Not a semantic/model benchmark. Existing reports must remain intact.
"""
import copy
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from language import LanguageAdapter, LanguageError, strict_json, validate_plan


def payloads(adapter):
    minimal = {'model': adapter.model, 'max_tokens': 1000, 'store': False,
               'messages': [{'role': 'system', 'content': 'Select the named lighting preset. Return one call to propose_lighting_plan, with presetId sunny. No other content.'},
                            {'role': 'user', 'content': 'sunny'}],
               'tools': [{'type': 'function', 'function': {'name': 'propose_lighting_plan',
                         'description': 'Return preset selection data only; no execution.',
                         'parameters': {'type': 'object', 'properties': {'presetId': {
                             'type': 'string', 'enum': ['sunny', 'sunrise', 'street']}},
                             'required': ['presetId'], 'additionalProperties': False}}}],
               'tool_choice': {'type': 'function', 'function': {'name': 'propose_lighting_plan'}},
               'parallel_tool_calls': False, 'chat_template_kwargs': {'enable_thinking': False}}
    # Reuse the exact production prompt/schema builder without a paid call.
    # The synthetic plan below is only a construction return, never evidence.
    captured = []
    builder = LanguageAdapter([{'id': key, 'hdr': hdr} for key, hdr in (
        ('sunny', 'sunny_vondelpark_2k.hdr'), ('sunrise', 'pink_sunrise_2k.hdr'), ('street', 'street_lamp_2k.hdr'))],
        enabled=True, key='OFFLINE_PAYLOAD_BUILDER_ONLY', model=adapter.model, max_tokens=1000, thinking_mode='off',
        transport=lambda payload, _: captured.append(copy.deepcopy(payload)) or json.dumps({
            'status': 'ready', 'presetIds': ['sunny'], 'reasons': ['Offline construction only.'],
            'excludedIds': [], 'unsupported': [], 'question': ''}))
    builder.recommend({'text': 'sunny', 'currentPlan': {'presetIds': [], 'excludedIds': []}, 'compareThree': False})
    full = captured[0]
    full['store'] = False
    cases = []
    for name, base, changes in [
        ('minimal-forced-top', minimal, {}),
        ('minimal-auto-top', minimal, {'tool_choice': 'auto'}),
        ('minimal-forced-nested', minimal, {'nested': True}),
        ('minimal-forced-nonempty', minimal, {'nonempty': True}),
        ('full-forced-top', full, {}),
        ('full-auto-top', full, {'tool_choice': 'auto'}),
    ]:
        payload = copy.deepcopy(base)
        if changes.get('nested'):
            payload['extra_body'] = {'chat_template_kwargs': payload.pop('chat_template_kwargs')}
        if changes.get('nonempty'):
            payload['chat_template_kwargs']['force_nonempty_content'] = True
        if 'tool_choice' in changes:
            payload['tool_choice'] = changes['tool_choice']
        cases.append((name, payload))
    return cases


def run():
    folder = ROOT / 'qa/language-real-20261011'
    output = folder / 'protocol-matrix.json'
    if output.exists():
        print('Report already exists; stop. Do not delete reports to repeat paid calls.')
        return 2
    prior_file = folder / 'bounded-suite.json'
    if not prior_file.exists():
        print('Missing prior budget ledger; stop.')
        return 2
    prior = json.loads(prior_file.read_text(encoding='utf-8'))
    if prior.get('totalRequestsReserved') != 8 or prior.get('status') != 'stopped-on-error':
        print('Prior budget differs from reviewed record; stop.')
        return 2
    presets = json.loads((ROOT / 'data/catalog.json').read_text(encoding='utf-8'))['presets']
    adapter = LanguageAdapter.from_env(presets)
    if not adapter.enabled:
        print('LANGUAGE_NOT_CONFIGURED: run in the same privately configured PowerShell.')
        return 2
    if adapter.model != 'nvidia/Nemotron-3_5-Lightning' or adapter.endpoint != 'https://api.tokenfactory.nebius.com/v1/chat/completions':
        print('Model or endpoint differs from authorized plan; stop.')
        return 2
    adapter.output_mode = 'tool'
    adapter.repair_attempts = 0
    report = {'date': '2026-10-11', 'kind': 'protocol-comparison-not-semantic-acceptance',
              'model': adapter.model, 'gpuEnabled': False, 'priorRequestsReserved': 8,
              'requestsThisRun': 0, 'totalRequestsReserved': 8, 'status': 'started',
              'reportedTokenCostEstimateThisRunUSD': 0, 'cases': []}
    folder.mkdir(parents=True, exist_ok=True)
    def save():
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    save()
    original = adapter.transport
    reserve = (15000 * .06 + 1000 * .24) / 1000000
    def counted(payload, remaining):
        if (report['requestsThisRun'] >= 6 or report['totalRequestsReserved'] >= 40 or
                (report['totalRequestsReserved'] + 1) * reserve > .10 or
                len(json.dumps(payload, ensure_ascii=False).encode('utf-8')) > 10000):
            raise LanguageError('ACCEPTANCE_BUDGET_STOP', 'Budget stop.')
        report['requestsThisRun'] += 1
        report['totalRequestsReserved'] += 1
        report['planningCostReservedUSD'] = round(report['totalRequestsReserved'] * reserve, 8)
        save()
        return original(payload, remaining)
    adapter.transport = counted
    for name, payload in payloads(adapter):
        item = {'id': name, 'status': 'started', 'maxTokens': 1000,
                'toolChoice': 'auto' if payload['tool_choice'] == 'auto' else 'fixed-function',
                'templateLocation': 'extra_body' if 'extra_body' in payload else 'top-level',
                'forceNonemptyContent': name.endswith('nonempty')}
        report['cases'].append(item)
        adapter.last_response_audit = {}
        save()
        started = time.monotonic()
        try:
            raw = adapter._bounded_transport(payload, adapter.timeout)
            parsed = strict_json(raw)
            if name.startswith('minimal'):
                valid = isinstance(parsed, dict) and set(parsed) == {'presetId'} and parsed['presetId'] == 'sunny'
                item['minimalSelectionMatch'] = valid
                item['status'] = 'valid' if valid else 'invalid-arguments'
            else:
                plan = validate_plan(parsed, adapter.allowed)
                if adapter._key and adapter._key in json.dumps(plan, ensure_ascii=False):
                    raise LanguageError('INVALID_MODEL_OUTPUT', 'Invalid credential echo.')
                item.update(status='valid', plan=plan, exactSelectionMatch=plan['presetIds'] == ['sunny'])
        except LanguageError as error:
            item.update(status='failed', errorCode=error.code)
        except (ValueError, TypeError, RecursionError):
            item.update(status='invalid-arguments', errorCode='INVALID_MODEL_OUTPUT')
        item['elapsedSeconds'] = round(time.monotonic() - started, 3)
        item['protocol'] = adapter.last_response_audit
        usage = item['protocol'].get('usage', {})
        if 'prompt_tokens' in usage and 'completion_tokens' in usage:
            amount = (usage['prompt_tokens'] * .06 + usage['completion_tokens'] * .24) / 1000000
            item['reportedTokenCostEstimateUSD'] = round(amount, 8)
            report['reportedTokenCostEstimateThisRunUSD'] = round(report['reportedTokenCostEstimateThisRunUSD'] + amount, 8)
        save()
        print(name, item['status'], item.get('errorCode', ''), flush=True)
        # Truncation/format failures are comparison observations, not retries.
        # Stop network/auth/rate/budget errors, avoiding repeated paid failures.
        if item.get('errorCode') not in (None, 'INVALID_MODEL_OUTPUT', 'LANGUAGE_OUTPUT_TRUNCATED'):
            report['status'] = 'stopped-on-service-error'
            break
    else:
        report['status'] = 'comparison-completed-requires-review'
    save()
    print('Report:', output)
    print('Total reserved requests:', report['totalRequestsReserved'], '/ 40. No automatic suite or GPU calls.')
    return 0 if report['status'].startswith('comparison') else 1


if __name__ == '__main__':
    raise SystemExit(run())
