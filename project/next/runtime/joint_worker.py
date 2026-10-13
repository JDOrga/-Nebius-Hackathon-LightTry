"""Guarded experimental worker. Existing sources/patches/weights are NOT modified.

Historical experiment inverse reuse is isolated from the production cache. Its
source run, successful inverse exit, exact input and all five channel hashes are
verified against the historical integrity ledger. No invented product task ID.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / 'scripts'))
from inference.jobs import atomic, read
from inference.reuse import artifacts, safe_file
from experiments.controls import VERSION, CASES
from weights import parse_deadline, check_time
from inference.weights_reuse import validate_reference, reuse_existing


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_packet(prep):
    plan = read(safe_file(prep, 'experiment.json'))
    if plan['version'] != VERSION or plan['cases'] != list(CASES):
        raise ValueError('FROZEN_MATRIX_MISMATCH')
    for item in plan['files']:
        if sha(safe_file(prep, item['path'])) != item['sha256']:
            raise ValueError('EXPERIMENT_PACKET_HASH_MISMATCH')
    config = read(prep / 'proof/configuration.json')
    expected = {'official_commit': '0f3e2dc435032ecbad654c2fc2153df85384b138',
        'seed': 1000, 'steps': 15, 'frames': 1, 'resolution_hw': [704, 1280],
        'guidance': 0.0, 'normal_unit_normalization': False, 'network_offload': False,
        'tokenizer_offload': False}
    if any(config.get(k) != v for k, v in expected.items()):
        raise ValueError('HISTORICAL_SAMPLING_CONFIGURATION_MISMATCH')
    status = read(prep / 'proof/status.json')
    if [s['exit'] for s in status['process_stages'] if s['stage'] == 'inverse'] != [0]:
        raise ValueError('HISTORICAL_INVERSE_NOT_COMPLETED')
    integrity = {e['path']: e for e in read(prep / 'proof/local_integrity.json')['files']}
    for item in plan['historicalFiles']:
        expected = integrity[item['sourcePath']]
        current = safe_file(prep, item['packetPath'])
        if sha(current) != expected['sha256'] or current.stat().st_size != expected['bytes']:
            raise ValueError('HISTORICAL_SOURCE_HASH_MISMATCH')
    if artifacts(prep / 'inverse/gbuffer_frames') != plan['inverseArtifacts']:
        raise ValueError('HISTORICAL_FIVE_CHANNELS_MISMATCH')
    selected = next(e for e in read(prep / 'proof/prepared_inputs.json')['images']
                    if Path(e['file']).stem == plan['sampleId'])
    if sha(prep / 'inputs/photo.png') != selected['derived_sha256']:
        raise ValueError('EXACT_HISTORICAL_INPUT_REQUIRED')
    return plan


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--prep', type=Path, required=True)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--joint', action='store_true', required=True, help='Verified joint or five-case calibration session; no inverse fallback')
    options = parser.parse_args()
    prep = options.prep.resolve()
    if os.name != 'posix' or sys.version_info[:2] != (3, 10) or not prep.is_relative_to('/home/jovyan'):
        raise ValueError('VERIFIED_CLOUD_RUNTIME_REQUIRED')
    runtime, receipt = read(options.runtime), read(options.receipt)
    deadline = parse_deadline(runtime['deadline_utc'])
    if (receipt.get('offline') or not receipt.get('single_run') or
            receipt.get('budget_usd_including_tax', 0) <= 0 or not receipt.get('approval_reference') or
            deadline > parse_deadline(receipt['deadline_utc']) or runtime.get('model_license_ack') is not True):
        raise ValueError('CURRENT_FIXED_GUARDED_BUDGET_REQUIRED')
    check_time(deadline)
    run = prep / 'run'
    if options.resume:
        previous = read(run / 'execution.json')
        if previous.get('status') != 'failed' or previous.get('executionStopped') is not True:
            raise ValueError('CONFIRMED_STOPPED_EXPERIMENT_RESUME_REQUIRED')
    else:
        run.mkdir()
    event = {'status': 'running', 'executionStopped': False, 'stage': 'preflight'}
    atomic(run / 'execution.json', event)
    process = None
    try:
        plan = verify_packet(prep)
        from next.runtime.joint import verify_joint
        joint = verify_joint(prep)
        event.update(taskId=joint['taskId'], nonce=joint['nonce'])
        atomic(run / 'execution.json', event)
        repo = Path(runtime['repo']).resolve()
        if not repo.is_relative_to('/home/jovyan'):
            raise ValueError('PERSISTENT_SOURCE_REQUIRED')
        head = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], timeout=10).decode().strip()
        if head != plan['runConfig']['upstreamCommit']:
            raise ValueError('UPSTREAM_COMMIT_MISMATCH')
        historical = read(prep / 'proof/configuration.json')
        for rel, digest in historical['official_code_hashes'].items():
            if sha(repo / rel) != digest:
                raise ValueError('OFFICIAL_CODE_CHANGED')
        for entry in read(prep / 'manifests/patch_manifest.json')['files']:
            if sha(repo / entry['path']) != entry['after_sha256']:
                raise ValueError('EXISTING_PATCH_MISMATCH')
        if sha(repo / 'asset/examples/hdri_examples' / plan['hdr']['hdr']) != plan['hdr']['sha256']:
            raise ValueError('HDR_CONTENT_MISMATCH')
        check_time(deadline)
        env = os.environ.copy()
        env.update(PYTHONPATH=str(repo), CUDA_HOME=runtime['cuda_home'], PYTHONUNBUFFERED='1',
                   HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
        def bounded(argv, logfile):
            nonlocal process
            check_time(deadline)
            with logfile.open('x') as log:
                process = subprocess.Popen(argv, cwd=repo, env=env, stdout=log,
                    stderr=subprocess.STDOUT, start_new_session=True)
                try:
                    process.wait(timeout=max(0.1, deadline - time.time()))
                except BaseException:
                    import signal
                    if process.poll() is None:
                        try: os.killpg(process.pid, signal.SIGTERM)
                        except ProcessLookupError: pass
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        try: os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError: pass
                        process.wait(timeout=5)  # do not claim stopped without wait proof
                    raise
            if process.returncode:
                raise ValueError('EXPERIMENT_CHILD_NONZERO_' + str(process.returncode))
        bounded([sys.executable, '-B', str(prep / 'scripts/preflight.py'), '--repo', str(repo),
            '--checkpoint-dir', runtime['checkpoint_dir'], '--cuda-home', runtime['cuda_home'],
            '--out', str(run / 'preflight.json')], run / ('preflight-' + str(time.time_ns()) + '.log'))
        reference = prep / 'weight-reference'
        validate_reference(prep / 'manifests/weights_manifest.json', reference / 'manifest.json',
                           reference / 'receipt.json', reference / 'reference.json')
        report = reuse_existing(Path(runtime['checkpoint_dir']), reference / 'manifest.json',
                               reference / 'receipt.json', reference / 'reference.json', deadline)
        atomic(run / 'weights_verification.json', report)
        states = run / 'presets'; states.mkdir(exist_ok=True)
        identities = {'0': {'input': plan['input'], 'inverseSource': plan['inverseSource'],
            'inverseArtifacts': plan['inverseArtifacts'], 'config': plan['runConfig'],
            'hdr': plan['hdr'], 'patch': read(prep / 'manifests/patch_manifest.json'), 'joint': joint}}
        if (states / 'identities.json').exists() and read(states / 'identities.json') != identities:
            raise ValueError('RESUME_SOURCE_IDENTITY_MISMATCH')
        atomic(states / 'identities.json', identities)
        argv = [sys.executable, '-u', '-B', str(prep / 'project/next/runtime/joint_entry.py'),
            '--phase', 'forward', '--timing', str(run / 'forward-timing.jsonl'),
            '--state-root', str(states), '--checkpoint_dir', runtime['checkpoint_dir'],
            '--diffusion_transformer_dir', 'Diffusion_Renderer_Forward_Cosmos_7B',
            '--dataset_path', str(prep / 'inverse/gbuffer_frames'), '--num_video_frames', '1',
            '--height', '704', '--width', '1280', '--num_steps', '15', '--seed', '1000',
            '--guidance', '0.0', '--envlight_ind', '0', '--use_custom_envmap=True',
            '--rotate_light=False', '--save_image=True', '--video_save_folder', str(run / 'forward')]
        atomic(run / 'configuration.json', {'experiment': plan, 'argv': argv,
            'weightVerification': report['mode'], 'contentVerifiedThisRun': False})
        event['stage'] = 'forward'; atomic(run / 'execution.json', event)
        bounded(argv, run / ('forward-' + str(time.time_ns()) + '.log'))
        event.update(status='succeeded', stage='complete', executionStopped=True, exitCode=0)
    except BaseException as error:
        event.update(status='failed', error=type(error).__name__ + ':' + str(error),
                     executionStopped=(process is None or process.poll() is not None) and
                     not isinstance(error, (OSError, KeyboardInterrupt)))
        raise
    finally:
        event['epoch'] = time.time(); atomic(run / 'execution.json', event)


if __name__ == '__main__':
    main()
