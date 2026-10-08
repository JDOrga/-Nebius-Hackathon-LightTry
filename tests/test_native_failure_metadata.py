"""Synthetic native failure keeps typed diagnostics and suppresses raw stderr."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]

class NativeMetadataTests(unittest.TestCase):
    def test_error_metadata_on_ps5_and_ps7(self):
        shells=[Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe']
        if shutil.which('pwsh'):shells.append(Path(shutil.which('pwsh')))
        source=r'''param([string]$Common,[string]$Record,[string]$Executable)
. $Common
$script:RemoteDeadline=[DateTimeOffset]::UtcNow.AddSeconds(30)
try{
 Invoke-NativeSshCommand @('-NoProfile','-Command') "[Console]::Error.WriteLine('CONTAINER_STAGE_FAILED_EXIT_1');[Console]::Error.WriteLine('secret=PRIVATE_MUST_NOT_BE_LOGGED');[Console]::Error.WriteLine('UNKNOWN_UPPERCASE_OUTPUT');exit 3" $Record $Executable | Out-Null
 throw 'EXPECTED_FAILURE_MISSING'
}catch{
 if($_.Exception.Message -ne 'BOUNDED_TRANSFER_FAILED_OUTPUT_NOT_ACCEPTED'){throw}
}
'''
        with tempfile.TemporaryDirectory(prefix='native failure with spaces ') as d:
            wrapper=Path(d)/'synthetic failure.ps1';wrapper.write_text(source,encoding='utf-8')
            for i,shell in enumerate(shells):
                record=Path(d)/('record-'+str(i)+'.json')
                p=subprocess.run([str(shell),'-NoProfile','-File',str(wrapper),str(ROOT/'cloud/Common.ps1'),str(record),str(shells[0])],capture_output=True,timeout=35)
                self.assertEqual(p.returncode,0,p.stderr)
                text=record.read_text(encoding='utf-8-sig');value=json.loads(text)
                self.assertEqual(value['exit_code'],3)
                self.assertTrue(value['output_complete'])
                self.assertFalse(value['raw_output_saved'])
                self.assertEqual(value['public_failure_labels'],['CONTAINER_STAGE_FAILED_EXIT_1'])
                self.assertNotIn('PRIVATE_MUST_NOT_BE_LOGGED',text)
                self.assertNotIn('UNKNOWN_UPPERCASE_OUTPUT',text)

if __name__=='__main__':unittest.main()
