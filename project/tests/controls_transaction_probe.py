"""Explicit CPU SYNTHETIC orchestration probe. Never evidence of neural control."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'project'))
from inference.jobs import atomic
from inference.timing import Timeline
from experiments.controls import VERSION, CASES


def main():
    p = argparse.ArgumentParser(); p.add_argument('source', type=Path); a = p.parse_args()
    import torch
    from PIL import Image
    torch.set_num_threads(2)
    spec = importlib.util.spec_from_file_location('transaction_source', a.source)
    source = importlib.util.module_from_spec(spec); spec.loader.exec_module(source)
    count = 0
    class Pipeline:
        def __init__(self, **kw):
            nonlocal count; count += 1
        def generate_video(self, *, data_batch, seed):
            return data_batch['env_ldr']
    def helper(hdr_dir, resolution=(704, 1280), num_frames=1, fixed_pose=True,
               rotate_envlight=False, env_format=['proj'], device='cpu',
               env_rot=180.0, env_strength=1.0, env_flip=True, log_scale=10000):
        value = torch.full((1, 704, 1280, 3), env_strength * (env_rot / 360))
        return {'env_ldr': value, 'env_log': value / 2, 'metadata': {'synthetic': True}}
    module = SimpleNamespace(DiffusionRendererPipeline=Pipeline, process_environment_map=helper)
    def demo(args):
        pipeline = module.DiffusionRendererPipeline()
        conditions = module.process_environment_map('SYNTHETIC_HDR', resolution=(704, 1280),
            num_frames=1, fixed_pose=True, rotate_envlight=False, env_format=['proj'], device='cpu')
        batch = {name: conditions[name].unsqueeze(0).permute(0, 4, 1, 2, 3) * 2 - 1
                 for name in ('env_ldr', 'env_log')}
        batch['env_nrm'] = torch.zeros_like(batch['env_ldr'])
        pipeline.generate_video(data_batch=batch, seed=1000)
        path = Path(args.video_save_folder) / 'relit_frames_0000/photo/0000.0000.jpg'
        path.parent.mkdir(parents=True)
        image = Image.new('RGB', (1280, 704), (120, 100, 80))
        image.paste((180, 160, 100), (100, 100, 400, 400)); image.save(path)
    module.demo = demo
    from inference.batch import validate_forward_result
    with tempfile.TemporaryDirectory(dir=ROOT / '.local/lighttry-development-20261011') as temporary:
        prep = Path(temporary); states = prep / 'run/presets'; states.mkdir(parents=True)
        atomic(states / 'identities.json', {'0': {'fixture': 'SYNTHETIC_ONLY_NOT_GPU'}})
        atomic(prep / 'experiment.json', {'version': VERSION, 'cases': list(CASES)})
        args = SimpleNamespace(envlight_ind=[0], seed=1000, num_steps=15,
            height=704, width=1280, num_video_frames=1, rotate_light=False)
        timeline = Timeline(prep / 'run/timing.jsonl', 'synthetic')
        source.run_forward(args, module, timeline, states, validate_forward_result)
        completions = list((prep / 'run').rglob('complete.json'))
        print(json.dumps({'scope': 'SYNTHETIC_ONLY_NOT_GPU', 'completedCases': len(completions),
                          'pipelineInitializations': count, 'input': 'fixed-fixture-v1'}))


if __name__ == '__main__':
    main()
