"""Uses the reviewed remote_probe prelude in the SAME VM-memory SSH invocation."""
import ipaddress
import os
import hashlib
import base64
import json
import re
import subprocess
import sys
import http.client
import struct
import time


def private_container(items,image,inspect_network=None):
    cid=choose_container(items,image)  # Exact model image/user/RW-home selector remains.
    selected=next(v for v in items if v['Id']==cid)
    visited=set();item=selected
    for depth in range(5):
        if item['Id'] in visited:raise ValueError('CONTAINER_NETWORK_REFERENCE_CYCLE')
        visited.add(item['Id']);mode=item.get('HostConfig',{}).get('NetworkMode')
        if isinstance(mode,str) and mode.startswith('container:'):
            reference=mode.split(':',1)[1]
            if not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,127}',reference):raise ValueError('CONTAINER_NETWORK_REFERENCE_INVALID')
            candidates=[v for v in items if v.get('State',{}).get('Running') is True and
                (v.get('Id')==reference or v.get('Name','').lstrip('/')==reference or
                 re.fullmatch('[a-f0-9]{12,64}',reference) and v.get('Id','').startswith(reference))]
            if len(candidates)!=1:raise ValueError('CONTAINER_NETWORK_REFERENCE_NOT_UNIQUE')
            item=candidates[0];continue
        break
    else:raise ValueError('CONTAINER_NETWORK_REFERENCE_LIMIT')
    if mode=='host':return cid,'127.0.0.1'
    if mode in ('none',''):raise ValueError('CONTAINER_NETWORK_NOT_PRIVATE_BRIDGE')
    networks=item.get('NetworkSettings',{}).get('Networks',{})
    addresses=[(n,v) for n,v in networks.items() if v.get('IPAddress')]
    if len(addresses)!=1:raise ValueError('CONTAINER_NETWORK_NOT_UNIQUE')
    name,details=addresses[0];ip=ipaddress.ip_address(details['IPAddress'])
    if ip.version!=4 or not any(ip in ipaddress.ip_network(n) for n in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16')):raise ValueError('CONTAINER_NETWORK_NOT_PRIVATE')
    if mode not in ('bridge','default'):
        if (not isinstance(mode,str) or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,127}',mode) or
                name!=mode or inspect_network is None):raise ValueError('CONTAINER_NETWORK_NOT_PRIVATE_BRIDGE')
        inspected=inspect_network(mode)
        if (not isinstance(inspected,list) or len(inspected)!=1 or inspected[0].get('Name')!=mode or
                not re.fullmatch('[a-f0-9]{64}',str(details.get('NetworkID',''))) or inspected[0].get('Id')!=details['NetworkID']):raise ValueError('CONTAINER_NETWORK_IDENTITY_MISMATCH')
        network=inspected[0]
        if network.get('Driver')!='bridge' or network.get('Scope')!='local':raise ValueError('CONTAINER_NETWORK_DRIVER_UNSUPPORTED')
        subnets=[v.get('Subnet') for v in network.get('IPAM',{}).get('Config',[]) if v.get('Subnet')]
        if not any(ip in ipaddress.ip_network(n) for n in subnets):raise ValueError('CONTAINER_NETWORK_SUBNET_MISMATCH')
    return cid,str(ip)


def metadata_vm_id(deadline):
    # VM-local, credential-free identity field only. No proxy, redirect, IAM
    # token endpoint, public request, retry or hostname-as-ID fallback.
    bound=min(2,deadline-time.time())
    if bound<=0:raise ValueError('BOOTSTRAP_DEADLINE')
    connection=http.client.HTTPConnection('metadata.nebius.internal',timeout=bound)
    try:
        connection.request('GET','/v1/instance-data/id',headers={'Metadata':'true'})
        response=connection.getresponse();raw=response.read(129)
        if response.status!=200 or len(raw)>128:raise ValueError('VM_METADATA_UNAVAILABLE')
        identity=raw.decode('ascii').strip()
        if not re.fullmatch('computeinstance-[a-z0-9]+',identity):raise ValueError('VM_METADATA_UNAVAILABLE')
        return identity
    except Exception:
        raise ValueError('VM_METADATA_UNAVAILABLE') from None
    finally:connection.close()


def main(q):
    import pwd
    if pwd.getpwuid(os.getuid()).pw_name!=q['hostIdentity']['sshUser']:
        raise ValueError('CURRENT_VM_IDENTITY_MISMATCH')
    if time.time()>=q['deadline']:raise ValueError('BOOTSTRAP_DEADLINE')
    if metadata_vm_id(q['deadline'])!=q['hostIdentity']['vmId']:raise ValueError('VM_METADATA_ID_MISMATCH')
    sid=q['sessionId']
    if not re.fullmatch('[a-f0-9]{32}',sid):raise ValueError('SESSION_INVALID')
    ids=docker('ps','-q','--no-trunc').split()
    if not ids or len(ids)>32 or any(not re.fullmatch('[a-f0-9]{64}',x) for x in ids):raise ValueError('NO_VALID_RUNNING_CONTAINERS')
    cid,bind=private_container(json.loads(docker('inspect',*ids)),q['image'],
        inspect_network=lambda name:json.loads(docker('network','inspect',name)))
    root='/home/'+q['hostIdentity']['sshUser']+'/lighttry-bootstrap-'+sid
    if q['operation']=='prepare':
        os.mkdir(root,0o700)
        result={'sessionId':sid,'containerId':cid,'tlsBind':bind,'uploadDirectory':root,'observedAt':time.time()}
    elif q['operation']=='install':
        if cid!=q['containerId'] or bind!=q['tlsBind']:raise ValueError('CONTAINER_CHANGED_DURING_BOOTSTRAP')
        code=root+'/gpu-service.tar.gz';secret=root+'/session-secrets.tar.gz'
        def checked(path,expected,maximum):
            if os.path.islink(path):raise ValueError('BOOTSTRAP_UPLOAD_UNSAFE')
            with open(path,'rb') as f:raw=f.read(maximum+1)
            if len(raw)>maximum or hashlib.sha256(raw).hexdigest()!=expected:raise ValueError('VM_ARCHIVE_HASH_MISMATCH')
            return raw
        a=checked(code,q['codeSha256'],8*1024**2);b=checked(secret,q['secretSha256'],1024**2)
        payload=struct.pack('!Q',len(a))+a+struct.pack('!Q',len(b))+b
        command=['sudo','-n','docker','exec','-i','-u','jovyan','-w','/home/jovyan',cid,q['containerPython'],
            '-B','-c',base64.b64decode(q['installer']).decode(),base64.b64encode(json.dumps(q).encode()).decode()]
        remaining=min(20,q['deadline']-time.time())
        if remaining<=0:raise ValueError('BOOTSTRAP_DEADLINE')
        response=subprocess.run(command,input=payload,capture_output=True,timeout=remaining)
        if response.returncode:raise ValueError('CONTAINER_INSTALL_UNCERTAIN')
        result=json.loads(response.stdout)
    else:raise ValueError('BOOTSTRAP_OPERATION_NOT_ALLOWED')
    print(json.dumps(result,separators=(',',':')))


if __name__=='__main__':
    try:main(json.loads(base64.b64decode(sys.argv[1])))
    except Exception as error:
        label=str(error)
        if not re.fullmatch('[A-Z0-9_]{1,100}',label):label='BOOTSTRAP_VM_FAILED'
        print(label,file=sys.stderr);sys.exit(3)
