import json,os,subprocess,time
from pathlib import Path
from datetime import datetime,timezone,timedelta
R=Path(__file__).resolve().parents[1];PS=Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
import tempfile
OUT=Path(tempfile.mkdtemp(prefix='guard fixtures with spaces '))
def put(p,v):
 temp=p.with_suffix('.writing');temp.write_text(json.dumps(v));temp.replace(p)
def read(p):
 end=time.monotonic()+1
 while True:
  try:return json.loads(p.read_text(encoding='utf-8-sig'))
  except PermissionError:
   if time.monotonic()>=end:raise
   time.sleep(.02)
def wait(check,timeout=15):
 start=time.monotonic()
 while time.monotonic()-start<timeout:
  try:
   value=check()
   if value:return value
  except (FileNotFoundError,PermissionError,json.JSONDecodeError):pass
  time.sleep(.1)
 raise AssertionError('offline fixture deadline')
def fixture(name,state='STARTING'):
 d=OUT/name;d.mkdir();now=datetime.now(timezone.utc)
 put(d/'startup.json',dict(created_utc=(now-timedelta(hours=2)).isoformat(),offline=True,single_run=True,budget_usd_including_tax=3,approval_reference='SYNTHETIC',devlab_id='SYNTHETIC',offline_test_policy=dict(work_seconds=2,stop_seconds=4)))
 put(d/'live-settings.json',dict(cloud_stop_enabled=True,devlab_id='SYNTHETIC'))
 put(d/'simulated-cloud.json',dict(state=state,instances=[],verify_reads=0,stop_requests=0))
 p=subprocess.Popen([str(PS),'-NoProfile','-File',str(R/'cloud/TeaRunningGuard.ps1'),'-RunDirectory',str(d),'-Execute'],stdout=(d/'stdout.txt').open('wb'),stderr=(d/'stderr.txt').open('wb'),creationflags=subprocess.CREATE_NO_WINDOW)
 wait(lambda:(d/'heartbeat.json').exists())
 assert read(d/'heartbeat.json')['stopped_verified'] is False
 return d,p
def release(d,p):
 wait(lambda:read(d/'simulated-cloud.json')['state']=='STOPPED')
 put(d/'independent-stopped-release.json',dict(state='STOPPED',instances=[]))
 p.wait(timeout=8);assert read(d/'heartbeat.json')['stopped_verified'] is True if (d/'heartbeat.json').is_file() else True;assert p.returncode==0,(d,(d/'stderr.txt').read_text())
def finish(d,p):
 if p.poll() is None:
  put(d/'complete.json',dict(stop_required=True));release(d,p)
rows=[];start=time.monotonic()
d,p=fixture('long-startup-then-running')
try:
 time.sleep(6)
 assert p.poll() is None and not (d/'launch.json').exists() and not (d/'timing.json').exists()
 assert read(d/'simulated-cloud.json')['stop_requests']==0 and not read(d/'heartbeat.json')['running_confirmed']
 # IMAGE_PULLING is still startup, not RUNNING confirmation.
 s=read(d/'simulated-cloud.json');s['state']='IMAGE_PULLING';put(d/'simulated-cloud.json',s);time.sleep(1.2)
 assert not (d/'running-confirmation.json').exists()
 s['state']='RUNNING';put(d/'simulated-cloud.json',s)
 wait(lambda:(d/'launch.json').exists());proof=(d/'running-confirmation.json').read_bytes();timing=read(d/'timing.json')
 time.sleep(1.5);assert (d/'running-confirmation.json').read_bytes()==proof and read(d/'timing.json')==timing
 wait(lambda:read(d/'simulated-cloud.json')['stop_requests']==1)
 put(d/'independent-stopped-release.json',dict(state='STOPPED',instances=[dict(state='RUNNING')]))
 time.sleep(2.2);assert p.poll() is None
 release(d,p);assert read(d/'heartbeat.json')['status']=='stopped' and not read(d/'heartbeat.json')['sleep_held']
 rows+= [dict(name='STARTING longer than active window and old created time: no clock or stop',passed=True),dict(name='IMAGE_PULLING does not anchor',passed=True),dict(name='first RUNNING anchors once; repeated RUNNING unchanged',passed=True),dict(name='active deadline stop + independent empty instances release',passed=True)]
finally:finish(d,p)
d,p=fixture('cancel-before-running')
try:
 put(d/'cancel.json',dict(cancel=True));release(d,p)
 assert not (d/'running-confirmation.json').exists();rows.append(dict(name='cancel during STARTING stops before anchor',passed=True))
finally:finish(d,p)
d,p=fixture('lost-startup-supervision')
try:
 s=read(d/'simulated-cloud.json');s['status_failures_remaining']=3;put(d/'simulated-cloud.json',s)
 wait(lambda:(d/'supervision-stop.json').exists());release(d,p)
 assert not (d/'launch.json').exists();rows.append(dict(name='three startup API failures stop without waiting forever',passed=True))
finally:finish(d,p)
d,p=fixture('diagnostic-write-failure')
try:
 # Move the heartbeat to retained evidence; make the next heartbeat write fail.
 (d/'heartbeat.json').rename(d/'prior-heartbeat.json');(d/'heartbeat.json').mkdir()
 release(d,p)
 assert read(d/'simulated-cloud.json')['stop_requests']>=1 and (d/'complete.json').exists()
 rows.append(dict(name='heartbeat write failure keeps stop-only supervision until independent receipt',passed=True))
finally:finish(d,p)
d,p=fixture('bounded-startup-without-running')
try:
 s=read(d/'startup.json');s['startup_wait_seconds']=2;put(d/'startup.json',s)
 # Startup policy is read at guard entry, so use a request older than the
 # production 600-second bound; no RUNNING receipt must be synthesized.
 put(d/'restart-attempt.json',dict(request_utc=(datetime.now(timezone.utc)-timedelta(seconds=601)).isoformat()))
 release(d,p)
 assert not (d/'running-confirmation.json').exists()
 rows.append(dict(name='startup request bound stops without anchoring RUNNING',passed=True))
finally:finish(d,p)
result=dict(passed=True,test_count=len(rows),tests=rows,elapsed_seconds=time.monotonic()-start,cloud_API_calls=0,SSH_connections=0,simulation_only=True)
(OUT/'guard-tests.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
