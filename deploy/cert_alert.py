"""Operator-only TLS renewal failure alert. Never logs the SMTP authorization code."""
import argparse
from email.message import EmailMessage
import json
import os
from pathlib import Path
import re
import secrets
import smtplib
import socket
import ssl
import stat
import subprocess
import time


def private_file(value, limit):
    path=Path(value)
    if not path.is_absolute() or any(item.is_symlink() for item in (path,*path.parents)):
        raise ValueError('PRIVATE_ABSOLUTE_FILE_REQUIRED')
    info=path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_size>limit:
        raise ValueError('PRIVATE_FILE_PERMISSIONS_REQUIRED')
    if os.name!='nt':
        if info.st_mode&0o077:
            raise ValueError('PRIVATE_FILE_PERMISSIONS_REQUIRED')
        if info.st_uid!=0:
            raise ValueError('ROOT_OWNED_SECRET_REQUIRED')
    return path


def load_config(path):
    raw=private_file(path,4096)
    value=json.loads(raw.read_text(encoding='utf-8'))
    required={'schemaVersion','recipient','smtpUser','smtpSecretFile','stateFile','expectedIp','warningHours'}
    if not isinstance(value,dict) or set(value)!=required or value['schemaVersion']!=1:
        raise ValueError('EXPLICIT_CERT_ALERT_CONFIG_REQUIRED')
    recipient=value['recipient']
    if (not isinstance(recipient,str) or not re.fullmatch(r'[1-9][0-9]{4,11}@qq\.com',recipient) or
            value['smtpUser']!=recipient or value['expectedIp']!='47.238.73.99' or
            type(value['warningHours']) is not int or not 24<=value['warningHours']<=120):
        raise ValueError('CERT_ALERT_TARGET_INVALID')
    for field in ('smtpSecretFile','stateFile'):
        p=Path(value[field])
        if not p.is_absolute() or any(x.is_symlink() for x in (p,*p.parents)):
            raise ValueError('PRIVATE_ALERT_PATH_REQUIRED')
    return value


def certificate_expiry(ip):
    with socket.create_connection(('127.0.0.1',443),timeout=8) as raw:
        with ssl.create_default_context().wrap_socket(raw,server_hostname=ip) as tls:
            return ssl.cert_time_to_seconds(tls.getpeercert()['notAfter'])


def renewal_result():
    result=subprocess.run(['systemctl','show','lighttry-cert-renew.service','-p','Result','--value'],
                          capture_output=True,text=True,timeout=8)
    return result.stdout.strip() if result.returncode==0 else 'unknown'


def issue(config,now=None,expiry=None,service=None):
    now=time.time() if now is None else now
    try:
        expiry=certificate_expiry(config['expectedIp']) if expiry is None else expiry
    except (OSError,ssl.SSLError,ValueError,KeyError,TimeoutError) as error:
        return 'TLS_INVALID_'+type(error).__name__,None
    service=renewal_result() if service is None else service
    if service!='success':return 'RENEWAL_SERVICE_'+re.sub('[^A-Za-z0-9_-]','_',service)[:40],expiry
    if expiry-now<=config['warningHours']*3600:return 'CERT_EXPIRES_SOON',expiry
    return None,expiry


def send_mail(config,subject,body):
    secret=private_file(config['smtpSecretFile'],256).read_text(encoding='ascii').strip()
    if not 8<=len(secret)<=128 or any(c.isspace() for c in secret):
        raise ValueError('SMTP_AUTH_CODE_FORMAT_INVALID')
    message=EmailMessage()
    message['From']=config['smtpUser'];message['To']=config['recipient'];message['Subject']=subject
    message.set_content(body)
    with smtplib.SMTP_SSL('smtp.qq.com',465,context=ssl.create_default_context(),timeout=20) as smtp:
        smtp.login(config['smtpUser'],secret)
        smtp.send_message(message)


def save_state(path,value):
    path=Path(path);path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    if any(x.is_symlink() for x in (path,path.parent)):
        raise ValueError('ALERT_STATE_SYMLINK_FORBIDDEN')
    tmp=path.with_name(path.name+'.'+secrets.token_hex(8)+'.tmp')
    try:
        with tmp.open('x',encoding='utf-8') as stream:
            os.chmod(tmp,0o600)
            json.dump(value,stream,sort_keys=True)
            stream.flush();os.fsync(stream.fileno())
        os.replace(tmp,path)
    finally:tmp.unlink(missing_ok=True)


def run(config,mode,*,now=None,expiry=None,service=None,mailer=send_mail):
    now=time.time() if now is None else now
    if mode=='test-email':
        mailer(config,'LightTry TLS 告警测试','这是证书监控的测试邮件，不代表证书故障。')
        return 'TEST_EMAIL_SENT'
    current,valid_until=issue(config,now,expiry,service)
    if mode=='check-only':return 'HEALTHY' if current is None else current
    state_path=Path(config['stateFile'])
    previous=json.loads(private_file(state_path,4096).read_text(encoding='utf-8')) if state_path.exists() else {}
    if current is None:
        if previous.get('issue'):save_state(state_path,{'issue':None,'sentAt':0})
        return 'HEALTHY'
    if previous.get('issue')==current and now-previous.get('sentAt',0)<86400:
        return 'ALERT_ALREADY_SENT'
    expiry_text=time.strftime('%Y-%m-%d %H:%M:%S UTC',time.gmtime(valid_until)) if valid_until else 'unknown'
    body=('LightTry HTTPS 证书需要检查。\n'
          '问题代码：'+current+'\n'
          '证书失效时间：'+expiry_text+'\n'
          '目标 IP：'+config['expectedIp']+'\n'
          '请检查 Certbot、Nginx 和续期计时器；本邮件不包含任何访问密钥。\n')
    mailer(config,'LightTry TLS 告警：'+current,body)
    save_state(state_path,{'issue':current,'sentAt':now})
    return 'ALERT_SENT'


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('mode',choices=('check-only','test-email','run'))
    parser.add_argument('--config',default='/etc/lighttry/cert-alert.json')
    args=parser.parse_args(argv)
    try:print(run(load_config(args.config),args.mode))
    except Exception as error:
        print('CERT_ALERT_ERROR_'+type(error).__name__)
        return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
