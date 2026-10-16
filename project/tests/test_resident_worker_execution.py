"""Execute original worker.main with synthetic model runner; zero cloud/GPU calls."""
import copy,hashlib,importlib.util,json,os,shutil,sys,tempfile,types
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'project'),str(ROOT/'scripts')]
from inference.jobs import RUN_CONFIG
import inference.batch as batch

def probe(source, *, bad_hdr=False, expired=False, resident=True):
    spec=importlib.util.spec_from_file_location('worker_probe',source)
    worker=importlib.util.module_from_spec(spec);spec.loader.exec_module(worker)
    native=type(Path());seen=[];heavy=[]
    with tempfile.TemporaryDirectory() as tmp:
        prep=Path(tmp);repo=prep/'repo';hdr=repo/'asset/examples/hdri_examples/sunny_vondelpark_2k.hdr'
        hdr.parent.mkdir(parents=True);hdr.write_bytes(b'SYNTHETIC_HDR')
        (prep/'inputs').mkdir();(prep/'inputs/photo.png').write_bytes(b'SYNTHETIC_INPUT')
        (prep/'manifests').mkdir()
        for name in ['weights_manifest.json','patch_manifest.json']:
            shutil.copyfile(ROOT/'manifests'/name,prep/'manifests'/name)
        preset={'id':'FIXTURE','index':0,'hdr':hdr.name,'sha256':hashlib.sha256(hdr.read_bytes()).hexdigest()}
        if bad_hdr:preset['sha256']='0'*64
        job={'taskId':'a'*32,'nonce':'b'*32,'runConfig':copy.deepcopy(RUN_CONFIG),'preset':preset,'presets':[preset],
             'input':{'id':'FIXTURE','sha256':hashlib.sha256(b'SYNTHETIC_INPUT').hexdigest()},'original':{'sha256':'c'*64}}
        for name,value in [('request',job),('runtime',{'executionMode':'resident' if resident else 'per-job','repo':str(repo),
               'checkpoint_dir':str(prep),'cuda_home':str(prep),'deadline_utc':'2000-01-01T00:00:00+00:00' if expired else '2099-01-01T00:00:00+00:00','model_license_ack':True}),
             ('receipt',{'offline':False,'single_run':True,'approval_reference':'SYNTHETIC','budget_usd_including_tax':3,'deadline_utc':'2099-01-01T00:00:00+00:00'})]:
            (prep/(name+'.json')).write_text(json.dumps(value),encoding='utf-8')
        def execute(job,inp,run,weights,patch_manifest,*args,**kwargs):
            assert weights==json.loads((ROOT/'manifests/weights_manifest.json').read_text())
            assert patch_manifest==json.loads((ROOT/'manifests/patch_manifest.json').read_text())
            seen.append('identity_metadata_received')
            out=run/'presets/0/attempt/relit_frames_0000';out.mkdir(parents=True)
            (out/'fixture.jpg').write_bytes(b'SYNTHETIC_RESULT')
            (out.parent.parent/'complete.json').write_text('{"attempt":"attempt"}')
            return {'source':{'taskId':job['taskId']},'key':'FIXTURE'}
        real_relative=native.is_relative_to
        def relative(self,*parts):
            return True if parts==('/home/jovyan',) else real_relative(self,*parts)
        worker.PREP=prep;worker.Path=native
        worker.os=types.SimpleNamespace(name='posix',environ=os.environ,replace=os.replace)
        worker.sys=types.SimpleNamespace(version_info=(3,10),executable=sys.executable)
        def forbidden(*args,**kwargs):heavy.append('FORBIDDEN');raise AssertionError('GPU_OR_HEAVY_PROBE_FORBIDDEN')
        try:
            with patch.object(native,'is_relative_to',relative),patch.object(sys,'argv',['worker','--request',str(prep/'request.json'),'--runtime',str(prep/'runtime.json'),'--receipt',str(prep/'receipt.json')]),patch.object(batch,'execute',execute),patch.object(worker,'run_bounded',forbidden),patch.object(worker,'verify',forbidden),patch.object(worker.subprocess,'run',forbidden),patch.object(worker,'validate_inverse',return_value=[]),patch.object(worker,'inspect',return_value=([{'sha256':'d'*64,'size':16}],None)):
                worker.main()
            outcome='succeeded';error=None
        except BaseException as exc:outcome=type(exc).__name__;error=str(exc)
        event=json.loads((prep/'run/execution.json').read_text()) if (prep/'run/execution.json').exists() else None
        return {'outcome':outcome,'error':error,'identityMetadataReceived':bool(seen),'heavyCalls':len(heavy),'cloudStarts':0,'modelCalls':0,'eventStatus':event.get('status') if event else None}


import unittest
class ResidentWorkerExecutionTests(unittest.TestCase):
    source=ROOT/'project/inference/worker.py'
    def test_resident_metadata_reaches_execution_and_receipt(self):
        result=probe(self.source)
        self.assertEqual(result['outcome'],'succeeded',result)
        self.assertTrue(result['identityMetadataReceived'])
        self.assertEqual(result['heavyCalls'],0)
        self.assertEqual(result['eventStatus'],'succeeded')
    def test_resident_hdr_identity_is_still_enforced(self):
        result=probe(self.source,bad_hdr=True)
        self.assertEqual(result['error'],'HDR_IDENTITY_MISMATCH')
        self.assertFalse(result['identityMetadataReceived'])
        self.assertEqual(result['heavyCalls'],0)
    def test_expired_request_cannot_reach_execution(self):
        result=probe(self.source,expired=True)
        self.assertNotEqual(result['outcome'],'succeeded')
        self.assertFalse(result['identityMetadataReceived'])
    def test_per_job_still_requires_original_verification(self):
        result=probe(self.source,resident=False)
        self.assertEqual(result['heavyCalls'],1)
        self.assertFalse(result['identityMetadataReceived'])
        self.assertEqual(result['outcome'],'AssertionError')
if __name__=='__main__':unittest.main()
