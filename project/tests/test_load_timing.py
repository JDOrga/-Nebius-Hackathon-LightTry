"""Cold-load telemetry only: hermetic fixtures, no torch/CUDA/cloud imports."""
import ast
import builtins
import json
import os
from pathlib import Path
import sys
import tempfile
from types import ModuleType,SimpleNamespace
import unittest
from unittest.mock import Mock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import resident_model as m


class LoadTimingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.calls=[]
        self.utils=ModuleType('cosmos_predict1.diffusion.inference.inference_utils')
        self.model_module=ModuleType('cosmos_predict1.diffusion.model.model_diffusion_renderer')
        self.vae=ModuleType('cosmos_predict1.diffusion.module.pretrained_vae')
        self.jit=ModuleType('cosmos_predict1.tokenizer.inference.utils')
        self.torch=SimpleNamespace(load=Mock(return_value={'weights':'FIXTURE'}),
            jit=SimpleNamespace(load=Mock(return_value='JIT_FIXTURE')),
            cuda=SimpleNamespace(synchronize=Mock()))
        self.utils.torch=self.vae.torch=self.jit.torch=self.torch
        self.utils.non_strict_load_model=Mock(return_value='MATCH_FIXTURE')
        calls=self.calls;utils=self.utils;vae=self.vae;jit=self.jit
        class BaseModel:
            def cuda(self):calls.append('cuda');return self
        class Model(BaseModel):
            def set_up_model(self):calls.append('setup')
            def set_up_tokenizer(self):
                vae.torch.load('SECRET_TOKENIZER_PATH',weights_only=False)
                jit.torch.jit.load('SECRET_JIT_PATH',map_location='cuda')
        class BasePipeline:
            def _load_network(self):
                self.model.set_up_model()
                try:state=utils.torch.load('SECRET_MODEL_PATH',map_location='cpu',weights_only=True)
                except ValueError:state=utils.torch.load('SECRET_MODEL_PATH',map_location='cpu',weights_only=False)
                assert utils.non_strict_load_model(self.model,state)=='MATCH_FIXTURE'
                assert self.model.cuda() is self.model
            def _load_tokenizer(self):self.model.set_up_tokenizer();self.model.cuda()
        class Pipeline(BasePipeline):
            loads=0
            def __init__(self,**kwargs):
                type(self).loads+=1;self._load_model();self._load_network();self._load_tokenizer()
            def _load_model(self):self.model=Model()
        self.Model=Model;self.Pipeline=Pipeline;self.model_module.DiffusionRendererModel=Model
        fields=['checkpoint_dir','diffusion_transformer_dir','offload_diffusion_transformer',
            'offload_tokenizer','offload_text_encoder_model','offload_guardrail_models',
            'guidance','num_steps','height','width','fps','num_video_frames','seed']
        self.entry=SimpleNamespace(DiffusionRendererPipeline=Pipeline,torch=self.torch,
            parse_arguments=Mock(return_value=SimpleNamespace(**dict.fromkeys(fields,0))))
        command=ModuleType('run_experiment');command.commands=lambda args:[['python','-B','entry']]*2
        modules={x.__name__:x for x in (self.utils,self.model_module,self.vae,self.jit,command)}
        self.addCleanup(patch.stopall)
        patch.dict(sys.modules,modules).start()
        patch.dict(os.environ,{},clear=False).start()
        self.chdir=patch.object(m.os,'chdir').start()
        self.importer=patch.object(m.importlib,'import_module',return_value=self.entry).start()
        self.verify=patch.object(m,'verify_runtime').start()
        self.process=patch.object(m.subprocess,'run').start()
        prior=sys.path[:];self.addCleanup(lambda:sys.path.__setitem__(slice(None),prior))

    def preload(self,phase='inverse'):
        cache,module=m.preload({'cudaHome':'CUDA_FIXTURE','repo':'REPO_FIXTURE',
            'checkpointDir':'SECRET_WEIGHT_DIRECTORY'},phase,self.root,10**12)
        self.addCleanup(cache.close)
        return cache,module

    def events(self):return [json.loads(line) for line in (self.root/'loading-timing.jsonl').read_text().splitlines()]

    def test_spans_nested_exactly_once_arguments_and_result_preserved(self):
        cache,module=self.preload()
        self.assertIs(module,self.entry);self.assertEqual(self.Pipeline.loads,1)
        self.torch.load.assert_has_calls([unittest.mock.call('SECRET_MODEL_PATH',map_location='cpu',weights_only=True),
            unittest.mock.call('SECRET_TOKENIZER_PATH',weights_only=False)])
        self.assertEqual(self.torch.load.call_count,2)
        self.torch.jit.load.assert_called_once_with('SECRET_JIT_PATH',map_location='cuda')
        self.torch.cuda.synchronize.assert_called_once_with()
        self.verify.assert_not_called();self.process.assert_not_called()
        self.assertEqual(self.calls,['setup','cuda','cuda'])
        events=self.events();finished=[e for e in events if e['event']=='finished']
        stages=[e['stage'] for e in finished]
        for stage in ('preload_total','environment_setup','module_import','argument_setup','pipeline_init',
            'model_config','network_load','network_setup','checkpoint_read','parameter_apply','tokenizer_load',
            'tokenizer_setup','cuda_synchronize'):
            self.assertEqual(stages.count(stage),1,stage)
        self.assertEqual(stages.count('device_move'),2)
        self.assertEqual(stages.count('tokenizer_checkpoint_read'),2)
        starts={e['spanId']:e for e in events if e['event']=='started'}
        for e in finished:
            self.assertIn(e['spanId'],starts);self.assertGreaterEqual(e['elapsedMs'],0)
            if e['parentSpanId'] is not None:self.assertIn(e['parentSpanId'],starts)
        self.assertEqual(stages[-1],'preload_total')
        self.assertNotIn('SECRET_',json.dumps(events));self.assertNotIn('FIXTURE',json.dumps(events))
        self.assertTrue(all(e['phase']=='inverse' for e in events))
        # Restore inherited methods as inherited, and torch aliases by identity.
        for name in ('_load_network','_load_tokenizer'):self.assertNotIn(name,vars(self.Pipeline))
        self.assertNotIn('cuda',vars(self.Model))
        for module in (self.utils,self.vae,self.jit):self.assertIs(module.torch,self.torch)
        self.assertFalse(hasattr(self.torch.load,'__wrapped__'))

    def test_forward_and_fallback_attempts_are_truthfully_separate(self):
        self.torch.load.side_effect=[ValueError('SECRET_EXCEPTION'),{'weights':'FIXTURE'},{}]
        self.preload('forward');events=self.events()
        read=[e for e in events if e['stage']=='checkpoint_read' and e['event']!='started']
        self.assertEqual([e['event'] for e in read],['failed','finished'])
        self.assertEqual(self.torch.load.call_args_list[1].kwargs['weights_only'],False)
        self.assertTrue(all(e['phase']=='forward' for e in events))
        self.assertNotIn('SECRET_EXCEPTION',json.dumps(events))

    def test_constructor_failure_preserves_exception_and_restores_hooks(self):
        error=RuntimeError('SECRET_CREDENTIAL_ERROR')
        self.torch.load.side_effect=error;old=self.utils.non_strict_load_model
        with self.assertRaises(RuntimeError) as found:self.preload()
        self.assertIs(found.exception,error);self.assertIs(self.utils.non_strict_load_model,old)
        self.assertIs(self.utils.torch,self.torch);self.assertNotIn('cuda',vars(self.Model))
        events=self.events();self.assertEqual(events[-1]['event'],'failed')
        self.assertEqual(events[-1]['stage'],'preload_total')
        self.assertFalse(any(e['stage']=='cuda_synchronize' for e in events))
        self.assertNotIn('SECRET_CREDENTIAL_ERROR',json.dumps(events))

    def test_sync_failure_closes_cache_and_cannot_record_success(self):
        self.torch.cuda.synchronize.side_effect=RuntimeError('CUDA_FIXTURE_FAIL')
        original=self.Pipeline.__init__
        with self.assertRaises(RuntimeError):self.preload()
        self.assertIs(self.Pipeline.__init__,original)
        self.assertEqual(self.events()[-1]['event'],'failed')
        self.torch.cuda.synchronize.assert_called_once()

    def test_expired_before_load_does_not_import_or_create_timing(self):
        with self.assertRaises(TimeoutError):m.preload({},'inverse',self.root,0)
        self.importer.assert_not_called();self.assertFalse((self.root/'loading-timing.jsonl').exists())

    def test_expiry_after_loading_still_fails_and_cleans_up(self):
        original=self.Pipeline.__init__
        with patch.object(m.time,'time',side_effect=[0,20]):
            with self.assertRaises(TimeoutError):
                m.preload({'cudaHome':'CUDA','repo':'REPO','checkpointDir':'WEIGHTS'},'inverse',self.root,10)
        self.assertIs(self.Pipeline.__init__,original)
        self.assertEqual(self.events()[-1]['event'],'failed')
        self.torch.cuda.synchronize.assert_called_once()

    def test_existing_file_is_not_overwritten_and_load_still_runs_once(self):
        path=self.root/'loading-timing.jsonl';path.write_text('PRISTINE_FIXTURE')
        self.preload();self.assertEqual(path.read_text(),'PRISTINE_FIXTURE')
        self.assertEqual(self.Pipeline.loads,1)

    def test_open_and_write_errors_do_not_mask_model_outcome(self):
        with patch.object(m.os,'open',side_effect=PermissionError('SECRET')):self.preload()
        timing=m.LoadTiming(self.root,'inverse');timing.close()
        sink=Mock();sink.write.side_effect=OSError('DISK_FULL');timing.stream=sink
        with timing.span('fixture'):pass
        self.assertIsNone(timing.stream);sink.close.assert_called_once()

    def test_unwritable_timing_still_propagates_original_model_error(self):
        error=RuntimeError('SECRET_MODEL_FAILURE');self.torch.load.side_effect=error
        with patch.object(m.os,'open',side_effect=PermissionError('SECRET_IO')):
            with self.assertRaises(RuntimeError) as found:self.preload()
        self.assertIs(found.exception,error);self.assertIs(self.utils.torch,self.torch)
        self.assertEqual(self.Pipeline.loads,1)

    def test_byte_limit_and_private_creation(self):
        timing=m.LoadTiming(self.root,'inverse')
        try:
            timing.emit(dict(stage='X'*65536,event='started'))
            self.assertEqual(timing.events,0)
            timing.emit(dict(stage='fixture',event='started'))
        finally:timing.close()
        self.assertEqual(len(self.events()),1)
        if os.name=='posix':self.assertEqual((self.root/'loading-timing.jsonl').stat().st_mode&0o777,0o600)

    def test_nested_metrics_monotonic_not_wall_clock_and_bounded(self):
        ticks=iter([0,1,3,5]);cpu=iter([0,1,2,3]);io=iter([
            {'read_bytes':0,'rchar':0},{'read_bytes':10,'rchar':15},
            {'read_bytes':40,'rchar':55},{'read_bytes':80,'rchar':100}])
        timing=m.LoadTiming(self.root,'forward',clock=lambda:next(ticks),cpu=lambda:next(cpu),
            wall=lambda:-100,io=lambda:next(io))
        try:
            with timing.span('outer'):
                with timing.span('inner'):pass
            for unused in range(200):timing.emit(dict(stage='fixture',event='started'))
        finally:timing.close()
        events=self.events();inner,outer=[e for e in events if e['event']=='finished']
        self.assertEqual(inner['elapsedMs'],2000);self.assertEqual(outer['elapsedMs'],5000)
        self.assertEqual(inner['ioReadBytes'],30);self.assertEqual(outer['ioReadBytes'],80)
        self.assertEqual(len(events),128);self.assertLessEqual((self.root/'loading-timing.jsonl').stat().st_size,65536)

    def test_io_unavailable_recorded_as_null(self):
        with patch.object(builtins,'open',side_effect=OSError('NO_PROC')):self.assertIsNone(m.process_io())
        timing=m.LoadTiming(self.root,'inverse',io=lambda:None)
        try:
            with timing.span('fixture'):pass
        finally:timing.close()
        self.assertIsNone(self.events()[-1]['ioReadBytes'])

    def test_parse_failure_restores_sys_argv_and_records_failure(self):
        original=sys.argv
        self.entry.parse_arguments.side_effect=ValueError('SECRET_ARGUMENTS')
        with self.assertRaises(ValueError):self.preload()
        self.assertIs(sys.argv,original);self.assertEqual(self.events()[-1]['event'],'failed')
        self.assertEqual(self.Pipeline.loads,0)

    def test_pinned_loader_call_sites_exist_without_importing_upstream(self):
        root=Path(__file__).resolve().parents[2]/'upstream/cosmos_predict1'
        utils=ast.parse((root/'diffusion/inference/inference_utils.py').read_text())
        functions={n.name:n for n in utils.body if isinstance(n,ast.FunctionDef)}
        network=ast.unparse(functions['load_network_model'])
        self.assertIn('torch.load(',network);self.assertIn('non_strict_load_model(',network)
        self.assertNotIn('mmap=',network);self.assertIn('skip_init_linear()',network)
        vae=(root/'diffusion/module/pretrained_vae.py').read_text()
        self.assertIn('self.encoder = torch.load(',vae)
        self.assertIn('self.decoder = torch.load(',vae)


if __name__=='__main__':unittest.main()
