"""New tests, failed dependencies and timeouts must remain visible in reports."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import selftest


class RunnerTests(unittest.TestCase):
    def test_discovers_new_modules_and_scripts_without_importing_them(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'tests').mkdir()
            (root / 'prototype').mkdir()
            (root / 'tests/test_new.py').write_text('import unittest\nraise RuntimeError("do not import")\n')
            (root / 'prototype/test_script.py').write_text('raise RuntimeError("do not execute")\n')
            commands = dict(selftest.discover_commands(root))
            self.assertEqual(commands['prototype-test_script'], ['prototype/test_script.py'])
            self.assertEqual(commands['tests-test_new'][-3:], ['-p', 'test_new.py', '-v'])

    def test_timeout_logs_partial_output_and_later_group_runs(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'report.json'
            responses = [subprocess.TimeoutExpired('test', 240, output=b'partial output', stderr=b'partial error'),
                         subprocess.CompletedProcess([], 0, 'next group ran', '')]
            with patch.object(sys, 'argv', ['selftest', '--out', str(out)]), \
                    patch.object(selftest, 'dependency_issues', return_value=[]), \
                    patch.object(selftest, 'discover_commands', return_value=[('slow', ['slow.py']), ('next', ['next.py'])]), \
                    patch.object(selftest.subprocess, 'run', side_effect=responses), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(selftest.main(), 1)
            report = json.loads(out.read_text())
            self.assertFalse(report['passed'])
            self.assertEqual([g['status'] for g in report['groups']], ['timeout', 'passed'])
            self.assertIn('partial output', (out.parent / 'slow.log').read_text())

    def test_missing_dependency_replaces_stale_success_without_running_tests(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'report.json'
            out.write_text('{"passed": true}')
            with patch.object(sys, 'argv', ['selftest', '--out', str(out)]), \
                    patch.object(selftest, 'dependency_issues', return_value=['Missing numpy']), \
                    patch.object(selftest.subprocess, 'run') as run, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(selftest.main(), 1)
                run.assert_not_called()
            report = json.loads(out.read_text())
            self.assertEqual(report['status'], 'dependency_failure')
            self.assertFalse(report['passed'])


if __name__ == '__main__':
    unittest.main()
