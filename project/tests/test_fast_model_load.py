from pathlib import Path
import importlib.util,json,sys,tempfile,types,os
from unittest.mock import patch,Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import resident_model as m
fields=['checkpoint_dir','diffusion_transformer_dir','offload_diffusion_transformer','offload_tokenizer','offload_text_encoder_model','offload_guardrail_models','guidance','num_steps','height','width','fps','num_video_frames','seed']
parsed=types.SimpleNamespace(**{k:0 for k in fields});seen=[]
fake=types.SimpleNamespace(parse_arguments=lambda:parsed,DiffusionRendererPipeline=object,torch=types.SimpleNamespace(cuda=types.SimpleNamespace(synchronize=lambda:None)))
command=types.ModuleType('run_experiment');command.commands=lambda a:[['python','-B','entry'],['python','-B','entry']]
NativePath=type(Path());fixture=Path('.')
with patch.object(m,'Path',NativePath),patch.dict(sys.modules,{'run_experiment':command}),patch.dict(os.environ,{},clear=False),patch.object(m.sys,'version_info',(3,10)),patch.object(m.os,'name','posix'),patch.object(m.os,'chdir'),patch.object(m,'verify_runtime') as verify,patch.object(m.subprocess,'run') as process,patch.object(m.importlib,'import_module',side_effect=lambda name:(seen.append(os.environ.get('CUDA_HOME')),fake)[1]),patch.object(m,'PipelineCache',return_value='LOADED'):
 for phase in ['inverse','forward']:assert m.preload({'python':'FIXTURE','repo':'FIXTURE','checkpointDir':'FIXTURE','cudaHome':'CUDA_FIXTURE'},phase,fixture,10**12)[0]=='LOADED'
 assert str(m.ROOT/'scripts') in m.sys.path
 assert verify.call_count==0
 assert process.call_count==0
 assert seen==['CUDA_FIXTURE','CUDA_FIXTURE']


import ast,unittest
class FastLoadTests(unittest.TestCase):
 def test_production_generation_skips_setup_scans(self):
  source=(Path(__file__).resolve().parents[1]/'inference/worker.py').read_text()
  tree=ast.parse(source)
  branch=next(n for n in ast.walk(tree) if isinstance(n,ast.If) and ast.unparse(n.test)=='resident')
  fast='\n'.join(ast.unparse(n) for n in branch.body)
  self.assertIn("'resident_loaded'",fast)
  for operation in ['verify(', 'run_bounded(', 'read_bytes(', 'subprocess.run(', 'reuse_existing(']:self.assertNotIn(operation,fast)
 def test_startup_has_no_runtime_preflight(self):
  tree=ast.parse(Path(m.__file__).read_text());f=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='preload')
  source=ast.unparse(f)
  for operation in ['verify_runtime(', 'subprocess.run(', 'sha256(', 'version_info']:self.assertNotIn(operation,source)
  self.assertLess(source.index('os.environ.update'),source.index('importlib.import_module'))
if __name__=='__main__':unittest.main()
