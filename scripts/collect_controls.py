"""Strict local retrieval verification. Raw tensors/secrets are never extracted."""
import argparse
import json
from pathlib import Path, PurePosixPath
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'project'))
from inference.jobs import atomic, read
from inference.images import digest
from inference.batch import validate_forward_result
from experiments.controls import CASES, normalize
from experiments.worker import verify_packet


def collect(archive, destination, packet):
    plan = verify_packet(packet)
    cases = {c['id']: c for c in CASES}
    destination.mkdir(parents=True, exist_ok=False)
    total = 0; files = {}
    fixed = {'execution.json', 'configuration.json', 'weights_verification.json',
             'preflight.json', 'preflight.log', 'forward-timing.jsonl', 'presets/identities.json'}
    with tarfile.open(archive, 'r:gz') as tar:
        for member in tar:
            name = member.name; parts = PurePosixPath(name).parts
            total += member.size
            if (not member.isfile() or not parts or PurePosixPath(name).is_absolute() or
                    '..' in parts or ':' in name or '\\' in name or
                    member.size > 20*1024**2 or total > 128*1024**2 or name in files):
                raise ValueError('UNSAFE_EXPERIMENT_RESULT_ARCHIVE')
            permitted = name in fixed or (len(parts) == 1 and name.startswith(('forward-', 'preflight-')) and name.endswith('.log'))
            if len(parts) >= 3 and parts[0] == 'controls' and parts[1] in cases:
                permitted |= len(parts) == 3 and parts[2] in (
                    'condition.json', 'env_ldr.png', 'env_log.png', 'model-condition.json', 'identities.json')
                permitted |= len(parts) == 4 and parts[2] == '0' and parts[3] in ('complete.json', 'state.json')
                permitted |= (len(parts) >= 6 and parts[2] == '0' and len(parts[3]) == 32 and
                    all(c in '0123456789abcdef' for c in parts[3]) and parts[4] == 'relit_frames_0000' and name.endswith('.jpg'))
            if not permitted:
                raise ValueError('RESULT_MEMBER_NOT_ALLOWLISTED')
            files[name] = tar.extractfile(member).read()
    for name, data in files.items():
        target = destination.joinpath(*PurePosixPath(name).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            stream.write(data)
    event = read(destination / 'execution.json')
    if event['status'] != 'succeeded' or event.get('executionStopped') is not True:
        atomic(destination / 'retrieval.json', {'status': 'failure evidence retained', 'event': event,
            'archiveSha256': digest(archive.read_bytes()), 'files': len(files)})
        return {'status': 'failed', 'event': event}
    if read(destination / 'configuration.json')['experiment'] != plan:
        raise ValueError('RETURNED_CONFIGURATION_MISMATCH')
    base = read(destination / 'presets/identities.json')['0']
    if (base['input'] != plan['input'] or base['inverseArtifacts'] != plan['inverseArtifacts'] or
            base['inverseSource'] != plan['inverseSource'] or base['hdr'] != plan['hdr'] or
            base['config'] != plan['runConfig']):
        raise ValueError('RETURNED_INVERSE_AND_FORWARD_IDENTITY_MISMATCH')
    verified = {}
    for name, case in cases.items():
        directory = destination / 'controls' / name
        record = read(directory / '0/complete.json')
        identity = record['identity']
        if (identity.get('caseId') != name or identity.get('experiment') != normalize(case['offsetDeg'], case['strength']) or
                any(identity.get(k) != v for k, v in base.items()) or record.get('seed') != 1000 or
                record.get('randomPolicy') != 'reset-before-forward-generate-v1'):
            raise ValueError('CONTROL_CASE_IDENTITY_MISMATCH')
        attempt = record['attempt']
        if len(attempt) != 32 or any(c not in '0123456789abcdef' for c in attempt):
            raise ValueError('INVALID_RESULT_ATTEMPT')
        if validate_forward_result(directory / '0' / attempt) != record['result']:
            raise ValueError('CONTROL_OUTPUT_HASH_MISMATCH')
        if read(directory / 'condition.json')['parameters'] != identity['experiment']:
            raise ValueError('ACTUAL_HDR_PARAMETERS_MISMATCH')
        model = read(directory / 'model-condition.json')
        if any(model[k]['shape'] != [1, 3, 1, 704, 1280] for k in ('env_ldr', 'env_log', 'env_nrm')):
            raise ValueError('ACTUAL_MODEL_CONDITION_SHAPE_MISMATCH')
        verified[name] = record['result']
    records = [json.loads(line) for line in (destination / 'forward-timing.jsonl').read_text().splitlines()]
    completed = [r for r in records if r['event'] == 'experiment_complete']
    if len(completed) != 1 or completed[0]['initializationCount'] != 1:
        raise ValueError('SINGLE_PIPELINE_INITIALIZATION_NOT_OBSERVED')
    if len([r for r in records if r['event'] == 'random_state_reset']) != 6:
        raise ValueError('SIX_RANDOM_RESETS_NOT_OBSERVED')
    nrm = {read(destination / 'controls' / name / 'model-condition.json')['env_nrm']['sha256'] for name in cases}
    if len(nrm) != 1:
        raise ValueError('NORMAL_CONDITION_CHANGED')
    result = {'status': 'passed', 'archiveSha256': digest(archive.read_bytes()),
        'sixOutputFrames': verified, 'inverseExecutions': 0, 'forwardInitializations': 1,
        'actualHdrAndModelCondition': 'verified', 'humanVisualAcceptance': 'pending'}
    atomic(destination / 'retrieval.json', result)
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--archive', type=Path, nargs='+', required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--packet', type=Path, required=True)
    a = p.parse_args()
    archive = a.archive[0]
    if len(a.archive) > 1:
        archive = a.out.parent / (a.out.name + '-merged.tar.gz')
        names = set(); total = 0
        with archive.open('xb') as stream, tarfile.open(fileobj=stream, mode='w:gz') as merged:
            for chunk in a.archive:
                with tarfile.open(chunk, 'r:gz') as source:
                    for member in source:
                        total += member.size
                        name = member.name; path = PurePosixPath(name)
                        if (not member.isfile() or path.is_absolute() or '..' in path.parts or
                                ':' in name or '\\' in name or name in names or
                                member.size > 20*1024**2 or total > 128*1024**2):
                            raise ValueError('UNSAFE_RECOVERY_CHUNK')
                        names.add(name)
                        merged.addfile(member, source.extractfile(member))
    result = collect(archive, a.out, a.packet)
    result['remoteChunks'] = [{'path': str(p.resolve()), 'bytes': p.stat().st_size,
                              'sha256': digest(p.read_bytes())} for p in a.archive]
    if (a.out / 'retrieval.json').exists():
        atomic(a.out / 'retrieval.json', result)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
