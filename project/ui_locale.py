"""Two-language interface selection; never changes user content or model prompts."""
from http.cookies import SimpleCookie
import copy
import re

COOKIE='lighttry_lang'
SUPPORTED={'zh','en'}


def resolve_locale(cookie_header='', accept_language=''):
    try:
        cookie=SimpleCookie();cookie.load(cookie_header[:4096])
        manual=cookie[COOKIE].value if COOKIE in cookie else None
    except Exception:
        manual=None
    if manual in SUPPORTED:return manual
    ranked=[]
    for index,part in enumerate(accept_language[:1024].split(',')[:20]):
        bits=part.strip().split(';')
        primary=bits[0].strip().lower().split('-')[0]
        if primary not in SUPPORTED:continue
        quality=1.0
        for option in bits[1:]:
            if option.strip().startswith('q='):
                try:quality=float(option.strip()[2:])
                except ValueError:quality=0
        if 0<quality<=1:ranked.append((-quality,index,primary))
    return min(ranked)[2] if ranked else 'en'


ERRORS={
    'AUTH_REQUIRED':'Sign in with an access key first.',
    'INVALID_ORIGIN':'Submit this request from the current site.',
    'INVALID_TOKEN':'Refresh the page and try again.',
    'INVALID_HOST':'This access address is not configured.',
    'BROWSER_SPACE_REQUIRED':'Sign in again to bind this browser’s private workspace.',
    'INVALID_IMAGE':'Only JPG, PNG or WebP images whose contents match the declared format are accepted.',
    'INVALID_REQUEST':'The request data or identity is invalid.',
    'REQUEST_ABANDONED':'This request ID was abandoned. Confirm a new photo instead.',
    'REQUEST_ALREADY_ACCEPTED':'This request was already accepted; check its task before changing photos.',
    'IDEMPOTENCY_CONFLICT':'This request ID was already used with different data. Do not retry it.',
    'TASK_NOT_FOUND':'The task or request was not found.',
    'TASK_BUSY':'A task is running or its execution state is uncertain. Check it first.',
    'EXECUTION_NOT_AUTHORIZED':'This generation is not currently authorized; no image was submitted.',
    'GPU_STATUS_UNCERTAIN':'GPU status cannot be confirmed. Do not restart it.',
    'STATE_UNAVAILABLE':'The service is temporarily unavailable. Check status before retrying.',
    'REQUEST_INVALID':'The request or stored record is invalid.',
    'UPLOAD_BUSY':'The image decoder is busy. Try again later.',
    'RATE_LIMITED':'Too many requests. Wait before trying again.',
    'METHOD_NOT_ALLOWED':'This request method is not supported.',
    'UNSAFE_PATH':'This path is not allowed.',
}


def error_message(locale,code,original):
    if locale!='en':return original
    if code in ERRORS:return ERRORS[code]
    safe=re.sub(r'[^A-Z0-9_]','',str(code))[:80]
    return f'Request could not be completed ({safe or "UNKNOWN"}). Check status before retrying.'


def gpu_info(locale, source):
    """Translate display copy only; preserve codes, state and safety decisions."""
    if locale!='en':return source
    info=copy.deepcopy(source)
    state=info.get('state')
    diagnostic=info.get('diagnostic')
    if isinstance(diagnostic,dict):
        code=diagnostic.get('code','UNKNOWN')
        manual=code in ('OPERATOR_STOP','USER_REQUESTED_STOP') or str(code).startswith('USER_STOP_')
        titles={'GPU_CONNECTION_FAILED':'GPU connection failed','GPU_START_FAILED':'GPU start or preflight failed',
                'GPU_STATUS_UNCERTAIN':'GPU status cannot be confirmed','GPU_MODEL_FAILED':'Model loading failed'}
        if manual:title='GPU stopped' if state=='STOPPED' else 'GPU stopping'
        else:title=titles.get(code,'GPU setup needs attention')
        if not diagnostic.get('active') and state=='STOPPED' and not manual:title='Previous fault · '+title
        detail=('Stop was requested by the operator.' if manual else
                'Status query failed or the snapshot expired; an old state does not prove release.' if code=='GPU_STATUS_UNCERTAIN' else
                'The model process reported a failure and cannot generate.' if code=='GPU_MODEL_FAILED' else
                'Connection, startup or deployment did not complete; there is no automatic retry.')
        released=state=='STOPPED' and info.get('monitor',{}).get('verifiedStopped') is True and info.get('monitor',{}).get('instancesEmpty') is True
        cost='STOPPED and an empty instance list are confirmed.' if released else 'Release is not confirmed; GPU charges may continue.'
        action='A new start requires a manual action.' if released else 'Use Stop if no longer needed; wait for release and do not start again.'
        diagnostic.update(title=title,detail=detail,cost=cost,action=action)
        info['message']=' '.join((title+':',detail,cost,action))
    elif state=='STOPPING':info['message']='Stop is in progress. Wait for STOPPED and an empty instance list.'
    elif state=='UNKNOWN':info['message']='GPU status cannot be confirmed. Do not restart based on an old snapshot.'
    elif state=='STOPPED':info['message']='GPU is stopped.' if info.get('canStart') else 'GPU start is unavailable until safety checks pass.'
    else:info['message']='GPU is active. Use the monitor for confirmed progress and safety deadlines.'
    failure=info.get('hostConfirmation',{}).get('failure')
    if isinstance(failure,dict) and failure.get('message'):
        failure['message']='Bootstrap did not complete. See the error code; there is no automatic retry.'
    return info
