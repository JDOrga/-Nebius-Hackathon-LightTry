"""The hard cutoff applies while waiting for RUNNING, using only synthetic state."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from datetime import datetime,timezone,timedelta

ROOT=Path(__file__).resolve().parents[1]
PS=Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
def put(p,v):
    t=p.with_suffix('.writing');t.write_text(json.dumps(v));t.replace(p)
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def wait(fn):
    start=time.monotonic()
    while time.monotonic()-start<15:
        try:
            if fn():return
        except (OSError,ValueError):pass
        time.sleep(.1)
    raise AssertionError('offline guard timeout')

with tempfile.TemporaryDirectory(prefix='absolute deadline with spaces ') as d:
    run=Path(d);now=datetime.now(timezone.utc)
    put(run/'startup.json',dict(offline=True,single_run=True,devlab_id='devlab-synthetic',budget_usd_including_tax=1,approval_reference='SYNTHETIC',created_utc=now.isoformat(),absolute_deadline_utc=(now+timedelta(seconds=3)).isoformat()))
    put(run/'live-settings.json',dict(cloud_stop_enabled=True))
    put(run/'simulated-cloud.json',dict(state='STARTING',instances=[],verify_reads=0,stop_requests=0))
    p=subprocess.Popen([str(PS),'-NoProfile','-File',str(ROOT/'cloud/TeaRunningGuard.ps1'),'-RunDirectory',d,'-Execute'],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        wait(lambda:read(run/'simulated-cloud.json')['state']=='STOPPED')
        assert read(run/'simulated-cloud.json')['stop_requests']>=1
        assert not (run/'running-confirmation.json').exists()
        assert p.poll() is None # stop submission alone never releases supervision
        put(run/'independent-stopped-release.json',dict(state='STOPPED',instances=[]))
        p.communicate(timeout=10);assert p.returncode==0
    finally:
        if p.poll() is None:
            put(run/'complete.json',dict(stop_required=True))
            put(run/'independent-stopped-release.json',dict(state='STOPPED',instances=[]))
            p.communicate(timeout=15)
print(json.dumps({'passed':True,'test_count':1,'cloud_calls':0,'absolute_cutoff_during_STARTING':True}))
