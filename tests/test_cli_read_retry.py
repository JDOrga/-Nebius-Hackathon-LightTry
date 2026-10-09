"""Bounded retries apply to transient reads, never to auth errors or mutations."""
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'cloud'))
import cli_bridge

class RetryTests(unittest.TestCase):
    settings={'cli_path':'SYNTHETIC','profile':'synthetic'}
    def test_classified_read_can_retry_once(self):
        responses=[subprocess.CompletedProcess([],52,'','rpc error: code = DeadlineExceeded'),
                   subprocess.CompletedProcess([],0,'{"state":"STOPPED"}','')]
        with patch.object(cli_bridge.subprocess,'run',side_effect=responses) as run:
            self.assertEqual(cli_bridge.run_cli(self.settings,['ai','devlab','get']),{'state':'STOPPED'})
            self.assertEqual(run.call_count,2)

    def test_uncertain_restart_is_never_retried(self):
        response=subprocess.CompletedProcess([],52,'','rpc error: code = DeadlineExceeded')
        with patch.object(cli_bridge.subprocess,'run',return_value=response) as run:
            with self.assertRaisesRegex(RuntimeError,'CLI_FAILED_EXIT_52'):
                cli_bridge.run_cli(self.settings,['ai','devlab','restart'],False)
            self.assertEqual(run.call_count,1)

    def test_auth_and_unknown_errors_do_not_retry(self):
        for code,error in [(7,'Unauthenticated'),(15,'PermissionDenied'),(12,'UNCLASSIFIED_SYNTHETIC')]:
            with patch.object(cli_bridge.subprocess,'run',return_value=subprocess.CompletedProcess([],code,'',error)) as run:
                with self.assertRaises(RuntimeError):cli_bridge.run_cli(self.settings,['ai','devlab','get'])
                self.assertEqual(run.call_count,1)

    def test_read_timeout_retry_shares_one_budget(self):
        with patch.object(cli_bridge.time,'monotonic',side_effect=[100,100,125]):
            with patch.object(cli_bridge.subprocess,'run',side_effect=[subprocess.TimeoutExpired('synthetic',25),subprocess.CompletedProcess([],0,'{}','')]) as run:
                self.assertEqual(cli_bridge.run_cli(self.settings,['ai','devlab','get']),{})
                self.assertEqual([c.kwargs['timeout'] for c in run.call_args_list],[25,10])

    def test_sequential_calls_share_operation_budget(self):
        with patch.object(cli_bridge.time, 'monotonic', side_effect=[100, 100, 112, 112, 124, 124, 136, 136]), \
                patch.object(cli_bridge.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '{}', '')) as run:
            for _ in range(3):
                cli_bridge.run_cli(self.settings, ['ai', 'devlab', 'get'], budget_end=135)
            with self.assertRaisesRegex(RuntimeError, 'BUDGET_EXHAUSTED'):
                cli_bridge.run_cli(self.settings, ['ai', 'devlab', 'get'], budget_end=135)
            self.assertEqual([c.kwargs['timeout'] for c in run.call_args_list], [25, 23, 11])

    def test_expired_restart_blocked_at_process_boundary(self):
        with patch.object(cli_bridge.time, 'time', return_value=101), \
                patch.object(cli_bridge.subprocess, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'ABSOLUTE_DEADLINE_REACHED'):
                cli_bridge.run_cli(self.settings, ['ai', 'devlab', 'restart'], False, not_after=100)
            run.assert_not_called()

    def test_restart_process_has_remaining_time_and_no_cli_retries(self):
        with patch.object(cli_bridge.time, 'time', return_value=100), \
                patch.object(cli_bridge.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, 'operation', '')) as run:
            cli_bridge.run_cli(self.settings, ['ai', 'devlab', 'restart'], False, not_after=102)
            self.assertEqual(run.call_args.kwargs['timeout'], 2)
            self.assertIn('--retries=0', run.call_args.args[0])

if __name__=='__main__':unittest.main()
