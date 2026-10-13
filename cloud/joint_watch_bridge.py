"""Locate the approved container once, then stream its read-only file watcher."""
import base64
import datetime
import json
import os
import pwd
import re
import subprocess
import sys


def main(req):
    if pwd.getpwuid(os.getuid()).pw_name != req['ssh_user']:
        raise ValueError('VM_USER_MISMATCH')
    q = req['container_request']
    if not re.fullmatch('[0-9a-f]{32}', q['runId']) or not q['prep'].endswith('/preview-' + q['runId']):
        raise ValueError('WATCH_SOURCE_BINDING_MISMATCH')
    probe = {'__name__': 'local_reused_probe'}
    exec(compile(base64.b64decode(req['probe_source']), '<reused-probe>', 'exec'), probe)
    ids = probe['docker']('ps', '-q', '--no-trunc').split()
    if not ids or len(ids) > 32 or any(not re.fullmatch('[0-9a-f]{64}', x) for x in ids):
        raise ValueError('NO_VALID_RUNNING_CONTAINERS')
    cid = probe['choose_container'](json.loads(probe['docker']('inspect', *ids)), req['image'])
    command = ['sudo', '-n', 'docker', 'exec', '-i', '-u', 'jovyan', '-w', '/home/jovyan',
               cid, req['container_python'], '-u', '-B', '-c',
               base64.b64decode(req['container_program']).decode(),
               base64.b64encode(json.dumps(q).encode()).decode()]
    deadline = datetime.datetime.fromisoformat(q['deadlineUtc'].replace('Z', '+00:00')).timestamp()
    remaining = deadline - __import__('time').time()
    if remaining <= 0:
        raise ValueError('FIXED_WATCH_DEADLINE_REACHED')
    result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=sys.stdout,
                            stderr=subprocess.DEVNULL, timeout=remaining)
    if result.returncode:
        raise ValueError('WATCH_CONTAINER_FAILED_EXIT_' + str(result.returncode))


if __name__ == '__main__':
    try:
        main(json.loads(base64.b64decode(sys.argv[1])))
    except Exception as e:
        label = str(e)
        if not re.fullmatch('[A-Z0-9_]+', label):
            label = 'WATCH_BRIDGE_FAILED_' + type(e).__name__
        print(label, file=sys.stderr); sys.exit(3)
