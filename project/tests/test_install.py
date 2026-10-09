"""Exercise ZIP integrity and safe installation without historical material or credentials."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import install_demo_assets as installer


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='LightTry install test ')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / 'data').mkdir()
        self.payload = b'synthetic image identity'
        self.record = dict(path='inputs/test.png', bytes=len(self.payload), sha256=hashlib.sha256(self.payload).hexdigest())
        (self.root / 'data/catalog.json').write_text(json.dumps(dict(assets={'test': self.record})))
        (self.root / 'data/demo-package.json').write_text(json.dumps(dict(records={})))
        self.archive = self.root / 'test.zip'
        self.destination = self.root / 'external assets'

    def bundle(self, files):
        with zipfile.ZipFile(self.archive, 'w') as bundle:
            for name, data in files:
                bundle.writestr(name, data)

    def install(self):
        with patch.object(installer, 'ROOT', self.root), patch.object(installer, 'load_catalog') as validate:
            result = installer.install(self.archive, self.destination)
            validate.assert_called_once()
            return result

    def test_verified_install_and_existing_destination_refusal(self):
        self.bundle([('demo-assets/inputs/test.png', self.payload)])
        self.assertEqual(self.install(), self.destination)
        self.assertEqual((self.destination / 'inputs/test.png').read_bytes(), self.payload)
        with self.assertRaisesRegex(ValueError, '已存在'):
            self.install()

    def test_modified_content_does_not_leave_installation(self):
        self.bundle([('demo-assets/inputs/test.png', b'x' * len(self.payload))])
        with self.assertRaisesRegex(ValueError, 'SHA256'):
            self.install()
        self.assertFalse(self.destination.exists())

    def test_extra_traversal_and_missing_files_are_rejected(self):
        for files in ([], [('demo-assets/inputs/test.png', self.payload), ('demo-assets/../escape', b'x')]):
            self.bundle(files)
            with self.assertRaisesRegex(ValueError, '清单'):
                self.install()
            self.assertFalse(self.destination.exists())
            self.assertFalse((self.root / 'escape').exists())


if __name__ == '__main__':
    unittest.main()
