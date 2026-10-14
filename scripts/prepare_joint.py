"""Freeze a fresh local joint packet; no keys, API, uploads or GPU."""
import argparse
import copy
import hashlib
import io
from pathlib import Path
import shutil
import sys
import tarfile
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'project'))
from inference.jobs import atomic,read
from runtime.driver import BUNDLE_FILES
from runtime.joint import matrix,changes,energy,VERSION,verify_joint
from experiments.worker import verify_packet
from light_console import synthesize,encode_hdr,decode_hdr
from lighting import identity

def freeze(packet, output):
    entries=[]
    for path in sorted(packet.rglob('*')):
        if path.is_file() and path.name!='bundle_contents.json':
            entries.append({'path':path.relative_to(packet).as_posix(),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size})
    atomic(packet/'bundle_contents.json',{'files':entries})
    verify_packet(packet);verify_joint(packet)
    archive=output/'inference-code.tar.gz'
    with archive.open('xb') as stream,tarfile.open(fileobj=stream,mode='w:gz') as tar:
        for path in sorted(packet.rglob('*')):
            if path.is_file():tar.add(path,arcname=path.relative_to(packet).as_posix(),recursive=False)
    atomic(output/'bundle.json',{'archive':'inference-code.tar.gz','archive_path':str(archive.resolve()),'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'bytes':archive.stat().st_size})

def prepare(output, applied=None):
    output.mkdir();packet=output/'packet';packet.mkdir()
    source=ROOT/'.local/lighttry-development-20261011/matte-frozen-v2/packet'
    # Validate unchanged historical provenance BEFORE copying anything.
    historical=verify_packet(source)
    for name in ('proof','inverse','inputs','weight-reference'):
        shutil.copytree(source/name,packet/name)
    names=set(BUNDLE_FILES)|{'project/experiments/worker.py','project/runtime/joint.py',
        'project/runtime/joint_entry.py','project/runtime/joint_worker.py',
        'project/runtime/joint_launch.py','project/runtime/joint_inspect.py',
        'project/runtime/joint_results.py','project/runtime/joint_bundle.py','project/runtime/key_unknowns.py','project/runtime/calibration.py','project/runtime/joint_watch.py','project/runtime/status_stream.py','cloud/Prepare-JointWatch.ps1','cloud/joint_watch_bridge.py','cloud/Retrieve-JointBundle.ps1','cloud/joint_bundle_bridge.py','cloud/install_bundle.py'}
    for name in sorted(names):
        dst=packet/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,dst)
    envs={e['id']:e for e in read(ROOT/'project/runtime/environments.json')}
    recipes=matrix(envs);records=[]
    if applied:
        value=read(applied)
        from runtime.joint_language import verify_applied
        verify_applied(value)
        if value.get('photoBinding',{}).get('inputSha256')!=historical['input']['sha256']:
            raise ValueError('REAL_AI_PHOTO_REFERENCE_MISMATCH')
        recipes['AI']=value['parameters'];shutil.copyfile(applied,packet/'ai-applied.json')
    for name,recipe in recipes.items():
        record={'id':name,'parameters':recipe,'recipeKey':identity(recipe),
            'comparison':'A vs B: different input sources, not single-factor' if name=='A' else
                ('baseline' if name=='B' else 'vs B: '+str(changes(recipes['B'],recipe))),
            'source':'real confirmed Nemotron' if name=='AI' else 'bundled HDR' if name=='A' else 'manual procedural',
            'hdrFile':None,'hdrSha256':envs['sunny']['sha256']}
        if recipe['mode']=='procedural':
            image=synthesize(recipe);data=encode_hdr(image)
            rel='recipes/'+name+'.hdr';p=packet/rel;p.parent.mkdir(exist_ok=True);p.write_bytes(data)
            record.update(hdrFile=rel,hdrSha256=hashlib.sha256(data).hexdigest(),
                synthesizedEnergy=energy(image),encodedDecodedEnergy=energy(decode_hdr(data)))
        elif recipe['environmentId']!='sunny':raise ValueError('ONLY_APPROVED_EXISTING_SUNNY_ENVIRONMENT')
        records.append(record)
    joint={'version':VERSION,'taskId':uuid.uuid4().hex,'nonce':uuid.uuid4().hex,
        'cases':records,'status':'PREPARED_NOT_AUTHORIZED','inverseExecutionsTarget':0,
        'initializationsTarget':1,'forwardTarget':len(records),'input':historical['input'],
        'inverseSource':historical['inverseSource'],'runConfig':historical['runConfig'],
        'AIStatus':'confirmed real response' if applied else 'PENDING_REAL_RESPONSE_AND_EXPLICIT_APPLICATION'}
    atomic(packet/'joint.json',joint)
    # New preparation ledger; NEVER edits the historical plan/hashes.
    plan=copy.deepcopy(historical)
    plan['files']=[{'path':p.relative_to(packet).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
        for p in sorted(packet.rglob('*')) if p.is_file()]
    atomic(packet/'experiment.json',plan)
    freeze(packet,output)
    atomic(output/'preparation.json',joint)
    atomic(output/'execution-disabled.json',{'enabled':False,'model_license_ack':False,'guard_run_directory':'HOST_CURRENT_CONFIRMED_RUN',
        'jointTaskId':joint['taskId'],'jointPackageSha256':read(output/'bundle.json')['sha256']})
    from runtime.joint_results import comparison
    comparison(packet,output/'comparison.html',None)
    print('PREPARED_NOT_AUTHORIZED',str(output.resolve()),'inverse=0; forward='+str(len(records))+'; initialization target=1')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True);parser.add_argument('--ai-applied',type=Path)
    options=parser.parse_args();prepare(options.out.resolve(),options.ai_applied)
