"""A recognized complete legacy package may load; damaged/mixed packages may not."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import shared_http


class LegacyDemoTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / 'data').mkdir()
        self.assets = self.root / 'assets'
        self.assets.mkdir()
        def record(payload, path=None):
            result = dict(bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest())
            if path:
                result['path'] = path
            return result
        catalog = dict(samples=[dict(id='old', name='Old'), dict(id='new', name='New')],
                       assets={'old': record(b'old image', 'old.png'),
                               'new': record(b'new image', 'new.png')}, preferredSample='new')
        legacy = dict(name='legacy', sampleIds=['old'], assetIds=['old'],
                      records={'license.txt': record(b'old license')})
        package = dict(records={'license.txt': record(b'new license'),
                                'new-source.json': record(b'new source')}, compatiblePackages=[legacy])
        (self.root / 'data/catalog.json').write_text(json.dumps(catalog), encoding='utf8')
        (self.root / 'data/demo-package.json').write_text(json.dumps(package), encoding='utf8')
        (self.assets / 'old.png').write_bytes(b'old image')
        (self.assets / 'license.txt').write_bytes(b'old license')

    def load(self):
        with patch.object(shared_http, 'ROOT', self.root):
            return shared_http.load_catalog(self.assets)

    def test_complete_legacy_only_exposes_installed_samples(self):
        catalog = self.load()
        self.assertEqual([s['id'] for s in catalog['samples']], ['old'])
        self.assertEqual(set(catalog['assets']), {'old'})
        self.assertNotIn('preferredSample', catalog)
        self.assertEqual(catalog['demoPackage']['unavailableSamples'], ['New'])

    def test_corrupted_legacy_image_and_license_are_rejected(self):
        for name in ('old.png', 'license.txt'):
            path = self.assets / name
            original = path.read_bytes()
            path.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, '校验失败'):
                self.load()
            path.write_bytes(original)

    def test_partial_new_package_cannot_fall_back(self):
        (self.assets / 'new.png').write_bytes(b'new image')
        with self.assertRaisesRegex(ValueError, '校验失败'):
            self.load()

    def test_complete_current_package_keeps_all_samples(self):
        (self.assets / 'new.png').write_bytes(b'new image')
        (self.assets / 'license.txt').write_bytes(b'new license')
        (self.assets / 'new-source.json').write_bytes(b'new source')
        catalog = self.load()
        self.assertEqual(len(catalog['samples']), 2)
        self.assertEqual(catalog['preferredSample'], 'new')
        self.assertNotIn('demoPackage', catalog)


if __name__ == '__main__':
    unittest.main()
