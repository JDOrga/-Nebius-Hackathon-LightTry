[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$RunDirectory,
      [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{32}$')][string]$SourceRunId,
      [Parameter(Mandatory=$true)][string]$Destination,[switch]$Execute,[switch]$Resume,[switch]$SingleCases)
$ErrorActionPreference='Stop'
if(!$Execute){@{mode='LOCAL_PLAN';cloud_calls=0;parts=@('metadata','pair0','pair1','pair2');maximum_chunk_bytes=163840;transfer_timeout_unchanged=90;maximum_network_attempts_per_part=2;regenerate_cases=$false}|ConvertTo-Json;exit 0}
$root=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
. (Join-Path $root 'cloud/RequestJson.ps1')
$run=[IO.Path]::GetFullPath($RunDirectory)
$dest=[IO.Path]::GetFullPath($Destination)
if(!$run.StartsWith(($root+'\cloud-runs\'),[StringComparison]::OrdinalIgnoreCase) -or
   !$dest.StartsWith(($root+'\.local\'),[StringComparison]::OrdinalIgnoreCase)){throw 'LOCAL_RECOVERY_PATH_REQUIRED'}
if(Test-Path -LiteralPath $dest){if(!$Resume){throw 'PRESERVE_EXISTING_RECOVERY_DIRECTORY'}}
else{New-Item -ItemType Directory -Path $dest | Out-Null}
$settings=Get-Content -LiteralPath (Join-Path $run 'live-settings.json') -Raw -Encoding UTF8|ConvertFrom-JsonUtc
$source=$settings.container_data_dir+'/preview-'+$SourceRunId+'/run'
$transport=Join-Path $root 'cloud/ControlChunkTransport.ps1'
$program=Join-Path $root 'project/experiments/export_chunk.py'
$exe=Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0/powershell.exe'
$records=@()
$parts=@('metadata','pair0','pair1','pair2')
if($SingleCases){$parts=@('metadata','case0','case1','case2','case3','case4','case5')}
foreach($part in $parts){
 $archive=Join-Path $dest ($part+'.tar.gz')
 if(Test-Path -LiteralPath $archive){
  if(!$Resume){throw 'PRESERVE_EXISTING_COMPLETED_CHUNK'}
  $proof=Join-Path $dest ($part+'-download-receipt.json')
  if(!(Test-Path $proof)){ $proof=Join-Path $dest ($part+'-canonical-download-receipt.json') }
  if(!(Test-Path $proof)){throw 'COMPLETED_CHUNK_PROVENANCE_MISSING'}
  $prior=Get-Content $proof -Raw|ConvertFrom-JsonUtc
  if((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $prior.sha256 -or
    (Get-Item -LiteralPath $archive).Length -ne $prior.bytes){throw 'COMPLETED_CHUNK_HASH_MISMATCH_NO_RERUN'}
  Write-Output ($part+' already hash verified; skipped')
  continue
 }
 $request=Join-Path $dest ($part+'-request.json')
 [IO.File]::WriteAllText($request,(@{root=$source;data_root=$settings.container_data_dir;part=$part}|ConvertTo-Json),[Text.UTF8Encoding]::new($false))
 $exported=$false
 for($attempt=1;$attempt -le 2;$attempt++){
  $stdout=Join-Path $dest ($part+'-export-'+$attempt+'.stdout.json')
  $stderr=Join-Path $dest ($part+'-export-'+$attempt+'.stderr.txt')
  $arguments=@('-NoProfile','-File',$transport,'-RunDirectory',$run,'-Operation','export_control_chunk',
    '-SourceRunId',$SourceRunId,'-ControlPart',$part,'-ContainerProgramPath',$program,'-RequestPath',$request,'-Execute')
  $process=Start-Process -FilePath $exe -ArgumentList $arguments -WindowStyle Hidden -PassThru -Wait -RedirectStandardOutput $stdout -RedirectStandardError $stderr
  if($process.ExitCode -eq 0){$exported=$true;break}
  $native=Join-Path $run 'export_control_chunk-native.json'
  if(!(Test-Path $native)){throw 'EXPORT_FAILED_WITHOUT_SAFE_NETWORK_CLASSIFICATION'}
  $diag=Get-Content $native -Raw|ConvertFrom-JsonUtc
  if($diag.cleanup_incomplete -or $diag.remaining_owned_processes -ne 0 -or
    !($diag.status -eq 'PROCESS_TIMEOUT' -or $diag.stderr_categories -contains 'CONNECTION_TIMEOUT')){throw 'NONTRANSIENT_OR_UNCERTAIN_EXPORT_NO_RETRY'}
 }
 if(!$exported){throw 'BOUNDED_EXPORT_ATTEMPTS_EXHAUSTED'}
 Copy-Item -LiteralPath (Join-Path $run 'export_control_chunk-result.json') -Destination (Join-Path $dest ($part+'-export-receipt.json'))
 $metadata=(Get-Content (Join-Path $run 'export_control_chunk-result.json') -Raw|ConvertFrom-JsonUtc).output|ConvertFrom-JsonUtc
 if($metadata.bytes -gt 163840){throw 'RECOVERY_CHUNK_TOO_LARGE'}
 $downloaded=$false
 for($attempt=1;$attempt -le 2;$attempt++){
  $target=Join-Path $run ('control-canonical-'+$SourceRunId+'-'+$part+'.tar.gz')
  if(Test-Path -LiteralPath $target){throw 'UNEXPECTED_PRIOR_DOWNLOAD_PRESERVE'}
  $arguments=@('-NoProfile','-File',$transport,'-RunDirectory',$run,'-Operation','download_control_chunk',
    '-SourceRunId',$SourceRunId,'-ControlPart',$part,'-DownloadResults','-Execute')
  $process=Start-Process -FilePath $exe -ArgumentList $arguments -WindowStyle Hidden -PassThru -Wait -RedirectStandardOutput (Join-Path $dest ($part+'-download-'+$attempt+'.stdout.txt')) -RedirectStandardError (Join-Path $dest ($part+'-download-'+$attempt+'.stderr.txt'))
  if($process.ExitCode -eq 0){$downloaded=$true;break}
  if(Test-Path -LiteralPath $target){Move-Item -LiteralPath $target -Destination (Join-Path $dest ($part+'-failed-attempt-'+$attempt+'.partial.tar.gz'))}
  $diag=Get-Content (Join-Path $run 'download_control_chunk-native.json') -Raw|ConvertFrom-JsonUtc
  if($diag.cleanup_incomplete -or $diag.remaining_owned_processes -ne 0 -or
    !($diag.status -eq 'PROCESS_TIMEOUT' -or $diag.stderr_categories -contains 'CONNECTION_TIMEOUT')){throw 'NONTRANSIENT_OR_UNCERTAIN_DOWNLOAD_NO_RETRY'}
 }
 if(!$downloaded){throw 'BOUNDED_DOWNLOAD_ATTEMPTS_EXHAUSTED'}
 Move-Item -LiteralPath $target -Destination $archive
 Copy-Item -LiteralPath (Join-Path $run 'result-download-receipt.json') -Destination (Join-Path $dest ($part+'-download-receipt.json'))
 $records+=@{part=$part;bytes=$metadata.bytes;sha256=$metadata.sha256;source_run_id=$SourceRunId;current_guard_run_id=(Split-Path $run -Leaf);archive=$archive}
 [IO.File]::WriteAllText((Join-Path $dest 'chunks.json'),($records|ConvertTo-Json -Depth 6),[Text.UTF8Encoding]::new($false))
 Write-Output ($part+' verified '+$metadata.bytes+' bytes')
}
