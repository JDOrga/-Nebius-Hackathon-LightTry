"""Terminal-only snapshot: validate once remotely, send one bounded archive."""
import base64
import gzip
import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile
import time

if '__file__' in globals():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
else:
    q = json.loads(base64.b64decode(sys.argv[1]))
    prep = Path(q['root']).resolve().parent
    if not prep.is_relative_to('/home/jovyan'):
        raise ValueError('PERSISTENT_EXPORT_SOURCE_REQUIRED')
    sys.path.insert(0, str(prep / 'project'))
from inference.jobs import read
from inference.reuse import safe_file
from runtime.joint_results import validate_case

MAX_ARCHIVE = 700 * 1024  # base64 plus framing stays below existing 1 MiB capture


def build(root, packet, task_id, nonce):
    started = time.perf_counter()
    plan = read(safe_file(packet, 'joint.json'))
    event = read(safe_file(root, 'execution.json'))
    if (plan['taskId'], plan['nonce']) != (task_id, nonce):
        raise ValueError('BUNDLE_TASK_IDENTITY_MISMATCH')
    if (event.get('taskId'), event.get('nonce')) != (task_id, nonce):
        raise ValueError('BUNDLE_EXECUTION_IDENTITY_MISMATCH')
    if event['status'] not in ('succeeded', 'failed') or event.get('executionStopped') is not True:
        raise ValueError('TERMINAL_STOPPED_WORKER_REQUIRED')
    files, completed = {}, []
    for case in plan['cases']:
        directory = root / 'cases' / case['id']
        if not (directory / '0/complete.json').exists():
            continue  # retain earlier completed results on terminal failure
        record = validate_case(packet, root, case)
        marker = read(safe_file(directory, '0/complete.json'))
        paths = [safe_file(directory, '0/complete.json'),
                 safe_file(directory, 'condition.json'),
                 safe_file(directory, 'model-condition.json'), Path(record['path'])]
        for path in paths:
            files[path.relative_to(root).as_posix()] = path.read_bytes()
        completed.append(case['id'])
    if event['status'] == 'succeeded' and len(completed) != len(plan['cases']):
        raise ValueError('SUCCEEDED_BUNDLE_INCOMPLETE')
    for name in ('execution.json', 'configuration.json', 'preflight.json',
                 'weights_verification.json', 'forward-timing.jsonl', 'export-timing.jsonl'):
        if (root / name).exists():
            files[name] = safe_file(root, name).read_bytes()
    # Protect against a changed terminal receipt during snapshot construction.
    if read(safe_file(root, 'execution.json')) != event:
        raise ValueError('TERMINAL_RECEIPT_CHANGED')
    manifest = {'version': 'terminal-single-ssh-v1', 'taskId': task_id, 'nonce': nonce,
                'status': event['status'], 'completed': completed,
                'files': {n: {'bytes': len(v), 'sha256': hashlib.sha256(v).hexdigest()}
                          for n, v in files.items()}}
    files['retrieval-manifest.json'] = json.dumps(manifest, sort_keys=True).encode()
    stream = io.BytesIO()
    with gzip.GzipFile(fileobj=stream, mode='wb', mtime=0) as gz:
        with tarfile.open(fileobj=gz, mode='w|') as tar:
            for name, data in sorted(files.items()):
                item = tarfile.TarInfo(name); item.size = len(data)
                tar.addfile(item, io.BytesIO(data))
    data = stream.getvalue()
    if len(data) > MAX_ARCHIVE:
        raise ValueError('BUNDLE_CAPTURE_BOUND_EXCEEDED_NO_CHUNK_FALLBACK')
    return data, {**{k: manifest[k] for k in ('version', 'taskId', 'nonce', 'status', 'completed')},
                  'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                  'exportSeconds': time.perf_counter() - started}


def main(q):
    root = Path(q['root']).resolve(); base = Path(q['data_root']).resolve()
    if not base.is_relative_to('/home/jovyan') or not root.is_relative_to(base) or root.name != 'run':
        raise ValueError('EXACT_JOINT_ROOT_REQUIRED')
    data, _ = build(root, root.parent, q['taskId'], q['nonce'])
    sys.stdout.buffer.write(data)


if __name__ == '__main__':
    main(json.loads(base64.b64decode(sys.argv[1])))
