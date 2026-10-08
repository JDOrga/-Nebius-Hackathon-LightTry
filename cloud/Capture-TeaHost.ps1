[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$RunDirectory,
    [switch]$Execute,
    [switch]$Offline,
    [string]$FixturePath
)
# Default is a local plan. Production needs a fresh guarded/authorized run.
# Candidate capture never creates trust, authenticates SSH, starts or restarts a VM.
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'RequestJson.ps1')
$ErrorActionPreference='Stop'
if (!$Execute) {
    @{entry=$PSCommandPath;mode='LOCAL_PLAN_ONLY';API_calls=0;remote_scans=0;
      maximum_capture_attempts=12;ready_max_reads=60;ready_deadline_minutes_from_t0=5;capture_deadline_minutes_from_t0=6;ready_poll_ms=5000;consecutive_API_failure_limit=3;API_timeout_seconds=45;
      scan_timeout_seconds=8;scan_internal_seconds=5;stop_reserve_seconds=120} | ConvertTo-Json
    exit 0
}
. (Join-Path $PSScriptRoot 'HostCapture.Native.ps1')
$run=[IO.Path]::GetFullPath($RunDirectory)
$events=Join-Path $run 'host-capture-events.jsonl'
$stage='setup'; $attempt=0; $category='SETUP_FAILED'; $success=$false
$deadline=$null; $deadlineKind='not_loaded'; $target=$null; $locked=$null
$apiFailures=0; $lastFailure='NONE'; $diagnosticFailures=0
$offlineConfig=$null; $settings=$null; $startup=[DateTimeOffset]::UtcNow
$stageStarted=$startup
$launch=$null; $timing=$null
$phase='setup';$readyRead=0;$readyMaxReads=60;$readyPollMs=5000
function UtcText { [DateTimeOffset]::UtcNow.ToString('o') }
function Read-HostJson([string]$Path) { Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-JsonUtc }
function HostDigest([string]$Path) {
    $h=[Security.Cryptography.SHA256]::Create(); $f=[IO.File]::OpenRead($Path)
    try { ([BitConverter]::ToString($h.ComputeHash($f))).Replace('-','').ToLowerInvariant() }
    finally { $f.Dispose(); $h.Dispose() }
}
function Write-HostJson([string]$Path,$Value) {
    if (Test-Path -LiteralPath $Path -PathType Container) { throw 'DIAGNOSTIC_TARGET_IS_DIRECTORY' }
    $temp=$Path+'.writing-'+[Guid]::NewGuid().ToString('N')
    [IO.File]::WriteAllText($temp,($Value | ConvertTo-Json -Depth 10),[Text.UTF8Encoding]::new($false))
    Move-Item -LiteralPath $temp -Destination $Path -Force
}
function RemainingMs {
    if ($null -eq $deadline) { return 0 }
    [Math]::Floor(($deadline-[DateTimeOffset]::UtcNow).TotalMilliseconds)
}
function Evidence($Value) {
    try {
        [IO.File]::AppendAllText($events,(($Value | ConvertTo-Json -Depth 10 -Compress)+[Environment]::NewLine),[Text.UTF8Encoding]::new($false))
    } catch {
        $script:diagnosticFailures++
        $ioType=$_.Exception.GetType().FullName
        # Keep the already sanitized stage/end/exit-code record outside the locked journal.
        try { Write-HostJson (Join-Path $run ('host-capture-event-fallback-'+[Guid]::NewGuid().ToString('N')+'.json')) @{
          journal_exception_type=$ioType;event=$Value;utc=(UtcText)} } catch { }
        # No raw exception text, environment or credentials; fallback public diagnostic.
        try { [IO.File]::AppendAllText((Join-Path $run 'host-capture-diagnostic-fallback.txt'),
          ((UtcText)+' '+$stage+' DIAGNOSTIC_WRITE_FAILED '+$ioType+[Environment]::NewLine)) } catch { }
        throw 'DIAGNOSTIC_WRITE_FAILED'
    }
}
function BeginStage([string]$Name) {
    $script:stage=$Name; $now=[DateTimeOffset]::UtcNow
    $script:stageStarted=$now
    if ((RemainingMs) -le 0) { throw ('DEADLINE_'+$deadlineKind) }
    if (Test-Path -LiteralPath (Join-Path $run 'complete.json')) { throw 'STOP_ALREADY_REQUESTED' }
    Evidence @{stage=$stage;phase=$phase;ready_read=$readyRead;event='start';utc=$now.ToString('o');attempt=$attempt;
      remaining_window_ms=(RemainingMs);deadline_kind=$deadlineKind}
    return $now
}
function FinishStage($Began,$Details) {
    $end=[DateTimeOffset]::UtcNow
    Evidence @{stage=$stage;phase=$phase;ready_read=$readyRead;event='end';start_utc=$Began.ToString('o');end_utc=$end.ToString('o');
      elapsed_ms=($end-$Began).TotalMilliseconds;attempt=$attempt;remaining_window_ms=(RemainingMs);
      deadline_kind=$deadlineKind;details=$Details}
    if ((RemainingMs) -le 0) { throw ('DEADLINE_'+$deadlineKind) }
}
function NativeDetails($Result) {
    @{process_started=$Result.Started;timed_out=$Result.TimedOut;exit_code=$Result.ExitCode;
      exception_type=$Result.ExceptionType;elapsed_ms=$Result.ElapsedMs;output_lines=$Result.OutputLines;
      native_error_code=$Result.NativeErrorCode;exception_hresult=$Result.ExceptionHResult;
      status=$Result.Status;implementation_version=$Result.ImplementationVersion;
      budget_ms=$Result.BudgetMs;execution_budget_ms=$Result.ExecutionBudgetMs;
      process_exited=$Result.ProcessExited;pipe_not_closed=$Result.PipeTimedOut;
      output_complete=$Result.OutputComplete;output_read_failed=$Result.ReadFailed;
      stdout_read_error=$Result.StdoutReadError;stderr_read_error=$Result.StderrReadError;
      cleanup_attempted=$Result.CleanupAttempted;cleanup_incomplete=$Result.CleanupIncomplete;
      private_job_assigned=$Result.JobAssigned;remaining_owned_processes=$Result.RemainingOwnedProcesses;
      stderr_lines=$Result.ErrorLines;truncated=$Result.Truncated;kill_failed=$Result.KillFailed}
}
function RequireProcess($Result,[string]$Prefix) {
    if (!$Result.Started) {
        if ($Result.TimedOut) { throw ($Prefix+'_PROCESS_TIMEOUT') }
        throw ($Prefix+'_PROCESS_START_FAILED')
    }
    if ($Result.CleanupIncomplete) { throw ($Prefix+'_CLEANUP_INCOMPLETE') }
    if ($Result.KillFailed) { throw ($Prefix+'_PROCESS_KILL_FAILED') }
    if ($Result.PipeTimedOut) { throw ($Prefix+'_PIPE_NOT_CLOSED') }
    if ($Result.ReadFailed) { throw ($Prefix+'_OUTPUT_READ_FAILED') }
    if ($Result.ExceptionType) { throw ($Prefix+'_PROCESS_ERROR') }
    # Timeout callers retain their existing classifications/retries and never parse output.
    if ($Result.TimedOut) { return }
    if ($Result.Truncated) { throw ($Prefix+'_OUTPUT_LIMIT_EXCEEDED') }
    if (!$Result.OutputComplete) { throw ($Prefix+'_OUTPUT_INCOMPLETE') }
}
function Backoff {
    $interval=2000;if($phase -eq 'ready_wait'){$interval=$readyPollMs}
    $wait=[Math]::Min($interval,(RemainingMs))
    if ($wait -le 0) { throw ('DEADLINE_'+$deadlineKind) }
    Start-Sleep -Milliseconds ([int]$wait)
}
function GetTarget([string]$Purpose) {
    $began=BeginStage 'api_locate'
    $timeout=[int][Math]::Min(48000,(RemainingMs))
    if ($Offline) {
        $args=@('-NoProfile','-File',$offlineConfig.api_script,'-FixturePath',$FixturePath)
        $api=Invoke-HostNative $offlineConfig.powershell $args $timeout
    } else {
        $args=@('-d',$settings.wsl_distro,'--','python3', (WslPath (Join-Path $PSScriptRoot 'host_capture_api.py')),
          '--settings',(WslPath (Join-Path $run 'live-settings.json')),
          '--bridge',(WslPath (Join-Path $original 'cli_bridge.py')),
          '--public-key-file',(WslPath ($settings.key_path+'.pub')),
          '--execute','--timeout-seconds',([string][Math]::Max(1,[Math]::Min(45,[Math]::Floor($timeout/1000)-2))))
        $api=Invoke-HostNative (Join-Path $env:SystemRoot 'System32/wsl.exe') $args $timeout
    }
    $details=NativeDetails $api
    $details.purpose=$Purpose
    # API raw stdout/stderr are never persisted. Decode only the typed public envelope.
    try { RequireProcess $api 'API' }
    catch { FinishStage $began $details; throw }
    if ($api.TimedOut) {
        $details.category='API_TIMEOUT'; FinishStage $began $details
        return @{ok=$false;category='API_TIMEOUT';retryable=$true}
    }
    try { $answer=$api.Stdout | ConvertFrom-JsonUtc } catch {
        $details.category='API_INVALID_JSON'; FinishStage $began $details; throw 'API_INVALID_JSON'
    }
    if ($null -eq $answer -or $answer.PSObject.Properties.Name -notcontains 'ok' -or $answer.ok -isnot [bool]) {
        $details.category='API_ENVELOPE_INVALID'; FinishStage $began $details; throw 'API_ENVELOPE_INVALID'
    }
    if (!$answer.ok) {
        if ($answer.PSObject.Properties.Name -notcontains 'category' -or $answer.PSObject.Properties.Name -notcontains 'exception_type') {
            $details.category='API_ENVELOPE_INVALID'; FinishStage $began $details; throw 'API_ENVELOPE_INVALID'
        }
        $label=[string]$answer.category
        if ($label -notmatch '^[A-Z0-9_]{1,100}$') { $label='API_UNCLASSIFIED_ERROR' }
        $details.category=$label
        $typeName=[string]$answer.exception_type
        if ($typeName -notmatch '^[A-Za-z0-9_.]{1,100}$') { $typeName='REDACTED' }
        $details.worker_exception_type=$typeName
        if ($answer.PSObject.Properties.Name -contains 'devlab_state' -and $answer.devlab_state -in @('STARTING','PROVISIONING','RUNNING','IMAGE_PULLING','STOPPING','STOPPED')) {
            $details.devlab_state=$answer.devlab_state
        }
        if ($answer.PSObject.Properties.Name -contains 'cli_exit_code' -and
            ($null -eq $answer.cli_exit_code -or $answer.cli_exit_code -is [int])) {
            $details.cli_exit_code=$answer.cli_exit_code
        }
        FinishStage $began $details
        # Only an explicit allowlist may retry, even if a faulty worker says otherwise.
        return @{ok=$false;category=$label;retryable=($label -in @('API_TRANSIENT','API_TIMEOUT','DEVLAB_NOT_READY','VM_INFO_PENDING'))}
    }
    if ($api.ExitCode -ne 0 -or $api.Truncated) {
        $details.category='API_ENVELOPE_INVALID'; FinishStage $began $details; throw 'API_ENVELOPE_INVALID'
    }
    if ($answer.PSObject.Properties.Name -notcontains 'target') {
        $details.category='API_ENVELOPE_INVALID'; FinishStage $began $details; throw 'API_ENVELOPE_INVALID'
    }
    $t=$answer.target
    foreach($field in @('id','vm_id','ip','ssh_user','host_alias','image','api_target_verified','public_key_mapping_verified','state')) {
        if ($null -eq $t -or $t.PSObject.Properties.Name -notcontains $field) {
            $details.category='API_ENVELOPE_INVALID'; FinishStage $began $details; throw 'API_ENVELOPE_INVALID'
        }
    }
    $valid=($t.id -eq $settings.devlab_id -and $t.vm_id -match '^computeinstance-[a-z0-9]+$' -and
      $t.ip -match '^[0-9a-fA-F:.]+$' -and $t.ssh_user -match '^[a-z_][a-z0-9_-]{0,31}$' -and
      $t.host_alias -eq ('nebius-'+$t.id+'-'+$t.vm_id) -and $t.image -and
      $t.api_target_verified -eq $true -and $t.public_key_mapping_verified -eq $true)
    $address=$null
    $valid=($valid -and [Net.IPAddress]::TryParse([string]$t.ip,[ref]$address))
    $details.api_located=$true; $details.identity_and_public_key_mapping_passed=$valid
    if ($valid) { $details.target=$t }
    FinishStage $began $details
    if (!$valid) { throw 'IDENTITY_MAPPING_MISMATCH' }
    if ($null -ne $locked -and ($t.vm_id -ne $locked.vm_id -or $t.ip -ne $locked.ip -or
       $t.ssh_user -ne $locked.ssh_user -or $t.host_alias -ne $locked.host_alias -or $t.image -ne $locked.image)) {
        throw 'VM_IDENTITY_CHANGED'
    }
    return @{ok=$true;target=$t}
}
function WslPath([string]$Path) {
    $p=[IO.Path]::GetFullPath($Path)
    if ($p -notmatch '^([A-Za-z]):\\(.*)$') { throw 'WSL_PATH_INVALID' }
    '/mnt/'+$Matches[1].ToLowerInvariant()+'/'+$Matches[2].Replace('\','/')
}
function PublicScanEvidence($Scan,[string]$Ip) {
    # Save only exact public-key lines or recognized public handshake messages.
    # Unknown lines are counted/redacted, never copied to disk.
    $ipRegex=[regex]::Escape($Ip); $out=@(); $err=@(); $redacted=0
    foreach($line in @($Scan.Stdout -split '\r?\n')) {
        if (!$line) { continue }
        if ($line -match ('^'+$ipRegex+' ssh-ed25519 [A-Za-z0-9+/=]{1,256}$')) { $out+=$line }
        else { $redacted++ }
    }
    foreach($line in @($Scan.Stderr -split '\r?\n')) {
        if (!$line) { continue }
        if ($line -match ('^# '+$ipRegex+':22 SSH-2\.0-[A-Za-z0-9_.+ /-]{1,180}$') -or
            $line -match ('^'+$ipRegex+': Connection (refused|timed out|closed)$')) { $err+=$line }
        else { $redacted++ }
    }
    @{public_stdout=@($out);public_stderr=@($err);unrecognized_lines_redacted=$redacted}
}
function ValidatePublicKey([string]$Encoded) {
    try {
        $b=[Convert]::FromBase64String($Encoded)
        # SSH wire format: 11-byte algorithm, 32-byte Ed25519 public key, no extra fields.
        if ($b.Length -ne 51 -or $b[0] -ne 0 -or $b[1] -ne 0 -or $b[2] -ne 0 -or $b[3] -ne 11 -or
          [Text.Encoding]::ASCII.GetString($b,4,11) -ne 'ssh-ed25519' -or
          $b[15] -ne 0 -or $b[16] -ne 0 -or $b[17] -ne 0 -or $b[18] -ne 32) { return $false }
        return $true
    } catch { return $false }
}
try {
    if ($Offline) {
        if (!$FixturePath) { throw 'OFFLINE_FIXTURE_REQUIRED' }
        $offlineConfig=Read-HostJson $FixturePath
        $settings=@{devlab_id='devlab-synthetic'}
        if ($offlineConfig.simulation_only -ne $true) { throw 'OFFLINE_FIXTURE_INVALID' }
        # No production bridge/settings are loaded in this branch. Only native synthetic process.
        $scanner=[IO.Path]::GetFullPath($offlineConfig.scanner)
        if ([IO.Path]::GetFileName($scanner) -ne 'synthetic-keyscan.exe') { throw 'OFFLINE_SCANNER_INVALID' }
        $keygen=Join-Path $env:SystemRoot 'System32/OpenSSH/ssh-keygen.exe'
    } else {
        if ($FixturePath) { throw 'PRODUCTION_FIXTURE_FORBIDDEN' }
        $original=$PSScriptRoot
        $settings=Read-HostJson (Join-Path $run 'live-settings.json')
        $beat=Read-HostJson (Join-Path $run 'heartbeat.json')
        if ($beat.offline -or !$beat.sleep_held -or $beat.stopped_verified -or
          $null -eq (Get-Process -Id $beat.pid -ErrorAction SilentlyContinue) -or
          ([DateTimeOffset]::UtcNow-[DateTimeOffset]::Parse($beat.utc)).TotalSeconds -gt 30) { throw 'LIVE_GUARD_REQUIRED' }
        if (!$settings.devlab_id -or !$settings.cloud_stop_enabled) { throw 'AUTHORIZED_RESOURCE_MISMATCH' }
        $scanner=Join-Path $env:SystemRoot 'System32/OpenSSH/ssh-keyscan.exe'
        $keygen=Join-Path $env:SystemRoot 'System32/OpenSSH/ssh-keygen.exe'
    }
    $launch=Read-HostJson (Join-Path $run 'launch.json')
    $timing=Read-HostJson (Join-Path $run 'timing.json')
    if (!$Offline -and (!$launch.single_run -or $launch.budget_usd_including_tax -le 0 -or !$launch.approval_reference)) {
        throw 'FRESH_SINGLE_RUN_AUTHORIZATION_REQUIRED'
    }
    $work=[DateTimeOffset]::Parse($timing.work_deadline_utc).ToUniversalTime()
    $stop=[DateTimeOffset]::Parse($timing.stop_trigger_utc).ToUniversalTime()
    $guard=[DateTimeOffset]::Parse($launch.deadline_utc).ToUniversalTime()
    $t0=[DateTimeOffset]::Parse($timing.t0_utc).ToUniversalTime()
    $verification=[DateTimeOffset]::Parse($timing.verification_target_utc).ToUniversalTime()
    $runningClock=($launch.PSObject.Properties.Name -contains 'timing_policy' -and $launch.timing_policy -eq 'RUNNING_ANCHORED_18_25_27')
    $stopOffset=1380;$verifyOffset=1500;if($runningClock){$stopOffset=1500;$verifyOffset=1620}
    if ($stop -ne $guard -or $work -le $t0 -or $stop -le $work -or $verification -le $stop -or
       ($verification-$t0).TotalSeconds -gt $verifyOffset+1) { throw 'TIMING_CONTRACT_INVALID' }
    if (!$Offline -and (($work-$t0).TotalSeconds -gt 1080 -or ($stop-$t0).TotalSeconds -gt $stopOffset -or
       ($verification-$t0).TotalSeconds -ne $verifyOffset)) { throw 'FIXED_TIMING_POLICY_REQUIRED' }
    if($runningClock -and !$Offline){
        $proofPath=Join-Path $run 'running-confirmation.json';$proof=Read-HostJson $proofPath
        if($proof.state -ne 'RUNNING' -or !$proof.independent_api -or $proof.id -ne $settings.devlab_id -or
          [DateTimeOffset]::Parse($proof.utc) -ne $t0 -or $launch.running_confirmed_utc -ne $proof.utc -or
          (HostDigest $proofPath) -ne $launch.running_confirmation_sha256 -or $timing.running_confirmation_sha256 -ne $launch.running_confirmation_sha256){throw 'RUNNING_ANCHOR_INVALID'}
    }
    $deadline=$work; $deadlineKind='WORK'
    if ($stop.AddSeconds(-120) -lt $deadline) { $deadline=$stop.AddSeconds(-120); $deadlineKind='STOP_RESERVE' }
    $overallDeadline=$deadline;$overallKind=$deadlineKind
    $readySeconds=300;$captureSeconds=360
    # Offline-only shortened clocks exercise the same branches without cloud or long sleeps.
    if($Offline -and $offlineConfig.PSObject.Properties.Name -contains 'simulation_policy') {
        $policy=$offlineConfig.simulation_policy
        $readySeconds=[int]$policy.ready_seconds;$captureSeconds=[int]$policy.capture_seconds
        $readyPollMs=[int]$policy.ready_poll_ms;$readyMaxReads=[int]$policy.ready_max_reads
        if($readySeconds -lt 1 -or $readySeconds -gt 300 -or $captureSeconds -le $readySeconds -or $captureSeconds -gt 360 -or $readyPollMs -lt 1 -or $readyPollMs -gt 5000 -or $readyMaxReads -lt 1 -or $readyMaxReads -gt 60){throw 'OFFLINE_POLICY_INVALID'}
    }
    $captureDeadline=$overallDeadline;$captureKind=$overallKind
    if($t0.AddSeconds($captureSeconds) -lt $captureDeadline){$captureDeadline=$t0.AddSeconds($captureSeconds);$captureKind='CAPTURE'}
    $readyDeadline=$captureDeadline;$readyKind=$captureKind
    if($t0.AddSeconds($readySeconds) -lt $readyDeadline){$readyDeadline=$t0.AddSeconds($readySeconds);$readyKind='READY_WAIT'}
    $deadline=$readyDeadline;$deadlineKind=$readyKind;$phase='ready_wait'
    foreach($name in @('host-capture-events.jsonl','host-candidate.json','host-key-candidate.txt','host-capture-error.json')) {
        if (Test-Path -LiteralPath (Join-Path $run $name)) { throw 'PRESERVE_EXISTING_CAPTURE_NO_REPLAY' }
    }
    $sourceHashes=@{}
    foreach($path in @($PSCommandPath,(Join-Path $PSScriptRoot 'HostCapture.Native.ps1'),
        (Join-Path $PSScriptRoot 'HostCapture.Native.cs'),(Join-Path $PSScriptRoot 'host_capture_api.py'))) {
        $sourceHashes[$path]=HostDigest $path
    }
    if (!$Offline) { $sourceHashes[(Join-Path $original 'cli_bridge.py')]=HostDigest (Join-Path $original 'cli_bridge.py') }
    # Preserve actual implementation beside each new run; never copy auth settings.
    $codeSnapshot=Join-Path $run 'host-capture-code'
    if (Test-Path -LiteralPath $codeSnapshot) { throw 'PRESERVE_EXISTING_CAPTURE_NO_REPLAY' }
    New-Item -ItemType Directory -Path $codeSnapshot | Out-Null
    foreach($path in $sourceHashes.Keys) {
        Copy-Item -LiteralPath $path -Destination (Join-Path $codeSnapshot ([IO.Path]::GetFileName($path)))
    }
    $scannerHash='NOT_FOUND'
    if (Test-Path -LiteralPath $scanner -PathType Leaf) { $scannerHash=HostDigest $scanner }
    Evidence @{stage='setup';event='configuration';utc=(UtcText);entry=$PSCommandPath;source_hashes=$sourceHashes;
      invocation=@{RunDirectory=$run;Execute=$true;Offline=[bool]$Offline};code_snapshot=$codeSnapshot;
      powershell_version=$PSVersionTable.PSVersion.ToString();scanner_path=$scanner;scanner_sha256=$scannerHash;
      offline=[bool]$Offline;work_deadline_utc=$work.ToString('o');guard_deadline_utc=$guard.ToString('o');
      effective_capture_deadline_utc=$deadline.ToString('o');deadline_kind=$deadlineKind;
      max_attempts=12;ready_max_reads=$readyMaxReads;ready_poll_ms=$readyPollMs;ready_deadline_utc=$readyDeadline.ToString('o');capture_deadline_utc=$captureDeadline.ToString('o');remaining_work_after_capture_ms=($work-$captureDeadline).TotalMilliseconds;API_failure_limit=3;API_timeout_ms=45000;scan_internal_timeout_seconds=5;scan_process_timeout_ms=8000;
      retry_backoff_ms=2000;candidate_is_independently_verified=$false;trust_created=$false}
    $ready=$false
    for($readyRead=1;$readyRead -le $readyMaxReads;$readyRead++) {
        $answer=GetTarget 'ready_wait'
        if($answer.ok){$ready=$true;$locked=$answer.target;$apiFailures=0;break}
        $lastFailure=$answer.category
        if(!$answer.retryable){throw $lastFailure}
        if($lastFailure -in @('API_TRANSIENT','API_TIMEOUT')){$apiFailures++}else{$apiFailures=0}
        if($apiFailures -ge 3){throw 'API_SUPERVISION_UNAVAILABLE'}
        if($readyRead -lt $readyMaxReads){Backoff}
    }
    if(!$ready){throw 'READY_WAIT_READ_LIMIT'}
    $phase='capture';$deadline=$captureDeadline;$deadlineKind=$captureKind
    for($attempt=1;$attempt -le 12;$attempt++) {
        $answer=GetTarget 'before_scan'
        if (!$answer.ok) {
            $lastFailure=$answer.category
            if (!$answer.retryable) { throw $lastFailure }
            if ($lastFailure -in @('API_TRANSIENT','API_TIMEOUT')) { $apiFailures++ } else { $apiFailures=0 }
            if ($apiFailures -ge 3) { throw 'API_SUPERVISION_UNAVAILABLE' }
            Backoff; continue
        }
        $apiFailures=0; $target=$answer.target
        if ($null -eq $locked) { $locked=$target }
        $began=BeginStage 'native_keyscan'
        $scan=Invoke-HostNative $scanner @('-T','5','-t','ed25519',[string]$target.ip) ([int][Math]::Min(8000,(RemainingMs)))
        $details=NativeDetails $scan; $details.public_output=PublicScanEvidence $scan $target.ip
        FinishStage $began $details; RequireProcess $scan 'SCAN'
        if ($scan.TimedOut) { $lastFailure='SCAN_TIMEOUT'; Backoff; continue }
        if ($scan.Truncated) { throw 'SCAN_OUTPUT_LIMIT_EXCEEDED' }
        $began=BeginStage 'parse_public_key'
        $lines=@($scan.Stdout -split '\r?\n' | Where-Object {$_})
        $keys=@(); $invalid=0; $algorithms=@()
        foreach($line in $lines) {
            $parts=$line -split ' '
            if ($parts.Count -eq 3) { $algorithms+=$parts[1] }
            if ($parts.Count -ne 3 -or $parts[0] -ne $target.ip -or $parts[1] -ne 'ssh-ed25519' -or
                !(ValidatePublicKey $parts[2])) { $invalid++; continue }
            $keys+=$line
        }
        FinishStage $began @{returned_lines=$lines.Count;algorithms=@($algorithms | Where-Object {$_ -match '^ssh-[a-z0-9-]{1,30}$'});
          parsed_count=$keys.Count;invalid_count=$invalid;scan_exit_code=$scan.ExitCode}
        if ($invalid -gt 0 -or $keys.Count -gt 1) { throw 'SCAN_PUBLIC_KEY_PARSE_FAILED' }
        if ($scan.ExitCode -ne 0) { $lastFailure='SCAN_NONZERO_EXIT'; Backoff; continue }
        if ($keys.Count -eq 0) { $lastFailure='SCAN_EMPTY_OUTPUT'; Backoff; continue }
        $began=BeginStage 'fingerprint'
        $keyPath=Join-Path $run ('host-key-attempt-'+$attempt+'.txt')
        [IO.File]::WriteAllText($keyPath,($keys[0]+[Environment]::NewLine),[Text.UTF8Encoding]::new($false))
        $fp=Invoke-HostNative $keygen @('-lf',$keyPath,'-E','sha256') ([int][Math]::Min(5000,(RemainingMs)))
        $details=NativeDetails $fp
        try {
            RequireProcess $fp 'FINGERPRINT'
            if ($fp.TimedOut -or $fp.ExitCode -ne 0) { throw 'FINGERPRINT_PARSE_FAILED' }
        } catch { FinishStage $began $details; throw }
        $match=[regex]::Match($fp.Stdout,'\bSHA256:[A-Za-z0-9+/]{43}(?=\s|$)')
        if ($match.Success) { $details.public_fingerprint=$match.Value }
        FinishStage $began $details
        if (!$match.Success) { throw 'FINGERPRINT_PARSE_FAILED' }
        # Recheck authoritative current identity before publishing a candidate.
        $fresh=GetTarget 'after_scan'
        if (!$fresh.ok) {
            $lastFailure=$fresh.category
            if (!$fresh.retryable) { throw $lastFailure }
            if ($lastFailure -in @('API_TRANSIENT','API_TIMEOUT')) { $apiFailures++ }
            if ($apiFailures -ge 3) { throw 'API_SUPERVISION_UNAVAILABLE' }
            Backoff; continue
        }
        $began=BeginStage 'publish_candidate'
        Copy-Item -LiteralPath $keyPath -Destination (Join-Path $run 'host-key-candidate.txt')
        Write-HostJson (Join-Path $run 'host-candidate.json') @{
          vm_id=$fresh.target.vm_id;ip=$fresh.target.ip;ssh_user=$fresh.target.ssh_user;host_alias=$fresh.target.host_alias;
          fingerprint=$match.Value;independently_verified=$false;user_confirmed=$false;api_target_verified=$true;
          public_key_mapping_verified=$true;devlab_state=$fresh.target.state;utc=(UtcText);target=$fresh.target}
        FinishStage $began @{result='CANDIDATE_ONLY_USER_CONFIRMATION_REQUIRED';fingerprint=$match.Value;trust_created=$false}
        $success=$true; break
    }
    if (!$success) { throw 'CAPTURE_ATTEMPTS_EXHAUSTED' }
    Write-HostJson (Join-Path $run 'host-capture-result.json') @{success=$true;attempts=$attempt;utc=(UtcText);trust_created=$false}
} catch {
    $errorRecord=$_
    $category=[string]$errorRecord.Exception.Message
    if ($category -notmatch '^[A-Z0-9_]{1,100}$') { $category='UNCLASSIFIED_LOCAL_ERROR' }
    # Stop signal is attempted FIRST, independent of diagnostic log success.
    $stopWritten=$false
    try {
        if (!(Test-Path -LiteralPath (Join-Path $run 'complete.json'))) {
            Write-HostJson (Join-Path $run 'complete.json') @{reason='host_capture_failed';failure_category=$category;
              completed_utc=(UtcText);stop_required=$true;supervise_STOPPED_required=$true;restart_allowed=$false}
        }
        $stopWritten=$true
    } catch {
        # Atomic writer can fail; try direct exclusive create of the same guard signal.
        try {
            $stream=[IO.File]::Open((Join-Path $run 'complete.json'),[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read)
            try { $bytes=[Text.Encoding]::UTF8.GetBytes('{"reason":"host_capture_failed","stop_required":true}');$stream.Write($bytes,0,$bytes.Length) }
            finally { $stream.Dispose() }
            $stopWritten=$true
        } catch { }
    }
    $failure=@{stage=$stage;phase=$phase;ready_read=$readyRead;attempt=$attempt;utc=(UtcText);elapsed_ms=([DateTimeOffset]::UtcNow-$startup).TotalMilliseconds;
      stage_start_utc=$stageStarted.ToString('o');stage_end_utc=(UtcText);stage_elapsed_ms=([DateTimeOffset]::UtcNow-$stageStarted).TotalMilliseconds;
      remaining_window_ms=(RemainingMs);deadline_kind=$deadlineKind;category=$category;last_retry_cause=$lastFailure;
      exception_type=$errorRecord.Exception.GetType().FullName;error_id=$errorRecord.FullyQualifiedErrorId.Split(',')[0];
      script_line_number=$errorRecord.InvocationInfo.ScriptLineNumber;script_path=$errorRecord.InvocationInfo.ScriptName;
      safe_message=$category;diagnostic_write_failures=$diagnosticFailures;stop_signal_written=$stopWritten;
      raw_exception_message_saved=$false;STOPPED_verification_required=$true;restart_allowed=$false}
    # ErrorId can embed source text; only stable identifier labels survive.
    if ($failure.error_id -notmatch '^[A-Za-z0-9_.]{1,100}$') { $failure.error_id='REDACTED' }
    try { Write-HostJson (Join-Path $run 'host-capture-error.json') $failure } catch { }
    try { Evidence @{event='failure';details=$failure} } catch { }
    $failure | ConvertTo-Json -Depth 6
    exit 1
}
exit 0
