"""Read-only checks against actual local source records and loopback HTTP."""
import hashlib
import importlib.util
import json
import threading
import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import unquote
from urllib.request import urlopen
from http.server import ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('preview_server', ROOT / 'server.py')
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


class CatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not server.resolve_assets_dir().exists():
            raise unittest.SkipTest(server.INSTALL_HINT)
        cls.catalog = server.load_catalog()
        cls.source = server.resolve_assets_dir()
        cls.records = json.loads((cls.source / 'source-records.json').read_text(encoding='utf-8'))

    def test_input_and_original_identities_match_prepared_records(self):
        for sample, record in zip(self.catalog['samples'], self.records['images']):
            self.assertEqual(sample['input']['sha256'], record['derived_sha256'])
            self.assertEqual(sample['original']['sha256'], record['sha256'])
            self.assertEqual(sample['canvas']['validRegion'], record['valid_region_xyxy'])
            self.assertEqual((sample['input']['width'], sample['input']['height']), (1280, 704))

    def test_forward_matches_historical_export_hashes_and_hdr_order(self):
        hashes = {e['path'].replace('\\', '/'): e['sha256'] for e in self.records['forward']['exported_results']}
        self.assertEqual(self.records['forward']['state'], 'official_entry_completed')
        for preset, hdr in zip(self.catalog['presets'], self.records['hdrs']):
            self.assertEqual(preset['hdr'], hdr['filename'])
            self.assertEqual(preset['sha256'], hdr['sha256'])
            for sample in self.catalog['samples']:
                result = sample['results'][preset['id']]
                path = f"run/forward/{sample['id']}__0000.relit_{preset['index']:04d}.jpg"
                self.assertEqual(result['sha256'], hashes[path])
                self.assertEqual((result['width'], result['height']), (1280, 704))

    def test_no_experiment_channels_or_crops_or_fusion_assets(self):
        self.assertEqual(len(self.catalog['assets']), 20)
        for item in self.catalog['assets'].values():
            self.assertFalse(any(x in item['path'] for x in ('basecolor', 'scale_', 'fusion', 'roi')))
        self.assertTrue(self.catalog['samples'][3]['unstable'])


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not server.resolve_assets_dir().exists():
            raise unittest.SkipTest(server.INSTALL_HINT)
        server.Handler.assets_dir = server.resolve_assets_dir()
        server.Handler.catalog = server.load_catalog()
        cls.httpd = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        cls.base = f'http://127.0.0.1:{cls.httpd.server_port}'
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join()

    def test_catalog_does_not_expose_source_paths(self):
        with urlopen(self.base + '/api/catalog') as response:
            data = json.load(response)
            self.assertNotIn('assets', data)
            self.assertNotIn('provenance', data)

    def test_all_downloads_are_original_result_bytes_and_honest_names(self):
        catalog = server.Handler.catalog
        for sample in catalog['samples']:
            for preset in catalog['presets']:
                with urlopen(self.base + f"/download/{sample['id']}/{preset['id']}") as response:
                    self.assertEqual(hashlib.sha256(response.read()).hexdigest(), sample['results'][preset['id']]['sha256'])
                    filename = unquote(response.headers['Content-Disposition'])
                    self.assertIn(sample['name'] + '_' + preset['name'], filename)
                    self.assertIn('image/jpeg', response.headers['Content-Type'])

    def test_unknown_uploads_and_private_paths_cannot_be_exported_or_served(self):
        for route in ('/download/upload/sunny', '/assets/../../config/local.json', '/config/local.json', '/server.py', '/data/catalog.json'):
            with self.assertRaises(HTTPError) as caught:
                urlopen(self.base + route)
            self.assertEqual(caught.exception.code, 404)

    def test_provenance_and_assets_paths_are_not_served(self):
        for route in ('/source-records.json', '/assets/ATTRIBUTION.txt', '/demo-assets/source-records.json'):
            with self.assertRaises(HTTPError) as caught:
                urlopen(self.base + route)
            self.assertEqual(caught.exception.code, 404)

    def test_server_has_no_upload_or_inference_endpoint(self):
        from urllib.request import Request
        with self.assertRaises(HTTPError) as caught:
            urlopen(Request(self.base + '/api/inference', data=b'input', method='POST'))
        self.assertEqual(caught.exception.code, 501)


class ConfigurationTests(unittest.TestCase):
    def test_missing_assets_gives_install_instructions(self):
        with tempfile.TemporaryDirectory(prefix='LightTry missing assets ') as directory:
            with self.assertRaisesRegex(ValueError, 'install_demo_assets.py'):
                server.load_catalog(directory)

    def test_relative_paths_use_project_root_and_reject_escape(self):
        self.assertEqual(server.resolve_assets_dir('example assets'), (ROOT / 'example assets').resolve())
        with self.assertRaisesRegex(ValueError, '越界'):
            server.asset_path(ROOT, {'path': '../outside.jpg'})

    def test_environment_and_explicit_path_precedence(self):
        from unittest.mock import patch
        with patch.dict('os.environ', {'LIGHTTRY_DEMO_ASSETS': 'machine assets'}):
            self.assertEqual(server.resolve_assets_dir(), (ROOT / 'machine assets').resolve())
            self.assertEqual(server.resolve_assets_dir('explicit assets'), (ROOT / 'explicit assets').resolve())


if __name__ == '__main__':
    unittest.main()
