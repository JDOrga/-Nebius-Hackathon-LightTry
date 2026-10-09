# Adapted for the authorized one-hour experiment: no preflight stop, USD3 scope, <=3600s.
"""One authorized run only. No raw API or authentication output is printed."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import os
# Reuse the original CLI bridge; no authentication or settings copies.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cli_bridge as bridge
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from weights import parse_utc


def utc():
    return datetime.now(timezone.utc)


def mutate(settings, operation, *, not_after=None):
    # Asynchronous CLI mutation output is a plain operation ID; do not parse it
    # as JSON or expose it. The guard separately verifies the resource state.
    bridge.run_cli(settings, ['ai', 'devlab', operation, '--id', settings['devlab_id'],
                             '--async', '--profile', settings['profile']], json_result=False,
                   not_after=not_after)


def check_restart_guard(run, launch, settings):
    """Re-read live authorization after slow work and immediately before restart."""
    deadline = parse_utc(launch['absolute_deadline_utc'])
    if utc() >= deadline:
        raise ValueError('ABSOLUTE_DEADLINE_REACHED')
    snapshot = json.loads((run / 'live-settings.json').read_text(encoding='utf-8-sig'))
    if any(snapshot[k] != settings[k] for k in ('devlab_id', 'project_id')):
        raise ValueError('GUARD_SCOPE_MISMATCH')
    beat = json.loads((run / 'heartbeat.json').read_text(encoding='utf-8-sig'))
    now = utc()
    if now >= deadline:
        raise ValueError('ABSOLUTE_DEADLINE_REACHED')
    age = (now - parse_utc(beat['utc'])).total_seconds()
    if (launch.get('offline') or not snapshot['cloud_stop_enabled']
            or beat['status'] != 'ready_waiting_start' or not beat['sleep_held']
            or not 0 <= age <= 25):
        raise ValueError('LIVE_GUARD_NOT_READY')
    if any((run / name).exists() for name in ('cancel.json', 'complete.json', 'supervision-stop.json')):
        raise ValueError('GUARD_STOP_ALREADY_REQUESTED')
    if (launch.get('timing_policy') != 'RUNNING_ANCHORED_18_25_27'
            or beat.get('running_confirmed') or (run / 'running-confirmation.json').exists()):
        raise ValueError('PRE_RUNNING_SINGLE_START_REQUIRED')
    return deadline


def main():
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['preflight', 'restart', 'stop'])
    p.add_argument('--settings', required=True)
    p.add_argument('--execute', action='store_true')
    p.add_argument('--public-key-file')
    p.add_argument('--run-directory')
    a = p.parse_args()
    if not a.execute:
        print(json.dumps({'mode':'LOCAL_PLAN','cloud_calls':0})); return
    settings = json.loads(Path(a.settings).read_text(encoding='utf-8-sig'))
    if not settings.get('devlab_id') or not settings.get('project_id'):
        raise ValueError('AUTHORIZED_RESOURCE_MISMATCH')
    if a.action == 'preflight':
        project = bridge.run_cli(settings, ['iam', 'v2', 'project', 'get', '--id', settings['project_id']])
        bridge.validate_project_owner(project, settings)
        raw = bridge.run_cli(settings, ['ai', 'devlab', 'get', '--id', settings['devlab_id']])
        summary = bridge.devlab_summary(raw, settings)
        key = bridge.canonical_key(Path(a.public_key_file).read_text())
        if key not in [bridge.canonical_key(k) for k in raw['spec'].get('ssh_authorized_keys', [])]:
            raise ValueError('LOCAL_KEY_NOT_IN_DEVLAB')
        if summary['state'] != 'STOPPED':
            raise ValueError('EXPECTED_STOPPED_BEFORE_SINGLE_RESTART')
        spec = raw['spec']
        shape = {k: spec.get(k, '') for k in ('platform', 'preset')}
        shape['disk'] = {k: spec.get('disk', {}).get(k, '') for k in ('size_bytes', 'type')}
        # Read-only: never issue stop to an already stopped resource.
        print(json.dumps({'utc': utc().isoformat(), 'state': summary['state'], 'shape': shape,
                          'project_ownership_verified': True, 'local_key_matches': True,
                          'real_stop_api_accepted': False, 'read_only': True}))
        return
    run = Path(a.run_directory)
    launch = json.loads((run / 'startup.json').read_text(encoding='utf-8-sig'))
    snapshot = json.loads((run / 'live-settings.json').read_text(encoding='utf-8-sig'))
    if snapshot['devlab_id'] != settings['devlab_id'] or snapshot['project_id'] != settings['project_id'] or not launch['single_run']:
        raise ValueError('GUARD_SCOPE_MISMATCH')
    if a.action == 'restart':
        if launch.get('budget_usd_including_tax') <= 0 or not launch.get('approval_reference'):
            raise ValueError('USD3_APPROVAL_REFERENCE_REQUIRED')
        deadline = check_restart_guard(run, launch, settings)
        observed = bridge.devlab_summary(bridge.run_cli(settings, ['ai', 'devlab', 'get', '--id', settings['devlab_id']],
                                                       not_after=deadline.timestamp()), settings)
        if observed['state'] != 'STOPPED':
            raise ValueError('EXPECTED_STOPPED_BEFORE_SINGLE_RESTART')
        check_restart_guard(run, launch, settings)
        # Exclusive local marker prevents a retry even after an uncertain response.
        marker = run / 'restart-attempt.json'
        started = utc().isoformat()
        with marker.open('x', encoding='utf-8') as f:
            json.dump({'request_utc': started, 'devlab_id': settings['devlab_id'], 'clock_not_started': True}, f)
        deadline = check_restart_guard(run, launch, settings)
        mutate(settings, 'restart', not_after=deadline.timestamp())
        print(json.dumps({'restart_request_utc': started, 'clock_not_started': True, 'accepted': True, 'restart_attempts': 1}))
    else:
        if not snapshot['cloud_stop_enabled']:
            raise ValueError('SINGLE_RUN_STOP_AUTH_REVOKED')
        mutate(settings, 'stop')
        print(json.dumps({'stop_accepted_at_utc': utc().isoformat(), 'stop_submitted': True, 'stopped_verified': False}))


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        label = str(e)
        if not label or not all(c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ_0123456789' for c in label):
            label = 'LIVE_SESSION_FAILED_' + type(e).__name__
        print(json.dumps({'error': label}), file=sys.stderr)
        sys.exit(2)
