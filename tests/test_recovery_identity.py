"""Input mutations and recovery configuration cannot silently change provenance."""
import argparse
import copy
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_experiment as worker


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        data = root / 'inputs'
        data.mkdir()
        (data / 'frame.jpg').write_bytes(b'synthetic dataset')
        source = root / 'contact-source.png'
        source.write_bytes(b'synthetic contact source')
        self.args = argparse.Namespace(input_dir=data, input_image=source,
                                       checkpoint_dir=root / 'weights', cuda_home=root / 'cuda', offload=False)
        self.prior = self.plan()

    def plan(self):
        return dict(height=704, width=1280, steps=15, seed=1000, repo='synthetic-repo',
                    python='synthetic-python', recovery=worker.recovery_identity(self.args, None))

    def test_unchanged_inputs_can_resume(self):
        worker.validate_recovery(self.prior, self.plan())

    def test_contact_image_replaced_at_same_path_is_rejected(self):
        self.args.input_image.write_bytes(b'changed contact source')
        with self.assertRaisesRegex(ValueError, 'inputs or settings differ'):
            worker.validate_recovery(self.prior, self.plan())

    def test_changed_or_added_dataset_file_is_rejected(self):
        for name in ('frame.jpg', 'extra.jpg'):
            with self.subTest(name=name):
                path = self.args.input_dir / name
                path.write_bytes(b'changed dataset')
                with self.assertRaises(ValueError):
                    worker.validate_recovery(self.prior, self.plan())
                if name == 'frame.jpg':
                    path.write_bytes(b'synthetic dataset')

    def test_offload_or_checkpoint_path_changes_are_rejected(self):
        self.args.offload = True
        with self.assertRaises(ValueError):
            worker.validate_recovery(self.prior, self.plan())
        self.args.offload = False
        self.args.checkpoint_dir = self.args.checkpoint_dir / 'other'
        with self.assertRaises(ValueError):
            worker.validate_recovery(self.prior, self.plan())

    def test_old_plan_requires_new_inverse_run(self):
        prior = copy.deepcopy(self.prior)
        del prior['recovery']
        with self.assertRaisesRegex(ValueError, 'start a new inverse run'):
            worker.validate_recovery(prior, self.plan())


if __name__ == '__main__':
    unittest.main()
