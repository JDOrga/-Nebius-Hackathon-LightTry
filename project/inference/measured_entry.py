"""Small in-process adapter around pinned upstream demos; never edits upstream.

Invoked by the guarded worker, with its existing bounded subprocess deadline.
Forward demo is called per preset but its pipeline constructor returns ONE object.
All completion markers are validated; a failed item leaves later items pending.
"""
import argparse
import importlib
from pathlib import Path
import sys
import uuid
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from inference.jobs import atomic, read
from inference.reuse import safe_file, key
from inference.images import digest
from inference.timing import Timeline


def checked_directory(path):
    if any(p.is_symlink() or getattr(p, 'is_junction', lambda: False)() for p in (path, *path.parents)):
        raise ValueError('UNSAFE_FORWARD_DIRECTORY')
    path.mkdir(parents=True, exist_ok=True)
    return path


def observe_generation(pipeline, module, args, phase, timeline):
    original = pipeline.generate_video
    count = 0
    def generate(self, *a, **kw):
        nonlocal count
        count += 1
        if phase == 'forward':
            # Upstream accepts seed but torch.randn uses global state.
            module.misc.set_random_seed(args.seed)
            timeline.emit('random_state_reset', seed=args.seed, policy='reset-before-forward-generate-v1', ordinal=count)
        with timeline.span('generation', ordinal=count, first=count == 1, seed=args.seed, modelObjectId=hex(id(self))):
            return original(self, *a, **kw)
    pipeline.generate_video = generate
    return original


def run_forward(args, module, timeline, state_root, validate_output):
    indices = list(args.envlight_ind)
    if not indices or len(indices) > 3 or len(set(indices)) != len(indices) or any(i not in (0, 1, 2) for i in indices):
        raise ValueError('BOUNDED_UNIQUE_HDR_SELECTION_REQUIRED')
    checked_directory(state_root)
    # This identity is supplied by the worker: inverse provenance + forward model/config/HDR.
    identities = read(safe_file(state_root, 'identities.json'))
    pending = []
    for index in indices:
        item = checked_directory(state_root / str(index))
        marker = item / 'complete.json'
        expected = identities[str(index)]
        if marker.exists():
            prior = read(safe_file(item, 'complete.json'))
            attempt_name = prior.get('attempt', '')
            if len(attempt_name) != 32 or any(c not in '0123456789abcdef' for c in attempt_name):
                raise ValueError('UNSAFE_FORWARD_ATTEMPT')
            attempt = item / attempt_name
            if attempt.is_symlink() or attempt.resolve().parent != item.resolve():
                raise ValueError('UNSAFE_FORWARD_ATTEMPT')
            if (prior['identity'] != expected or validate_output(attempt) != prior['result'] or
                    not prior['result']['path'].startswith(f'relit_frames_{index:04d}/')):
                raise ValueError('FORWARD_COMPLETION_MISMATCH')
            timeline.emit('preset_reused', presetIndex=index, source=prior['source'])
        else:
            pending.append(index)
    if not pending:
        return
    constructor = module.DiffusionRendererPipeline
    pipeline = None
    initialization_count = 0

    def shared_pipeline(**kwargs):
        nonlocal pipeline, initialization_count
        if pipeline is None:
            with timeline.span('pipeline_initialization'):
                pipeline = constructor(**kwargs)
            initialization_count += 1
            timeline.emit('pipeline_ready', initializationCount=initialization_count, modelObjectId=hex(id(pipeline)))
        else:
            timeline.emit('pipeline_reused', initializationCount=initialization_count, modelObjectId=hex(id(pipeline)))
        return pipeline

    module.DiffusionRendererPipeline = shared_pipeline
    try:
        for index in pending:
            item = checked_directory(state_root / str(index))
            attempt = item / uuid.uuid4().hex
            attempt.mkdir()
            args.envlight_ind = [index]
            args.video_save_folder = str(attempt)
            atomic(item / 'state.json', {'status': 'running', 'seed': args.seed,
                   'randomPolicy': 'reset-before-forward-generate-v1', 'attempt': attempt.name})
            try:
                with timeline.span('preset', presetIndex=index, seed=args.seed):
                    module.demo(args)
                    with timeline.span('preset_validation', presetIndex=index):
                        result = validate_output(attempt)
                    if not result['path'].startswith(f'relit_frames_{index:04d}/'):
                        raise ValueError('FORWARD_PRESET_OWNERSHIP_MISMATCH')
                atomic(item / 'complete.json', {'identity': identities[str(index)], 'result': result,
                       'attempt': attempt.name, 'source': {'process': timeline.process, 'presetIndex': index,
                           'modelObjectId': hex(id(pipeline))}, 'completedEpoch': time.time(),
                       'seed': args.seed, 'randomPolicy': 'reset-before-forward-generate-v1'})
                atomic(item / 'state.json', {'status': 'succeeded'})
                timeline.emit('preset_complete', presetIndex=index, modelObjectId=hex(id(pipeline)), seed=args.seed)
            except BaseException as error:
                atomic(item / 'state.json', {'status': 'failed', 'error': type(error).__name__, 'attempt': attempt.name})
                # CUDA failures can poison a context; do not claim remaining work succeeded.
                raise
    finally:
        module.DiffusionRendererPipeline = constructor
        timeline.emit('forward_session_end', initializationCount=initialization_count,
                      modelRetainedAfterExit=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--phase', choices=('inverse', 'forward'), required=True)
    parser.add_argument('--timing', type=Path, required=True)
    parser.add_argument('--state-root', type=Path)
    options, upstream_args = parser.parse_known_args()
    timeline = Timeline(options.timing, options.phase, process_entry=True)
    with timeline.span('imports'):
        module = importlib.import_module('cosmos_predict1.diffusion.inference.inference_' + options.phase + '_renderer')
    sys.argv = [sys.argv[0], *upstream_args]
    args = module.parse_arguments()
    pipeline = module.DiffusionRendererPipeline
    # Observe real callable boundaries. These nested spans MUST NOT be summed.
    restores = []
    def wrap(owner, name, event):
        original = getattr(owner, name)
        def measured(*a, **kw):
            with timeline.span(event):
                return original(*a, **kw)
        setattr(owner, name, measured)
        restores.append((owner, name, original))
    wrap(pipeline, '_load_model', 'model_construction')
    wrap(pipeline, '_load_network', 'network_load_including_assignment')
    wrap(pipeline, '_load_tokenizer', 'tokenizer_load_including_assignment')
    torch = module.torch
    wrap(torch, 'load', 'weight_deserialization')
    wrap(torch.jit, 'load', 'jit_weight_deserialization')
    wrap(torch.nn.Module, 'to', 'module_device_or_dtype_migration')
    wrap(torch.nn.Module, 'cuda', 'module_cuda_migration')
    original_generate = observe_generation(pipeline, module, args, options.phase, timeline)
    wrap(module, 'save_image_or_video', 'result_write')
    try:
        if options.phase == 'inverse':
            with timeline.span('inverse_demo'):
                module.demo(args)
        else:
            if options.state_root is None:
                raise ValueError('FORWARD_STATE_ROOT_REQUIRED')
            from inference.batch import validate_forward_result
            run_forward(args, module, timeline, options.state_root, validate_forward_result)
    finally:
        pipeline.generate_video = original_generate
        for owner, name, original in reversed(restores):
            setattr(owner, name, original)
        timeline.emit('process_end')


if __name__ == '__main__':
    main()
