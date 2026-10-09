"""Restart must revalidate a changing guard after a slow status read."""
import contextlib
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'cloud'))
import live_session_running as session


class RestartBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.run = Path(self.temp.name)
        self.now = datetime(2030, 1, 1, tzinfo=timezone.utc)
        self.settings = dict(devlab_id='devlab-synthetic', project_id='project-synthetic', cloud_stop_enabled=True)
        self.launch = dict(single_run=True, offline=False, budget_usd_including_tax=1,
                           approval_reference='SYNTHETIC',
                           absolute_deadline_utc='2030-01-01T00:00:10.0000000Z',
                           timing_policy='RUNNING_ANCHORED_18_25_27')
        self.beat = dict(utc='2030-01-01T00:00:00.0000000Z', status='ready_waiting_start',
                         sleep_held=True, running_confirmed=False)
        self.write('startup.json', self.launch)
        self.write('live-settings.json', self.settings)
        self.write('heartbeat.json', self.beat)

    def write(self, name, value):
        (self.run / name).write_text(json.dumps(value))

    def invoke(self, during_read=lambda: None):
        def read(*args, **kwargs):
            during_read()
            return dict(metadata=dict(id='devlab-synthetic', parent_id='project-synthetic'),
                        status=dict(state='STOPPED', instances=[]))
        argv = ['session', 'restart', '--execute', '--settings', str(self.run / 'live-settings.json'),
                '--run-directory', str(self.run)]
        with patch.object(sys, 'argv', argv), patch.object(session, 'utc', side_effect=lambda: self.now), \
                patch.object(session.bridge, 'run_cli', side_effect=read), \
                patch.object(session, 'mutate') as mutation, contextlib.redirect_stdout(io.StringIO()):
            try:
                session.main()
            except ValueError:
                mutation.assert_not_called()
                raise
            return mutation

    def test_query_crossing_deadline_never_restarts(self):
        with self.assertRaisesRegex(ValueError, 'ABSOLUTE_DEADLINE_REACHED'):
            self.invoke(lambda: setattr(self, 'now', self.now + timedelta(seconds=11)))
        self.assertFalse((self.run / 'restart-attempt.json').exists())

    def test_guard_revoked_during_query_never_restarts(self):
        with self.assertRaisesRegex(ValueError, 'LIVE_GUARD_NOT_READY'):
            self.invoke(lambda: self.write('live-settings.json', dict(self.settings, cloud_stop_enabled=False)))

    def test_cancel_during_query_never_restarts(self):
        with self.assertRaisesRegex(ValueError, 'GUARD_STOP_ALREADY_REQUESTED'):
            self.invoke(lambda: self.write('cancel.json', {}))

    def test_guard_status_change_during_query_never_restarts(self):
        with self.assertRaisesRegex(ValueError, 'LIVE_GUARD_NOT_READY'):
            self.invoke(lambda: self.write('heartbeat.json', dict(self.beat, status='stopping')))

    def test_valid_seven_digit_utc_is_single_use(self):
        mutation = self.invoke()
        mutation.assert_called_once_with(self.settings, 'restart',
                                         not_after=(self.now + timedelta(seconds=10)).timestamp())
        with self.assertRaises(FileExistsError):
            self.invoke()


if __name__ == '__main__':
    unittest.main()
