"""Offline real subprocess status streams; no SSH/API/GPU execution."""
import base64,contextlib,datetime,io,json,os,pathlib,subprocess,sys,tempfile,types,unittest
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT/'project'),str(ROOT/'scripts')]
from next.runtime.status_stream import observe
from next.runtime.joint_watch import watch
PLAN={'taskId':'a'*32,'nonce':'b'*32,'cases':[{'id':'C'}]}
class WatchTests(unittest.TestCase):
 def setup(self,t):
  r=pathlib.Path(t);job=r/'job';job.mkdir();beat={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'pid':os.getpid(),'offline':False,'sleep_held':True,'stopped_verified':False,'supervision_stop_latched':False};(r/'heartbeat.json').write_text(json.dumps(beat));return r,job
 def frame(self,status='running',stopped=False):return {'watchNonce':'c'*32,'taskId':PLAN['taskId'],'nonce':PLAN['nonce'],'status':status,'stage':'forward','executionStopped':stopped,'completed':['C'] if stopped else []}
 def spec(self,lines):
  script='import sys,json;'+''.join('print('+repr(json.dumps(x))+',flush=True);' for x in lines)
  return {'executable':sys.executable,'arguments':['-u','-c',script],'watchNonce':'c'*32}
 def test_one_owned_process_many_events_then_terminal(self):
  with tempfile.TemporaryDirectory() as t:
   r,j=self.setup(t)
   with patch('next.runtime.status_stream.subprocess.Popen',wraps=subprocess.Popen) as launch:
    result=observe(self.spec([self.frame(),self.frame(),self.frame('succeeded',True)]),r,PLAN,__import__('time').time()+10,j)
   self.assertEqual(launch.call_count,1);self.assertEqual(result['status'],'succeeded');self.assertEqual(len((j/'watch-events.jsonl').read_text().splitlines()),3)
 def test_disconnect_no_reconnect(self):
  with tempfile.TemporaryDirectory() as t:
   r,j=self.setup(t)
   with patch('next.runtime.status_stream.subprocess.Popen',wraps=subprocess.Popen) as launch:
    with self.assertRaisesRegex(ValueError,'NO_RECONNECT'):observe(self.spec([self.frame()]),r,PLAN,__import__('time').time()+10,j)
   self.assertEqual(launch.call_count,1)
 def test_wrong_task_and_watch_nonce_rejected(self):
  for field in ('taskId','watchNonce'):
   with tempfile.TemporaryDirectory() as t:
    r,j=self.setup(t);bad=self.frame();bad[field]='d'*32
    with self.assertRaisesRegex(ValueError,'IDENTITY'):observe(self.spec([bad]),r,PLAN,__import__('time').time()+10,j)
 def test_unknown_worker_state_not_success(self):
  with tempfile.TemporaryDirectory() as t:
   r,j=self.setup(t)
   with self.assertRaisesRegex(ValueError,'WORKER_STOP'):observe(self.spec([self.frame('failed',False)]),r,PLAN,__import__('time').time()+10,j)
 def test_local_guard_missing_prevents_process(self):
  with tempfile.TemporaryDirectory() as t:
   r,j=self.setup(t);beat=json.loads((r/'heartbeat.json').read_text());beat['sleep_held']=False;(r/'heartbeat.json').write_text(json.dumps(beat))
   with patch('next.runtime.status_stream.subprocess.Popen') as launch:
    with self.assertRaisesRegex(ValueError,'GUARD'):observe(self.spec([]),r,PLAN,__import__('time').time()+10,j)
    launch.assert_not_called()
 def test_guard_loss_during_stream_kills_owned_process(self):
  with tempfile.TemporaryDirectory() as t:
   r,j=self.setup(t);p=r/'heartbeat.json';code="import pathlib,time,json;print("+repr(json.dumps(self.frame()))+",flush=True);p=pathlib.Path("+repr(str(p))+");q=json.loads(p.read_text());q['sleep_held']=False;p.write_text(json.dumps(q));time.sleep(20)"
   with patch('next.runtime.status_stream.subprocess.Popen',wraps=subprocess.Popen) as launch:
    with self.assertRaisesRegex(ValueError,'GUARD'):observe({'executable':sys.executable,'arguments':['-u','-c',code],'watchNonce':'c'*32},r,PLAN,__import__('time').time()+10,j)
    self.assertEqual(launch.call_count,1)
 def test_fixed_deadline_kills_no_retry(self):
  with tempfile.TemporaryDirectory() as t:
   r,j=self.setup(t);spec={'executable':sys.executable,'arguments':['-u','-c','import time;time.sleep(20)'],'watchNonce':'c'*32}
   with self.assertRaisesRegex(TimeoutError,'DEADLINE'):observe(spec,r,PLAN,__import__('time').time()+.25,j)
 def test_remote_file_watcher_only_changes_then_terminal(self):
  with tempfile.TemporaryDirectory() as t:
   p=pathlib.Path(t);(p/'joint.json').write_text(json.dumps(PLAN));(p/'run').mkdir();event=p/'run/execution.json';event.write_text(json.dumps({'status':'running','stage':'initialization','taskId':PLAN['taskId'],'nonce':PLAN['nonce']}));ticks=[]
   def advance(_):
    ticks.append(1);event.write_text(json.dumps({'status':'succeeded','stage':'complete','executionStopped':True,'taskId':PLAN['taskId'],'nonce':PLAN['nonce']}))
   out=io.StringIO()
   with contextlib.redirect_stdout(out):watch(p,PLAN['taskId'],PLAN['nonce'],'c'*32,__import__('time').time()+10,sleep=advance)
   values=[json.loads(x) for x in out.getvalue().splitlines()];self.assertEqual([v['status'] for v in values],['running','succeeded']);self.assertEqual(len(ticks),1)
 def test_expired_deadline_never_starts_connection(self):
  with tempfile.TemporaryDirectory() as t:
   r,j=self.setup(t)
   with patch('next.runtime.status_stream.subprocess.Popen') as launch:
    with self.assertRaisesRegex(TimeoutError,'DEADLINE'):observe(self.spec([]),r,PLAN,__import__('time').time()-1,j)
    launch.assert_not_called()
 def test_native_prepare_offline_once_and_no_ssh(self):
  import shutil
  with tempfile.TemporaryDirectory() as t:
   t=pathlib.Path(t);cloud=t/'cloud';cloud.mkdir();run=t/'cloud-runs'/('d'*32);run.mkdir(parents=True);source=t/'project/next/runtime';source.mkdir(parents=True)
   shutil.copyfile(ROOT/'cloud/Prepare-JointWatch.ps1',cloud/'Prepare-JointWatch.ps1');(cloud/'remote_probe.py').write_text('pass');(cloud/'joint_watch_bridge.py').write_text('pass');(source/'joint_watch.py').write_text('pass')
   now=datetime.datetime.now(datetime.timezone.utc)
   values={'host-trust.json':{'user_confirmed':True,'vm_id':'vm-fixture','ip':'127.0.0.1','pin_path':'pin'},'heartbeat.json':{'offline':False,'sleep_held':True,'stopped_verified':False,'supervision_stop_latched':False,'utc':now.isoformat(),'pid':os.getpid()},'launch.json':{'offline':False,'single_run':True,'budget_usd_including_tax':3,'approval_reference':'OFFLINE','deadline_utc':(now+datetime.timedelta(minutes=10)).isoformat()},'timing.json':{'work_deadline_utc':(now+datetime.timedelta(minutes=8)).isoformat()},'live-settings.json':{'known_hosts_path':'pin','container_python':'python'},'request.json':{'prep':'/home/jovyan/preview-'+'d'*32,'taskId':PLAN['taskId'],'nonce':PLAN['nonce']}}
   for n,v in values.items():(run/n).write_text(json.dumps(v),encoding='utf-8')
   stub=r"""function ConvertFrom-JsonUtc {param([Parameter(ValueFromPipeline=$true)]$x)process{$x|ConvertFrom-Json}}
function Write-AtomicJson($p,$v){[IO.File]::WriteAllText($p,($v|ConvertTo-Json -Depth 8))}
function ConvertTo-Base64($t){[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($t))}
function Invoke-Bridge($a){Add-Content (Join-Path $run 'calls.txt') 'API';return [pscustomobject]@{vm_id='vm-fixture';ip='127.0.0.1';ssh_user='fixture';image='fixture'}}
function Get-SshArguments($t){return ,@('-T','fixture')}
function New-EncodedShellCommand($p,$a){return 'fixture-watch-command'}
"""
   (cloud/'Common.ps1').write_text(stub,encoding='utf-8');p=subprocess.run(['powershell.exe','-NoProfile','-File',str(cloud/'Prepare-JointWatch.ps1'),'-RunDirectory',str(run),'-RequestPath',str(run/'request.json'),'-Execute'],capture_output=True,text=True,timeout=20)
   self.assertEqual(p.returncode,0,p.stderr);self.assertEqual((run/'calls.txt').read_text().split(),['API']);spec=json.loads((run/'watch-command.json').read_text());self.assertEqual(spec['arguments'],['-T','fixture','fixture-watch-command']);self.assertFalse(spec['reconnectAllowed']);self.assertEqual(spec['sshSessionsTarget'],1)
 def test_native_prepare_one_precheck_no_poll_ssh(self):
  s=(ROOT/'cloud/Prepare-JointWatch.ps1').read_text();self.assertEqual(s.count('=Invoke-Bridge target'),1);self.assertNotIn('Invoke-NativeSshCommand',s)
  cmd="$t=$null;$e=$null;[System.Management.Automation.Language.Parser]::ParseFile('"+str(ROOT/'cloud/Prepare-JointWatch.ps1')+"',[ref]$t,[ref]$e)|Out-Null;if($e.Count){$e|Out-String;exit 1}"
  p=subprocess.run(['powershell.exe','-NoProfile','-Command',cmd],capture_output=True);self.assertEqual(p.returncode,0,p.stderr)
if __name__=='__main__':unittest.main(verbosity=2)
