[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$RunDirectory,[switch]$Execute)
if(!$Execute){@{mode='LOCAL_PLAN';cloud_calls=0}|ConvertTo-Json;exit 0}
# Independent supervisor verification. Never releases solely from a stop request.
. (Join-Path $PSScriptRoot 'Common.ps1')
$script:SettingsFile=Join-Path $RunDirectory 'live-settings.json'
$launch=Get-Content -LiteralPath (Join-Path $RunDirectory 'startup.json') -Raw -Encoding UTF8 | ConvertFrom-JsonUtc
if ($launch.offline -or !$launch.single_run -or $launch.budget_usd_including_tax -le 0 -or !$launch.approval_reference) {
    throw 'Current explicit single-run authorization receipt required.'
}
$id=(Read-Settings).devlab_id
for ($attempt=1; $attempt -le 3; $attempt++) {
    try {
        $state=Invoke-Bridge status
        Write-AtomicJson (Join-Path $RunDirectory ('independent-state-'+[Guid]::NewGuid().ToString('N')+'.json')) @{
            independent_api=$true;status=$state;utc=[DateTimeOffset]::UtcNow.ToString('o')}
        if ($state.id -eq $id -and $state.state -eq 'STOPPED' -and @($state.instances).Count -eq 0) {
            $release=@{state='STOPPED';id=$id;instances=@();independent_api=$true;utc=[DateTimeOffset]::UtcNow.ToString('o')}
            Write-AtomicJson (Join-Path $RunDirectory 'independent-stopped-release.json') $release
            $release | ConvertTo-Json
            exit 0
        }
    } catch { }
    if ($attempt -lt 3) { Start-Sleep -Seconds (5*$attempt) }
}
# No release receipt on unresolved state. Keep the independent guard armed.
Invoke-Bridge stop -AuthorizedStop | Out-Null
throw 'STOPPED with empty instances still unverified; stop requested again, retain supervision and notify user.'
