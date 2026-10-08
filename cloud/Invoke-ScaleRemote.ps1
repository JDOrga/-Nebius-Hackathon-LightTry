[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$RunDirectory,
      [Parameter(Mandatory=$true)][string]$Operation,
      [string]$ContainerProgramPath,[string]$RequestPath,[switch]$UploadArchive,[switch]$DownloadResults,[switch]$Execute)
if(!$Execute){@{mode='LOCAL_PLAN';cloud_calls=0}|ConvertTo-Json;exit 0}
$ErrorActionPreference='Stop'
function RuntimeDigest([string]$Path){
 $h=[Security.Cryptography.SHA256]::Create();$f=[IO.File]::OpenRead($Path)
 try{([BitConverter]::ToString($h.ComputeHash($f))).Replace('-','').ToLowerInvariant()}finally{$f.Dispose();$h.Dispose()}
}

$original=$PSScriptRoot
. (Join-Path $original 'Common.ps1')
$run=[IO.Path]::GetFullPath($RunDirectory)
$root=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if (!$run.StartsWith(($root+'\cloud-runs\'),[StringComparison]::OrdinalIgnoreCase)) { throw 'Run outside workspace.' }
$trust=Get-Content -LiteralPath (Join-Path $run 'host-trust.json') -Raw -Encoding UTF8 | ConvertFrom-JsonUtc
if (!$trust.user_confirmed) { throw 'Fresh host approval is required.' }
$script:SettingsFile=Join-Path $run 'live-settings.json'
$snapshot=Read-Settings
$beat=Get-Content (Join-Path $run 'heartbeat.json') -Raw | ConvertFrom-JsonUtc
$receipt=Get-Content (Join-Path $run 'launch.json') -Raw | ConvertFrom-JsonUtc
if($receipt.offline -or !$receipt.single_run -or $receipt.budget_usd_including_tax -le 0 -or !$receipt.approval_reference -or $beat.offline -or !$beat.sleep_held -or $beat.stopped_verified -or ([DateTimeOffset]::UtcNow-[DateTimeOffset]::Parse($beat.utc)).TotalSeconds -gt 30 -or !(Get-Process -Id $beat.pid -ErrorAction SilentlyContinue)){throw 'LIVE_BUDGET_GUARD_REQUIRED'}
$snapshot.known_hosts_path=$trust.pin_path
$script:SettingsFile=Join-Path $run 'interactive-settings.json'
Write-AtomicJson $script:SettingsFile $snapshot
$target=Invoke-Bridge target
if ($target.vm_id -ne $trust.vm_id -or $target.ip -ne $trust.ip) { throw 'API target changed from approved host.' }
$receipt=Get-Content -LiteralPath (Join-Path $run 'launch.json') -Raw -Encoding UTF8 | ConvertFrom-JsonUtc
if ($Operation -in @('launch','install_bundle','upload_directory') -or $UploadArchive) {
    $cutoff=[DateTimeOffset]::Parse($receipt.launched_utc).AddMinutes(18)
} else { $cutoff=[DateTimeOffset]::Parse($receipt.deadline_utc).AddSeconds(-60) }
if ([DateTimeOffset]::UtcNow -ge $cutoff) { throw 'Fixed operation cutoff reached; persist evidence and stop.' }
$timing=Get-Content (Join-Path $run 'timing.json') -Raw | ConvertFrom-JsonUtc
$workLimit=[DateTimeOffset]::Parse($timing.work_deadline_utc)
if($Operation -in @('launch','install_bundle','upload_directory') -or $UploadArchive){if($workLimit -lt $cutoff){$cutoff=$workLimit}}
if($cutoff -gt [DateTimeOffset]::Parse($receipt.deadline_utc)){$cutoff=[DateTimeOffset]::Parse($receipt.deadline_utc)}
$script:RemoteDeadline=$cutoff
$argsList=Get-SshArguments $target
$fresh=Invoke-Bridge target
if ($fresh.vm_id -ne $target.vm_id -or $fresh.ip -ne $target.ip -or $fresh.ssh_user -ne $target.ssh_user -or $fresh.image -ne $target.image) { throw 'API target changed before SSH.' }
$bundle=Get-Content -LiteralPath (Join-Path $run 'bundle.json') -Raw -Encoding UTF8 | ConvertFrom-JsonUtc
$archive=$bundle.archive_path
if($bundle.archive -ne 'inference-code.tar.gz' -or [IO.Path]::GetFullPath($archive) -ne [IO.Path]::GetFullPath((Join-Path $run 'inference-code.tar.gz'))){throw 'BUNDLE_MUST_BE_CURRENT_RUN_CODE_ARCHIVE'}
$hash=$bundle.sha256

if ($DownloadResults) {
    $export=Get-Content -LiteralPath (Join-Path $run 'export_results-result.json') -Raw -Encoding UTF8 | ConvertFrom-JsonUtc
    $metadata=$export.output | ConvertFrom-JsonUtc
    $expected='/home/'+$target.ssh_user+'/nebius-upload-'+(Split-Path $run -Leaf)+'/batch-results-fast.tar.gz'
    if ($metadata.remote_path -ne $expected) { throw 'Unexpected results export path.' }
    $dest=Join-Path $run 'results.tar.gz'
    if (Test-Path -LiteralPath $dest) { throw 'Preserve existing download.' }
    $scpArgs=@($argsList[0..($argsList.Count-3)])+@(($target.ssh_user+'@'+$target.ip+':'+$expected),$dest)
    $transfer=Invoke-BoundedTransfer 'scp.exe' $scpArgs
    $code=$transfer.ExitCode
    if ($code -ne 0) { throw ('RESULT_SCP_FAILED_EXIT_'+$code) }
    if ((RuntimeDigest $dest) -ne $metadata.sha256) { throw 'RESULT_ARCHIVE_HASH_MISMATCH' }
    Write-AtomicJson (Join-Path $run 'result-download-receipt.json') @{sha256=$metadata.sha256;local_path=$dest;bytes=$metadata.bytes;utc=[DateTimeOffset]::UtcNow.ToString('o')}
    $dest
    exit 0
}

if ($UploadArchive) {
    if ((RuntimeDigest $archive) -ne $hash) { throw 'Archive hash changed.' }
    $remote='/home/'+$target.ssh_user+'/nebius-upload-'+(Split-Path $run -Leaf)+'/'+$bundle.archive
    $scpArgs=@($argsList[0..($argsList.Count-3)])+@($archive,($target.ssh_user+'@'+$target.ip+':'+$remote))
    $transfer=Invoke-BoundedTransfer 'scp.exe' $scpArgs
    $code=$transfer.ExitCode
    if ($code -ne 0) { throw ('SCP_FAILED_EXIT_'+$code) }
    Write-AtomicJson (Join-Path $run 'upload-receipt.json') @{vm_id=$target.vm_id;archive_sha256=$hash;archive_filename=$bundle.archive;remote_path=$remote;utc=[DateTimeOffset]::UtcNow.ToString('o')}
    exit 0
}
$nonce=[Guid]::NewGuid().ToString('N')
$request=@{nonce=$nonce;operation=$Operation;image=$target.image;ssh_user=$target.ssh_user;
    run_id=(Split-Path $run -Leaf);container_python=$snapshot.container_python;archive_sha256=$hash;archive_filename=$bundle.archive;
    probe_source=(ConvertTo-Base64 (Get-Content -LiteralPath (Join-Path $original 'remote_probe.py') -Raw -Encoding UTF8))}
if ($ContainerProgramPath) { $request.container_program=ConvertTo-Base64 (Get-Content -LiteralPath $ContainerProgramPath -Raw -Encoding UTF8) }
. (Join-Path $PSScriptRoot 'RequestJson.ps1')
if ($RequestPath) { $jsonText=Get-Content -LiteralPath $RequestPath -Raw -Encoding UTF8; $request.container_request=ConvertFrom-RequestJson $jsonText; if($request.container_request.PSObject.Properties.Name -contains 'deadline_utc') { $requested=[DateTimeOffset]::Parse($request.container_request.deadline_utc); $timing=Get-Content (Join-Path $run 'timing.json') -Raw | ConvertFrom-JsonUtc; if($requested.Offset -ne [TimeSpan]::Zero -or $requested -gt [DateTimeOffset]::Parse($timing.work_deadline_utc) -or $requested -le [DateTimeOffset]::UtcNow){throw 'REQUEST_OUTSIDE_FIXED_WORK_WINDOW'} } }
if($Operation -eq 'launch'){if(!$RequestPath){throw 'LAUNCH_REQUEST_REQUIRED'};$request.container_request | Add-Member -NotePropertyName guard_launch_receipt -NotePropertyValue $receipt -Force}
$program=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'experiment_vm_bridge.py') -Raw -Encoding UTF8
$command=New-EncodedShellCommand $program (ConvertTo-Base64 ($request | ConvertTo-Json -Depth 8 -Compress))
if ($command.Length -gt 28000) { throw 'Native command too large.' }
$output=Invoke-NativeSshCommand $argsList $command (Join-Path $run ($Operation+'-native.json'))
$result=Read-RemoteResult $output $nonce $Operation $target.image
Write-AtomicJson (Join-Path $run ($Operation+'-result.json')) $result
$result | ConvertTo-Json -Depth 6
