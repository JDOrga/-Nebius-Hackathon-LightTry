"""Read-only Nebius service-account proof; never prints credentials or raw RPC errors.

This program deliberately constructs an SDK with PKReader, not CLI config or an
environment IAM token. It cannot start, stop, restart, or submit inference.
"""
import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import stat
import sys


REQUIRED = {'schemaVersion', 'serviceAccountId', 'publicKeyId', 'privateKeyFile',
            'projectId', 'devlabId', 'authMethod'}


def load_config(name):
    path = Path(name)
    if not path.is_absolute() or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('EXPLICIT_PRIVATE_CONFIG_REQUIRED')
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > 4096 or (os.name != 'nt' and info.st_mode & 0o007):
        raise ValueError('PRIVATE_CONFIG_PERMISSIONS_REQUIRED')
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict) or set(value) != REQUIRED or value['schemaVersion'] != 1 or \
            value['authMethod'] != 'service-account-private-key':
        raise ValueError('SERVICE_ACCOUNT_CONFIG_REQUIRED')
    for field, prefix in (('serviceAccountId', 'serviceaccount-'),
                          ('publicKeyId', 'publickey-'), ('projectId', 'project-'),
                          ('devlabId', 'devlab-')):
        item = value[field]
        if not isinstance(item, str) or not re.fullmatch(prefix + r'[a-z0-9]{8,64}', item):
            raise ValueError('BOUND_IDENTITY_INVALID')
    key = Path(value['privateKeyFile'])
    if not key.is_absolute() or any(p.is_symlink() for p in (key, *key.parents)):
        raise ValueError('PRIVATE_KEY_PATH_REQUIRED')
    key_info = key.stat()
    if not stat.S_ISREG(key_info.st_mode) or key_info.st_size > 16384 or (os.name != 'nt' and key_info.st_mode & 0o007):
        raise ValueError('PRIVATE_KEY_PERMISSIONS_REQUIRED')
    with key.open('rb') as stream:
        if stream.read(27) != b'-----BEGIN PRIVATE KEY-----':
            raise ValueError('PKCS8_PRIVATE_KEY_REQUIRED')
    return value


def error_category(error):
    """Classify structured RPC codes only, never stringify arbitrary error text."""
    codes = []
    for item in (error, getattr(error, 'status', None)):
        if item is None:
            continue
        for field in ('code', 'status_code', 'http_status'):
            value = getattr(item, field, None)
            if callable(value):
                try:
                    value = value()
                except Exception:
                    continue
            if value is not None:
                codes.append(getattr(value, 'name', str(value)).upper())
    if any(x in ('16', '401', 'UNAUTHENTICATED', 'STATUSCODE.UNAUTHENTICATED') for x in codes):
        return '401_UNAUTHENTICATED'
    if any(x in ('7', '403', 'PERMISSION_DENIED', 'STATUSCODE.PERMISSION_DENIED') for x in codes):
        return '403_PERMISSION_DENIED'
    return 'REDACTED_' + type(error).__name__


def name(value):
    return getattr(value, 'name', str(value)).split('.')[-1]


def renewal_probe(sdk, option_names=None):
    if option_names is None:
        from nebius.aio.token.renewable import (OPTION_RENEW_REQUEST_TIMEOUT,
                                                OPTION_RENEW_REQUIRED, OPTION_RENEW_SYNCHRONOUS)
        option_names = (OPTION_RENEW_REQUIRED, OPTION_RENEW_SYNCHRONOUS,
                        OPTION_RENEW_REQUEST_TIMEOUT)
    options = dict(zip(option_names, ('true', 'true', '5')))
    sdk.whoami(auth_options=options, auth_timeout=18, timeout=10).wait()
    return 'FORCED_REFRESH_SUCCEEDED'


def probe(config, *, force_renew=False):
    from nebius.sdk import SDK
    from nebius.base.service_account.pk_file import Reader as PKReader
    from nebius.aio.metrics import Metrics
    from nebius.api.nebius.ai.v1 import DevlabServiceClient, GetDevlabRequest
    from nebius.api.nebius.iam.v1 import AuthPublicKeyServiceClient, GetAuthPublicKeyRequest
    from nebius.api.nebius.iam.v2 import ProjectServiceClient, GetProjectRequest

    observed = {'authMethod': 'service-account-private-key',
                'serviceAccountId': config['serviceAccountId'],
                'publicKeyId': config['publicKeyId'],
                'expectedProjectId': config['projectId'],
                'devlabId': config['devlabId'], 'token': {'acquired': False}}
    lifetime = []
    def token_lifetime(metric):
        ttl = float(metric.ttl_seconds)
        if 0 < ttl < 7 * 86400:
            lifetime.append((ttl, datetime.now(timezone.utc)))
    sdk = SDK(credentials=PKReader(filename=config['privateKeyFile'],
                                   public_key_id=config['publicKeyId'],
                                   service_account_id=config['serviceAccountId']),
              metrics=Metrics(token_lifetime=token_lifetime),
              user_agent_prefix='LightTry-SA-ReadOnly/1.0')
    try:
        try:
            profile = sdk.whoami(auth_timeout=20, timeout=10).wait()
            account = profile.service_account_profile
            if account is None or account.info is None:
                raise ValueError('NOT_SERVICE_ACCOUNT_PROFILE')
            metadata = account.info.metadata
            observed['identity'] = {'id': metadata.id, 'name': metadata.name,
                                    'projectId': metadata.parent_id,
                                    'active': bool(account.info.status.active)}
            if metadata.id != config['serviceAccountId']:
                raise ValueError('SERVICE_ACCOUNT_ID_MISMATCH')
            observed['token']['acquired'] = True
            if lifetime:
                ttl, at = lifetime[-1]
                observed['token'].update(ttlSeconds=round(ttl),
                    expiresAtUtcApprox=(at + timedelta(seconds=ttl)).isoformat())
            else:
                observed['token']['ttlSeconds'] = None
            if force_renew:
                observed['renewal'] = renewal_probe(sdk)
        except Exception as error:
            observed['authenticationError'] = error_category(error)
            return observed

        try:
            item = DevlabServiceClient(sdk).get(
                GetDevlabRequest(id=config['devlabId']), auth_timeout=20, timeout=10).wait()
            instances = [{'id': x.compute_instance_id, 'state': name(x.state)}
                         for x in item.status.instances]
            observed['devlabGet'] = {'success': True, 'interface': 'nebius.ai.v1.DevlabService/Get',
                                     'id': item.metadata.id, 'projectId': item.metadata.parent_id,
                                     'state': name(item.status.state), 'instances': instances}
            observed['devlabGet']['identityMatch'] = (
                item.metadata.id == config['devlabId'] and
                item.metadata.parent_id == config['projectId'])
        except Exception as error:
            observed['devlabGet'] = {'success': False, 'interface': 'nebius.ai.v1.DevlabService/Get',
                                     'error': error_category(error)}
            return observed

        try:
            project = ProjectServiceClient(sdk).get(
                GetProjectRequest(id=config['projectId']), auth_timeout=20, timeout=10).wait()
            observed['projectGet'] = {'success': True, 'id': project.metadata.id,
                                      'name': project.metadata.name}
        except Exception as error:
            observed['projectGet'] = {'success': False, 'error': error_category(error)}

        try:
            key = AuthPublicKeyServiceClient(sdk).get(
                GetAuthPublicKeyRequest(id=config['publicKeyId']), auth_timeout=20, timeout=10).wait()
            expiry = key.spec.expires_at
            explicit_expiry = expiry if expiry is not None and expiry.timestamp() > 0 else None
            observed['publicKey'] = {'metadataRead': True, 'id': key.metadata.id,
                                     'state': name(key.status.state),
                                     'expiresAtUtc': explicit_expiry.isoformat() if explicit_expiry else None,
                                     'expiryConfigured': explicit_expiry is not None,
                                     'keySize': key.status.key_size}
        except Exception as error:
            observed['publicKey'] = {'metadataRead': False, 'error': error_category(error),
                                     'expiresAtUtc': 'UNKNOWN'}
        return observed
    finally:
        sdk.sync_close()


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    parser.add_argument('--force-renew', action='store_true')
    parser.add_argument('--context', choices=('host', 'web', 'guard', 'fresh'), default='host')
    args = parser.parse_args(argv)
    try:
        result = probe(load_config(args.config), force_renew=args.force_renew)
        result['context'] = args.context
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result.get('devlabGet', {}).get('success') and \
            result['devlabGet'].get('identityMatch') else 1
    except Exception as error:
        print(json.dumps({'context': args.context, 'fatal': error_category(error)}))
        return 1


if __name__ == '__main__':
    sys.exit(main())
