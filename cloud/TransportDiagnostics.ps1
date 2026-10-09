# Only fixed categories, numeric process facts and hashes leave this module.
# Neither commands, arbitrary stderr nor credential/path values are persisted.
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
function Get-SafeNativeSummary($Result) {
 $labels=@($Result.Stderr -split '\r?\n'|Where-Object {$_ -cmatch '^(CONTAINER_STAGE_FAILED_EXIT_[0-9]+|SMOKE_[A-Z0-9_]{1,110}|VM_[A-Z0-9_]{1,110}|DOCKER_QUERY_FAILED|NO_VALID_RUNNING_CONTAINERS|CONTAINER_MATCH_NOT_UNIQUE|INVALID_ARCHIVE_NAME)$'}|Select-Object -Unique -First 8)
 return @{schema_version=2;phase='native_completed';status=$Result.Status;exit_code=$Result.ExitCode;
  started=$Result.Started;timed_out=$Result.TimedOut;process_exited=$Result.ProcessExited;
  pipe_not_closed=$Result.PipeTimedOut;output_complete=$Result.OutputComplete;truncated=$Result.Truncated;
  read_failed=$Result.ReadFailed;cleanup_incomplete=$Result.CleanupIncomplete;cleanup_attempted=$Result.CleanupAttempted;
  remaining_owned_processes=$Result.RemainingOwnedProcesses;job_assigned=$Result.JobAssigned;
  native_error_code=$Result.NativeErrorCode;stdout_read_error=$Result.StdoutReadError;stderr_read_error=$Result.StderrReadError;
  budget_ms=$Result.BudgetMs;execution_budget_ms=$Result.ExecutionBudgetMs;elapsed_ms=$Result.ElapsedMs;
  implementation_version=$Result.ImplementationVersion;stdout_lines=$Result.OutputLines;stderr_lines=$Result.ErrorLines;
  stdout_bytes=[Text.Encoding]::UTF8.GetByteCount($Result.Stdout);stderr_bytes=[Text.Encoding]::UTF8.GetByteCount($Result.Stderr);
  stderr_categories=@(Get-TransportStderrCategories $Result.Stderr);public_failure_labels=$labels;
  classification_basis='fixed pattern observations; no root-cause or retry inference';
  raw_output_saved=$false;raw_stdout_saved=$false;stderr_saved=$false}
}
