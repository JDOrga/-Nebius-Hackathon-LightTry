# Fixed categories, numeric facts, hashes and sanitized diagnostic sentences only.
# Unknown free-form lines are omitted; never persist raw streams or commands.
function Get-TransportTextDigest([string]$Text) {
 $hash=[Security.Cryptography.SHA256]::Create()
 try{([BitConverter]::ToString($hash.ComputeHash([Text.Encoding]::UTF8.GetBytes($Text)))).Replace('-','').ToLowerInvariant()}finally{$hash.Dispose()}
}
function Get-SafeTransportContext([hashtable]$Context) {
 $safe=@{}
 if(!$Context){return $safe}
 if($Context.ContainsKey('operation') -and $Context.operation -in @('upload_directory','upload','download_results','install_bundle','launch','inspect','export_results','probe','locate','env','gpu','work','verify')){$safe.operation=$Context.operation}
 foreach($key in @('connection_arguments_sha256','target_identity_sha256','host_pin_sha256','request_sha256')){
  if($Context.ContainsKey($key) -and $Context[$key] -cmatch '^[a-f0-9]{64}$'){$safe[$key]=$Context[$key]}
 }
 return $safe
}
function Get-TransportStderrCategories([string]$Stderr) {
 $categories=@()
 # These are pattern observations, not verified root causes or retry permission.
 $patterns=[ordered]@{
  HOST_KEY_CHANGED='(?im)^.*REMOTE HOST IDENTIFICATION HAS CHANGED.*$'
  HOST_KEY_VERIFICATION_FAILED='(?im)^.*Host key verification failed\.?\s*$'
  AUTHENTICATION_REJECTED='(?im)^.*Permission denied \((?:publickey|password|keyboard-interactive|gssapi-keyex|gssapi-with-mic)(?:,(?:publickey|password|keyboard-interactive|gssapi-keyex|gssapi-with-mic))*\)\.?\s*$'
  IDENTITY_FILE_UNAVAILABLE='(?im)^Warning: Identity file .+ not accessible: .+$'
  PRIVATE_KEY_LOAD_FAILED='(?im)^(?:Load key .+: .+|.*UNPROTECTED PRIVATE KEY FILE.*|.*bad permissions.*)$'
  DNS_RESOLUTION_FAILED='(?im)^ssh: Could not resolve hostname .+$'
  CONNECTION_REFUSED='(?im)^ssh: connect to host .+ port \d+: Connection refused\s*$'
  CONNECTION_TIMEOUT='(?im)^(?:ssh: connect to host .+ port \d+: Connection timed out|Connection timed out during banner exchange|Connection to .+ timed out)\s*$'
  CONNECTION_RESET='(?im)^(?:(?:kex_exchange_identification|ssh_exchange_identification): read: Connection reset by peer|Connection reset by .+|client_loop: send disconnect: Connection reset(?: by peer)?)\s*$'
  CONNECTION_CLOSED='(?im)^(?:(?:kex_exchange_identification|ssh_exchange_identification): Connection closed by remote host|Connection closed by .+|Connection to .+ closed(?: by remote host)?\.?|(?:scp: )?Connection closed)\s*$'
  BROKEN_PIPE='(?im)^(?:client_loop: send disconnect: Broken pipe|.*: write: Broken pipe)\s*$'
  SSH_NEGOTIATION_FAILED='(?im)^Unable to negotiate with .+: no matching .+ found\..+$'
 }
 foreach($key in $patterns.Keys){if($Stderr -match $patterns[$key]){$categories+=$key}}
 if(!$categories.Count -and $Stderr.Trim()){$categories=@('UNCLASSIFIED_STDERR')}
 return $categories
}
function ConvertTo-SafeStderrLine([string]$Line) {
 $line=[regex]::Replace($Line,'\x1B\[[0-?]*[ -/]*[@-~]','').Trim()
 # Reconstruct recognized sentences rather than attempting to scrub arbitrary
 # remote output. Every captured variable is either discarded or constrained.
 if($line -match '^(?<tool>ssh|scp): connect to host .+ port (?<port>[0-9]{1,5}): (?<reason>Connection refused|Connection timed out|No route to host|Network is unreachable|Host is down)\.?$'){
  return ($Matches.tool+': connect to host [REDACTED HOST] port '+$Matches.port+': '+$Matches.reason)
 }
 if($line -match '^ssh: Could not resolve hostname .+: (?<reason>Name or service not known|Temporary failure in name resolution|No such host is known\.?)$'){
  return ('ssh: Could not resolve hostname [REDACTED HOST]: '+$Matches.reason)
 }
 if($line -match '^(?:.+: )?Permission denied \((?<methods>(?:publickey|password|keyboard-interactive|gssapi-keyex|gssapi-with-mic)(?:,(?:publickey|password|keyboard-interactive|gssapi-keyex|gssapi-with-mic))*)\)\.?$'){
  return ('[REDACTED TARGET]: Permission denied ('+$Matches.methods+').')
 }
 if($line -match '^(?<prefix>kex_exchange_identification|ssh_exchange_identification): (?<reason>read: Connection reset by peer|Connection closed by remote host|banner line contains invalid characters|read: Connection timed out)$'){
  return ($Matches.prefix+': '+$Matches.reason)
 }
 if($line -match '^Connection (?<action>reset|closed) by .+?(?: port (?<port>[0-9]{1,5}))?\.?$'){
  $port='';if($Matches.ContainsKey('port')){$port=' port '+$Matches.port}
  return ('Connection '+$Matches.action+' by [REDACTED HOST]'+$port)
 }
 if($line -match '^Connection to .+ (?<reason>closed by remote host|closed|timed out)\.?$'){
  return ('Connection to [REDACTED HOST] '+$Matches.reason)
 }
 if($line -match '^(?<prefix>client_loop: send disconnect|ssh_dispatch_run_fatal: Connection to .+ port [0-9]{1,5}): (?<reason>Broken pipe|Connection reset by peer|Connection timed out|message authentication code incorrect)$'){
  $prefix='client_loop: send disconnect';if($Matches.prefix.StartsWith('ssh_dispatch_run_fatal')){$prefix='ssh_dispatch_run_fatal: Connection to [REDACTED HOST]'}
  return ($prefix+': '+$Matches.reason)
 }
 if($line -match '^Warning: Identity file .+ not accessible: (?<reason>No such file or directory|Permission denied|Bad file descriptor)\.?$'){
  return ('Warning: Identity file [REDACTED PATH] not accessible: '+$Matches.reason)
 }
 if($line -match '^Load key .+: (?<reason>error in libcrypto|invalid format|incorrect passphrase supplied to decrypt private key|bad permissions|Permission denied|No such file or directory)$'){
  return ('Load key [REDACTED PATH]: '+$Matches.reason)
 }
 if($line -match '^Permissions (?<mode>[0-7]{3,4}) for .+ are too open\.$'){
  return ('Permissions '+$Matches.mode+' for [REDACTED PATH] are too open.')
 }
 if($line -match '^Bad owner or permissions on .+$'){return 'Bad owner or permissions on [REDACTED PATH]'}
 if($line -match '^Offending (?<kind>ED25519|RSA|ECDSA|DSA) key in .+:(?<number>[0-9]{1,8})$'){
  return ('Offending '+$Matches.kind+' key in [REDACTED PATH]:'+$Matches.number)
 }
 if($line -match '^Host key for .+ has changed and you have requested strict checking\.$'){
  return 'Host key for [REDACTED HOST] has changed and you have requested strict checking.'
 }
 if($line -match '^Unable to negotiate with .+ port (?<port>[0-9]{1,5}): no matching (?<kind>key exchange method|host key type|cipher|MAC|compression method) found\. Their offer: .+$'){
  return ('Unable to negotiate with [REDACTED HOST] port '+$Matches.port+': no matching '+$Matches.kind+' found. Their offer: [OMITTED OFFER LIST]')
 }
 if($line -match '^@*\s*(?:WARNING:\s*)?REMOTE HOST IDENTIFICATION HAS CHANGED!?\s*@*$'){return 'WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!'}
 if($line -match '^@*\s*WARNING: UNPROTECTED PRIVATE KEY FILE!?\s*@*$'){return 'WARNING: UNPROTECTED PRIVATE KEY FILE!'}
 if($line -match '^SHA256:[A-Za-z0-9+/=]+\.?$'){return '[REDACTED FINGERPRINT]'}
 if($line -in @('Host key verification failed.','Host key verification failed','Connection timed out during banner exchange',
  'It is possible that someone is doing something nasty!',
  'Someone could be eavesdropping on you right now (man-in-the-middle attack)!',
  'It is also possible that a host key has just been changed.',
  'The fingerprint for the ED25519 key sent by the remote host is',
  'The fingerprint for the RSA key sent by the remote host is',
  'The fingerprint for the ECDSA key sent by the remote host is',
  'This private key will be ignored.','It is required that your private key files are NOT accessible by others.',
  'scp: Connection closed','Connection closed')){return $line}
 if($line -cmatch '^(CONTAINER_STAGE_FAILED_EXIT_[0-9]+|SMOKE_[A-Z0-9_]{1,110}|VM_[A-Z0-9_]{1,110}|DOCKER_QUERY_FAILED|NO_VALID_RUNNING_CONTAINERS|CONTAINER_MATCH_NOT_UNIQUE|INVALID_ARCHIVE_NAME)$'){return $line}
 return $null
}
function Get-SafeStderrExcerpt([string]$Stderr,[bool]$SourceCaptureIncomplete=$false) {
 $scanLimit=32768;$byteLimit=4096;$lineLimit=40
 $scan=$Stderr;$scanTruncated=($Stderr.Length -gt $scanLimit)
 if($scanTruncated){
  # Keep both ends: a long banner must not displace a trailing failure message.
  $half=[int](($scanLimit-32)/2)
  $head=$Stderr.Substring(0,$half);$tail=$Stderr.Substring($Stderr.Length-$half)
  $cut=$head.LastIndexOf("`n");if($cut -ge 0){$head=$head.Substring(0,$cut)}else{$head=''}
  $cut=$tail.IndexOf("`n");if($cut -ge 0){$tail=$tail.Substring($cut+1)}else{$tail=''}
  $scan=$head+"`n[SOURCE MIDDLE OMITTED]`n"+$tail
 }
 $safe=[Collections.Generic.List[string]]::new();$omitted=0;$pending=0;$recognized=0
 foreach($line in ($scan -split '\r?\n')){
  if(!$line.Trim()){continue}
  if($line -eq '[SOURCE MIDDLE OMITTED]'){
   if($pending){$safe.Add('['+$pending+' unrecognized stderr lines omitted]');$pending=0}
   $safe.Add($line);continue
  }
  $clean=ConvertTo-SafeStderrLine $line
  if($null -eq $clean){$omitted++;$pending++;continue}
  if($pending){$safe.Add('['+$pending+' unrecognized stderr lines omitted]');$pending=0}
  $safe.Add($clean);$recognized++
 }
 if($pending){$safe.Add('['+$pending+' unrecognized stderr lines omitted]')}
 $lineTruncated=($safe.Count -gt $lineLimit)
 if($lineTruncated){$selected=@($safe|Select-Object -First 19)+@('[EXCERPT MIDDLE OMITTED]')+@($safe|Select-Object -Last 20)}else{$selected=@($safe)}
 $text=$selected -join "`n";$byteTruncated=([Text.Encoding]::UTF8.GetByteCount($text) -gt $byteLimit)
 if($byteTruncated){
  # Preserve complete sentences from both ends within separate byte quotas.
  $head=[Collections.Generic.List[string]]::new();$tail=[Collections.Generic.List[string]]::new()
  $bytes=0
  foreach($line in @($selected|Select-Object -First 19)){
   $size=[Text.Encoding]::UTF8.GetByteCount($line)+1;if($bytes+$size -gt 1950){break};$head.Add($line);$bytes+=$size
  }
  $bytes=0;$end=@($selected|Select-Object -Last 20)
  for($i=$end.Count-1;$i -ge 0;$i--){
   $size=[Text.Encoding]::UTF8.GetByteCount($end[$i])+1;if($bytes+$size -gt 1950){break};$tail.Insert(0,$end[$i]);$bytes+=$size
  }
  $text=(@($head)+@('[EXCERPT MIDDLE OMITTED]')+@($tail)) -join "`n"
 }
 return @{text=$text;policy='recognized diagnostic sentences only; variable fields redacted; free-form lines omitted';
  max_bytes=$byteLimit;max_lines=$lineLimit;max_scan_characters=$scanLimit;
  captured_characters=$Stderr.Length;captured_bytes=[Text.Encoding]::UTF8.GetByteCount($Stderr);
  scanned_characters=$scan.Length;retained_bytes=[Text.Encoding]::UTF8.GetByteCount($text);retained_lines=$(if($text){@($text -split "`n").Count}else{0});
  recognized_lines_in_scan=$recognized;unrecognized_lines_omitted_in_scan=$omitted;
  scan_truncated=$scanTruncated;line_truncated=$lineTruncated;byte_truncated=$byteTruncated;
  source_capture_basis='native combined-output truncation/read/completion flags; stderr completeness may be unknown';
  source_capture_incomplete=$SourceCaptureIncomplete;truncated=($scanTruncated -or $lineTruncated -or $byteTruncated -or $SourceCaptureIncomplete);
  raw_stderr_saved=$false;redaction_failed=$false}
}
function Get-SafeNativeSummary($Result) {
 $labels=@($Result.Stderr -split '\r?\n'|Where-Object {$_ -cmatch '^(CONTAINER_STAGE_FAILED_EXIT_[0-9]+|SMOKE_[A-Z0-9_]{1,110}|VM_[A-Z0-9_]{1,110}|DOCKER_QUERY_FAILED|NO_VALID_RUNNING_CONTAINERS|CONTAINER_MATCH_NOT_UNIQUE|INVALID_ARCHIVE_NAME)$'}|Select-Object -Unique -First 8)
 try{$excerpt=Get-SafeStderrExcerpt $Result.Stderr ($Result.Truncated -or $Result.ReadFailed -or !$Result.OutputComplete)}catch{
  $excerpt=@{text='[STDERR EXCERPT UNAVAILABLE]';policy='redaction failed; source text omitted';
   max_bytes=4096;max_lines=40;max_scan_characters=32768;retained_bytes=28;retained_lines=1;
   redaction_failed=$true;raw_stderr_saved=$false;truncated=$true}
 }
 return @{schema_version=2;phase='native_completed';status=$Result.Status;exit_code=$Result.ExitCode;
  started=$Result.Started;timed_out=$Result.TimedOut;process_exited=$Result.ProcessExited;
  pipe_not_closed=$Result.PipeTimedOut;output_complete=$Result.OutputComplete;truncated=$Result.Truncated;
  read_failed=$Result.ReadFailed;cleanup_incomplete=$Result.CleanupIncomplete;cleanup_attempted=$Result.CleanupAttempted;
  remaining_owned_processes=$Result.RemainingOwnedProcesses;job_assigned=$Result.JobAssigned;
  native_error_code=$Result.NativeErrorCode;stdout_read_error=$Result.StdoutReadError;stderr_read_error=$Result.StderrReadError;
  budget_ms=$Result.BudgetMs;execution_budget_ms=$Result.ExecutionBudgetMs;elapsed_ms=$Result.ElapsedMs;
  implementation_version=$Result.ImplementationVersion;stdout_lines=$Result.OutputLines;stderr_lines=$Result.ErrorLines;
  stdout_bytes=[Text.Encoding]::UTF8.GetByteCount($Result.Stdout);stderr_bytes=[Text.Encoding]::UTF8.GetByteCount($Result.Stderr);
  stderr_categories=@(Get-TransportStderrCategories $Result.Stderr);stderr_excerpt=$excerpt;public_failure_labels=$labels;
  classification_basis='fixed pattern observations; no root-cause or retry inference';
  raw_output_saved=$false;raw_stdout_saved=$false;stderr_saved=$false}
}
