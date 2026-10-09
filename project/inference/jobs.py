"""Durable single-task state. Only verified current-task output becomes success."""
import copy
import json
import os
import re
import threading
import time
import uuid
from pathlib import Path

from .images import InputError, decode, digest, prepare, MAX_BYTES

ID = re.compile(r'^[0-9a-f]{32}$')
ACTIVE = {'queued', 'running'}
STAGES = {'preflight', 'weights', 'inverse', 'forward', 'validating', 'transferring'}
RUN_CONFIG = {'model': 'Cosmos Diffusion Renderer',
    'upstreamCommit': '0f3e2dc435032ecbad654c2fc2153df85384b138',
    'width': 1280, 'height': 704, 'frames': 1, 'steps': 15, 'seed': 1000,
    'guidance': 0.0, 'offload': False, 'execution': 'separate inverse then forward processes'}


class JobError(Exception):
    def __init__(self, code, message, http=400):
        self.code, self.message, self.http = code, message, http
        super().__init__(message)


def atomic(path, value):
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temporary, path)


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


class TaskStore:
    def __init__(self, root, presets, executor=None, timeout=1080, retention=86400, clock=time.time):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.presets = {p['id']: p for p in presets}
        self.executor, self.timeout, self.retention, self.clock = executor, timeout, retention, clock
        self.mutex = threading.RLock()
        # OS releases this lock on process exit; another server cannot share this store.
        self.lockfile = (self.root / '.server.lock').open('a+b')
        self.lockfile.write(b'0'); self.lockfile.flush(); self.lockfile.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.lockfile.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.lockfile, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.lockfile.close()
            raise JobError('STORE_IN_USE', '任务目录正在被另一个本地服务使用。', 409)

    def close(self):
        self.lockfile.close()  # Execution is independent; closing the UI server is not cancellation.

    def directory(self, task_id):
        if not isinstance(task_id, str) or not ID.fullmatch(task_id):
            raise JobError('TASK_NOT_FOUND', '任务不存在。', 404)
        path = self.root / task_id
        if path.is_symlink() or path.resolve().parent != self.root or not path.is_dir():
            raise JobError('TASK_NOT_FOUND', '任务不存在。', 404)
        return path

    def capabilities(self):
        return {'enabled': self.executor is not None, 'developmentTestMode': False,
                'message': '推理服务已配置；只允许一个任务串行执行。' if self.executor else '已载入，尚未连接推理服务',
                'cancelRunning': False, 'maxBytes': MAX_BYTES}

    def public(self, task):
        fields = ('taskId', 'input', 'preset', 'status', 'stage', 'result', 'error',
                  'createdAt', 'updatedAt', 'expiresAt', 'executionUncertain', 'runConfig')
        return copy.deepcopy({key: task[key] for key in fields if key in task})

    def submit(self, data, metadata, mime):
        with self.mutex:
            if not self.executor:
                raise JobError('SERVICE_NOT_CONNECTED', '真实推理默认关闭；本机预览不会上传或生成。', 503)
            try:
                input_id = metadata['inputId']
                key = metadata['requestId']
                preset = self.presets[metadata['presetId']]
                if not all(isinstance(x, str) and ID.fullmatch(x) for x in (input_id, key)):
                    raise ValueError()
                name = metadata.get('name', '照片')
                if not isinstance(name, str) or len(name) > 200 or any(ord(c) < 32 for c in name):
                    raise ValueError()
            except (KeyError, TypeError, ValueError):
                raise JobError('INVALID_REQUEST', '任务身份、预设或照片名称无效。')
            if mime not in ('image/jpeg', 'image/png', 'image/webp'):
                raise JobError('INVALID_IMAGE', '只接受 JPG、PNG、WebP。')
            # Idempotency survives server restarts. Same key with altered data is a conflict.
            identity = digest(data)
            fingerprint = digest(json.dumps([input_id, preset['id'], identity], separators=(',', ':')).encode())
            existing = []
            for folder in self.root.iterdir():
                if ID.fullmatch(folder.name) and folder.is_dir() and not folder.is_symlink() and (folder / 'task.json').is_file():
                    task = self._refresh(folder)
                    existing.append(task)
                    if task['requestId'] == key:
                        if task['fingerprint'] != fingerprint:
                            raise JobError('IDEMPOTENCY_CONFLICT', '重复请求的图片或预设发生变化。', 409)
                        return self.public(task)
            if any(t['status'] in ACTIVE or t.get('executionUncertain') for t in existing):
                raise JobError('TASK_BUSY', '已有任务执行中，或执行端状态待核实；请先查看该任务。', 409)
            if hasattr(self.executor, 'check_ready'):
                try:
                    self.executor.check_ready()
                except (OSError, ValueError, KeyError):
                    raise JobError('EXECUTION_NOT_AUTHORIZED', '当前本地授权、守护或主机确认尚未就绪；未执行或上传图片。', 503)
            try:
                _, _, original = decode(data, mime)
            except InputError as error:
                raise JobError('INVALID_IMAGE', str(error), 422)
            now = self.clock()
            task_id = uuid.uuid4().hex
            folder = self.root / task_id
            folder.mkdir()
            try:
                (folder / 'original').write_bytes(data)
                (folder / 'inputs').mkdir()
                prepared = prepare(data, folder / 'inputs/photo.png')
            except InputError as error:
                # No executable request was written; preserve invalid input only locally.
                raise JobError('INVALID_IMAGE', str(error), 422)
            task = {'taskId': task_id, 'input': {'id': input_id, 'name': name, 'kind': 'upload',
                'url': f'/api/tasks/{task_id}/input', 'originalUrl': f'/api/tasks/{task_id}/original',
                'width': 1280, 'height': 704, 'sha256': prepared['sha256'], 'canvas': prepared},
                'preset': preset, 'status': 'queued', 'stage': None, 'result': None, 'error': None,
                'createdAt': now, 'updatedAt': now, 'deadline': now + self.timeout,
                'requestId': key, 'fingerprint': fingerprint, 'original': original,
                'nonce': uuid.uuid4().hex, 'runConfig': RUN_CONFIG.copy(), 'executionUncertain': False}
            task['runConfig'].update(self.executor.run_config() if hasattr(self.executor, 'run_config') else
                                     {'weightVerification': 'full', 'weightContentHashesChecked': True})
            atomic(folder / 'task.json', task)
            request = {k: task[k] for k in ('taskId', 'nonce', 'input', 'preset', 'original', 'runConfig')}
            # No paths, original names or client commands are used as execution arguments.
            atomic(folder / 'request.json', request)
            try:
                self.executor.submit(folder, request)
            except Exception:
                task.update(status='failed', error={'code': 'DISPATCH_FAILED', 'message': '执行适配器未能确认接收任务；请核查本地执行记录。'},
                            executionUncertain=True, updatedAt=self.clock())
                atomic(folder / 'task.json', task)
            return self.public(task)

    def _check_result(self, folder, task, receipt):
        expected = {'taskId': task['taskId'], 'nonce': task['nonce'], 'inputId': task['input']['id'],
            'presetId': task['preset']['id'], 'inputSha256': task['input']['sha256'],
            'originalSha256': task['original']['sha256'], 'runConfig': task['runConfig']}
        if any(receipt.get(k) != value for k, value in expected.items()):
            raise ValueError('RESULT_IDENTITY_MISMATCH')
        if receipt.get('file') != 'result.jpg' or receipt.get('processExitCodes') != [0, 0]:
            raise ValueError('RESULT_NOT_FROM_COMPLETED_EXECUTION')
        result_path = folder / 'result.jpg'
        if result_path.is_symlink() or result_path.resolve().parent != folder or not result_path.is_file():
            raise ValueError('RESULT_FILE_OUTSIDE_TASK')
        if result_path.stat().st_size > MAX_BYTES:
            raise ValueError('RESULT_TOO_LARGE')
        payload = result_path.read_bytes()
        if len(payload) != receipt.get('bytes') or digest(payload) != receipt.get('sha256'):
            raise ValueError('RESULT_HASH_MISMATCH')
        rgb, _, meta = decode(payload, 'image/jpeg')
        if rgb.size != (1280, 704):
            raise ValueError('RESULT_SIZE_MISMATCH')
        from PIL import ImageStat
        if max(ImageStat.Stat(rgb).stddev) < 0.5:
            raise ValueError('RESULT_EFFECTIVELY_CONSTANT')
        return {'url': f"/api/tasks/{task['taskId']}/result", 'downloadUrl': f"/api/tasks/{task['taskId']}/download",
            'width': 1280, 'height': 704, 'taskId': task['taskId'], 'inputId': task['input']['id'],
            'presetId': task['preset']['id'], 'sha256': meta['sha256'], 'bytes': meta['bytes'],
            'validation': 'current task identity, successful process exits, JPEG decode, size and SHA256; visual review pending'}

    def _refresh(self, folder):
        task = read(folder / 'task.json')
        now = self.clock()
        if task['status'] in ACTIVE or task.get('executionUncertain'):
            # Executor writes events atomically; never infer stages from elapsed time.
            event_path = folder / 'execution.json'
            if event_path.exists():
                try:
                    event = read(event_path)
                    if (event.get('taskId'), event.get('nonce')) != (task['taskId'], task['nonce']):
                        raise ValueError('EVENT_IDENTITY_MISMATCH')
                    status = event['status']
                    if status not in {'queued', 'running', 'succeeded', 'failed'}:
                        raise ValueError('INVALID_EXECUTOR_STATE')
                    if task['status'] in ACTIVE:
                        if status == 'succeeded':
                            if event.get('executionStopped') is not True:
                                raise ValueError('EXECUTION_COMPLETION_NOT_CONFIRMED')
                            # A late result is retained as evidence but cannot reverse timeout.
                            if now > task['deadline']:
                                raise TimeoutError()
                            task['result'] = self._check_result(folder, task, read(folder / 'receipt.json'))
                            task.update(status='succeeded', expiresAt=now + self.retention, executionUncertain=False)
                        elif status == 'failed':
                            task.update(status='failed', result=None, error={'code': 'EXECUTION_FAILED', 'message': 'Cosmos 执行失败，请查看本地执行日志。'},
                                        executionUncertain=not event.get('executionStopped', False))
                        else:
                            if not (task['status'] == 'running' and status == 'queued'):
                                task['status'] = status
                            stage = event.get('stage')
                            if stage in STAGES:
                                task['stage'] = stage
                    elif status in {'succeeded', 'failed'} and event.get('executionStopped') is True:
                        task['executionUncertain'] = False
                except TimeoutError:
                    task.update(status='failed', result=None, executionUncertain=False,
                                error={'code': 'TASK_TIMEOUT', 'message': '任务已超时，本次结果不再发布。执行端已结束。'})
                except (OSError, ValueError, KeyError, InputError):
                    task.update(status='failed', result=None, executionUncertain=True,
                                error={'code': 'RESULT_INVALID', 'message': '执行记录或结果归属校验失败；不会展示或下载此结果。'})
            if task['status'] in ACTIVE and now > task['deadline']:
                task.update(status='failed', result=None, executionUncertain=True,
                            error={'code': 'TASK_TIMEOUT', 'message': '任务超时；未确认执行端已停止，禁止再次提交。独立守护仍负责停机。'})
            if task.get('executionUncertain') and self.executor and hasattr(self.executor, 'confirmed_stopped'):
                if self.executor.confirmed_stopped(folder):
                    task['executionUncertain'] = False
                    task['error']['message'] += ' 本次资源已由独立 API 确认 STOPPED；本次任务仍为失败。'
            task['updatedAt'] = now
            atomic(folder / 'task.json', task)
        if task['status'] == 'succeeded' and now >= task['expiresAt']:
            task.update(status='expired', result=None, updatedAt=now, error={'code': 'RESULT_EXPIRED', 'message': '结果已过期，不能继续展示或下载。'})
            atomic(folder / 'task.json', task)
        elif task['status'] == 'succeeded':
            try:
                self._check_result(folder, task, read(folder / 'receipt.json'))
            except (OSError, ValueError, KeyError, InputError):
                task.update(status='failed', result=None, updatedAt=now,
                            error={'code': 'RESULT_INVALID', 'message': '结果文件身份校验失败；不能继续展示或下载。'})
                atomic(folder / 'task.json', task)
        return task

    def get(self, task_id):
        with self.mutex:
            return self.public(self._refresh(self.directory(task_id)))

    def by_request(self, request_id):
        if not isinstance(request_id, str) or not ID.fullmatch(request_id):
            raise JobError('TASK_NOT_FOUND', '任务不存在。', 404)
        with self.mutex:
            for folder in self.root.iterdir():
                if ID.fullmatch(folder.name) and not folder.is_symlink() and (folder / 'task.json').is_file():
                    if read(folder / 'task.json')['requestId'] == request_id:
                        return self.public(self._refresh(folder))
        raise JobError('TASK_NOT_FOUND', '该请求尚无任务记录；重新载入图片后才可提交。', 404)

    def cancel(self, task_id):
        self.get(task_id)
        raise JobError('CANCEL_UNSUPPORTED', '当前适配器不能保证终止远端进程；任务未取消。独立守护和固定截止仍生效。', 409)

    def file(self, task_id, kind):
        with self.mutex:
            folder = self.directory(task_id)
            task = self._refresh(folder)
            allowed = {'input': 'inputs/photo.png', 'original': 'original', 'result': 'result.jpg', 'download': 'result.jpg'}
            if kind not in allowed:
                raise JobError('FILE_NOT_FOUND', '文件不在允许范围内。', 404)
            if kind in ('result', 'download'):
                if task['status'] != 'succeeded':
                    raise JobError('RESULT_UNAVAILABLE', '本次任务没有可用且未过期的结果。', 410 if task['status'] == 'expired' else 409)
                try:
                    self._check_result(folder, task, read(folder / 'receipt.json'))
                except (OSError, ValueError, KeyError, InputError):
                    task.update(status='failed', result=None, error={'code': 'RESULT_INVALID', 'message': '结果文件校验失败。'})
                    atomic(folder / 'task.json', task)
                    raise JobError('RESULT_INVALID', '结果文件校验失败。', 409)
            path = folder / allowed[kind]
            if path.is_symlink() or not path.resolve().is_relative_to(folder) or not path.is_file():
                raise JobError('FILE_NOT_FOUND', '文件不在允许范围内。', 404)
            mime = task['original']['mime'] if kind == 'original' else 'image/png' if kind == 'input' else 'image/jpeg'
            filename = f"LightTry_{task_id}_{task['preset']['id']}.jpg" if kind == 'download' else None
            if path.stat().st_size > MAX_BYTES:
                raise JobError('FILE_INVALID', '任务文件大小校验失败。', 409)
            payload = path.read_bytes()
            if kind in ('input', 'original') and digest(payload) != (task['input'] if kind == 'input' else task['original'])['sha256']:
                raise JobError('FILE_INVALID', '任务输入文件身份校验失败。', 409)
            return payload, mime, filename
