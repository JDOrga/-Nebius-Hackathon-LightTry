"""Freeze a small, traceable LOCAL HDR experiment; no cloud calls or lifecycle.

Only existing prepared inputs and exact five-channel JPEGs cross the boundary.
The original photo, credentials, machine history and raw tensor arrays do not.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import shutil
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'project'))
from experiments.controls import VERSION, CASES
from experiments.worker import verify_packet
from inference.driver import BUNDLE_FILES
from inference.jobs import atomic, read, RUN_CONFIG
from inference.images import digest
from inference.reuse import artifacts
from inference.weights_reuse import validate_reference

EXTRA_CODE = ['project/experiments/__init__.py', 'project/experiments/controls.py',
    'project/experiments/measured_controls.py', 'project/experiments/worker.py']


def prepare(destination, sample_id, history, config):
    destination.mkdir(parents=True, exist_ok=False)
    packet = destination / 'packet'; packet.mkdir()
    integrity = read(history / 'local_integrity.json')
    ledger = {e['path'].replace('\\', '/'): e for e in integrity['files']}
    files, historical_files = [], []
    def add(source, name, *, historic=None):
        if source.is_symlink() or not source.is_file():
            raise ValueError('REGULAR_SOURCE_REQUIRED')
        data = source.read_bytes()
        if historic:
            record = ledger[historic]
            if digest(data) != record['sha256'] or len(data) != record['bytes']:
                raise ValueError('ORIGINAL_HISTORICAL_FILE_CHANGED')
            historical_files.append({'sourcePath': record['path'], 'packetPath': name})
        target = packet / name; target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            stream.write(data)
        files.append({'path': name, 'sha256': digest(data), 'bytes': len(data)})
    for rel in BUNDLE_FILES + EXTRA_CODE:
        add(ROOT / rel, rel)
    for rel, dest in [('configuration.json', 'configuration.json'),
                      ('prepared_inputs.json', 'prepared_inputs.json'),
                      ('run/status.json', 'status.json')]:
        add(history / rel, 'proof/' + dest, historic=rel)
    add(history / 'local_integrity.json', 'proof/local_integrity.json')
    add(history / 'execution_summary.json', 'proof/execution_summary.json')
    for path in sorted((history / 'run/inverse/gbuffer_frames' / sample_id).glob('*.jpg')):
        rel = path.relative_to(history).as_posix()
        add(path, 'inverse/gbuffer_frames/' + sample_id + '/' + path.name, historic=rel)
    selected = next(e for e in read(history / 'prepared_inputs.json')['images']
                    if Path(e['file']).stem == sample_id)
    add(history / 'inputs-srgb' / (sample_id + '.png'), 'inputs/photo.png')
    add(history / 'masks' / (sample_id + '_interior.png'), 'inputs/interior-mask.png')
    paths = [Path(config[k]) for k in ('historical_weights_manifest', 'historical_weights_receipt',
                                     'historical_weights_reference')]
    validate_reference(ROOT / 'manifests/weights_manifest.json', *paths)
    for p, name in zip(paths[:2], ('manifest.json', 'receipt.json')):
        add(p, 'weight-reference/' + name)
    reference = {k: read(paths[2])[k] for k in
                 ('weights_manifest_sha256', 'receipt_sha256', 'historical_run_id')}
    atomic(packet / 'weight-reference/reference.json', reference)
    files.append({'path': 'weight-reference/reference.json',
        'sha256': digest((packet / 'weight-reference/reference.json').read_bytes()),
        'bytes': (packet / 'weight-reference/reference.json').stat().st_size})
    catalog = read(ROOT / 'project/data/catalog.json')
    plan = {'version': VERSION, 'sampleId': sample_id, 'cases': list(CASES),
        'runConfig': {**RUN_CONFIG, 'weightVerification': 'historical_metadata'},
        'hdr': catalog['presets'][0], 'input': {'sha256': selected['derived_sha256'],
            'preprocessing': selected, 'note': 'exact prior prepared PNG; no new preprocessing'},
        'inverseSource': {'kind': 'historical-four-materials', 'runId': history.name,
            'inverseExitCode': 0, 'integrityLedgerSha256': digest((history / 'local_integrity.json').read_bytes()),
            'historicalCloudAcceptance': 'failed; local structure passed; quality mixed'},
        'inverseArtifacts': artifacts(packet / 'inverse/gbuffer_frames'),
        'files': files, 'historicalFiles': historical_files, 'productionCapability': False}
    atomic(packet / 'experiment.json', plan)
    verify_packet(packet)
    listing = files + [{'path': 'experiment.json', 'sha256': digest((packet / 'experiment.json').read_bytes()),
                         'bytes': (packet / 'experiment.json').stat().st_size}]
    archive = destination / 'inference-code.tar.gz'
    with archive.open('xb') as stream, tarfile.open(fileobj=stream, mode='w:gz') as tar:
        for record in listing:
            data = (packet / record['path']).read_bytes()
            info = tarfile.TarInfo(record['path']); info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        data = json.dumps({'files': listing}).encode()
        info = tarfile.TarInfo('bundle_contents.json'); info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    atomic(destination / 'bundle.json', {'archive': archive.name, 'archive_path': str(archive.resolve()),
        'sha256': digest(archive.read_bytes())})
    atomic(destination / 'preparation.json', {'state': 'LOCAL_PREPARED', 'files': listing,
        'sampleId': sample_id, 'archiveSha256': digest(archive.read_bytes()),
        'archiveBytes': archive.stat().st_size, 'inverseExecutions': 0,
        'forwardInitializations': 1, 'sourceRunId': history.name, 'cases': list(CASES),
        'sourceLedgerSha256': plan['inverseSource']['integrityLedgerSha256'],
        'sourceOfficialAndPatchChecks': 'required unchanged; no relaxing validator',
        'modelControl': 'NOT_YET_GPU_VERIFIED', 'cloudCalls': 0})
    return read(destination / 'preparation.json')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--sample', choices=('01_matte_terracotta', '03_glossy_metal_teapot'),
                   default='01_matte_terracotta')
    p.add_argument('--history', type=Path, required=True)
    p.add_argument('--config', type=Path, required=True)
    a = p.parse_args()
    result = prepare(a.out.resolve(), a.sample, a.history.resolve(), read(a.config))
    print(json.dumps({k: result[k] for k in ('state', 'sampleId', 'archiveBytes',
                                          'archiveSha256', 'cloudCalls')}))


if __name__ == '__main__':
    main()
