"""End-to-end Windows PS5.1 offline tests; synthetic public output only."""
import base64, hashlib, importlib.util, json, shutil, time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('fixture',ROOT/'test_host_capture.py')
f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)

def prepare():
    f.RESULTS.mkdir(exist_ok=False)
    (f.RESULTS/'scanner.cs').write_text(f.SCANNER,encoding='ascii')
    build=f.RESULTS/'build.ps1'
    build.write_text('Add-Type -Path $args[0] -OutputAssembly $args[1] -OutputType ConsoleApplication',encoding='ascii')
    result=f.ps(build,[f.RESULTS/'scanner.cs',f.RESULTS/'synthetic-keyscan.exe']);assert result.returncode==0,result.stderr

def check_failure(run,code,events,error,stage,category):
    assert code==1 and error['category']==category and error['stage']==stage,(code,error)
    assert error['stop_signal_written'] and json.loads((run/'complete.json').read_text())['stop_required']
    assert not (run/'host-candidate.json').exists() and not (run/'host-key-candidate.txt').exists()
    event=next(v for v in events if v.get('stage')==stage and v.get('event')=='end')
    data=event['details']
    assert data['truncated'] and not data['output_complete'] and data['exit_code']==0,data
    assert not data['timed_out'] and not data['pipe_not_closed'] and not data['cleanup_incomplete'],data
    return data

def main():
    start=time.monotonic();prepare();rows=[]
    run,config=f.fixture('normal-api-json-large-stderr')
    api=config.parent/'synthetic API.ps1'
    text=api.read_text();text=text.replace("$vm='computeinstance-synthetic'", "[Console]::Error.WriteLine(('E'*9000))\n$vm='computeinstance-synthetic'")
    api.write_text(text,encoding='ascii')
    code,events,error,elapsed=f.execute(run,config)
    data=check_failure(run,code,events,error,'api_locate','API_OUTPUT_LIMIT_EXCEEDED')
    assert 'api_located' not in data and not any(v.get('stage')=='native_keyscan' for v in events)
    assert (config.parent/'api-index.txt').read_text()=='1'
    rows.append(dict(name='normal API JSON + oversized stderr',passed=True,category=error['category'],
      elapsed_seconds=elapsed,parsed_or_used=False,candidate_published=False,complete_signal=True))

    run,config=f.fixture('normal-fingerprint-large-stderr')
    # Override only the local fingerprint executable path in an isolated test
    # copy, so production needs no test parameters or authentication changes.
    entry=run.parent/'isolated test entry';entry.mkdir()
    for name in ['HostCapture.Native.ps1','HostCapture.Native.cs','host_capture_api.py','RequestJson.ps1']:
        shutil.copyfile(f.SCRIPTS/name,entry/name)
    production=(f.SCRIPTS/'Capture-TeaHost.ps1').read_text(encoding='utf-8-sig')
    old="$keygen=Join-Path $env:SystemRoot 'System32/OpenSSH/ssh-keygen.exe'"
    assert production.count(old)==2
    (entry/'Capture-TeaHost.ps1').write_text(production.replace(old,"$keygen=Join-Path $PSScriptRoot 'synthetic-keygen.exe'",1),encoding='utf-8')
    blob=base64.b64decode((config.parent/'public-line.txt').read_text().split()[2])
    fingerprint=base64.b64encode(hashlib.sha256(blob).digest()).decode().rstrip('=')
    cs='''using System;using System.IO;public class SyntheticFingerprint {
public static int Main(string[] a){
if(a.Length!=4||a[0]!="-lf"||!File.Exists(a[1])||a[2]!="-E"||a[3]!="sha256")return 99;
Console.WriteLine("256 SHA256:FINGERPRINT 192.0.2.10 (ED25519)");
Console.Error.WriteLine(new String('E',9000));return 0;}}'''.replace('FINGERPRINT',fingerprint)
    (entry/'synthetic-keygen.cs').write_text(cs,encoding='ascii')
    build=entry/'build.ps1';build.write_text('Add-Type -Path $args[0] -OutputAssembly $args[1] -OutputType ConsoleApplication',encoding='ascii')
    result=f.ps(build,[entry/'synthetic-keygen.cs',entry/'synthetic-keygen.exe']);assert result.returncode==0,result.stderr
    began=time.monotonic()
    result=f.ps(entry/'Capture-TeaHost.ps1',['-RunDirectory',run,'-Execute','-Offline','-FixturePath',config])
    (run/'process.stdout.txt').write_bytes(result.stdout);(run/'process.stderr.txt').write_bytes(result.stderr)
    events=[json.loads(v) for v in (run/'host-capture-events.jsonl').read_text().splitlines()]
    error=json.loads((run/'host-capture-error.json').read_text())
    data=check_failure(run,result.returncode,events,error,'fingerprint','FINGERPRINT_OUTPUT_LIMIT_EXCEEDED')
    assert 'public_fingerprint' not in data
    assert not any(v.get('stage')=='publish_candidate' for v in events)
    assert (config.parent/'api-index.txt').read_text()=='2'
    rows.append(dict(name='normal fingerprint + oversized stderr',passed=True,category=error['category'],
      elapsed_seconds=time.monotonic()-began,parsed_or_used=False,candidate_published=False,complete_signal=True,
      fixture='isolated entry path override; production code has no additional test switch'))

    # Preserve existing timeout/readiness retry behavior, not just hard rejection.
    for name,api,scan,expected in [
      ('scan-timeout-retry',['success'],['timeout','success'],'SCAN_TIMEOUT'),
      ('api-timeout-label-retry',['API_TIMEOUT','success'],['success'],'API_TIMEOUT')]:
        run,config=f.fixture(name,api,scan)
        code,events,error,elapsed=f.execute(run,config)
        assert code==0 and error is None and (run/'host-candidate.json').exists(),error
        assert not (run/'complete.json').exists()
        if expected=='SCAN_TIMEOUT':
            assert any(v.get('stage')=='native_keyscan' and v.get('event')=='end' and v['details']['timed_out'] for v in events)
            assert (config.parent/'scan-index.txt').read_text()=='2'
        else:
            assert any(v.get('stage')=='api_locate' and v.get('event')=='end' and v['details'].get('category')=='API_TIMEOUT' for v in events)
        rows.append(dict(name=name,passed=True,elapsed_seconds=elapsed,existing_retry_behavior_preserved=True))
    result=dict(passed=True,test_count=len(rows),tests=rows,elapsed_seconds=time.monotonic()-start,
      real_windows_PS51=True,cloud_API_calls=0,remote_scans=0,SSH_connections=0,auth_changes=0,trust_changes=0)
    (f.RESULTS/'output-complete-tests.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
