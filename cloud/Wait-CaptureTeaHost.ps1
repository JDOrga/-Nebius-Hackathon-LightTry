[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$RunDirectory,[switch]$Execute)
. (Join-Path $PSScriptRoot 'RequestJson.ps1')
$ErrorActionPreference='Stop'
if(!$Execute){@{mode='LOCAL_PLAN';wait='STARTING_WITHOUT_EXPERIMENT_TIMER';capture='AFTER_RUNNING_CONFIRMATION';cloud_calls=0}|ConvertTo-Json;exit 0}
$run=[IO.Path]::GetFullPath($RunDirectory)
try{
 while(!(Test-Path (Join-Path $run 'launch.json'))){
  if((Test-Path (Join-Path $run 'complete.json')) -or (Test-Path (Join-Path $run 'cancel.json'))){throw 'STARTUP_CANCELLED_OR_STOP_REQUIRED'}
  $start=Get-Content (Join-Path $run 'startup.json') -Raw|ConvertFrom-JsonUtc
  if([DateTimeOffset]::UtcNow -ge [DateTimeOffset]::Parse($start.absolute_deadline_utc)){throw 'ABSOLUTE_STARTUP_DEADLINE_REACHED'}
  $b=Get-Content (Join-Path $run 'heartbeat.json') -Raw|ConvertFrom-JsonUtc
  if($b.offline -or !$b.sleep_held -or $b.status -eq 'failed' -or $b.supervision_stop_latched -or $null -eq (Get-Process -Id $b.pid -ErrorAction SilentlyContinue) -or ([DateTimeOffset]::UtcNow-[DateTimeOffset]::Parse($b.utc)).TotalSeconds -gt 60){throw 'STARTUP_SUPERVISION_UNAVAILABLE'}
  Start-Sleep -Seconds 2
 }
 $launch=Get-Content (Join-Path $run 'launch.json') -Raw|ConvertFrom-JsonUtc
 $proof=Get-Content (Join-Path $run 'running-confirmation.json') -Raw|ConvertFrom-JsonUtc
 $hasher=[Security.Cryptography.SHA256]::Create();$file=[IO.File]::OpenRead((Join-Path $run 'running-confirmation.json'))
 try{$hash=([BitConverter]::ToString($hasher.ComputeHash($file))).Replace('-','').ToLowerInvariant()}finally{$file.Dispose();$hasher.Dispose()}
 if($launch.timing_policy -ne 'RUNNING_ANCHORED_18_25_27' -or $proof.state -ne 'RUNNING' -or !$proof.independent_api -or $proof.id -ne (Get-Content (Join-Path $run 'live-settings.json') -Raw | ConvertFrom-JsonUtc).devlab_id -or $hash -ne $launch.running_confirmation_sha256){throw 'RUNNING_ANCHOR_INVALID'}
 & (Join-Path $PSScriptRoot 'Capture-TeaHost.ps1') -RunDirectory $run -Execute
 exit $LASTEXITCODE
}catch{
 $label=$_.Exception.Message;if($label -notmatch '^[A-Z0-9_]+$'){$label='RUNNING_WAIT_LOCAL_FAILURE'}
 try{[IO.File]::WriteAllText((Join-Path $run 'complete.json'),('{"reason":"'+$label+'","stop_required":true,"restart_allowed":false}'))}catch{}
 throw $label
}
