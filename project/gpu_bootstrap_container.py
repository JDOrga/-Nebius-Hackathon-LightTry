"""Fixed stdin installer/launcher executed as jovyan AFTER current SSH host approval."""
import base64
import gzip
import hashlib
import io
import json
import os
from pathlib import Path,PurePosixPath
import socket
import struct
import subprocess
import sys
import tarfile
import time


def unpack(raw,destination,expected=None,limit=8*1024**2):
    with gzip.GzipFile(fileobj=io.BytesIO(raw),mode='rb') as compressed:
        expanded=compressed.read(limit+1024**2+1)
    if len(expanded)>limit+1024**2:raise ValueError('BOOTSTRAP_EXPANSION_LIMIT')
    contents={}
    with tarfile.open(fileobj=io.BytesIO(expanded),mode='r:') as tar:
        for member in tar:
            name=member.name;p=PurePosixPath(name)
            if (len(contents)>=129 or not member.isfile() or p.is_absolute() or '..' in p.parts or
                '\\' in name or ':' in name or name in contents or member.size>2*1024**2 or
                sum(map(len,contents.values()))+member.size>limit):raise ValueError('BOOTSTRAP_ARCHIVE_UNSAFE')
            contents[name]=tar.extractfile(member).read()
    if expected is not None and set(contents)!=set(expected):raise ValueError('BOOTSTRAP_CONTENTS_MISMATCH')
    if expected is None:
        manifest=json.loads(contents['bundle_contents.json'])
        if set(contents)!={v['path'] for v in manifest['files']}|{'bundle_contents.json'}:raise ValueError('BOOTSTRAP_CONTENTS_MISMATCH')
        for item in manifest['files']:
            body=contents[item['path']]
            if len(body)!=item['bytes'] or hashlib.sha256(body).hexdigest()!=item['sha256']:raise ValueError('BOOTSTRAP_FILE_HASH_MISMATCH')
    destination.mkdir(mode=0o700)
    for name,body in contents.items():
        path=destination/name;path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        with path.open('xb') as stream:stream.write(body)
        path.chmod(0o600)
    return contents


def receive(stream,expected,maximum):
    length=stream.read(8)
    if len(length)!=8:raise ValueError('BOOTSTRAP_STREAM_TRUNCATED')
    size=struct.unpack('!Q',length)[0]
    if not 0<size<=maximum:raise ValueError('BOOTSTRAP_STREAM_LIMIT')
    raw=stream.read(size)
    if len(raw)!=size or hashlib.sha256(raw).hexdigest()!=expected:raise ValueError('BOOTSTRAP_ARCHIVE_HASH_MISMATCH')
    return raw


def install_files(q,stream,base):
    if time.time()>=q['deadline']:raise ValueError('BOOTSTRAP_DEADLINE')
    root=Path(base)/q['sessionId']
    if len(q['sessionId'])!=32 or any(c not in '0123456789abcdef' for c in q['sessionId']):raise ValueError('SESSION_INVALID')
    if any(p.is_symlink() for p in (root,*root.parents)):raise ValueError('BOOTSTRAP_ROOT_UNSAFE')
    root.mkdir(parents=True,mode=0o700)  # Exclusive; never relaunch an ambiguous install.
    code=receive(stream,q['codeSha256'],8*1024**2)
    secret=receive(stream,q['secretSha256'],1024**2)
    if stream.read(1):raise ValueError('BOOTSTRAP_EXTRA_INPUT')
    unpack(code,root/'code')
    unpack(secret,root/'secrets',{'worker.json','model-grant.json','tls.crt','tls.key','worker.token','launch.json'},limit=1024**2)
    secrets=root/'secrets';grant=json.loads((secrets/'model-grant.json').read_text())
    if (grant.get('sessionId')!=q['sessionId'] or grant.get('resourceId')!=q['resourceId'] or
        grant.get('hostIdentity')!=q['hostIdentity'] or grant.get('hostConfirmed') is not True or
        grant.get('modelLicenseAck') is not True or grant.get('expiresAt',0)>q['deadline'] or
        grant.get('expiresAt',0)<=time.time()):raise ValueError('BOOTSTRAP_GRANT_MISMATCH')
    worker=json.loads((secrets/'worker.json').read_text())
    if worker.get('enabled') is not True or worker.get('executionMode')!='resident':raise ValueError('RESIDENT_ENABLE_REQUIRED')
    worker['grantFile']=str(secrets/'model-grant.json');(secrets/'worker.json').write_text(json.dumps(worker));(secrets/'worker.json').chmod(0o600)
    # No public port: CPU connects through the pinned SSH container-private tunnel.
    import ipaddress
    address=ipaddress.ip_address(q['tlsBind'])
    if address.version!=4 or not any(address in ipaddress.ip_network(n) for n in ('127.0.0.0/8','10.0.0.0/8','172.16.0.0/12','192.168.0.0/16')):raise ValueError('PRIVATE_BIND_REQUIRED')
    with socket.socket() as probe:probe.bind((q['tlsBind'],q['tlsPort']))
    if time.time()>=q['deadline']:raise ValueError('BOOTSTRAP_DEADLINE')
    with (root/'launch-attempt').open('x'):pass
    command=[worker['python'],'-u','-B',str(root/'code/start.py'),'--worker','--data-root',str(root/'data'),
       '--session-id',q['sessionId'],'--resource-id',q['resourceId'],'--worker-token-file',str(secrets/'worker.token'),
       '--worker-config',str(secrets/'worker.json'),'--worker-tls-cert',str(secrets/'tls.crt'),'--worker-tls-key',str(secrets/'tls.key'),
       '--worker-tls-bind',q['tlsBind'],'--worker-tls-port',str(q['tlsPort'])]
    with (root/'worker.log').open('xb') as log:
        child=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
            cwd=root/'code',start_new_session=True,shell=False)
    result={'sessionId':q['sessionId'],'resourceId':q['resourceId'],'workerPid':child.pid,
            'codeSha256':q['codeSha256'],'tlsBind':q['tlsBind'],'tlsPort':q['tlsPort'],'launchRequested':True}
    (root/'launch.json').write_text(json.dumps(result));(root/'launch.json').chmod(0o600)
    return result


def install(q,stream):
    import pwd
    if pwd.getpwuid(os.getuid()).pw_name!='jovyan':raise ValueError('CONTAINER_USER_MISMATCH')
    return install_files(q,stream,Path('/home/jovyan/lighttry-service'))


if __name__=='__main__':
    try:print(json.dumps(install(json.loads(base64.b64decode(sys.argv[1])),sys.stdin.buffer)))
    except Exception as error:
        import re
        label=str(error)
        if not re.fullmatch('[A-Z0-9_]{1,100}',label):label='BOOTSTRAP_CONTAINER_FAILED'
        print(label,file=sys.stderr);sys.exit(3)
