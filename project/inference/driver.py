"""Guarded transport orchestration. No VM start/restart or new credentials.

Invoked only by explicitly enabled task submission. The plain application never
calls this driver. Local bundle/extraction functions are independently testable.
"""
import argparse
import io
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tarfile
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'project'))
from inference.jobs import atomic, read
from inference.images import digest, MAX_BYTES

BUNDLE_FILES = ['scripts/run_experiment.py', 'scripts/weights.py', 'scripts/validate_outputs.py',
    'scripts/preflight.py', 'scripts/apply_hdr_patch.py', 'prototype/env_sampling.py',
    'patches/replace_hdr_sampling.patch', 'manifests/patch_manifest.json',
    'manifests/weights_manifest.json', 'manifests/upstream.json', 'third_party/Cosmos-LICENSE',
    'project/inference/worker.py', 'project/inference/weights_reuse.py']


def authorization(config_path):
    config = read(Path(config_path))
    if config.get('enabled') is not True or config.get('model_license_ack') is not True:
        raise ValueError('EXPLICIT_ENABLE_AND_MODEL_LICENSE_REQUIRED')
    run = Path(config['guard_run_directory']).resolve()
    if run.parent != ROOT / 'cloud-runs' or len(run.name) != 32 or any(c not in '0123456789abcdef' for c in run.name):
        raise ValueError('CURRENT_LOCAL_RUN_REQUIRED')
    if any((run / marker).exists() for marker in ('complete.json', 'cancel.json', 'supervision-stop.json')):
        raise ValueError('GUARDED_RUN_COMPLETED_OR_REVOKED')
    receipt, beat, timing, trust = (read(run / name) for name in
        ('launch.json', 'heartbeat.json', 'timing.json', 'host-trust.json'))
    sys.path.insert(0, str(ROOT / 'scripts'))
    from weights import parse_deadline
    now = time.time()
    if receipt.get('offline') or not receipt.get('single_run') or not receipt.get('approval_reference') or receipt.get('budget_usd_including_tax', 0) <= 0:
        raise ValueError('CURRENT_BUDGET_AUTHORIZATION_REQUIRED')
    deadline = min(parse_deadline(timing['work_deadline_utc']), parse_deadline(receipt['deadline_utc']))
    if now >= deadline or beat.get('offline') or beat.get('stopped_verified') or not beat.get('sleep_held') or not 0 <= now - parse_deadline(beat['utc']) <= 30:
        raise ValueError('LIVE_GUARD_AND_FIXED_DEADLINE_REQUIRED')
    if not trust.get('user_confirmed'):
        raise ValueError('CURRENT_HOST_APPROVAL_REQUIRED')
    # Existing transport revalidates live guard PID, API target, pin and deadline
    # before every operation. No credentials are read or copied by this code.
    return run, config, read(run / 'live-settings.json'), timing, deadline


def build_bundle(job, run, config=None):
    request = read(job / 'request.json')
    payload = (job / 'inputs/photo.png').read_bytes()
    if digest(payload) != request['input']['sha256']:
        raise ValueError('CURRENT_INPUT_HASH_MISMATCH')
    archive = run / 'inference-code.tar.gz'
    if archive.exists() or (run / 'bundle.json').exists():
        raise FileExistsError('ONE_TASK_PER_AUTHORIZED_RUN_PRESERVE_EXISTING_BUNDLE')
    entries = []
    references = {}
    mode = (config or {}).get('weights_mode', 'full')
    if mode != request['runConfig'].get('weightVerification', 'full'):
        raise ValueError('WEIGHT_POLICY_CHANGED_RESTART_LOCAL_SERVER')
    if mode == 'historical_metadata':
        from inference.weights_reuse import validate_reference
        paths = [Path(config[key]).resolve() for key in
                 ('historical_weights_manifest', 'historical_weights_receipt', 'historical_weights_reference')]
        validate_reference(ROOT / 'manifests/weights_manifest.json', *paths)
        references['weight-reference/manifest.json'] = paths[0].read_bytes()
        references['weight-reference/receipt.json'] = paths[1].read_bytes()
        ref = read(paths[2])
        # Keep hashes and historical identity; remove personal source paths.
        references['weight-reference/reference.json'] = json.dumps({key:ref[key] for key in
            ('weights_manifest_sha256','receipt_sha256','historical_run_id')}).encode()
    with archive.open('xb') as stream, tarfile.open(fileobj=stream, mode='w:gz') as tar:
        def add(name, data):
            info = tarfile.TarInfo(name); info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
            entries.append({'path': name, 'sha256': digest(data)})
        for rel in BUNDLE_FILES:
            path = ROOT / rel
            if path.is_symlink():
                raise ValueError('SYMLINK_FORBIDDEN')
            add(rel, path.read_bytes())
        # Only the prepared current photo crosses the transport, never the original name/path.
        minimal = dict(request)
        minimal['input'] = {k: v for k, v in request['input'].items() if k not in ('name', 'url', 'originalUrl')}
        add('request.json', json.dumps(minimal).encode())
        add('inputs/photo.png', payload)
        for name, data in references.items():
            add(name, data)
        info = tarfile.TarInfo('bundle_contents.json')
        data = json.dumps({'files': entries}).encode(); info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    atomic(run / 'bundle.json', {'archive': archive.name, 'archive_path': str(archive),
                               'sha256': digest(archive.read_bytes())})


def extract_result(archive, destination, *, require_gbuffers=False):
    # Never extract arbitrary paths or intermediate historical files. Fixed names only.
    expected = {'result.jpg', 'receipt.json', 'execution.json'}
    audit = {'configuration.json', 'weights_verification.json', 'inverse_acceptance.json',
             'preflight.json', 'inverse.log', 'forward.log', 'preflight.log'}
    with tarfile.open(archive, 'r:gz') as tar:
        files = {}
        total = 0
        for member in tar:
            name = member.name
            path = PurePosixPath(name)
            total += member.size
            if not member.isfile() or path.is_absolute() or '..' in path.parts or ':' in name or '\\' in name or total > 512 * 1024**2:
                raise ValueError('UNSAFE_RESULT_ARCHIVE')
            gbuffer = (path.parts[:2] == ('inverse', 'gbuffer_frames') and
                       name.endswith(tuple('.' + label + '.jpg' for label in
                                           ('basecolor', 'normal', 'depth', 'roughness', 'metallic'))))
            if name in expected or name in audit or gbuffer:
                if name in files or member.size > MAX_BYTES:
                    raise ValueError('INVALID_RESULT_MEMBER')
                files[name] = tar.extractfile(member).read()
        if not expected.issubset(files):
            raise ValueError('CURRENT_RESULT_FILES_MISSING')
        # Receipt is checked by TaskStore before publishing success; executor event last.
        for name in ('result.jpg', 'receipt.json'):
            target = destination / name
            if target.exists():
                if target.is_symlink() or target.read_bytes() != files[name]:
                    raise ValueError('EXISTING_CURRENT_RESULT_DIFFERS')
            else:
                with target.open('xb') as stream:
                    stream.write(files[name])
        evidence = destination / 'remote-evidence'
        for name, data in files.items():
            if name in expected:
                continue
            target = evidence.joinpath(*PurePosixPath(name).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                if target.is_symlink() or target.read_bytes() != data:
                    raise ValueError('EXISTING_CURRENT_EVIDENCE_DIFFERS')
            else:
                with target.open('xb') as stream:
                    stream.write(data)
        receipt = json.loads(files['receipt.json'])
        if require_gbuffers and 'gBuffers' not in receipt:
            raise ValueError('FIVE_CURRENT_GBUFFERS_REQUIRED')
        if 'gBuffers' in receipt:
            from PIL import Image, ImageStat
            channels = receipt['gBuffers']
            labels = ('basecolor', 'normal', 'depth', 'roughness', 'metallic')
            if len(channels) != 5 or {item['channel'] for item in channels} != set(labels):
                raise ValueError('FIVE_CURRENT_GBUFFERS_REQUIRED')
            for item in channels:
                data = files.get(item['relativePath'])
                if data is None or len(data) != item['size'] or digest(data) != item['sha256']:
                    raise ValueError('GBUFFER_TRANSFER_HASH_MISMATCH')
                with Image.open(io.BytesIO(data)) as img:
                    img.load()
                    if img.format != 'JPEG' or img.mode != 'RGB' or img.size != (1280, 704):
                        raise ValueError('GBUFFER_DECODE_OR_SIZE_MISMATCH')
                    if max(ImageStat.Stat(img).stddev) < 0.5 and item['channel'] not in ('roughness', 'metallic'):
                        raise ValueError('GBUFFER_EFFECTIVELY_CONSTANT')
        return json.loads(files['execution.json'])


def run_driver(job, config_path):
    request = read(job / 'request.json')
    event = {'taskId': request['taskId'], 'nonce': request['nonce'], 'status': 'queued', 'executionStopped': False}
    remote_may_be_running = False
    authorized_run = None
    local_deadline = time.time() + 1080
    def emit(status, stage=None, stopped=False):
        event.update(status=status, stage=stage, executionStopped=stopped, observedAt=time.time())
        atomic(job / 'execution.json', event)
    try:
        run, config, settings, timing, deadline = authorization(config_path)
        authorized_run = run
        local_deadline = min(deadline, local_deadline)
        build_bundle(job, run, config)
        transport = ROOT / 'cloud/Invoke-ScaleRemote.ps1'
        def call(operation, program=None, value=None, flag=None):
            authorization(config_path)  # no extension or automatic reauthorization
            remaining = local_deadline - time.time()
            if remaining <= 0:
                raise TimeoutError('FIXED_WORK_WINDOW_ENDED')
            argv = ['powershell.exe', '-NoProfile', '-File', str(transport), '-RunDirectory', str(run),
                    '-Operation', operation, '-Execute']
            if program:
                argv.extend(['-ContainerProgramPath', str(program)])
            if value is not None:
                path = job / (operation + '-request.json')
                atomic(path, value)
                argv.extend(['-RequestPath', str(path)])
            if flag:
                argv.append(flag)
            # Existing transport has private Job cleanup and bounded SSH/SCP.
            # Keep the outer call alive until its own cleanup completes (up to 120s).
            with (job / (operation + '-transport.log')).open('ab') as log:
                result = subprocess.run(argv, stdout=log, stderr=subprocess.STDOUT,
                                        stdin=subprocess.DEVNULL, shell=False, timeout=120)
            if result.returncode:
                raise RuntimeError('GUARDED_TRANSPORT_FAILED_' + operation)
            if program:
                return json.loads(read(run / (operation + '-result.json'))['output'])
        call('upload_directory')
        call('upload', flag='-UploadArchive')
        installed = call('install_bundle', ROOT / 'cloud/install_bundle.py',
            {'run_id': run.name, 'data_root': settings['container_data_dir'],
             'archive_sha256': read(run / 'bundle.json')['sha256']})
        prep = installed['preparation']
        q = {'prep': prep, 'deadline_utc': timing['work_deadline_utc'], 'repo': settings['container_repo'],
             'checkpoint_dir': settings['container_checkpoint_dir'], 'cuda_home': settings['cuda_home'],
             'model_license_ack': True}
        q['weights_mode'] = config.get('weights_mode', 'full')
        remote_may_be_running = True  # even an ambiguous launch response must block retries
        try:
            call('launch', ROOT / 'project/inference/remote_launch.py', q)
        except RuntimeError:
            # Query the current nonce; never send launch again after an ambiguous response.
            remote = call('inspect', ROOT / 'project/inference/remote_inspect.py', {'prep': prep})
            if (remote.get('taskId'), remote.get('nonce')) != (request['taskId'], request['nonce']):
                raise ValueError('AMBIGUOUS_LAUNCH_PROCESS_STATE_UNRESOLVED')
            atomic(job / 'launch-recovery.json', {'reason': 'launch response failed',
                'change': 'inspect same task without relaunch', 'observed': remote, 'utcEpoch': time.time()})
        while True:
            if time.time() >= local_deadline:
                raise TimeoutError('FIXED_WORK_WINDOW_ENDED')
            remote = call('inspect', ROOT / 'project/inference/remote_inspect.py', {'prep': prep})
            if remote.get('status') != 'queued' or 'taskId' in remote:
                if (remote.get('taskId'), remote.get('nonce')) != (request['taskId'], request['nonce']):
                    raise ValueError('REMOTE_EVENT_IDENTITY_MISMATCH')
                if remote.get('status') == 'failed':
                    remote_may_be_running = not remote.get('executionStopped', False)
                    raise RuntimeError('COSMOS_WORKER_FAILED')
                if remote.get('status') == 'succeeded':
                    remote_may_be_running = False
                    break
                if remote.get('status') == 'running':
                    emit('running', remote.get('stage'))
            time.sleep(min(4, max(0, local_deadline - time.time())))
        emit('running', 'transferring')
        for recovery_attempt in range(2):
            try:
                call('export_results', ROOT / 'cloud/export_results.py', {'root': prep + '/run', 'data_root': settings['container_data_dir']})
                call('download_results', flag='-DownloadResults')
                exported = extract_result(run / 'results.tar.gz', job, require_gbuffers=True)
                break
            except (KeyError, json.JSONDecodeError) as error:
                # A known local field/JSON problem after confirmed worker exit:
                # keep the same task active for one explicit operator repair.
                # Trust/transport failures and integrity errors are not caught.
                if recovery_attempt or local_deadline - time.time() < 180:
                    raise
                atomic(job / 'recovery-needed.json', {'reason': type(error).__name__ + ': ' + str(error),
                    'stage': 'transferring', 'modelExecutionStopped': True,
                    'nextAction': 'repair local fields then create retry-results.json with reason and change',
                    'deadlineEpoch': local_deadline, 'maxRetries': 1})
                retry_path = job / 'retry-results.json'
                while not retry_path.exists():
                    authorization(config_path)
                    if local_deadline - time.time() < 180:
                        raise TimeoutError('RECOVERY_WINDOW_INSUFFICIENT')
                    time.sleep(1)
                repair = read(retry_path)
                if not repair.get('reason') or not repair.get('change'):
                    raise ValueError('EXPLICIT_REPAIR_RECORD_REQUIRED')
                observed = call('inspect', ROOT / 'project/inference/remote_inspect.py', {'prep': prep})
                if (observed.get('taskId'), observed.get('nonce'), observed.get('status'), observed.get('executionStopped')) != (
                        request['taskId'], request['nonce'], 'succeeded', True):
                    raise ValueError('RESULT_RECOVERY_WORKER_STATE_UNRESOLVED')
                atomic(job / 'recovery-applied.json', dict(repair, observed=observed, utcEpoch=time.time()))
        if (job / 'recovery-applied.json').exists():
            atomic(job / 'recovery-result.json', {'status': 'transferred', 'utcEpoch': time.time(),
                'modelRelaunched': False, 'retryCount': 1})
        if (exported.get('taskId'), exported.get('nonce'), exported.get('status')) != (request['taskId'], request['nonce'], 'succeeded'):
            raise ValueError('EXPORTED_EVENT_IDENTITY_MISMATCH')
        emit('succeeded', 'validating', True)
    except BaseException as error:
        (job / 'driver-failure.txt').write_text(type(error).__name__ + ': ' + str(error), encoding='utf-8')
        emit('failed', event.get('stage'), not remote_may_be_running)
    finally:
        # Success waits only for local page acceptance; fixed independent guard
        # stays active. Unknown/unsafe errors still request protective shutdown.
        try:
            if authorized_run is not None:
                marker = 'inference-finished.json' if event['status'] == 'succeeded' else 'complete.json'
                atomic(authorized_run / marker, {'stop_required': event['status'] != 'succeeded',
                    'taskId': request['taskId'], 'reason': 'await local page acceptance' if
                    event['status'] == 'succeeded' else 'unsafe or unresolved execution failure'})
        except (KeyError, OSError, ValueError):
            pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--job', type=Path, required=True)
    parser.add_argument('--config', type=Path, required=True)
    args = parser.parse_args()
    run_driver(args.job.resolve(), args.config.resolve())
