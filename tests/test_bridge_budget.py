"""Exercise the native bridge boundary and the guard with a hung synthetic read."""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PS = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'


class BridgeBudgetTests(unittest.TestCase):
    def test_hung_bridge_is_bounded_and_raw_output_is_suppressed(self):
        source = r'''param([string]$Common,[string]$Native,[string]$Executable)
. $Common
. $Native
$clock=[Diagnostics.Stopwatch]::StartNew()
try {
 Invoke-BridgeProcess $Executable @('-NoProfile','-Command',"[Console]::Error.WriteLine('PRIVATE_SYNTHETIC');Start-Sleep -Seconds 20") 1000 | Out-Null
 throw 'EXPECTED_TIMEOUT_MISSING'
} catch {
 if($_.Exception.Message -ne 'BRIDGE_PROCESS_BUDGET_OR_OUTPUT_FAILURE'){throw}
}
@{elapsed_ms=$clock.ElapsedMilliseconds;bounded=$true}|ConvertTo-Json -Compress
'''
        with tempfile.TemporaryDirectory() as temp:
            wrapper = Path(temp) / 'test.ps1'
            wrapper.write_text(source)
            result = subprocess.run([str(PS), '-NoProfile', '-File', str(wrapper),
                                     str(ROOT / 'cloud/Common.ps1'), str(ROOT / 'cloud/HostCapture.Native.ps1'), str(PS)],
                                    capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertLess(json.loads(result.stdout)['elapsed_ms'], 2500)
            self.assertNotIn('PRIVATE_SYNTHETIC', result.stdout + result.stderr)

    def test_slow_observation_cannot_occupy_stop_window(self):
        # Isolated copy replaces only the transport with local synthetic work.
        # Production guard timing, Observe budget and SubmitStop paths are retained.
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cloud = root / 'cloud'
            cloud.mkdir()
            for name in ('Common.ps1', 'RequestJson.ps1', 'HostCapture.Native.ps1', 'HostCapture.Native.cs'):
                shutil.copyfile(ROOT / 'cloud' / name, cloud / name)
            common = cloud / 'Common.ps1'
            common.write_text(common.read_text() + r'''
$script:ObservationCount=0
function Invoke-Bridge($Action,[int]$TimeoutMs) {
 $script:ObservationCount++
 if($script:ObservationCount -eq 1){
  Write-AtomicJson (Join-Path $run 'read-budget.json') @{milliseconds=$TimeoutMs}
  Invoke-BridgeProcess (Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0/powershell.exe') @('-NoProfile','-Command','Start-Sleep -Seconds 20') $TimeoutMs | Out-Null
 }
 $p=Join-Path $run 'simulated-cloud.json';$s=Get-Content $p -Raw|ConvertFrom-JsonUtc
 if($s.state -eq 'STOPPING'){$s.state='STOPPED';$s.instances=@();Write-AtomicJson $p $s}
 return @{id=$startup.devlab_id;state=$s.state;instances=$s.instances;project_ownership_verified=$true}
}
''')
            guard = (ROOT / 'cloud/TeaRunningGuard.ps1').read_text()
            guard = guard.replace('function Observe {\n if(!$offline){', 'function Observe {\n if($true){', 1)
            self.assertIn('function Observe {\n if($true){', guard)
            (cloud / 'TeaRunningGuard.ps1').write_text(guard)
            run = root / 'run'
            run.mkdir()
            now = datetime.now(timezone.utc)
            documents = {
                'startup.json': dict(offline=True, single_run=True, devlab_id='devlab-synthetic',
                                     budget_usd_including_tax=1, approval_reference='SYNTHETIC', created_utc=now.isoformat(),
                                     absolute_deadline_utc=(now + timedelta(seconds=4)).isoformat()),
                'live-settings.json': dict(cloud_stop_enabled=True),
                'simulated-cloud.json': dict(state='STARTING', instances=[], verify_reads=0, stop_requests=0),
                'independent-stopped-release.json': dict(state='STOPPED', instances=[]),
            }
            for name, value in documents.items():
                (run / name).write_text(json.dumps(value))
            result = subprocess.run([str(PS), '-NoProfile', '-File', str(cloud / 'TeaRunningGuard.ps1'),
                                     '-RunDirectory', str(run), '-Execute'], capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            budget = json.loads((run / 'read-budget.json').read_text(encoding='utf-8-sig'))
            self.assertLessEqual(budget['milliseconds'], 4000)
            self.assertGreater(json.loads((run / 'simulated-cloud.json').read_text(encoding='utf-8-sig'))['stop_requests'], 0)
            self.assertTrue(json.loads((run / 'heartbeat.json').read_text(encoding='utf-8-sig'))['stopped_verified'])
            self.assertFalse((run / 'running-confirmation.json').exists())


if __name__ == '__main__':
    unittest.main()
