"""Runs in VM memory; only inspect allowlisted Docker metadata and bounded commands."""
import base64
import json
import re
import subprocess
import sys


def choose_container(items, image):
    candidates = [c for c in items if c.get('State', {}).get('Running') is True
                  and c.get('Config', {}).get('Image') == image
                  and c.get('Config', {}).get('User') in ('jovyan', 'jovyan:users', '1000', '1000:100')
                  and any(m.get('Destination') == '/home' and m.get('RW') is True
                          for m in c.get('Mounts', []))]
    if len(candidates) != 1:
        raise ValueError('CONTAINER_MATCH_NOT_UNIQUE')
    cid = candidates[0]['Id']
    if not re.fullmatch(r'[0-9a-f]{64}', cid):
        raise ValueError('INVALID_CONTAINER_ID')
    return cid


def docker(*args):
    result = subprocess.run(['sudo', '-n', 'docker', *args], capture_output=True,
                            text=True, timeout=20)
    if result.returncode:
        raise ValueError('DOCKER_QUERY_FAILED')
    return result.stdout


def main(request):
    ids = docker('ps', '-q', '--no-trunc').split()
    if not ids or len(ids) > 32 or any(not re.fullmatch(r'[0-9a-f]{64}', i) for i in ids):
        raise ValueError('NO_VALID_RUNNING_CONTAINERS')
    # Docker inspect can contain secret Env; raw data never leaves VM memory.
    cid = choose_container(json.loads(docker('inspect', *ids)), request['image'])
    commands = {'probe': ['python3', '-c', 'import os,pwd,json; print(json.dumps(dict(user=pwd.getpwuid(os.getuid()).pw_name,cwd=os.getcwd(),home=os.path.expanduser("~"))))'], 'gpu': ['nvidia-smi','--query-gpu=name,memory.total,driver_version','--format=csv,noheader']}
    operation = request['operation']
    report = {'nonce': request['nonce'], 'operation': operation, 'container_id': cid,
              'image': request['image'], 'container_user': 'jovyan', 'container_home': '/home/jovyan'}
    if operation != 'locate':
        if operation not in commands:
            raise ValueError('COMMAND_NOT_ALLOWED')
        result = subprocess.run(['sudo', '-n', 'docker', 'exec', '-u', 'jovyan', '-w',
                                 '/home/jovyan', cid, *commands[operation]], capture_output=True,
                                text=True, timeout=60)
        if result.returncode:
            raise ValueError('CONTAINER_COMMAND_FAILED')
        report['output'] = result.stdout
        if operation == 'probe':
            identity = json.loads(result.stdout)
            if identity != {'user': 'jovyan', 'cwd': '/home/jovyan', 'home': '/home/jovyan'}:
                raise ValueError('CONTAINER_IDENTITY_MISMATCH')
    print('LOCAL_RESULT_' + request['nonce'] + ':' + json.dumps(report, separators=(',', ':')))
    print('LOCAL_DONE_' + request['nonce'])


if __name__ == '__main__':
    try:
        main(json.loads(base64.b64decode(sys.argv[1])))
    except Exception as error:
        label = str(error)
        if not re.fullmatch(r'[A-Z0-9_]+', label):
            label = 'REMOTE_FAILED_' + type(error).__name__
        print(label, file=sys.stderr)
        sys.exit(3)
