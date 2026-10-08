"""Read-only API locator; invoked only by the explicitly enabled host entry.
Returns allowlisted public identity and classified errors, never CLI stderr/config.
Uses existing cli_bridge validators; no start/stop/auth/trust operations.
"""
import argparse, importlib.util, json, re, signal, subprocess
from pathlib import Path

class Failure(Exception):
    def __init__(self, label, retryable=False, exit_code=None, devlab_state=None):
        self.label, self.retryable = label, retryable
        self.exit_code = exit_code
        self.devlab_state = devlab_state

def cli(settings, args, structured=True):
    command = [settings['cli_path'], *args, '--color=false', '--no-check-update',
               '--no-progress', '--no-browser', '--auth-timeout=3s', '--timeout=15s',
               '--per-retry-timeout=10s', '--retries=1']
    if structured:
        command += ['--format', 'json', '--profile', settings['profile']]
    try:
        result = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True,
                                text=True, timeout=25)
    except subprocess.TimeoutExpired:
        raise Failure('API_TIMEOUT', True) from None
    if result.returncode:
        # Transient status is grounded in the returned error, not guessed from exit code.
        if re.search(r'\b(unauthenticated|permission.?denied)\b', result.stderr, re.I):
            raise Failure('API_AUTH_OR_PERMISSION', exit_code=result.returncode)
        if re.search(r'\b(unavailable|deadline.?exceeded)\b', result.stderr, re.I):
            raise Failure('API_TRANSIENT', True, result.returncode)
        raise Failure('API_NONZERO_EXIT', exit_code=result.returncode)
    try:
        return json.loads(result.stdout) if structured else result.stdout.strip()
    except (ValueError, TypeError):
        raise Failure('API_INVALID_JSON') from None

def locate(settings, bridge, public_key):
    tenant = cli(settings, ['config', 'get', 'tenant-id', '--profile', settings['profile']], False)
    project = cli(settings, ['config', 'get', 'parent-id', '--profile', settings['profile']], False)
    bridge.validate_profile_context(settings, tenant, project)
    bridge.validate_project_owner(cli(settings, ['iam', 'v2', 'project', 'get', '--id', settings['project_id']]), settings)
    raw = cli(settings, ['ai', 'devlab', 'get', '--id', settings['devlab_id']])
    summary = bridge.devlab_summary(raw, settings)
    if summary['state'] not in ('RUNNING', 'IMAGE_PULLING'):
        if summary['state'] in ('STARTING', 'PROVISIONING'):
            raise Failure('DEVLAB_NOT_READY', True, devlab_state=summary['state'])
        raise Failure('DEVLAB_INACTIVE')
    active = [v for v in summary['instances'] if v['state'] == 'RUNNING' or
              (summary['state'] == 'IMAGE_PULLING' and v['state'] == 'IMAGE_PULLING' and v['compute_instance_state'] == 'RUNNING')]
    if not active:
        raise Failure('VM_INFO_PENDING', True, devlab_state=summary['state'])
    if len(active) != 1:
        raise Failure('VM_IDENTITY_AMBIGUOUS')
    if not active[0]['public_ip']:
        raise Failure('VM_INFO_PENDING', True, devlab_state=summary['state'])
    vm = cli(settings, ['compute', 'instance', 'get', '--id', active[0]['compute_instance_id']])
    target = bridge.connection_target(raw, vm, public_key, settings, allow_image_pulling=True)
    fresh = bridge.devlab_summary(cli(settings, ['ai', 'devlab', 'get', '--id', settings['devlab_id']]), settings)
    if fresh['state'] != summary['state'] or fresh['instances'] != summary['instances']:
        raise Failure('VM_CHANGED_DURING_VALIDATION')
    # These flags are emitted only after original identity/key mapping validators pass.
    return {**{k: target[k] for k in ('id', 'vm_id', 'ip', 'ssh_user', 'host_alias', 'image', 'state')},
            'api_target_verified': True, 'public_key_mapping_verified': True}

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--execute', action='store_true'); p.add_argument('--settings', required=True); p.add_argument('--bridge', required=True)
    p.add_argument('--public-key-file', required=True); p.add_argument('--timeout-seconds', type=int, default=45)
    a = p.parse_args()
    if not a.execute:
        print(json.dumps({'mode':'LOCAL_PLAN','cloud_calls':0})); return
    if hasattr(signal, 'SIGALRM'):
        def expired(*_): raise Failure('API_TIMEOUT', True)
        signal.signal(signal.SIGALRM, expired); signal.alarm(a.timeout_seconds)
    try:
        spec = importlib.util.spec_from_file_location('existing_identity_bridge', a.bridge)
        bridge = importlib.util.module_from_spec(spec); spec.loader.exec_module(bridge)
        settings = json.loads(Path(a.settings).read_text(encoding='utf-8-sig'))
        if not re.fullmatch(r'devlab-[a-z0-9]+', settings.get('devlab_id','')):
            raise Failure('AUTHORIZED_RESOURCE_MISMATCH')
        target = locate(settings, bridge, Path(a.public_key_file).read_text())
        print(json.dumps({'ok': True, 'target': target})); return
    except Failure as e:
        data = {'ok': False, 'category': e.label, 'retryable': e.retryable, 'exception_type': type(e).__name__,
                'cli_exit_code': e.exit_code}
        if e.devlab_state in ('STARTING','PROVISIONING','RUNNING','IMAGE_PULLING','STOPPING','STOPPED'):
            data['devlab_state'] = e.devlab_state
    except Exception as e:
        label = str(e)
        if not re.fullmatch('[A-Z0-9_]{1,100}', label): label = 'API_UNCLASSIFIED_ERROR'
        data = {'ok': False, 'category': label, 'retryable': False, 'exception_type': type(e).__name__}
    print(json.dumps(data)); raise SystemExit(2)

if __name__ == '__main__': main()
