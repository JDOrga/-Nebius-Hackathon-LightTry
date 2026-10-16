"""Synthetic result transport -> real product validation/download; not model output."""
import copy,hashlib,io,json,tarfile,time,unittest
import test_real_links as fixtures
from inference.jobs import TaskStore,atomic,JobError
from inference_fixture import image_bytes

class ResultPathTests(unittest.TestCase):
 def setUp(self):
  self.f=fixtures.ModelTests();self.f.setUp();f=self.f
  from inference.images import prepare
  canvas=prepare((f.folder/'inputs/photo.png').read_bytes(),f.folder/'inputs/photo.png')
  f.request['input'].update(canvas=canvas,sha256=canvas['sha256'])
  f.request['runConfig']['modelExecutionMode']='resident-v1';atomic(f.folder/'request.json',f.request)
  self.store=TaskStore(f.folder.parent,[f.request['preset']],f.cpu)
  now=time.time();self.task={**copy.deepcopy(f.request),'status':'queued','stage':'queued','result':None,'error':None,'createdAt':now,'updatedAt':now,'deadline':now+100,'expiresAt':None,'executionUncertain':False,'requestId':'9'*32}
  # No batch/parameter claim here: this tests exact single-result HTTP transport path.
  atomic(f.folder/'task.json',self.task)
  self.image=image_bytes((1280,704),'JPEG');r=f.request;finished=time.time()
  self.receipt=dict(taskId=r['taskId'],nonce=r['nonce'],inputId=r['input']['id'],presetId=r['preset']['id'],inputSha256=r['input']['sha256'],originalSha256=r['original']['sha256'],runConfig=r['runConfig'],file='result.jpg',sha256=hashlib.sha256(self.image).hexdigest(),bytes=len(self.image),executionMode='resident',processExitCodes=[None,None],finishedAt=finished,inverseReuse={'reused':False,'source':{'taskId':r['taskId']},'key':'d'*64},residentExecution={'version':1,'taskId':r['taskId'],'nonce':r['nonce'],'phases':[dict(phase=phase,id=str(i)*32,bootId='c'*32,pid=100+i,modelObjectId='0xabcd',exitCode=0,cudaSynchronized=True,completedAt=finished) for i,phase in enumerate(('inverse','forward'),1)]})
  self.receipt['gBuffers']=[dict(channel=label,relativePath='inverse/gbuffer_frames/photo.'+label+'.jpg',size=len(self.image),sha256=hashlib.sha256(self.image).hexdigest()) for label in ('basecolor','normal','depth','roughness','metallic')]
 def tearDown(self):self.store.close();self.f.tearDown()
 def remote_result(self,with_inverse=False,tamper_inverse=False):
  f=self.f;f.cpu.submit(f.folder,f.request);envelope=json.loads((f.folder/'https-binding.json').read_text())['envelope']
  files={'result.jpg':self.image,'receipt.json':json.dumps(self.receipt).encode(),'execution.json':json.dumps(dict(taskId=f.request['taskId'],nonce=f.request['nonce'],status='succeeded',stage='validating',executionStopped=True)).encode()}
  files.update({x['relativePath']:self.image for x in self.receipt['gBuffers']})
  if with_inverse:
   from model_contract import model_request
   from lighting import canonical
   from inference.reuse import identity,key
   from pathlib import Path
   root=Path(__file__).resolve().parents[2]
   wire=json.loads(canonical(model_request(f.request)))
   value=identity(wire,(f.folder/'inputs/photo.png').read_bytes(),json.loads((root/'manifests/weights_manifest.json').read_text()),json.loads((root/'manifests/patch_manifest.json').read_text()))
   if tamper_inverse:value['config']['seed']+=1
   record={'schema':1,'identity':value,'key':key(value),'source':{'taskId':f.request['taskId'],'nonce':f.request['nonce'],'inverseExitCode':0},
     'artifacts':[{'channel':x['channel'],'path':'photo.'+x['channel']+'.jpg','bytes':len(self.image),'sha256':hashlib.sha256(self.image).hexdigest()} for x in self.receipt['gBuffers']]}
   files['inverse/inverse-complete.json']=json.dumps(record).encode()
  buffer=io.BytesIO()
  with tarfile.open(fileobj=buffer,mode='w:gz') as archive:
   for name,raw in files.items():
    info=tarfile.TarInfo(name);info.size=len(raw);archive.addfile(info,io.BytesIO(raw))
  raw=buffer.getvalue();f.worker.query.return_value={**envelope,'status':'succeeded','resultSha256':hashlib.sha256(raw).hexdigest()};f.worker.download.return_value=raw
  f.cpu.reconcile(f.folder)
 def test_wire_numeric_inverse_identity_reaches_product_without_retry(self):
  f=self.f;original=copy.deepcopy(f.request)
  self.assertIsInstance(f.request['runConfig']['guidance'],float)
  self.remote_result(with_inverse=True)
  self.assertEqual(f.request,original)
  self.assertIsInstance(f.request['runConfig']['guidance'],float)
  self.assertEqual(self.store.get(f.request['taskId'])['status'],'succeeded')
  self.assertEqual(self.store.file(f.request['taskId'],'download')[0],self.image)
  self.assertFalse((f.folder/'https-result-rejected.json').exists())
  f.cpu.reconcile(f.folder);f.worker.download.assert_called_once()
 def test_actual_changed_inverse_identity_remains_rejected(self):
  with self.assertRaisesRegex(ValueError,'INVERSE_IDENTITY_MISMATCH'):
   self.remote_result(with_inverse=True,tamper_inverse=True)
  self.assertTrue((self.f.folder/'https-result-rejected.json').exists())
  self.assertFalse((self.f.folder/'execution.json').exists())
 def test_verified_synthetic_archive_reaches_real_product_download(self):
  self.remote_result();f=self.f;value=self.store.get(f.request['taskId']);self.assertEqual(value['status'],'succeeded',value)
  payload,mime,name=self.store.file(f.request['taskId'],'download');self.assertEqual(payload,self.image);self.assertEqual(mime,'image/jpeg');self.assertTrue(name.endswith('_full.jpg'))
  f.cpu.reconcile(f.folder);f.worker.download.assert_called_once()
 def test_wrong_cuda_proof_never_enables_download(self):
  self.receipt['residentExecution']['phases'][0]['cudaSynchronized']=False;self.remote_result();f=self.f
  self.assertEqual(self.store.get(f.request['taskId'])['status'],'failed')
  with self.assertRaises(JobError):self.store.file(f.request['taskId'],'download')
 def test_download_revalidates_bytes_after_public_success(self):
  self.remote_result();f=self.f;self.assertEqual(self.store.get(f.request['taskId'])['status'],'succeeded')
  (f.folder/'result.jpg').write_bytes(b'tampered')
  with self.assertRaises(JobError):self.store.file(f.request['taskId'],'download')

if __name__=='__main__':unittest.main()
