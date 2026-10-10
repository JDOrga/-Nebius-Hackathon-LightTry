"""Read-only local batch plan. Prints JSON; cannot start, submit or infer."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'project'))
from inference.jobs import ID, read
from inference.reuse import identity, key, validate, safe_file


def plan(task_id, preset_ids, cold=False):
    if not ID.fullmatch(task_id):
        raise ValueError('LOCAL_TASK_ID_REQUIRED')
    catalog = {p['id']: p for p in read(ROOT / 'project/data/catalog.json')['presets']}
    if not preset_ids or len(preset_ids) > 3 or len(set(preset_ids)) != len(preset_ids):
        raise ValueError('ONE_TO_THREE_UNIQUE_PRESETS_REQUIRED')
    presets = [catalog[p] for p in preset_ids]
    source = ROOT / 'project/.tasks' / task_id
    request = read(safe_file(source, 'request.json'))
    value = identity(request, safe_file(source, 'inputs/photo.png').read_bytes(),
                     read(ROOT / 'manifests/weights_manifest.json'), read(ROOT / 'manifests/patch_manifest.json'))
    registry = ROOT / 'project/.inverse-cache' / key(value)
    reusable = None
    if not cold and registry.exists():
        try: reusable = validate(registry, value)['source']
        except (OSError, ValueError, KeyError): pass
    return {'mode': 'LOCAL_PLAN_ONLY_NO_EXECUTION', 'sourceTaskId': task_id,
        'selectedPresets': presets, 'inverseKey': key(value), 'reuseSource': reusable,
        'inverseExecutions': 0 if reusable else 1, 'forwardInitializations': 1,
        'forwardOrder': preset_ids, 'randomPolicy': 'reset-before-forward-generate-v1',
        'workerRequestExtension': {'presets': presets, 'preset': presets[0]},
        'weightVerification': request['runConfig']['weightVerification'],
        'authorization': 'NEW explicit budget/window/upload approval required; keep RUNNING 18/25/27 and earlier absolute deadline',
        'timing': ['process_start', 'model_construction', 'weight_deserialization',
                   'module_device_or_dtype_migration', 'generation(first=true)', 'preset', 'result_write'],
        'coldInverse': cold, 'localDriverConfigForColdRun': {'reuse_inverse': False} if cold else None,
        'gpuValidated': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--task-id', required=True)
    parser.add_argument('--presets', nargs='+', choices=('sunny', 'sunrise', 'street'), required=True)
    parser.add_argument('--cold-inverse', action='store_true')
    args = parser.parse_args()
    print(json.dumps(plan(args.task_id, args.presets, args.cold_inverse), ensure_ascii=False, indent=2))
