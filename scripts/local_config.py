"""Offline configuration: only inspect path metadata; never read credentials."""
import argparse
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = Path(os.environ.get('NEBIUS_LOCAL_CONFIG', str(ROOT / 'config/local.json')))
REQUIRED = ('cli_path', 'wsl_distro', 'profile', 'tenant_id', 'project_id', 'devlab_id',
            'key_path', 'public_key_fingerprint', 'known_hosts_path', 'auth_config_path',
            'data_dir', 'upstream_repo', 'container_python', 'container_repo',
            'container_checkpoint_dir', 'container_data_dir', 'cuda_home')

def load(path=CONFIG):
    if not Path(path).is_file():
        raise ValueError('LOCAL_CONFIG_MISSING_NO_AUTO_LOGIN')
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def upstream():
    # Absent configuration permits synthetic tests, never a fallback into old experiments.
    return Path(load()['upstream_repo']) if CONFIG.is_file() else ROOT / '.local/upstream-not-configured'

def validate(config, check_paths=True):
    issues = []
    for name in REQUIRED:
        value = config.get(name)
        if not isinstance(value, str) or not value or 'REPLACE' in value or 'replace' in value:
            issues.append({'field': name, 'category': 'REQUIRED_LOCAL_VALUE'})
    if check_paths:
        for name in ('key_path', 'known_hosts_path', 'auth_config_path', 'data_dir', 'upstream_repo'):
            value = config.get(name)
            if value and not Path(value).exists():
                issues.append({'field': name, 'category': 'LOCAL_PATH_MISSING_NO_AUTO_SETUP'})
        if config.get('key_path') and not Path(config['key_path'] + '.pub').is_file():
            issues.append({'field': 'key_path', 'category': 'PUBLIC_KEY_PATH_MISSING'})
    return issues

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--config', type=Path, default=CONFIG)
    a = p.parse_args()
    try:
        issues = validate(load(a.config))
    except (ValueError, OSError):
        issues = [{'field': 'config', 'category': 'LOCAL_CONFIG_MISSING_OR_INVALID_NO_AUTO_LOGIN'}]
    print(json.dumps({'offline': True, 'cloud_calls': 0, 'issues': issues}))
    return 1 if issues else 0

if __name__ == '__main__':
    raise SystemExit(main())
