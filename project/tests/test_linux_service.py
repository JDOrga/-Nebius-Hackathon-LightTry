"""Private CPU deployment tests. Synthetic result fixture, never model/cloud execution."""
import base64
import copy
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'project'))
sys.path.insert(0, str(ROOT / 'project/tests'))
from service import Application, parser
from inference_fixture import OfflineExecutor, image_bytes
from inference.images import digest
from light_console import encode_hdr
import numpy as np

PASSWORD = 'OFFLINE_TEST_ONLY_' + 'X' * 32
AUTH = 'Basic ' + base64.b64encode(('lighttry:' + PASSWORD).encode()).decode()


def request(app, path, method='GET', body=b'', headers=None):
    env = {'REQUEST_METHOD': method, 'PATH_INFO': path, 'wsgi.input': io.BytesIO(body),
           'HTTP_HOST': 'localhost:8080', 'HTTP_AUTHORIZATION': AUTH,
           'CONTENT_LENGTH': str(len(body)), 'CONTENT_TYPE': 'application/json'}
    if method != 'GET':
        env['HTTP_X_LIGHTTRY_TOKEN'] = app.handler.csrf_token
        env['HTTP_ORIGIN'] = 'http://localhost:8080'
    if not headers or headers.get('HTTP_AUTHORIZATION',AUTH)==AUTH:
        token,_=app.login_sessions.issue('lighttry');env['HTTP_COOKIE']='lighttry_session='+token
    env.update(headers or {})
    captured = []
    result = b''.join(app(env, lambda status, response_headers: captured.append((status, response_headers))))
    return int(captured[0][0].split()[0]), result, dict(captured[0][1])


class LinuxServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir='/var/tmp' if os.name != 'nt' else None)
        self.previous_tempdir = tempfile.tempdir
        self.env = patch.dict(os.environ, {'LIGHTTRY_ACCESS_PASSWORD': PASSWORD})
        self.env.start()
        self.options = parser().parse_args(['--data-root', self.tmp.name, '--public-origin', 'http://localhost:8080'])
        self.app = Application(self.options)

    def tearDown(self):
        self.app.close()
        tempfile.tempdir = self.previous_tempdir
        self.env.stop()
        self.tmp.cleanup()

    def test_private_paths_auth_same_origin_csrf_and_default_paid_off(self):
        self.assertEqual(request(self.app, '/api/photos/' + 'a'*32, headers={'HTTP_AUTHORIZATION': ''})[0], 401)
        self.assertEqual(request(self.app, '/', headers={'HTTP_HOST': 'evil.test:8080'})[0], 403)
        self.assertEqual(request(self.app, '/api/workspace', 'POST', b'{}', {'HTTP_ORIGIN': 'https://evil.test'})[0], 403)
        self.assertEqual(request(self.app, '/api/workspace', 'POST', b'{}', {'HTTP_X_LIGHTTRY_TOKEN': ''})[0], 403)
        self.assertEqual(request(self.app, '/photos/' + 'a'*64)[0], 404)
        self.assertEqual(request(self.app, '/api/photos/../../workspace.sqlite3')[0], 404)
        self.assertEqual(request(self.app, '/api/tasks', 'POST', b'{}')[0], 503)
        info = json.loads(request(self.app, '/api/inference')[1]); self.assertFalse(info['enabled'])
        self.assertEqual(json.loads(request(self.app, '/api/catalog')[1])['samples'], [])
        self.assertEqual(request(self.app, '/')[0], 200)
        self.assertEqual(request(self.app, '/workspace-portability.js')[0], 200)

    def test_sqlite_atomic_immutable_versions_and_photo_conflict(self):
        scheme = {'schemaVersion':1, 'planId':'b'*32, 'version':1, 'name':'照片方案',
                  'inputId':'a'*32, 'parentVersion':None,
                  'parameters':{'environmentId':'sunny','offsetDeg':0,'strength':1}}
        library = {'schemaVersion':1, 'schemes':[scheme]}
        data = json.dumps(library, ensure_ascii=False).encode()
        for _ in range(2): self.assertEqual(request(self.app, '/api/workspace', 'POST', data)[0], 200)
        newer = {**scheme, 'version':2, 'parentVersion':1, 'name':'第二版'}
        conflict = {**scheme, 'name':'不能覆盖'}
        self.assertEqual(request(self.app, '/api/workspace', 'POST', json.dumps({'schemaVersion':1,'schemes':[newer,conflict]}).encode())[0],409)
        self.assertEqual(len(self.app.workspace.library()['schemes']),1)  # Whole import rolled back.
        payload = image_bytes()
        photo = self.app.workspace.save_photo('a'*32, '用户照片.png', payload, 'image/png')
        self.assertEqual(photo['originalSha'], digest(payload))
        from inference.jobs import JobError
        with self.assertRaises(JobError): self.app.workspace.save_photo('a'*32,'其他.png',image_bytes((64,64)),'image/png')
        self.assertEqual(self.app.workspace.photo('a'*32)[1],payload)
        exported = json.loads(request(self.app, '/api/workspace/export')[1])
        self.assertNotIn(PASSWORD,json.dumps(exported));self.assertNotIn('pixels',json.dumps(exported))

    def test_invalid_configuration_and_symlink_fail_closed(self):
        for origin in ('https://*.example.com','https://user:secret@example.com','https://example.com/path'):
            with self.subTest(origin=origin):
                bad = copy.copy(self.options);bad.public_origin=origin
                with self.assertRaises(ValueError): Application(bad)
        bad=copy.copy(self.options);bad.data_root=str(ROOT/'project/web/private')
        with self.assertRaises(ValueError):Application(bad)
        if os.name != 'nt':
            other = Path(self.tmp.name)/'link';other.symlink_to(Path(self.tmp.name)/'photos',target_is_directory=True)
            bad=copy.copy(self.options);bad.data_root=str(other)
            with self.assertRaises(ValueError):Application(bad)
        with patch.dict(os.environ,{'LIGHTTRY_ACCESS_PASSWORD':'REPLACE_WITH_A_NEW_PRIVATE_PASSWORD'}):
            with self.assertRaises(ValueError):Application(self.options)

    @unittest.skipIf(os.name == 'nt', 'Real Linux/Waitress process acceptance')
    def test_actual_linux_process_restarts_preserve_photos_hdr_versions_tasks_and_results(self):
        # Assert port availability before starting, never terminate an unrelated listener.
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
            probe.bind(('0.0.0.0',8080))
        scheme={'schemaVersion':1,'planId':'b'*32,'version':1,'name':'重启测试方案',
                'inputId':'a'*32,'parentVersion':None,
                'parameters':{'environmentId':'sunny','offsetDeg':0,'strength':1}}
        self.app.workspace.save_library({'schemaVersion':1,'schemes':[scheme,{**scheme,'version':2,'parentVersion':1,'name':'第二版'}]})
        photo_bytes=image_bytes();self.app.workspace.save_photo('a'*32,'用户原图.png',photo_bytes,'image/png')
        hdr=encode_hdr(np.ones((32,64,3),dtype=np.float32))
        status, raw, _=request(self.app,'/api/environments/import','POST',hdr,{'CONTENT_TYPE':'application/octet-stream'})
        self.assertEqual(status,200); imported=json.loads(raw)
        executor=OfflineExecutor();store=self.app.handler.task_store;store.executor=executor
        task=store.submit(photo_bytes,{'inputId':'a'*32,'requestId':'d'*32,'presetId':'sunny','name':'测试照片'},'image/png')
        receipt=executor.succeed();self.assertEqual(store.get(task['taskId'])['status'],'succeeded')
        pending=store.submit(photo_bytes,{'inputId':'c'*32,'requestId':'e'*32,'presetId':'sunny'},'image/png')
        self.app.close();tempfile.tempdir=self.previous_tempdir
        # Deliberately poison local machine config; --service must not read it.
        poisoned=ROOT/'.local/studio.json';poisoned.parent.mkdir(exist_ok=True)
        original=poisoned.read_bytes() if poisoned.exists() else None
        poisoned.write_text('{"python":"WJX_PATH_MUST_NEVER_BE_READ","not_a_path":true}')
        runs=[]
        from urllib.request import build_opener, HTTPCookieProcessor
        from http.cookiejar import CookieJar
        from urllib.parse import urlencode
        browser = None
        def http(path,auth=True):
            nonlocal browser
            if auth:
                if browser is None:
                    candidate=build_opener(HTTPCookieProcessor(CookieJar()))
                    login=Request('http://localhost:8080/auth/login',data=urlencode({'accessKey':PASSWORD}).encode(),headers={'Origin':'http://localhost:8080'})
                    with candidate.open(login,timeout=5) as response:response.read()
                    browser=candidate
                with browser.open('http://localhost:8080'+path,timeout=3) as response:return response.status,response.read()
            with urlopen('http://localhost:8080'+path,timeout=3) as response:return response.status,response.read()
        try:
            for turn in (1,2):
                browser=None
                log=Path(self.tmp.name)/f'process-{turn}.log'
                with log.open('wb') as stream:
                    process=subprocess.Popen([sys.executable,'-X','utf8','-B',str(ROOT/'start.py'),'--service',
                                              '--data-root',self.tmp.name,'--public-origin','http://localhost:8080'],
                                             cwd='/',env=os.environ.copy(),stdout=stream,stderr=subprocess.STDOUT)
                    try:
                        deadline=time.monotonic()+20
                        while True:
                            if process.poll() is not None:self.fail('Service exited: '+log.read_text())
                            try:
                                if http('/api/health')[0]==200:break
                            except (OSError,HTTPError):pass
                            if time.monotonic()>deadline:self.fail('Linux service not ready in 20s')
                            time.sleep(.1)
                        library=json.loads(http('/api/workspace')[1]);self.assertEqual(len(library['schemes']),2)
                        self.assertIn(task['taskId'],library['taskIds']);self.assertIn(pending['taskId'],library['taskIds'])
                        self.assertEqual(http('/api/photos/'+'a'*32)[1],photo_bytes)
                        self.assertEqual(json.loads(http('/api/tasks/'+pending['taskId'])[1])['status'],'queued')
                        result=json.loads(http('/api/tasks/'+task['taskId'])[1]);self.assertEqual(result['status'],'succeeded')
                        self.assertEqual(digest(http(result['result']['url'])[1]),receipt['sha256'])
                        envs=json.loads(http('/api/environments')[1])['environments'];self.assertTrue(any(e['id']==imported['id'] for e in envs))
                        self.assertEqual(http(imported['thumbnail'])[0],200)
                        with self.assertRaises(HTTPError) as error:http('/api/photos/'+'a'*32,False)
                        self.assertEqual(error.exception.code,401);error.exception.close()
                        self.assertFalse(json.loads(http('/api/inference')[1])['enabled'])
                        self.assertEqual(http('/')[0],200)
                    finally:
                        process.terminate()
                        try:process.wait(timeout=10)
                        except subprocess.TimeoutExpired:process.kill();process.wait();self.fail('SIGTERM did not stop service')
                    self.assertEqual(process.returncode,0,log.read_text())
                    runs.append({'restart':turn,'photoSha256':digest(photo_bytes),'resultSha256':receipt['sha256'],
                                 'versions':2,'pendingStatus':'queued','resultStatus':'succeeded','paidEnabled':False,'exit':process.returncode})
            self.assertTrue((Path(self.tmp.name)/'logs/service.log').is_file())
            self.assertEqual((Path(self.tmp.name)/'workspace.sqlite3').stat().st_mode & 0o077,0)
            print(json.dumps({'linuxRestartAcceptance':runs,'fixture':'synthetic offline executor; no model/cloud calls'},sort_keys=True))
        finally:
            if original is None:poisoned.unlink(missing_ok=True)
            else:poisoned.write_bytes(original)
            # Reopen for common tearDown and prove OS released the store lock.
            self.app=Application(self.options)


if __name__=='__main__':unittest.main()
