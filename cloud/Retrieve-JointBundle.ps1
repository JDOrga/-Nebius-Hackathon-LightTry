[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$RunDirectory,
      [Parameter(Mandatory=$true)][string]$RequestPath,[switch]$Execute)
if(!$Execute){@{mode='LOCAL_PLAN';API_calls=0;ssh_sessions=0;retrieval='terminal-single-ssh-v1'}|ConvertTo-Json;exit 0}
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
$dest=Join-Path $run 'joint-results.tar.gz'
if(Test-Path $dest){throw 'PRESERVE_EXISTING_DOWNLOAD'}
$nonce=[Guid]::NewGuid().ToString('N')
$req=@{nonce=$nonce;image=$target.image;ssh_user=$target.ssh_user;run_id=(Split-Path $run -Leaf);container_python=$snapshot.container_python;
 container_request=$q;probe_source=(ConvertTo-Base64 (Get-Content (Join-Path $PSScriptRoot 'remote_probe.py') -Raw));
 container_program=(ConvertTo-Base64 (Get-Content (Join-Path $root 'project/runtime/joint_bundle.py') -Raw))}
$program=Get-Content (Join-Path $PSScriptRoot 'joint_bundle_bridge.py') -Raw
$command=New-EncodedShellCommand $program (ConvertTo-Base64 ($req|ConvertTo-Json -Depth 8 -Compress))
if($command.Length -gt 28000){throw 'NATIVE_COMMAND_TOO_LARGE'}
$output=Invoke-NativeSshCommand $sshArgs $command (Join-Path $run 'retrieve_joint_bundle-native.json') -Context @{operation='retrieve_joint_bundle';ssh_sessions=1}
$result=Read-RemoteResult $output $nonce 'retrieve_joint_bundle' $target.image
$metadata=$result.output|ConvertFrom-JsonUtc
if($metadata.taskId -ne $q.taskId -or $metadata.nonce -ne $q.nonce -or $metadata.bytes -le 0 -or $metadata.bytes -gt 716800 -or $metadata.sha256 -notmatch '^[0-9a-f]{64}$'){throw 'BUNDLE_RESPONSE_IDENTITY_MISMATCH'}
$data=[Convert]::FromBase64String($metadata.dataBase64)
if($data.Length -ne $metadata.bytes){throw 'BUNDLE_FRAME_BYTES_MISMATCH'}
$temp=$dest+'.partial'
if(Test-Path $temp){throw 'PRESERVE_EXISTING_PARTIAL_DOWNLOAD'}
[IO.File]::WriteAllBytes($temp,$data);Move-Item -LiteralPath $temp -Destination $dest
# Local content SHA/decode checks happen once in the Python consumer.
$record=@{taskId=$metadata.taskId;nonce=$metadata.nonce;sha256=$metadata.sha256;bytes=$metadata.bytes;local_path=$dest;ssh_sessions=1;pretransfer_api_validations=1}
Write-AtomicJson (Join-Path $run 'retrieve_joint_bundle-result.json') $record
$record|ConvertTo-Json
