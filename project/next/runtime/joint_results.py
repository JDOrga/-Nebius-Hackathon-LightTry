"""Immutable per-case export, identity/decode checks and local comparison page."""
import base64
import gzip
import hashlib
import html
import io
import json
from pathlib import Path,PurePosixPath
import sys
import tarfile
import time
if '__file__' in globals():
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
else:  # existing native transport executes the reviewed program via python -c
    q=json.loads(base64.b64decode(sys.argv[1]))
    prep=Path(q['root']).resolve().parent
    if not prep.is_relative_to('/home/jovyan'):raise ValueError('PERSISTENT_EXPORT_SOURCE_REQUIRED')
    sys.path.insert(0,str(prep/'project'))
from inference.jobs import atomic,read
from inference.batch import validate_forward_result
from inference.reuse import safe_file
from lighting import identity
from light_console import preprocessing_parameters

PARTS={'case'+str(i):name for i,name in enumerate('ABCDEF')};PARTS['pair0']='AI'

def payload(root,part):
    started=time.perf_counter()
    files=[]
    if part=='metadata':
        for name in ('execution.json','configuration.json','preflight.json','weights_verification.json','forward-timing.jsonl','export-timing.jsonl'):
            if (root/name).is_file():files.append(safe_file(root,name))
    elif part in PARTS:
        directory=root/'cases'/PARTS[part]
        marker=directory/'0/complete.json'
        if not marker.exists():raise ValueError('CASE_NOT_ATOMICALLY_COMPLETED')
        record=read(safe_file(directory,'0/complete.json'))
        attempt=directory/'0'/record['attempt']
        actual=validate_forward_result(attempt)
        actual.update(conditionProofSha256=hashlib.sha256(safe_file(directory,'condition.json').read_bytes()).hexdigest(),
            modelProofSha256=hashlib.sha256(safe_file(directory,'model-condition.json').read_bytes()).hexdigest())
        if actual!=record['result']:raise ValueError('EXPORT_RESULT_MISMATCH')
        files=[safe_file(directory,'0/complete.json'),safe_file(directory,'condition.json'),
            safe_file(directory,'model-condition.json'),safe_file(attempt,record['result']['path'])]
    else:raise ValueError('JOINT_EXPORT_PART_INVALID')
    stream=io.BytesIO()
    with gzip.GzipFile(fileobj=stream,mode='wb',mtime=0) as gz,tarfile.open(fileobj=gz,mode='w|') as tar:
        for path in files:
            name=path.relative_to(root).as_posix();data=path.read_bytes()
            info=tarfile.TarInfo(name);info.size=len(data);tar.addfile(info,io.BytesIO(data))
    data=stream.getvalue()
    if len(data)>163840:raise ValueError('JOINT_CHUNK_EXCEEDS_EXISTING_TRANSPORT_BOUND')
    ended=time.perf_counter()
    with (root/'export-timing.jsonl').open('a',encoding='utf-8') as ledger:
        ledger.write(json.dumps({'event':'export_end','part':part,'monotonicStart':started,
            'monotonicEnd':ended,'seconds':ended-started,'bytes':len(data)})+'\n')
    return data

def extract(archive,target,expected_hash):
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=expected_hash:raise ValueError('DOWNLOAD_CONTENT_HASH_MISMATCH')
    with tarfile.open(archive,'r:gz') as tar:
        members=tar.getmembers()
        if sum(m.size for m in members)>4*1024**2:raise ValueError('CHUNK_EXPANSION_LIMIT')
        names=set()
        for m in members:
            p=PurePosixPath(m.name)
            if not m.isfile() or p.is_absolute() or '..' in p.parts or ':' in m.name or '\\' in m.name or m.name in names:
                raise ValueError('UNSAFE_JOINT_RESULT_MEMBER')
            names.add(m.name)
            dst=target.joinpath(*p.parts)
            if any(x.is_symlink() for x in (dst,*dst.parents)):raise ValueError('RESULT_SYMLINK')
            data=tar.extractfile(m).read()
            if dst.exists() and dst.read_bytes()!=data:raise ValueError('PRESERVE_PRIOR_RESULT_NO_OVERWRITE')
            dst.parent.mkdir(parents=True,exist_ok=True)
            if not dst.exists():dst.write_bytes(data)

def validate_case(packet,root,case):
    plan=read(packet/'joint.json');directory=root/'cases'/case['id']
    completed=read(safe_file(directory,'0/complete.json'));binding=completed['identity']
    if (binding.get('case')!=case or binding.get('jointPlanKey')!=identity(plan) or
        binding.get('taskId')!=plan['taskId'] or binding.get('nonce')!=plan['nonce']):
        raise ValueError('TASK_RECIPE_COMPLETION_IDENTITY_MISMATCH')
    result=validate_forward_result(directory/'0'/completed['attempt'])
    result.update(conditionProofSha256=hashlib.sha256(safe_file(directory,'condition.json').read_bytes()).hexdigest(),
        modelProofSha256=hashlib.sha256(safe_file(directory,'model-condition.json').read_bytes()).hexdigest())
    if result!=completed['result']:raise ValueError('RETRIEVED_FRAME_HASH_MISMATCH')
    condition=read(safe_file(directory,'condition.json'));model=read(safe_file(directory,'model-condition.json'))
    if (condition['hdrSha256']!=case['hdrSha256'] or condition['parameters']!=preprocessing_parameters(case['parameters']) or
        condition['loaderHookEffective'] is not True or condition.get('device')!='cuda'):raise ValueError('ACTUAL_HDR_PROOF_MISMATCH')
    for name in ('env_ldr','env_log','env_nrm'):
        if model[name].get('finite') is not True or model[name]['shape']!=[1,3,1,704,1280] or not -1.00001<=model[name]['min']<=model[name]['max']<=1.00001:
            raise ValueError('ACTUAL_CONDITION_PROOF_MISMATCH')
    return {'caseId':case['id'],'status':'structure-passed','visual':'pending human review',
        'path':str((directory/'0'/completed['attempt']/result['path']).resolve()),'sha256':result['sha256']}

def comparison(packet,target,root):
    plan=read(packet/'joint.json');items=[];records=[]
    if plan.get('version')=='direction-energy-calibration-five-v2':
        from next.runtime.calibration import comparison_page
        comparison_page(packet,target,root)
        return [validate_case(packet,root,c) for c in plan['cases'] if root and (root/'cases'/c['id']/'0/complete.json').exists()]
    for case in plan['cases']:
        state='尚未运行';source='';image=''
        if root and (root/'cases'/case['id']/'0/complete.json').exists():
            result=validate_case(packet,root,case);records.append(result);state='结构通过；视觉待人工判断'
            image='<img src="'+html.escape(Path(result['path']).as_uri(),quote=True)+'" width="640">'
        items.append('<section><h2>'+case['id']+' — '+state+'</h2>'+image+'<p>'+html.escape(case['source']+'; '+case['comparison'])+'</p><pre>'+html.escape(json.dumps(case['parameters'],ensure_ascii=False,indent=2))+'</pre><p>recipeKey '+case['recipeKey']+'; HDR SHA '+case['hdrSha256']+'</p></section>')
    target.write_text('<!doctype html><meta charset="utf-8"><title>LightTry 联合对照</title><style>body{font:16px sans-serif;max-width:1400px;margin:auto}section{border:1px solid #ccc;margin:16px;padding:16px}img{max-width:100%}</style><h1>参数化调光台联合验收</h1><p>坐标未校准：方位角不是照片左/右。结构通过≠可控或视觉通过。A/B 不属于单变量；C—F 对 B。</p><p>人工逐项：方向、明暗、高光、阴影、颜色、轮廓/主体保真；记录通过/失败/不确定及理由。不开展新的材质研究。角宽保持峰值强度，改变球面积总能量；不得据此宣称物理柔光。</p>'+''.join(items),encoding='utf-8')
    return records

def main(q):
    root=Path(q['root']).resolve();base=Path(q['data_root']).resolve()
    if not base.is_relative_to('/home/jovyan') or not root.is_relative_to(base) or root.name!='run':raise ValueError('EXACT_JOINT_ROOT_REQUIRED')
    sys.stdout.buffer.write(payload(root,q['part']))

if __name__=='__main__':main(json.loads(base64.b64decode(sys.argv[1])))
