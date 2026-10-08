# Single entry for the unified guarded runtime. Defaults never access the cloud.
[CmdletBinding()]
param(
    [ValidateSet('Plan','Status','Arm','Capture','ConfirmHost','Transfer','ConfirmStopped')]
    [string]$Action='Plan',
    [switch]$Execute,
    [string]$RunDirectory,
    [double]$ApprovedBudgetUsdIncludingTax=0,
    [string]$ApprovalReference,
    [string]$DeadlineUtc,
    [string]$ExpectedVm,[string]$ExpectedIp,[string]$ExpectedFingerprint,
    [switch]$UserConfirmed,
    [string]$Operation,[string]$ContainerProgramPath,[string]$RequestPath,
    [switch]$UploadArchive,[switch]$DownloadResults
)
$ErrorActionPreference='Stop'
$entries=@{
    Status='Status.ps1'; Arm='Start-TeaRunningGuard.ps1';
    Capture='Wait-CaptureTeaHost.ps1'; ConfirmHost='Confirm-TeaHost.ps1';
    Transfer='Invoke-ScaleRemote.ps1'; ConfirmStopped='Confirm-RunningStopped.ps1'
}
if(!$Execute -or $Action -eq 'Plan'){
    @{runtime='guarded-cosmos';mode='LOCAL_PLAN';action=$Action;cloud_calls=0;
      actions=@('Status','Arm','Capture','ConfirmHost','Transfer','ConfirmStopped')} | ConvertTo-Json
    exit 0
}
if($Action -in @('Capture','ConfirmHost','Transfer','ConfirmStopped') -and !$RunDirectory){throw 'RUN_DIRECTORY_REQUIRED'}
if($Action -eq 'ConfirmHost' -and (!$ExpectedVm -or !$ExpectedIp -or !$ExpectedFingerprint -or !$UserConfirmed)){throw 'EXACT_USER_HOST_CONFIRMATION_REQUIRED'}
if($Action -eq 'Transfer' -and !$Operation){throw 'REMOTE_OPERATION_REQUIRED'}
$entry=Join-Path $PSScriptRoot $entries[$Action]
$accepted=(Get-Command -Name $entry -ErrorAction Stop).Parameters
$forward=@{Execute=$true}
foreach($name in $PSBoundParameters.Keys){
    if($name -ne 'Action' -and $name -ne 'Execute' -and $accepted.ContainsKey($name)){
        $forward[$name]=$PSBoundParameters[$name]
    }
}
$global:LASTEXITCODE=0
& $entry @forward
exit $LASTEXITCODE
