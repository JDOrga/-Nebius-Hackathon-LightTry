"""Local/guarded joint acceptance primitives. No lifecycle or provider calls."""
import copy
import hashlib
import inspect
import json
from pathlib import Path
import time

from inference.jobs import atomic, read
from inference.reuse import safe_file
from lighting import identity
from light_console import normalize, initial, synthesize, encode_hdr, preprocessing_parameters

VERSION = 'console-nemotron-joint-v1'


def changes(a, b, prefix=''):
    if isinstance(a, dict) and isinstance(b, dict):
        return [v for k in sorted(set(a) | set(b)) for v in changes(a.get(k), b.get(k), prefix + '/' + k)]
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        return [v for i, (x, y) in enumerate(zip(a, b)) for v in changes(x, y, prefix + '/' + str(i))]
    return [] if a == b else [{'field': prefix, 'before': a, 'after': b}]


def matrix(environments):
    b = initial(environments['sunny'])
    b.update(mode='procedural', environmentId=None, environmentSha256=None,
        zones=[dict(id='key', name='主光', enabled=True, azimuthDeg=45,
            elevationDeg=30, strength=3, color='#ffffff', sizeDeg=25)])
    recipes = {'A': initial(environments['sunny']), 'B': b}
    for name, field, value in [('C', 'azimuthDeg', 135), ('D', 'strength', 1.5), ('E', 'sizeDeg', 70)]:
        recipes[name] = copy.deepcopy(b); recipes[name]['zones'][0][field] = value
    recipes['F'] = copy.deepcopy(b)
    recipes['F']['zones'].append(dict(id='fill', name='补光', enabled=True,
        azimuthDeg=250, elevationDeg=20, strength=.7, color='#ffffff', sizeDeg=55))
    return {k: normalize(v, environments) for k, v in recipes.items()}


def energy(array):
    import numpy as np
    h, w, _ = array.shape
    weights = np.cos(np.pi / 2 - (np.arange(h) + .5) * np.pi / h)
    integral = (array.astype('float64') * weights[:, None, None]).sum(axis=(0, 1)) * (2 * np.pi / w) * (np.pi / h)
    return {'sphericalIntegralRGB': integral.tolist(), 'peakRGB': array.max(axis=(0, 1)).tolist(),
            'units': 'relative linear RGB radiance times steradians; not lux',
            'sizeSemantics': 'peak amplitude fixed; FWHM changes total energy, NOT energy-normalized'}


def verify_joint(prep):
    plan = read(safe_file(prep, 'joint.json'))
    envs = {e['id']: e for e in read(prep / 'project/next/runtime/environments.json')}
    if plan['version'] == 'direction-energy-key-unknowns-v1':
        from next.runtime.key_unknowns import recipes
        expected=recipes(envs)
        if len(plan['cases'])!=4:raise ValueError('JOINT_PLAN_VERSION_OR_COUNT')
    elif plan['version']==VERSION and 6<=len(plan['cases'])<=7:
        expected=matrix(envs)
    else:raise ValueError('JOINT_PLAN_VERSION_OR_COUNT')
    if [c['id'] for c in plan['cases'][:len(expected)]] != list(expected):
        raise ValueError('JOINT_CASE_ORDER')
    for c in plan['cases']:
        recipe = normalize(c['parameters'], envs)
        if recipe != c['parameters'] or identity(recipe) != c['recipeKey']:
            raise ValueError('JOINT_RECIPE_IDENTITY')
        if c['id'] in expected and recipe != expected[c['id']]:
            raise ValueError('JOINT_SINGLE_FACTOR_MATRIX_CHANGED')
        if c['id'] == 'AI':
            accepted = read(safe_file(prep, 'ai-applied.json'))
            if accepted['parameters'] != recipe or accepted['confirmed'] is not True or accepted['modelCalled'] is not True:
                raise ValueError('JOINT_REAL_AI_APPLICATION_REQUIRED')
            if accepted.get('photoBinding',{}).get('inputSha256')!=plan['input']['sha256']:
                raise ValueError('JOINT_AI_PHOTO_BINDING_MISMATCH')
        if c.get('hdrFile'):
            p = safe_file(prep, c['hdrFile'])
            if hashlib.sha256(p.read_bytes()).hexdigest() != c['hdrSha256']:
                raise ValueError('JOINT_HDR_HASH_MISMATCH')
    manifest = read(safe_file(prep, 'bundle_contents.json'))
    for entry in manifest['files']:
        if hashlib.sha256(safe_file(prep, entry['path']).read_bytes()).hexdigest() != entry['sha256']:
            raise ValueError('JOINT_FROZEN_PACKET_CHANGED')
    return plan


def strict_condition(original, recipe, hdr, expected_hash, directory, timeline, *, execution_device='cuda'):
    """Observe actual upstream decode / cleanup / transformed cubemap input.

    The original loader and projector execute unchanged. A substituted HDR is
    bound at process_environment_map.hdr_dir; missing hooks fail before forward.
    """
    import numpy as np
    from experiments.controls import summarize_tensor
    signature = inspect.signature(original)
    namespace = original.__globals__
    loader = namespace['load_and_preprocess_hdr']
    g = loader.__globals__
    torch, util, imageio = g['torch'], g['util'], g['imageio_v3']
    calls, arrays = [], {}
    params = preprocessing_parameters(recipe)

    def hook(*a, **kw):
        bound = signature.bind(*a, **kw); bound.apply_defaults()
        if (bound.arguments['resolution'] != (704, 1280) or bound.arguments['num_frames'] != 1 or
            bound.arguments['fixed_pose'] is not True or bound.arguments['rotate_envlight'] is not False or
            bound.arguments['env_format'] != ['proj'] or str(bound.arguments['device']) != execution_device):
            raise ValueError('PRODUCTION_CONDITION_CONFIGURATION_MISMATCH')
        if hdr.is_symlink() or hashlib.sha256(hdr.read_bytes()).hexdigest() != expected_hash:
            raise ValueError('ACTUAL_HDR_MISSING_OR_CHANGED')
        bound.arguments.update(hdr_dir=str(hdr), env_rot=params['envRot'], env_strength=params['strength'],
            env_flip=True, rotate_envlight=False, log_scale=10000)
        observed = {}
        imread, clean, cube = imageio.imread, torch.nan_to_num, util.latlong_to_cubemap
        mapping_original=namespace['hdr_mapping'];mapping_stats=[]
        def decode(path, *x, **y):
            if Path(path).resolve() != hdr.resolve(): raise ValueError('HDR_FALLBACK_FORBIDDEN')
            value = imread(path, *x, **y); observed['decoded'] = np.asarray(value).copy(); return value
        def cleanup(tensor, *x, **y):
            observed['beforeClamp'] = tensor.detach().float().cpu().numpy().copy()
            return clean(tensor, *x, **y)
        def cubemap(tensor, *x, **y):
            observed['transformed'] = tensor.detach().float().cpu().numpy().copy()
            return cube(tensor, *x, **y)
        def mapping(env_hdr,log_scale):
            mapped=mapping_original(env_hdr,log_scale)
            # Exact statistics derived from the ACTUAL projection supplied to
            # the unchanged mapping; equivalence to its returned clamp is checked.
            pre_log=util.rgb2srgb(torch.log1p(env_hdr)/np.log1p(log_scale))
            pre_reinhard=util.reinhard(env_hdr,max_point=16)
            if not torch.equal(pre_log.clamp(0,1),mapped['env_log']):raise ValueError('ACTUAL_LOG_CLAMP_MISMATCH')
            def truncation(value,post):
                arr=value.detach().float().cpu().numpy();out=(arr<0)|(arr>1)
                return {'beforeClipMax':float(arr.max()),'afterClipMax':float(post.max().item()),
                    'clippedChannelFraction':float(out.mean()),'clippedPixelFraction':float(out.any(axis=-1).mean())}
            mapping_stats.append({'projectedHDRMax':float(env_hdr.max().item()),
                'logSRGB':truncation(pre_log,mapped['env_log']),
                'reinhardLinear':truncation(pre_reinhard,pre_reinhard.clamp(0,1)),
                'computedFromActualMappingInputAndLogOutputMatched':True})
            return mapped
        imageio.imread, torch.nan_to_num, util.latlong_to_cubemap = decode, cleanup, cubemap
        namespace['hdr_mapping']=mapping
        try:
            if execution_device=='cuda': torch.cuda.synchronize()
            with timeline.span('condition_processing'):
                result = original(*bound.args, **bound.kwargs)
                if execution_device=='cuda': torch.cuda.synchronize()
        finally:
            imageio.imread, torch.nan_to_num, util.latlong_to_cubemap = imread, clean, cube
            namespace['hdr_mapping']=mapping_original
        if set(observed) != {'decoded', 'beforeClamp', 'transformed'}:
            raise ValueError('HDR_LOADER_HOOK_NOT_EFFECTIVE')
        if len(mapping_stats)!=1:raise ValueError('ACTUAL_MAPPING_HOOK_NOT_EFFECTIVE')
        raw, pre, transformed = (observed[k] for k in ('decoded', 'beforeClamp', 'transformed'))
        if not all(np.isfinite(x).all() for x in (raw, pre, transformed)):
            raise ValueError('NONFINITE_HDR_FORBIDDEN')
        expected = np.roll(np.flip(np.clip(pre, 0, 65504), axis=1), int(pre.shape[1] * params['envRot'] / 360), axis=1)
        if not np.array_equal(pre, raw.astype('float32') * params['strength']) or not np.array_equal(expected, transformed):
            raise ValueError('ACTUAL_HDR_TRANSFORM_MISMATCH')
        outside = (pre < 0) | (pre > 65504)
        stats = {'decodedMax': float(raw.max()), 'afterMultiplyBeforeClampMax': float(pre.max()),
            'afterClampAndTransformMax': float(transformed.max()),
            'clippedChannelFraction': float(outside.mean()),
            'clippedPixelFraction': float(outside.any(axis=2).mean()),
            'pixelDenominator': int(pre.shape[0]*pre.shape[1]), 'channelDenominator': int(pre.size),
            'decodedEnergy': energy(raw), 'transformedEnergy': energy(transformed),
            'afterClampBeforeTransformMax': float(np.clip(pre, 0, 65504).max())}
        fields = {}
        for name in ('env_ldr', 'env_log'):
            fields[name], arr = summarize_tensor(result[name]); arrays[name] = arr
            fields[name]['finite']=True
            if list(arr.shape) != [1, 704, 1280, 3] or arr.min() < 0 or arr.max() > 1:
                raise ValueError('PRODUCTION_PROJECTED_CONDITION_INVALID')
        report = {'parameters': params, 'hdrPath': str(hdr.resolve()), 'hdrSha256': expected_hash,
            'injectionSite': 'process_environment_map.hdr_dir', 'loaderHookEffective': True, 'device':execution_device,
            'fields': fields, 'hdrStatistics': stats, 'projectionMappingStatistics':mapping_stats[0], 'metadata': result['metadata']}
        calls.append(report); atomic(directory / 'condition.json', report)
        return result
    return hook, calls, arrays


def session(args, module, timeline, state_root, validate_output):
    from next.runtime.entry import _original_run_forward
    from experiments.controls import summarize_tensor
    import numpy as np
    prep = state_root.parent.parent
    plan = verify_joint(prep)
    if (args.seed, args.num_steps, args.guidance, args.height, args.width, args.num_video_frames, args.rotate_light) != (1000,15,0.,704,1280,1,False):
        raise ValueError('JOINT_FIXED_MODEL_CONFIGURATION')
    base = read(state_root / 'identities.json')['0']
    constructor, helper = module.DiffusionRendererPipeline, module.process_environment_map
    pipeline = None; active = {}; initialization_count = 0; total_forward = 0
    def retained(**kw):
        nonlocal pipeline, initialization_count
        if pipeline is None:
            with timeline.span('joint_initialization'):
                pipeline = constructor(**kw)
            initialization_count += 1
            original = pipeline.generate_video
            def generate(*a, **k):
                nonlocal total_forward
                if len(active['calls']) != 1: raise ValueError('CONDITION_HOOK_REQUIRED_BEFORE_FORWARD')
                records = {}
                for name in ('env_ldr','env_log','env_nrm'):
                    records[name], arr = summarize_tensor(k['data_batch'][name])
                    records[name]['finite']=True
                    if records[name]['shape'] != [1,3,1,704,1280] or arr.min() < -1.00001 or arr.max() > 1.00001:
                        raise ValueError('MODEL_CONDITION_SHAPE_RANGE')
                    if name != 'env_nrm' and not np.array_equal(arr, active['arrays'][name][None].transpose(0,4,1,2,3)*2-1):
                        raise ValueError('MODEL_CONDITION_HASH_MISMATCH')
                active['forward'] += 1; total_forward += 1
                atomic(active['directory']/'model-condition.json', records)
                module.torch.cuda.synchronize()
                with timeline.span('joint_forward', caseId=active['id'], ordinal=total_forward, modelObjectId=hex(id(pipeline))):
                    result = original(*a, **k); module.torch.cuda.synchronize(); return result
            pipeline.generate_video = generate
            timeline.emit('joint_pipeline_ready', initializationCount=initialization_count, modelObjectId=hex(id(pipeline)))
        return pipeline
    module.DiffusionRendererPipeline = retained
    try:
        for case in plan['cases']:
            directory = state_root.parent/'cases'/case['id']; directory.mkdir(parents=True, exist_ok=True)
            expected = {'0': {**base, 'jointPlanKey':identity(plan), 'case':case,
                'taskId':plan['taskId'], 'nonce':plan['nonce']}}
            if (directory/'identities.json').exists() and read(directory/'identities.json') != expected:
                raise ValueError('JOINT_RESUME_IDENTITY_MISMATCH')
            atomic(directory/'identities.json', expected)
            hdr = safe_file(prep,case['hdrFile']) if case.get('hdrFile') else Path(module.ENV_LIGHT_PATH_LIST[0]).resolve()
            module.process_environment_map, calls, arrays = strict_condition(helper,case['parameters'],hdr,case['hdrSha256'],directory,timeline)
            active.update(directory=directory,id=case['id'],calls=calls,arrays=arrays,forward=0)
            def validate(attempt):
                result = validate_output(attempt)
                # Before atomic complete: resumed entries also require durable proofs.
                condition = read(directory/'condition.json'); model = read(directory/'model-condition.json')
                if condition['hdrSha256'] != case['hdrSha256'] or condition['parameters'] != preprocessing_parameters(case['parameters']):
                    raise ValueError('JOINT_COMPLETION_CONDITION_MISMATCH')
                if any(model[k]['shape'] != [1,3,1,704,1280] for k in ('env_ldr','env_log','env_nrm')):
                    raise ValueError('JOINT_COMPLETION_MODEL_PROOF_MISSING')
                if calls and (len(calls)!=1 or active['forward']!=1):
                    raise ValueError('EXACT_ONE_CONDITION_AND_FORWARD_REQUIRED')
                result.update(conditionProofSha256=hashlib.sha256((directory/'condition.json').read_bytes()).hexdigest(),
                    modelProofSha256=hashlib.sha256((directory/'model-condition.json').read_bytes()).hexdigest())
                return result
            case_args = copy.deepcopy(args); case_args.envlight_ind = [0]
            _original_run_forward(case_args,module,timeline,directory,validate)
            timeline.emit('joint_case_complete',caseId=case['id'],newForward=active['forward'])
        timeline.emit('joint_complete',initializationCount=initialization_count,forwardCount=total_forward,
            inverseCount=0, modelObjectId=hex(id(pipeline)))
    finally:
        module.DiffusionRendererPipeline, module.process_environment_map = constructor, helper
        timeline.emit('joint_session_end',initializationCount=initialization_count,forwardCount=total_forward)
