"""Experimental launch via the existing guarded, pinned transport; no VM lifecycle."""
import base64
import json
from pathlib import Path
import subprocess
import sys


def main(q):
    prep = Path(q['prep']).resolve()
    if not prep.is_relative_to('/home/jovyan') or (prep / 'run').exists():
        raise ValueError('NEW_PERSISTENT_PREPARATION_REQUIRED')
    sys.path.insert(0, str(prep / 'scripts'))
    from weights import parse_deadline, check_time
    deadline = parse_deadline(q['deadline_utc']); check_time(deadline)
    receipt = q['guard_launch_receipt']
    if (receipt.get('offline') or not receipt.get('single_run') or
            receipt.get('budget_usd_including_tax', 0) <= 0 or not receipt.get('approval_reference') or
            deadline > parse_deadline(receipt['deadline_utc']) or q.get('model_license_ack') is not True):
        raise ValueError('CURRENT_GUARDED_BUDGET_REQUIRED')
    for name, value in [('launch-marker.json', {'deadline': q['deadline_utc']}),
                        ('runtime.json', q), ('guard-receipt.json', receipt)]:
        with (prep / name).open('x') as stream:
            json.dump(value, stream)
    with (prep / 'worker.log').open('x') as stream:
        child = subprocess.Popen([sys.executable, '-u', '-B',
            str(prep / 'project/experiments/worker.py'), '--prep', str(prep),
            '--runtime', str(prep / 'runtime.json'), '--receipt', str(prep / 'guard-receipt.json')],
            stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
    print(json.dumps({'workerPid': child.pid, 'prep': str(prep)}))


if __name__ == '__main__':
    main(json.loads(base64.b64decode(sys.argv[1])))
