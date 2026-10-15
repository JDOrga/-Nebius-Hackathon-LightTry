"""Explicit local demonstration. No provider, model, GPU or cloud adapter."""
import copy
import io
import json
import re
import threading
from PIL import Image, ImageDraw, ImageEnhance, ImageOps

from inference.images import digest, decode
from inference.jobs import atomic, JobError
from scheme_store import SchemeStore
from recipe_language import RecipeLanguage
from language import LanguageError


class SimulationExecutor:
    supports_lighting_parameters = True

    def run_config(self):
        return {'simulation': True, 'model': 'OFFLINE_CPU_DEMO', 'upstreamCommit': None,
                'steps': 0, 'forwardModel': 'OFFLINE_CPU_DEMO', 'inverseModel': 'NONE',
                'weightVerification': 'not-applicable', 'weightContentHashesChecked': False,
                'execution': 'local CPU demonstration; no model processes'}

    def submit(self, folder, request):
        def event(status, stage, stopped=False, error=None):
            atomic(folder / 'execution.json', dict(taskId=request['taskId'], nonce=request['nonce'],
                status=status, stage=stage, executionStopped=stopped, simulation=True, error=error))
        def render():
            try:
                event('running', 'forward')
                # A labeled CPU illustration, never an approximation of Cosmos.
                image = Image.open(folder / 'inputs/photo.png').convert('RGB')
                image = ImageOps.fit(image, (1280, 704))
                params = request['preset']['parameters']
                image = ImageEnhance.Brightness(image).enhance(min(1.6, max(.4, params['strength'])))
                draw = ImageDraw.Draw(image)
                draw.rectangle((0, 0, 1280, 90), fill='#173e36')
                draw.text((24, 18), 'SIMULATION ONLY - CPU DEMO / NO MODEL / NO GPU', fill='white', font_size=28)
                draw.text((24, 58), 'Not a relighting result. Environment: '+str(params.get('environmentId')),
                          fill='white', font_size=20)
                out = io.BytesIO(); image.save(out, 'JPEG', quality=92)
                payload = out.getvalue()
                (folder / 'result.jpg').write_bytes(payload)
                receipt = {k: request[k] for k in ('taskId', 'nonce', 'runConfig')}
                receipt.update(inputId=request['input']['id'], presetId=request['preset']['id'],
                    inputSha256=request['input']['sha256'], originalSha256=request['original']['sha256'],
                    file='result.jpg', sha256=digest(payload), bytes=len(payload), simulation=True,
                    recipeKey=request['preset']['recipeKey'], parameters=copy.deepcopy(params))
                atomic(folder / 'receipt.json', receipt)
                event('succeeded', 'validating', True)
            except Exception:
                event('failed', 'forward', True, {'code':'SIMULATION_FAILED', 'message':'本地演示图生成失败。'})
        threading.Thread(target=render, daemon=True).start()


class SimulationStore(SchemeStore):
    def capabilities(self):
        return {**super().capabilities(), 'developmentTestMode': True,
                'message': '离线模拟；仅生成带水印的 CPU 演示图，不调用模型。'}

    def public(self, task):
        return {**super().public(task), 'simulation': True}

    def submit(self, data, metadata, mime, **kwargs):
        if 'lightingScheme' not in metadata or 'languageProposalId' in metadata:
            raise JobError('SIMULATION_SCHEME_REQUIRED', '模拟只接受手动或模拟建议产生的方案。', 422)
        return super().submit(data, metadata, mime, **kwargs)

    def _check_result(self, folder, task, receipt):
        # Separate offline receipt format: never manufacture model tensors or
        # successful GPU process exits to pass production evidence checks.
        preset = task['preset']
        expected = dict(taskId=task['taskId'], nonce=task['nonce'], inputId=task['input']['id'],
            presetId=preset['id'], inputSha256=task['input']['sha256'],
            originalSha256=task['original']['sha256'], runConfig=task['runConfig'],
            simulation=True, file='result.jpg', recipeKey=preset['recipeKey'], parameters=preset['parameters'])
        if any(receipt.get(k) != v for k, v in expected.items()) or 'processExitCodes' in receipt:
            raise ValueError('SIMULATION_RECEIPT_MISMATCH')
        path = folder / 'result.jpg'
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 20 * 1024 * 1024:
            raise ValueError('SIMULATION_RESULT_FILE_INVALID')
        payload = path.read_bytes()
        if digest(payload) != receipt['sha256'] or len(payload) != receipt['bytes']:
            raise ValueError('SIMULATION_RESULT_HASH_MISMATCH')
        rgb, _, _ = decode(payload, 'image/jpeg')
        if rgb.size != (1280, 704):
            raise ValueError('SIMULATION_RESULT_SIZE_MISMATCH')
        return dict(url=f"/api/tasks/{task['taskId']}/result", downloadUrl=f"/api/tasks/{task['taskId']}/download",
            width=1280, height=704, taskId=task['taskId'], inputId=task['input']['id'],
            presetId=preset['id'], sha256=receipt['sha256'], bytes=receipt['bytes'],
            recipeKey=preset['recipeKey'], parameters=copy.deepcopy(preset['parameters']), simulation=True,
            validation='offline simulation identity and image hash only; no model execution evidence',
            submittedPlan={'planId':preset['scheme']['planId'], 'version':preset['scheme']['version']})


def install(handler, tasks_dir):
    def script(payload, timeout):
        context = json.loads(payload['messages'][1]['content'])
        text = context['request']
        if '超时' in text:
            raise LanguageError('LANGUAGE_TIMEOUT', '本地脚本模拟超时；未调用模型。')
        params = copy.deepcopy(context['selectedScheme']['parameters'])
        if params.get('schemaVersion') != 2:
            params = {k: params[k] for k in ('environmentId', 'offsetDeg', 'strength')}
        if '为什么' in text or '解释' in text:
            return json.dumps(dict(status='explanation', action='revise', parameters=None, name='',
                reason='这是本地规则脚本；建议可用于演练操作，演示图不能判断真实重布光效果。', question=''), ensure_ascii=False)
        env = 'street' if any(w in text for w in ('夜', '街灯')) else 'sunrise' if any(w in text for w in ('晨', '粉')) else 'sunny'
        if params.get('mode') != 'procedural':
            params['environmentId'] = env
            if params.get('schemaVersion') == 2:
                params['environmentSha256'] = handler.task_store.environments[env]['sha256']
        if '暗' in text:
            params['strength'] = max(.25, params['strength'] * .7)
        elif '亮' in text:
            params['strength'] = min(4, params['strength'] * 1.4)
        angle = re.search(r'(?:旋转|转动)\s*(-?\d+(?:\.\d+)?)', text)
        if angle:
            params['offsetDeg'] = (params['offsetDeg'] + float(angle[1])) % 360
        return json.dumps(dict(status='ready', action='revise', parameters=params, name='',
            reason='本地模拟建议：按关键词调整方案；应用后可生成带模拟水印的演示图。', question=''), ensure_ascii=False)

    handler.task_store.close()
    handler.task_store = SimulationStore(tasks_dir, handler.catalog['presets'], SimulationExecutor(),
        lighting_capabilities=handler.lighting_capabilities)
    handler.recipe_language = RecipeLanguage(handler.catalog['presets'], handler.lighting_capabilities,
        'OFFLINE_SIMULATION_KEY', tasks_dir.parent / 'language-ledger.json', transport=script, max_calls=20)
