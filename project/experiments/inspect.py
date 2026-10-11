"""Read-only exact experiment state; limited model logs, no environment/credentials."""
import base64
import hashlib
import json
import os
from pathlib import Path
import sys


def main(q):
    prep = Path(q['prep']).resolve()
    if not prep.is_relative_to('/home/jovyan') or not prep.name.startswith('preview-'):
        raise ValueError('EXACT_EXPERIMENT_PREPARATION_REQUIRED')
    def read(relative):
        path = prep / relative
        if path.is_symlink() or not path.resolve().is_relative_to(prep):
            raise ValueError('UNSAFE_INSPECTION_PATH')
        return json.loads(path.read_text()) if path.is_file() else None
    status = read('run/execution.json')
    cases = {}
    result_files = {}
    for case in ('baseline', 'rotation-minus45', 'rotation-plus45', 'strength-low', 'strength-high', 'baseline-repeat'):
        cases[case] = read('run/controls/' + case + '/0/state.json')
        completed = read('run/controls/' + case + '/0/complete.json')
        if completed:
            result_files[case] = completed['result']
    processes = []
    for path in Path('/proc').glob('[0-9]*/cmdline'):
        try:
            data = path.read_bytes(); argv = data.split(b'\0')
            if (str(prep / 'project/experiments/worker.py').encode() in argv or
                    str(prep / 'project/experiments/measured_controls.py').encode() in argv):
                processes.append({'pid': int(path.parent.name), 'argvSha256': hashlib.sha256(data).hexdigest()})
        except (OSError, ValueError):
            pass
    logs = {}
    names = ['worker.log', 'run/preflight.log']
    names += [str(p.relative_to(prep)) for p in sorted((prep / 'run').glob('forward-*.log'))[-2:]]
    for name in names:
        path = prep / name
        if path.is_file() and not path.is_symlink():
            # Inference/preflight logs only, not arbitrary machine history.
            logs[name] = path.read_text(errors='replace')[-2400:]
    timeline = prep / 'run/forward-timing.jsonl'
    tail = [json.loads(line) for line in timeline.read_text().splitlines()[-6:]] if timeline.is_file() else []
    print(json.dumps({'status': status, 'cases': cases, 'ownedProcesses': processes,
                     'launchMarker': read('launch-marker.json'), 'logs': logs,
                     'resultFiles': result_files, 'timelineTail': tail}))


if __name__ == '__main__':
    main(json.loads(base64.b64decode(sys.argv[1])))
