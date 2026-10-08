[CmdletBinding()]
param([switch]$Execute,[switch]$Offline,[double]$ApprovedBudgetUsdIncludingTax=0,[string]$ApprovalReference,[string]$DeadlineUtc)
. (Join-Path $PSScriptRoot 'Common.ps1')
if(!$Execute){@{mode='LOCAL_PLAN';clock_start='FIRST_INDEPENDENT_API_RUNNING';startup_time_limit=$null;work_minutes=18;stop_minutes=25;verification_target_minutes=27;cloud_calls=0}|ConvertTo-Json;exit 0}
if(!$Offline -and ($ApprovedBudgetUsdIncludingTax -le 0 -or !$ApprovalReference)){throw 'EXPLICIT_BUDGET_AUTHORIZATION_REQUIRED'}
if(!$Offline){
 if(!$DeadlineUtc){throw 'FIXED_UTC_DEADLINE_REQUIRED'}
 if($DeadlineUtc -notmatch '(Z|\+00:00)$'){throw 'EXPLICIT_UTC_SUFFIX_REQUIRED'}
 $absolute=[DateTimeOffset]::Parse($DeadlineUtc)
 if($absolute.Offset -ne [TimeSpan]::Zero -or $absolute -le [DateTimeOffset]::UtcNow -or ($absolute-[DateTimeOffset]::UtcNow).TotalSeconds -gt 3600){throw 'FIXED_UTC_DEADLINE_INVALID'}
}
$settings=Read-Settings
if(!$Offline){foreach($field in @('auth_config_path','key_path')){if(!(Test-Path -LiteralPath $settings.$field)){throw 'LOCAL_AUTH_OR_KEY_PATH_MISSING_NO_AUTO_LOGIN'}};if(!(Test-Path -LiteralPath ($settings.key_path+'.pub'))){throw 'LOCAL_PUBLIC_KEY_PATH_MISSING'}}
$root=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'));$run=Join-Path $root ('cloud-runs/'+[Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory $run|Out-Null
$settings.cloud_stop_enabled=$true
Write-AtomicJson (Join-Path $run 'live-settings.json') $settings
Write-AtomicJson (Join-Path $run 'startup.json') @{created_utc=[DateTimeOffset]::UtcNow.ToString('o');offline=[bool]$Offline;single_run=$true;budget_usd_including_tax=$ApprovedBudgetUsdIncludingTax;approval_reference=$ApprovalReference;devlab_id=$settings.devlab_id;timing_policy='RUNNING_ANCHORED_18_25_27';absolute_deadline_utc=$DeadlineUtc;restart_limit=1}
if($Offline){Write-AtomicJson (Join-Path $run 'simulated-cloud.json') @{state='STOPPED';instances=@();verify_reads=0;stop_requests=0}}
$exe=Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0/powershell.exe'
$guard=Join-Path $PSScriptRoot 'TeaRunningGuard.ps1'
$p=Start-Process -FilePath $exe -ArgumentList @('-NoProfile','-File',('"'+$guard+'"'),'-RunDirectory',('"'+$run+'"'),'-Execute') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $run 'guard.stdout.log') -RedirectStandardError (Join-Path $run 'guard.stderr.log')
$watch=[Diagnostics.Stopwatch]::StartNew()
while(!(Test-Path (Join-Path $run 'heartbeat.json')) -and $watch.Elapsed.TotalSeconds -lt 10){if($p.HasExited){throw 'GUARD_SETUP_FAILED'};Start-Sleep -Milliseconds 100}
if(!(Test-Path (Join-Path $run 'heartbeat.json'))){throw 'GUARD_HEARTBEAT_MISSING'}
@{RunDirectory=$run;Pid=$p.Id;timing_created=$false;start_clock='FIRST_RUNNING';restart_called=$false}|ConvertTo-Json
