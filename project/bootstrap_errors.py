"""Closed bootstrap diagnostic codes. Never persist raw exception/SSH output."""
import json
import ssl
import subprocess
import errno

STAGES={'state_check':'检查当前会话','capture':'读取主机指纹','authorize':'建立本次模型授权',
        'preflight':'部署预检','prepare':'SSH远程准备','upload':'上传部署材料',
        'install':'远程安装与启动','tunnel':'建立SSH隧道','direct_https':'配置直连HTTPS','unknown':'阶段未记录'}
MESSAGES={
 'SSH_COMMAND_TIMEOUT':'SSH连接或远程命令超过时限，未取得完成回执；不能确定远端是否执行。',
 'HTTPS_SETUP_TIMEOUT':'直连HTTPS部署或证书准备超过时限，未确认完成。',
 'BOOTSTRAP_WINDOW_EXPIRED':'本次引导或授权窗口已关闭，未延长时限或重新启动。',
 'SSH_NETWORK_UNAVAILABLE':'SSH报告连接超时、拒绝或网络不可达。',
 'SSH_CONNECTION_CLOSED':'SSH连接被重置或关闭，远端执行结果未确认。',
 'SSH_AUTH_FAILED':'SSH认证被拒绝，请检查当前账户及已配置的访问密钥。',
 'SSH_HOST_KEY_REJECTED':'主机指纹校验失败；禁止绕过校验或沿用旧主机信任。',
 'REMOTE_HELPER_FAILED':'远端准备程序返回失败，未继续上传或重复启动。',
 'REMOTE_COMMAND_FAILED':'远程命令返回非零状态；安全记录不足以判断更具体原因。',
 'REMOTE_OUTPUT_TOO_LARGE':'远程返回超过安全大小上限，结果未采信。',
 'REMOTE_JSON_INVALID':'远程命令已返回，但返回内容不是有效JSON，执行结果未确认。',
 'LOCAL_JSON_INVALID':'本地配置或授权文件的JSON无法解析，流程已中断。',
 'LOCAL_FILE_NOT_FOUND':'本地必需文件或可执行程序不存在。',
 'LOCAL_PERMISSION_DENIED':'本地文件或程序访问被拒绝。',
 'LOCAL_TEXT_ENCODING':'本地或远程文本编码无法解析。',
 'LOCAL_IO_FAILED':'本地读写或进程启动出现系统错误。',
 'LOCAL_PORT_BUSY':'本地连接端口已被占用，未创建新的隧道或重复启动。',
 'FROZEN_MATERIAL_CHANGED':'冻结部署包或私有配置已发生变化，完整性预检拒绝继续。',
 'TLS_VERIFICATION_FAILED':'HTTPS证书或身份验证失败，未降低安全要求。',
 'SESSION_OR_BINDING_REJECTED':'当前会话、授权、哈希或主机绑定校验失败。',
 'LOCAL_PROGRAM_ERROR':'本地引导代码出现类型或字段错误，已截断流程。',
 'BOOTSTRAP_UNCLASSIFIED':'尚未分类的引导异常；保留类型信息，但不猜测原因。'}


class CommandFailure(OSError):
    def __init__(self, code, legacy, exit_code=None):
        self.diagnostic_code=code if code in MESSAGES else 'BOOTSTRAP_UNCLASSIFIED'
        self.exit_code=exit_code if type(exit_code) is int else None
        super().__init__(legacy)


def stderr_code(raw):
    """Inspect bounded bytes IN MEMORY; return only a fixed code, never raw text."""
    text=(raw[:4096].decode('ascii',errors='ignore') if isinstance(raw,bytes) else '') .lower()
    if any(s in text for s in ('host key verification failed','remote host identification has changed')):return 'SSH_HOST_KEY_REJECTED'
    if any(s in text for s in ('permission denied (','authentication failed','no supported authentication methods')):return 'SSH_AUTH_FAILED'
    if any(s in text for s in ('connection timed out','connection refused','no route to host','network is unreachable')):return 'SSH_NETWORK_UNAVAILABLE'
    if any(s in text for s in ('connection reset','connection closed by','broken pipe')):return 'SSH_CONNECTION_CLOSED'
    return 'REMOTE_COMMAND_FAILED'


def classify(error, stage='unknown', duration_ms=None):
    if isinstance(error,CommandFailure):code=error.diagnostic_code
    elif isinstance(error,subprocess.TimeoutExpired):code='HTTPS_SETUP_TIMEOUT' if stage=='direct_https' else 'SSH_COMMAND_TIMEOUT'
    elif isinstance(error,json.JSONDecodeError):code='LOCAL_JSON_INVALID' if stage in ('preflight','authorize','state_check') else 'REMOTE_JSON_INVALID'
    elif isinstance(error,UnicodeError):code='LOCAL_TEXT_ENCODING'
    elif isinstance(error,ssl.SSLError):code='TLS_VERIFICATION_FAILED'
    elif isinstance(error,FileNotFoundError):code='LOCAL_FILE_NOT_FOUND'
    elif isinstance(error,PermissionError):code='LOCAL_PERMISSION_DENIED'
    elif isinstance(error,OSError):code='LOCAL_PORT_BUSY' if error.errno==errno.EADDRINUSE else 'LOCAL_IO_FAILED'
    elif isinstance(error,(TypeError,KeyError,AttributeError)):code='LOCAL_PROGRAM_ERROR'
    elif isinstance(error,ValueError):
        code='BOOTSTRAP_WINDOW_EXPIRED' if str(error)=='BOOTSTRAP_DEADLINE' else 'FROZEN_MATERIAL_CHANGED' if str(error) in ('FROZEN_BOOTSTRAP_BINDING_CHANGED','FROZEN_BOOTSTRAP_CODE_CHANGED') else 'SSH_HOST_KEY_REJECTED' if str(error) in ('SSH_HOST_KEY_INVALID','SSH_HOST_KEY_NOT_UNIQUE') else 'SESSION_OR_BINDING_REJECTED'
    else:code='BOOTSTRAP_UNCLASSIFIED'
    types={'TimeoutExpired','JSONDecodeError','UnicodeDecodeError','UnicodeEncodeError','SSLError',
           'FileNotFoundError','PermissionError','OSError','TypeError','KeyError','AttributeError','ValueError','CommandFailure'}
    result={'code':code,'stage':stage if stage in STAGES else 'unknown',
            'exceptionType':type(error).__name__ if type(error).__name__ in types else 'OtherError',
            'rawDetailsRecorded':False,'retryAllowed':False}
    if duration_ms is not None:result['durationMs']=max(0,min(2147483647,int(duration_ms)))
    if isinstance(error,CommandFailure) and error.exit_code is not None:result['exitCode']=error.exit_code
    return result


def public_error(value):
    if not isinstance(value,dict) or value.get('code') not in MESSAGES:return None
    code=value['code'];stage=value.get('stage') if value.get('stage') in STAGES else 'unknown'
    return {'code':code,'stage':stage,'stageLabel':STAGES[stage],
            'message':MESSAGES[code],'retryAllowed':False}
