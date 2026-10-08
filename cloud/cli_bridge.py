"""WSL CLI adapter: only emit allowlisted, non-secret fields; never echo CLI stderr."""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path


def cli_error_label(exit_code, stderr):
    if exit_code == 7:
        if re.search(r'\bunauthenticated\b', stderr, re.IGNORECASE):
            return 'CLI_SERVER_UNAUTHENTICATED_EXIT_7'
        return 'CLI_AUTH_REQUIRED_EXIT_7'
    if exit_code == 15:
        return 'CLI_PERMISSION_DENIED_EXIT_15'
    return 'CLI_FAILED_EXIT_' + str(exit_code)


def run_cli(settings, args, json_result=True):
    command = [settings['cli_path'], *args, '--color=false', '--no-check-update',
               '--no-progress', '--no-browser', '--auth-timeout=3s',
               '--timeout=15s', '--per-retry-timeout=10s', '--retries=1']
    if json_result:
        command += ['--format', 'json', '--profile', settings['profile']]
    mutation = args[:3] in (['ai', 'devlab', 'restart'], ['ai', 'devlab', 'stop'])
    end = time.monotonic() + (25 if mutation else 35)
    for attempt in range(1 if mutation else 2):
        remaining = end - time.monotonic()
        if remaining <= 0:
            raise RuntimeError('CLI_READ_BUDGET_EXHAUSTED')
        try:
            result = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True,
                                    text=True, timeout=min(25, remaining))
        except subprocess.TimeoutExpired:
            if not mutation and attempt == 0:
                continue
            raise RuntimeError('CLI_PROCESS_TIMEOUT') from None
        if not result.returncode:
            return json.loads(result.stdout) if json_result else result.stdout.strip()
        # Only classified transient reads retry. Never repeat an uncertain mutation.
        transient = re.search(r'\b(?:Unavailable|DeadlineExceeded)\b|connection reset|TLS handshake timeout',
                              result.stderr, re.IGNORECASE)
        if not mutation and attempt == 0 and transient and result.returncode not in (7, 15):
            continue
        # Authentication errors can include URLs/codes; do not print raw stderr.
        raise RuntimeError(cli_error_label(result.returncode, result.stderr))


def canonical_key(key):
    parts = key.strip().split()
    if len(parts) < 2 or not parts[0].startswith('ssh-'):
        raise ValueError('INVALID_PUBLIC_KEY')
    return ' '.join(parts[:2])


def validate_profile_context(settings, tenant, project):
    if project != settings['project_id']:
        raise ValueError('PROFILE_PROJECT_MISMATCH')
    # A user can access an invited tenant's resource IDs while retaining their
    # own default tenant. The project's API identity proves resource ownership.
    return tenant == settings['tenant_id']


def validate_project_owner(raw, settings):
    meta = raw.get('metadata', {})
    if meta.get('id') != settings['project_id'] or meta.get('parent_id') != settings['tenant_id']:
        raise ValueError('PROJECT_ID_OR_TENANT_MISMATCH')
    return meta['parent_id']


def devlab_summary(raw, settings):
    meta, spec, status = (raw.get(k, {}) for k in ('metadata', 'spec', 'status'))
    if meta.get('id') != settings['devlab_id'] or meta.get('parent_id') != settings['project_id']:
        raise ValueError('DEVLAB_ID_OR_PROJECT_MISMATCH')
    if not isinstance(status.get('state'), str) or status['state'] not in {
            'PROVISIONING', 'STARTING', 'RUNNING', 'STOPPING', 'STOPPED',
            'DELETING', 'FAILED', 'ERROR', 'IMAGE_PULLING'}:
        raise ValueError('MISSING_OR_UNKNOWN_DEVLAB_STATE')
    return {'id': meta['id'], 'project_id': meta['parent_id'], 'state': status['state'],
            'image': spec.get('image', ''), 'workspace': spec.get('workspace', {}).get('container_path', ''),
            'instances': [{k: x.get(k, '') for k in
                           ('compute_instance_id', 'state', 'compute_instance_state', 'public_ip', 'private_ip')}
                          for x in status.get('instances', [])]}


def connection_target(devlab, vm, public_key, settings, allow_image_pulling=False):
    import ipaddress
    import yaml  # Available in this LOCAL Ubuntu; safe_load only.
    summary = devlab_summary(devlab, settings)
    allowed_states = {'RUNNING', 'IMAGE_PULLING'} if allow_image_pulling else {'RUNNING'}
    if summary['state'] not in allowed_states:
        raise ValueError('DEVLAB_NOT_RUNNING')
    instances = [x for x in summary['instances'] if x['state'] == 'RUNNING' or
                 (allow_image_pulling and x['state'] == 'IMAGE_PULLING' and x['compute_instance_state'] == 'RUNNING')]
    if len(instances) != 1:
        raise ValueError('CURRENT_VM_NOT_UNIQUE')
    current = instances[0]
    vm_id = current['compute_instance_id']
    if not re.fullmatch(r'computeinstance-[a-z0-9]+', vm_id):
        raise ValueError('INVALID_VM_ID')
    vm_meta = vm.get('metadata', {})
    if vm_meta.get('id') != vm_id:
        raise ValueError('VM_ID_OR_PROJECT_MISMATCH')
    # Serverless creates its backing VM under an appbox. The authoritative
    # current Devlab pointer, exact VM identity/name, IP and public key bind it.
    parent = vm_meta.get('parent_id', '')
    if parent != settings['project_id'] and not (
            re.fullmatch(r'appbox-[a-z0-9]+', parent) and vm_meta.get('name') == settings['devlab_id']):
        raise ValueError('VM_ID_OR_PROJECT_MISMATCH')
    if vm.get('status', {}).get('state') != 'RUNNING':
        raise ValueError('VM_NOT_RUNNING')
    address = str(ipaddress.ip_address(current['public_ip'].split('/')[0]))
    vm_addresses = [str(ipaddress.ip_address(x['public_ip_address']['address'].split('/')[0]))
                    for x in vm['status'].get('network_interfaces', [])
                    if x.get('public_ip_address', {}).get('address')]
    if address not in vm_addresses:
        raise ValueError('API_IP_MISMATCH')
    key = canonical_key(public_key)
    if key not in [canonical_key(k) for k in devlab.get('spec', {}).get('ssh_authorized_keys', [])]:
        raise ValueError('LOCAL_KEY_NOT_IN_DEVLAB')
    # Do not return or log cloud-init. Retain only a matching SSH username.
    user_data = vm.get('spec', {}).get('cloud_init_user_data', '')
    try:
        document = yaml.safe_load(user_data) or {}
    except yaml.YAMLError:
        raise ValueError('API_USERNAME_AND_KEY_NOT_UNIQUELY_VERIFIED') from None
    if not isinstance(document, dict) or not isinstance(document.get('users', []), list):
        raise ValueError('API_USERNAME_AND_KEY_NOT_UNIQUELY_VERIFIED')
    users = document.get('users', [])
    names = [u.get('name') for u in users if isinstance(u, dict) and key in
             [canonical_key(k) for k in u.get('ssh_authorized_keys', [])]]
    if len(names) != 1 or not re.fullmatch(r'[a-z_][a-z0-9_-]{0,31}', names[0] or ''):
        raise ValueError('API_USERNAME_AND_KEY_NOT_UNIQUELY_VERIFIED')
    if not summary['image'] or summary['workspace'] != '/home':
        raise ValueError('EXPECTED_IMAGE_OR_HOME_WORKSPACE_MISSING')
    return {**summary, 'vm_id': vm_id, 'vm_parent_id': parent, 'ip': address, 'ssh_user': names[0],
            'host_alias': 'nebius-' + settings['devlab_id'] + '-' + vm_id}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--settings', required=True)
    p.add_argument('--execute', action='store_true')
    p.add_argument('--action', choices=['local', 'status', 'target', 'host-target', 'stop'], required=True)
    p.add_argument('--public-key-file')
    p.add_argument('--authorized-stop', action='store_true')
    args = p.parse_args()
    settings = json.loads(Path(args.settings).read_text(encoding='utf-8-sig'))
    if not args.execute or args.action == 'local':
        print(json.dumps({'offline':True,'cloud_calls':0,'config_exists':Path.home().joinpath('.nebius/config.yaml').is_file()})); return
    config_exists = Path.home().joinpath('.nebius/config.yaml').is_file()
    if not config_exists:
        raise RuntimeError('LOGIN_REQUIRED_NO_LOCAL_PROFILE_CONFIG')
    tenant = run_cli(settings, ['config', 'get', 'tenant-id', '--profile', settings['profile']], json_result=False)
    project = run_cli(settings, ['config', 'get', 'parent-id', '--profile', settings['profile']], json_result=False)
    # Wrong project defaults are rejected locally. Default tenant differences
    # are permitted only when live project ownership matches the fixed target.
    validate_profile_context(settings, tenant, project)
    project_raw = run_cli(settings, ['iam', 'v2', 'project', 'get', '--id', settings['project_id']])
    owner = validate_project_owner(project_raw, settings)
    devlab = run_cli(settings, ['ai', 'devlab', 'get', '--id', settings['devlab_id']])
    summary = devlab_summary(devlab, settings)
    if args.action == 'status':
        print(json.dumps({**summary, 'tenant_id': owner, 'project_ownership_verified': True}))
    elif args.action in ('target', 'host-target'):
        host_only = args.action == 'host-target'
        if summary['state'] != 'RUNNING' and not (host_only and summary['state'] == 'IMAGE_PULLING'):
            raise ValueError('DEVLAB_NOT_RUNNING')
        active = [x for x in summary['instances'] if x['state'] == 'RUNNING' or
                  (host_only and x['state'] == 'IMAGE_PULLING' and x['compute_instance_state'] == 'RUNNING')]
        if len(active) != 1:
            raise ValueError('CURRENT_VM_NOT_UNIQUE')
        vm = run_cli(settings, ['compute', 'instance', 'get', '--id', active[0]['compute_instance_id']])
        target = connection_target(devlab, vm, Path(args.public_key_file).read_text(), settings, allow_image_pulling=host_only)
        # Catch a restart during the two API reads; caller rechecks immediately before SSH, too.
        fresh = devlab_summary(run_cli(settings, ['ai', 'devlab', 'get', '--id', settings['devlab_id']]), settings)
        if fresh['state'] != summary['state'] or fresh['instances'] != summary['instances']:
            raise ValueError('VM_CHANGED_DURING_VALIDATION')
        print(json.dumps(target))
    else:
        if not settings['cloud_stop_enabled'] or not args.authorized_stop:
            raise RuntimeError('CLOUD_STOP_NOT_ENABLED_OR_AUTHORIZED')
        if summary['state'] != 'STOPPED':
            # CLI --async returns a plain operation ID, even with --format=json.
            run_cli(settings, ['ai', 'devlab', 'stop', '--id', settings['devlab_id'], '--async',
                               '--profile', settings['profile']], json_result=False)
        # A successful stop submission is not STOPPED confirmation.
        print(json.dumps({'stop_submitted': True, 'stopped_verified': False}))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        known = str(error)
        if not re.fullmatch(r'[A-Z0-9_]+', known):
            known = 'BRIDGE_FAILED_' + type(error).__name__
        print(json.dumps({'error': known}), file=sys.stderr)
        sys.exit(2)
