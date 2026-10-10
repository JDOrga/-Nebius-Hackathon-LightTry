"""Bounded one-photo orchestration shared by the guarded worker and offline tests."""
import io
import contextlib
import os
from pathlib import Path
import sys

from .images import digest, MAX_BYTES
from .jobs import atomic, read
from .reuse import identity, key, complete, validate, copy_completed, safe_file
from .timing import Timeline


def validate_forward_result(root):
    from PIL import Image, ImageStat
    matches = [p for directory in root.glob('relit_frames_*') for p in directory.rglob('*.jpg')]
    if len(matches) != 1:
        raise ValueError('UNIQUE_FORWARD_FRAME_REQUIRED')
    path = safe_file(root, matches[0].relative_to(root).as_posix())
    payload = path.read_bytes()
    with Image.open(io.BytesIO(payload)) as image:
        image.load()
        if image.format != 'JPEG' or image.mode != 'RGB' or image.size != (1280, 704):
            raise ValueError('FORWARD_DECODE_MISMATCH')
        if max(ImageStat.Stat(image).stddev) < .5:
            raise ValueError('FORWARD_CONSTANT')
    return {'path': path.relative_to(root).as_posix(), 'sha256': digest(payload), 'bytes': len(payload)}


def measured_command(command, phase, run, state_root=None):
    argv = command[:2] + [str(Path(__file__).with_name('measured_entry.py')),
        '--phase', phase, '--timing', str(run / (phase + '-timing.jsonl'))]
    if state_root is not None:
        argv += ['--state-root', str(state_root)]
    return argv + command[3:]


@contextlib.contextmanager
def session_lock(run):
    path = run / '.batch.lock'
    if path.is_symlink() or run.is_symlink():
        raise ValueError('UNSAFE_BATCH_DIRECTORY')
    stream = path.open('a+b')
    try:
        stream.write(b'0'); stream.flush(); stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise ValueError('BATCH_ALREADY_RUNNING') from error
        yield
    finally:
        stream.close()


def execute(*args, **kwargs):
    run = args[2] if len(args) > 2 else kwargs['run']
    with session_lock(run):
        return _execute(*args, **kwargs)


def _execute(job, input_path, run, weights, patch, inverse_argv, forward_argv, launch,
            *, inverse_source=None, emit=lambda stage: None):
    """launch must be the existing deadline-bounded child runner; never cloud lifecycle.

    Call only after worker authorization/weights/source checks. Offline tests inject
    an explicitly labelled fake launch, not a selectable production mode.
    """
    value = identity(job, input_path.read_bytes(), weights, patch)
    requirement = job.get('requiredInverseReuse')
    if requirement is not None:
        if requirement.get('key') != key(value):
            raise ValueError('REQUIRED_INVERSE_KEY_MISMATCH')
        candidate = run / 'inverse' if (run / 'inverse/inverse-complete.json').exists() else inverse_source
        if candidate is None:
            raise ValueError('REQUIRED_INVERSE_REUSE_MISSING_NO_COLD_FALLBACK')
        if validate(candidate, value)['source'] != requirement.get('source'):
            raise ValueError('REQUIRED_INVERSE_SOURCE_MISMATCH')
    timer = Timeline(run / 'orchestration-timing.jsonl', 'orchestration')
    inverse = run / 'inverse'
    emit('inverse')
    with timer.span('inverse_ready'):
        if (inverse / 'inverse-complete.json').exists():
            provenance = validate(inverse, value)
            timer.emit('inverse_reused', source=provenance['source'])
        elif inverse_source is not None:
            provenance = copy_completed(inverse_source, inverse, value)
            timer.emit('inverse_reused', source=provenance['source'])
        else:
            if inverse.exists():
                raise ValueError('PARTIAL_INVERSE_REQUIRES_NEW_RUN_DIRECTORY')
            launch(measured_command(inverse_argv, 'inverse', run), run / 'inverse.log')
            provenance = complete(inverse, value, {'taskId': job['taskId'], 'nonce': job['nonce'],
                'inputEncodedSha256': job['input']['sha256'], 'inverseExitCode': 0,
                'weightVerification': job['runConfig']['weightVerification']})
    # The inverse child is confirmed exited before the forward process is created.
    presets = job.get('presets', [job['preset']])
    indices = [p['index'] for p in presets]
    if not indices or len(indices) > 3 or len(set(indices)) != len(indices) or any(i not in (0, 1, 2) for i in indices):
        raise ValueError('BOUNDED_UNIQUE_HDR_SELECTION_REQUIRED')
    states = run / 'presets'
    if states.is_symlink() or getattr(states, 'is_junction', lambda: False)():
        raise ValueError('UNSAFE_PRESET_DIRECTORY')
    states.mkdir(exist_ok=True)
    forward_model = [e for e in weights['files'] if not e['path'].startswith('Diffusion_Renderer_Inverse_Cosmos_7B/')]
    identities = {str(p['index']): {'inverseKey': key(value), 'inverseArtifacts': provenance['artifacts'],
        'request': {'taskId': job['taskId'], 'nonce': job['nonce'], 'inputId': job['input'].get('id'),
                    'inputSha256': job['input']['sha256'], 'originalSha256': job.get('original', {}).get('sha256')},
        'forwardModel': forward_model, 'patch': patch, 'config': job['runConfig'], 'hdr': p,
        'randomPolicy': 'reset-before-forward-generate-v1'} for p in presets}
    marker = states / 'identities.json'
    if marker.exists() and read(safe_file(states, 'identities.json')) != identities:
        raise ValueError('BATCH_RESUME_IDENTITY_MISMATCH')
    if not marker.exists():
        atomic(marker, identities)
    for index in indices:
        item = states / str(index)
        if item.is_symlink() or getattr(item, 'is_junction', lambda: False)():
            raise ValueError('UNSAFE_PRESET_DIRECTORY')
        item.mkdir(exist_ok=True)
        if not (item / 'state.json').exists():
            atomic(item / 'state.json', {'status': 'pending'})
    forward = forward_argv.copy()
    start, end = forward.index('--envlight_ind') + 1, forward.index('--use_custom_envmap=True')
    forward[start:end] = [str(i) for i in indices]
    emit('forward')
    with timer.span('forward_session'):
        launch(measured_command(forward, 'forward', run, states), run / ('forward-' + timer.process + '.log'))
    return provenance
