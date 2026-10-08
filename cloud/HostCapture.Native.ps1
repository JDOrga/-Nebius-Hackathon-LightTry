# All waits, pipe drains and cleanup share one Stopwatch budget.
Set-StrictMode -Version Latest
if (-not ('TeaHostNativeBudget2' -as [type])) {
    Add-Type -Path (Join-Path $PSScriptRoot 'HostCapture.Native.cs')
}
function Invoke-HostNative([string]$Executable,[string[]]$ArgumentList,[int]$TimeoutMs) {
    [TeaHostNativeBudget2]::Run($Executable,$ArgumentList,$TimeoutMs,8192)
}
