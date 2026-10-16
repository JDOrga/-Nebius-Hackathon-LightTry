"""Exact VM installer argv/stdin -> actual container installer, no real SSH/Docker/model."""
import base64,contextlib,hashlib,io,json,sys,tempfile,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_bootstrap_vm_identity import program
from gpu_bootstrap_package import build,archive

class WireTests(unittest.TestCase):
 def exercise(self,tamper=False):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);bundle=build(root/'package');code=Path(bundle['archive']).read_bytes();sid='b'*32;host={'sshUser':'nebius','vmId':'computeinstance-fixture'};deadline=time.time()+60
   grant=dict(sessionId=sid,resourceId='fixture',hostIdentity=host,hostConfirmed=True,modelLicenseAck=True,expiresAt=deadline)
   worker=dict(schemaVersion=1,enabled=True,executionMode='resident',python='/fixture/model-python',grantFile='/unused',repo='/fixture/repo',checkpointDir='/fixture/weights',cudaHome='/fixture/cuda')
   secret=archive({'worker.json':json.dumps(worker).encode(),'model-grant.json':json.dumps(grant).encode(),'tls.crt':b'SYNTHETIC_CERT','tls.key':b'SYNTHETIC_KEY','worker.token':b'SYNTHETIC_TOKEN_ONLY','launch.json':json.dumps({'deadline':deadline}).encode()})
   installer=Path('project/gpu_bootstrap_container.py').read_text()
   q=dict(sessionId=sid,resourceId='fixture',hostIdentity=host,deadline=deadline,image='fixture',tlsPort=0,containerPython='/fixture/model-python',codeSha256=hashlib.sha256(code).hexdigest(),secretSha256=hashlib.sha256(secret).hexdigest(),installer=base64.b64encode(installer.encode()).decode(),operation='install',containerId='a'*64,tlsBind='127.0.0.1')
   vm=program();vm['metadata_vm_id']=Mock(return_value=host['vmId'])
   item={'Id':'a'*64,'State':{'Running':True},'Config':{'Image':'fixture','User':'jovyan'},'Mounts':[{'Destination':'/home','RW':True}],'HostConfig':{'NetworkMode':'host'}}
   vm['docker']=Mock(side_effect=['a'*64,json.dumps([item])]);actual_open=open;docker_calls=[]
   def remote_open(path,*args,**kwargs):
    if str(path)=='/home/nebius/lighttry-bootstrap-'+sid+'/gpu-service.tar.gz':return io.BytesIO(code+(b'changed' if tamper else b''))
    if str(path)=='/home/nebius/lighttry-bootstrap-'+sid+'/session-secrets.tar.gz':return io.BytesIO(secret)
    return actual_open(path,*args,**kwargs)
   def docker_exec(command,**kw):
    docker_calls.append(command)
    self.assertEqual(command[:7],['sudo','-n','docker','exec','-i','-u','jovyan'])
    self.assertEqual(command[7:12],['-w','/home/jovyan','a'*64,'/fixture/model-python','-B'])
    self.assertEqual(command[12],'-c');self.assertEqual(command[13],installer);decoded=json.loads(base64.b64decode(command[14]));self.assertEqual(decoded,q)
    self.assertLessEqual(kw['timeout'],20);self.assertTrue(kw['capture_output'])
    namespace={'__name__':'offline_container_installer'};exec(compile(command[13],'exact-container-python-c','exec'),namespace)
    with patch('subprocess.Popen',return_value=SimpleNamespace(pid=12345)) as spawn:
     receipt=namespace['install_files'](decoded,io.BytesIO(kw['input']),root/'deployed')
     spawn.assert_called_once();launch=spawn.call_args.args[0];self.assertEqual(launch[0],'/fixture/model-python');self.assertIn('--worker-tls-cert',launch);self.assertIn('--worker-config',launch)
     self.assertTrue((root/'deployed'/sid/'launch-attempt').exists())
     deployed=json.loads((root/'deployed'/sid/'secrets/worker.json').read_text());self.assertEqual(deployed['grantFile'],str(root/'deployed'/sid/'secrets/model-grant.json'))
    return SimpleNamespace(returncode=0,stdout=json.dumps(receipt).encode(),stderr=b'')
   with patch.dict(sys.modules,{'pwd':SimpleNamespace(getpwuid=lambda _:SimpleNamespace(pw_name='nebius'))}),patch('os.getuid',return_value=1000,create=True),patch('builtins.open',side_effect=remote_open),patch('subprocess.run',side_effect=docker_exec),contextlib.redirect_stdout(io.StringIO()) as output:
    if tamper:
     with self.assertRaisesRegex(ValueError,'VM_ARCHIVE_HASH_MISMATCH'):vm['main'](q)
     self.assertEqual(docker_calls,[]);self.assertFalse((root/'deployed').exists());return
    vm['main'](q)
   result=json.loads(output.getvalue());self.assertTrue(result['launchRequested']);self.assertEqual(result['workerPid'],12345);self.assertEqual(len(docker_calls),1)
 def test_exact_vm_docker_wire_runs_actual_installer_with_single_mocked_worker_launch(self):self.exercise()
 def test_changed_upload_hash_stops_before_docker_exec_or_installer(self):self.exercise(tamper=True)

if __name__=='__main__':unittest.main()
