"""One image / one HDR, in the existing Linux environment. No installs or lifecycle."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

PREP = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PREP / 'scripts'))
from run_experiment import commands, run_bounded
from weights import parse_deadline, check_time, verify
from validate_outputs import validate_inverse, inspect


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest() if hasattr(hashlib, 'file_digest') else hash_stream(stream)


def hash_stream(stream):
    h = hashlib.sha256()
    for block in iter(lambda: stream.read(8 * 1024**2), b''):
        h.update(block)
    return h.hexdigest()


def atomic(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2), encoding='utf-8')
    os.replace(temporary, path)


def one_preset_commands(args, index):
    if index not in (0, 1, 2):
        raise ValueError('INVALID_HDR_INDEX')
    inverse, forward = commands(args)
    start = forward.index('--envlight_ind') + 1
    end = forward.index('--use_custom_envmap=True')
    forward[start:end] = [str(index)]
    # Fixed validated guidance; don't expose model flags to browser input.
    for command in (inverse, forward):
        command.extend(['--guidance', '0.0'])
    return inverse, forward


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    job = json.loads(args.request.read_text())
    runtime = json.loads(args.runtime.read_text())
    budget = json.loads(args.receipt.read_text())
    deadline = parse_deadline(runtime['deadline_utc'])
    if os.name != 'posix' or sys.version_info[:2] != (3, 10):
        raise ValueError('VERIFIED_LINUX_PYTHON310_REQUIRED')
    if budget.get('offline') or not budget.get('single_run') or not budget.get('approval_reference') or budget.get('budget_usd_including_tax', 0) <= 0:
        raise ValueError('CURRENT_GUARDED_BUDGET_REQUIRED')
    if deadline > parse_deadline(budget['deadline_utc']) or runtime.get('model_license_ack') is not True:
        raise ValueError('FIXED_DEADLINE_AND_LICENSE_REQUIRED')
    check_time(deadline)
    repo, checkpoints = Path(runtime['repo']), Path(runtime['checkpoint_dir'])
    for path in (PREP, repo, checkpoints, Path(runtime['cuda_home'])):
        if not path.resolve().is_relative_to('/home/jovyan'):
            raise ValueError('PERSISTENT_LOCAL_PATH_REQUIRED')
    run = PREP / 'run'
    run.mkdir()  # exclusive; never accept an old output directory
    event = {'taskId': job['taskId'], 'nonce': job['nonce'], 'status': 'running', 'executionStopped': False}
    def emit(stage, status='running', stopped=False):
        event.update(stage=stage, status=status, executionStopped=stopped, observedAt=time.time())
        atomic(run / 'execution.json', event)
    env = os.environ.copy()
    env.update(PYTHONPATH=str(repo), CUDA_HOME=runtime['cuda_home'], PYTHONUNBUFFERED='1',
               HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
    try:
        emit('preflight')
        head = subprocess.run(['git', '-C', str(repo), 'rev-parse', 'HEAD'], capture_output=True,
                              text=True, check=True, timeout=10).stdout.strip()
        if head != job['runConfig']['upstreamCommit']:
            raise ValueError('UPSTREAM_COMMIT_MISMATCH')
        patch = json.loads((PREP / 'manifests/patch_manifest.json').read_text())
        for entry in patch['files']:
            if sha(repo / entry['path']) != entry['after_sha256']:
                raise ValueError('EXISTING_HDR_PATCH_MISMATCH')
        # Fixed entry source is independently checked against the upstream Git blob.
        for name in ('inference_inverse_renderer.py', 'inference_forward_renderer.py'):
            rel = 'cosmos_predict1/diffusion/inference/' + name
            original = subprocess.run(['git', '-C', str(repo), 'show', head + ':' + rel],
                                      capture_output=True, check=True, timeout=10).stdout
            if sha(repo / rel) != hashlib.sha256(original).hexdigest():
                raise ValueError('MODEL_ENTRY_MODIFIED')
        hdr = repo / 'asset/examples/hdri_examples' / job['preset']['hdr']
        if hdr.parent.resolve() != (repo / 'asset/examples/hdri_examples').resolve() or sha(hdr) != job['preset']['sha256']:
            raise ValueError('HDR_IDENTITY_MISMATCH')
        input_image = PREP / 'inputs/photo.png'
        if sha(input_image) != job['input']['sha256']:
            raise ValueError('INPUT_IDENTITY_MISMATCH')
        run_bounded([sys.executable, '-B', str(PREP / 'scripts/preflight.py'), '--repo', str(repo),
            '--checkpoint-dir', str(checkpoints), '--cuda-home', runtime['cuda_home'],
            '--out', str(run / 'preflight.json')], repo, run / 'preflight.log', env, deadline)
        emit('weights')
        manifest = json.loads((PREP / 'manifests/weights_manifest.json').read_text())
        mode = runtime.get('weights_mode', 'full')
        if mode != job['runConfig']['weightVerification']:
            raise ValueError('WEIGHT_POLICY_MISMATCH')
        if mode == 'full':
            for entry in manifest['files']:
                if not verify(checkpoints / entry['path'], entry, deadline):
                    raise ValueError('CHECKPOINT_VERIFICATION_FAILED_NO_DOWNLOAD')
            weight_report = {'mode': 'full', 'content_verified_this_run': True, 'new_downloads': False}
        elif mode == 'historical_metadata':
            from weights_reuse import reuse_existing, validate_reference
            reference = PREP / 'weight-reference'
            validate_reference(PREP / 'manifests/weights_manifest.json', reference / 'manifest.json',
                               reference / 'receipt.json', reference / 'reference.json')
            weight_report = reuse_existing(checkpoints, reference / 'manifest.json', reference / 'receipt.json',
                                           reference / 'reference.json', deadline)
        else:
            raise ValueError('UNKNOWN_WEIGHT_POLICY')
        atomic(run / 'weights_verification.json', weight_report)
        command_args = argparse.Namespace(checkpoint_dir=checkpoints, input_dir=PREP / 'inputs',
            run_dir=run, height=704, width=1280, offload=False)
        inverse, forward = one_preset_commands(command_args, job['preset']['index'])
        atomic(run / 'configuration.json', {'request': job, 'runtime': runtime,
            'inverseArgv': inverse, 'forwardArgv': forward, 'weightContentHashesChecked': mode == 'full'})
        emit('inverse')
        run_bounded(inverse, repo, run / 'inverse.log', env, deadline)
        channels = validate_inverse(run / 'inverse', 704, 1280)
        atomic(run / 'inverse_acceptance.json', channels)
        emit('forward')  # inverse process has exited; both 7Bs never coexist
        run_bounded(forward, repo, run / 'forward.log', env, deadline)
        emit('validating')
        output_dir = run / 'forward' / f"relit_frames_{job['preset']['index']:04d}"
        paths = list(output_dir.rglob('*.jpg'))
        if len(paths) != 1 or paths[0].is_symlink() or not paths[0].resolve().is_relative_to(run):
            raise ValueError('UNIQUE_CURRENT_OUTPUT_REQUIRED')
        records, _ = inspect(paths, 704, 1280)
        check_time(deadline)
        shutil.copyfile(paths[0], run / 'result.jpg')
        receipt = {'taskId': job['taskId'], 'nonce': job['nonce'], 'inputId': job['input']['id'],
            'presetId': job['preset']['id'], 'inputSha256': job['input']['sha256'],
            'originalSha256': job['original']['sha256'], 'runConfig': job['runConfig'],
            'file': 'result.jpg', 'sha256': records[0]['sha256'], 'bytes': records[0]['size'],
            'processExitCodes': [0, 0], 'finishedAt': time.time(), 'outputValidation': records,
            'gBuffers': [dict(record, channel=label,
                relativePath=Path(record['path']).relative_to(run).as_posix())
                for label, record in zip(('basecolor', 'normal', 'depth', 'roughness', 'metallic'), channels)],
            'visualAcceptance': 'pending local human review'}
        atomic(run / 'receipt.json', receipt)
        emit('validating', 'succeeded', True)
    except BaseException as error:
        (run / 'failure.txt').write_text(type(error).__name__ + ': ' + str(error), encoding='utf-8')
        # run_bounded waits for/cleans only its own child group before raising.
        # A timeout kill fallback in the reused helper has no subsequent wait
        # proof. Preserve uncertainty until the guard/API confirms STOPPED.
        stopped = not isinstance(error, (subprocess.TimeoutExpired, OSError, KeyboardInterrupt))
        emit(event.get('stage', 'preflight'), 'failed', stopped)
        raise


if __name__ == '__main__':
    main()
