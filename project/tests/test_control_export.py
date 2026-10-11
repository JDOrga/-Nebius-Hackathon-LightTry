"""Recovery transport preparation: no network and no fake GPU claims."""
import io
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'project'))
from experiments.export_chunk import payload


class ExportTests(unittest.TestCase):
    def test_chunk_keeps_proof_skips_heavy_png_and_tensor(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, data in [('execution.json', b'{"status":"succeeded"}'),
                ('controls/baseline/condition.json', b'{}'),
                ('controls/baseline/0/a/relit_frames_0000/photo.jpg', b'SYNTHETIC_JPEG_NOT_GPU'),
                ('controls/baseline/0/a/photo.relit_0000.jpg', b'DUPLICATE_FLAT_NOT_NEEDED'),
                ('controls/baseline/env_ldr.png', b'HEAVY_BITMAP'),
                ('controls/baseline/condition-arrays.npz', b'TENSOR')]:
                p = root / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(data)
            data = payload(root, 'pair0')
            with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as tar:
                self.assertEqual(set(tar.getnames()), {'controls/baseline/condition.json',
                    'controls/baseline/0/a/relit_frames_0000/photo.jpg'})
            self.assertLess(len(data), 160*1024)
            with self.assertRaises(ValueError): payload(root, '../secrets')


if __name__ == '__main__': unittest.main()
