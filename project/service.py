"""Deployment WSGI entry, served by Waitress; shares the existing business handlers."""
import argparse
import base64
from email.message import Message
from http import HTTPStatus
import io
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import secrets
import signal
import tempfile
from types import SimpleNamespace
from urllib.parse import urlsplit

import studio
from inference.jobs import ID, JobError
from inference.images import MAX_BYTES
from persistence import Workspace

ROOT = Path(__file__).resolve().parent.parent
LOG = logging.getLogger('lighttry.service')


class RequestConnection:
    # Waitress owns transport timeouts and buffering; business handlers keep their API.
    def settimeout(self, seconds):
        pass


class Application:
    def __init__(self, options):
        parsed = urlsplit(options.public_origin)
        if (parsed.scheme not in ('http', 'https') or not parsed.hostname or
                parsed.username or parsed.password or parsed.path not in ('', '/') or
                parsed.query or parsed.fragment or '*' in parsed.netloc):
            raise ValueError('EXACT_PUBLIC_ORIGIN_REQUIRED')
        self.origin = parsed.scheme + '://' + parsed.netloc
        password = os.environ.get('LIGHTTRY_ACCESS_PASSWORD', '')
        if (password == 'REPLACE_WITH_A_NEW_PRIVATE_PASSWORD' or len(password) < 24 or
                len(password) > 256 or any(ord(c) < 33 or ord(c) > 126 for c in password)):
            raise ValueError('LIGHTTRY_ACCESS_PASSWORD_24_TO_256_ASCII_REQUIRED')
        self.credentials = ('lighttry:' + password).encode('ascii')
        data = Path(options.data_root).expanduser()
        if not data.is_absolute() or data.resolve().is_relative_to(ROOT.resolve()):
            raise ValueError('DATA_ROOT_MUST_BE_ABSOLUTE_AND_OUTSIDE_CODE')
        if any(p.is_symlink() for p in (data, *data.parents)):
            raise ValueError('DATA_ROOT_SYMLINK_FORBIDDEN')
        for name in ('photos', 'tasks', 'environments-v2', 'inverse-cache', 'logs', 'tmp', 'workspace.sqlite3'):
            if (data / name).is_symlink():
                raise ValueError('PERSISTENT_PATH_SYMLINK_FORBIDDEN')
        if (data / 'logs/service.log').is_symlink():
            raise ValueError('LOG_PATH_SYMLINK_FORBIDDEN')
        assets = Path(options.assets_dir).expanduser().resolve() if options.assets_dir else ROOT / 'project/demo-assets'
        if data.resolve().is_relative_to(assets) or assets.is_relative_to(data.resolve()):
            raise ValueError('PRIVATE_DATA_AND_DEMO_ASSETS_MUST_BE_SEPARATE')
        data.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.environ['LIGHTTRY_DATA_ROOT'] = str(data.resolve())
        os.environ['LIGHTTRY_INVERSE_CACHE'] = str(data / 'inverse-cache')
        # Uploaded bodies buffered by Waitress must also stay on the private data volume.
        (data / 'tmp').mkdir(exist_ok=True, mode=0o700)
        tempfile.tempdir = str(data / 'tmp')
        origin = self.origin

        class DeploymentHandler(studio.Handler):
            def valid_host(self):
                return self.headers.get('Host') == urlsplit(origin).netloc

            def valid_origin(self):
                return self.headers.get('Origin') in (None, origin)

            def send_response(self, code, message=None):
                self.response_status = code
                self.response_headers = []

            def send_header(self, name, value):
                self.response_headers.append((name, str(value)))

            def end_headers(self):
                pass

            def log_message(self, fmt, *args):
                pass  # Never log raw request targets, names, credentials or body content.

        args = SimpleNamespace(assets_dir=str(assets), tasks_dir=data / 'tasks',
                               evidence_config=options.evidence_config,
                               accepted_package=options.accepted_package, no_demo=not options.assets_dir,
                               language_key_file=None, inference_config=None)
        self.handler = studio.configure(args, DeploymentHandler)
        # Long-lived storage by default; historical expiry/deadlines remain untouched.
        self.handler.task_store.retention = 100 * 365 * 86400
        try:
            self.workspace = Workspace(data, self.handler.environment_library.environments,
                                       self.handler.lighting_capabilities)
        except Exception:
            self.handler.task_store.close()
            raise
        logs = RotatingFileHandler(data / 'logs/service.log', maxBytes=2 * 1024 * 1024, backupCount=3, encoding='utf-8')
        logs.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
        self.log_handler = logs
        LOG.addHandler(logs); LOG.setLevel(logging.INFO)
        LOG.info('service initialized; paid services disabled')

    def close(self):
        self.handler.task_store.close()
        LOG.info('service stopped')
        LOG.removeHandler(self.log_handler); self.log_handler.close()

    def authorized(self, environ):
        value = environ.get('HTTP_AUTHORIZATION', '')
        if not value.startswith('Basic ') or len(value) > 1024:
            return False
        try:
            return secrets.compare_digest(base64.b64decode(value[6:], validate=True), self.credentials)
        except ValueError:
            return False

    def __call__(self, environ, start_response):
        h = self.handler.__new__(self.handler)
        h.path = environ.get('PATH_INFO', '/')
        if environ.get('QUERY_STRING'):
            h.path += '?' + environ['QUERY_STRING']
        h.command = environ['REQUEST_METHOD']
        h.request_version = 'HTTP/1.1'
        h.requestline = h.command + ' / HTTP/1.1'
        h.client_address = ('', 0)
        h.server = SimpleNamespace(server_port=8080)
        h.connection = RequestConnection()
        h.rfile = environ['wsgi.input']; h.wfile = io.BytesIO()
        h.response_headers = []; h.response_status = 500
        h.headers = Message()
        for key, value in environ.items():
            if key.startswith('HTTP_'):
                h.headers[key[5:].replace('_', '-')] = str(value)
        for name in ('CONTENT_TYPE', 'CONTENT_LENGTH'):
            if environ.get(name):
                h.headers[name.replace('_', '-')] = str(environ[name])
        try:
            if not h.valid_host():
                h.job_error(JobError('INVALID_HOST', '访问地址未配置。', 403))
            elif not self.authorized(environ):
                h.job_error(JobError('AUTH_REQUIRED', '请使用工作室账号登录。', 401))
                h.send_header('WWW-Authenticate', 'Basic realm="LightTry", charset="UTF-8"')
            elif not h.valid_origin():
                h.job_error(JobError('INVALID_ORIGIN', '仅接受已配置的同源访问。', 403))
            elif h.command in ('POST', 'PUT', 'DELETE') and h.headers.get('X-LightTry-Token') != h.csrf_token:
                h.job_error(JobError('INVALID_TOKEN', '请刷新页面后重试。', 403))
            elif self.private_route(h):
                pass
            elif h.command == 'GET':
                h.do_GET()
            elif h.command == 'POST':
                # Mutable environment catalog and task preset bindings are shared.
                with h.task_store.mutex:
                    h.do_POST()
                    h.task_store.environments.update(h.environment_library.environments)
            else:
                h.job_error(JobError('METHOD_NOT_ALLOWED', '请求方法不支持。', 405))
        except JobError as error:
            h.job_error(error)
        except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
            h.wfile = io.BytesIO()
            h.job_error(JobError('REQUEST_INVALID', '请求数据或持久化记录无效。', 422))
        except Exception:
            LOG.error('request failed; internal I/O or application error')
            h.wfile = io.BytesIO()
            h.job_error(JobError('STATE_UNAVAILABLE', '服务读写失败，请检查本机日志。', 503))
        LOG.info('request method=%s status=%s', h.command, h.response_status)
        start_response(f'{h.response_status} {HTTPStatus(h.response_status).phrase}', h.response_headers)
        return [h.wfile.getvalue()]

    def body(self, h, limit):
        if h.headers.get('Transfer-Encoding'):
            raise JobError('INVALID_BODY', '不接受分块请求。', 400)
        try:
            size = int(h.headers.get('Content-Length', '0'))
        except ValueError:
            raise JobError('INVALID_BODY', '请求长度无效。', 400)
        if not 0 < size <= limit:
            raise JobError('BODY_TOO_LARGE', '请求为空或超过上限。', 413)
        data = h.rfile.read(size)
        if len(data) != size:
            raise JobError('INVALID_BODY', '请求不完整。', 400)
        return data

    def private_route(self, h):
        path = urlsplit(h.path).path
        if h.command == 'GET' and path == '/api/health':
            with self.workspace.connect() as db:
                db.execute('SELECT 1').fetchone()
            h.json_response({'status': 'ready', 'paidServices': False})
        elif h.command == 'GET' and path in ('/api/workspace', '/api/workspace/export'):
            value = self.workspace.library()
            value['taskIds'] = [p.name for p in h.task_store.root.iterdir()
                                if ID.fullmatch(p.name) and not p.is_symlink() and (p / 'task.json').is_file()]
            h.send_bytes(json.dumps(value, ensure_ascii=False).encode(), 'application/json; charset=utf-8',
                         'lighttry-workspace.json' if path.endswith('/export') else None)
        elif h.command == 'POST' and path == '/api/workspace':
            if h.headers.get('Content-Type') != 'application/json':
                raise JobError('INVALID_BODY', '需要 JSON。', 400)
            body = studio.shared.strict_json(self.body(h, 1024 * 1024).decode('utf-8'))
            with h.task_store.mutex:
                h.json_response(self.workspace.save_library(body))
        elif path.startswith('/api/photos/'):
            pid = path.removeprefix('/api/photos/')
            if h.command == 'GET':
                _, data, mime = self.workspace.photo(pid)
                h.send_bytes(data, mime)
            elif h.command == 'POST':
                metadata = studio.shared.strict_json(base64.b64decode(h.headers.get('X-LightTry-Photo', ''), validate=True).decode('utf-8'))
                if not isinstance(metadata, dict) or set(metadata) != {'name'}:
                    raise JobError('PHOTO_METADATA_INVALID', '照片名称字段无效。', 422)
                h.json_response(self.workspace.save_photo(pid, metadata['name'], self.body(h, MAX_BYTES),
                                                          h.headers.get('Content-Type')), 201)
            else:
                h.job_error(JobError('METHOD_NOT_ALLOWED', '请求方法不支持。', 405))
        else:
            return False
        return True


def parser():
    p = argparse.ArgumentParser(description='Linux/CPU standalone service; paid services remain OFF.')
    p.add_argument('--data-root', default=os.environ.get('LIGHTTRY_DATA_ROOT', '/var/lib/lighttry'))
    p.add_argument('--assets-dir', help='Optional licensed demo assets; absent means no bundled demo photos.')
    p.add_argument('--public-origin', default=os.environ.get('LIGHTTRY_PUBLIC_ORIGIN', 'http://localhost:8080'))
    p.add_argument('--evidence-config', type=Path)
    p.add_argument('--accepted-package', type=Path, action='append')
    return p


def main(argv=None):
    options = parser().parse_args(argv)
    # Permissions apply to SQLite, photos, HDR, logs and temporary uploaded bodies.
    os.umask(0o077)
    app = Application(options)
    try:
        from waitress import serve
        def stop(signum, frame):
            raise KeyboardInterrupt()
        signal.signal(signal.SIGTERM, stop)
        print('LightTry CPU service: 0.0.0.0:8080; data=' + str(app.workspace.root), flush=True)
        serve(app, listen='0.0.0.0:8080', threads=4, connection_limit=64,
              max_request_header_size=16384, max_request_body_size=32 * 1024 * 1024,
              channel_timeout=30, expose_tracebacks=False, clear_untrusted_proxy_headers=True)
    finally:
        app.close()
