"""Offline integration: real Windows PowerShell 5.1 -> synthetic native exe.
Never calls cloud APIs, ssh, ssh-keyscan or modifies trust/authentication.
Only ssh-keygen -lf on synthetic public data is used for local fingerprint parsing.
"""
import base64, hashlib, json, os, shutil, struct, subprocess, sys, time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
SCRIPTS = PROJECT / 'cloud'
PS = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
import tempfile
RESULTS = Path(tempfile.mkdtemp(prefix='capture fixtures with spaces ')) / 'results'

SCANNER = r'''
using System; using System.IO; using System.Reflection; using System.Threading;
public class SyntheticKeyscan {
 public static int Main(string[] args) {
  string root=Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);
  File.AppendAllText(Path.Combine(root,"arguments.txt"),String.Join("|",args)+"\n");
  if(args.Length!=5||args[0]!="-T"||args[1]!="5"||args[2]!="-t"||args[3]!="ed25519"||args[4]!="192.0.2.10")return 99;
  string index=Path.Combine(root,"scan-index.txt"); int i=File.Exists(index)?Int32.Parse(File.ReadAllText(index)):0;
  File.WriteAllText(index,(i+1).ToString()); string[] modes=File.ReadAllLines(Path.Combine(root,"scan-modes.txt"));
  string mode=modes[Math.Min(i,modes.Length-1)];
  if(mode=="timeout") {Thread.Sleep(10000);return 0;}
  if(mode=="empty")return 0;
  if(mode=="nonzero") {Console.Error.WriteLine("192.0.2.10: Connection refused");return 9;}
  if(mode=="invalid") {Console.WriteLine("192.0.2.10 ssh-ed25519 AAAA");return 0;}
  if(mode=="redact") {Console.Error.WriteLine("TOKEN_SHOULD_NEVER_APPEAR secret=password");Console.WriteLine("private-key-secret");return 1;}
  Console.Error.WriteLine("# 192.0.2.10:22 SSH-2.0-Synthetic_1.0");
  Console.WriteLine(File.ReadAllText(Path.Combine(root,"public-line.txt")).Trim());return 0;
 }
}
'''
API = r'''
param([string]$FixturePath)
$ErrorActionPreference='Stop'
$config=Get-Content -LiteralPath $FixturePath -Raw | ConvertFrom-Json
$root=Split-Path $FixturePath
$index=Join-Path $root 'api-index.txt'
$i=0;if(Test-Path $index){$i=[int](Get-Content $index -Raw)}
[IO.File]::WriteAllText($index,[string]($i+1))
$mode=$config.api_modes[[Math]::Min($i,$config.api_modes.Count-1)]
if($mode -eq 'invalidjson'){Write-Output 'NOT_JSON';exit 2}
if($mode -eq 'badfields'){@{ok=$true;target=@{vm_id='missing-identity-fields'}}|ConvertTo-Json -Compress;exit 0}
if($mode -eq 'stderr') {[Console]::Error.WriteLine('token=PRIVATE_MUST_NOT_BE_LOGGED');exit 7}
if($mode -ne 'success' -and $mode -ne 'mapping' -and $mode -ne 'changed'){
 @{ok=$false;category=$mode;retryable=$true;exception_type='SyntheticApiError'} | ConvertTo-Json -Compress;exit 2
}
$vm='computeinstance-synthetic';if($mode -eq 'changed'){$vm='computeinstance-changed'}
@{ok=$true;target=@{id='devlab-synthetic';vm_id=$vm;ip='192.0.2.10';ssh_user='nebius';
 host_alias=('nebius-devlab-synthetic-'+$vm);image='synthetic-image';state='RUNNING';
 api_target_verified=$true;public_key_mapping_verified=($mode -ne 'mapping')}} | ConvertTo-Json -Depth 4 -Compress
exit 0
'''

def write(path, value):
    path.write_text(json.dumps(value, indent=2), encoding='utf-8')

def ps(script, args=(), timeout=90):
    return subprocess.run([str(PS), '-NoProfile', '-File', str(script), *map(str, args)],
                          stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout)

def fixture(name, api=('success',), scan=('success',), work_seconds=110, offset=False):
    folder = RESULTS / name / 'native process with spaces'
    folder.mkdir(parents=True)
    shutil.copyfile(RESULTS / 'synthetic-keyscan.exe', folder / 'synthetic-keyscan.exe')
    (folder / 'scan-modes.txt').write_text('\n'.join(scan), encoding='ascii')
    blob = struct.pack('>I', 11) + b'ssh-ed25519' + struct.pack('>I', 32) + bytes(range(32))
    (folder / 'public-line.txt').write_text('192.0.2.10 ssh-ed25519 '+base64.b64encode(blob).decode()+'\n', encoding='ascii')
    api_file = folder / 'synthetic API.ps1'; api_file.write_text(API, encoding='ascii')
    config = folder / 'fixture.json'
    write(config, dict(simulation_only=True, scanner=str(folder/'synthetic-keyscan.exe'),
                       powershell=str(PS), api_script=str(api_file), api_modes=list(api)))
    run = RESULTS / name / 'run directory with spaces'; run.mkdir()
    now = datetime.now(timezone.utc); t0=now if work_seconds >= 0 else now-timedelta(minutes=1)
    fmt = lambda v: v.astimezone(timezone(timedelta(hours=8))).isoformat() if offset else v.isoformat()
    stop=t0+timedelta(minutes=23)
    write(run/'launch.json', dict(deadline_utc=fmt(stop),single_run=True,budget_usd_including_tax=3,
                                 approval_reference='SYNTHETIC_ONLY',offline=True))
    write(run/'timing.json', dict(t0_utc=fmt(t0), work_deadline_utc=fmt(now+timedelta(seconds=work_seconds)),
                                 stop_trigger_utc=fmt(stop),verification_target_utc=fmt(t0+timedelta(minutes=25))))
    return run, config

def execute(run, config):
    started=time.monotonic()
    result=ps(SCRIPTS/'Capture-TeaHost.ps1', ['-RunDirectory',run,'-Execute','-Offline','-FixturePath',config])
    (run/'process.stdout.txt').write_bytes(result.stdout);(run/'process.stderr.txt').write_bytes(result.stderr)
    events=[]
    if (run/'host-capture-events.jsonl').is_file():
        try:events=[json.loads(l) for l in (run/'host-capture-events.jsonl').read_text().splitlines()]
        except PermissionError:events=[]  # Intentional live file-lock fault injection.
    failure=json.loads((run/'host-capture-error.json').read_text()) if (run/'host-capture-error.json').is_file() else None
    return result.returncode,events,failure,time.monotonic()-started

def main():
    RESULTS.mkdir(exist_ok=False)
    (RESULTS/'scanner.cs').write_text(SCANNER,encoding='ascii')
    build=RESULTS/'build synthetic.ps1'
    build.write_text("Add-Type -Path $args[0] -OutputAssembly $args[1] -OutputType ConsoleApplication\n",encoding='ascii')
    result=ps(build,[RESULTS/'scanner.cs',RESULTS/'synthetic-keyscan.exe'])
    assert result.returncode==0,result.stderr
    rows=[]
    def check(name, action):
        try: action(); rows.append(dict(name=name,passed=True))
        except Exception as e:
            rows.append(dict(name=name,passed=False,error=str(e))); raise
    def success_case(name,api,scan,expected_stage=None,expected_exit=None,offset=False):
        run,config=fixture(name,api,scan,offset=offset)
        code,events,error,_=execute(run,config)
        assert code==0,(name,error,(run/'process.stderr.txt').read_text(errors='replace'))
        candidate=json.loads((run/'host-candidate.json').read_text())
        assert candidate['independently_verified'] is False and candidate['user_confirmed'] is False
        assert not (run/'complete.json').exists() and not (run/'known_hosts').exists() and not (run/'host-trust.json').exists()
        assert candidate['fingerprint'].startswith('SHA256:')
        if expected_stage:
            assert any(e.get('stage')==expected_stage and e.get('event')=='end' and
                       (e['details'].get('timed_out') if expected_exit=='timeout' else e['details'].get('exit_code')==expected_exit) for e in events)
        argv=(config.parent/'arguments.txt').read_text().splitlines()
        assert all(v=='-T|5|-t|ed25519|192.0.2.10' for v in argv),argv
        assert all('remaining_window_ms' in e for e in events if e.get('event') in ('start','end'))
    check('API transient then recovery, real PS5.1/native argv',lambda:success_case('api-recovery',['API_TRANSIENT','success'],['success']))
    check('VM information pending then recovery',lambda:success_case('vm-pending',['VM_INFO_PENDING','success'],['success']))
    check('Scan empty then success, same VM and no restart',lambda:success_case('empty-recovery',['success'],['empty','success']))
    check('Native scan timeout recorded then recovery',lambda:success_case('timeout',['success'],['timeout','success'],'native_keyscan','timeout'))
    check('Native nonzero exit9 recorded then recovery',lambda:success_case('nonzero',['success'],['nonzero','success'],'native_keyscan',9))
    check('UTC and +08 timestamps equivalent, local keygen path contains spaces',lambda:success_case('offset',['success'],['success'],offset=True))
    def failure_case(name,api,scan,category,seconds=110):
        run,config=fixture(name,api,scan,seconds)
        code,events,error,_=execute(run,config)
        assert code!=0 and error and error['category']==category,(name,code,error)
        assert error['stage'] and error['exception_type'] and error['stop_signal_written']
        assert json.loads((run/'complete.json').read_text())['stop_required']
        assert not (run/'host-candidate.json').exists() and not (run/'host-trust.json').exists()
        if not category.startswith('DEADLINE_'): assert error['remaining_window_ms']>0,error
        return run,events,error
    check('Illegal key: hard parsing failure, remaining window not expiry',lambda:failure_case('illegal',['success'],['invalid'],'SCAN_PUBLIC_KEY_PARSE_FAILED'))
    check('Mapping mismatch: hard failure without scan/retry',lambda:failure_case('mapping',['mapping'],['success'],'IDENTITY_MAPPING_MISMATCH'))
    check('VM changes after scan: refuses candidate',lambda:failure_case('changed',['success','changed'],['success'],'VM_IDENTITY_CHANGED'))
    check('API invalid JSON: no transient retry',lambda:failure_case('bad-api',['invalidjson'],['success'],'API_INVALID_JSON'))
    check('Incomplete API identity envelope hard classified, no scan',lambda:failure_case('bad-envelope',['badfields'],['success'],'API_ENVELOPE_INVALID'))
    check('API auth: no transient retry despite faulty retryable flag',lambda:failure_case('auth',['API_AUTH_OR_PERMISSION'],['success'],'API_AUTH_OR_PERMISSION'))
    check('Three API failures: early stop, not deadline exhaustion',lambda:failure_case('api-limit',['API_TRANSIENT'],['success'],'API_SUPERVISION_UNAVAILABLE'))
    check('True work deadline before process start',lambda:failure_case('expired',['success'],['success'],'DEADLINE_WORK',-1))
    check('Deadline reached during scan: actual work cutoff recorded',lambda:failure_case('during-expiry',['success'],['timeout'],'DEADLINE_WORK',4))
    check('Twelve empty scans exhaust attempts with remaining time, not deadline',lambda:failure_case('attempt-limit',['success'],['empty'],'CAPTURE_ATTEMPTS_EXHAUSTED'))
    def reserve_expiry():
        run,config=fixture('reserve-expired')
        now=datetime.now(timezone.utc);t0=now-timedelta(seconds=30);stop=now+timedelta(minutes=1)
        write(run/'launch.json',dict(deadline_utc=stop.isoformat(),offline=True))
        write(run/'timing.json',dict(t0_utc=t0.isoformat(),work_deadline_utc=(now+timedelta(seconds=10)).isoformat(),
          stop_trigger_utc=stop.isoformat(),verification_target_utc=(t0+timedelta(minutes=25)).isoformat()))
        code,events,error,_=execute(run,config)
        assert code==1 and error['category']=='DEADLINE_STOP_RESERVE',error
    check('Stop reserve cutoff is distinguished from work deadline',reserve_expiry)
    def missing_process():
        run,config=fixture('start-failure');(config.parent/'synthetic-keyscan.exe').unlink()
        code,events,error,_=execute(run,config)
        assert code==1 and error['category']=='SCAN_PROCESS_START_FAILED',error
        scan=[e for e in events if e.get('stage')=='native_keyscan' and e.get('event')=='end'][0]['details']
        assert scan['process_started'] is False and scan['exit_code'] is None and scan['exception_type']
    check('Native executable launch failure retains exception type and null exit',missing_process)
    def logging_failure():
        run,config=fixture('logging-failure')
        # Obstruct error log AFTER preserve gate; exercise the actual error writer.
        api_script=config.parent/'synthetic API.ps1'
        api_script.write_text("param([string]$FixturePath)\n"+
          "$root=Split-Path (Split-Path $FixturePath);"+
          "New-Item -ItemType Directory -Path (Join-Path $root 'run directory with spaces/host-capture-error.json') | Out-Null;"+
          "@{ok=$false;category='IDENTITY_MAPPING_MISMATCH';retryable=$false;exception_type='SyntheticError'}|ConvertTo-Json -Compress;exit 2",encoding='ascii')
        code,events,_,_=execute_no_errorfile(run,config)
        assert code==1 and json.loads((run/'complete.json').read_text())['stop_required']
    def execute_no_errorfile(run,config):
        result=ps(SCRIPTS/'Capture-TeaHost.ps1',['-RunDirectory',run,'-Execute','-Offline','-FixturePath',config])
        return result.returncode,[],None,0
    check('Error log write obstruction cannot lose guard completion signal',logging_failure)
    def event_failure():
        run,config=fixture('event-failure')
        # Independent fixture process owns its lock. It is not a descendant of
        # an API worker that the new private-job runner correctly cleans up.
        holder=config.parent/'hold log.ps1'
        holder.write_text("param([string]$FixturePath)\n"+
          "$root=Split-Path (Split-Path $FixturePath);$run=Join-Path $root 'run directory with spaces';"+
          "$events=Join-Path $run 'host-capture-events.jsonl';$watch=[Diagnostics.Stopwatch]::StartNew();"+
          "while(!(Test-Path $events) -and $watch.Elapsed.TotalSeconds -lt 10){Start-Sleep -Milliseconds 10};"+
          "$f=[IO.File]::Open((Join-Path $run 'host-capture-events.jsonl'),[IO.FileMode]::Open,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None);"+
          "[IO.File]::WriteAllText((Join-Path $run 'lock-ready.txt'),'ready');Start-Sleep 15;$f.Dispose()",encoding='ascii')
        api_script=config.parent/'synthetic API.ps1'
        api_script.write_text("param([string]$FixturePath)\nStart-Sleep -Milliseconds 600;"+
          "@{ok=$false;category='API_TRANSIENT';retryable=$true;exception_type='SyntheticError'}|ConvertTo-Json -Compress;exit 2",encoding='ascii')
        lock_process=subprocess.Popen([str(PS),'-NoProfile','-File',str(holder),'-FixturePath',str(config)],
          stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            code,events,error,_=execute(run,config)
            assert code==1 and error['category']=='DIAGNOSTIC_WRITE_FAILED' and error['diagnostic_write_failures']>0,error
            assert error['stop_signal_written'] and (run/'complete.json').exists(),error
        finally:
            if lock_process.poll() is None:lock_process.terminate()
            lock_process.communicate(timeout=5)
    check('Locked diagnostic log still emits stop signal and fallback detail',event_failure)
    def redaction():
        run,config=fixture('redaction',['success','success','mapping'],['redact'])
        code,events,error,_=execute(run,config)
        combined='\n'.join(p.read_text(errors='replace') for p in run.glob('*.json*'))
        assert 'TOKEN_SHOULD_NEVER_APPEAR' not in combined and 'secret=password' not in combined and 'private-key-secret' not in combined
        assert error['category']=='SCAN_PUBLIC_KEY_PARSE_FAILED',error
        assert any(e.get('stage')=='native_keyscan' and e.get('event')=='end' and e['details']['public_output']['unrecognized_lines_redacted']>=2 for e in events)
    check('Unknown stdout/stderr redacted; only public handshake allowlist retained',redaction)
    default=ps(SCRIPTS/'Capture-TeaHost.ps1',['-RunDirectory',RESULTS/'never created'])
    check('Default entry performs no operation',lambda: (_ for _ in ()).throw(AssertionError()) if default.returncode or (RESULTS/'never created').exists() else None)
    def argv_quoting():
        script=RESULTS/'argv quoting.ps1'
        script.write_text(r'''param([string]$Module,[string]$Executable)
. $Module
$r=Invoke-HostNative $Executable @('a"b','two words\','', 'plain') 3000
if(!$r.Started -or $r.TimedOut -or $r.ExitCode -ne 99){exit 1}
''',encoding='ascii')
        result=ps(script,[SCRIPTS/'HostCapture.Native.ps1',RESULTS/'synthetic-keyscan.exe'])
        assert result.returncode==0,result.stderr
        assert (RESULTS/'arguments.txt').read_text().splitlines()[-1]=='a"b|two words\\||plain'
    check('Real native argument transport preserves quotes, trailing backslash and empty argument',argv_quoting)
    write(RESULTS/'offline-tests.json',dict(passed=True,test_count=len(rows),tests=rows,cloud_API_calls=0,SSH_connections=0))
    print(json.dumps({'passed':True,'test_count':len(rows)}))

if __name__=='__main__': main()
