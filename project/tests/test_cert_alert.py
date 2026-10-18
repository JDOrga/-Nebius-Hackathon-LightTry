"""Offline certificate email alert checks; SMTP is always replaced by a stub."""
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

SOURCE=Path(__file__).resolve().parents[2]/'deploy/cert_alert.py'
SPEC=importlib.util.spec_from_file_location('cert_alert',SOURCE)
alert=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(alert)


class CertificateAlertTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name)
        self.config={'schemaVersion':1,'recipient':'1928692778@qq.com',
                     'smtpUser':'1928692778@qq.com','smtpSecretFile':str(root/'auth.txt'),
                     'stateFile':str(root/'state.json'),'expectedIp':'47.238.73.99',
                     'warningHours':72}
        self.path=root/'config.json'
        self.path.write_text(json.dumps(self.config),encoding='utf-8');self.path.chmod(0o600)
        self.sent=[]
        self.mailer=lambda config,subject,body:self.sent.append((subject,body))

    def test_explicit_private_recipient_and_tls_target(self):
        self.assertEqual(alert.load_config(self.path),self.config)
        value=dict(self.config,smtpUser='other@qq.com')
        self.path.write_text(json.dumps(value),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'CERT_ALERT_TARGET_INVALID'):alert.load_config(self.path)
        self.path.write_text(json.dumps(self.config),encoding='utf-8')
        if os.name!='nt':
            self.path.chmod(0o644)
            with self.assertRaisesRegex(ValueError,'PRIVATE_FILE_PERMISSIONS_REQUIRED'):alert.load_config(self.path)

    def test_healthy_expiry_and_failed_renewal_without_provider_calls(self):
        now=1000000
        self.assertEqual(alert.run(self.config,'check-only',now=now,expiry=now+5*86400,service='success'),
                         'HEALTHY')
        self.assertEqual(alert.run(self.config,'check-only',now=now,expiry=now+3600,service='success'),
                         'CERT_EXPIRES_SOON')
        self.assertEqual(alert.run(self.config,'check-only',now=now,expiry=now+5*86400,service='exit-code'),
                         'RENEWAL_SERVICE_exit-code')
        self.assertEqual(self.sent,[])

    def test_alert_dedupes_and_recovers_without_secret_in_state(self):
        now=1000000
        options=dict(now=now,expiry=now+3600,service='success',mailer=self.mailer)
        self.assertEqual(alert.run(self.config,'run',**options),'ALERT_SENT')
        self.assertEqual(alert.run(self.config,'run',**options),'ALERT_ALREADY_SENT')
        self.assertEqual(len(self.sent),1)
        self.assertIn('CERT_EXPIRES_SOON',self.sent[0][0])
        saved=Path(self.config['stateFile']).read_text(encoding='utf-8')
        self.assertNotIn('1928692778',saved)
        self.assertEqual(alert.run(self.config,'run',now=now+10,expiry=now+5*86400,
                                   service='success',mailer=self.mailer),'HEALTHY')
        self.assertEqual(alert.run(self.config,'run',now=now+20,expiry=now+3600,
                                   service='success',mailer=self.mailer),'ALERT_SENT')
        self.assertEqual(len(self.sent),2)

    def test_test_email_is_explicit_and_no_health_gate(self):
        self.assertEqual(alert.run(self.config,'test-email',mailer=self.mailer),'TEST_EMAIL_SENT')
        self.assertEqual(len(self.sent),1)
        self.assertIn('测试',self.sent[0][0])


if __name__=='__main__':unittest.main()
