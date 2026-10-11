"""OFFLINE scripted contract/flow evidence only. Never constructs real transport.

Exit 0 = offline mechanics complete; 1 = failure; 2 = preflight;
3 = incomplete. modelAcceptance always not-tested even with exit 0.
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from language import LanguageError
from serve_language_fixture import ScriptedLanguage
from acceptance_checks import dimensions, failure_dimensions
from freeze_language_candidate import snapshot


def run(output, manifest_path=None):
    if output.exists():
        print('Output exists; choose a new offline output file.')
        return 2
    candidate = snapshot()
    manifest = Path(manifest_path) if manifest_path else ROOT / 'docs/LANGUAGE_CANDIDATE_20261011_DEMO.json'
    if manifest_path and not manifest.is_file():
        print('Explicit offline snapshot missing; refused.')
        return 2
    if manifest.exists() and json.loads(manifest.read_text(encoding='utf-8'))['candidateSHA256'] != candidate['candidateSHA256']:
        print('Frozen candidate differs; do not pool results across changed sources.')
        return 2
    presets = json.loads((ROOT / 'data/catalog.json').read_text(encoding='utf-8'))['presets']
    adapter = ScriptedLanguage(presets)
    cases = json.loads((ROOT / 'tests/language_cases.json').read_text(encoding='utf-8'))
    cases += json.loads((ROOT / 'tests/language_regressions.json').read_text(encoding='utf-8'))
    plans, results = {}, []
    for source in cases:
        case = dict(source)
        previous = plans.get(case.get('after'))
        if case.get('after') and previous is None:
            results.append({'id': case['id'], 'status': 'skipped-dependency-failed'})
            continue
        current = {'presetIds': previous['presetIds'] if previous else case.get('current', []),
                   'excludedIds': previous['excludedIds'] if previous else case.get('excluded', [])}
        case['current'], case['excluded'] = current['presetIds'], current['excludedIds']
        expected = case.get('language', 'zh' if case['id'].endswith('-zh') else 'en')
        started = time.monotonic()
        item = {'id': case['id'], 'status': 'started', 'evidence': 'OFFLINE_SCRIPT_NOT_NEMOTRON'}
        try:
            plan = adapter.recommend({'text': case['text'], 'currentPlan': current,
                'compareThree': case['check'] == 'three',
                'responseLanguage': case.get('productLanguage', expected),
                **({'operation': case['operation']} if 'operation' in case else {})})
            item.update(status='valid', plan=plan, checks=dimensions(case, plan))
            if not any(v == 'fail' for v in item['checks'].values()):
                plans[case['id']] = plan
        except LanguageError as error:
            item.update(status='failed', errorCode=error.code, checks=failure_dimensions(adapter, error))
        item['elapsedSeconds'] = round(time.monotonic() - started, 3)
        item['operationAudit'] = adapter.last_operation_audit
        results.append(item)
    failed = any(r['status'] == 'failed' or 'fail' in r.get('checks', {}).values() for r in results)
    incomplete = any(r['status'].startswith('skipped') for r in results)
    report = {'evidence': 'OFFLINE_SCRIPT_NOT_NEMOTRON', 'realRequests': 0, 'modelAcceptance': 'not-tested',
              'candidateId':candidate['candidateId'], 'intendedConfiguration':candidate['config'], 'actualModel':'OFFLINE_SCRIPT',
              'expectedCases': len(cases), 'executedCases': sum(r['status'] != 'skipped-dependency-failed' for r in results),
              'offlineMechanics': 'failed' if failed else 'incomplete' if incomplete else 'passed',
              'cases': results, 'exitCode': 1 if failed else 3 if incomplete else 0}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(report['offlineMechanics'], len(results), 'offline cases; model acceptance NOT TESTED:', output)
    return report['exitCode']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, help='Explicit NEW offline source snapshot; never overwrite historical acceptance.')
    args=parser.parse_args()
    raise SystemExit(run(args.output,args.manifest))
