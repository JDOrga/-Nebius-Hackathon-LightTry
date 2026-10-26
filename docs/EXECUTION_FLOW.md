# Execution safety

This is the operator workflow for Nebius authentication, paid inference, and
shutdown. It takes precedence over historical runbooks. Local code review or
web development does not authorize cloud access, GPU startup, or paid AI calls.
This document is a workflow requirement, not proof of automated or live validation.

## Prepare before authorization

Read the current private checkpoint and only the latest state it references.
The existing local checkpoint is `.local/calibration-20261013/checkpoint.json`;
it is not distributed. Preserve confirmed task IDs, package hashes, inputs,
scripts, and completed steps; do not rediscover or rerun completed work.

Finish relevant offline checks, freeze the source bundle, verify upload contents,
record the exact CLI and verified login entry in private configuration, and prepare
the guard and independent stop checks. Keep machine-specific paths in
`.local/studio.json`; never commit credentials or create authorization from examples.
GPU and text-service permissions are separate. Neither carries over from closed sessions.

## Authenticate, preflight, launch once

1. Bind the new explicit scope, resource, budget, package hash, and fixed deadline.
2. Verify current CLI authentication, tenant/project ownership, resource identity,
   STOPPED state, empty instances, and the approved public key. Any failure stops the chain.
3. On authentication failure, immediately open the already verified existing-profile
   login entry. Do not guess commands, install a new CLI, or change projects.
   Never ask the user to paste tokens into chat. Resume necessary checks immediately
   after authentication; browser success alone is not API authentication proof.
4. Confirm guard readiness, fresh heartbeat, sleep inhibition, and unused single-start
   latch before one startup request. Record the attempt before sending it.
5. After independently confirmed RUNNING, bind the current VM/IP and SSH fingerprint.
   Automatic first-use pinning requires explicit private acceptance of first-connection
   interception risk; otherwise stop for the required trust decision. Later SSH
   connections must strictly match the session pin. Never reuse a previous host's trust.
6. Upload only the frozen package, verify its hash and worker, record the launch
   attempt, and launch once. Model readiness requires both actual inference phases
   to be loaded, alive, and bound to the current session/resource.

Do not insert unrelated tests, reporting, or package rebuilding into the authorized
short chain. Target executor handoff is 30 seconds after authentication events and
15 seconds from successful preflight/guard readiness to the single start request;
network and user waiting are measured separately, not promised as startup latency.

## Fixed limits and observation

- Startup wait: at most **600 seconds** from the startup request.
- From the first reliable independent RUNNING observation: work ends at **18 minutes**,
  stop deadline is **25 minutes**, and verification target is **27 minutes**.
- Absolute protection: no later than the original guard window of **40 minutes**.
  Always take the earlier deadline, including `min(verification target, absolute deadline)`.
- Record UTC and Asia/Shanghai times. Never extend windows, restart a session,
  duplicate launch, or reset latches after an uncertain result.
- The guard owns provider polling. Read its local receipts instead of starting
  another cloud/SSH poller; report transitions immediately and waits every 60 seconds.
- Stop early when finished. Do not leave GPUs running for reports or user decisions.

Preserve uncertain attempts and original failures. Query the original task rather
than retrying POST/PUT. Missing observation, hash/identity mismatch, or an unknown
remote process must not be concealed by reconnecting or relaunching.

## Shutdown before reporting

After STOPPED is observed, immediately verify independently that the provider is
STOPPED **and `instances=[]`**, retain the release receipt, and verify sleep inhibition
is released. A successful stop request is not resource-release proof.

For a bounded experiment guard, also verify process exit and final
`stopped_verified=true`, `sleep_held=false`. A deliberately persistent CPU guard
may remain idle after GPU shutdown: report that fact, not a fictitious guard exit.
Before ending that guard or upgrading it, independently verify GPU release first.

Start independent release checks within 15 seconds of observing STOPPED; report
safety within 15 seconds after all required evidence is available. Until then use
`stop-unverified`, retain supervision, and state what is missing. If the verification
deadline passes, continue **stop-only supervision**, never inference or a new startup.

Report execution outcome, confirmed start/launch/result counts, actual release
evidence, and unverified steps before compiling a longer report. Unknown is not zero.
Extend the existing evidence ledger and four-role transaction records rather than
creating another final/release tree. Preserve failed checks even after later success.

## Protection boundaries

CPU-only protection requires explicit private `cpuHostRiskAccepted=true` and
`protection.mode=cpu-only`. A same-host web process and guard are not an independent
control plane: CPU failure or loss of cloud access may leave the GPU billable.
Software budgets are not provider-enforced billing caps. No document, example,
offline test, health response, or historical receipt authorizes a new paid session
or proves a currently deployed, working end-to-end model pipeline.
