# Project execution

- For Nebius experiments, CLI authentication, paid inference, or shutdown, read
  `docs/EXECUTION_FLOW.md` and the latest state referenced by the current private
  checkpoint first. Ordinary local code and frontend work must not start cloud operations.
- Complete local preparation before authorization. After authorization, use only
  authentication, required preflight, guard readiness, and one bounded launch.
  Stop on any failed preflight; use the verified login entry after authentication failure.
- Continue required checks immediately after the user authenticates. Automatic
  first-use host pinning requires explicit private operational-risk acceptance;
  all later SSH connections must match that session's pin. Keep parameter confirmation.
- Report transitions promptly and long waits every 60 seconds without duplicate cloud polling.
- Never extend the 600-second startup limit or fixed work, stop, verification, and
  absolute deadlines. Never reconnect, relaunch, or inherit closed authorization.
- After STOPPED, prioritize independent empty-instance proof, the guard's actual
  lifecycle state, and sleep-inhibition release. Report safety before documentation.
- Preserve failures and unknown outcomes. Distinguish specifications, implemented
  code, offline simulation, remote deployment, and real model validation.

# Repository structure

- `start.py` is the only entry point; `project/web/` is the only frontend.
  Do not restore a Next.js or legacy frontend.
- Update existing documentation and evidence ledgers; do not create parallel product trees.
- Keep machine-local paths in ignored `.local/studio.json`. Preserve original
  experiments, authorization ledgers, failures, and shutdown evidence unchanged.
- `master` is for judging; keep tests and historical development tools on `dev`.
