"""Loopback-only, read-only preview server. Python standard library only."""
import argparse
import hashlib
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, urlsplit

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent


def load_catalog():
    data = json.loads((ROOT / 'data/catalog.json').read_text(encoding='utf-8'))
    for item in data['assets'].values():
        path = (REPO / item['path']).resolve()
        if not path.is_relative_to(REPO) or not path.is_file():
            raise ValueError('样例素材不存在或路径越界：' + item['path'])
        with path.open('rb') as f:
            if hashlib.file_digest(f, 'sha256').hexdigest() != item['sha256']:
                raise ValueError('样例素材校验失败：' + item['path'])
    return data


class Handler(BaseHTTPRequestHandler):
    catalog = None

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
            return self.send_file(REPO / item['path'])
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
            return self.send_file(REPO / self.catalog['assets'][key]['path'], filename)
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
    args = parser.parse_args()
    Handler.catalog = load_catalog()
    with ThreadingHTTPServer(('127.0.0.1', args.port), Handler) as server:
        print(f'光照预览：http://127.0.0.1:{args.port} （仅本机；Ctrl+C 停止）', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
