"""Validated executor stage evidence -> existing product task records (no cloud I/O)."""
import copy
import io
import math
from pathlib import Path
import shutil
import tarfile
import time
import uuid

from .jobs import ID, RUN_CONFIG, JobError, atomic, read
from .images import digest, decode, MAX_BYTES
from .reuse import safe_file, identity, validate
from .batch import validate_forward_result

WORKSPACE = Path(__file__).resolve().parents[2]


def canonical(request):
    value = copy.deepcopy(request)
    value['input'] = {k:v for k,v in value['input'].items() if k not in ('name','url','originalUrl')}
    return value


def evidence_items(folder, request, presets, run_id):
    """Only transferred/validated stage evidence can publish a per-preset result."""
    evidence = folder/'remote-evidence'
    configuration = read(safe_file(evidence, 'configuration.json'))
    if configuration['request'] != canonical(request):
        raise ValueError('BATCH_CONFIGURATION_MISMATCH')
    weights = read(WORKSPACE/'manifests/weights_manifest.json')
    patch = read(WORKSPACE/'manifests/patch_manifest.json')
    value = identity(request, safe_file(folder,'inputs/photo.png').read_bytes(), weights, patch)
    inverse = validate(evidence/'inverse', value)
    if request.get('requiredInverseReuse') is not None and request['requiredInverseReuse'] != {'key':inverse['key'],'source':inverse['source']}:
        raise ValueError('REQUIRED_INVERSE_SOURCE_MISMATCH')
    forward_model = [e for e in weights['files'] if not e['path'].startswith('Diffusion_Renderer_Inverse_Cosmos_7B/')]
    items = {}
    for preset in request.get('presets', [request['preset']]):
        if presets.get(preset['id']) != preset:
            raise ValueError('BATCH_PRESET_MAPPING_MISMATCH')
        directory = evidence/'presets'/str(preset['index'])
        state = read(safe_file(directory,'state.json'))
        if state['status'] not in ('pending','running','succeeded','failed'):
            raise ValueError('INVALID_PRESET_STATE')
        item = {'preset':preset,'status':state['status'],'result':None,'error':None}
        marker = directory/'complete.json'
        if marker.exists():
            record = read(safe_file(directory,'complete.json'))
            expected = {'inverseKey':inverse['key'],'inverseArtifacts':inverse['artifacts'],
                'request':{'taskId':request['taskId'],'nonce':request['nonce'],'inputId':request['input']['id'],
                    'inputSha256':request['input']['sha256'],'originalSha256':request['original']['sha256']},
                'forwardModel':forward_model,'patch':patch,'config':request['runConfig'],'hdr':preset,
                'randomPolicy':'reset-before-forward-generate-v1'}
            if record['identity'] != expected or not ID.fullmatch(record['attempt']):
                raise ValueError('BATCH_RESULT_IDENTITY_MISMATCH')
            if record['source']['presetIndex'] != preset['index'] or not ID.fullmatch(record['source']['process']):
                raise ValueError('BATCH_RESULT_SOURCE_MISMATCH')
            when = record['completedEpoch']
            if not isinstance(when,(float,int)) or not math.isfinite(when) or when <= 0:
                raise ValueError('INVALID_GENERATION_TIME')
            if record['seed'] != request['runConfig']['seed'] or record['randomPolicy'] != expected['randomPolicy']:
                raise ValueError('BATCH_RANDOM_POLICY_MISMATCH')
            raw = safe_file(directory/record['attempt'],record['result']['path']).read_bytes()
            if digest(raw)!=record['result']['sha256'] or len(raw)!=record['result']['bytes']:
                raise ValueError('BATCH_RESULT_HASH_MISMATCH')
            try:
                output = validate_forward_result(directory/record['attempt'])
            except OSError as error:
                raise ValueError('BATCH_RESULT_DECODE_MISMATCH') from error
            if output != record['result'] or not output['path'].startswith(f"relit_frames_{preset['index']:04d}/"):
                raise ValueError('BATCH_RESULT_HASH_MISMATCH')
            target = folder/'results'/f"{preset['id']}.jpg"
            if target.parent.is_symlink() or getattr(target.parent,'is_junction',lambda:False)() or not target.parent.resolve().is_relative_to(folder.resolve()):
                raise ValueError('UNSAFE_PRODUCT_RESULT_DIRECTORY')
            target.parent.mkdir(exist_ok=True)
            payload = safe_file(directory/record['attempt'],output['path']).read_bytes()
            if target.exists():
                if digest(safe_file(folder,f"results/{preset['id']}.jpg").read_bytes()) != output['sha256']:
                    raise ValueError('PRODUCT_RESULT_CONTENT_CONFLICT')
            else:
                temporary = target.with_suffix('.'+uuid.uuid4().hex+'.tmp')
                temporary.write_bytes(payload); temporary.replace(target)
            base = f"/api/tasks/{request['taskId']}/presets/{preset['id']}"
            item.update(status='succeeded', result={'taskId':request['taskId'],'inputId':request['input']['id'],
                'presetId':preset['id'],'url':base+'/result','downloadUrl':base+'/download',
                'regionUrl':base+'/result-region','regionDownloadUrl':base+'/download-region',
                'width':1280,'height':704,'sha256':output['sha256'],'bytes':output['bytes'],
                'generatedAt':when,'source':{'taskId':request['taskId'],'runId':run_id,**record['source']},
                'inverseReuse':{'reused':inverse['source']['taskId'] != request['taskId'],
                    'sourceTaskId':inverse['source']['taskId'],'key':inverse['key']}})
        elif state['status'] == 'succeeded':
            raise ValueError('PRESET_COMPLETION_MARKER_MISSING')
        elif state['status'] == 'failed':
            item['error'] = {'code':'PRESET_FAILED','message':'该灯光生成失败：'+str(state.get('error','执行端失败'))[:120]}
        items[preset['id']] = item
    return items


def verify_product_file(folder, item):
    result = item['result']
    path = safe_file(folder,f"results/{item['preset']['id']}.jpg")
    data = path.read_bytes()
    if digest(data) != result['sha256'] or len(data) != result['bytes']:
        raise ValueError('PRODUCT_RESULT_HASH_MISMATCH')
    rgb, _, _ = decode(data,'image/jpeg')
    from PIL import ImageStat
    if rgb.size != (1280,704) or max(ImageStat.Stat(rgb).stddev) < .5:
        raise ValueError('PRODUCT_RESULT_DECODE_MISMATCH')
    return data


def register_local(store, relative_job, run_id, original_task_id):
    """CLI-only import from workspace/.local; exact archived request and input bind run."""
    if not all(isinstance(x,str) and ID.fullmatch(x) for x in (run_id,original_task_id)):
        raise ValueError('INVALID_SOURCE_ID')
    # safe_file rejects traversal, symlinks/junctions and Windows drive paths.
    request_path = safe_file(WORKSPACE/'.local',relative_job+'/request.json')
    source = request_path.parent
    request = read(request_path)
    if not ID.fullmatch(request['taskId']) or not ID.fullmatch(request['nonce']):
        raise ValueError('INVALID_EXECUTION_ID')
    if any(request['runConfig'].get(k) != v for k,v in RUN_CONFIG.items()):
        raise ValueError('EXECUTION_CONFIG_MISMATCH')
    selected = request.get('presets',[request['preset']])
    if not 1 <= len(selected) <= 3 or len({p['id'] for p in selected}) != len(selected):
        raise ValueError('INVALID_PRESET_LIST')
    run = WORKSPACE/'cloud-runs'/run_id
    bundle = read(safe_file(run,'bundle.json'))
    archive = safe_file(run,'inference-code.tar.gz')
    if digest(archive.read_bytes()) != bundle['sha256']:
        raise ValueError('RUN_ARCHIVE_HASH_MISMATCH')
    with tarfile.open(archive) as tar:
        member = tar.getmember('request.json')
        if not member.isfile() or member.size > 1024*1024:
            raise ValueError('RUN_REQUEST_INVALID')
        import json
        archived = json.load(tar.extractfile(member))
    if canonical(archived) != canonical(request):
        raise ValueError('RUN_TASK_IDENTITY_MISMATCH')
    import json
    launched = json.loads(read(safe_file(run,'launch-result.json'))['output'])
    if not str(launched.get('prep','')).endswith('/preview-'+run_id):
        raise ValueError('RUN_DESTINATION_MISMATCH')
    event = read(safe_file(source,'execution.json'))
    if (event.get('taskId'),event.get('nonce'),event.get('executionStopped')) != (request['taskId'],request['nonce'],True) or event.get('status') not in ('succeeded','failed'):
        raise ValueError('EXECUTION_NOT_CONFIRMED_STOPPED')
    original = safe_file(store.directory(original_task_id),'original').read_bytes()
    if digest(original) != request['original']['sha256']:
        raise ValueError('ORIGINAL_INPUT_MISMATCH')
    prepared = safe_file(source,'inputs/photo.png').read_bytes()
    if digest(prepared) != request['input']['sha256']:
        raise ValueError('PREPARED_INPUT_MISMATCH')
    receipt = read(safe_file(source,'receipt.json')) if (source/'receipt.json').exists() else None
    if receipt is None and event['status']=='succeeded': raise ValueError('SUCCESS_RECEIPT_REQUIRED')
    for name, expected in {'taskId':request['taskId'],'nonce':request['nonce'],'inputId':request['input']['id'],
            'presetId':request['preset']['id'],'inputSha256':request['input']['sha256'],
            'originalSha256':request['original']['sha256'],'runConfig':request['runConfig']}.items():
        if receipt is not None and receipt.get(name) != expected: raise ValueError('RECEIPT_IDENTITY_MISMATCH')
    binding = {'runId':run_id,'requestSha256':digest(request_path.read_bytes()),'archiveSha256':bundle['sha256']}
    with store.mutex:
        target = store.root/request['taskId']
        if target.is_symlink() or getattr(target,'is_junction',lambda:False)():
            raise ValueError('UNSAFE_PRODUCT_TASK_DIRECTORY')
        # Validate in an unpublished directory, including idempotent re-registration.
        stage = store.root/('.register-'+uuid.uuid4().hex)
        stage.mkdir()
        try:
            (stage/'inputs').mkdir(); (stage/'inputs/photo.png').write_bytes(prepared)
            (stage/'original').write_bytes(original)
            atomic(stage/'request.json',request)
            if receipt is not None: atomic(stage/'receipt.json',receipt)
            atomic(stage/'source-execution.json',event)
            total = 0
            for path in (source/'remote-evidence').rglob('*'):
                if path.is_dir():
                    if path.is_symlink() or getattr(path,'is_junction',lambda:False)(): raise ValueError('UNSAFE_EVIDENCE_DIRECTORY')
                    continue
                checked = safe_file(source,path.relative_to(source).as_posix())
                total += checked.stat().st_size
                if total > 512*1024**2: raise ValueError('EVIDENCE_TOO_LARGE')
                dest = stage/path.relative_to(source); dest.parent.mkdir(parents=True,exist_ok=True)
                dest.write_bytes(checked.read_bytes())
            items = evidence_items(stage,request,store.presets,run_id)
            if not any(x['status']=='succeeded' for x in items.values()): raise ValueError('NO_COMPLETED_RESULTS')
            primary=items[request['preset']['id']]['result']
            if primary and receipt is not None and (receipt.get('file')!='result.jpg' or receipt.get('sha256')!=primary['sha256'] or receipt.get('bytes')!=primary['bytes']):
                raise ValueError('PRIMARY_RECEIPT_HASH_MISMATCH')
            if event['status']=='succeeded' and receipt.get('processExitCodes') not in ([None,0],[0,0]): raise ValueError('RECEIPT_EXECUTION_INCOMPLETE')
            binding['results'] = {p:i['result']['sha256'] for p,i in items.items() if i['result']}
            binding['itemsSha256']=digest(json.dumps(items,sort_keys=True,separators=(',',':')).encode())
            if target.exists():
                previous = read(safe_file(target,'task.json'))
                if previous.get('registration') != binding: raise ValueError('REGISTRATION_IDENTITY_CONFLICT')
                for item in items.values():
                    if item['result']: verify_product_file(target,item)
                return store.public(store._refresh(target))
            now = store.clock()
            statuses = [i['status'] for i in items.values()]
            task = {**request,'presets':selected,'presetResults':items,'status':'succeeded' if all(s=='succeeded' for s in statuses) else 'partial',
                'stage':None,'result':items[request['preset']['id']]['result'],'error':None,
                'createdAt':min(i['result']['generatedAt'] for i in items.values() if i['result']),
                'updatedAt':now,'expiresAt':now+store.retention,'registeredAt':now,'registration':binding,
                'requestId':request['taskId'],'fingerprint':digest(request_path.read_bytes()),'executionUncertain':False}
            task['input'].update(url=f"/api/tasks/{request['taskId']}/input",originalUrl=f"/api/tasks/{request['taskId']}/original")
            atomic(stage/'task.json',task)
            stage.rename(target)  # one atomic publication, never overwrite an existing task
            return store.public(task)
        finally:
            # Only this unpublished, freshly-created staging directory is disposable.
            if stage.exists(): shutil.rmtree(stage)
