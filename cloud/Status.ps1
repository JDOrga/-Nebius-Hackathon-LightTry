[CmdletBinding()]
param([switch]$Execute)
if (!$Execute) { @{mode='LOCAL_PLAN';cloud_calls=0}|ConvertTo-Json;exit 0 }
. (Join-Path $PSScriptRoot 'Common.ps1')
Invoke-Bridge status | ConvertTo-Json -Depth 8
