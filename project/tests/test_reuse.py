"""OFFLINE SYNTHETIC orchestration and invocation counts. NOT GPU acceptance."""
import argparse
import copy
import json
import sys
import tempfile
import types
import unittest
import tarfile
from unittest.mock import patch as mock_patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
sys.path.insert(0, str(ROOT.parent / 'scripts'))
from inference_fixture import image_bytes
from inference.images import prepare, digest
from inference.jobs import atomic, read, RUN_CONFIG
from inference.reuse import identity, key, complete, validate, copy_completed, safe_file, LABELS
from inference.batch import execute, validate_forward_result, session_lock
from inference.measured_entry import run_forward
from inference.timing import Timeline
from run_experiment import commands

WEIGHTS = read(ROOT.parent / 'manifests/weights_manifest.json')
PATCH = read(ROOT.parent / 'manifests/patch_manifest.json')
PRESETS = read(ROOT / 'data/catalog.json')['presets']


class SyntheticBackend:
    """Only test code can inject this backend. No torch/SSH/API imports."""
    def __init__(self, fail=None):
        self.inverse_calls = self.processes = self.initializations = 0
        self.generated = []
        self.object_ids = []
        self.fail = fail

    def launch(self, argv, logfile):
        logfile.write_text('OFFLINE SYNTHETIC / NOT GPU', encoding='utf-8')
        phase = argv[argv.index('--phase') + 1]
        if phase == 'inverse':
            self.inverse_calls += 1
            root = Path(argv[argv.index('--video_save_folder') + 1]) / 'gbuffer_frames/photo'
            root.mkdir(parents=True)
            for label in LABELS:
                (root / ('0000.0000.' + label + '.jpg')).write_bytes(image_bytes((1280, 704), 'JPEG'))
            return
        self.processes += 1
        root = Path(argv[argv.index('--state-root') + 1])
        indices = [int(i) for i in argv[argv.index('--envlight_ind') + 1:argv.index('--use_custom_envmap=True')]]
        backend = self
        class Pipeline:
            def __init__(self, **kw):
                backend.initializations += 1
        module = types.SimpleNamespace(DiffusionRendererPipeline=Pipeline)
        def demo(args):
            model = module.DiffusionRendererPipeline(seed=args.seed)
            index = args.envlight_ind[0]
            backend.object_ids.append(id(model))
            if index == backend.fail:
                raise RuntimeError('OFFLINE SYNTHETIC FAILURE')
            backend.generated.append(index)
            out = Path(args.video_save_folder) / f'relit_frames_{index:04d}/photo'
            out.mkdir(parents=True)
            (out / '0000.0000.jpg').write_bytes(image_bytes((1280, 704), 'JPEG'))
        module.demo = demo
        run_forward(argparse.Namespace(envlight_ind=indices, seed=1000), module,
            Timeline(root.parent / 'synthetic-timing.jsonl', 'OFFLINE SYNTHETIC'), root, validate_forward_result)


class ReuseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.input = self.root / 'photo.png'
        canvas = prepare(image_bytes(), self.input)
        self.job = {'taskId': 'a' * 32, 'nonce': 'b' * 32, 'input': {'sha256': canvas['sha256'], 'canvas': canvas},
                    'preset': PRESETS[0], 'presets': PRESETS, 'runConfig': {**RUN_CONFIG, 'weightVerification': 'historical_metadata'}}
        self.run = self.root / 'run'; self.run.mkdir()
        self.argv = commands(argparse.Namespace(checkpoint_dir=self.root / 'checkpoints', input_dir=self.root,
            run_dir=self.run, width=1280, height=704, offload=False))
        self.backend = SyntheticBackend()

    def execute(self, source=None):
        return execute(self.job, self.input, self.run, WEIGHTS, PATCH, *self.argv, self.backend.launch, inverse_source=source)

    def test_one_inverse_one_real_object_multiple_demos(self):
        result = self.execute()
        self.assertEqual((self.backend.inverse_calls, self.backend.processes, self.backend.initializations), (1, 1, 1))
        self.assertEqual(self.backend.generated, [0, 1, 2])
        self.assertEqual(len(set(self.backend.object_ids)), 1)
        self.assertEqual(result['source']['taskId'], self.job['taskId'])

    def test_repeat_submission_skips_all_completed_generation(self):
        self.execute(); self.execute()
        self.assertEqual(self.backend.inverse_calls, 1)
        self.assertEqual(self.backend.initializations, 1)
        self.assertEqual(self.backend.generated, [0, 1, 2])

    def test_inverse_survives_forward_failure_and_resume_skips_completed(self):
        self.backend.fail = 1
        with self.assertRaises(RuntimeError): self.execute()
        self.assertTrue((self.run / 'inverse/inverse-complete.json').exists())
        self.assertEqual(read(self.run / 'presets/0/state.json')['status'], 'succeeded')
        self.assertEqual(read(self.run / 'presets/1/state.json')['status'], 'failed')
        self.assertEqual(read(self.run / 'presets/2/state.json')['status'], 'pending')
        saved = (self.run / 'presets/0/complete.json').read_bytes()
        self.backend.fail = None
        self.execute()
        self.assertEqual(self.backend.inverse_calls, 1)
        self.assertEqual(self.backend.generated, [0, 1, 2])
        self.assertEqual(self.backend.initializations, 2)  # next process reloads forward
        self.assertEqual(saved, (self.run / 'presets/0/complete.json').read_bytes())

    def test_inverse_success_first_forward_failure_preserves_inverse(self):
        self.backend.fail = 0
        with self.assertRaises(RuntimeError): self.execute()
        value = identity(self.job, self.input.read_bytes(), WEIGHTS, PATCH)
        validate(self.run / 'inverse', value)
        self.assertFalse((self.run / 'presets/0/complete.json').exists())

    def test_same_pixels_other_hdr_reuses_source_and_preserves_hashes(self):
        prior = self.execute()
        source = self.run / 'inverse'
        self.run = self.root / 'second'; self.run.mkdir()
        self.argv = commands(argparse.Namespace(checkpoint_dir=self.root / 'checkpoints', input_dir=self.root,
            run_dir=self.run, width=1280, height=704, offload=False))
        self.job['taskId'] = 'c' * 32
        self.job['preset'] = PRESETS[2]; self.job['presets'] = [PRESETS[2]]
        reused = self.execute(source)
        self.assertEqual(self.backend.inverse_calls, 1)
        self.assertEqual(reused, prior)
        self.assertEqual(reused['source']['taskId'], 'a' * 32)

    def test_identity_excludes_hdr_and_input_names_but_includes_dependencies(self):
        original = identity(self.job, self.input.read_bytes(), WEIGHTS, PATCH)
        self.job['preset'] = PRESETS[1]; self.job['input']['name'] = 'same-name.png'
        self.assertEqual(identity(self.job, self.input.read_bytes(), WEIGHTS, PATCH), original)
        for field, value in [('seed', 1001), ('steps', 16), ('upstreamCommit', 'different')]:
            job = copy.deepcopy(self.job); job['runConfig'][field] = value
            self.assertNotEqual(key(identity(job, self.input.read_bytes(), WEIGHTS, PATCH)), key(original))
        changed = copy.deepcopy(PATCH); changed['files'][0]['after_sha256'] = 'c' * 64
        self.assertNotEqual(identity(self.job, self.input.read_bytes(), WEIGHTS, changed), original)
        forward_only = copy.deepcopy(PATCH); forward_only['files'][1]['after_sha256'] = 'c' * 64
        self.assertEqual(identity(self.job, self.input.read_bytes(), WEIGHTS, forward_only), original)
        changed = copy.deepcopy(WEIGHTS); changed['files'][2]['sha256'] = 'c' * 64
        self.assertNotEqual(identity(self.job, self.input.read_bytes(), changed, PATCH), original)
        job = copy.deepcopy(self.job); job['input']['canvas']['validRegion'][0] += 1
        self.assertNotEqual(identity(job, self.input.read_bytes(), WEIGHTS, PATCH), original)
        job = copy.deepcopy(self.job); job['input']['canvas']['preprocessingVersion'] = 'v2'
        self.assertNotEqual(identity(job, self.input.read_bytes(), WEIGHTS, PATCH), original)

    def test_different_bytes_same_filename_not_hit(self):
        old = identity(self.job, self.input.read_bytes(), WEIGHTS, PATCH)
        canvas = prepare(image_bytes((900, 400)), self.input)
        self.job['input'] = {'sha256': canvas['sha256'], 'canvas': canvas}
        self.assertNotEqual(old, identity(self.job, self.input.read_bytes(), WEIGHTS, PATCH))

    def test_configuration_change_rejects_existing_inverse(self):
        self.execute(); self.job['runConfig']['seed'] += 1
        with self.assertRaisesRegex(ValueError, 'IDENTITY_MISMATCH'): self.execute()
        self.assertEqual(self.backend.inverse_calls, 1)

    def test_partial_running_or_unknown_cache_is_rejected(self):
        value = identity(self.job, self.input.read_bytes(), WEIGHTS, PATCH)
        source = self.run / 'inverse'
        source.mkdir()
        with self.assertRaises(ValueError): validate(source, value)
        with self.assertRaises(ValueError): self.execute(source)
        self.assertEqual(self.backend.inverse_calls, 0)

    def test_corrupt_or_missing_artifact_rejects_completed_cache(self):
        self.execute()
        marker = self.run / 'inverse/inverse-complete.json'
        record = read(marker)
        path = self.run / 'inverse/gbuffer_frames' / record['artifacts'][0]['path']
        path.write_bytes(image_bytes((1280, 704)))
        with self.assertRaises(ValueError): validate(marker.parent, record['identity'])
        path.unlink()
        with self.assertRaises(ValueError): validate(marker.parent, record['identity'])

    def test_source_unknown_or_marked_running_rejected(self):
        self.execute(); marker = self.run / 'inverse/inverse-complete.json'; record = read(marker)
        record['source']['inverseExitCode'] = None; atomic(marker, record)
        with self.assertRaisesRegex(ValueError, 'UNKNOWN'): validate(marker.parent, record['identity'])

    def test_completed_forward_corruption_not_silently_regenerated(self):
        self.execute()
        item = self.run / 'presets/0'; record = read(item / 'complete.json')
        (item / record['attempt'] / record['result']['path']).write_bytes(b'bad')
        with self.assertRaises(Exception): self.execute()
        self.assertEqual(self.backend.generated, [0, 1, 2])

    def test_paths_and_forged_forward_attempt_rejected(self):
        for path in ('../photo.png', '/photo.png', 'C:/photo.png', 'gbuffer_frames\\photo.png'):
            with self.assertRaises(ValueError): safe_file(self.root, path)
        self.execute(); item = self.run / 'presets/0'; record = read(item / 'complete.json')
        record['attempt'] = '../outside'; atomic(item / 'complete.json', record)
        with self.assertRaisesRegex(ValueError, 'UNSAFE_FORWARD_ATTEMPT'): self.execute()

    def test_duplicate_concurrent_session_rejected(self):
        with session_lock(self.run):
            with self.assertRaisesRegex(ValueError, 'ALREADY_RUNNING'): self.execute()
        self.assertEqual(self.backend.inverse_calls, 0)

    def test_monotonic_timing_failure_and_first_result_labels(self):
        ticks = iter(range(10))
        path = self.root / 'clock.jsonl'; timer = Timeline(path, 'OFFLINE', clock=lambda: next(ticks))
        with self.assertRaises(RuntimeError):
            with timer.span('generation', first=True): raise RuntimeError()
        events = [json.loads(line) for line in path.read_text().splitlines()]
        self.assertEqual(events[-1]['success'], False)
        self.assertEqual(events[-1]['first'], True)
        self.assertTrue(all(e['elapsedSeconds'] >= 0 for e in events))

    def test_failed_stage_export_preserves_inverse_and_partial_forward_without_publishing(self):
        from inference.driver import extract_stage_evidence
        self.backend.fail = 1
        with self.assertRaises(RuntimeError): self.execute()
        atomic(self.run / 'execution.json', {'taskId': self.job['taskId'], 'nonce': self.job['nonce'],
            'status': 'failed', 'executionStopped': True})
        destination = self.root / 'project/.tasks' / self.job['taskId']
        (destination / 'inputs').mkdir(parents=True)
        (destination / 'inputs/photo.png').write_bytes(self.input.read_bytes())
        manifests = self.root / 'manifests'; manifests.mkdir()
        atomic(manifests / 'weights_manifest.json', WEIGHTS); atomic(manifests / 'patch_manifest.json', PATCH)
        archive = self.root / 'stages.tar.gz'
        with tarfile.open(archive, 'w:gz') as tar:
            for file in self.run.rglob('*'):
                if file.is_file() and file.suffix in ('.json', '.jpg', '.jsonl', '.log'):
                    tar.add(file, arcname=file.relative_to(self.run).as_posix())
        with mock_patch('inference.driver.ROOT', self.root):
            record = extract_stage_evidence(archive, destination, self.job)
        self.assertFalse((destination / 'result.jpg').exists())
        self.assertTrue((destination / 'remote-evidence/presets/0/complete.json').exists())
        self.assertEqual(read(destination / 'remote-evidence/presets/2/state.json')['status'], 'pending')
        self.assertEqual(record, validate(self.root / 'project/.inverse-cache' / record['key'], record['identity']))

    def test_reused_receipt_requires_valid_source_and_no_fictional_inverse_exit(self):
        from inference.jobs import TaskStore
        from inference_fixture import OfflineExecutor
        backend = OfflineExecutor()
        store = TaskStore(self.root / 'tasks', PRESETS, backend)
        self.addCleanup(store.close)
        meta = {'inputId': 'd' * 32, 'requestId': 'e' * 32, 'presetId': 'sunny'}
        task = store.submit(image_bytes(), meta, 'image/png')
        folder, request = backend.calls[-1]
        receipt = backend.succeed()
        value = identity(request, (folder / 'inputs/photo.png').read_bytes(), WEIGHTS, PATCH)
        inverse = folder / 'remote-evidence/inverse'
        frames = inverse / 'gbuffer_frames/photo'; frames.mkdir(parents=True)
        for label in LABELS:
            (frames / ('0000.0000.' + label + '.jpg')).write_bytes(image_bytes((1280, 704), 'JPEG'))
        provenance = complete(inverse, value, {'taskId': 'f' * 32, 'nonce': 'b' * 32, 'inverseExitCode': 0})
        receipt['processExitCodes'] = [None, 0]
        receipt['inverseReuse'] = {'reused': True, 'source': provenance['source'], 'key': provenance['key']}
        atomic(folder / 'receipt.json', receipt)
        result = store.get(task['taskId'])
        self.assertEqual(result['status'], 'succeeded')
        self.assertEqual(result['result']['inverseReuse']['sourceTaskId'], 'f' * 32)
        receipt['inverseReuse']['source']['taskId'] = '0' * 32
        atomic(folder / 'receipt.json', receipt)
        self.assertEqual(store.get(task['taskId'])['status'], 'failed')

    def test_historical_import_is_idempotent_and_preserves_old_files(self):
        from prepare_inverse_reuse import import_task
        task_id, run_id = '6d541112fa164c099d9fc06c560b464d', 'dc011af5186c492d8ffd2f6342e5c07f'
        folder = ROOT / '.tasks' / task_id
        if not folder.exists(): self.skipTest('local historical evidence not present')
        paths = [folder / 'request.json', folder / 'receipt.json', folder / 'result.jpg',
                 ROOT.parent / 'manifests/weights_manifest.json', folder / 'remote-evidence/configuration.json']
        before = [digest(p.read_bytes()) for p in paths]
        first = import_task(task_id, run_id); second = import_task(task_id, run_id)
        self.assertEqual(first, second)
        self.assertEqual(before, [digest(p.read_bytes()) for p in paths])

    def test_production_generation_hook_resets_forward_rng_but_keeps_inverse_sequence(self):
        import random
        from inference.measured_entry import observe_generation
        seeds = []
        def reset(seed): seeds.append(seed); random.seed(seed)
        module = types.SimpleNamespace(misc=types.SimpleNamespace(set_random_seed=reset))
        class Pipeline:
            def generate_video(self, **kwargs): return random.random()
        timer = Timeline(self.root / 'rng.jsonl', 'OFFLINE SYNTHETIC')
        original = observe_generation(Pipeline, module, argparse.Namespace(seed=1000), 'forward', timer)
        model = Pipeline()
        a = model.generate_video(seed=1000); random.random(); b = model.generate_video(seed=1000)
        self.assertEqual(a, b); self.assertEqual(seeds, [1000, 1000])
        Pipeline.generate_video = original; seeds.clear()
        original = observe_generation(Pipeline, module, argparse.Namespace(seed=1000), 'inverse', timer)
        random.seed(1000)
        self.assertNotEqual(model.generate_video(), model.generate_video())
        self.assertEqual(seeds, [])
        Pipeline.generate_video = original

    def test_parent_spawn_boundaries_observe_actual_offline_child(self):
        import time
        from run_experiment import run_bounded
        timer = Timeline(self.root / 'spawn.jsonl', 'OFFLINE SYNTHETIC PARENT')
        run_bounded([sys.executable, '-c', 'print("OFFLINE SYNTHETIC, NO GPU")'], self.root,
            self.root / 'child.log', None, time.time() + 30, timing=timer)
        events = [json.loads(line) for line in (self.root / 'spawn.jsonl').read_text().splitlines()]
        self.assertEqual([e['event'] for e in events],
                         ['session_start', 'process_spawn_start', 'process_spawn_return', 'process_exit'])
        self.assertEqual(events[-1]['exitCode'], 0)

    def test_required_reuse_missing_never_falls_back_to_inverse(self):
        value = identity(self.job,self.input.read_bytes(),WEIGHTS,PATCH)
        self.job['requiredInverseReuse'] = {'key':key(value),'source':{'taskId':'f'*32,'nonce':'e'*32,'inverseExitCode':0}}
        with self.assertRaisesRegex(ValueError,'NO_COLD_FALLBACK'): self.execute()
        self.assertEqual((self.backend.inverse_calls,self.backend.initializations),(0,0))

    def test_required_reuse_rejects_wrong_source_before_forward(self):
        record = self.execute()
        self.job['requiredInverseReuse'] = {'key':record['key'],'source':{**record['source'],'taskId':'f'*32}}
        with self.assertRaisesRegex(ValueError,'SOURCE_MISMATCH'): self.execute()
        self.assertEqual(self.backend.inverse_calls,1)
        self.assertEqual(self.backend.initializations,1)

    def test_actual_model_object_and_random_reset_events_are_observable(self):
        self.execute()
        rows=[json.loads(line) for line in (self.run/'synthetic-timing.jsonl').read_text().splitlines()]
        ready=[e for e in rows if e['event']=='pipeline_ready']
        reused=[e for e in rows if e['event']=='pipeline_reused']
        complete=[e for e in rows if e['event']=='preset_complete']
        self.assertEqual(len(ready),1);self.assertEqual(len(reused),2);self.assertEqual(len(complete),3)
        self.assertEqual(len({e['modelObjectId'] for e in ready+reused+complete}),1)


if __name__ == '__main__': unittest.main()
