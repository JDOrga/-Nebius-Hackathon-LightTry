"""Deployment WSGI entry, served by Waitress; shares the existing business handlers."""
import argparse
import base64
import copy
import time
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
import threading
from types import SimpleNamespace
from urllib.parse import urlsplit, parse_qs
from http.cookies import SimpleCookie
from ui_locale import resolve_locale,error_message,gpu_info

import studio
from inference.jobs import ID, JobError
from inference.images import MAX_BYTES
from persistence import Workspace
from security import Accounts, RateLimiter, ProviderSecrets, create_temporary_account, LoginSessions, runtime_file
from gpu_queue import GPUQueue
from gpu_bootstrap import load_control

ROOT = Path(__file__).resolve().parent.parent
LOG = logging.getLogger('lighttry.service')


def wsgi_response_headers(headers):
    """Transport headers belong to the WSGI server, including Connection-nominated fields."""
    blocked={'connection','keep-alive','proxy-authenticate','proxy-authorization',
             'te','trailer','transfer-encoding','upgrade','proxy-connection'}
    for name,value in headers:
        if name.lower()=='connection':blocked.update(token.strip().lower() for token in value.split(','))
    return [(name,value) for name,value in headers if name.lower() not in blocked]


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
        self.accounts = Accounts(options.accounts_file, ROOT, os.environ.get('LIGHTTRY_ACCESS_KEY') or os.environ.get('LIGHTTRY_ACCESS_PASSWORD'))
        scoped=getattr(options,'session_scoped_accounts',()) or ()
        if (not isinstance(scoped,(list,tuple)) or any(
                not isinstance(name,str) or name not in self.accounts.users or
                self.accounts.users[name]['role']!='user' for name in scoped)):
            raise ValueError('EXPLICIT_BROWSER_SCOPED_USER_REQUIRED')
        self.session_scoped_accounts=frozenset(scoped)
        self.login_sessions = LoginSessions(self.accounts)
        self.login_slots = threading.BoundedSemaphore(2)
        self.provider_secrets = ProviderSecrets(ROOT)
        self.upload_slots = threading.BoundedSemaphore(2)
        self.gpu_sessions=None
        self.presence_stop=threading.Event()
        self.presence_slots=threading.BoundedSemaphore(8)
        self.entry_lock=threading.Lock()
        self.entry_start=None
        self.entry_thread=None
        self.gpu_scope=None  # Only trusted server bootstrap may install a new scope; never browser fields.
        self.gpu_control=load_control(getattr(options,'gpu_control_config',None),ROOT)
        if self.gpu_control:
            self.gpu_sessions=self.gpu_control.sessions
            self.gpu_scope=self.gpu_control.scope
        data = Path(options.data_root).expanduser()
        if not data.is_absolute() or data.resolve().is_relative_to(ROOT.resolve()):
            raise ValueError('DATA_ROOT_MUST_BE_ABSOLUTE_AND_OUTSIDE_CODE')
        if any(p.is_symlink() for p in (data, *data.parents)):
            raise ValueError('DATA_ROOT_SYMLINK_FORBIDDEN')
        for name in ('photos', 'tasks', 'environments-v2', 'inverse-cache', 'logs', 'tmp', 'workspace.sqlite3', 'queue', 'auth'):
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
        self.previous_tempdir=tempfile.tempdir
        self.runtime_tmp=str(data/'tmp')
        tempfile.tempdir = self.runtime_tmp
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

        task_root=data/'tasks'
        if getattr(options,'local_task_root',None) is not None:
            if getattr(options,'local_loopback',False) is not True or parsed.hostname!='127.0.0.1':
                raise ValueError('LOCAL_TASK_PATH_OVERRIDE_REQUIRES_LOOPBACK_PROFILE')
            task_root=Path(options.local_task_root)
            if not task_root.is_absolute() or any(p.is_symlink() for p in (task_root,*task_root.parents)):
                raise ValueError('LOCAL_TASK_PATH_UNSAFE')
        args = SimpleNamespace(assets_dir=str(assets), tasks_dir=task_root,
                               evidence_config=options.evidence_config,
                               accepted_package=options.accepted_package, no_demo=not options.assets_dir,
                               language_key_file=None, inference_config=None)
        self.handler = studio.configure(args, DeploymentHandler)
        # Long-lived storage by default; historical expiry/deadlines remain untouched.
        self.handler.task_store.retention = 100 * 365 * 86400
        try:
            self.workspace = Workspace(data, self.handler.environment_library.environments,
                                       self.handler.lighting_capabilities,default_owner=os.environ.get('LIGHTTRY_LEGACY_OWNER','lighttry'))
        except Exception:
            self.handler.task_store.close()
            raise
        migration_owner = os.environ.get('LIGHTTRY_LEGACY_OWNER', 'lighttry')
        if migration_owner not in self.accounts.users:
            self.handler.task_store.close(); raise ValueError('EXPLICIT_LEGACY_OWNER_ACCOUNT_REQUIRED')
        self.workspace.bind_legacy(migration_owner,self.handler.task_store.root,self.handler.environment_library)
        self.limiter=RateLimiter(self.workspace)
        self.model_executor=None
        if getattr(options,'model_grant_file',None):
            if not self.gpu_control:
                self.handler.task_store.close();raise ValueError('GPU_CONTROL_REQUIRED_FOR_MODEL_GRANT')
            from https_executor import HTTPSCosmosExecutor
            self.model_executor=HTTPSCosmosExecutor(self.gpu_control,options.model_grant_file,self.handler.task_store.root)
            self.handler.task_store.executor=self.model_executor
        self.queue=GPUQueue(self.workspace,self.handler.task_store)
        logs = RotatingFileHandler(data / 'logs/service.log', maxBytes=2 * 1024 * 1024, backupCount=3, encoding='utf-8')
        logs.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
        self.log_handler = logs
        LOG.addHandler(logs); LOG.setLevel(logging.INFO)
        LOG.info('service initialized; GPU control binding=%s; model adapter=%s',bool(self.gpu_control),bool(self.model_executor))
        self.operator_recipe_language=None
        text_config=getattr(options,'language_config',None)
        if text_config:
            try:self.configure_role_language(text_config)
            except Exception:
                self.close()
                raise

    def close(self):
        self.presence_stop.set()
        if self.gpu_control:self.gpu_control.close()
        self.queue.close()
        if self.model_executor:self.model_executor.close()
        self.handler.task_store.close()
        LOG.info('service stopped')
        LOG.removeHandler(self.log_handler); self.log_handler.close()
        if tempfile.tempdir==self.runtime_tmp:tempfile.tempdir=self.previous_tempdir

    def session_token(self, environ):
        raw = environ.get('HTTP_COOKIE', '')
        if len(raw) > 8192:
            return ''
        try:
            cookie = SimpleCookie(); cookie.load(raw)
            return cookie['lighttry_session'].value if 'lighttry_session' in cookie else ''
        except Exception:
            return ''

    def browser_token(self, environ):
        raw=environ.get('HTTP_COOKIE','')
        if len(raw)>8192:return ''
        try:
            cookie=SimpleCookie();cookie.load(raw)
            return cookie['lighttry_space'].value if 'lighttry_space' in cookie else ''
        except Exception:return ''

    def authorized(self, environ):
        # Basic authentication is deliberately no longer accepted.
        return self.login_sessions.authenticate(self.session_token(environ))

    def is_operator(self, owner):
        return bool(owner and self.accounts.users[owner]['role']=='operator')

    def language_for(self, owner, owner_scope=None):
        if self.is_operator(owner) and self.operator_recipe_language is not None:
            return self.operator_recipe_language
        return self.handler.recipe_language

    def configure_role_language(self, text_config):
        """Only explicit private policy plus a server-side key enables paid text."""
        from recipe_language import RecipeLanguage
        from studio import measured_context
        cfg=json.loads(runtime_file(text_config,ROOT).decode('utf-8'))
        legacy=set(cfg)=={'schemaVersion','ledgerFile','maxCalls','budgetUsd'} and cfg['schemaVersion']==1
        tiered=set(cfg)=={'schemaVersion','user','operator'} and cfg['schemaVersion']==2
        if not (legacy or tiered):raise ValueError('EXPLICIT_LOCAL_TEXT_SCOPE_REQUIRED')
        key=self.provider_secrets.get('nemotron').lstrip('\ufeff')
        if not key.isascii() or not 20<=len(key)<=4096 or any(c.isspace() for c in key):
            raise ValueError('KEY_FILE_FORMAT_INVALID_NO_REQUEST')
        def private_ledger(raw):
            ledger=Path(raw)
            if (not ledger.is_absolute() or ledger.resolve().is_relative_to(ROOT.resolve())
                    or any(p.is_symlink() for p in (ledger,*ledger.parents))):
                raise ValueError('PRIVATE_TEXT_LEDGER_REQUIRED')
            return ledger
        measured=measured_context(self.handler.studies)
        if legacy:
            self.handler.recipe_language=RecipeLanguage(self.handler.catalog['presets'],
                self.handler.lighting_capabilities,key,private_ledger(cfg['ledgerFile']),
                max_calls=cfg['maxCalls'],budget=cfg['budgetUsd'],repair_limit=0,measured_cases=measured)
            self.handler.task_store.approved_language_operation=self.handler.recipe_language.approved_operation
            return
        user,operator=cfg['user'],cfg['operator']
        bounded_user=isinstance(user,dict) and set(user)=={'ledgerFile','maxCalls','budgetUsd'}
        unlimited_user=(isinstance(user,dict) and set(user)=={'ledgerFile','unbounded','ownerAcceptsUnboundedCost'} and
            user['unbounded'] is True and user['ownerAcceptsUnboundedCost'] is True)
        if ((user is not None and not (bounded_user or unlimited_user)) or
                not isinstance(operator,dict) or set(operator)!={'ledgerFile','unbounded','operatorAcceptsUnboundedCost'} or
                operator['unbounded'] is not True or operator['operatorAcceptsUnboundedCost'] is not True):
            raise ValueError('EXPLICIT_ROLE_TEXT_POLICY_REQUIRED')
        operator_ledger=private_ledger(operator['ledgerFile'])
        user_ledger=private_ledger(user['ledgerFile']) if user is not None else None
        if user_ledger is not None and user_ledger.resolve()==operator_ledger.resolve():
            raise ValueError('ROLE_TEXT_LEDGERS_MUST_DIFFER')
        self.handler.recipe_language=(RecipeLanguage(self.handler.catalog['presets'],
            self.handler.lighting_capabilities,key,user_ledger,
            max_calls=None if unlimited_user else user['maxCalls'],
            budget=None if unlimited_user else user['budgetUsd'],repair_limit=0,
            measured_cases=measured,unbounded=unlimited_user,ledger_scope='user')
            if user is not None else None)
        self.operator_recipe_language=RecipeLanguage(self.handler.catalog['presets'],
            self.handler.lighting_capabilities,key,operator_ledger,max_calls=None,budget=None,
            repair_limit=0,measured_cases=measured,unbounded=True,ledger_scope='operator')
        from language import LanguageError
        def verify_operation(operation_id,input_id,parameters):
            for language in (self.handler.recipe_language,self.operator_recipe_language):
                if language is None:continue
                try:return language.approved_operation(operation_id,input_id,parameters)
                except LanguageError as error:
                    if error.code!='INVALID_LANGUAGE_PROVENANCE':raise
            raise LanguageError('INVALID_LANGUAGE_PROVENANCE','该建议未被正式服务接受。',422)
        self.handler.task_store.approved_language_operation=verify_operation

    def session_cookie(self, token, seconds):
        secure = '; Secure' if self.origin.startswith('https://') else ''
        return ('lighttry_session=' + token + '; Path=/; Max-Age=' + str(seconds) +
                '; HttpOnly; SameSite=Strict' + secure)

    def browser_cookie(self, token):
        secure='; Secure' if self.origin.startswith('https://') else ''
        return 'lighttry_space='+token+'; Path=/; Max-Age=31536000; HttpOnly; SameSite=Strict'+secure

    def login_page(self, h, status=200, failed=False):
        message = ('Invalid or expired access key. Please try again.' if failed else
                   'Enter your access key to continue creating with light.') if h.ui_locale=='en' else (
                   '访问密钥无效或已过期，请重新输入。' if failed else '输入访问密钥，继续你的光照创作。')
        html = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>登录 · LightTry</title><style>
:root{font:14px/1.6 "Segoe UI","Microsoft YaHei",sans-serif;color:#294738;background:#f2f6f3}*{box-sizing:border-box}body{margin:0;min-height:100dvh;display:grid;place-items:center;padding:24px;background:radial-gradient(ellipse at top right,#dcebe1,transparent 65%)}main{width:min(420px,100%);background:white;border:1px solid #dce7df;border-radius:22px;padding:38px;box-shadow:0 15px 60px #294d3210}.brand{font-size:26px;font-weight:750;letter-spacing:-1px}h1{font-size:21px;margin:28px 0 8px}p{font-size:13px;color:#75897b;margin:0 0 26px}label{display:block;font-size:12px;font-weight:650;margin:0 0 8px}input,button{font:inherit;width:100%;border-radius:10px;padding:12px 14px}input{border:1px solid #c9d9ce;background:#f8fbf9;color:#294738}input:focus-visible,button:focus-visible{outline:3px solid #67a48080;outline-offset:3px}button{border:0;background:#286d4e;color:white;font-weight:650;margin-top:18px;cursor:pointer}button:hover{background:#20573f}.privacy{font-size:11px;margin:20px 0 0;color:#8d9d92}</style><main><div class="brand">LightTry</div><h1>访问工作室</h1><p role="status">MESSAGE</p><form action="/auth/login" method="post"><label for="access-key">访问密钥</label><input id="access-key" name="accessKey" type="password" autocomplete="current-password" minlength="24" maxlength="256" required placeholder="输入你的访问密钥"><button type="submit">进入工作室</button></form><p class="privacy">请妥善保管密钥，不要分享给他人。</p></main></html>'''
        html=html.replace('</style><main>','.languages{display:flex;justify-content:flex-end;gap:12px;font-size:12px}.languages a{color:#286d4e}</style><main>')
        html=html.replace('<div class="brand">LightTry</div>','<nav class="languages" aria-label="Language"><a href="/lang/zh">中文</a><a href="/lang/en">English</a></nav><div class="brand">LightTry</div>')
        if h.ui_locale=='en':
            for source,target in (('lang="zh-CN"','lang="en"'),('登录 · LightTry','Sign in · LightTry'),
                    ('访问工作室','Enter the studio'),('输入你的访问密钥','Enter your access key'),
                    ('访问密钥','Access key'),('进入工作室','Enter studio'),
                    ('请妥善保管密钥，不要分享给他人。','Keep this key private. Do not share it.')):
                html=html.replace(source,target)
        h.send_bytes(html.replace('MESSAGE', message).encode('utf-8'), 'text/html; charset=utf-8', status=status)

    def login_route(self, h, environ):
        path = urlsplit(h.path).path
        if path in ('/lang/zh','/lang/en') and h.command=='GET':
            language=path.rsplit('/',1)[-1]
            secure='; Secure' if self.origin.startswith('https://') else ''
            h.ui_locale=language
            h.send_response(303);h.send_header('Location','/' if h.user else '/login')
            h.send_header('Set-Cookie','lighttry_lang='+language+'; Path=/; Max-Age=31536000; SameSite=Lax'+secure)
            h.end_headers();return True
        if path == '/login' and h.command == 'GET':
            self.login_page(h)
            return True
        if path == '/auth/login' and h.command == 'POST':
            if h.headers.get('Origin') != self.origin:
                raise JobError('INVALID_ORIGIN', '请从本站登录页面提交。', 403)
            self.limiter.consume('login', environ.get('REMOTE_ADDR','unknown'))
            if h.headers.get_content_type() != 'application/x-www-form-urlencoded':
                raise JobError('INVALID_BODY', '登录内容格式不正确。', 400)
            body = self.body(h, 4096)
            try:
                values = parse_qs(body.decode('utf-8'), strict_parsing=True, max_num_fields=2)
                if set(values) != {'accessKey'} or len(values['accessKey']) != 1:
                    raise ValueError()
                key = values['accessKey'][0]
            except (ValueError, UnicodeError):
                raise JobError('INVALID_BODY', '请重新输入访问密钥。', 400)
            if not self.login_slots.acquire(blocking=False):
                raise JobError('LOGIN_BUSY', '登录服务繁忙，请稍后重试。', 429)
            try:
                owner = self.accounts.authenticate_key(key)
            finally:
                self.login_slots.release()
            if not owner:
                self.login_page(h, 401, failed=True)
                return True
            self.login_sessions.revoke(self.session_token(environ))
            token, seconds = self.login_sessions.issue(owner)
            space=(self.workspace.issue_browser_space(owner,self.accounts.users[owner]['hash'],
                self.browser_token(environ)) if owner in self.session_scoped_accounts else None)
            h.send_response(303); h.send_header('Location', self.gpu_login_destination())
            if space:h.send_header('Set-Cookie',self.browser_cookie(space))
            h.send_header('Set-Cookie', self.session_cookie(token, seconds)); h.end_headers()
            return True
        return False

    def gpu_entry_info(self, owner=None, owner_scope=None):
        # Consume the guard's local snapshot only: never add a cloud poll on login.
        snapshot = {}
        if self.gpu_sessions:
            try:
                snapshot = self.gpu_sessions.latest()
            except Exception:
                snapshot = {}
        if not isinstance(snapshot,dict):
            snapshot={}
        observed = snapshot.get('lastObservedAt')
        fresh = (isinstance(observed,(int,float)) and not isinstance(observed,bool) and
                 -5 <= time.time()-observed <= 60)
        state = snapshot.get('state') if fresh else 'UNKNOWN'
        active = state in ('STARTING','LOADING','READY','EXECUTING')
        scope = self.gpu_scope
        issuer=getattr(getattr(self,'gpu_control',None),'scope_issuer',None)
        current_scope_ok=bool(scope and scope.get('budgetApproved') is True and scope.get('expiresAt',0)>time.time())
        if issuer:
            try:issuer.limits();current_scope_ok=True
            except ValueError:current_scope_ok=False
        allowed = bool(owner and
                       self.gpu_sessions and scope and current_scope_ok and state=='STOPPED' and
                       snapshot.get('verifiedStopped') is True)
        reason = ''
        if not self.gpu_sessions or not scope:
            reason = 'GPU 启动服务暂不可用，可以先进入工作台。'
        elif state=='UNKNOWN':
            reason = '暂时无法确认 GPU 状态，可以先进入工作台。'
        elif state=='STOPPING':
            reason = 'GPU 正在关闭，请稍后再启动。'
        elif not allowed and not active:
            reason = 'GPU 暂不具备安全启动条件，可以先进入工作台。'
        with self.entry_lock:
            pending = dict(self.entry_start) if self.entry_start else None
        if pending and (not scope or pending['scopeId']!=scope.get('scopeId')):
            pending=None
        if issuer and pending and snapshot.get('sessionId') and snapshot.get('verifiedStopped') and snapshot.get('scopeId')==pending['scopeId']:
            pending=None
        if pending and not active:
            allowed=False
            reason=('启动请求已提交，请等待状态更新。' if pending['status']=='requested' else '上次启动未成功，请联系管理员核实。')
        bootstrap=getattr(getattr(self,'gpu_control',None),'bootstrap',None)
        enrollment=bootstrap.public(snapshot) if bootstrap else {'stage':'not_configured','canConfirm':False}
        auto_trust=bool(getattr(getattr(self,'gpu_control',None),'auto_host_trust',False))
        if auto_trust:
            enrollment={**enrollment,'canConfirm':False,'automatic':True}
        from gpu_monitoring import public_failure
        diagnostic=public_failure(snapshot,enrollment,fresh) if self.gpu_sessions else None
        if diagnostic:
            reason=diagnostic['title']+'：'+diagnostic['detail']+' '+diagnostic['cost']+' '+diagnostic['action']
            enrollment['canConfirm']=False if diagnostic['active'] else enrollment.get('canConfirm',False)
            if diagnostic['active']:allowed=False
        operator=bool(owner and self.accounts.users[owner]['role']=='operator')
        if not operator:enrollment['canConfirm']=False
        if state=='LOADING' and bootstrap and not diagnostic:
            reason={'awaiting_host_confirmation':'正在自动绑定本次服务器连接。' if auto_trust else '请先核对并确认本次服务器连接。','waiting_authorization':'正在等待本次模型授权。',
                    'deploying':'正在连接模型服务。','deployed':'服务器已连接，正在加载模型。',
                    'uncertain':'服务器连接未确认，请先停止并核查。'}.get(enrollment['stage'],'正在准备服务器连接。')
        # Stop binds to the latest durable session/resource, not the Web's
        # possibly older start scope. Expired start approval cannot block release.
        stop_base=bool(owner and scope and snapshot.get('sessionId') and
                      snapshot.get('resourceId')==scope.get('resourceId') and not snapshot.get('verifiedStopped') and not snapshot.get('stopSent'))
        stop_blocked=bool(stop_base and not operator and self.queue.foreign_in_flight(owner_scope or owner))
        can_stop=bool(stop_base and not stop_blocked)
        from gpu_monitoring import public_monitor
        return {'active':active,'state':state,'canStart':allowed,'canStop':can_stop,
                'stopBlockedByOtherTasks':stop_blocked,'hostConfirmation':enrollment,'diagnostic':diagnostic,
                'monitor':public_monitor(snapshot,fresh,time.time()),
                'sessionId':snapshot.get('sessionId'),'message':reason,'simulation':snapshot.get('simulation') is True,
                'configured':self.gpu_sessions is not None,'canGenerate':bool(fresh and state=='READY' and not (diagnostic and diagnostic['active'])),
                'observedAt':observed if isinstance(observed,(int,float)) and not isinstance(observed,bool) else None,'stale':bool(observed is not None and not fresh),
                  'serverNow':time.time(),
                'startStatus':pending.get('status') if pending else None,
                'protectionMode':getattr(self.gpu_sessions,'protection_mode',None),
                'hostLossProtected':False if getattr(self.gpu_sessions,'protection_mode',None)=='cpu-only' else None}

    def gpu_login_destination(self):
        return '/' if self.gpu_entry_info()['active'] else '/gpu-entry'

    def gpu_entry_page(self, h):
        info=self.gpu_entry_info(h.user,h.owner_scope)
        if info['active']:
            h.send_response(303);h.send_header('Location','/');h.end_headers();return
        title='GPU 尚未启动' if info['state']=='STOPPED' else '进入工作台前'
        intro='现在启动 GPU，为接下来的图片生成做准备？' if info['state']=='STOPPED' else '暂时无法确认 GPU 可用状态，你仍可以进入工作台编辑方案。'
        if h.ui_locale=='en':
            title='GPU not started' if info['state']=='STOPPED' else 'Before entering the workbench'
            intro=('Start the GPU now to prepare for image generation?' if info['state']=='STOPPED' else
                   'GPU availability cannot be confirmed yet. You can still edit plans in the workbench.')
        disabled='' if info['canStart'] else ' disabled'
        html='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>准备工作台 · LightTry</title><style>
:root{font:14px/1.7 "Segoe UI","Microsoft YaHei",sans-serif;color:#294738;background:#f2f6f3}*{box-sizing:border-box}body{margin:0;min-height:100dvh;display:grid;place-items:center;padding:24px;background:radial-gradient(ellipse at top right,#dcebe1,transparent 65%)}main{width:min(470px,100%);background:white;border:1px solid #dce7df;border-radius:22px;padding:38px;box-shadow:0 15px 60px #294d3210}.brand{font-size:26px;font-weight:750;letter-spacing:-1px}h1{font-size:23px;margin:26px 0 10px}p{font-size:13px;color:#75897b;margin:0 0 22px}.actions{display:grid;gap:10px}button,a{font:inherit;border-radius:10px;padding:12px 14px;text-align:center;font-weight:650}button{border:1px solid #286d4e;background:#286d4e;color:white;cursor:pointer}button:hover:not(:disabled){background:#20573f}button:disabled{background:#e7eee9;border-color:#d9e3dc;color:#91a194;cursor:not-allowed}a{border:1px solid #cdded2;text-decoration:none;color:#426c51;background:#f8fbf9}a:hover{background:#edf4ef}:focus-visible{outline:3px solid #67a48080;outline-offset:3px}.note{font-size:11px;margin:20px 0 0;color:#879a8c}</style><main id="gpu-entry" data-token="TOKEN"><div class="brand">LightTry</div><h1>TITLE</h1><p>INTRO</p><div class="actions"><button id="start-gpu"DISABLED>启动 GPU 并进入工作台</button><a href="/">暂不启动，直接进入</a></div><p class="note">启动 GPU 可能产生费用。提交后立即进入工作台，无需等待启动完成。</p><p class="note" role="status">REASON</p></main><script type="module" src="/gpu-entry.js"></script></html>'''
        if info['simulation']:
            html=html.replace('<div class="brand">LightTry</div>','<div class="brand">LightTry</div><p class="note">离线演示 · 不会启动真实 GPU</p>')
        budget=info.get('budgetUsdIncludingTax')
        if type(budget) in (int,float) and 0<budget<=1000:
            budget_note=('Session budget $'+format(budget,'.2f')+' (including tax). Automatic stop is not a hard billing cap.'
                         if h.ui_locale=='en' else '本次预算 '+format(budget,'.2f')+' 美元（含税）。自动停机不保证账单硬封顶。')
            html=html.replace('启动 GPU 可能产生费用。',budget_note)
        reason=info['message']
        if h.ui_locale=='en':
            if info.get('diagnostic'):
                reason=error_message('en',info['diagnostic'].get('code'),reason)+' Do not restart until release is confirmed.'
            elif info['state']=='STOPPING':reason='Stop is in progress. Wait for STOPPED and an empty instance list.'
            elif info['state']=='STOPPED':reason='Ready for a single start request.' if info['canStart'] else 'Start is unavailable until safety checks pass.'
            else:reason='Status is not confirmed. You can edit plans without starting another GPU request.'
            for source,target in (('lang="zh-CN"','lang="en"'),('准备工作台 · LightTry','Prepare workbench · LightTry'),
                    ('启动 GPU 并进入工作台','Start GPU and enter workbench'),('暂不启动，直接进入','Enter without starting'),
                    ('启动 GPU 可能产生费用。','Starting the GPU may incur charges.'),
                    ('提交后立即进入工作台，无需等待启动完成。',' You can enter the workbench immediately without waiting for startup.'),
                    ('离线演示 · 不会启动真实 GPU','Offline demo · no real GPU will start')):
                html=html.replace(source,target)
        html=html.replace('</style><main id="gpu-entry"','.languages{display:flex;justify-content:flex-end;gap:12px;font-size:12px}.languages a{color:#286d4e}</style><main id="gpu-entry"')
        html=html.replace('<div class="brand">LightTry</div>','<nav class="languages" aria-label="Language"><a href="/lang/zh">中文</a><a href="/lang/en">English</a></nav><div class="brand">LightTry</div>')
        html=html.replace('TOKEN',h.csrf_token).replace('TITLE',title).replace('INTRO',intro).replace('DISABLED',disabled).replace('REASON',reason)
        h.send_bytes(html.encode('utf-8'),'text/html; charset=utf-8')

    def start_gpu_from_entry(self, h):
        if h.headers.get('Content-Type')!='application/json':
            raise JobError('INVALID_BODY','请求格式不正确。',400)
        body=studio.shared.strict_json(self.body(h,1024).decode('utf-8'))
        if not isinstance(body,dict) or set(body)!={'requestId'} or not ID.fullmatch(str(body['requestId'])):
            raise JobError('INVALID_BODY','启动请求无效。',422)
        info=self.gpu_entry_info(h.user,h.owner_scope)
        if info['active']:
            h.json_response({'status':'already_active'},202);return
        if not self.gpu_sessions or not self.gpu_scope:
            raise JobError('CONTROL_NOT_CONFIGURED','启动服务暂不可用，未启动 GPU。',503)
        scope=copy.deepcopy(self.gpu_scope)
        with self.entry_lock:
            issuer=getattr(getattr(self,'gpu_control',None),'scope_issuer',None)
            if self.entry_start and ((issuer and self.entry_start.get('requestId')==body['requestId']) or (not issuer and self.entry_start['scopeId']==scope.get('scopeId'))):
                h.json_response({'status':self.entry_start['status']},202);return
            if not info['canStart'] or (self.entry_thread and self.entry_thread.is_alive()):
                raise JobError('START_BLOCKED','暂不能安全启动 GPU，请先进入工作台。',409)
            control=getattr(self,'gpu_control',None)
            if getattr(control,'scope_issuer',None):
                try:scope=control.issue_scope(body['requestId'],h.user)
                except ValueError:
                    raise JobError('CURRENT_SCOPE_UNAVAILABLE','本次启动授权无法安全建立，未启动 GPU。',409)
                self.gpu_scope=scope
            self.entry_start={'scopeId':scope.get('scopeId'),'requestId':body['requestId'],'status':'requested'}
            def run():
                status='unknown'
                try:
                    value=self.gpu_sessions.start(scope)
                    status='requested' if value.get('state') in ('STARTING','LOADING','READY','EXECUTING') else 'failed'
                except Exception:
                    status='failed'
                    LOG.warning('entry GPU request failed; no automatic retry')
                finally:
                    with self.entry_lock:
                        self.entry_start['status']=status
            self.entry_thread=threading.Thread(target=run,name='gpu-entry-start',daemon=True)
            self.entry_thread.start()
        h.json_response({'status':'requested'},202)

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
        h.ui_locale=resolve_locale(environ.get('HTTP_COOKIE',''),environ.get('HTTP_ACCEPT_LANGUAGE',''))
        slot=False
        try:
            h.user=self.authorized(environ)
            operator=self.is_operator(h.user)
            if not operator:self.limiter.consume('ip',environ.get('REMOTE_ADDR','unknown'))
            h.owner_scope=(h.user if h.user not in self.session_scoped_accounts else self.workspace.browser_space(
                h.user,self.accounts.users[h.user]['hash'],self.browser_token(environ)) if h.user else None)
            if h.user:h.recipe_language=self.language_for(h.user,h.owner_scope)
            if not h.valid_host():
                h.job_error(JobError('INVALID_HOST', '访问地址未配置。', 403))
            elif self.login_route(h, environ):
                pass
            elif not h.user:
                if h.command == 'GET' and urlsplit(h.path).path in ('/', '/index.html'):
                    self.login_page(h, 401)
                else:
                    h.job_error(JobError('AUTH_REQUIRED', '请先使用访问密钥登录。', 401))
            elif not h.owner_scope and urlsplit(h.path).path!='/auth/logout':
                h.job_error(JobError('BROWSER_SPACE_REQUIRED','请重新登录以绑定此浏览器的私有工作区。',401))
            elif not h.valid_origin():
                h.job_error(JobError('INVALID_ORIGIN', '仅接受已配置的同源访问。', 403))
            elif h.command in ('POST', 'PUT', 'DELETE') and h.headers.get('X-LightTry-Token') != h.csrf_token:
                h.job_error(JobError('INVALID_TOKEN', '请刷新页面后重试。', 403))
            else:
                if not operator:self.limiter.consume('user',h.owner_scope)
                path=urlsplit(h.path).path
                if any(part in ('.','..') for part in path.split('/')) or '%' in path or '\\' in path or any(ord(c)<32 for c in path):
                    raise JobError('UNSAFE_PATH','路径无效。',404)
                if h.command=='POST':
                    if not operator:
                        self.limiter.consume('write',h.owner_scope)
                        if path=='/api/tasks':self.limiter.consume('generate',h.owner_scope)
                        if path in ('/api/lighting/recommend','/api/language/recommend'):
                            self.limiter.consume_language(h.owner_scope)
                    if path.startswith('/api/photos/') or path in ('/api/tasks','/api/environments/import'):
                        if not operator:self.limiter.consume('upload',h.owner_scope)
                        slot=self.upload_slots.acquire(blocking=False)
                        if not slot:raise JobError('UPLOAD_BUSY','解码通道繁忙，请稍后重试。',429)
                self.check_ownership(h,path)
                if path=='/api/gpu/presence-stream' and h.command=='GET':
                    if h.headers.get('X-LightTry-Token')!=h.csrf_token:
                        raise JobError('INVALID_TOKEN','在线连接需要同源认证。',403)
                    disconnected=environ.get('waitress.client_disconnected')
                    if not callable(disconnected):
                        raise JobError('PRESENCE_STREAM_UNAVAILABLE','服务器未启用连接断开检测。',503)
                    if not self.presence_slots.acquire(blocking=False):
                        raise JobError('PRESENCE_STREAM_BUSY','在线连接数达到上限。',503)
                    from client_presence import PresenceStream
                    stream=PresenceStream(lambda:self.gpu_sessions,disconnected,
                        lambda:self.authorized(environ)==h.user,self.presence_stop,self.presence_slots.release)
                    start_response('200 OK',[('Content-Type','text/event-stream'),('Cache-Control','no-store'),('X-Accel-Buffering','no')])
                    return stream
                if path == '/auth/logout' and h.command == 'POST':
                    self.login_sessions.revoke(self.session_token(environ))
                    h.json_response({'status':'signed_out'})
                    h.send_header('Set-Cookie', self.session_cookie('', 0))
                elif self.private_route(h):pass
                elif h.command=='GET':h.do_GET()
                elif h.command=='POST':
                    with h.task_store.mutex:
                        h.do_POST()
                        h.task_store.environments.update(h.environment_library.environments)
                else:h.job_error(JobError('METHOD_NOT_ALLOWED','请求方法不支持。',405))
        except JobError as error:
            h.job_error(error)
        except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
            h.wfile = io.BytesIO()
            h.job_error(JobError('REQUEST_INVALID', '请求数据或持久化记录无效。', 422))
        except Exception:
            LOG.error('request failed; internal I/O or application error')
            h.wfile = io.BytesIO()
            h.job_error(JobError('STATE_UNAVAILABLE', '服务读写失败，请检查本机日志。', 503))
        finally:
            if slot:self.upload_slots.release()
        h.response_headers = [(k,v) for k,v in h.response_headers if k.lower() not in ('cache-control','referrer-policy','x-content-type-options')]
        h.send_header('Cache-Control', 'no-store')
        # Same-origin forms need an Origin; never send referrers cross-origin.
        h.send_header('Referrer-Policy', 'same-origin')
        h.send_header('X-Content-Type-Options', 'nosniff')
        h.send_header('Content-Language', 'en' if h.ui_locale=='en' else 'zh-CN')
        if h.response_status==429:h.send_header('Retry-After','60')
        LOG.info('request status=%s',h.response_status)
        start_response(f'{h.response_status} {HTTPStatus(h.response_status).phrase}', wsgi_response_headers(h.response_headers))
        return [h.wfile.getvalue()]

    def check_ownership(self,h,path):
        if path.startswith(('/study/','/study-download/','/study-region/','/study-download-region/')) and h.owner_scope!=self.workspace.default_owner:
            raise JobError('OBJECT_NOT_FOUND','结果不存在或不属于当前账号。',404)
        if path.startswith('/api/tasks/'):
            identity=path.split('/')[3]
            self.workspace.require_owner('task',identity,h.owner_scope)
        if path.startswith('/api/environments/') and path.endswith('/thumbnail'):
            sha=path.split('/')[3]
            if not any(e['sha256']==sha and e.get('source',{}).get('kind')!='local-import' for e in h.environment_library.environments.values()):
                self.workspace.require_owner('hdr','hdr-'+sha,h.owner_scope)
        if path=='/api/workspace' and h.command=='POST':return

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
        if path=='/gpu-entry' and h.command=='GET':
            self.gpu_entry_page(h)
        elif path=='/gpu-entry.js' and h.command=='GET':
            h.send_bytes((ROOT/'project/web/gpu-entry.js').read_bytes(),'application/javascript; charset=utf-8')
        elif path=='/api/gpu/presence' and h.command=='POST':
            if self.gpu_sessions:
                current=self.gpu_sessions.latest()
                if current.get('sessionId'):self.gpu_sessions.client_presence(current['sessionId'])
            h.json_response({'ok':True})
        elif path=='/api/gpu/entry-status' and h.command=='GET':
            h.json_response(gpu_info(h.ui_locale,self.gpu_entry_info(h.user,h.owner_scope)))
        elif path=='/api/gpu/entry-start' and h.command=='POST':
            self.start_gpu_from_entry(h)
        elif path=='/api/gpu/status' and h.command=='GET':
            h.json_response(self.gpu_sessions.latest() if self.gpu_sessions else {'state':'STOPPED','label':'停止','configured':False,'providerState':None,'verifiedStopped':False,'simulation':False})
        elif path in ('/api/gpu/start','/api/gpu/stop','/api/gpu/confirm-host','/api/generate','/api/tasks/start','/api/tasks/stop'):
            if h.command=='GET':raise JobError('METHOD_NOT_ALLOWED','生成、启动或停止不得由 GET 触发。',405)
            if path not in ('/api/gpu/start','/api/gpu/stop') and not self.is_operator(h.user):
                raise JobError('OPERATOR_REQUIRED','此云控制操作仅限管理员。',403)
            if not self.gpu_sessions or not self.gpu_scope:raise JobError('CONTROL_NOT_CONFIGURED','受守护云控制未配置；没有启动或停止。',503)
            if h.headers.get('Content-Type')!='application/json':raise JobError('INVALID_BODY','需要 JSON。',400)
            body=studio.shared.strict_json(self.body(h,8192).decode('utf-8'))
            if path=='/api/gpu/start':
                if set(body)!={'requestId'} or not ID.fullmatch(body['requestId']):raise JobError('INVALID_BODY','只接受本次点击身份，不接受客户端预算或主机参数。',422)
                self.start_gpu_from_entry(h)
            elif path=='/api/gpu/confirm-host':
                if getattr(self.gpu_control,'auto_host_trust',False):
                    raise JobError('AUTOMATIC_HOST_TRUST_ACTIVE','本次服务器由守护自动绑定，浏览器不能代表运维方确认。',409)
                bootstrap=getattr(self.gpu_control,'bootstrap',None)
                expected={'sessionId','hostIdentity','fingerprint'} if bootstrap else {'sessionId','hostIdentity'}
                if set(body)!=expected:raise JobError('INVALID_BODY','需要本会话的当前主机确认。',422)
                if bootstrap:bootstrap.confirm(body['sessionId'],body['hostIdentity'],body['fingerprint'])
                h.json_response(self.gpu_sessions.confirm_host(body['sessionId'],body['hostIdentity']))
            elif path=='/api/gpu/stop':
                if set(body)!={'sessionId'}:raise JobError('INVALID_BODY','需要会话身份。',422)
                with self.queue.mutex:
                    current=self.gpu_sessions.latest()
                    if body['sessionId']!=current.get('sessionId'):raise JobError('SESSION_NOT_FOUND','会话不匹配。',404)
                    if not self.is_operator(h.user) and self.queue.foreign_in_flight(h.owner_scope):
                        raise JobError('FOREIGN_GPU_TASK','有其他用户的生成任务正在运行或排队，普通用户无权关闭 GPU。',403)
                    h.json_response(self.gpu_sessions.request_stop(body['sessionId']),202)
            else:raise JobError('CONTROL_NOT_CONFIGURED','此控制接口未配置。',503)
        elif h.command=='GET' and path=='/api/me':
            me={'username':h.user,'role':self.accounts.users[h.user]['role']}
            if h.user in self.session_scoped_accounts:me['workspaceId']=h.owner_scope.split('~',1)[1]
            h.json_response(me)
        elif h.command=='GET' and path=='/api/environments':
            h.json_response({'environments':[e for e in h.environment_library.environments.values() if e.get('source',{}).get('kind')!='local-import' or self.workspace.owned('hdr',e['id'],h.owner_scope)]})
        elif h.command=='GET' and path=='/api/accepted-results':
            own=h.owner_scope==self.workspace.default_owner
            h.json_response({'schemes':h.imported_schemes if own else [],'studies':[x for x in h.studies if x.get('recipeKey')] if own else []})
        elif h.command=='GET' and path=='/api/lighting':
            own=h.owner_scope==self.workspace.default_owner
            h.json_response({'schemaVersion':1,'capabilities':h.lighting_capabilities,'studies':h.studies if own else [],
                'importedSchemes':h.imported_schemes if own else [],'textOnlyAI':True,
                'language':h.recipe_language.capabilities() if h.recipe_language else {'enabled':False,'message':'Nemotron 未启用；手动操作不收费。'}})
        elif h.command=='POST' and path in ('/api/lighting/normalize','/api/lighting/condition','/api/lighting/recommend','/api/language/recommend'):
            if h.headers.get('Content-Type')!='application/json':raise JobError('INVALID_BODY','需要 JSON。',400)
            data=self.body(h,8192);body=studio.shared.strict_json(data.decode('utf-8'))
            if not isinstance(body,dict):raise JobError('INVALID_BODY','需要 JSON 对象。',400)
            scheme=body.get('currentScheme',body);params=scheme.get('parameters',scheme)
            environment=params.get('environmentId')
            if isinstance(environment,str) and environment.startswith('hdr-'):self.workspace.require_owner('hdr',environment,h.owner_scope)
            if scheme.get('planId'):
                with self.workspace.connect() as db:row=db.execute("SELECT owner FROM ownership WHERE kind='plan' AND id=?",(scheme['planId'],)).fetchone()
                if row and row[0]!=h.owner_scope:raise JobError('OBJECT_NOT_FOUND','方案不属于当前账号。',404)
            h.rfile=io.BytesIO(data)
            with h.task_store.mutex:h.do_POST()
        elif h.command=='POST' and path=='/api/environments/import':
            if h.headers.get('Content-Type')!='application/octet-stream':raise JobError('INVALID_BODY','需要 HDR 原始字节。',400)
            payload=self.body(h,32*1024*1024)
            studio.decode_hdr(payload)
            identity='hdr-'+studio.digest(payload)
            with h.task_store.mutex:
                self.workspace.claim('hdr',identity,h.owner_scope)
                from urllib.parse import unquote
                env=h.environment_library.import_bytes(payload,unquote(h.headers.get('X-Environment-Name','导入环境')))
                h.task_store.environments[env['id']]=env
                h.json_response(env)
        elif h.command=='POST' and path=='/api/tasks':
            if not h.task_store.executor or not callable(getattr(h.task_store.executor,'authorize_job',None)):
                raise JobError('SERVICE_NOT_CONNECTED','收费执行默认关闭，且需逐项服务端授权。',503)
            encoded=h.headers.get('X-LightTry-Request','')
            if len(encoded)>4096:raise JobError('INVALID_REQUEST','任务元数据过长。',413)
            metadata=studio.shared.strict_json(base64.b64decode(encoded,validate=True).decode('utf-8'))
            if 'lightingScheme' in metadata:
                env=metadata['lightingScheme'].get('parameters',{}).get('environmentId')
                if isinstance(env,str) and env.startswith('hdr-'):self.workspace.require_owner('hdr',env,h.owner_scope)
            h.json_response(self.queue.submit(self.body(h,MAX_BYTES),metadata,h.headers.get('Content-Type'),h.owner_scope),202)
        elif path.startswith('/api/requests/') and path.endswith('/abandon') and path.count('/')==4 and h.command=='POST':
            rid=path.split('/')[-2]
            h.json_response(self.queue.abandon_request(rid,h.owner_scope))
        elif path.startswith('/api/requests/') and h.command=='GET':
            rid=path.split('/')[-1]
            try:task=self.queue.by_request(rid,h.owner_scope)
            except JobError:
                task=None
                from inference.jobs import read
                for folder in h.task_store.root.iterdir():
                    if ID.fullmatch(folder.name) and self.workspace.owned('task',folder.name,h.owner_scope) and not folder.is_symlink() and (folder/'task.json').is_file():
                        if read(folder/'task.json').get('requestId')==rid:task=h.task_store.get(folder.name);break
                if task is None:raise JobError('TASK_NOT_FOUND','请求不存在。',404)
            h.json_response(task)
        elif path.startswith('/api/tasks/') and self.queue.contains(path.split('/')[3],h.owner_scope):
            parts=path.split('/');identity=parts[3]
            if h.command=='GET' and len(parts)==4:h.json_response(self.queue.get(identity,h.owner_scope))
            elif h.command=='GET' and len(parts)==5 and parts[-1]=='original' and not (h.task_store.root/identity/'task.json').is_file():
                row=self.queue.row(identity,h.owner_scope);file=self.queue.root/identity/'original'
                if any(p.is_symlink() for p in (file,*file.parents)) or not file.is_file():raise JobError('FILE_NOT_FOUND','照片不存在。',404)
                payload=file.read_bytes()
                metadata=json.loads(row[4])
                from lighting import canonical
                if len(payload)>MAX_BYTES or studio.digest(canonical({'metadata':metadata,'photoSha256':studio.digest(payload),'mime':row[5]}).encode())!=row[3]:raise JobError('FILE_CHANGED','排队照片校验失败。',409)
                h.send_bytes(payload,row[5])
            else:return False
        elif h.command == 'GET' and path == '/api/health':
            with self.workspace.connect() as db:
                db.execute('SELECT 1').fetchone()
            h.json_response({'status': 'ready', 'paidServices': self.model_executor is not None})
        elif h.command == 'GET' and path in ('/api/workspace', '/api/workspace/export'):
            value = self.workspace.library(h.owner_scope)
            value['taskIds'] = [p.name for p in h.task_store.root.iterdir()
                                if ID.fullmatch(p.name) and not p.is_symlink() and (p / 'task.json').is_file() and self.workspace.owned('task',p.name,h.owner_scope)]
            with self.workspace.connect() as db:
                value['taskIds'] += [r[0] for r in db.execute('SELECT id FROM gpu_queue WHERE owner=?',(h.owner_scope,)) if r[0] not in value['taskIds']]
            h.send_bytes(json.dumps(value, ensure_ascii=False).encode(), 'application/json; charset=utf-8',
                         'lighttry-workspace.json' if path.endswith('/export') else None)
        elif h.command == 'POST' and path == '/api/workspace':
            if h.headers.get('Content-Type') != 'application/json':
                raise JobError('INVALID_BODY', '需要 JSON。', 400)
            body = studio.shared.strict_json(self.body(h, 1024 * 1024).decode('utf-8'))
            with h.task_store.mutex:
                h.json_response(self.workspace.save_library(body,h.owner_scope))
        elif path.startswith('/api/photos/'):
            pid = path.removeprefix('/api/photos/')
            if h.command == 'GET':
                _, data, mime = self.workspace.photo(pid,h.owner_scope)
                h.send_bytes(data, mime)
            elif h.command == 'POST':
                metadata = studio.shared.strict_json(base64.b64decode(h.headers.get('X-LightTry-Photo', ''), validate=True).decode('utf-8'))
                if not isinstance(metadata, dict) or set(metadata) != {'name'}:
                    raise JobError('PHOTO_METADATA_INVALID', '照片名称字段无效。', 422)
                h.json_response(self.workspace.save_photo(pid, metadata['name'], self.body(h, MAX_BYTES),
                                                          h.headers.get('Content-Type'),h.owner_scope), 201)
            else:
                h.job_error(JobError('METHOD_NOT_ALLOWED', '请求方法不支持。', 405))
        else:
            return False
        return True


def parser():
    p = argparse.ArgumentParser(description='Linux/CPU standalone service; paid services remain OFF.')
    p.add_argument('--listen-host',choices=('127.0.0.1','0.0.0.0'),default='0.0.0.0',
                   help='Explicit bind address. Use 127.0.0.1 with host-network containers behind Nginx.')
    def listen_port(value):
        try: port=int(value)
        except ValueError:raise argparse.ArgumentTypeError('LISTEN_PORT_INVALID') from None
        if not 1024<=port<=65535:raise argparse.ArgumentTypeError('LISTEN_PORT_INVALID')
        return port
    p.add_argument('--listen-port',type=listen_port,default=8080)
    p.add_argument('--accounts-file',default=os.environ.get('LIGHTTRY_ACCOUNTS_FILE'))
    p.add_argument('--session-scoped-account',action='append',dest='session_scoped_accounts',default=[],
                   help='Explicit shared-key user whose private workspace and stop ownership use a durable browser identity.')
    p.add_argument('--language-config',type=Path,default=os.environ.get('LIGHTTRY_RECIPE_LANGUAGE_CONFIG_FILE'),
                   help='Private role text policy; requires a server-side Nemotron key. Never enabled by access keys alone.')
    p.add_argument('--model-grant-file',type=Path,default=os.environ.get('LIGHTTRY_MODEL_GRANT_FILE'))
    p.add_argument('--gpu-control-config',type=Path,default=os.environ.get('LIGHTTRY_GPU_CONTROL_CONFIG'),
                   help='Private audited control factory binding; no implicit cloud start.')
    p.add_argument('--init-account',action='store_true',help='Create runtime-only 7-day user account; no service/cloud start.')
    p.add_argument('--account-output',type=Path,help='Private plaintext login handoff file, outside code.')
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
    if options.init_account:
        if not options.account_output:raise ValueError('PRIVATE_ACCOUNT_OUTPUT_REQUIRED')
        print(json.dumps(create_temporary_account(options.data_root,options.account_output,ROOT)))
        return
    app = Application(options)
    try:
        from waitress import serve
        def stop(signum, frame):
            raise KeyboardInterrupt()
        signal.signal(signal.SIGTERM, stop)
        app.queue.start()
        if app.gpu_control:app.gpu_control.start_heartbeat()
        if app.model_executor:app.model_executor.start()
        print('LightTry CPU service: '+options.listen_host+':'+str(options.listen_port)+'; data=' + str(app.workspace.root), flush=True)
        serve(app, listen=options.listen_host+':'+str(options.listen_port), threads=16, connection_limit=64,
              max_request_header_size=16384, max_request_body_size=32 * 1024 * 1024,
              channel_timeout=30, channel_request_lookahead=1, expose_tracebacks=False, clear_untrusted_proxy_headers=True)
    finally:
        app.close()
