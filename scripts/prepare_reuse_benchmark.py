"""Prepare a frozen LOCAL package for the two-HDR benchmark. No execution/API."""
import copy
import json
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'project'))
from inference.jobs import read, atomic, RUN_CONFIG
from inference.driver import build_bundle, bind_prepared_bundle, BUNDLE_FILES
from inference.reuse import identity, key, validate, safe_file
from inference.images import digest
from prepare_inverse_reuse import import_task


def main():
    source_id = '6d541112fa164c099d9fc06c560b464d'
    history = ROOT / 'project/.tasks' / source_id
    base = ROOT / '.local/reuse-benchmark-20261010'
    base.mkdir(exist_ok=True)
    plan = read(ROOT / '.local/reuse-preparation-20261009/reuse-plan.json')
    source = import_task(source_id, 'dc011af5186c492d8ffd2f6342e5c07f')
    if plan['reuseSource'] != source['source'] or plan['inverseKey'] != source['key']:
        raise ValueError('APPROVED_REUSE_PLAN_SOURCE_MISMATCH')
    config = read(ROOT / 'project/inference.local.json')
    if config['weights_mode'] != 'historical_metadata':
        raise ValueError('HISTORICAL_METADATA_REQUIRED')
    private = base / 'private-job'
    package = base / 'package'
    if private.exists() or package.exists():
        raise FileExistsError('PRESERVE_EXISTING_PREPARATION')
    private.mkdir(); (private / 'inputs').mkdir(); package.mkdir()
    request = copy.deepcopy(read(history / 'request.json'))
    request.update(taskId=uuid.uuid4().hex, nonce=uuid.uuid4().hex,
        presets=plan['selectedPresets'], preset=plan['selectedPresets'][0],
        requiredInverseReuse={'key': source['key'], 'source': source['source']})
    request['input']['id'] = uuid.uuid4().hex
    for name in ('url', 'originalUrl'):
        request['input'].pop(name, None)
    request['runConfig'] = {**RUN_CONFIG, 'weightVerification':'historical_metadata', 'weightContentHashesChecked':False}
    payload = safe_file(history, 'inputs/photo.png').read_bytes()
    (private / 'inputs/photo.png').write_bytes(payload)
    atomic(private / 'request.json', request)
    config.update(enabled=False, guard_run_directory=None, reuse_inverse=True)
    config['prepared_bundle_directory'] = str(package)
    atomic(base / 'inference-disabled.json', config)
    build_bundle(private, package, config)
    # Exercise the REAL frozen-package binding locally; no guard/API/inference.
    review = base / 'package-binding-check'; review.mkdir()
    bind_prepared_bundle(private, review, config)
    atomic(base / 'preparation.json', {'mode':'LOCAL_PREPARED_NOT_AUTHORIZED',
        'taskId':request['taskId'], 'nonce':request['nonce'], 'sourceTaskId':source_id,
        'source':source['source'], 'inverseKey':source['key'],
        'requiredInverseReuse':True, 'expectedInverseExecutions':0, 'expectedForwardInitializations':1,
        'presets':[p['id'] for p in request['presets']], 'content_verified':False,
        'packageSha256':read(package / 'bundle.json')['sha256'],
        'packageBytes':(package / 'inference-code.tar.gz').stat().st_size,
        'requestSha256':digest((private / 'request.json').read_bytes()),
        'historicalFileHashes':{str(p.relative_to(ROOT)):digest(p.read_bytes()) for p in
            [history/'request.json', history/'receipt.json', history/'task.json', history/'result.jpg',
             ROOT/'manifests/weights_manifest.json', ROOT/'manifests/patch_manifest.json']},
        'codeHashes':{p:digest((ROOT/p).read_bytes()) for p in BUNDLE_FILES},
        'otherReviewedPrograms':{p:digest((ROOT/p).read_bytes()) for p in
            ['project/inference/remote_launch.py','project/inference/remote_inspect.py',
             'cloud/install_bundle.py','cloud/export_results.py']},
        'productRegistration':'NONE; private execution benchmark only', 'cloudMutations':0,
        'budgetAuthorization':'PENDING; old budget/start not inherited'})
    print(json.dumps({'mode':'LOCAL_PREPARED_NOT_AUTHORIZED','taskId':request['taskId'],
                      'packageBytes':(package/'inference-code.tar.gz').stat().st_size,
                      'requiredInverseReuse':True,'cloud_calls':0}))


if __name__ == '__main__': main()
