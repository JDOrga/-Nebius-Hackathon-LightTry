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
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'project'))
from inference.jobs import atomic, read
from inference import driver as shared_driver
from inference.images import digest, MAX_BYTES

BUNDLE_FILES = ['scripts/run_experiment.py', 'scripts/weights.py', 'scripts/validate_outputs.py',
    'scripts/preflight.py', 'scripts/apply_hdr_patch.py', 'prototype/env_sampling.py',
    'patches/replace_hdr_sampling.patch', 'manifests/patch_manifest.json',
    'manifests/weights_manifest.json', 'manifests/upstream.json', 'third_party/Cosmos-LICENSE',
    'project/inference/worker.py', 'project/inference/weights_reuse.py',
    'project/inference/jobs.py', 'project/inference/images.py', 'project/inference/__init__.py',
    'project/inference/reuse.py', 'project/inference/batch.py','project/resident_ipc.py','project/model_readiness.py',
    'project/inference/timing.py', 'project/inference/measured_entry.py',
    'project/lighting.py','project/light_console.py','project/experiments/__init__.py','project/experiments/controls.py',
    'project/runtime/layout.py','project/runtime/__init__.py','project/runtime/worker.py','project/runtime/entry.py',
    'project/runtime/policy.json','project/runtime/environments.json','project/runtime/export_product_chunks.py']

def retryable_archive_failure(operation,summary):
    # Only immutable export/SCP of an already completed result. Never retry
    # ambiguous model launch, authentication, pin/permission or integrity errors.
    return (operation in ('export_control_chunk','download_control_chunk') and
        summary.get('exit_code')==255 and summary.get('stderr_categories') in (['CONNECTION_CLOSED'],['CONNECTION_RESET']) and
        summary.get('cleanup_incomplete') is False and summary.get('remaining_owned_processes')==0 and
        summary.get('process_exited') is True and summary.get('output_complete') is True)


authorization = shared_driver.authorization


def build_bundle(job, run, config=None):
    return shared_driver.build_bundle(job, run, config, root=ROOT, bundle_files=BUNDLE_FILES, include_derived_hdr=True)


def bind_prepared_bundle(job, run, config):
    return shared_driver.bind_prepared_bundle(job, run, config, root=ROOT, bundle_files=BUNDLE_FILES)


def extract_result(archive, destination, *, require_gbuffers=False):
    return shared_driver.extract_result(archive, destination, require_gbuffers=require_gbuffers, extra_audit=('parameter-proof.json',))


def extract_stage_evidence(archive, destination, request):
    return shared_driver.extract_stage_evidence(archive, destination, request, root=ROOT)


def run_driver(job, config_path):
    from inference.timing import Timeline
    timeline = Timeline(job / 'local-timing.jsonl', 'driver')
    timeline.emit('submission_entry')
    ready_presets = set()
    def observe_presets(remote):
        for index, item in remote.get('presets', {}).items():
            if item.get('status') == 'succeeded' and index not in ready_presets:
                ready_presets.add(index)
                timeline.emit('preset_available_observed', presetIndex=int(index), remoteCompletedEpoch=item.get('completedEpoch'))
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
        for name,expected in config.get('code_hashes',{}).items():
            if name not in BUNDLE_FILES+[str(Path(__file__).relative_to(ROOT).as_posix())]:raise ValueError('UNKNOWN_FROZEN_CODE_PATH')
            if digest((ROOT/name).read_bytes())!=expected:raise ValueError('FROZEN_CODE_CHANGED_BEFORE_DISPATCH')
        authorized_run = run
        local_deadline = min(deadline, local_deadline)
        if config.get('prepared_bundle_directory'):
            bind_prepared_bundle(job, run, config)
        else:
            build_bundle(job, run, config)
        transport = ROOT / 'cloud/Invoke-ScaleRemote.ps1'
        def call(operation, program=None, value=None, flag=None, chunk=None):
            authorization(config_path)  # no extension or automatic reauthorization
            remaining = local_deadline - time.time()
            if remaining <= 0:
                raise TimeoutError('FIXED_WORK_WINDOW_ENDED')
            argv = ['powershell.exe', '-NoProfile', '-File', str(ROOT/'cloud/ControlChunkTransport.ps1' if chunk else transport), '-RunDirectory', str(run),
                    '-Operation', operation, '-Execute']
            if chunk:argv.extend(['-SourceRunId',run.name,'-ControlPart',chunk])
            if program:
                argv.extend(['-ContainerProgramPath', str(program)])
            if value is not None:
                path = job / (operation + ('-'+chunk if chunk else '') + '-request.json')
                atomic(path, value)
                argv.extend(['-RequestPath', str(path)])
            if flag:
                argv.append(flag)
            # Existing transport has private Job cleanup and bounded SSH/SCP.
            # Keep the outer call alive until its own cleanup completes (up to 120s).
            timeline.emit('transport_start', operation=operation)
            with (job / (operation + '-transport.log')).open('ab') as log:
                result = subprocess.run(argv, stdout=log, stderr=subprocess.STDOUT,
                                        stdin=subprocess.DEVNULL, shell=False, timeout=120)
            timeline.emit('transport_end', operation=operation, exitCode=result.returncode)
            if result.returncode and (run/(operation+'-native.json')).exists() and retryable_archive_failure(operation,read(run/(operation+'-native.json'))):
                authorization(config_path)
                if local_deadline-time.time()>120:
                    timeline.emit('classified_immutable_transfer_retry',operation=operation,maxRetries=1)
                    time.sleep(2)
                    if flag and chunk:
                        partial=run/('control-canonical-'+run.name+'-'+chunk+'.tar.gz')
                        if partial.exists():
                            preserved=partial.with_name(partial.name+'.partial-'+uuid.uuid4().hex)
                            if partial.resolve().parent!=run.resolve() or preserved.resolve().parent!=run.resolve():raise ValueError('PARTIAL_OUTSIDE_RUN')
                            partial.rename(preserved)
                    with (job/(operation+'-transport.log')).open('ab') as log:
                        result=subprocess.run(argv,stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,shell=False,timeout=120)
                    timeline.emit('immutable_transfer_retry_end',operation=operation,exitCode=result.returncode)
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
            call('launch', ROOT / 'project/runtime/remote_launch.py', q)
        except RuntimeError:
            # Query the current nonce; never send launch again after an ambiguous response.
            remote = call('inspect', ROOT / 'project/inference/remote_inspect.py', {'prep': prep})
            if (remote.get('taskId'), remote.get('nonce')) != (request['taskId'], request['nonce']):
                raise ValueError('AMBIGUOUS_LAUNCH_PROCESS_STATE_UNRESOLVED')
            observe_presets(remote)
            atomic(job / 'launch-recovery.json', {'reason': 'launch response failed',
                'change': 'inspect same task without relaunch', 'observed': remote, 'utcEpoch': time.time()})
        while True:
            if time.time() >= local_deadline:
                raise TimeoutError('FIXED_WORK_WINDOW_ENDED')
            remote = call('inspect', ROOT / 'project/inference/remote_inspect.py', {'prep': prep})
            if remote.get('status') != 'queued' or 'taskId' in remote:
                if (remote.get('taskId'), remote.get('nonce')) != (request['taskId'], request['nonce']):
                    raise ValueError('REMOTE_EVENT_IDENTITY_MISMATCH')
                observe_presets(remote)
                if remote.get('status') == 'failed':
                    remote_may_be_running = not remote.get('executionStopped', False)
                    if not remote_may_be_running:
                        # Preserve stage evidence under the SAME deadline; no model relaunch.
                        call('export_results', ROOT / 'cloud/export_results.py', {'root': prep + '/run', 'data_root': settings['container_data_dir']})
                        call('download_results', flag='-DownloadResults')
                        extract_stage_evidence(run / 'results.tar.gz', job, request)
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
                from runtime.export_product_chunks import PARTS,combine
                paths=[]
                for part in PARTS:
                    metadata=call('export_control_chunk',ROOT/'project/runtime/export_product_chunks.py',
                        {'root':prep+'/run','data_root':settings['container_data_dir'],'part':part},chunk=part)
                    atomic(job/('export-'+part+'-receipt.json'),metadata)
                    destination=run/('control-canonical-'+run.name+'-'+part+'.tar.gz')
                    if destination.exists():
                        if digest(destination.read_bytes())!=metadata['sha256'] or destination.stat().st_size!=metadata['bytes']:raise ValueError('EXISTING_PRODUCT_CHUNK_MISMATCH')
                    else:call('download_control_chunk',flag='-DownloadResults',chunk=part)
                    if digest(destination.read_bytes())!=metadata['sha256'] or destination.stat().st_size!=metadata['bytes']:raise ValueError('PRODUCT_CHUNK_HASH_MISMATCH')
                    paths.append(destination)
                merged=run/'results.tar.gz'
                atomic(job/'product-chunk-assembly.json',combine(paths,merged))
                exported = extract_result(merged, job, require_gbuffers=True)
                extract_stage_evidence(run / 'results.tar.gz', job, request)
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
        timeline.emit('results_local_validated', productBatchRegistration=False)
    except BaseException as error:
        (job / 'driver-failure.txt').write_text(type(error).__name__ + ': ' + str(error), encoding='utf-8')
        emit('failed', event.get('stage'), not remote_may_be_running)
    finally:
        # Success waits only for local page acceptance; fixed independent guard
        # stays active. Unknown/unsafe errors still request protective shutdown.
        try:
            if authorized_run is not None:
                # Results are already local. Never retain a billed GPU to wait
                # for browser/manual acceptance or front-end development.
                marker = 'complete.json'
                atomic(authorized_run / marker, {'stop_required': True,
                    'taskId': request['taskId'], 'reason': 'verified results acquired; browser acceptance is local after stop' if
                    event['status'] == 'succeeded' else 'unsafe or unresolved execution failure'})
        except (KeyError, OSError, ValueError):
            pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--job', type=Path, required=True)
    parser.add_argument('--config', type=Path, required=True)
    args = parser.parse_args()
    run_driver(args.job.resolve(), args.config.resolve())
