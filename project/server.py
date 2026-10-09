"""Loopback-only, read-only preview server. Python standard library only."""
import argparse
import hashlib
import json
import mimetypes
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, urlsplit

ROOT = Path(__file__).resolve().parent
INSTALL_HINT = ('请在代码根目录安装单独提供的 lighttry-demo-assets-20261009.zip：'
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

    def do_GET(self):
        route = urlsplit(self.path).path
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
            preset = next((p for p in self.catalog['presets'] if p['id'] == pieces[3]), None)
            if not sample or not preset:
                return self.send_error(404)
            key = sample['results'][preset['id']]['assetId']
            filename = f"{sample['name']}_{preset['name']}_AI光照预览.jpg"
            return self.send_file(asset_path(self.assets_dir, self.catalog['assets'][key]), filename)
        # Explicit allowlist prevents serving configs, history, sources or arbitrary paths.
        allowed = {'/': 'index.html', '/index.html': 'index.html', '/app.js': 'app.js', '/state.js': 'state.js',
                   '/sources.js': 'sources.js', '/styles.css': 'styles.css', '/favicon.svg': 'favicon.svg', '/about.html': 'about.html'}
        if route in allowed:
            return self.send_file(ROOT / 'web' / allowed[route])
        self.send_error(404)

    def send_file(self, path, filename=None):
        mime = 'text/javascript' if path.suffix == '.js' else mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
        self.send_bytes(path.read_bytes(), mime, filename)

    def send_bytes(self, payload, content_type, filename=None):
        self.send_response(200)
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
    args = parser.parse_args()
    Handler.assets_dir = resolve_assets_dir(args.assets_dir)
    try:
        Handler.catalog = load_catalog(Handler.assets_dir)
    except (ValueError, OSError) as error:
        parser.exit(2, str(error) + '\n')
    with ThreadingHTTPServer(('127.0.0.1', args.port), Handler) as server:
        print(f'光照预览：http://127.0.0.1:{args.port} （仅本机；Ctrl+C 停止）', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
