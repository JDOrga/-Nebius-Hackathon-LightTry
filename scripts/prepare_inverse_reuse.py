"""Offline import of verified historical inverse evidence into a NEW registry.

No cloud calls. No edits to historical requests, receipts, manifests or outputs.
Requires the original locally retained code bundle to establish model/patch identity.
"""
import argparse
import json
from pathlib import Path
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'project'))
from inference.jobs import read, ID
from inference.images import digest
from inference.reuse import identity, key, artifacts, complete, copy_completed, validate, safe_file


def import_task(task_id, run_id):
    if not ID.fullmatch(task_id) or not ID.fullmatch(run_id):
        raise ValueError('FIXED_LOCAL_ID_REQUIRED')
    task = ROOT / 'project/.tasks' / task_id
    run = ROOT / 'cloud-runs' / run_id
    request = read(safe_file(task, 'request.json'))
    receipt = read(safe_file(task, 'receipt.json'))
    config = read(safe_file(task, 'remote-evidence/configuration.json'))
    sanitized = dict(request)
    sanitized['input'] = {k: v for k, v in request['input'].items() if k not in ('name', 'url', 'originalUrl')}
    if config['request'] != sanitized or receipt.get('processExitCodes') != [0, 0]:
        raise ValueError('HISTORICAL_COMPLETED_EXECUTION_REQUIRED')
    for field, expected in {'taskId': task_id, 'nonce': request['nonce'],
                           'inputSha256': request['input']['sha256'], 'runConfig': request['runConfig']}.items():
        if receipt.get(field) != expected:
            raise ValueError('HISTORICAL_SOURCE_MISMATCH')
    bundle = safe_file(run, 'inference-code.tar.gz')
    if digest(bundle.read_bytes()) != read(safe_file(run, 'bundle.json'))['sha256']:
        raise ValueError('HISTORICAL_BUNDLE_MISMATCH')
    with tarfile.open(bundle, 'r:gz') as archive:
        def member(name):
            entries = [m for m in archive.getmembers() if m.name == name]
            if len(entries) != 1 or not entries[0].isfile() or entries[0].size > 20 * 1024**2:
                raise ValueError('HISTORICAL_MEMBER_INVALID')
            return archive.extractfile(entries[0]).read()
        archived_request = json.loads(member('request.json'))
        if any(archived_request[k] != request[k] for k in ('taskId', 'nonce', 'runConfig', 'preset')):
            raise ValueError('HISTORICAL_BUNDLE_TASK_MISMATCH')
        weights = json.loads(member('manifests/weights_manifest.json'))
        patch = json.loads(member('manifests/patch_manifest.json'))
        payload = member('inputs/photo.png')
    if payload != safe_file(task, 'inputs/photo.png').read_bytes():
        raise ValueError('HISTORICAL_MODEL_INPUT_MISMATCH')
    # Only the known fixed old inverse flags can be assigned the v1 identity.
    argv = config['inverseArgv']
    from inference.worker import one_preset_commands
    command_args = argparse.Namespace(checkpoint_dir=Path(argv[argv.index('--checkpoint_dir') + 1]),
        input_dir=Path(argv[argv.index('--dataset_path') + 1]),
        run_dir=Path(argv[argv.index('--video_save_folder') + 1]).parent,
        height=704, width=1280, offload=False)
    expected_inverse, _ = one_preset_commands(command_args, request['preset']['index'])
    # Posix paths in a historical Linux argv must stay Posix on Windows.
    expected_inverse = [part.replace('\\', '/') for part in expected_inverse]
    expected_inverse[0] = argv[0]
    if argv != expected_inverse:
        raise ValueError('HISTORICAL_INVERSE_FLAGS_UNSUPPORTED')
    for option, expected in {'--seed': '1000', '--num_steps': '15', '--guidance': '0.0',
            '--height': '704', '--width': '1280', '--num_video_frames': '1',
            '--diffusion_transformer_dir': 'Diffusion_Renderer_Inverse_Cosmos_7B',
            '--group_mode': 'webdataset'}.items():
        if argv[argv.index(option) + 1] != expected:
            raise ValueError('HISTORICAL_INVERSE_CONFIG_UNSUPPORTED')
    evidence = task / 'remote-evidence/inverse'
    records = artifacts(evidence / 'gbuffer_frames')
    expected = {r['channel']: (r['sha256'], r['size'], r['relativePath']) for r in receipt['gBuffers']}
    if len(expected) != 5 or any(expected[r['channel']] !=
        (r['sha256'], r['bytes'], 'inverse/gbuffer_frames/' + r['path']) for r in records):
        raise ValueError('HISTORICAL_GBUFFER_RECEIPT_MISMATCH')
    value = identity(request, payload, weights, patch)
    target = ROOT / 'project/.inverse-cache' / key(value)
    target.parent.mkdir(exist_ok=True)
    if target.exists():
        return validate(target, value)
    target.mkdir()
    import shutil
    for record in records:
        destination = target / 'gbuffer_frames' / record['path']
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(safe_file(evidence / 'gbuffer_frames', record['path']), destination)
    return complete(target, value, {'taskId': task_id, 'nonce': request['nonce'], 'runId': run_id,
        'inverseExitCode': 0, 'historicalImport': True, 'receiptSha256': digest((task / 'receipt.json').read_bytes()),
        'bundleSha256': digest(bundle.read_bytes()), 'inputEncodedSha256': request['input']['sha256'],
        'weightVerification': request['runConfig']['weightVerification']})


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--task-id', required=True)
    parser.add_argument('--run-id', required=True)
    args = parser.parse_args()
    record = import_task(args.task_id, args.run_id)
    print(json.dumps({'key': record['key'], 'source': record['source'], 'artifactCount': len(record['artifacts']),
                      'validation': 'LOCAL HISTORICAL EVIDENCE ONLY; NO GPU RUN'}))
