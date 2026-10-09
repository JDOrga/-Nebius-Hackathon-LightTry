"""Starts only the reviewed local driver, after explicit local configuration."""
import json
import subprocess
import sys
from pathlib import Path


class GuardedCosmosExecutor:
    def __init__(self, config_path):
        self.config_path = Path(config_path).resolve()
        value = json.loads(self.config_path.read_text(encoding='utf-8-sig'))
        if value.get('enabled') is not True:
            raise ValueError('INFERENCE_EXPLICIT_ENABLE_REQUIRED')
        self.weights_mode = value.get('weights_mode', 'full')
        if self.weights_mode not in ('full', 'historical_metadata'):
            raise ValueError('INVALID_WEIGHT_VERIFICATION_MODE')
        run = Path(value['guard_run_directory']).resolve()
        workspace = Path(__file__).resolve().parents[2]
        if run.parent != workspace / 'cloud-runs' or len(run.name) != 32 or any(c not in '0123456789abcdef' for c in run.name):
            raise ValueError('CURRENT_LOCAL_GUARDED_RUN_REQUIRED')
        self.children = []

    def submit(self, folder, request):
        # Do the read-only authorization check again at submission. No SSH/API here.
        from .driver import authorization
        run, _, settings, _, _ = authorization(self.config_path)
        from .jobs import atomic
        from .images import digest
        atomic(folder / 'runtime-binding.json', {'guardRunId': run.name,
            'resourceId': settings['devlab_id'], 'launchSha256': digest((run / 'launch.json').read_bytes())})
        with (folder / 'driver.log').open('xb') as output:
            child = subprocess.Popen([sys.executable, '-X', 'utf8', '-B', str(Path(__file__).with_name('driver.py')),
                '--config', str(self.config_path), '--job', str(folder)], stdin=subprocess.DEVNULL,
                stdout=output, stderr=subprocess.STDOUT, shell=False)
        self.children.append(child)

    def check_ready(self):
        from .driver import authorization
        authorization(self.config_path)

    def run_config(self):
        return {'weightVerification': self.weights_mode,
                'weightContentHashesChecked': self.weights_mode == 'full'}

    def confirmed_stopped(self, folder):
        from .jobs import read
        from .images import digest
        try:
            binding = read(folder / 'runtime-binding.json')
            rid = binding['guardRunId']
            if len(rid) != 32 or any(c not in '0123456789abcdef' for c in rid):
                return False
            run = Path(__file__).resolve().parents[2] / 'cloud-runs' / rid
            release, beat = read(run / 'independent-stopped-release.json'), read(run / 'heartbeat.json')
            if digest((run / 'launch.json').read_bytes()) != binding['launchSha256']:
                return False
            from .driver import ROOT
            sys.path.insert(0, str(ROOT / 'scripts'))
            from weights import parse_deadline
            launch = read(run / 'launch.json')
            return (release.get('independent_api') is True and release.get('id') == binding['resourceId'] and
                release.get('state') == 'STOPPED' and release.get('instances') == [] and
                parse_deadline(release['utc']) >= parse_deadline(launch['launched_utc']) and
                beat.get('stopped_verified') is True and beat.get('sleep_held') is False and not beat.get('offline'))
        except (OSError, ValueError, KeyError):
            return False
