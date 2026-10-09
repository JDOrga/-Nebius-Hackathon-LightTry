param([Parameter(Mandatory=$true)][string]$RunDirectory,[switch]$Execute)
if(!$Execute){@{mode='LOCAL_PLAN';cloud_calls=0}|ConvertTo-Json;exit 0}
. (Join-Path $PSScriptRoot 'Common.ps1')
$run=[IO.Path]::GetFullPath($RunDirectory)
$startup=Get-Content (Join-Path $run 'startup.json') -Raw|ConvertFrom-JsonUtc
$offline=[bool]$startup.offline;$script:SettingsFile=Join-Path $run 'live-settings.json'
if(!$offline -and (!(Read-Settings).cloud_stop_enabled -or $startup.budget_usd_including_tax -le 0 -or !$startup.approval_reference)){throw 'CURRENT_STOP_AND_FEE_AUTHORIZATION_REQUIRED'}
$workSeconds=1080;$stopSeconds=1500;$verifySeconds=1620;$interval=10
if($offline){$interval=1;if($startup.PSObject.Properties.Name -contains 'offline_test_policy'){$workSeconds=[int]$startup.offline_test_policy.work_seconds;$stopSeconds=[int]$startup.offline_test_policy.stop_seconds;$verifySeconds=$stopSeconds+2}}
$absolute=$null
if($startup.PSObject.Properties.Name -contains 'absolute_deadline_utc' -and $startup.absolute_deadline_utc){$absolute=[DateTimeOffset]::Parse($startup.absolute_deadline_utc)}
if(!$offline -and !$absolute){throw 'ABSOLUTE_DEADLINE_REQUIRED'}
$lock=$null;$sleepHeld=$false;$clock=$null;$deadline=$null;$anchor=$null
$seenActive=$false;$failures=0;$stopLatched=$false;$lastStop=[DateTimeOffset]::MinValue;$confirmed=0;$iterations=0;$stopRequests=0;$lastState='UNKNOWN'
function Heartbeat($status){$path=Join-Path $run 'heartbeat.json';if(Test-Path $path -PathType Container){throw 'HEARTBEAT_PATH_IS_DIRECTORY'};Write-AtomicJson $path @{pid=$PID;utc=[DateTimeOffset]::UtcNow.ToString('o');status=$status;offline=$offline;sleep_held=$sleepHeld;stopped_verified=($status -eq 'stopped');running_confirmed=($null -ne $anchor);deadline_utc=$(if($deadline){$deadline.ToString('o')}else{$null});running_confirmed_utc=$(if($anchor){$anchor.ToString('o')}else{$null});consecutive_api_failures=$failures;supervision_stop_latched=$stopLatched;iterations=$iterations;stop_attempts=$stopRequests;last_cloud_state=$lastState}}
function Observe {
 if(!$offline){
  $budget=35000.0
  # Before the cutoff, a status read may not occupy the stop window.
  # After it, bounded reads remain available to verify STOPPED.
  $due=Due
  if($due -and $stopRequests -eq 0 -and $lastState -notin @('STOPPING','STOPPED')){throw 'GUARD_STOP_REQUIRED_BEFORE_OBSERVATION'}
  if(!$due){
   if($absolute){$budget=[Math]::Min($budget,($absolute-[DateTimeOffset]::UtcNow).TotalMilliseconds)}
   if($clock){$budget=[Math]::Min($budget,($stopSeconds-$clock.Elapsed.TotalSeconds)*1000);$budget=[Math]::Min($budget,($deadline-[DateTimeOffset]::UtcNow).TotalMilliseconds)}
  }
  if($budget -lt 1){throw 'GUARD_OBSERVATION_DEADLINE_REACHED'}
  return (Invoke-Bridge status -TimeoutMs ([int][Math]::Floor($budget)))
 }
 $p=Join-Path $run 'simulated-cloud.json';$s=Get-Content $p -Raw|ConvertFrom-JsonUtc
 if($s.PSObject.Properties.Name -contains 'status_failures_remaining' -and $s.status_failures_remaining -gt 0){$s.status_failures_remaining--;Write-AtomicJson $p $s;throw 'SYNTHETIC_API_FAILURE'}
 if($s.state -eq 'STOPPING'){$s.verify_reads++;if($s.verify_reads -ge 2){$s.state='STOPPED';$s.instances=@()};Write-AtomicJson $p $s}
 return @{id=$startup.devlab_id;state=$s.state;instances=$s.instances;project_ownership_verified=$true}
}
function SubmitStop {
 $script:stopRequests++
 if(!$offline){Invoke-Bridge stop -AuthorizedStop|Out-Null;return}
 $p=Join-Path $run 'simulated-cloud.json';$s=Get-Content $p -Raw|ConvertFrom-JsonUtc;$s.state='STOPPING';$s.verify_reads=0;$s.stop_requests++;Write-AtomicJson $p $s
}
function Due {
 if($absolute -and [DateTimeOffset]::UtcNow -ge $absolute){return $true}
 if($stopLatched -or (Test-Path (Join-Path $run 'complete.json')) -or (Test-Path (Join-Path $run 'cancel.json'))){return $true}
 return ($null -ne $clock -and ($clock.Elapsed.TotalSeconds -ge $stopSeconds -or [DateTimeOffset]::UtcNow -ge $deadline))
}
function PauseGuard {
 $milliseconds=$interval*1000.0
 if(!(Due)){
  if($absolute){$milliseconds=[Math]::Min($milliseconds,($absolute-[DateTimeOffset]::UtcNow).TotalMilliseconds)}
  if($clock){$milliseconds=[Math]::Min($milliseconds,($stopSeconds-$clock.Elapsed.TotalSeconds)*1000);$milliseconds=[Math]::Min($milliseconds,($deadline-[DateTimeOffset]::UtcNow).TotalMilliseconds)}
 }
 Start-Sleep -Milliseconds ([int][Math]::Max(1,[Math]::Floor($milliseconds)))
}
function StartRunningClock($observed){
 $script:anchor=[DateTimeOffset]::UtcNow;$script:clock=[Diagnostics.Stopwatch]::StartNew();$script:deadline=$anchor.AddSeconds($stopSeconds)
 if($absolute -and $deadline -gt $absolute){$script:deadline=$absolute}
 $confirmation=@{id=$observed.id;state='RUNNING';instances=@($observed.instances);independent_api=(!$offline);utc=$anchor.ToString('o');timing_policy='RUNNING_ANCHORED_18_25_27'}
 # Exclusive receipt: a repeated RUNNING or process resume must never re-anchor.
 $path=Join-Path $run 'running-confirmation.json';$stream=[IO.File]::Open($path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read)
 try{$bytes=[Text.Encoding]::UTF8.GetBytes(($confirmation|ConvertTo-Json -Depth 8));$stream.Write($bytes,0,$bytes.Length)}finally{$stream.Dispose()}
 $hasher=[Security.Cryptography.SHA256]::Create();$file=[IO.File]::OpenRead($path)
 try{$hash=([BitConverter]::ToString($hasher.ComputeHash($file))).Replace('-','').ToLowerInvariant()}finally{$file.Dispose();$hasher.Dispose()}
 Write-AtomicJson (Join-Path $run 'timing.json') @{t0_utc=$anchor.ToString('o');work_deadline_utc=$(if($deadline.AddSeconds(-120) -lt $anchor.AddSeconds($workSeconds)){$deadline.AddSeconds(-120).ToString('o')}else{$anchor.AddSeconds($workSeconds).ToString('o')});stop_trigger_utc=$deadline.ToString('o');verification_target_utc=$anchor.AddSeconds($verifySeconds).ToString('o');timing_policy='RUNNING_ANCHORED_18_25_27';running_confirmation_sha256=$hash;startup_started_utc=$startup.created_utc}
 Write-AtomicJson (Join-Path $run 'launch.json') @{offline=$offline;single_run=$true;prevent_sleep=(!$offline);launched_utc=$anchor.ToString('o');deadline_utc=$deadline.ToString('o');budget_usd_including_tax=$startup.budget_usd_including_tax;approval_reference=$startup.approval_reference;timing_policy='RUNNING_ANCHORED_18_25_27';running_confirmed_utc=$anchor.ToString('o');running_confirmation_sha256=$hash;startup_started_utc=$startup.created_utc}
}
try {
 $lockRoot=Join-Path $script:ToolRoot '../cloud-runs';New-Item -ItemType Directory -Force $lockRoot|Out-Null
 $lockPath=Join-Path $lockRoot 'devlab.guard.lock';if($offline){$lockPath=Join-Path $run 'offline.guard.lock'}
 $lock=[IO.File]::Open($lockPath,[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
 if(!$offline){Add-Type 'using System;using System.Runtime.InteropServices;public static class TeaRunningPower{[DllImport("kernel32.dll")]public static extern uint SetThreadExecutionState(uint f);}';if([TeaRunningPower]::SetThreadExecutionState(2147483649) -eq 0){throw 'SLEEP_HOLD_FAILED'};$sleepHeld=$true}
 if(Test-Path (Join-Path $run 'running-confirmation.json')){throw 'PRESERVE_RUNNING_ANCHOR_NO_GUARD_REPLAY'}
 Heartbeat 'armed'
 while($true){
  $iterations++;$status='awaiting_running'
  try{
   # Submit a due stop before beginning another potentially slow observation.
   $operation='stop'
   if((Due) -and $lastState -notin @('STOPPING','STOPPED') -and ([DateTimeOffset]::UtcNow-$lastStop).TotalSeconds -ge $interval){$lastStop=[DateTimeOffset]::UtcNow;SubmitStop}
   $operation='observe';$observed=Observe;$failures=0
   if($observed.id -ne $startup.devlab_id -or !$observed.project_ownership_verified){throw 'API_SCOPE_MISMATCH'}
   $lastState=$observed.state
   if($lastState -eq 'RUNNING' -and $null -eq $anchor -and !(Due)){$operation='clock_commit';StartRunningClock $observed;$operation='observe'}
   if($lastState -eq 'STOPPED'){
    if(!$seenActive -and !(Due)){$confirmed=0;$status='ready_waiting_start'}
    else{$confirmed++;$status='verifying_stopped';if($confirmed -ge 2 -and @($observed.instances).Count -eq 0){break}}
   }else{
    $seenActive=$true;$confirmed=0
    if($lastState -notin @('STARTING','PROVISIONING','IMAGE_PULLING','RUNNING','STOPPING')){$stopLatched=$true}
    if(Due){$status='stopping';if($lastState -ne 'STOPPING' -and ([DateTimeOffset]::UtcNow-$lastStop).TotalSeconds -ge $interval){$lastStop=[DateTimeOffset]::UtcNow;SubmitStop}}
    elseif($anchor){$status='running_window'}
   }
  }catch{
   if($offline){[Console]::Error.WriteLine($_.Exception.Message)}
   try{Write-AtomicJson (Join-Path $run ('guard-error-'+[Guid]::NewGuid().ToString('N')+'.json')) @{operation=$operation;exception_type=$_.Exception.GetType().FullName;script_line=$_.InvocationInfo.ScriptLineNumber;utc=[DateTimeOffset]::UtcNow.ToString('o')}}catch{}
   $confirmed=0;$failures++;if($operation -eq 'clock_commit' -or $_.Exception.Message -eq 'API_SCOPE_MISMATCH'){$stopLatched=$true}
   if($failures -ge 3){$stopLatched=$true;Write-AtomicJson (Join-Path $run 'supervision-stop.json') @{reason='THREE_CONSECUTIVE_API_FAILURES';utc=[DateTimeOffset]::UtcNow.ToString('o');restart_allowed=$false}}
   $status='retrying';if((Due) -and ([DateTimeOffset]::UtcNow-$lastStop).TotalSeconds -ge $interval){$lastStop=[DateTimeOffset]::UtcNow;try{SubmitStop}catch{}}
  }
  Heartbeat $status;PauseGuard
 }
 Heartbeat 'awaiting_independent_stopped'
 while($true){
  $p=Join-Path $run 'independent-stopped-release.json'
  if(Test-Path $p){$v=Get-Content $p -Raw|ConvertFrom-JsonUtc;if($v.state -eq 'STOPPED' -and @($v.instances).Count -eq 0 -and ($offline -or ($v.independent_api -eq $true -and $v.id -eq $startup.devlab_id))){break}}
  Start-Sleep -Seconds 1
 }
 if($sleepHeld){[TeaRunningPower]::SetThreadExecutionState(2147483648)|Out-Null;$sleepHeld=$false}
 $settings=Read-Settings;$settings.cloud_stop_enabled=$false;Write-AtomicJson $script:SettingsFile $settings
 Heartbeat 'stopped'
}catch{
 # Diagnostic failures cannot suppress the early-stop latch or stop request.
 try{Write-AtomicJson (Join-Path $run 'complete.json') @{reason='GUARD_FAILURE';stop_required=$true;restart_allowed=$false}}catch{}
 # Stay in stop-only supervision even if evidence writing fails.
 while($true){
  try{$v=Observe;if($v.id -eq $startup.devlab_id -and $v.state -eq 'STOPPED' -and @($v.instances).Count -eq 0){
   $p=Join-Path $run 'independent-stopped-release.json'
   if(Test-Path $p){$release=Get-Content $p -Raw|ConvertFrom-JsonUtc;if($release.state -eq 'STOPPED' -and @($release.instances).Count -eq 0 -and ($offline -or ($release.independent_api -eq $true -and $release.id -eq $startup.devlab_id))){break}}
  }elseif($v.state -ne 'STOPPING'){SubmitStop}}catch{try{SubmitStop}catch{}}
  Start-Sleep -Seconds $interval
 }
}finally{if($sleepHeld){[TeaRunningPower]::SetThreadExecutionState(2147483648)|Out-Null};if($lock){$lock.Dispose()}}
