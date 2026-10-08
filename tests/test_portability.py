"""Synthetic cross-machine contracts; no cloud, SSH, credential content or login."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import local_config

def shells():
    ps5=Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
    return [ps5]+([Path(shutil.which('pwsh'))] if shutil.which('pwsh') else [])

class PortabilityTests(unittest.TestCase):
    def test_local_config_paths_with_spaces_and_no_credential_reads(self):
        with tempfile.TemporaryDirectory(prefix='configuration with spaces ') as d:
            base=Path(d)
            cfg={k:'SYNTHETIC' for k in local_config.REQUIRED}
            for k in ('key_path','known_hosts_path','auth_config_path'):
                p=base/(k+' with spaces');p.touch();cfg[k]=str(p)
            Path(cfg['key_path']+'.pub').touch()
            cfg.update(data_dir=d,upstream_repo=d)
            # Validator must use metadata only, even when all credential paths exist.
            with patch.object(Path,'read_text',side_effect=AssertionError('credential read forbidden')):
                self.assertEqual(local_config.validate(cfg),[])
            cfg['auth_config_path']=str(base/'absent auth')
            issues=local_config.validate(cfg)
            self.assertTrue(any(x['field']=='auth_config_path' for x in issues))

    def test_missing_configuration_is_offline_failure(self):
        p=subprocess.run([sys.executable,'-B',str(ROOT/'scripts/local_config.py'),'--config',str(ROOT/'.local/absent.json')],capture_output=True,text=True,timeout=10)
        self.assertEqual(p.returncode,1)
        report=json.loads(p.stdout);self.assertEqual(report['cloud_calls'],0)
        self.assertIn('NO_AUTO_LOGIN',report['issues'][0]['category'])

    def test_utc_nested_request_roundtrip_on_ps5_and_ps7(self):
        value={'deadline_utc':'2030-01-02T03:04:05Z','nested':{'launched_utc':'2030-01-02T03:04:05.123456+00:00'},'list':['2030-01-02T03:04:05Z']}
        with tempfile.TemporaryDirectory(prefix='UTC request with spaces ') as d:
            q=Path(d)/'request with spaces.json';q.write_text(json.dumps(value))
            wrapper=Path(d)/'serialize.ps1'
            wrapper.write_text("param([string]$Module,[string]$Request)\n. $Module\n$v=Get-Content -LiteralPath $Request -Raw | ConvertFrom-JsonUtc\n$v|ConvertTo-Json -Depth 12 -Compress\n")
            for shell in shells():
                p=subprocess.run([str(shell),'-NoProfile','-File',str(wrapper),str(ROOT/'cloud/RequestJson.ps1'),str(q)],capture_output=True,timeout=15)
                self.assertEqual(p.returncode,0,p.stderr)
                self.assertEqual(json.loads(p.stdout.decode('utf-8-sig')),value)

    def test_default_cloud_commands_are_plans_without_configuration(self):
        entries={'Invoke-Cloud.ps1':[],'Status.ps1':[],'Start-TeaRunningGuard.ps1':[], 'TeaRunningGuard.ps1':['-RunDirectory','never created'],
                 'Capture-TeaHost.ps1':['-RunDirectory','never created'], 'Wait-CaptureTeaHost.ps1':['-RunDirectory','never created'],
                 'Invoke-ScaleRemote.ps1':['-RunDirectory','never created','-Operation','probe'],
                 'Confirm-RunningStopped.ps1':['-RunDirectory','never created'],
                 'Confirm-TeaHost.ps1':['-RunDirectory','never created','-ExpectedVm','synthetic','-ExpectedIp','192.0.2.10','-ExpectedFingerprint','synthetic']}
        for shell in shells():
            for name,args in entries.items():
                p=subprocess.run([str(shell),'-NoProfile','-File',str(ROOT/'cloud'/name),*args],capture_output=True,timeout=15)
                self.assertEqual(p.returncode,0,(name,p.stderr))
                v=json.loads(p.stdout.decode('utf-8-sig'))
                self.assertEqual(v.get('cloud_calls',v.get('API_calls')),0)

    def test_missing_authentication_never_attempts_login(self):
        # Explicit read-only status still stops locally before any CLI if config is absent.
        with tempfile.TemporaryDirectory(prefix='missing configuration ') as d:
            env=dict(os.environ,NEBIUS_LOCAL_CONFIG=str(Path(d)/'absent.json'))
            p=subprocess.run([str(shells()[0]),'-NoProfile','-File',str(ROOT/'cloud/Invoke-Cloud.ps1'),'-Action','Status','-Execute'],env=env,capture_output=True,timeout=10)
            self.assertNotEqual(p.returncode,0)
            self.assertIn(b'NO_AUTO_LOGIN',p.stderr)

    def test_inference_import_does_not_spawn_or_download(self):
        sys.path.insert(0,str(ROOT/'cloud'))
        import importlib
        with patch('subprocess.run',side_effect=AssertionError('external process at import')), patch('subprocess.Popen',side_effect=AssertionError('process at import')), patch('urllib.request.urlopen',side_effect=AssertionError('network at import')):
            for name in ('weights','run_experiment','validate_outputs','preflight','cli_bridge','host_capture_api','live_session_running'):
                importlib.import_module(name)

if __name__=='__main__':unittest.main()
