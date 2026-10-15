"""Local simulation must complete without fabricating production model evidence."""
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from simulation import SimulationStore, SimulationExecutor
from scheme_store import SchemeStore
from inference.jobs import read, JobError


class SimulationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.presets = json.loads((ROOT / 'data/catalog.json').read_text(encoding='utf8'))['presets']
        self.store = SimulationStore(Path(temp.name) / 'tasks', self.presets, SimulationExecutor(),
            lighting_capabilities={'revision':'offline', 'parameterized':True, 'approvedVariants':{}})
        self.addCleanup(self.store.close)
        out = io.BytesIO(); Image.new('RGB', (64, 80), '#8a9b7a').save(out, 'PNG')
        self.photo = out.getvalue()
        self.meta = dict(requestId='a'*32, inputId='b'*32, name='synthetic.png', lightingScheme=dict(
            schemaVersion=1, planId='c'*32, version=1, parentVersion=None, name='模拟', inputId='b'*32,
            parameters=dict(environmentId='sunny', offsetDeg=0, strength=.7)))

    def complete(self):
        task = self.store.submit(self.photo, self.meta, 'image/png')
        folder = self.store.directory(task['taskId'])
        limit = time.monotonic() + 5
        while (not (folder / 'execution.json').exists() or
               read(folder / 'execution.json')['status'] != 'succeeded') and time.monotonic() < limit:
            time.sleep(.01)
        self.assertTrue((folder / 'receipt.json').exists())
        return folder, read(folder / 'task.json'), read(folder / 'receipt.json')

    def test_procedural_recipe_completes_through_task_polling(self):
        from light_console import initial
        params = initial(self.presets[0])
        params.update(mode='procedural', environmentId=None, environmentSha256=None)
        self.meta['lightingScheme']['parameters'] = params
        folder, task, receipt = self.complete()
        public = self.store.get(task['taskId'])
        self.assertEqual(public['status'], 'succeeded')
        self.assertTrue(public['result']['simulation'])
        self.assertEqual(public['result']['parameters'], params)

    def test_output_has_simulation_identity_and_no_gpu_evidence(self):
        folder, task, receipt = self.complete()
        result = self.store._check_result(folder, task, receipt)
        self.assertTrue(result['simulation'])
        self.assertTrue(task['runConfig']['simulation'])
        self.assertFalse(task['runConfig']['weightContentHashesChecked'])
        self.assertNotIn('processExitCodes', receipt)
        self.assertNotIn('actualModelCondition', receipt)
        with self.assertRaisesRegex(ValueError, 'RESULT_LIGHTING_IDENTITY_MISMATCH'):
            SchemeStore._check_result(self.store, folder, task, receipt)

    def test_tampered_output_and_identity_are_rejected(self):
        folder, task, receipt = self.complete()
        bad = copy.deepcopy(receipt); bad['parameters']['strength'] = 1
        with self.assertRaisesRegex(ValueError, 'RECEIPT_MISMATCH'):
            self.store._check_result(folder, task, bad)
        (folder / 'result.jpg').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'HASH_MISMATCH'):
            self.store._check_result(folder, task, receipt)

    def test_provider_provenance_cannot_be_used_in_simulation(self):
        self.meta['languageProposalId'] = 'd'*32
        with self.assertRaises(JobError):
            self.store.submit(self.photo, self.meta, 'image/png')


if __name__ == '__main__':
    unittest.main()
