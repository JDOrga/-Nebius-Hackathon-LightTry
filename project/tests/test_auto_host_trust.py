"""Guard-owned first-contact trust; no provider, SSH, or model calls."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'project'))
from guard_runtime import cpu_guard_step
from gpu_bootstrap import auto_host_trust_enabled


class AutoHostTrustTests(unittest.TestCase):
    def test_private_owner_risk_opt_in_is_exact(self):
        self.assertFalse(auto_host_trust_enabled({'bootstrap': {}}))
        self.assertTrue(auto_host_trust_enabled({'bootstrap': {}, 'autoHostTrust': {
            'enabled': True, 'operatorAcceptsFirstContactMitmRisk': True}}))
        for setting in (True, {'enabled': True}, {'enabled': True,
                'operatorAcceptsFirstContactMitmRisk': False}):
            with self.subTest(setting=setting), self.assertRaisesRegex(ValueError,
                    'EXPLICIT_FIRST_CONTACT_RISK_ACCEPTANCE_REQUIRED'):
                auto_host_trust_enabled({'bootstrap': {}, 'autoHostTrust': setting})
        with self.assertRaisesRegex(ValueError,'EXPLICIT_FIRST_CONTACT_RISK_ACCEPTANCE_REQUIRED'):
            auto_host_trust_enabled({'autoHostTrust': {
                'enabled': True, 'operatorAcceptsFirstContactMitmRisk': True}})

    def fixture(self, enabled=True):
        sid = 'a' * 32
        host = {'vmId': 'VM_FIXTURE', 'ip': '203.0.113.7', 'sshUser': 'nebius'}
        current = {'sessionId': sid, 'state': 'LOADING', 'hostIdentity': host,
                   'hostConfirmed': False, 'verifiedStopped': False, 'stopSent': False}
        confirmed = {**current, 'hostConfirmed': True, 'hostTrustMethod': 'guard-tofu'}
        guard = Mock()
        guard.latest.return_value = {'sessionId': sid}
        guard.get.return_value = current
        guard.poll.return_value = current
        guard.confirm_host.return_value = confirmed
        bootstrap = Mock()
        bootstrap.public.return_value = {'canConfirm': True, 'sessionId': sid,
            'hostIdentity': host, 'fingerprint': 'SHA256:FIXTURE'}
        control = SimpleNamespace(refresh_scope=Mock(), sessions=guard,
            bootstrap=bootstrap, auto_host_trust=enabled)
        return sid, host, current, confirmed, guard, bootstrap, control

    def test_owner_opt_in_auto_pins_before_deployment(self):
        sid, host, _, confirmed, guard, bootstrap, control = self.fixture()
        cpu_guard_step(control)
        bootstrap.confirm.assert_called_once_with(sid, host, 'SHA256:FIXTURE')
        guard.confirm_host.assert_called_once_with(sid, host, trust_method='guard-tofu')
        bootstrap.step.assert_called_once_with(confirmed)
        guard.request_stop.assert_not_called()

    def test_without_owner_opt_in_never_auto_accepts(self):
        _, _, current, _, guard, bootstrap, control = self.fixture(False)
        cpu_guard_step(control)
        bootstrap.confirm.assert_not_called()
        guard.confirm_host.assert_not_called()
        bootstrap.step.assert_called_once_with(current)

    def test_no_candidate_only_starts_one_capture_step(self):
        _, _, current, _, guard, bootstrap, control = self.fixture()
        bootstrap.public.return_value = {'canConfirm': False, 'stage': 'pending'}
        cpu_guard_step(control)
        bootstrap.confirm.assert_not_called()
        guard.confirm_host.assert_not_called()
        bootstrap.step.assert_called_once_with(current)
        guard.poll.assert_called_once()

    def test_candidate_bound_to_other_host_stops_before_pin(self):
        sid, _, _, _, guard, bootstrap, control = self.fixture()
        bootstrap.public.return_value['hostIdentity'] = {'vmId': 'OTHER'}
        cpu_guard_step(control)
        bootstrap.confirm.assert_not_called()
        guard.confirm_host.assert_not_called()
        guard.request_stop.assert_called_once_with(sid, 'AUTO_HOST_TRUST_FAILED')
        bootstrap.step.assert_not_called()

    def test_unbindable_captured_key_stops_without_waiting_for_user(self):
        sid, _, _, _, guard, bootstrap, control = self.fixture()
        bootstrap.public.return_value = {'canConfirm': False, 'stage': 'awaiting_host_confirmation'}
        cpu_guard_step(control)
        bootstrap.confirm.assert_not_called()
        guard.request_stop.assert_called_once_with(sid, 'AUTO_HOST_TRUST_FAILED')
        bootstrap.step.assert_not_called()

    def test_pin_failure_stops_instead_of_deploying(self):
        sid, _, _, _, guard, bootstrap, control = self.fixture()
        bootstrap.confirm.side_effect = ValueError('SSH_PIN_CHANGED')
        cpu_guard_step(control)
        guard.confirm_host.assert_not_called()
        guard.request_stop.assert_called_once_with(sid, 'AUTO_HOST_TRUST_FAILED')
        bootstrap.step.assert_not_called()
        guard.fallback.publish.assert_called_once_with(None)


if __name__ == '__main__':
    unittest.main()
