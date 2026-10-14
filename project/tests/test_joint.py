"""Explicit OFFLINE SYNTHETIC model tests; never represent Nemotron/GPU proof."""
import copy
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from runtime import joint
from runtime.joint_language import semantic,verify_applied
from runtime.joint_results import payload,extract,validate_case
from inference.jobs import atomic,read
from inference.timing import Timeline
from light_console import synthesize,encode_hdr,initial,preprocessing_parameters
from lighting import identity

ENVS={e['id']:e for e in read(Path(__file__).resolve().parents[1]/'runtime/environments.json')}

class MatrixTests(unittest.TestCase):
    def test_single_factors(self):
        m=joint.matrix(ENVS)
        for n,f in [('C','azimuthDeg'),('D','strength'),('E','sizeDeg')]:
            self.assertEqual([d['field'] for d in joint.changes(m['B'],m[n])],['/zones/0/'+f])
        self.assertEqual(m['F']['zones'][0],m['B']['zones'][0]);self.assertEqual(len(m['F']['zones']),2)
    def test_size_changes_energy_not_peak_amplitude(self):
        m=joint.matrix(ENVS);b=joint.energy(synthesize(m['B']));e=joint.energy(synthesize(m['E']))
        self.assertGreater(e['sphericalIntegralRGB'][0],b['sphericalIntegralRGB'][0]*3)
        self.assertLess(abs(e['peakRGB'][0]-b['peakRGB'][0]),.03)
    def test_first_and_followup(self):
        m=joint.matrix(ENVS);f=m['F'];semantic(initial(ENVS['sunny']),f,'first',ENVS)
        q=copy.deepcopy(f);q['zones'][1]['strength']=.35
        _,delta=semantic(f,q,'second',ENVS);self.assertEqual(len(delta),1)
    def test_followup_rejects_extra_changes(self):
        f=joint.matrix(ENVS)['F'];q=copy.deepcopy(f);q['zones'][1]['strength']=.35;q['zones'][0]['azimuthDeg']=60
        with self.assertRaisesRegex(ValueError,'FOLLOWUP'):semantic(f,q,'second',ENVS)
    def test_id_order_stable(self):
        f=joint.matrix(ENVS)['F'];q=copy.deepcopy(f);q['zones'].reverse()
        with self.assertRaisesRegex(ValueError,'STABLE'):semantic(f,q,'second',ENVS)
    def test_text_does_not_apply(self):
        f=joint.matrix(ENVS)['F']
        with self.assertRaisesRegex(ValueError,'FOLLOWUP'):semantic(f,f,'second',ENVS)
    def test_fake_provider_rejected(self):
        with self.assertRaisesRegex(ValueError,'REAL_CONFIRMED'):verify_applied({'confirmed':True,'modelCalled':False})

class SessionTests(unittest.TestCase):
    def setUp(self):
        import numpy as np
        import torch
        torch.set_num_threads(2)
        self.temp=tempfile.TemporaryDirectory();self.prep=Path(self.temp.name)
        self.root=self.prep/'run/presets';self.root.mkdir(parents=True)
        recipes=joint.matrix(ENVS)
        self.plan={'cases':[{'id':k,'parameters':v,'recipeKey':identity(v),'hdrFile':'recipes/'+k+'.hdr','hdrSha256':'f'*64,'source':'OFFLINE_SYNTHETIC_NOT_GPU','comparison':'offline fixture'} for k,v in recipes.items()], 'taskId':'a'*32,'nonce':'b'*32}
        for c in self.plan['cases']:
            p=self.prep/c['hdrFile'];p.parent.mkdir(exist_ok=True);p.write_bytes(b'explicit synthetic HDR')
        atomic(self.prep/'joint.json',self.plan);atomic(self.root/'identities.json',{'0':{'OFFLINE_SYNTHETIC':True}})
        self.count=0;owner=self
        class Pipeline:
            def __init__(self,**kw):owner.count+=1
            def generate_video(self,**kw):return None
        def demo(args):
            p=self.module.DiffusionRendererPipeline()
            result=self.module.process_environment_map('carrier')
            batch={k:torch.tensor(v)[None].permute(0,4,1,2,3)*2-1 for k,v in result.items()}
            batch['env_nrm']=torch.zeros((1,3,1,704,1280))
            p.generate_video(data_batch=batch)
            from PIL import Image
            path=Path(args.video_save_folder)/'relit_frames_0000/photo/0000.0000.jpg';path.parent.mkdir(parents=True)
            arr=np.zeros((704,1280,3),dtype='uint8');arr[:,640:]=200;Image.fromarray(arr).save(path)
        self.module=types.SimpleNamespace(DiffusionRendererPipeline=Pipeline,process_environment_map=lambda:None,demo=demo,
            ENV_LIGHT_PATH_LIST=['carrier'],torch=types.SimpleNamespace(cuda=types.SimpleNamespace(synchronize=lambda:None)))
        self.args=types.SimpleNamespace(seed=1000,num_steps=15,guidance=0.,height=704,width=1280,num_video_frames=1,rotate_light=False,envlight_ind=[0])
        self.timer=Timeline(self.prep/'timing.jsonl','OFFLINE_SYNTHETIC')
    def tearDown(self):self.temp.cleanup()
    def condition(self,original,recipe,hdr,sha,directory,timeline):
        import numpy as np
        calls=[];arrays={}
        def hook(*a,**k):
            for n in ('env_ldr','env_log'):arrays[n]=np.zeros((1,704,1280,3),dtype='float32')
            report={'hdrSha256':sha,'parameters':preprocessing_parameters(recipe),'device':'cuda',
                'loaderHookEffective':True,'OFFLINE_SYNTHETIC':True}
            calls.append(report);atomic(directory/'condition.json',report);return arrays
        return hook,calls,arrays
    def run_session(self,hook=None):
        from inference.batch import validate_forward_result
        with patch.object(joint,'verify_joint',return_value=self.plan),patch.object(joint,'strict_condition',side_effect=hook or self.condition):
            joint.session(self.args,self.module,self.timer,self.root,validate_forward_result)
    def test_one_initialization_six_forwards_and_resume_zero(self):
        self.run_session();self.assertEqual(self.count,1)
        events=[json.loads(v) for v in (self.prep/'timing.jsonl').read_text().splitlines()]
        end=[e for e in events if e['event']=='joint_complete'][-1];self.assertEqual((end['initializationCount'],end['forwardCount'],end['inverseCount']),(1,6,0))
        for c in self.plan['cases']:validate_case(self.prep,self.prep/'run',c)
        self.run_session();self.assertEqual(self.count,1)
    def test_second_failure_preserves_first(self):
        n=0
        def fail(*a,**kw):
            nonlocal n
            n+=1
            if n==2:raise ValueError('SYNTHETIC_CONDITION_FAILURE')
            return self.condition(*a,**kw)
        with self.assertRaisesRegex(ValueError,'SYNTHETIC_CONDITION_FAILURE'):self.run_session(fail)
        self.assertTrue((self.prep/'run/cases/A/0/complete.json').exists());self.assertFalse((self.prep/'run/cases/B/0/complete.json').exists())
    def test_missing_hook_never_completes(self):
        def empty(*a,**kw):return lambda *x,**y:{},[],{}
        with self.assertRaisesRegex(ValueError,'HOOK_REQUIRED'):self.run_session(empty)
        self.assertFalse((self.prep/'run/cases/A/0/complete.json').exists())
    def test_export_and_identity_mismatch(self):
        self.run_session();data=payload(self.prep/'run','case0');archive=self.prep/'case0.tar.gz';archive.write_bytes(data)
        target=self.prep/'retrieved';target.mkdir();extract(archive,target,hashlib.sha256(data).hexdigest())
        validate_case(self.prep,target,self.plan['cases'][0])
        bad=copy.deepcopy(self.plan['cases'][0]);bad['recipeKey']='0'*64
        with self.assertRaisesRegex(ValueError,'IDENTITY'):validate_case(self.prep,target,bad)
    def test_archive_wrong_hash(self):
        p=self.prep/'bad.tar.gz';p.write_bytes(b'bad')
        with self.assertRaisesRegex(ValueError,'HASH'):extract(p,self.prep/'retrieved','0'*64)
    def test_proof_tamper_rejected_not_repaired(self):
        self.run_session();p=self.prep/'run/cases/A/condition.json';v=read(p);v['hdrSha256']='0'*64;atomic(p,v)
        with self.assertRaisesRegex(ValueError,'FRAME_HASH'):validate_case(self.prep,self.prep/'run',self.plan['cases'][0])
        with self.assertRaisesRegex(ValueError,'CONDITION_MISMATCH'):self.run_session()
    def test_guarded_driver_contract_synthetic_transport(self):
        """Execute real orchestrator with explicitly mocked transport, NOT cloud."""
        import importlib.util,time,shutil
        repo=Path(__file__).resolve().parents[2]
        spec=importlib.util.spec_from_file_location('joint_driver_test',repo/'scripts/run_joint.py')
        driver=importlib.util.module_from_spec(spec);spec.loader.exec_module(driver)
        self.run_session();shutil.copyfile(self.prep/'timing.jsonl',self.prep/'run/forward-timing.jsonl')
        package=self.prep/'package';packet=package/'packet';packet.mkdir(parents=True)
        atomic(packet/'joint.json',self.plan)
        for name in ('cloud/install_bundle.py','project/runtime/joint_launch.py','project/runtime/joint_inspect.py','project/runtime/joint_results.py'):
            dst=packet/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(repo/name,dst)
        data=b'EXPLICIT_OFFLINE_SYNTHETIC_ARCHIVE';(package/'inference-code.tar.gz').write_bytes(data)
        digest=hashlib.sha256(data).hexdigest();atomic(package/'bundle.json',{'sha256':digest,'archive':'inference-code.tar.gz'})
        guard=self.prep/('c'*32);guard.mkdir();operations=[];exported={}
        def transport(argv,**kw):
            op=argv[argv.index('-Operation')+1];operations.append(op)
            part=argv[argv.index('-ControlPart')+1] if '-ControlPart' in argv else None
            out=None
            if op=='install_bundle':out={'preparation':'/home/jovyan/prepared/preview-'+guard.name}
            if op=='launch':out={'workerPid':123,'OFFLINE_SYNTHETIC':True}
            if op=='inspect':out={'taskId':self.plan['taskId'],'nonce':self.plan['nonce'],'status':'succeeded','executionStopped':True,'completed':list('ABCDEF')}
            if op=='export_control_chunk':
                exported[part]=payload(self.prep/'run',part);out={'sha256':hashlib.sha256(exported[part]).hexdigest(),'bytes':len(exported[part])}
            if op=='download_control_chunk':(guard/('control-canonical-'+guard.name+'-'+part+'.tar.gz')).write_bytes(exported[part])
            if out is not None:atomic(guard/(op+'-result.json'),{'output':json.dumps(out)})
            return types.SimpleNamespace(returncode=0)
        config={'jointPackageSha256':digest,'jointTaskId':self.plan['taskId']}
        settings={'container_data_dir':'/home/jovyan/prepared','container_repo':'REPO','container_checkpoint_dir':'CKPT','cuda_home':'CUDA'}
        timing={'work_deadline_utc':'2099-01-01T00:00:00Z'}
        with patch.object(driver,'verify_joint',return_value=self.plan),patch.object(driver,'authorization',return_value=(guard,config,settings,timing,time.time()+60)),patch.object(driver.subprocess,'run',side_effect=transport),patch.object(driver,'shutdown') as stop:
            driver.execute(package,self.prep/'SYNTHETIC_CONFIG.json');stop.assert_called_once()
        self.assertEqual(operations.count('launch'),1);self.assertEqual(operations.count('download_control_chunk'),7)
        summary=read(package/'execution/summary.json');self.assertEqual(summary['observedCounts']['forwardCount'],6)
        self.assertEqual(summary['visual'],'pending')

if __name__=='__main__':unittest.main()
