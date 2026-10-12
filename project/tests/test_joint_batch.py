"""OFFLINE: real retained results as fixtures, mocked network, no API/SSH/GPU."""
import base64,copy,hashlib,importlib.util,io,json,pathlib,subprocess,sys,tempfile,types,unittest
from unittest.mock import patch,mock_open
ROOT=pathlib.Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'project'))
from next.runtime.joint_bundle import build,MAX_ARCHIVE
from next.runtime.joint_results import extract
BASE=ROOT/'.local/lighttry-joint-20261012/ai-confirmed-package';RESULTS=BASE/'execution/results';PLAN=json.loads((BASE/'packet/joint.json').read_text())
def module(path,name):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
DRIVER=module(ROOT/'scripts/run_joint_batch.py','batch_driver_test')
@unittest.skipUnless(RESULTS.is_dir(), 'requires retained authorized result fixture; no remote fallback')
class BatchTests(unittest.TestCase):
 def pack(self):return build(RESULTS,BASE/'packet',PLAN['taskId'],PLAN['nonce'])
 def test_all_real_retained_cases_one_archive(self):
  data,m=self.pack();self.assertLess(len(data),MAX_ARCHIVE);self.assertEqual(m['completed'],['A','B','C','D','E','F','AI'])
  with tempfile.TemporaryDirectory() as t:
   t=pathlib.Path(t);a=t/'all.tar.gz';a.write_bytes(data);job=t/'job';job.mkdir();out=t/'results';out.mkdir();remote=json.loads((BASE/'execution/last-observed.json').read_text())
   with patch.object(DRIVER,'validate_case',wraps=DRIVER.validate_case) as check:
    got=DRIVER.consume_bundle(BASE,job,out,remote,{**m,'local_path':str(a)});self.assertEqual(len(got),7);self.assertEqual(check.call_count,7)
 def test_hash_corruption_rejected(self):
  data,m=self.pack()
  with tempfile.TemporaryDirectory() as t:
   a=pathlib.Path(t)/'bad.tar.gz';a.write_bytes(data+b'bad')
   with self.assertRaisesRegex(ValueError,'HASH'):extract(a,pathlib.Path(t)/'out',m['sha256'])
 def test_wrong_task_rejected(self):
  with self.assertRaisesRegex(ValueError,'IDENTITY'):build(RESULTS,BASE/'packet','wrong',PLAN['nonce'])
 def test_running_and_unknown_process_rejected(self):
  import next.runtime.joint_bundle as b
  actual=b.read
  for e in [{'status':'running','executionStopped':False},{'status':'failed','executionStopped':False}]:
   event={**actual(RESULTS/'execution.json'),**e}
   with patch.object(b,'read',side_effect=lambda p:event if p.name=='execution.json' else actual(p)):
    with self.assertRaisesRegex(ValueError,'TERMINAL'):self.pack()
 def test_failed_partial_preserves_completed_only(self):
  import next.runtime.joint_bundle as b
  original_read=b.read;original_exists=pathlib.Path.exists
  event={**original_read(RESULTS/'execution.json'),'status':'failed','executionStopped':True}
  def exists(p):
   return False if p.name=='complete.json' and 'cases' in p.parts and p.parts[p.parts.index('cases')+1] not in ('A','B') else original_exists(p)
  with patch.object(b,'read',side_effect=lambda p:event if p.name=='execution.json' else original_read(p)),patch.object(pathlib.Path,'exists',exists):
   data,m=self.pack();self.assertEqual(m['completed'],['A','B']);self.assertEqual(m['status'],'failed')
 def test_overflow_fails_no_chunk_fallback(self):
  with patch('next.runtime.joint_bundle.MAX_ARCHIVE',1):
   with self.assertRaisesRegex(ValueError,'NO_CHUNK_FALLBACK'):self.pack()
 def test_missing_hdr_proof_fails(self):
  import next.runtime.joint_results as r
  actual=r.read
  def read(p):
   q=actual(p)
   if p.name=='condition.json':q['loaderHookEffective']=False
   return q
  with patch.object(r,'read',read):
   with self.assertRaisesRegex(ValueError,'HDR_PROOF'):self.pack()
 def test_single_ssh_bridge_and_framing(self):
  data,m=self.pack();probe="def docker(*args):\n return 'a'*64 if args[0]=='ps' else '[]'\ndef choose_container(items,image):\n return 'a'*64\n"
  pwd=types.SimpleNamespace(getpwuid=lambda uid:types.SimpleNamespace(pw_name='nebius'))
  with patch.dict(sys.modules,pwd=pwd):bridge=module(ROOT/'cloud/joint_bundle_bridge.py','batch_bridge_test')
  q={'root':'/home/jovyan/nebius-cosmos/preview-'+'b'*32+'/run','taskId':PLAN['taskId'],'nonce':PLAN['nonce']}
  req={'ssh_user':'nebius','run_id':'b'*32,'image':'fixture','nonce':'c'*32,'container_python':'python','container_request':q,'probe_source':base64.b64encode(probe.encode()).decode(),'container_program':base64.b64encode(b'pass').decode()}
  output=io.StringIO()
  with patch.object(bridge.subprocess,'run',return_value=types.SimpleNamespace(returncode=0,stdout=data)) as execute,patch('builtins.open',mock_open()),patch.object(bridge.os,'getuid',return_value=1000,create=True),patch('sys.stdout',output):bridge.main(req)
  self.assertEqual(execute.call_count,1);lines=output.getvalue().splitlines();self.assertEqual(lines[-1],'LOCAL_DONE_'+'c'*32)
  frame=json.loads(lines[0].split(':',1)[1]);body=json.loads(frame['output']);self.assertEqual(base64.b64decode(body['dataBase64']),data);self.assertLess(len(output.getvalue().encode()),1048576)
 def test_powershell_transport_offline_one_api_one_ssh(self):
  import shutil,datetime
  data,m=self.pack()
  with tempfile.TemporaryDirectory() as t:
   t=pathlib.Path(t);cloud=t/'cloud';cloud.mkdir();run=t/'cloud-runs'/('b'*32);run.mkdir(parents=True);(t/'project/next/runtime').mkdir(parents=True)
   shutil.copyfile(ROOT/'cloud/Retrieve-JointBundle.ps1',cloud/'Retrieve-JointBundle.ps1')
   (cloud/'remote_probe.py').write_text('pass');(cloud/'joint_bundle_bridge.py').write_text('pass');(t/'project/next/runtime/joint_bundle.py').write_text('pass')
   now=datetime.datetime.now(datetime.timezone.utc)
   values={'host-trust.json':{'user_confirmed':True,'vm_id':'vm-fixture','ip':'127.0.0.1','pin_path':'pin'},
    'heartbeat.json':{'offline':False,'sleep_held':True,'stopped_verified':False,'supervision_stop_latched':False,'utc':now.isoformat(),'pid':__import__('os').getpid()},
    'launch.json':{'offline':False,'single_run':True,'budget_usd_including_tax':3,'approval_reference':'offline-fixture','deadline_utc':(now+datetime.timedelta(minutes=10)).isoformat()},
    'timing.json':{'work_deadline_utc':(now+datetime.timedelta(minutes=8)).isoformat()},
    'live-settings.json':{'known_hosts_path':'pin','container_python':'python'},
    'request.json':{'root':'fixture','taskId':PLAN['taskId'],'nonce':PLAN['nonce']},
    'frame-fixture.json':{**m,'dataBase64':base64.b64encode(data).decode()}}
   for name,value in values.items():(run/name).write_text(json.dumps(value),encoding='utf-8')
   stub=r"""function ConvertFrom-JsonUtc { param([Parameter(ValueFromPipeline=$true)]$x) process { if(!$x){throw 'EMPTY_FIXTURE_JSON'}; Write-Host ('JSON_FIXTURE_INPUT='+([string]$x).Substring(0,[Math]::Min(80,([string]$x).Length))); $x|ConvertFrom-Json } }
function Write-AtomicJson($p,$v){[IO.File]::WriteAllText($p,($v|ConvertTo-Json -Depth 8))}
function ConvertTo-Base64($t){[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($t))}
function Invoke-Bridge($action){Add-Content (Join-Path $run 'calls.txt') 'API';return [pscustomobject]@{vm_id='vm-fixture';ip='127.0.0.1';ssh_user='fixture';image='fixture'}}
function Get-SshArguments($t){return ,@('-T','fixture')}
function New-EncodedShellCommand($p,$a){return 'fixture-command'}
function Invoke-NativeSshCommand($a,$c,$p,$Context){Add-Content (Join-Path $run 'calls.txt') 'SSH';$m=[IO.File]::ReadAllText((Join-Path $run 'frame-fixture.json'));$r=@{nonce=$nonce;operation='retrieve_joint_bundle';image='fixture';output=$m};return ('LOCAL_RESULT_'+$nonce+':'+($r|ConvertTo-Json -Compress)+[Environment]::NewLine+'LOCAL_DONE_'+$nonce)}
function Read-RemoteResult($o,$n,$op,$i){return (($o -split '\r?\n')[0].Substring(('LOCAL_RESULT_'+$n+':').Length)|ConvertFrom-Json)}
"""
   (cloud/'Common.ps1').write_text(stub,encoding='utf-8')
   cmd=['powershell.exe','-NoProfile','-File',str(cloud/'Retrieve-JointBundle.ps1'),'-RunDirectory',str(run),'-RequestPath',str(run/'request.json'),'-Execute']
   p=subprocess.run(cmd,capture_output=True,text=True,timeout=20);self.assertEqual(p.returncode,0,p.stdout+p.stderr);self.assertEqual((run/'calls.txt').read_text().split(),['API','SSH']);self.assertEqual((run/'joint-results.tar.gz').read_bytes(),data)
 def test_transport_ast_and_once_only_contract(self):
  s=(ROOT/'cloud/Retrieve-JointBundle.ps1').read_text(encoding='utf-8-sig');self.assertEqual(s.count('=Invoke-Bridge target'),1);self.assertEqual(s.count('=Invoke-NativeSshCommand '),1);self.assertNotIn('scp.exe',s)
  cmd="$t=$null;$e=$null;[System.Management.Automation.Language.Parser]::ParseFile('"+str(ROOT/'cloud/Retrieve-JointBundle.ps1')+"',[ref]$t,[ref]$e)|Out-Null;if($e.Count){$e|Out-String;exit 1}"
  p=subprocess.run(['powershell.exe','-NoProfile','-Command',cmd],capture_output=True,text=True);self.assertEqual(p.returncode,0,p.stderr)
if __name__=='__main__':unittest.main(verbosity=2)




