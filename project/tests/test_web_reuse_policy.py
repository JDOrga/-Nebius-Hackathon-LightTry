"""Offline operator policy checks; no cloud or model execution."""
import copy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
from inference.executor import GuardedCosmosExecutor
from inference.jobs import TaskStore, atomic, read, JobError
from inference_fixture import OfflineExecutor, image_bytes

PRESETS = read(ROOT / 'data/catalog.json')['presets']

class PolicyTests(unittest.TestCase):
    def test_policy_failure_never_dispatches_or_persists_executable_request(self):
        class Executor(OfflineExecutor):
            def prepare_request(self, folder, request):
                raise ValueError('REQUIRED_INVERSE_REUSE_UNAVAILABLE_NO_COLD_FALLBACK')
        with tempfile.TemporaryDirectory() as temp:
            executor = Executor()
            store = TaskStore(Path(temp), PRESETS, executor)
            with self.assertRaises(JobError) as error:
                store.submit(image_bytes(), {'inputId':'a'*32, 'requestId':'b'*32,
                    'presetIds':['sunny','sunrise']}, 'image/png')
            self.assertEqual(error.exception.code, 'REQUIRED_REUSE_INVALID')
            self.assertEqual(list(Path(temp).rglob('request.json')), [])
            self.assertEqual(list(Path(temp).rglob('execution.json')), [])
            store.close()

    def test_request_binds_exact_source_and_rejects_other_presets(self):
        requirement = {'key':'c'*64, 'source':{'taskId':'d'*32}}
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp); (folder/'inputs').mkdir()
            (folder/'inputs/photo.png').write_bytes(b'local policy test')
            config = folder/'config.json'
            atomic(config, {'required_inverse_reuse':requirement,
                            'required_preset_ids':['sunny','sunrise']})
            executor = object.__new__(GuardedCosmosExecutor); executor.config_path=config
            request = {'presets':copy.deepcopy(PRESETS[:2])}
            with patch('inference.reuse.identity', return_value={}), \
                 patch('inference.reuse.key', return_value=requirement['key']), \
                 patch('inference.reuse.validate', return_value={'source':requirement['source']}):
                executor.prepare_request(folder, request)
                self.assertEqual(request['requiredInverseReuse'], requirement)
                request['presets'] = [PRESETS[2]]
                with self.assertRaisesRegex(ValueError,'AUTHORIZED_BATCH_PRESETS_REQUIRED'):
                    executor.prepare_request(folder,request)

if __name__ == '__main__': unittest.main()
