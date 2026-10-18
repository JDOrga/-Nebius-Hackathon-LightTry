"""Offline tests for explicit service-account binding and safe renewal diagnostics."""
import json
import tempfile
import unittest
from pathlib import Path

from project.nebius_sa_probe import error_category, load_config, renewal_probe


class NebiusSAProbeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.key = root / 'private.pem'
        self.key.write_bytes(b'-----BEGIN PRIVATE KEY-----\nFIXTURE_ONLY\n-----END PRIVATE KEY-----\n')
        self.key.chmod(0o600)
        self.config = root / 'service-account.json'
        self.value = {'schemaVersion': 1, 'authMethod': 'service-account-private-key',
                      'serviceAccountId': 'serviceaccount-e00ybpfwg84xtz6dd6',
                      'publicKeyId': 'publickey-e00gdw8z6bkh7b5agw',
                      'privateKeyFile': str(self.key),
                      'projectId': 'project-e00cydn2pr00f38xvq3j95',
                      'devlabId': 'devlab-e00mt1pp6rph9z4qyv'}
        self.config.write_text(json.dumps(self.value), encoding='utf-8')
        self.config.chmod(0o600)

    def test_explicit_config_accepts_ids_but_no_static_token(self):
        self.assertEqual(load_config(self.config), self.value)
        self.value['staticToken'] = 'FORBIDDEN_FIXTURE'
        self.config.write_text(json.dumps(self.value), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'SERVICE_ACCOUNT_CONFIG_REQUIRED'):
            load_config(self.config)

    def test_token_expiry_forces_synchronous_refresh(self):
        class SDK:
            expired = True
            def whoami(self, **kwargs):
                self.options = kwargs['auth_options']
                class Request:
                    def wait(inner):
                        self.expired = False
                return Request()
        sdk = SDK()
        self.assertEqual(renewal_probe(sdk, ('required', 'synchronous', 'timeout')),
                         'FORCED_REFRESH_SUCCEEDED')
        self.assertFalse(sdk.expired)
        self.assertEqual(sdk.options, {'required': 'true', 'synchronous': 'true', 'timeout': '5'})

    def test_authentication_and_permission_failures_stay_separate(self):
        class Status:
            def __init__(self, code):self.code = code
        class Error(Exception):
            def __init__(self, code):self.status = Status(code)
        self.assertEqual(error_category(Error(16)), '401_UNAUTHENTICATED')
        self.assertEqual(error_category(Error(7)), '403_PERMISSION_DENIED')
        class SDK:
            def whoami(self, **kwargs):
                class Request:
                    def wait(self):raise Error(16)
                return Request()
        with self.assertRaises(Error) as caught:
            renewal_probe(SDK(), ('required', 'synchronous', 'timeout'))
        self.assertEqual(error_category(caught.exception), '401_UNAUTHENTICATED')


if __name__ == '__main__':unittest.main()
