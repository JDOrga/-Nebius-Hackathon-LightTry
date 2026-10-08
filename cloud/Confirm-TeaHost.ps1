[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$RunDirectory,
      [Parameter(Mandatory=$true)][string]$ExpectedVm,
      [Parameter(Mandatory=$true)][string]$ExpectedIp,
      [Parameter(Mandatory=$true)][string]$ExpectedFingerprint,
      [switch]$UserConfirmed,[switch]$Execute)
if(!$Execute){@{mode='LOCAL_PLAN';cloud_calls=0;trust_created=$false}|ConvertTo-Json;exit 0}
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'Common.ps1')
if (!$UserConfirmed) { throw 'Exact current host confirmation required.' }
$run=[IO.Path]::GetFullPath($RunDirectory)
if (!(Test-Path -LiteralPath (Join-Path $run 'heartbeat.json'))) { throw 'Current independent guard required.' }
$candidate=Get-Content -LiteralPath (Join-Path $run 'host-candidate.json') -Raw -Encoding UTF8 | ConvertFrom-JsonUtc
if ($candidate.vm_id -ne $ExpectedVm -or $candidate.ip -ne $ExpectedIp -or $candidate.fingerprint -ne $ExpectedFingerprint) { throw 'Candidate differs from human-confirmed exact host.' }
$script:SettingsFile=Join-Path $run 'live-settings.json'
$target=Invoke-Bridge target
if ($target.vm_id -ne $ExpectedVm -or $target.ip -ne $ExpectedIp -or $target.ssh_user -ne $candidate.ssh_user -or $target.host_alias -ne $candidate.host_alias) { throw 'API target differs from confirmed candidate.' }
$key=Join-Path $run 'host-key-candidate.txt'
$fp=@(& ssh-keygen.exe -lf $key -E sha256) -join ' '
if ($LASTEXITCODE -ne 0 -or !$fp.Contains($ExpectedFingerprint)) { throw 'Current public host fingerprint differs.' }
$parts=(Get-Content -LiteralPath $key -Raw -Encoding UTF8).Trim().Split(' ')
if ($parts.Count -ne 3 -or $parts[0] -ne $ExpectedIp -or $parts[1] -ne 'ssh-ed25519') { throw 'Invalid public key candidate.' }
$pin=Join-Path $run 'known_hosts'
if (Test-Path -LiteralPath $pin) { throw 'Preserve existing current pin; no overwrite.' }
[IO.File]::WriteAllText($pin,($target.host_alias+' '+$parts[1]+' '+$parts[2]+[Environment]::NewLine),[Text.UTF8Encoding]::new($false))
Write-AtomicJson (Join-Path $run 'host-trust.json') @{user_confirmed=$true;independently_verified=$false;vm_id=$ExpectedVm;ip=$ExpectedIp;ssh_user=$target.ssh_user;host_alias=$target.host_alias;fingerprint=$ExpectedFingerprint;pin_path=$pin;utc=[DateTimeOffset]::UtcNow.ToString('o')}
$target | ConvertTo-Json -Depth 5
