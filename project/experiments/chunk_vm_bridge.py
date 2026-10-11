"""Native-SSH memory bridge; reuse the tested container selection and markers."""
import base64, hashlib, json, os, pwd, re, subprocess, sys


def main(req):
    if pwd.getpwuid(os.getuid()).pw_name != req['ssh_user']:
        raise ValueError('VM_USER_MISMATCH')
    probe = {'__name__': 'local_reused_probe'}
    exec(compile(base64.b64decode(req['probe_source']), '<reused-probe>', 'exec'), probe)
    ids = probe['docker']('ps', '-q', '--no-trunc').split()
    if not ids or len(ids) > 32 or any(not re.fullmatch('[0-9a-f]{64}', i) for i in ids):
        raise ValueError('NO_VALID_RUNNING_CONTAINERS')
    cid = probe['choose_container'](json.loads(probe['docker']('inspect', *ids)), req['image'])
    report = dict(nonce=req['nonce'], operation=req['operation'], container_id=cid,
                  image=req['image'], container_user='jovyan', container_home='/home/jovyan')
    if not re.fullmatch(r'[A-Za-z0-9_-]+\.tar\.gz', req['archive_filename']):
        raise ValueError('INVALID_ARCHIVE_NAME')
    if req['operation'] == 'upload_directory':
        path = '/home/'+req['ssh_user']+'/nebius-upload-'+req['run_id']
        if not re.fullmatch('[0-9a-f]{32}', req['run_id']):
            raise ValueError('INVALID_RUN_ID')
        os.mkdir(path)
        report['output'] = json.dumps(dict(upload_directory=path))

    elif req['operation'] == 'export_control_chunk':
        if not re.fullmatch('[0-9a-f]{32}', req['run_id']): raise ValueError('INVALID_RUN_ID')
        part=req['control_part'];source_id=req['source_run_id']
        if part not in ('metadata','pair0','pair1','pair2','case0','case1','case2','case3','case4','case5') or not re.fullmatch('[0-9a-f]{32}',source_id):
            raise ValueError('INVALID_CONTROL_CHUNK_IDENTITY')
        q=req['container_request']
        if q.get('part')!=part or not q.get('root','').endswith('/preview-'+source_id+'/run'):
            raise ValueError('CONTROL_SOURCE_BINDING_MISMATCH')
        path='/home/'+req['ssh_user']+'/nebius-upload-'+req['run_id']+'/control-canonical-'+source_id+'-'+part+'.tar.gz'
        request_hash=hashlib.sha256(json.dumps(q,sort_keys=True).encode()+base64.b64decode(req['container_program'])).hexdigest()
        receipt_path=path+'.receipt.json'
        if os.path.exists(path):
            if not os.path.isfile(receipt_path):raise ValueError('PRESERVE_UNCONFIRMED_CHUNK_NO_OVERWRITE')
            prior=json.load(open(receipt_path))
            h=hashlib.sha256(open(path,'rb').read()).hexdigest()
            if prior['request_hash']!=request_hash or prior['sha256']!=h or prior['bytes']!=os.stat(path).st_size:
                raise ValueError('EXISTING_CHUNK_IDENTITY_CHANGED')
            report['output']=json.dumps({k:prior[k] for k in ('remote_path','sha256','bytes')})
            print('LOCAL_RESULT_'+req['nonce']+':'+json.dumps(report,separators=(',',':')))
            print('LOCAL_DONE_'+req['nonce']);return
        command=['sudo','-n','docker','exec','-i','-u','jovyan','-w','/home/jovyan',cid,
                 req['container_python'],'-B','-c',
                 base64.b64decode(req['container_program']).decode(),
                 base64.b64encode(json.dumps(req['container_request']).encode()).decode()]
        with open(path,'xb') as f:
            r=subprocess.run(command,stdin=subprocess.DEVNULL,stdout=f,stderr=subprocess.PIPE,timeout=90)
        if r.returncode: raise ValueError('RESULT_EXPORT_FAILED_EXIT_'+str(r.returncode))
        h=hashlib.sha256()
        with open(path,'rb') as f:
            for block in iter(lambda:f.read(8*1024**2),b''):h.update(block)
        metadata={'remote_path':path,'sha256':h.hexdigest(),'bytes':os.stat(path).st_size}
        if metadata['bytes']>163840:raise ValueError('CHUNK_EXCEEDS_SIZE_BOUND')
        with open(receipt_path,'x') as f:json.dump(dict(metadata,request_hash=request_hash),f)
        report['output']=json.dumps(metadata)

    else:
        command = ['sudo','-n','docker','exec','-i','-u','jovyan','-w','/home/jovyan',cid,
                   req['container_python'],'-B','-c',
                   base64.b64decode(req['container_program']).decode(),
                   base64.b64encode(json.dumps(req.get('container_request',{})).encode()).decode()]
        stdin = subprocess.DEVNULL
        stream = None
        if req['operation'] == 'install_bundle':
            path = '/home/'+req['ssh_user']+'/nebius-upload-'+req['run_id']+'/'+req['archive_filename']
            if not re.fullmatch('[0-9a-f]{32}', req['run_id']):
                raise ValueError('INVALID_RUN_ID')
            h = hashlib.sha256()
            with open(path,'rb') as f:
                for chunk in iter(lambda:f.read(8*1024*1024),b''): h.update(chunk)
            if h.hexdigest() != req['archive_sha256']:
                raise ValueError('VM_ARCHIVE_HASH_MISMATCH')
            stream = open(path,'rb'); stdin = stream
        try:
            result = subprocess.run(command, stdin=stdin, capture_output=True, text=True, timeout=90)
        finally:
            if stream: stream.close()
        if result.returncode:
            # Only the allowlisted numeric failure escapes. Never dump docker
            # inspect, environment variables or arbitrary stderr.
            public_labels=[line for line in result.stderr.splitlines()
                           if re.fullmatch(r'SMOKE_[A-Z0-9_]{1,110}',line)]
            if len(public_labels)==1:
                raise ValueError(public_labels[0])
            raise ValueError('CONTAINER_STAGE_FAILED_EXIT_'+str(result.returncode))
        report['output'] = result.stdout
    print('LOCAL_RESULT_'+req['nonce']+':'+json.dumps(report,separators=(',',':')))
    print('LOCAL_DONE_'+req['nonce'])


if __name__ == '__main__':
    try: main(json.loads(base64.b64decode(sys.argv[1])))
    except Exception as exc:
        label = str(exc)
        if not re.fullmatch('[A-Z0-9_]+', label): label='VM_BRIDGE_FAILED_'+type(exc).__name__
        print(label,file=sys.stderr); sys.exit(3)
