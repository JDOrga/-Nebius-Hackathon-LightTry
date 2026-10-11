import io,json,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'project'))
from next.runtime import entry
from inference.jobs import atomic,read
from inference.timing import Timeline
from inference.batch import validate_forward_result
from lighting import normalize_parameters
class SchemeEntryTests(unittest.TestCase):
 def test_actual_model_entry_matches_each_approved_hdr_condition_cpu_synthetic(self):
  import torch
  from PIL import Image
  torch.set_num_threads(2)
  envs={v['id']:v for v in read(ROOT/'project/next/runtime/environments.json')};policy=read(ROOT/'project/next/runtime/policy.json')
  for offset,strength in [(0,1),(0,.7),(45,1)]:
   with self.subTest(offset=offset,strength=strength),tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp);state=root/'presets';state.mkdir();raw={'environmentId':'sunny','offsetDeg':offset,'strength':strength};atomic(state/'identities.json',{'0':{'hdr':{'scheme':{'parameters':raw},'parameters':normalize_parameters(raw,envs,policy)}}})
    calls=[];initializations=[]
    class Pipeline:
     def __init__(self,**kw):initializations.append(1)
     def generate_video(self,*,data_batch):return data_batch['env_ldr']
    def helper(hdr_dir, resolution=(704,1280),num_frames=1,fixed_pose=True,rotate_envlight=False,env_format=['proj'],device='cpu',env_rot=180,env_strength=1,env_flip=True,log_scale=10000):
     calls.append((env_rot,env_strength,env_flip,rotate_envlight));v=torch.full((1,704,1280,3),env_strength*env_rot/360);return {'env_ldr':v,'env_log':v/2,'metadata':{'envmap_rot':env_rot,'envmap_strength':env_strength,'envmap_flip':env_flip,'rotate_envlight':rotate_envlight,'synthetic':True}}
    module=SimpleNamespace(DiffusionRendererPipeline=Pipeline,process_environment_map=helper)
    def demo(args):
     p=module.DiffusionRendererPipeline();c=module.process_environment_map('SYNTHETIC_HDR');batch={k:c[k].unsqueeze(0).permute(0,4,1,2,3)*2-1 for k in ('env_ldr','env_log')};batch['env_nrm']=torch.zeros_like(batch['env_ldr']);p.generate_video(data_batch=batch);f=Path(args.video_save_folder)/'relit_frames_0000/photo/0000.0000.jpg';f.parent.mkdir(parents=True);im=Image.new('RGB',(1280,704),(120,100,80));im.paste((170,160,150),(50,50,400,400));im.save(f)
    module.demo=demo;args=SimpleNamespace(envlight_ind=[0],seed=1000);entry.run_forward(args,module,Timeline(root/'timing.jsonl','SYNTHETIC_ONLY'),state,validate_forward_result)
    self.assertEqual(calls,[(180+offset,strength,True,False)]);self.assertEqual(len(initializations),1);self.assertEqual(read(state/'0/model-condition.json')['env_ldr']['shape'],[1,3,1,704,1280]);self.assertEqual(module.process_environment_map,helper)
 def test_unapproved_pair_fails_before_helper(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);atomic(root/'identities.json',{'0':{'hdr':{'scheme':{'parameters':{'environmentId':'sunny','offsetDeg':45,'strength':.7}},'parameters':{}}}})
   with self.assertRaises(ValueError):entry.run_forward(SimpleNamespace(envlight_ind=[0]),SimpleNamespace(),None,root,None)
if __name__=='__main__':unittest.main()
