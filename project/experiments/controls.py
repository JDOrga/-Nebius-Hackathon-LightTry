"""Single-factor HDR experiment around the UNCHANGED official renderer callable.

The 180 degree + flip loading convention is retained. Offset is added to it;
rotate_light is never used as an angle. Neural response is a separate gate.
"""
import copy
import hashlib
import inspect
import json
from pathlib import Path
import time

from inference.jobs import atomic, read
from inference.reuse import key, safe_file

VERSION = 'hdr-controls-experiment-v1'
CASES = (
    {'id': 'baseline', 'offsetDeg': 0, 'strength': 1.0},
    {'id': 'rotation-minus45', 'offsetDeg': -45, 'strength': 1.0},
    {'id': 'rotation-plus45', 'offsetDeg': 45, 'strength': 1.0},
    {'id': 'strength-low', 'offsetDeg': 0, 'strength': 0.7},
    {'id': 'strength-high', 'offsetDeg': 0, 'strength': 1.4},
    {'id': 'baseline-repeat', 'offsetDeg': 0, 'strength': 1.0},
)


def normalize(offset=0, strength=1):
    # Experiment-only whitelist. No free-form range or implicit bool conversion.
    if type(offset) not in (int, float) or type(strength) not in (int, float):
        raise ValueError('NUMERIC_HDR_PARAMETERS_REQUIRED')
    if offset not in (-45, 0, 45) or strength not in (0.7, 1, 1.4):
        raise ValueError('HDR_EXPERIMENT_VALUES_NOT_ALLOWED')
    if offset != 0 and strength != 1:
        raise ValueError('ONE_FACTOR_AT_A_TIME_REQUIRED')
    return {'offsetDeg': int(offset), 'strength': float(strength),
            'envRot': 180.0 + offset, 'envFlip': True,
            'rotateEnvlight': False, 'logScale': 10000, 'version': VERSION}


def summarize_tensor(tensor, baseline=None):
    import numpy as np
    array = tensor.detach().float().cpu().numpy()
    if not np.isfinite(array).all():
        raise ValueError('NONFINITE_CONDITION')
    result = {'shape': list(array.shape), 'dtype': str(tensor.dtype),
        'sha256': hashlib.sha256(array.tobytes()).hexdigest(),
        'min': float(array.min()), 'max': float(array.max()), 'mean': float(array.mean()),
        'zeroFraction': float((array == 0).mean()), 'oneFraction': float((array == 1).mean())}
    if baseline is not None:
        delta = array - baseline
        result.update(maeVsBaseline=float(np.abs(delta).mean()), maxDelta=float(np.abs(delta).max()))
    return result, array


def condition_hook(original, parameters, path, baseline_arrays, *, capture=True):
    """Bind literal helper parameters and record actual returned conditioning tensors."""
    from light_console import preprocessing_parameters
    expected = preprocessing_parameters(parameters)
    signature = inspect.signature(original)
    for name in ('env_rot', 'env_strength', 'env_flip', 'rotate_envlight', 'log_scale'):
        if name not in signature.parameters:
            raise ValueError('OFFICIAL_HELPER_SIGNATURE_CHANGED')
    calls = []
    def hooked(*args, **kwargs):
        bound = signature.bind(*args, **kwargs)
        bound.apply_defaults()
        if (bound.arguments['num_frames'] != 1 or bound.arguments['fixed_pose'] is not True or
                bound.arguments['rotate_envlight'] is not False or
                bound.arguments['env_format'] != ['proj']):
            raise ValueError('FIXED_CONDITIONING_CONFIGURATION_REQUIRED')
        bound.arguments.update(env_rot=expected['envRot'], env_strength=expected['strength'],
                               env_flip=True, rotate_envlight=False, log_scale=10000)
        result = original(*bound.args, **bound.kwargs)
        fields = {}
        for name in ('env_ldr', 'env_log'):
            fields[name], array = summarize_tensor(result[name], baseline_arrays.get(name))
            if name not in baseline_arrays:
                baseline_arrays[name] = array.copy()
            if capture:
                from PIL import Image
                import numpy as np
                Image.fromarray((np.clip(array[0], 0, 1) * 255).astype('uint8')).save(
                    path / (name + '.png'))
        report = {'parameters': expected, 'metadata': result['metadata'], 'fields': fields,
            'transformOrder': ['decode float32 HDR', 'multiply strength',
                'nan_to_num then clamp [0,65504]', 'horizontal flip',
                'roll int(width*(180+offset)/360)', '512 cubemap',
                'fixed camera projection', 'Reinhard/sRGB and log/sRGB'],
            'conditionChangedIsNotModelControl': True}
        import numpy as np
        if not (path / 'condition-arrays.npz').exists():
            np.savez(path / 'condition-arrays.npz', **{
                name: result[name].detach().float().cpu().numpy() for name in ('env_ldr', 'env_log')})
        calls.append(report)
        atomic(path / 'condition.json', report)
        return result
    return hooked, calls


def run_controlled_forward(args, module, timeline, state_root, validate_output, original_run):
    """One real pipeline, six bounded cases, exact source-specific inverse artifacts."""
    packet = state_root.parent.parent / 'experiment.json'
    plan = read(safe_file(packet.parent, packet.name))
    if (plan['version'] != VERSION or plan['cases'] != list(CASES) or
            list(args.envlight_ind) != [0] or args.seed != 1000 or args.num_steps != 15 or
            args.height != 704 or args.width != 1280 or args.num_video_frames != 1 or args.rotate_light):
        raise ValueError('FROZEN_EXPERIMENT_CONFIGURATION_REQUIRED')
    shared = None
    constructor = module.DiffusionRendererPipeline
    official_helper = module.process_environment_map
    initializations = 0
    active_directory = None
    actual_calls = []
    def retained(**kwargs):
        nonlocal shared, initializations
        if shared is None:
            shared = constructor(**kwargs)
            initializations += 1
            timeline.emit('experiment_pipeline_ready', modelObjectId=hex(id(shared)))
            original_generate = shared.generate_video
            def observed_generate(*a, **kw):
                import numpy as np
                batch = kw['data_batch']
                recorded = {}
                with np.load(active_directory / 'condition-arrays.npz') as archive:
                    for name in ('env_ldr', 'env_log'):
                        recorded[name], actual = summarize_tensor(batch[name])
                        expected = archive[name][None].transpose(0, 4, 1, 2, 3) * 2 - 1
                        if not np.array_equal(actual, expected):
                            raise ValueError('MODEL_BATCH_CONDITION_MISMATCH')
                recorded['env_nrm'], _ = summarize_tensor(batch['env_nrm'])
                atomic(active_directory / 'model-condition.json', recorded)
                actual_calls.append(active_directory.name)
                return original_generate(*a, **kw)
            shared.generate_video = observed_generate
        return shared
    module.DiffusionRendererPipeline = retained
    base_identity = read(state_root / 'identities.json')['0']
    input_args = copy.deepcopy(args)
    try:
        for ordinal, case in enumerate(CASES):
            directory = state_root.parent / 'controls' / case['id']
            directory.mkdir(parents=True, exist_ok=True)
            expected = {'0': {**base_identity, 'experiment': normalize(case['offsetDeg'], case['strength']),
                              'caseId': case['id'], 'packetSha256': key(plan)}}
            if (directory / 'identities.json').exists():
                if read(directory / 'identities.json') != expected:
                    raise ValueError('EXPERIMENT_RESUME_IDENTITY_MISMATCH')
            else:
                atomic(directory / 'identities.json', expected)
            if ordinal == 0:
                baseline_arrays = {}
                if (directory / '0/complete.json').exists():
                    import numpy as np
                    with np.load(directory / 'condition-arrays.npz') as arrays:
                        baseline_arrays.update({name: arrays[name].copy() for name in ('env_ldr', 'env_log')})
            active_directory = directory
            module.process_environment_map, calls = condition_hook(
                official_helper, case, directory, baseline_arrays)
            case_args = copy.deepcopy(input_args)
            with timeline.span('control_case', caseId=case['id']):
                original_run(case_args, module, timeline, directory, validate_output)
            reused = (directory / '0/complete.json').is_file() and not calls
            if not reused and len(calls) != 1:
                raise ValueError('EXACTLY_ONE_HDR_CONDITION_CALL_REQUIRED')
            if not reused and actual_calls.count(case['id']) != 1:
                raise ValueError('EXACTLY_ONE_MODEL_CONDITION_CALL_REQUIRED')
            # Baseline repeat is a distinct result, not a reused marker.
        timeline.emit('experiment_complete', initializationCount=initializations,
                      modelObjectId=hex(id(shared)), cases=len(CASES))
    finally:
        module.process_environment_map = official_helper
        module.DiffusionRendererPipeline = constructor


def dispatch_entry(original_run):
    def controlled(args, module, timeline, state_root, validate_output):
        return run_controlled_forward(args, module, timeline, state_root, validate_output, original_run)
    return controlled
