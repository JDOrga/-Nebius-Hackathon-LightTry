"""Explicit synthetic stage evidence, isolated tests only; never selectable by production."""
import sys
import time
import uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from inference.jobs import atomic,read
from inference.images import digest
from inference.reuse import identity,complete
from inference_fixture import OfflineExecutor,image_bytes


class BatchFixtureExecutor(OfflineExecutor):
    def submit(self,folder,request):
        super().submit(folder,request)
        atomic(folder/'runtime-binding.json',{'guardRunId':'f'*32,'testDouble':True})
        self.event('running','forward')

    def finish_batch(self,outcome='partial'):
        folder,request=self.calls[-1]
        evidence=folder/'remote-evidence';evidence.mkdir(exist_ok=True)
        config=read(folder/'request.json');config['input']={k:v for k,v in config['input'].items() if k not in ('name','url','originalUrl')}
        atomic(evidence/'configuration.json',{'request':config,'testDouble':True})
        weights=read(ROOT.parent/'manifests/weights_manifest.json');patch=read(ROOT.parent/'manifests/patch_manifest.json')
        value=identity(request,(folder/'inputs/photo.png').read_bytes(),weights,patch)
        inverse=evidence/'inverse';gbuffer=inverse/'gbuffer_frames/photo';gbuffer.mkdir(parents=True,exist_ok=True)
        payload=image_bytes((1280,704),'JPEG')
        for label in ('basecolor','normal','depth','roughness','metallic'):
            (gbuffer/f'0000.0000.{label}.jpg').write_bytes(payload)
        provenance=complete(inverse,value,{'taskId':request['taskId'],'nonce':request['nonce'],'inverseExitCode':0,'inputEncodedSha256':request['input']['sha256'],'weightVerification':'full','testDouble':True})
        for n,preset in enumerate(request['presets']):
            item=evidence/'presets'/str(preset['index']);item.mkdir(parents=True)
            if n>0 and outcome=='partial':
                atomic(item/'state.json',{'status':'failed','error':'OFFLINE_TEST_SECOND_FAILURE'});continue
            attempt=uuid.uuid4().hex;directory=item/attempt/f"relit_frames_{preset['index']:04d}/photo";directory.mkdir(parents=True)
            (directory/'0000.0000.jpg').write_bytes(payload)
            ident={'inverseKey':provenance['key'],'inverseArtifacts':provenance['artifacts'],
                'request':{'taskId':request['taskId'],'nonce':request['nonce'],'inputId':request['input']['id'],
                    'inputSha256':request['input']['sha256'],'originalSha256':request['original']['sha256']},
                'forwardModel':[e for e in weights['files'] if not e['path'].startswith('Diffusion_Renderer_Inverse_Cosmos_7B/')],
                'patch':patch,'config':request['runConfig'],'hdr':preset,'randomPolicy':'reset-before-forward-generate-v1'}
            atomic(item/'complete.json',{'identity':ident,'attempt':attempt,'result':{'path':f"relit_frames_{preset['index']:04d}/photo/0000.0000.jpg",'sha256':digest(payload),'bytes':len(payload)},
                'source':{'process':'e'*32,'presetIndex':preset['index'],'modelObjectId':'OFFLINE_TEST_OBJECT'},'completedEpoch':time.time(),
                'seed':1000,'randomPolicy':'reset-before-forward-generate-v1','testDouble':True})
            atomic(item/'state.json',{'status':'succeeded','testDouble':True})
        self.event('failed' if outcome=='partial' else 'succeeded','validating',True)
