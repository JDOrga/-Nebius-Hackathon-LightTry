[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$RunDirectory,
      [Parameter(Mandatory=$true)][string]$RequestPath,[switch]$Execute)
if(!$Execute){@{mode='LOCAL_PLAN';API_calls=0;ssh_sessions=0;progress='single-ssh-status-stream-v1'}|ConvertTo-Json;exit 0}
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'Common.ps1')
$run=[IO.Path]::GetFullPath($RunDirectory)
$root=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if(!$run.StartsWith(($root+'\cloud-runs\'),[StringComparison]::OrdinalIgnoreCase)){throw 'RUN_OUTSIDE_WORKSPACE'}
$trust=Get-Content (Join-Path $run 'host-trust.json') -Raw|ConvertFrom-JsonUtc
$beat=Get-Content (Join-Path $run 'heartbeat.json') -Raw|ConvertFrom-JsonUtc
$receipt=Get-Content (Join-Path $run 'launch.json') -Raw|ConvertFrom-JsonUtc
if(!$trust.user_confirmed -or $receipt.offline -or !$receipt.single_run -or $receipt.budget_usd_including_tax -le 0 -or !$receipt.approval_reference -or $beat.offline -or !$beat.sleep_held -or $beat.stopped_verified -or $beat.supervision_stop_latched -or ([DateTimeOffset]::UtcNow-[DateTimeOffset]::Parse($beat.utc)).TotalSeconds -gt 30 -or !(Get-Process -Id $beat.pid -ErrorAction SilentlyContinue)){throw 'LIVE_BUDGET_GUARD_REQUIRED'}
$timing=Get-Content (Join-Path $run 'timing.json') -Raw|ConvertFrom-JsonUtc
$script:RemoteDeadline=[DateTimeOffset]::Parse($timing.work_deadline_utc)
$stopLimit=[DateTimeOffset]::Parse($receipt.deadline_utc).AddSeconds(-60)
if($stopLimit -lt $script:RemoteDeadline){$script:RemoteDeadline=$stopLimit}
if([DateTimeOffset]::UtcNow -ge $script:RemoteDeadline){throw 'FIXED_WORK_WINDOW_ENDED'}
$snapshot=Get-Content (Join-Path $run 'live-settings.json') -Raw|ConvertFrom-JsonUtc
$snapshot.known_hosts_path=$trust.pin_path
$script:SettingsFile=Join-Path $run 'bundle-interactive-settings.json'
Write-AtomicJson $script:SettingsFile $snapshot
# One pre-transfer API identity validation. No API/SSH loop per image.
$target=Invoke-Bridge target
if($target.vm_id -ne $trust.vm_id -or $target.ip -ne $trust.ip){throw 'API_TARGET_CHANGED_FROM_APPROVED_HOST'}
$sshArgs=Get-SshArguments $target
$q=Get-Content $RequestPath -Raw|ConvertFrom-JsonUtc
$watchNonce=[Guid]::NewGuid().ToString('N')
$q | Add-Member -NotePropertyName watchNonce -NotePropertyValue $watchNonce
$q | Add-Member -NotePropertyName runId -NotePropertyValue (Split-Path $run -Leaf)
$q | Add-Member -NotePropertyName deadlineUtc -NotePropertyValue $script:RemoteDeadline.ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ss.ffffffzzz',[Globalization.CultureInfo]::InvariantCulture)
$req=@{image=$target.image;ssh_user=$target.ssh_user;container_python=$snapshot.container_python;container_request=$q;
 probe_source=(ConvertTo-Base64 (Get-Content (Join-Path $PSScriptRoot 'remote_probe.py') -Raw));
 container_program=(ConvertTo-Base64 (Get-Content (Join-Path $root 'project/next/runtime/joint_watch.py') -Raw))}
$program=Get-Content (Join-Path $PSScriptRoot 'joint_watch_bridge.py') -Raw
$command=New-EncodedShellCommand $program (ConvertTo-Base64 ($req|ConvertTo-Json -Depth 8 -Compress))
if($command.Length -gt 28000){throw 'NATIVE_COMMAND_TOO_LARGE'}
$exe=(Get-Command ssh.exe -CommandType Application -ErrorAction Stop|Select-Object -First 1).Source
$record=@{executable=$exe;arguments=@($sshArgs)+@($command);watchNonce=$watchNonce;taskId=$q.taskId;nonce=$q.nonce;deadlineUtc=$q.deadlineUtc;deadlineUtcOriginal=$script:RemoteDeadline.ToString('o');wireFractionDigits=6;sshSessionsTarget=1;reconnectAllowed=$false}
$path=Join-Path $run 'watch-command.json'
if(Test-Path $path){throw 'PRESERVE_EXISTING_WATCH_NO_RECONNECT'}
Write-AtomicJson $path $record
@{prepared=$true;sshSessionsTarget=1;cloudTargetPrecheck=1;reconnectAllowed=$false}|ConvertTo-Json
