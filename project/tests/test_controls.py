"""Offline experiment validation. No GPU or upstream model calls."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'project'))
from experiments.controls import normalize, CASES
from experiments.worker import verify_packet


class ControlTests(unittest.TestCase):
    def test_loading_convention_and_one_factor(self):
        self.assertEqual(normalize()['envRot'], 180)
        self.assertEqual(normalize(-45)['envRot'], 135)
        self.assertEqual(normalize(45)['envRot'], 225)
        self.assertEqual(normalize(0, 0.7)['strength'], 0.7)
        for values in [(True, 1), (0, True), (float('nan'), 1), (0, float('inf')),
                       (90, 1), (-45, 0.7), (0, -1), (0, 2), ('45', 1)]:
            with self.subTest(values=values), self.assertRaises(ValueError):
                normalize(*values)

    def test_repeat_not_cached_case(self):
        self.assertEqual(len({c['id'] for c in CASES}), 6)
        self.assertEqual(normalize(CASES[0]['offsetDeg'], CASES[0]['strength']),
                         normalize(CASES[-1]['offsetDeg'], CASES[-1]['strength']))
        self.assertNotEqual(CASES[0]['id'], CASES[-1]['id'])

    def test_packet_and_tamper(self):
        # Local real-source package is optional, never a synthetic GPU result.
        packet = ROOT / '.local/lighttry-development-20261011/matte-frozen-v2/packet'
        if not packet.exists():
            self.skipTest('prepare real historical packet first')
        import shutil
        with tempfile.TemporaryDirectory() as temporary:
            dest = Path(temporary) / 'packet'; shutil.copytree(packet, dest)
            plan = verify_packet(dest)
            self.assertEqual(len(plan['inverseArtifacts']), 5)
            self.assertEqual(plan['inverseSource']['kind'], 'historical-four-materials')
            for rel in ['inputs/photo.png', 'proof/status.json',
                        'project/inference/measured_entry.py', 'project/experiments/controls.py']:
                p = dest / rel; pristine = p.read_bytes(); p.write_bytes(pristine + b'bad')
                with self.subTest(file=rel), self.assertRaises(ValueError):
                    verify_packet(dest)
                p.write_bytes(pristine)


if __name__ == '__main__':
    unittest.main()
