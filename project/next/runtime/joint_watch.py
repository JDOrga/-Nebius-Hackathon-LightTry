"""Read-only state-file subscription inside one existing container process."""
import base64
import datetime
import json
from pathlib import Path
import sys
import time


def snapshot(prep, plan):
    path = prep / 'run/execution.json'
    raw = json.loads(path.read_text()) if path.is_file() else {'status': 'queued', 'stage': 'pending'}
    if raw.get('taskId', plan['taskId']) != plan['taskId'] or raw.get('nonce', plan['nonce']) != plan['nonce']:
        raise ValueError('WATCH_TASK_IDENTITY_MISMATCH')
    status = raw['status']
    if status not in ('queued', 'running', 'succeeded', 'failed'):
        raise ValueError('WATCH_STATUS_INVALID')
    completed = [c['id'] for c in plan['cases']
                 if (prep / 'run/cases' / c['id'] / '0/complete.json').is_file()
                 and not (prep / 'run/cases' / c['id'] / '0/complete.json').is_symlink()]
    return {'taskId': plan['taskId'], 'nonce': plan['nonce'], 'status': status,
            'stage': str(raw.get('stage', 'pending'))[:80],
            'executionStopped': raw.get('executionStopped') is True, 'completed': completed}


def watch(prep, task_id, nonce, watch_nonce, deadline, *, sleep=time.sleep, wall=time.time):
    plan = json.loads((prep / 'joint.json').read_text())
    if (plan['taskId'], plan['nonce']) != (task_id, nonce):
        raise ValueError('WATCH_PLAN_IDENTITY_MISMATCH')
    previous, last_emit = None, 0.
    monotonic_deadline=time.monotonic()+max(0.,deadline-wall())
    while wall() < deadline and time.monotonic()<monotonic_deadline:
        state = snapshot(prep, plan); now = time.monotonic()
        if state != previous or now - last_emit >= 15:
            print(json.dumps({'watchNonce': watch_nonce, **state}), flush=True)
            previous, last_emit = state, now
        if state['status'] in ('succeeded', 'failed'):
            return  # local client must also verify process-stopped and SSH exit
        sleep(min(2., max(0., deadline - wall())))
    raise ValueError('FIXED_WATCH_DEADLINE_REACHED')


def main(q):
    prep = Path(q['prep']).resolve()
    if not prep.is_relative_to('/home/jovyan') or prep.name != 'preview-' + q['runId']:
        raise ValueError('EXACT_WATCH_PREPARATION_REQUIRED')
    deadline = datetime.datetime.fromisoformat(q['deadlineUtc'].replace('Z', '+00:00')).timestamp()
    watch(prep, q['taskId'], q['nonce'], q['watchNonce'], deadline)


if __name__ == '__main__':
    main(json.loads(base64.b64decode(sys.argv[1])))
