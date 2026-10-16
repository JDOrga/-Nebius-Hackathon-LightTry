# Non-SSH GPU data channel (preparation only; not installed)

CPU -> GPU public IPv4:443 -> Nginx stream TCP passthrough -> private container:9443.
TLS terminates at the existing worker, not the proxy; bearer token stays encrypted.
SSH remains for initial deployment/diagnosis, not required by the direct data path.
Nebius API stop remains independent of both paths. A VM/kernel/container failure
can still affect both data channels; this is not a second host/network provider.

Before enablement bind CURRENT_SESSION_ID, RESOURCE_ID, HOST_IDENTITY, CPU_EGRESS_IPV4/32,
GPU_CURRENT_IPV4 and GPU_CONTAINER_IPV4. Confirm public ingress availability for the
actual Devlab resource; Compute networking documentation alone is not proof that
443 is reachable on this instance. Do not open to 0.0.0.0/0 or expose plaintext9080.
Render the nginx stream block with gpu_direct_https.render; nginx must have stream
support. Test nginx syntax and enforce matching host/cloud ingress restrictions.
No cloud firewall mutation or nginx installation is performed by this preparation.

Current localhost-only worker certificate is NOT sufficient for public-IP HTTPS.
Issue a current-session certificate with GPU_CURRENT_IPV4 in its IP SAN. Use it on
the SAME worker reached by both routes; configure CA+SHA256 pin in both clients.
Never disable hostname checking, reuse an old VM's identity, or send a token before
certificate verification. Use separate current-session secrets, outside the repo.

Optional CPU binding directWorkerFile points to private JSON. Default file is only
{"schemaVersion":1,"enabled":false}. An enabled record has EXACT fields:
schemaVersion=1, enabled=true, sessionId, resourceId, hostIdentity, origin,
tokenFile, caFile, certificateSha256. origin is https://GPU_CURRENT_IPV4:443 and
hostIdentity must exactly match the currently confirmed session. Paths are private.

Routing: direct HTTPS preferred, SSH HTTPS fallback. At most two bounded health GETs
select a route; session/resource/host must match. Actual model READY is still required.
POST/PUT failure is uncertain: no cross-route replay. Query the original jobId after
health selects a working route; missing/unknown task is NOT permission to resubmit.
No cloud start, SSH reconnect, model restart, scope renewal or deadline extension.

Acceptance next authorized session: both endpoints reach the same session; deliberately
close only SSH forwarding and confirm direct health and original-job query still work;
verify no second submit/model launch. Capture memory/OOM/system diagnostics during load
before failure rather than relying on SSH after it fails. Do not call this deployed or
claim fault tolerance until that real test passes.
