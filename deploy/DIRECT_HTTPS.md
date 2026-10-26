# GPU transport

The CPU service communicates with a session-bound GPU worker over authenticated
HTTPS. Optional direct mTLS transport can avoid an SSH data tunnel; it does not
replace Nebius API shutdown or authorize model execution.

## Trust and configuration

- Bind every connection to the current session, resource, host identity, and IP.
- Validate the server CA, hostname/IP SAN, and SHA-256 certificate pin.
- Direct transport also requires a dedicated CPU client certificate with clientAuth.
  Never upload the CPU private key or issuing CA private key to the GPU.
- Keep worker tokens and certificate/key files outside the source tree in private
  runtime configuration. Do not carry trust, certificates, or deadlines across sessions.
- `binding.directWorkerFile` is disabled unless explicitly configured. Its enabled
  record contains `schemaVersion`, `enabled`, `sessionId`, `resourceId`, `hostIdentity`,
  `origin`, `tokenFile`, `caFile`, `certificateSha256`, `clientCertificateFile`, and `clientKeyFile`.

## Implementations

`project/mtls_relay.py` is a bounded standard-library mTLS relay to a fixed private
TLS worker. It does not execute uploaded scripts, load models, or retry requests.
The alternative Nginx stream template is
`deploy/gpu-direct-https.stream.conf.example`; keep both client verification and
upstream TLS verification enabled. A template is not deployment proof.

Optional private `directTLS` setup is integrated with SSH bootstrap. It publishes
the direct binding only after a session-matching health check and revokes it on stop.
Proxy setup may overlap worker initialization; do not assume it gates model loading.

## Failure handling

Direct transport is preferred when configured; SSH HTTPS is the fallback. Health
checks are bounded and must match the current session/resource/host. Query the
original task after uncertainty: never resend POST/PUT, restart models, or extend
the budget window. An IP change does not grant another execution attempt.

Validate correct-client success, missing/wrong-client rejection, wrong-server-pin
rejection, and transport behavior with the SSH tunnel closed. Record transport,
model readiness, actual inference, and visual quality separately. Both channels
can fail together if the GPU, container, or network is unavailable.

See [execution safety](../docs/EXECUTION_FLOW.md) before any live operation.
