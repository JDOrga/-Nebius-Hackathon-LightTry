. (Join-Path $PSScriptRoot 'RequestJson.ps1')
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$script:ToolRoot = $PSScriptRoot
$script:SettingsFile = Join-Path $PSScriptRoot '../config/local.json'
if ($env:NEBIUS_LOCAL_CONFIG) { $script:SettingsFile = $env:NEBIUS_LOCAL_CONFIG }

function Read-Settings {
    if (!(Test-Path -LiteralPath $script:SettingsFile)) { throw 'LOCAL_CONFIG_MISSING_NO_AUTO_LOGIN' }
    $text=Get-Content -LiteralPath $script:SettingsFile -Raw -Encoding UTF8
    if ((Get-Command ConvertFrom-Json).Parameters.ContainsKey('DateKind')) { $text | ConvertFrom-Json -DateKind String } else { $text | ConvertFrom-JsonUtc }
}
function ConvertTo-WslPath([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    if ($full -notmatch '^([A-Za-z]):\\(.*)$') { throw 'Only Windows drive paths are supported.' }
    '/mnt/' + $Matches[1].ToLowerInvariant() + '/' + $Matches[2].Replace('\','/')
}
function ConvertTo-Base64([string]$Text) {
    [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($Text))
}
function New-EncodedShellCommand([string]$Program, [string]$Arguments = '') {
    # Single quotes survive the Windows PowerShell 5.1 native argument layer.
    $encoded = ConvertTo-Base64 $Program
    if ($Arguments -and $Arguments -notmatch '^[A-Za-z0-9+/= ]+$') { throw 'Unsafe encoded argument.' }
    "printf '%s' '$encoded' | base64 -d | python3 - $Arguments".TrimEnd()
}
function Invoke-Bridge([ValidateSet('local','status','target','host-target','stop')][string]$Action, [switch]$AuthorizedStop) {
    $settings = Read-Settings
    if ($Action -eq 'local') { return @{mode='OFFLINE';cloud_calls=0;config_present=$true} }
    if ($Action -eq 'stop' -and (!$AuthorizedStop -or !$settings.cloud_stop_enabled)) { throw 'Cloud stop is disabled for this preparation.' }
    if (!(Test-Path -LiteralPath $settings.auth_config_path)) { throw 'LOCAL_AUTH_PATH_MISSING_NO_AUTO_LOGIN' }
    $arguments = @('-d',$settings.wsl_distro,'--','python3',
                   (ConvertTo-WslPath (Join-Path $script:ToolRoot 'cli_bridge.py')),
                   '--settings',(ConvertTo-WslPath $script:SettingsFile),'--action',$Action,'--execute')
    if ($Action -in @('target','host-target')) { $arguments += @('--public-key-file',(ConvertTo-WslPath ($settings.key_path+'.pub'))) }
    if ($AuthorizedStop) { $arguments += '--authorized-stop' }
    # PS5.1 wraps native stderr as ErrorRecord and can throw before exit-code handling.
    $savedErrorAction=$ErrorActionPreference
    try {
        $ErrorActionPreference='Continue'
        $raw = @(& wsl.exe @arguments 2>&1)
        $exitCode=$LASTEXITCODE
    } finally { $ErrorActionPreference=$savedErrorAction }
    if ($exitCode -ne 0) {
        $safeError = ($raw -join "`n")
        if ($safeError -match 'LOGIN_REQUIRED_NO_LOCAL_PROFILE_CONFIG') { throw 'Login required: LOCAL local Nebius profile is not configured.' }
        if ($safeError -match 'PROJECT_ID_OR_TENANT_MISMATCH') { throw 'The API project identity or owning tenant differs from the verified target. No cloud action or SSH connection was attempted.' }
        if ($safeError -match 'PROFILE_PROJECT_MISMATCH') { throw 'LOCAL profile project differs from the specified target project. No API or login was attempted; confirm the project context first.' }
        if ($safeError -match 'CLI_SERVER_UNAUTHENTICATED_EXIT_7') { throw 'Nebius rejected current authentication (Unauthenticated, CLI exit 7). Check account, tenant and federation context; browser login success alone does not verify API authentication. No configuration was changed.' }
        if ($safeError -match 'CLI_AUTH_REQUIRED_EXIT_7') { throw 'Current LOCAL API authentication is unavailable (CLI exit 7). Check account, tenant and federation context before another login attempt; no configuration was changed.' }
        if ($safeError -match 'CLI_PERMISSION_DENIED_EXIT_15') { throw 'Current LOCAL authentication cannot access the requested resource (CLI exit 15, permission denied). Verify account and project permissions; no configuration was changed.' }
        if ($safeError -match '"error"\s*:\s*"([A-Z0-9_]+)"') { throw ('Nebius bridge: '+$Matches[1]) }
        throw 'Nebius bridge failed. Check WSL/CLI locally; raw diagnostics suppressed.'
    }
    try { ($raw -join "`n") | ConvertFrom-JsonUtc } catch { throw 'Bridge returned invalid JSON.' }
}
function Test-PublicKey {
    $settings = Read-Settings
    $publicKey = $settings.key_path + '.pub'
    if (!(Test-Path -LiteralPath $publicKey)) { throw 'LOCAL public key is missing.' }
    $fingerprint = @(& ssh-keygen.exe -lf $publicKey -E sha256 2>&1) -join ' '
    if ($LASTEXITCODE -ne 0 -or !$fingerprint.Contains($settings.public_key_fingerprint)) { throw 'LOCAL public key fingerprint mismatch.' }
    $true
}
function Get-SshArguments($Target, [switch]$Interactive, [switch]$PromptForKey) {
    $settings = Read-Settings
    Test-PublicKey | Out-Null
    if (!(Test-Path -LiteralPath $settings.key_path)) { throw 'LOCAL private key is missing or inaccessible; contents are never read by these scripts.' }
    if ($Target.ip -notmatch '^[0-9a-fA-F:.]+$' -or $Target.ssh_user -notmatch '^[a-z_][a-z0-9_-]{0,31}$' -or
        $Target.host_alias -notmatch '^nebius-devlab-[a-z0-9]+-computeinstance-[a-z0-9]+$') { throw 'Invalid validated SSH target.' }
    if (!(Test-Path -LiteralPath $settings.known_hosts_path)) { throw ('Host trust required for current VM alias '+$Target.host_alias+'. Independently verify its host key before adding a matching known_hosts entry.') }
    $trust = @(& ssh-keygen.exe -F $Target.host_alias -f $settings.known_hosts_path 2>&1)
    if ($LASTEXITCODE -ne 0 -or !$trust) { throw ('No verified host entry for '+$Target.host_alias+'. Restarted VMs require new trust.') }
    $arguments = @('-F','NUL','-i',$settings.key_path,'-o','IdentitiesOnly=yes',
       '-o','StrictHostKeyChecking=yes','-o',('UserKnownHostsFile="'+$settings.known_hosts_path+'"'),
       '-o','GlobalKnownHostsFile=NUL','-o',('HostKeyAlias='+$Target.host_alias),
       '-o','UpdateHostKeys=no','-o','PasswordAuthentication=no','-o','KbdInteractiveAuthentication=no',
       '-o','ConnectTimeout=12','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=3',
       '-o','ForwardAgent=no','-o','ClearAllForwardings=yes')
    if (!$Interactive -and !$PromptForKey) { $arguments += @('-o','BatchMode=yes') }
    if ($Interactive) { $arguments += '-t' } else { $arguments += '-T' }
    $arguments += ($Target.ssh_user+'@'+$Target.ip)
    return ,$arguments
}
function Read-RemoteResult([string]$Output, [string]$Nonce, [string]$Operation, [string]$Image) {
    $lines = @($Output -split '\r?\n' | Where-Object { $_ -ne '' })
    $prefix = 'LOCAL_RESULT_'+$Nonce+':'
    $resultLines = @($lines | Where-Object { $_.StartsWith($prefix) })
    $doneLines = @($lines | Where-Object { $_ -eq ('LOCAL_DONE_'+$Nonce) })
    if ($resultLines.Count -ne 1 -or $doneLines.Count -ne 1 -or $lines[-1] -ne ('LOCAL_DONE_'+$Nonce)) { throw 'Remote completion marker missing, duplicated or out of order.' }
    try { $result = $resultLines[0].Substring($prefix.Length) | ConvertFrom-JsonUtc } catch { throw 'Remote JSON is incomplete or invalid.' }
    if ($result.nonce -ne $Nonce -or $result.operation -ne $Operation -or $result.image -ne $Image -or
        $result.container_id -notmatch '^[0-9a-f]{64}$' -or $result.container_user -ne 'jovyan' -or
        $result.container_home -ne '/home/jovyan') { throw 'Remote JSON identity validation failed.' }
    if ($Operation -eq 'probe') {
        $identity = $result.output | ConvertFrom-JsonUtc
        if ($identity.user -ne 'jovyan' -or $identity.cwd -ne '/home/jovyan' -or $identity.home -ne '/home/jovyan') { throw 'Container user/home check failed.' }
    }
    $result
}
function Invoke-BoundedTransfer([string]$Executable,[string[]]$Arguments) {
    if (!$script:RemoteDeadline) { throw 'FIXED_REMOTE_DEADLINE_REQUIRED' }
    $budget=[int][Math]::Min(90000,($script:RemoteDeadline-[DateTimeOffset]::UtcNow).TotalMilliseconds)
    if($budget -le 0){throw 'FIXED_REMOTE_DEADLINE_REACHED'}
    . (Join-Path $PSScriptRoot 'HostCapture.Native.ps1')
    $native=Get-Command $Executable -CommandType Application -ErrorAction Stop
    $r=[TeaHostNativeBudget2]::Run($native.Source,$Arguments,$budget,1048576)
    if(!$r.Started -or $r.TimedOut -or $r.CleanupIncomplete -or !$r.OutputComplete -or $r.Truncated -or $r.ReadFailed -or $r.ExitCode -ne 0){
        $failure=[Exception]::new('BOUNDED_TRANSFER_FAILED_OUTPUT_NOT_ACCEPTED')
        $failure.Data['native_summary']=@{status=$r.Status;exit_code=$r.ExitCode;started=$r.Started;timed_out=$r.TimedOut;output_complete=$r.OutputComplete;truncated=$r.Truncated;read_failed=$r.ReadFailed;cleanup_incomplete=$r.CleanupIncomplete;elapsed_ms=$r.ElapsedMs;public_failure_labels=@($r.Stderr -split '\r?\n'|Where-Object {$_ -match '^(CONTAINER_STAGE_FAILED_EXIT_[0-9]+|SMOKE_[A-Z0-9_]{1,110}|VM_[A-Z0-9_]{1,110}|DOCKER_QUERY_FAILED|NO_VALID_RUNNING_CONTAINERS|CONTAINER_MATCH_NOT_UNIQUE|INVALID_ARCHIVE_NAME)$'});raw_output_saved=$false}
        throw $failure
    }
    return $r
}
function Invoke-NativeSshCommand([string[]]$Arguments,[string]$Command,[string]$DiagnosticsPath,[string]$Executable='ssh.exe') {
    try {$r=Invoke-BoundedTransfer $Executable (@($Arguments)+@($Command))}catch{
        if($DiagnosticsPath -and $_.Exception.Data.Contains('native_summary')){Write-AtomicJson $DiagnosticsPath $_.Exception.Data['native_summary']}
        throw
    }
    if($DiagnosticsPath){Write-AtomicJson $DiagnosticsPath @{exit_code=$r.ExitCode;output_complete=$r.OutputComplete;raw_stdout_saved=$false;stderr_saved=$false}}
    return $r.Stdout
}
function Set-ConnectionPhase([string]$Path,[string]$Phase) {
    if ($Path) { Write-AtomicJson $Path @{phase=$Phase;utc=[DateTimeOffset]::UtcNow.ToString('o')} }
}
function Hold-FailureWindow([string]$Directory) {
    Write-AtomicJson (Join-Path $Directory 'failure-window-open.json') @{pid=$PID;utc=[DateTimeOffset]::UtcNow.ToString('o');input_recorded=$false}
    Write-Host 'SSH has ended. No passphrase is requested now. Close this error-review window with X when finished.'
    while ($true) { Start-Sleep -Seconds 1 }
}
function Get-RemoteFailureCode([string]$Message) {
    if ($Message -match '^Remote JSON is incomplete or invalid') { return 'REMOTE_JSON_PARSE_FAILED' }
    if ($Message -match '^Remote completion marker') { return 'REMOTE_COMPLETION_MARKER_INVALID' }
    return 'REMOTE_IDENTITY_VALIDATION_FAILED'
}
function Invoke-ContainerOperation([ValidateSet('locate','probe','env','gpu','work','verify')][string]$Operation, [switch]$PromptForKey,[string]$DiagnosticsDirectory) {
    $phasePath='';$nativePath=''
    if ($DiagnosticsDirectory) { $phasePath=Join-Path $DiagnosticsDirectory 'connection-phase.json';$nativePath=Join-Path $DiagnosticsDirectory 'native-ssh.json' }
    Set-ConnectionPhase $phasePath 'api_target_validation'
    $target = Invoke-Bridge target
    $nonce = [Guid]::NewGuid().ToString('N')
    $request = @{nonce=$nonce;operation=$Operation;image=$target.image} | ConvertTo-Json -Compress
    $request64 = ConvertTo-Base64 $request
    $program = Get-Content -LiteralPath (Join-Path $script:ToolRoot 'remote_probe.py') -Raw -Encoding UTF8
    $command = New-EncodedShellCommand $program $request64
    Set-ConnectionPhase $phasePath 'ssh_preparation'
    $arguments = Get-SshArguments $target -PromptForKey:$PromptForKey
    Set-ConnectionPhase $phasePath 'api_target_recheck'
    $fresh = Invoke-Bridge target
    if ($fresh.vm_id -ne $target.vm_id -or $fresh.ip -ne $target.ip -or $fresh.ssh_user -ne $target.ssh_user -or $fresh.image -ne $target.image) { throw 'Current VM changed before SSH; retry validation.' }
    Set-ConnectionPhase $phasePath 'native_ssh_authentication_or_remote_execution'
    $output=Invoke-NativeSshCommand $arguments $command $nativePath
    Set-ConnectionPhase $phasePath 'remote_json_validation'
    try { $result = Read-RemoteResult $output $nonce $Operation $target.image } catch {
        throw (Get-RemoteFailureCode $_.Exception.Message)
    }
    Set-ConnectionPhase $phasePath 'remote_identity_verified'
    [pscustomobject]@{Target=$target;Result=$result}
}
function Write-AtomicJson([string]$Path, $Object) {
    $temp = $Path+'.'+[Guid]::NewGuid().ToString('N')+'.tmp'
    [IO.File]::WriteAllText($temp,($Object | ConvertTo-Json -Depth 8),[Text.UTF8Encoding]::new($false))
    Move-Item -LiteralPath $temp -Destination $Path -Force
}
