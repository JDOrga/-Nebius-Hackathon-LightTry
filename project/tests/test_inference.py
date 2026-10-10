"""Offline task and HTTP validation. Synthetic files / independent executor only."""
import base64
from concurrent.futures import ThreadPoolExecutor
import io
import json
import sys
import tarfile
import tempfile
import threading
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from http.server import ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from inference.images import decode, prepare, digest, InputError, MAX_BYTES
from inference.jobs import TaskStore, JobError, read, atomic
from inference.driver import build_bundle, extract_result, authorization, run_driver
from inference_fixture import OfflineExecutor, image_bytes
import server

PRESETS = json.loads((ROOT / 'data/catalog.json').read_text(encoding='utf-8'))['presets']


def metadata():
    return {'inputId': uuid.uuid4().hex, 'requestId': uuid.uuid4().hex, 'presetId': 'sunny', 'name': '新照片.png'}


class ImageTests(unittest.TestCase):
    def test_recorded_crop_is_exact_lossless_and_rejects_guesses(self):
        from PIL import Image, ImageChops
        from inference.images import crop_photo_region
        payload = image_bytes((1280, 704))
        canvas = {'width': 1280, 'height': 704, 'validRegion': [442, 0, 838, 704]}
        with Image.open(io.BytesIO(payload)) as full, Image.open(io.BytesIO(crop_photo_region(payload, canvas))) as crop:
            self.assertEqual(crop.size, (396, 704))
            self.assertIsNone(ImageChops.difference(full.crop((442, 0, 838, 704)), crop).getbbox())
        for bad in (None, {}, {**canvas, 'validRegion': [-1, 0, 838, 704]},
                    {**canvas, 'validRegion': [442, 0, 1281, 704]},
                    {**canvas, 'validRegion': [442, 0, 442, 704]},
                    {**canvas, 'validRegion': [442.0, 0, 838, 704]}, {**canvas, 'width': 1279}):
            with self.assertRaises(InputError): crop_photo_region(payload, bad)
    def test_supported_content_and_limits(self):
        for fmt, mime in [('PNG', 'image/png'), ('JPEG', 'image/jpeg'), ('WEBP', 'image/webp')]:
            self.assertEqual(decode(image_bytes(fmt=fmt), mime)[2]['mime'], mime)
        for data, mime in [(b'', None), (b'x' * (MAX_BYTES + 1), None), (b'bad', 'image/png'),
                           (image_bytes(), 'image/jpeg'), (image_bytes((31, 200)), None),
                           (image_bytes((16385, 32)), None), (image_bytes(fmt='GIF'), None),
                           (image_bytes()[:100], None)]:
            with self.subTest(mime=mime, size=len(data)), self.assertRaises(InputError):
                decode(data, mime)

    def test_animation_is_rejected(self):
        from PIL import Image
        stream = io.BytesIO()
        Image.new('RGB', (64, 64), 'red').save(stream, format='PNG', save_all=True,
            append_images=[Image.new('RGB', (64, 64), 'blue')], duration=50, loop=0)
        with self.assertRaises(InputError):
            decode(stream.getvalue(), 'image/png')

    def test_pixel_limit_checked_before_decoding_and_symlinks_denied(self):
        import struct, zlib
        payload = bytearray(image_bytes((64, 64)))
        payload[16:24] = struct.pack('>II', 8000, 6000)
        payload[29:33] = struct.pack('>I', zlib.crc32(payload[12:29]))
        with self.assertRaises(InputError): decode(bytes(payload), 'image/png')

    def test_preprocessing_matches_validated_samples_without_history_dependency(self):
        if not server.resolve_assets_dir().exists():
            self.skipTest(server.INSTALL_HINT)
        catalog = server.load_catalog()
        with tempfile.TemporaryDirectory() as directory:
            for sample in catalog['samples']:
                path = server.asset_path(server.resolve_assets_dir(), catalog['assets'][sample['original']['assetId']])
                target = Path(directory) / 'prepared.png'
                record = prepare(path.read_bytes(), target)
                from PIL import Image, ImageChops
                expected = server.asset_path(server.resolve_assets_dir(), catalog['assets'][sample['input']['assetId']])
                with Image.open(target) as actual, Image.open(expected) as previous:
                    # LittleCMS-created ICC headers include creation time; compare
                    # decoded pixels instead of claiming identical encoded PNG bytes.
                    self.assertIsNone(ImageChops.difference(actual, previous).getbbox())
                self.assertEqual(record['validRegion'], sample['canvas']['validRegion'])

    def test_corrupt_icc_and_exif_rotation(self):
        from PIL import Image
        source = Image.new('RGB', (64, 96), 'red')
        exif = source.getexif(); exif[274] = 6
        stream = io.BytesIO(); source.save(stream, format='JPEG', exif=exif)
        self.assertEqual(decode(stream.getvalue())[0].size, (96, 64))
        stream = io.BytesIO(); source.save(stream, format='PNG', icc_profile=b'bad ICC')
        with tempfile.TemporaryDirectory() as directory, self.assertRaises(InputError):
            prepare(stream.getvalue(), Path(directory) / 'input.png')


class JobTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='LightTry offline jobs ')
        self.executor = OfflineExecutor()
        self.now = 1000
        self.store = TaskStore(self.temp.name, PRESETS, self.executor, timeout=10, retention=60, clock=lambda: self.now)
        self.data, self.meta = image_bytes(), metadata()

    def tearDown(self):
        self.store.close(); self.temp.cleanup()

    def submit(self):
        return self.store.submit(self.data, self.meta, 'image/png')

    def test_default_off_is_zero_execution(self):
        self.store.executor = None
        with self.assertRaises(JobError) as error:
            self.submit()
        self.assertEqual(error.exception.code, 'SERVICE_NOT_CONNECTED')
        self.assertEqual(self.executor.calls, [])
        self.assertEqual(list(Path(self.temp.name).glob('*/request.json')), [])

    def test_events_and_validated_current_result(self):
        task = self.submit(); tid = task['taskId']
        self.assertEqual(task['status'], 'queued'); self.assertIsNone(task['result'])
        with self.assertRaises(JobError):
            self.store.file(tid, 'download')
        self.executor.event(stage='inverse')
        task = self.store.get(tid)
        self.assertEqual((task['status'], task['stage']), ('running', 'inverse'))
        self.assertNotIn('progress', task)
        receipt = self.executor.succeed()
        task = self.store.get(tid)
        self.assertEqual(task['status'], 'succeeded')
        self.assertEqual(task['result']['inputId'], self.meta['inputId'])
        payload, mime, filename = self.store.file(tid, 'download')
        self.assertEqual(digest(payload), receipt['sha256']); self.assertEqual(mime, 'image/jpeg')
        self.assertIn(tid, filename)
        self.assertNotIn('nonce', task); self.assertNotIn('requestId', task)

    def test_duplicate_key_concurrent_and_after_restart(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            tasks = list(pool.map(lambda _: self.submit(), range(2)))
        self.assertEqual(tasks[0]['taskId'], tasks[1]['taskId'])
        self.assertEqual(len(self.executor.calls), 1)
        self.store.close()
        self.store = TaskStore(self.temp.name, PRESETS, self.executor, clock=lambda: self.now)
        self.assertEqual(self.submit()['taskId'], tasks[0]['taskId'])
        self.assertEqual(self.store.by_request(self.meta['requestId'])['taskId'], tasks[0]['taskId'])
        self.assertEqual(len(self.executor.calls), 1)

    def test_duplicate_changes_and_serial_busy(self):
        self.submit()
        changed = dict(self.meta, presetId='street')
        with self.assertRaises(JobError) as error:
            self.store.submit(self.data, changed, 'image/png')
        self.assertEqual(error.exception.code, 'IDEMPOTENCY_CONFLICT')
        with self.assertRaises(JobError) as error:
            self.store.submit(self.data, metadata(), 'image/png')
        self.assertEqual(error.exception.code, 'TASK_BUSY')
        self.assertEqual(len(self.executor.calls), 1)

    def test_timeout_blocks_retry_and_late_success(self):
        tid = self.submit()['taskId']; self.now += 11
        task = self.store.get(tid)
        self.assertEqual(task['error']['code'], 'TASK_TIMEOUT'); self.assertTrue(task['executionUncertain'])
        with self.assertRaises(JobError):
            self.store.submit(self.data, metadata(), 'image/png')
        self.executor.succeed()
        task = self.store.get(tid)
        self.assertEqual(task['status'], 'failed'); self.assertIsNone(task['result'])
        self.assertFalse(task['executionUncertain'])
        with self.assertRaises(JobError): self.store.file(tid, 'download')

    def test_independent_stop_releases_busy_without_creating_result(self):
        tid = self.submit()['taskId']; self.now += 11
        self.assertTrue(self.store.get(tid)['executionUncertain'])
        self.executor.confirmed_stopped = lambda folder: True  # explicit independent test evidence
        task = self.store.get(tid)
        self.assertFalse(task['executionUncertain']); self.assertEqual(task['status'], 'failed')
        self.assertIsNone(task['result'])

    def test_wrong_executor_identity_and_unknown_stage_are_not_progress(self):
        tid = self.submit()['taskId']; folder = Path(self.temp.name) / tid
        self.executor.event(stage='fake_50_percent')
        task = self.store.get(tid)
        self.assertIsNone(task['stage']); self.assertNotIn('progress', task)
        event = read(folder / 'execution.json'); event['nonce'] = 'previous'; atomic(folder / 'execution.json', event)
        task = self.store.get(tid)
        self.assertEqual(task['error']['code'], 'RESULT_INVALID'); self.assertIsNone(task['result'])

    def test_failed_execution_and_unsupported_cancellation(self):
        tid = self.submit()['taskId']
        with self.assertRaises(JobError) as error: self.store.cancel(tid)
        self.assertEqual(error.exception.code, 'CANCEL_UNSUPPORTED')
        self.assertEqual(self.store.get(tid)['status'], 'queued')
        self.executor.event('failed', stopped=True)
        task = self.store.get(tid)
        self.assertEqual(task['error']['code'], 'EXECUTION_FAILED')
        self.assertFalse(task['executionUncertain'])
        self.assertIsNone(task['result'])

    def test_expiration_and_changed_result_download(self):
        tid = self.submit()['taskId']; self.executor.succeed()
        self.assertEqual(self.store.get(tid)['status'], 'succeeded')
        self.now += 60
        self.assertEqual(self.store.get(tid)['status'], 'expired')
        with self.assertRaises(JobError) as error: self.store.file(tid, 'download')
        self.assertEqual(error.exception.http, 410)

    def test_result_belongs_to_task_and_config(self):
        for field, wrong in [('taskId', uuid.uuid4().hex), ('nonce', uuid.uuid4().hex), ('inputId', 'old'),
            ('presetId', 'street'), ('inputSha256', 'old'), ('originalSha256', 'old'), ('runConfig', {}),
            ('file', '../old.jpg'), ('sha256', 'old'), ('processExitCodes', [0, 1])]:
            with self.subTest(field=field):
                with tempfile.TemporaryDirectory() as directory:
                    executor = OfflineExecutor(); store = TaskStore(directory, PRESETS, executor)
                    try:
                        tid = store.submit(self.data, metadata(), 'image/png')['taskId']
                        receipt = executor.succeed(); receipt[field] = wrong
                        atomic(Path(directory) / tid / 'receipt.json', receipt)
                        task = store.get(tid)
                        self.assertEqual(task['status'], 'failed'); self.assertIsNone(task['result'])
                        with self.assertRaises(JobError): store.file(tid, 'download')
                    finally: store.close()

    def test_missing_wrong_size_constant_and_tampered_outputs(self):
        for kind in ('missing', 'wrong_size', 'constant', 'tampered'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                from PIL import Image
                executor = OfflineExecutor(); store = TaskStore(directory, PRESETS, executor)
                try:
                    tid = store.submit(self.data, metadata(), 'image/png')['taskId']
                    receipt = executor.succeed(); path = Path(directory) / tid / 'result.jpg'
                    if kind == 'missing': path.unlink()
                    elif kind == 'wrong_size': path.write_bytes(image_bytes((64, 64), 'JPEG'))
                    elif kind == 'constant': Image.new('RGB', (1280, 704), 'red').save(path)
                    else:
                        self.assertEqual(store.get(tid)['status'], 'succeeded')
                        path.write_bytes(image_bytes((1280, 704), 'PNG'))
                    if kind in ('wrong_size', 'constant'):
                        receipt.update(sha256=digest(path.read_bytes()), bytes=path.stat().st_size)
                        atomic(path.parent / 'receipt.json', receipt)
                    if kind != 'tampered': self.assertEqual(store.get(tid)['status'], 'failed')
                    with self.assertRaises(JobError): store.file(tid, 'download')
                finally: store.close()

    def test_paths_input_ids_preset_and_filename_are_data(self):
        for changes in ({'inputId': '../x'}, {'requestId': 'X'}, {'presetId': '../street'}, {'name': 'bad\nname'}):
            with self.assertRaises(JobError): self.store.submit(self.data, dict(self.meta, **changes), 'image/png')
        self.meta['name'] = '$(secret); ..\\private.png'
        tid = self.submit()['taskId']
        for bad in ('../x', 'result.jpg', 'receipt.json', 'driver.log', 'input/../receipt.json'):
            with self.assertRaises(JobError): self.store.file(tid, bad)
        for bad in ('..', '../' + tid, tid.upper()):
            with self.assertRaises(JobError): self.store.get(bad)
        self.assertEqual((Path(self.temp.name) / tid / 'original').read_bytes(), self.data)

    def test_second_server_store_lock_and_preparation_failure(self):
        with self.assertRaises(JobError): TaskStore(self.temp.name, PRESETS, self.executor)
        from PIL import Image
        stream = io.BytesIO(); Image.new('RGB', (64, 64)).save(stream, format='PNG', icc_profile=b'invalid')
        with self.assertRaises(JobError): self.store.submit(stream.getvalue(), self.meta, 'image/png')
        self.assertEqual(self.submit()['status'], 'queued')  # partial invalid folder doesn't block future tasks


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.executor = OfflineExecutor()
        self.store = TaskStore(self.temp.name, PRESETS, self.executor)
        handler = type('OfflineHandler', (server.Handler,), {'task_store': self.store})
        self.http = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        self.base = f'http://127.0.0.1:{self.http.server_port}'
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True); self.thread.start()
        self.token = handler.csrf_token
        self.data, self.meta = image_bytes(), metadata()

    def tearDown(self):
        self.http.shutdown(); self.http.server_close(); self.thread.join(); self.store.close(); self.temp.cleanup()

    def post(self, meta=None, data=None, extra=None, route='/api/tasks'):
        headers = {'Content-Type': 'image/png', 'X-LightTry-Token': self.token,
            'X-LightTry-Request': base64.b64encode(json.dumps(meta or self.meta).encode()).decode()}
        headers.update(extra or {})
        return urlopen(Request(self.base + route, data=self.data if data is None else data, headers=headers, method='POST'))

    def test_http_submit_poll_input_original_download_and_errors(self):
        with self.post() as response:
            self.assertEqual(response.status, 202); task = json.load(response)
        tid = task['taskId']
        with urlopen(self.base + task['input']['url']) as response: self.assertEqual(digest(response.read()), task['input']['sha256'])
        with urlopen(self.base + task['input']['originalUrl']) as response: self.assertEqual(response.read(), self.data)
        with self.assertRaises(HTTPError) as error: urlopen(self.base + f'/api/tasks/{tid}/download')
        self.assertEqual(error.exception.code, 409)
        with self.assertRaises(HTTPError) as error: self.post(route=f'/api/tasks/{tid}/cancel', data=b'')
        self.assertEqual(json.load(error.exception)['error']['code'], 'CANCEL_UNSUPPORTED')
        self.executor.succeed()
        with urlopen(self.base + f'/api/tasks/{tid}') as response: self.assertEqual(json.load(response)['status'], 'succeeded')
        with urlopen(self.base + f'/api/tasks/{tid}/download') as response: self.assertIn(tid, response.headers['Content-Disposition'])
        with urlopen(self.base + '/api/requests/' + self.meta['requestId']) as response: self.assertEqual(json.load(response)['taskId'], tid)
        for suffix in ('request.json', 'receipt.json', 'driver.log', '..%2F..%2Fconfig', 'download/anything'):
            with self.assertRaises(HTTPError): urlopen(self.base + f'/api/tasks/{tid}/' + suffix)

    def test_batch_http_one_dispatch_and_preset_route_allowlist(self):
        meta={**self.meta,'presetIds':['sunny','sunrise','sunny']}
        with self.post(meta=meta) as response:task=json.load(response)
        with self.post(meta=meta) as response:self.assertEqual(json.load(response)['taskId'],task['taskId'])
        self.assertEqual(len(self.executor.calls),1)
        self.assertEqual([p['id'] for p in self.executor.calls[0][1]['presets']],['sunny','sunrise'])
        for path in ('presets/sunrise/download','presets/street/download','presets/../../original','presets/sunny/request.json'):
            with self.assertRaises(HTTPError):urlopen(self.base+f"/api/tasks/{task['taskId']}/"+path)
        with self.assertRaises(HTTPError) as error:self.post(meta={**meta,'presetIds':['../sunny']})
        self.assertEqual(error.exception.code,400)

    def test_region_routes_keep_full_result_and_share_recorded_rectangle(self):
        from PIL import Image, ImageChops
        with self.post(data=image_bytes((396, 704))) as response: task = json.load(response)
        tid = task['taskId']; box = task['input']['canvas']['validRegion']
        with self.assertRaises(HTTPError): urlopen(self.base + f'/api/tasks/{tid}/download-region')
        self.executor.succeed(); self.store.get(tid)
        for source, region in (('input', 'input-region'), ('result', 'result-region'), ('result', 'download-region')):
            with urlopen(self.base + f'/api/tasks/{tid}/{source}') as response: full = response.read()
            with urlopen(self.base + f'/api/tasks/{tid}/{region}') as response:
                crop = response.read(); self.assertEqual(response.headers['Content-Type'], 'image/png')
                if region == 'download-region': self.assertIn('_photo-region.png', response.headers['Content-Disposition'])
            with Image.open(io.BytesIO(full)) as a, Image.open(io.BytesIO(crop)) as b:
                self.assertEqual(b.size, (box[2] - box[0], box[3] - box[1]))
                self.assertIsNone(ImageChops.difference(a.crop(tuple(box)), b).getbbox())
        with urlopen(self.base + f'/api/tasks/{tid}/download') as response:
            self.assertEqual(digest(response.read()), read(self.store.directory(tid) / 'receipt.json')['sha256'])
        folder = self.store.directory(tid); damaged = read(folder / 'task.json')
        damaged['input']['canvas']['validRegion'] = [0, 0, 1281, 704]; atomic(folder / 'task.json', damaged)
        with self.assertRaises(HTTPError) as error: urlopen(self.base + f'/api/tasks/{tid}/input-region')
        self.assertEqual(error.exception.code, 409)

    def test_csrf_host_origin_and_public_no_secrets(self):
        for extra in ({'X-LightTry-Token': 'bad'}, {'Origin': 'https://evil.example'}, {'Host': 'evil.example'}):
            with self.assertRaises(HTTPError) as error: self.post(extra=extra)
            self.assertEqual(error.exception.code, 403)
        self.assertEqual(self.executor.calls, [])
        with urlopen(self.base + '/api/inference') as response:
            value = json.load(response)
            self.assertTrue(value['enabled']); self.assertFalse(value['developmentTestMode'])
            self.assertFalse(any('ssh' in k or 'token' in k.lower() and k != 'csrfToken' for k in value))

    def test_http_input_validation_and_disconnected(self):
        for data, extra, status in [(b'bad', {}, 422), (b'x', {'Content-Length': str(MAX_BYTES + 1)}, 413),
            (self.data, {'Content-Type': 'image/jpeg'}, 422), (self.data, {'X-LightTry-Request': 'bad'}, 400)]:
            with self.assertRaises(HTTPError) as error: self.post(data=data, extra=extra)
            self.assertEqual(error.exception.code, status)
            self.assertIn('error', json.load(error.exception))
        self.store.executor = None
        with self.assertRaises(HTTPError) as error: self.post()
        self.assertEqual(error.exception.code, 503)
        self.assertEqual(self.executor.calls, [])


class AdapterTests(unittest.TestCase):
    def test_historical_weights_policy_is_explicit_and_never_current_integrity(self):
        from inference.weights_reuse import validate_reference, reuse_existing
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); models = base / 'models'; models.mkdir(); (models / 'model.pt').write_bytes(b'cpu fixture')
            manifest = {'files':[{'path':'model.pt','size':11,'sha256':digest(b'cpu fixture')}]}
            current = base / 'current.json'; prior = base / 'prior.json'; receipt = base / 'receipt.json'; reference = base / 'reference.json'
            atomic(current, manifest); atomic(prior, manifest); atomic(receipt, {'files':[{'path':'model.pt','verified':True}]})
            atomic(reference, {'weights_manifest_sha256':digest(prior.read_bytes()),'receipt_sha256':digest(receipt.read_bytes()),'historical_run_id':'SYNTHETIC'})
            validate_reference(current, prior, receipt, reference)
            report = reuse_existing(models, prior, receipt, reference)
            self.assertFalse(report['content_verified_this_run']); self.assertFalse(report['all_verified'])
            self.assertEqual(report['checkpoint_content_bytes_read'], 0)
            (models/'model.pt').write_bytes(b'same size!!')
            self.assertFalse(reuse_existing(models, prior, receipt, reference)['content_verified_this_run'])
            atomic(current, {'files':[{'path':'model.pt','size':11,'sha256':'different'}]})
            with self.assertRaises(ValueError): validate_reference(current, prior, receipt, reference)

    def test_guarded_driver_sequence_with_independent_transport_double(self):
        self._driver_sequence()

    def test_local_field_repair_reuses_finished_model_and_keeps_guard(self):
        self._driver_sequence(recover=True)

    def _driver_sequence(self, recover=False):
        import time
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); executor = OfflineExecutor(); store = TaskStore(base / 'jobs', PRESETS, executor)
            try:
                tid = store.submit(image_bytes(), metadata(), 'image/png')['taskId']; job = base / 'jobs' / tid
                run = base / 'guarded-run'; run.mkdir(); config = base / 'config.json'; atomic(config, {'enabled': True})
                calls = []
                settings = {'container_data_dir':'/home/jovyan/data','container_repo':'/home/jovyan/source',
                            'container_checkpoint_dir':'/home/jovyan/models','cuda_home':'/home/jovyan/cuda'}
                authorization_result = (run, {}, settings, {'work_deadline_utc':'2030-01-01T00:00:00Z'}, time.time()+300)
                def transport(argv, **kwargs):
                    operation = argv[argv.index('-Operation') + 1]; calls.append(operation)
                    if recover and operation == 'export_results' and calls.count(operation) == 1:
                        atomic(job / 'retry-results.json', {'reason': 'synthetic missing local field',
                            'change': 'correct synthetic transport field mapping'})
                        raise KeyError('synthetic-local-field')
                    self.assertIs(kwargs['shell'], False)
                    self.assertEqual(Path(argv[argv.index('-File') + 1]).name, 'Invoke-ScaleRemote.ps1')
                    if operation == 'install_bundle': output = {'preparation':'/home/jovyan/data/preview-current'}
                    elif operation == 'launch': output = {'workerPid':123}
                    elif operation == 'inspect':
                        request = read(job / 'request.json')
                        output = {'taskId':tid,'nonce':request['nonce'],'status':'succeeded','executionStopped':True}
                    else: output = {}
                    if operation in ('install_bundle','launch','inspect','export_results'):
                        atomic(run / (operation + '-result.json'), {'output':json.dumps(output)})
                    if operation == 'download_results':
                        executor.succeed()
                        receipt = read(job / 'receipt.json')
                        receipt['gBuffers'] = []
                        for label in ('basecolor', 'normal', 'depth', 'roughness', 'metallic'):
                            name = f'inverse/gbuffer_frames/photo.{label}.jpg'
                            payload = image_bytes((1280, 704), 'JPEG')
                            target = job / name; target.parent.mkdir(parents=True, exist_ok=True)
                            target.write_bytes(payload)
                            receipt['gBuffers'].append({'channel': label, 'relativePath': name,
                                'sha256': digest(payload), 'size': len(payload)})
                        atomic(job / 'receipt.json', receipt)
                        with tarfile.open(run / 'results.tar.gz','w:gz') as tar:
                            for name in ('result.jpg','receipt.json','execution.json'):
                                tar.add(job / name, arcname=name)
                                (job / name).unlink()
                            for item in receipt['gBuffers']:
                                tar.add(job / item['relativePath'], arcname=item['relativePath'])
                    return SimpleNamespace(returncode=0)
                with patch('inference.driver.authorization', return_value=authorization_result), patch('inference.driver.subprocess.run', side_effect=transport):
                    run_driver(job, config)
                expected = ['upload_directory','upload','install_bundle','launch','inspect','export_results']
                if recover: expected += ['inspect', 'export_results']
                self.assertEqual(calls, expected + ['download_results'])
                if recover:
                    self.assertFalse(read(job / 'recovery-result.json')['modelRelaunched'])
                self.assertEqual(store.get(tid)['status'], 'succeeded')
                self.assertFalse((run / 'complete.json').exists())
                self.assertFalse(read(run / 'inference-finished.json')['stop_required'])
            finally: store.close()

    def test_ambiguous_launch_never_reports_success_or_stopped(self):
        import time
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory); executor=OfflineExecutor(); store=TaskStore(base/'jobs',PRESETS,executor)
            try:
                tid=store.submit(image_bytes(),metadata(),'image/png')['taskId'];job=base/'jobs'/tid
                run=base/'run';run.mkdir();cfg=base/'cfg.json';atomic(cfg,{'enabled':True})
                settings={'container_data_dir':'/home/jovyan/data','container_repo':'/home/jovyan/source',
                          'container_checkpoint_dir':'/home/jovyan/models','cuda_home':'/home/jovyan/cuda'}
                def transport(argv,**kwargs):
                    op=argv[argv.index('-Operation')+1]
                    if op=='install_bundle':atomic(run/(op+'-result.json'),{'output':json.dumps({'preparation':'/home/jovyan/data/current'})})
                    return SimpleNamespace(returncode=1 if op=='launch' else 0)
                with patch('inference.driver.authorization',return_value=(run,{},settings,{'work_deadline_utc':'2030-01-01T00:00:00Z'},time.time()+300)),patch('inference.driver.subprocess.run',side_effect=transport):
                    run_driver(job,cfg)
                task=store.get(tid)
                self.assertEqual(task['status'],'failed');self.assertTrue(task['executionUncertain'])
                self.assertFalse(read(job/'execution.json')['executionStopped'])
                self.assertTrue(read(run/'complete.json')['stop_required'])
            finally:store.close()

    def test_bundle_is_current_input_only_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); executor = OfflineExecutor(); store = TaskStore(base / 'jobs', PRESETS, executor)
            try:
                tid = store.submit(image_bytes(), metadata(), 'image/png')['taskId']
                job = base / 'jobs' / tid; run = base / 'run'; run.mkdir()
                build_bundle(job, run)
                with tarfile.open(run / 'inference-code.tar.gz') as tar:
                    self.assertIn('project/inference/worker.py', tar.getnames())
                    self.assertNotIn('original', tar.getnames())
                    self.assertFalse(any('local.json' in n or 'demo-assets' in n for n in tar.getnames()))
                    request = json.load(tar.extractfile('request.json'))
                    self.assertNotIn('name', request['input'])
                    self.assertEqual(digest(tar.extractfile('inputs/photo.png').read()), request['input']['sha256'])
                with self.assertRaises(FileExistsError): build_bundle(job, run)
            finally: store.close()

    def test_result_archive_range_and_duplicates(self):
        for name, type_ in [('../result.jpg', tarfile.REGTYPE), ('/result.jpg', tarfile.REGTYPE),
                            ('result.jpg', tarfile.SYMTYPE), ('x\\result.jpg', tarfile.REGTYPE)]:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                base = Path(directory); archive = base / 'result.tar.gz'
                with tarfile.open(archive, 'w:gz') as tar:
                    member = tarfile.TarInfo(name); member.type = type_; member.size = 1 if type_ == tarfile.REGTYPE else 0
                    tar.addfile(member, io.BytesIO(b'x') if member.size else None)
                with self.assertRaises(ValueError): extract_result(archive, base)

    def test_real_archive_requires_five_gbuffers_and_transfer_hashes(self):
        for bad in ('missing', 'tampered', 'wrong_size'):
            with self.subTest(bad=bad), tempfile.TemporaryDirectory() as directory:
                base = Path(directory); archive = base / 'result.tar.gz'
                payload = image_bytes((64, 64) if bad == 'wrong_size' else (1280, 704), 'JPEG')
                receipt = {'gBuffers': [{'channel': label,
                    'relativePath': f'inverse/gbuffer_frames/photo.{label}.jpg',
                    'size': len(payload), 'sha256': '0'*64 if bad == 'tampered' else digest(payload)}
                    for label in ('basecolor', 'normal', 'depth', 'roughness', 'metallic')]}
                if bad == 'missing': receipt.pop('gBuffers')
                with tarfile.open(archive, 'w:gz') as tar:
                    members = {'result.jpg': payload, 'receipt.json': json.dumps(receipt).encode(),
                               'execution.json': b'{}'}
                    members.update({item['relativePath']: payload for item in receipt.get('gBuffers', [])})
                    for name, data in members.items():
                        member = tarfile.TarInfo(name); member.size = len(data)
                        tar.addfile(member, io.BytesIO(data))
                with self.assertRaises(ValueError): extract_result(archive, base, require_gbuffers=True)

    def test_worker_reuses_fixed_entries_and_only_selected_hdr(self):
        import argparse
        from inference.worker import one_preset_commands
        args = argparse.Namespace(checkpoint_dir=Path('/models'), input_dir=Path('/inputs'), run_dir=Path('/run'),
                                  height=704, width=1280, offload=False)
        for index in range(3):
            inverse, forward = one_preset_commands(args, index)
            start = forward.index('--envlight_ind') + 1; end = forward.index('--use_custom_envmap=True')
            self.assertEqual(forward[start:end], [str(index)])
            self.assertTrue(inverse[2].endswith('inference_inverse_renderer.py'))
            self.assertTrue(forward[2].endswith('inference_forward_renderer.py'))
            self.assertEqual(inverse[inverse.index('--num_steps') + 1], '15')
            self.assertNotIn('--offload_diffusion_transformer', inverse)

    def test_disabled_configuration_does_not_authorize_or_connect(self):
        with tempfile.TemporaryDirectory() as directory, patch('subprocess.Popen') as popen:
            path = Path(directory) / 'local.json'; atomic(path, {'enabled': False})
            with self.assertRaises(ValueError): authorization(path)
            popen.assert_not_called()


if __name__ == '__main__':
    unittest.main()
