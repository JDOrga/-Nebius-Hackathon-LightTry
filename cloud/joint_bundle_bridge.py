"""One pinned SSH invocation: container validation, snapshot, archive transmission."""
import base64
import hashlib
import json
import os
import pwd
import re
import subprocess
import sys


def main(req):
    if pwd.getpwuid(os.getuid()).pw_name != req['ssh_user']:
        raise ValueError('VM_USER_MISMATCH')
    if not re.fullmatch('[0-9a-f]{32}', req['run_id']):
        raise ValueError('INVALID_RUN_ID')
    q = req['container_request']
    if not q['root'].endswith('/preview-' + req['run_id'] + '/run'):
        raise ValueError('BUNDLE_SOURCE_BINDING_MISMATCH')
    probe = {'__name__': 'local_reused_probe'}
    exec(compile(base64.b64decode(req['probe_source']), '<reused-probe>', 'exec'), probe)
    ids = probe['docker']('ps', '-q', '--no-trunc').split()
    if not ids or len(ids) > 32 or any(not re.fullmatch('[0-9a-f]{64}', x) for x in ids):
        raise ValueError('NO_VALID_RUNNING_CONTAINERS')
    cid = probe['choose_container'](json.loads(probe['docker']('inspect', *ids)), req['image'])
    command = ['sudo', '-n', 'docker', 'exec', '-i', '-u', 'jovyan', '-w', '/home/jovyan',
               cid, req['container_python'], '-B', '-c',
               base64.b64decode(req['container_program']).decode(),
               base64.b64encode(json.dumps(q).encode()).decode()]
    result = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, timeout=75)
    if result.returncode:
        raise ValueError('BUNDLE_EXPORT_FAILED_EXIT_' + str(result.returncode))
    data = result.stdout
    if not 0 < len(data) <= 700 * 1024:
        raise ValueError('BUNDLE_CAPTURE_BOUND_EXCEEDED_NO_CHUNK_FALLBACK')
    path = '/home/' + req['ssh_user'] + '/nebius-upload-' + req['run_id'] + '/joint-results.tar.gz'
    with open(path, 'xb') as f:
        f.write(data)  # preserve remote snapshot, never overwrite/re-export silently
    metadata = {'taskId': q['taskId'], 'nonce': q['nonce'], 'bytes': len(data),
                'sha256': hashlib.sha256(data).hexdigest(),
                'dataBase64': base64.b64encode(data).decode()}
    report = dict(nonce=req['nonce'], operation='retrieve_joint_bundle', image=req['image'],
                  container_id=cid, container_user='jovyan', container_home='/home/jovyan',
                  output=json.dumps(metadata, separators=(',', ':')))
    print('LOCAL_RESULT_' + req['nonce'] + ':' + json.dumps(report, separators=(',', ':')))
    print('LOCAL_DONE_' + req['nonce'])


if __name__ == '__main__':
    try:
        main(json.loads(base64.b64decode(sys.argv[1])))
    except Exception as exc:
        label = str(exc)
        if not re.fullmatch('[A-Z0-9_]+', label):
            label = 'BUNDLE_BRIDGE_FAILED_' + type(exc).__name__
        print(label, file=sys.stderr); sys.exit(3)
