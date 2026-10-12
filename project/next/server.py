"""Local versioned-plan workbench; all real inference/language defaults remain OFF."""
import argparse
import json
from pathlib import Path
import sys
import re
from urllib.parse import urlsplit
from http.server import ThreadingHTTPServer

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
import server as legacy
from inference.jobs import JobError
from inference.images import digest
from inference.images import crop_photo_region
from next.store import SchemeStore
from next.evidence import load_evidence
from next.accepted import load_accepted, measured_context
from lighting import normalize_scheme
from light_console import EnvironmentLibrary, MAX_BYTES, normalize, synthesize, encode_hdr, decode_hdr, sha
import io
from PIL import Image
import numpy as np


class Handler(legacy.Handler):
    lighting_capabilities = None
    studies = []
    study_files = {}
    recipe_language = None
    imported_schemes = []

    def do_GET(self):
        if not self.valid_host():
            return self.job_error(JobError('INVALID_HOST', '只接受本机地址。', 403))
        route = urlsplit(self.path).path
        static = {'/': 'index.html', '/index.html': 'index.html',
                  '/workbench.js': 'workbench.js', '/scheme-state.js': 'scheme-state.js', '/chat.js': 'chat.js', '/console.js':'console.js', '/workbench.css': 'workbench.css'}
        if route in static:
            return self.send_file(Path(__file__).parent / 'web' / static[route])
        if route == '/api/accepted-results':
            return self.json_response({'schemes': self.imported_schemes, 'studies': [s for s in self.studies if s.get('recipeKey')]})
        if route == '/api/environments':
            return self.json_response({'environments':list(self.environment_library.environments.values())})
        if re.fullmatch(r'/api/environments/[a-f0-9]{64}/thumbnail',route):
            key=route.split('/')[3];e=next((e for e in self.environment_library.environments.values() if e['sha256']==key),None)
            if not e:return self.send_error(404)
            try:
                if e['source']['kind']=='local-import':
                    data=self.environment_library.safe_path(e['derivedSha256']+'.hdr').read_bytes();expected=e['derivedSha256']
                else:
                    data=(PROJECT.parent/'upstream/asset/examples/hdri_examples'/e['hdr']).read_bytes();expected=e['sha256']
                if digest(data)!=expected:return self.send_error(409)
                a=decode_hdr(data,max_value=1e12)
            except (ValueError,OSError):return self.send_error(422)
            a=a/(1+a);a=np.where(a<=.0031308,12.92*a,1.055*a**(1/2.4)-.055)
            image=Image.fromarray((np.clip(a,0,1)*255).astype('uint8'));image.thumbnail((256,128));out=io.BytesIO();image.save(out,format='PNG');return self.send_bytes(out.getvalue(),'image/png')
        if route == '/api/lighting':
            return self.json_response({'schemaVersion': 1, 'capabilities': self.lighting_capabilities,
                'studies': self.studies, 'importedSchemes': self.imported_schemes, 'textOnlyAI': True,
                'language': self.recipe_language.capabilities() if self.recipe_language else {'enabled': False, 'message': 'Nemotron 未启用；手动操作不收费。'}})
        if route.startswith('/sample-region/'):
            parts=route.strip('/').split('/')
            if len(parts)!=3:return self.send_error(404)
            sample=next((s for s in self.catalog['samples'] if s['id']==parts[1]),None)
            record=sample and (sample['input'] if parts[2]=='input' else sample['results'].get(parts[2]))
            if not record or not sample.get('canvas'):return self.send_error(404)
            data=legacy.asset_path(self.assets_dir,self.catalog['assets'][record['assetId']]).read_bytes()
            if digest(data)!=record['sha256']:return self.job_error(JobError('ASSET_CHANGED','历史素材校验失败。',409))
            cropped=crop_photo_region(data,sample['canvas'])
            return self.send_bytes(cropped,'image/png',parts[1]+'-'+parts[2]+'-region.png' if urlsplit(self.path).query=='download=1' else None)
        if route.startswith(('/study/', '/study-download/', '/study-region/', '/study-download-region/')):
            key = route.split('/')[-1]
            item = self.study_files.get(key)
            if item is None:
                return self.send_error(404)
            path, sha = item
            data = path.read_bytes()
            if digest(data) != sha:
                return self.job_error(JobError('STUDY_CHANGED', '实测图片校验失败；不显示旧图。', 409))
            if route.startswith(('/study-region/', '/study-download-region/')):
                entry = next(x for x in self.studies if x['result']['url'] == '/study/' + key)
                cropped = crop_photo_region(data, entry['canvas'])
                return self.send_bytes(cropped, 'image/png', key + '-region.png' if route.startswith('/study-download-region/') else None)
            return self.send_bytes(data, 'image/jpeg', key + '.jpg' if route.startswith('/study-download/') else None)
        return super().do_GET()

    def do_POST(self):
        route=urlsplit(self.path).path
        if route in ('/api/environments/import','/api/lighting/condition'):
            if not self.valid_host() or self.headers.get('X-LightTry-Token')!=self.csrf_token or self.headers.get('Origin') not in (None,'http://'+self.headers.get('Host','')):
                return self.job_error(JobError('INVALID_ORIGIN','仅接受当前本机应用。',403))
            try:
                size=int(self.headers.get('Content-Length','0'))
                limit=MAX_BYTES if route.endswith('import') else 8192
                if not 0<size<=limit or self.headers.get('Transfer-Encoding'):raise ValueError('REQUEST_SIZE_INVALID')
                self.connection.settimeout(10);data=self.rfile.read(size)
                if len(data)!=size:raise ValueError('REQUEST_TRUNCATED')
                if route.endswith('import'):
                    if self.headers.get('Content-Type')!='application/octet-stream':raise ValueError('HDR_BYTES_REQUIRED')
                    name=__import__('urllib.parse',fromlist=['unquote']).unquote(self.headers.get('X-Environment-Name','本机环境'))
                    value=self.environment_library.import_bytes(data,name)
                    self.task_store.environments[value['id']]=value
                    if self.recipe_language:self.recipe_language.environments[value['id']]=value
                    return self.json_response(value)
                if self.headers.get('Content-Type')!='application/json':raise ValueError('JSON_REQUIRED')
                recipe=normalize(legacy.strict_json(data.decode('utf-8')),self.environment_library.environments)
                derived=self.environment_library.derived(recipe)
                if derived is None:return self.json_response({'recipe':recipe,'status':'bundled-environment','modelExecuted':False})
                a=decode_hdr(derived);from light_console import loaded_latlong
                a=loaded_latlong(a,recipe['offsetDeg'],recipe['strength'])
                return self.json_response({'recipe':recipe,'derivedHdrSha256':digest(derived),'loadedLatlongSha256':digest(a.tobytes()),'shape':list(a.shape),'min':float(a.min()),'max':float(a.max()),'modelExecuted':False,'status':'CPU HDR validated; model projection pending'})
            except (ValueError,KeyError,TypeError,UnicodeError,OSError) as e:return self.job_error(JobError('LIGHTING_INVALID',str(e),422))
        recovery=re.fullmatch(r'/api/tasks/([a-f0-9]{32})/recover-transferred',urlsplit(self.path).path)
        if recovery:
            if (not self.valid_host() or self.headers.get('X-LightTry-Token')!=self.csrf_token or self.headers.get('Origin') not in (None,'http://'+self.headers.get('Host',''))):
                return self.job_error(JobError('INVALID_ORIGIN','仅接受当前本机应用提交。',403))
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=1024 or self.headers.get('Transfer-Encoding') or self.headers.get('Content-Type')!='application/json':raise ValueError()
                self.connection.settimeout(5);body=legacy.strict_json(self.rfile.read(size).decode('utf-8'))
                if set(body)!={'recoveryGuardRunId'}:raise ValueError()
                return self.json_response(self.task_store.recover_transferred_result(recovery[1],body['recoveryGuardRunId']))
            except JobError as e:return self.job_error(e)
            except (ValueError,KeyError,TypeError,OSError):return self.job_error(JobError('RECOVERY_INVALID','恢复数据缺失或无效。',422))
        if urlsplit(self.path).path == '/api/lighting/recommend':
            if (not self.valid_host() or self.headers.get('X-LightTry-Token') != self.csrf_token or
                    self.headers.get('Origin') not in (None, 'http://' + self.headers.get('Host', ''))):
                return self.job_error(JobError('INVALID_ORIGIN', '请从当前本机应用提交。', 403))
            try:
                if self.recipe_language is None: raise legacy.LanguageError('LANGUAGE_NOT_CONFIGURED','Nemotron 未启用。',503)
                size=int(self.headers.get('Content-Length','0'))
                if size>8192:raise legacy.LanguageError('CONTEXT_TOO_LONG','文字上下文超过8KiB，请缩短历史或当前需求。',400)
                if not 0<size<=8192 or self.headers.get('Transfer-Encoding') or self.headers.get('Content-Type')!='application/json':raise ValueError()
                self.connection.settimeout(5);raw=self.rfile.read(size)
                if len(raw)!=size:raise ValueError()
                body=legacy.strict_json(raw.decode('utf-8'))
                return self.json_response(self.recipe_language.recommend(body))
            except legacy.LanguageError as e:return self.job_error(e)
            except (ValueError,KeyError,TypeError,UnicodeError,RecursionError):return self.job_error(JobError('INVALID_LANGUAGE_REQUEST','文字方案请求无效。',400))
        if urlsplit(self.path).path == '/api/lighting/normalize':
            if (not self.valid_host() or self.headers.get('X-LightTry-Token') != self.csrf_token or
                    self.headers.get('Origin') not in (None, 'http://' + self.headers.get('Host', ''))):
                return self.job_error(JobError('INVALID_ORIGIN', '请从当前本机应用提交。', 403))
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 8192 or self.headers.get('Content-Type') != 'application/json':
                    raise ValueError()
                self.connection.settimeout(5)
                if self.headers.get('Transfer-Encoding'): raise ValueError()
                raw = self.rfile.read(size)
                if len(raw) != size: raise ValueError()
                body = legacy.strict_json(raw.decode('utf-8'))
                value = normalize_scheme(body, self.environment_library.environments, self.lighting_capabilities)
                return self.json_response(value)
            except (ValueError, KeyError, TypeError, UnicodeError, RecursionError):
                return self.job_error(JobError('INVALID_LIGHTING_SCHEME', '参数、版本或组合未通过校验。', 422))
        return super().do_POST()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--port', type=int, default=8785)
    p.add_argument('--assets-dir', required=True)
    p.add_argument('--evidence-config', type=Path)
    p.add_argument('--accepted-package', type=Path)
    p.add_argument('--tasks-dir', type=Path, default=PROJECT.parent / '.local/lighttry-development-20261011/workbench-tasks')
    p.add_argument('--inference-config', type=Path)
    p.add_argument('--language-key-file', type=Path, help='程序直接读取本机 Key 文件；不显示、不入库。仅显式使用时启用。')
    p.add_argument('--language-ledger', type=Path, help='本轮独立账本；不复用旧文字预算。')
    p.add_argument('--language-max-calls', type=int, default=12)
    p.add_argument('--language-budget', type=float, default=.20)
    a = p.parse_args()
    Handler.assets_dir = legacy.resolve_assets_dir(a.assets_dir)
    Handler.catalog = legacy.load_catalog(Handler.assets_dir)
    Handler.lighting_capabilities, Handler.studies, Handler.study_files = load_evidence(a.evidence_config)
    accepted, accepted_files, Handler.imported_schemes = load_accepted(a.accepted_package, Handler.catalog)
    Handler.studies.extend(accepted); Handler.study_files.update(accepted_files)
    Handler.lighting_capabilities={**Handler.lighting_capabilities,'parameterized':True,'legacyRevision':Handler.lighting_capabilities['revision'],'revision':'parameterized-engineering-v2','experimental':True}
    Handler.environment_library=EnvironmentLibrary(a.tasks_dir.parent/'environments-v2',Handler.catalog['presets'])
    if a.language_key_file:
        if not a.language_ledger: raise ValueError('NEW_LANGUAGE_LEDGER_REQUIRED')
        key=a.language_key_file.read_text(encoding='utf-8-sig').strip()
        if not key.isascii() or not 20<=len(key)<=4096 or any(c.isspace() for c in key):raise ValueError('KEY_FILE_FORMAT_INVALID_NO_REQUEST')
        from next.language import RecipeLanguage
        Handler.recipe_language=RecipeLanguage(Handler.catalog['presets'],Handler.lighting_capabilities,key,a.language_ledger,
            max_calls=a.language_max_calls,budget=a.language_budget, measured_cases=measured_context(accepted))
    executor = None
    if a.inference_config:
        # A separate reviewed parameter adapter is required, never the old driver
        # that would accept a field and silently ignore it.
        from next.runtime.executor import SchemeExecutor
        executor = SchemeExecutor(a.inference_config)
    Handler.task_store = SchemeStore(a.tasks_dir, Handler.catalog['presets'], executor,
                                    lighting_capabilities=Handler.lighting_capabilities,
                                    approved_language_operation=Handler.recipe_language.approved_operation if Handler.recipe_language else None)
    Handler.task_store.environment_library=Handler.environment_library
    Handler.task_store.environments.update(Handler.environment_library.environments)
    with ThreadingHTTPServer(('127.0.0.1', a.port), Handler) as http:
        print('LightTry 方案工作台：http://127.0.0.1:' + str(a.port), flush=True)
        try: http.serve_forever()
        except KeyboardInterrupt: pass
        finally: Handler.task_store.close()


if __name__ == '__main__': main()
