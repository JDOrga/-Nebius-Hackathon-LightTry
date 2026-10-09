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
    def test_categories_context_and_success_failure_use_same_safe_schema(self):
        shells=[Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe']
        if shutil.which('pwsh'):shells.append(Path(shutil.which('pwsh')))
        cases=[
            ('auth','user@192.0.2.10: Permission denied (publickey).','AUTHENTICATION_REJECTED',255),
            ('host','WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!','HOST_KEY_CHANGED',255),
            ('timeout','ssh: connect to host 192.0.2.10 port 22: Connection timed out','CONNECTION_TIMEOUT',255),
            ('reset','kex_exchange_identification: read: Connection reset by peer','CONNECTION_RESET',255),
            ('unknown','PRIVATE_MUST_NOT_BE_LOGGED unknown arbitrary diagnostic','UNCLASSIFIED_STDERR',255),
            ('success','',None,0),
        ]
        source=r'''param([string]$Common,[string]$Cases,[string]$Directory,[string]$Executable)
. $Common
$all=Get-Content -LiteralPath $Cases -Raw|ConvertFrom-JsonUtc
foreach($case in $all){
 $script:RemoteDeadline=[DateTimeOffset]::UtcNow.AddSeconds(30)
 $encoded=ConvertTo-Base64 ([string]$case.stderr)
 $command="[Console]::Error.WriteLine([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('$encoded')));[Console]::WriteLine('PRIVATE_STDOUT_MUST_NOT_BE_LOGGED');exit "+$case.exit
 $record=Join-Path $Directory ($case.name+'.json')
 $ctx=@{operation='inspect';connection_arguments_sha256=('a'*64);password='PRIVATE_CTX';target_identity_sha256='PRIVATE_INVALID_HASH'}
 try {Invoke-NativeSshCommand @('-NoProfile','-Command') $command $record $Executable $ctx|Out-Null;if($case.exit -ne 0){throw 'EXPECTED_FAILURE_MISSING'}}
 catch {if($case.exit -eq 0 -or $_.Exception.Message -ne 'BOUNDED_TRANSFER_FAILED_OUTPUT_NOT_ACCEPTED'){throw}}
}
'''
        with tempfile.TemporaryDirectory(prefix='safe native categories ') as d:
            base=Path(d); wrapper=base/'classify.ps1'; wrapper.write_text(source,encoding='utf-8')
            path=base/'cases.json'; path.write_text(json.dumps([{'name':n,'stderr':s,'exit':e} for n,s,c,e in cases]))
            for i,shell in enumerate(shells):
                folder=base/str(i);folder.mkdir()
                p=subprocess.run([str(shell),'-NoProfile','-File',str(wrapper),str(ROOT/'cloud/Common.ps1'),str(path),str(folder),str(shells[0])],capture_output=True,timeout=45)
                self.assertEqual(p.returncode,0,p.stderr)
                for name,stderr,category,code in cases:
                    with self.subTest(shell=str(shell),category=name):
                        text=(folder/(name+'.json')).read_text(encoding='utf-8-sig'); record=json.loads(text)
                        self.assertEqual(record['schema_version'],2)
                        self.assertEqual(record['exit_code'],code)
                        self.assertEqual(record['stderr_categories'],[category] if category else [])
                        self.assertEqual(record['invocation']['context'],{'operation':'inspect','connection_arguments_sha256':'a'*64})
                        self.assertTrue(record['output_complete']);self.assertTrue(record['process_exited'])
                        self.assertFalse(record['raw_output_saved']);self.assertFalse(record['stderr_saved'])
                        self.assertGreater(record['invocation']['argument_characters'],0)
                        self.assertEqual(len(record['invocation']['arguments_sha256']),64)
                        self.assertEqual(record['phase'],'native_completed')
                        self.assertNotIn('PRIVATE_',text);self.assertNotIn('192.0.2.10',text)
                        attempts=list((folder/'transport-attempts').glob(name+'-*.json'))
                        self.assertEqual(len(attempts),1)
                        self.assertEqual(json.loads(attempts[0].read_text(encoding='utf-8-sig')),record)

    def test_diagnostic_write_failure_does_not_mask_native_failure(self):
        shell=Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
        source=r'''param([string]$Common,[string]$Executable,[string]$Record)
. $Common
$script:RemoteDeadline=[DateTimeOffset]::UtcNow.AddSeconds(30)
# Simulate an unwritable completion receipt after the prepared receipt succeeds.
$script:count=0
function Write-AtomicJson([string]$Path,$Object){$script:count++;if($script:count -ge 2){throw 'SYNTHETIC_LOG_IO_FAILURE'}}
try{Invoke-NativeSshCommand @('-NoProfile','-Command') 'exit 255' $Record $Executable|Out-Null;throw 'EXPECTED_FAILURE_MISSING'}
catch{
 if($_.Exception.Message -ne 'BOUNDED_TRANSFER_FAILED_OUTPUT_NOT_ACCEPTED'){throw}
 if(!$_.Exception.Data['native_summary'].diagnostic_write_failed -or $_.Exception.Data['native_summary'].exit_code -ne 255){throw 'NATIVE_FAILURE_METADATA_LOST'}
}
'''
        with tempfile.TemporaryDirectory() as d:
            wrapper=Path(d)/'write_failure.ps1';wrapper.write_text(source)
            p=subprocess.run([str(shell),'-NoProfile','-File',str(wrapper),str(ROOT/'cloud/Common.ps1'),str(shell),str(Path(d)/'synthetic.json')],capture_output=True,timeout=35)
            self.assertEqual(p.returncode,0,p.stderr)

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
