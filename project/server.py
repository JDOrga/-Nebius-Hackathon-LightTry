"""Loopback preview and durable inference tasks; real execution disabled by default."""
import argparse
import base64
import hashlib
import json
import mimetypes
import os
import secrets
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, urlsplit

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from inference.jobs import TaskStore, JobError
from inference.images import MAX_BYTES
from language import LanguageAdapter, LanguageError, strict_json
INSTALL_HINT = ('请在代码根目录安装单独提供的 lighttry-demo-assets-20261010-candidate.zip：'
                'python -X utf8 -B project/install_demo_assets.py "<素材包路径>"。'
                '默认位置为 project/demo-assets；外部位置用 --assets-dir 或 LIGHTTRY_DEMO_ASSETS。'
                '详见 project/docs/LOCAL_DEMO_MIGRATION.md；不会替换图片或连接云端。')


def resolve_assets_dir(value=None):
    path = Path(value or os.environ.get('LIGHTTRY_DEMO_ASSETS') or 'demo-assets').expanduser()
    # Relative configuration is stable even when launched from another working directory.
    return (path if path.is_absolute() else ROOT / path).resolve()


def asset_path(assets_dir, item):
    path = (assets_dir / item['path']).resolve()
    if not path.is_relative_to(assets_dir):
        raise ValueError('样例素材路径越界：' + item['path'])
    return path


def load_catalog(assets_dir=None):
    assets_dir = resolve_assets_dir(assets_dir)
    data = json.loads((ROOT / 'data/catalog.json').read_text(encoding='utf-8'))
    for item in data['assets'].values():
        path = asset_path(assets_dir, item)
        if not path.is_file():
            raise ValueError('样例素材缺失：' + item['path'] + '\n' + INSTALL_HINT)
        with path.open('rb') as f:
            if hashlib.file_digest(f, 'sha256').hexdigest() != item['sha256']:
                raise ValueError('样例素材校验失败：' + item['path'] + '\n' + INSTALL_HINT)
    package = json.loads((ROOT / 'data/demo-package.json').read_text(encoding='utf-8'))
    for name, record in package['records'].items():
        path = asset_path(assets_dir, {'path': name})
        if not path.is_file():
            raise ValueError('来源记录缺失：' + name + '\n' + INSTALL_HINT)
        with path.open('rb') as stream:
            if path.stat().st_size != record['bytes'] or hashlib.file_digest(stream, 'sha256').hexdigest() != record['sha256']:
                raise ValueError('来源记录校验失败：' + name + '\n' + INSTALL_HINT)
    return data


class Handler(BaseHTTPRequestHandler):
    catalog = None
    assets_dir = None
    task_store = None
    language_service = None
    csrf_token = secrets.token_urlsafe(32)

    def valid_host(self):
        return self.headers.get('Host') in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}')

    def json_response(self, value, status=200):
        return self.send_bytes(json.dumps(value, ensure_ascii=False).encode(), 'application/json; charset=utf-8', status=status)

    def job_error(self, error):
        return self.json_response({'error': {'code': error.code, 'message': error.message}}, error.http)

    def do_POST(self):
        if not self.valid_host():
            return self.job_error(JobError('INVALID_HOST', '只接受本机地址。', 403))
        expected_origin = f'http://{self.headers.get("Host")}'
        if (self.headers.get('Origin') not in (None, expected_origin) or
                self.headers.get('X-LightTry-Token') != self.csrf_token):
            return self.job_error(JobError('INVALID_ORIGIN', '请从当前本机应用提交任务。', 403))
        route = urlsplit(self.path).path
        try:
            if route == '/api/language/recommend':
                if not self.language_service:
                    raise LanguageError('LANGUAGE_NOT_CONFIGURED', '文字服务未配置；请手动选择灯光。', 503)
                if self.headers.get('Transfer-Encoding') or self.headers.get('Content-Type') != 'application/json':
                    raise JobError('INVALID_BODY', '文字请求须使用 JSON。', 400)
                try:
                    size = int(self.headers.get('Content-Length', '0'))
                    if not 0 < size <= 8192:
                        raise ValueError()
                    self.connection.settimeout(5)
                    raw = self.rfile.read(size)
                    if len(raw) != size:
                        raise ValueError()
                    body = strict_json(raw.decode('utf-8'))
                except (ValueError, UnicodeError, RecursionError):
                    raise JobError('INVALID_BODY', '文字请求为空、过长或格式无效。', 400)
                return self.json_response(self.language_service.recommend(body))
            if not self.task_store or not self.task_store.executor:
                raise JobError('SERVICE_NOT_CONNECTED', '真实推理默认关闭；本机预览不会上传或生成。', 503)
            if route == '/api/tasks':
                if self.headers.get('Transfer-Encoding'):
                    raise JobError('INVALID_BODY', '不接受分块传输。', 400)
                try:
                    size = int(self.headers.get('Content-Length', '0'))
                except ValueError:
                    raise JobError('INVALID_BODY', '图片大小无效。')
                if not 0 < size <= MAX_BYTES:
                    raise JobError('IMAGE_TOO_LARGE', '图片为空或超过 20 MB。', 413)
                encoded = self.headers.get('X-LightTry-Request', '')
                if len(encoded) > 4096:
                    raise JobError('INVALID_REQUEST', '任务元数据过长。')
                try:
                    metadata = json.loads(base64.b64decode(encoded, validate=True).decode('utf-8'))
                    if not isinstance(metadata, dict):
                        raise ValueError()
                except (ValueError, UnicodeError):
                    raise JobError('INVALID_REQUEST', '任务元数据无效。')
                self.connection.settimeout(10)
                data = self.rfile.read(size)
                if len(data) != size:
                    raise JobError('INVALID_BODY', '图片传输不完整。')
                task = self.task_store.submit(data, metadata, self.headers.get('Content-Type', ''))
                return self.json_response(task, 202)
            pieces = route.split('/')
            if len(pieces) == 5 and pieces[:3] == ['', 'api', 'tasks'] and pieces[4] == 'cancel':
                return self.json_response(self.task_store.cancel(pieces[3]))
            raise JobError('ROUTE_NOT_FOUND', '接口不存在。', 404)
        except (JobError, LanguageError) as error:
            return self.job_error(error)
        except (OSError, TimeoutError):
            return self.job_error(JobError('LOCAL_IO_ERROR', '本地读写失败或请求超时；请检查任务状态后重试。', 503))
        except Exception:
            return self.job_error(JobError('INTERNAL_ERROR', '本地服务异常；请检查任务状态与本地日志。', 500))

    def do_GET(self):
        if not self.valid_host():
            return self.job_error(JobError('INVALID_HOST', '只接受本机地址。', 403))
        route = urlsplit(self.path).path
        if route == '/api/language':
            return self.json_response(self.language_service.capabilities() if self.language_service else {
                'enabled': False, 'developmentTestMode': False, 'message': '文字服务未配置；仍可手动选择灯光。'})
        if route == '/api/inference':
            capabilities = self.task_store.capabilities() if self.task_store else {
                'enabled': False, 'developmentTestMode': False, 'cancelRunning': False,
                'message': '已载入，尚未连接推理服务'}
            return self.json_response({**capabilities, 'csrfToken': self.csrf_token})
        if route.startswith('/api/tasks/'):
            try:
                if not self.task_store:
                    raise JobError('TASK_NOT_FOUND', '任务不存在。', 404)
                pieces = route.split('/')
                if len(pieces) == 4:
                    return self.json_response(self.task_store.get(pieces[3]))
                if len(pieces) == 5:
                    payload, mime, filename = self.task_store.file(pieces[3], pieces[4])
                    return self.send_bytes(payload, mime, filename)
                if len(pieces) == 7 and pieces[4]=='presets':
                    payload, mime, filename = self.task_store.file(pieces[3],pieces[6],pieces[5])
                    return self.send_bytes(payload,mime,filename)
                raise JobError('TASK_NOT_FOUND', '任务不存在。', 404)
            except JobError as error:
                return self.job_error(error)
            except (OSError, ValueError):
                return self.job_error(JobError('STATE_UNAVAILABLE', '任务记录暂时不可读取；不会展示未核实结果。', 503))
        if route.startswith('/api/requests/'):
            try:
                if not self.task_store:
                    raise JobError('TASK_NOT_FOUND', '任务不存在。', 404)
                return self.json_response(self.task_store.by_request(route.removeprefix('/api/requests/')))
            except JobError as error:
                return self.job_error(error)
        if route == '/api/catalog':
            public = {k: v for k, v in self.catalog.items() if k not in ('assets', 'provenance')}
            return self.send_bytes(json.dumps(public, ensure_ascii=False).encode(), 'application/json; charset=utf-8')
        if route.startswith('/assets/'):
            key = route.removeprefix('/assets/')
            item = self.catalog['assets'].get(key)
            if not item:
                return self.send_error(404)
            return self.send_file(asset_path(self.assets_dir, item))
        if route.startswith('/download/'):
            pieces = route.split('/')
            if len(pieces) != 4:
                return self.send_error(404)
            sample = next((s for s in self.catalog['samples'] if s['id'] == pieces[2]), None)
            region = pieces[3].endswith('-region')
            preset_id = pieces[3].removesuffix('-region')
            preset = next((p for p in self.catalog['presets'] if p['id'] == preset_id), None)
            if not sample or not preset:
                return self.send_error(404)
            result = sample.get('regionResults' if region else 'results', {}).get(preset_id)
            if not result:
                return self.send_error(404)
            key = result['assetId']
            suffix = 'photo-region.png' if region else 'full.jpg'
            filename = f"{sample['name']}_{preset['name']}_AI光照预览_{suffix}"
            return self.send_file(asset_path(self.assets_dir, self.catalog['assets'][key]), filename)
        # Explicit allowlist prevents serving configs, history, sources or arbitrary paths.
        allowed = {'/': 'index.html', '/index.html': 'index.html', '/app.js': 'app.js', '/state.js': 'state.js',
                   '/sources.js': 'sources.js', '/plan.js': 'plan.js', '/styles.css': 'styles.css', '/favicon.svg': 'favicon.svg', '/about.html': 'about.html'}
        if route in allowed:
            return self.send_file(ROOT / 'web' / allowed[route])
        self.send_error(404)

    def send_file(self, path, filename=None):
        mime = 'text/javascript' if path.suffix == '.js' else mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
        self.send_bytes(path.read_bytes(), mime, filename)

    def send_bytes(self, payload, content_type, filename=None, status=200):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'self' blob:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        if filename:
            self.send_header('Content-Disposition', "attachment; filename=preview.jpg; filename*=UTF-8''" + quote(filename))
        self.end_headers()
        self.wfile.write(payload)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--assets-dir', help='独立素材目录；相对路径从 project/ 解析')
    parser.add_argument('--inference-config', help='显式指定本机推理配置；默认关闭')
    parser.add_argument('--language-service', action='store_true', help='显式读取文字服务环境配置；默认关闭，不自动调用')
    parser.add_argument('--tasks-dir', default='.tasks', help='本机私有任务目录；相对 project/ 解析')
    args = parser.parse_args()
    Handler.assets_dir = resolve_assets_dir(args.assets_dir)
    try:
        Handler.catalog = load_catalog(Handler.assets_dir)
        if args.language_service:
            Handler.language_service = LanguageAdapter.from_env(Handler.catalog['presets'])
        executor, timeout, retention = None, 1080, 86400
        if args.inference_config:
            config_path = Path(args.inference_config)
            if not config_path.is_absolute():
                config_path = ROOT / config_path
            config = json.loads(config_path.read_text(encoding='utf-8-sig'))
            if config.get('enabled') is True:
                import PIL
                from inference.executor import GuardedCosmosExecutor
                executor = GuardedCosmosExecutor(config_path)
            timeout, retention = int(config.get('timeout_seconds', timeout)), int(config.get('retention_seconds', retention))
            if not 10 <= timeout <= 1080 or not 60 <= retention <= 86400:
                raise ValueError('任务超时须在 10–1080 秒、结果保留须在 60–86400 秒内。')
        tasks_dir = Path(args.tasks_dir)
        Handler.task_store = TaskStore(tasks_dir if tasks_dir.is_absolute() else ROOT / tasks_dir,
                                      Handler.catalog['presets'], executor, timeout, retention)
    except (ValueError, OSError, KeyError, ImportError, JobError, LanguageError) as error:
        parser.exit(2, str(error) + '\n')
    with ThreadingHTTPServer(('127.0.0.1', args.port), Handler) as server:
        print(f'光照预览：http://127.0.0.1:{args.port} （仅本机；Ctrl+C 停止）', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            Handler.task_store.close()


if __name__ == '__main__':
    main()
