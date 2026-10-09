"""Small program explicitly sent through the existing guarded launch transport."""
import base64
import json
import os
from pathlib import Path
import subprocess
import sys


def main(q):
    prep = Path(q['prep']).resolve()
    if not prep.is_relative_to('/home/jovyan') or (prep / 'run').exists():
        raise ValueError('NEW_PERSISTENT_PREPARATION_REQUIRED')
    sys.path.insert(0, str(prep / 'scripts'))
    from weights import parse_deadline, check_time
    deadline = parse_deadline(q['deadline_utc'])
    check_time(deadline)
    receipt = q['guard_launch_receipt']  # transport supplies this, never the browser
    if receipt.get('offline') or not receipt.get('single_run') or receipt.get('budget_usd_including_tax', 0) <= 0 or not receipt.get('approval_reference') or deadline > parse_deadline(receipt['deadline_utc']):
        raise ValueError('CURRENT_GUARDED_BUDGET_REQUIRED')
    with (prep / 'launch-marker.json').open('x') as stream:
        json.dump({'deadline': q['deadline_utc']}, stream)
    with (prep / 'runtime.json').open('x') as stream:
        json.dump(q, stream)
    with (prep / 'guard-receipt.json').open('x') as stream:
        json.dump(receipt, stream)
    with (prep / 'worker.log').open('x') as stream:
        p = subprocess.Popen([sys.executable, '-u', '-B', str(prep / 'project/inference/worker.py'),
            '--request', str(prep / 'request.json'), '--runtime', str(prep / 'runtime.json'),
            '--receipt', str(prep / 'guard-receipt.json')], stdin=subprocess.DEVNULL,
            stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
    print(json.dumps({'workerPid': p.pid, 'prep': str(prep)}))


if __name__ == '__main__':
    main(json.loads(base64.b64decode(sys.argv[1])))
