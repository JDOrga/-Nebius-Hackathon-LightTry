"""Local default; explicit authorization dispatches once through existing guard."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'project'))
from inference.jobs import atomic,read
from runtime.driver import authorization
from runtime.joint import verify_joint
from runtime.joint_results import extract,comparison,validate_case,PARTS
from inference.timing import Timeline
from runtime.status_stream import observe

def shutdown(run,job,timing):
    """Early completion signals the pre-armed guard; independently verify release."""
    atomic(run/'complete.json',{'stop_required':True,'reason':'joint completed or failed; preserve results; no new launch'})
    try:
        with (job/'independent-stop.log').open('ab') as log:
            result=subprocess.run(['powershell.exe','-NoProfile','-File',str(ROOT/'cloud/Confirm-RunningStopped.ps1'),
                '-RunDirectory',str(run),'-Execute'],stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,timeout=120,shell=False)
        if result.returncode:raise ValueError('INDEPENDENT_STOPPED_UNVERIFIED_GUARD_REMAINS_ARMED')
        from weights import parse_deadline
        limit=min(time.time()+120,parse_deadline(timing['verification_target_utc']))
        while time.time()<limit:
            release,beat=read(run/'independent-stopped-release.json'),read(run/'heartbeat.json')
            pid=int(beat['pid'])
            if pid<=0:raise ValueError('GUARD_PID_INVALID')
            exited=subprocess.run(['powershell.exe','-NoProfile','-Command',
                f'if(Get-Process -Id {pid} -ErrorAction SilentlyContinue){{exit 1}}else{{exit 0}}'],capture_output=True,timeout=10).returncode==0
            if release.get('independent_api') is True and release['state']=='STOPPED' and release['instances']==[] and beat.get('stopped_verified') is True and beat.get('sleep_held') is False and exited:
                atomic(job/'stop-verification.json',{'independentRelease':release,'heartbeat':beat,'guardExited':True,'sleepReleased':True});return
            time.sleep(1)
        raise ValueError('GUARD_EXIT_OR_SLEEP_RELEASE_UNVERIFIED')
    except BaseException as error:
        atomic(job/'stop-unverified.json',{'error':str(error),'keepIndependentSupervision':True});raise

def consume_bundle(package,job,root,remote,metadata):
    """One local archive SHA plus one decode/identity pass; no remote recheck."""
    plan=read(package/'packet/joint.json')
    if remote['status'] not in ('succeeded','failed') or remote.get('executionStopped') is not True:
        raise ValueError('TERMINAL_STOPPED_WORKER_REQUIRED')
    if (metadata['taskId'],metadata['nonce'])!=(plan['taskId'],plan['nonce']):
        raise ValueError('BUNDLE_RESPONSE_IDENTITY_MISMATCH')
    archive=Path(metadata['local_path'])
    if archive.stat().st_size!=metadata['bytes']:raise ValueError('TRANSFER_BYTES_MISMATCH')
    extract(archive,root,metadata['sha256'])
    manifest=read(root/'retrieval-manifest.json')
    if (manifest['taskId'],manifest['nonce'],manifest['status'])!=(plan['taskId'],plan['nonce'],remote['status']):
        raise ValueError('BUNDLE_MANIFEST_IDENTITY_MISMATCH')
    snapshot=read(root/'execution.json')
    if (snapshot.get('taskId'),snapshot.get('nonce'),snapshot.get('status'),snapshot.get('executionStopped'))!=(plan['taskId'],plan['nonce'],remote['status'],True):
        raise ValueError('BUNDLE_EXECUTION_IDENTITY_MISMATCH')
    if manifest['completed']!=remote['completed']:raise ValueError('BUNDLE_COMPLETED_SET_MISMATCH')
    records=[]
    for case in plan['cases']:
        if case['id'] not in manifest['completed']:continue
        record=validate_case(package/'packet',root,case)
        atomic(job/(case['id']+'-retrieval.json'),record);records.append((case,record))
    import html
    sections=[]
    for case,record in records:
        sections.append('<section><h2>'+case['id']+' — 结构通过；视觉待判断</h2><img width="640" src="'+
            html.escape(Path(record['path']).as_uri(),quote=True)+'"><p>'+html.escape(case['source']+'; '+case['comparison'])+
            '</p><pre>'+html.escape(json.dumps(case['parameters'],ensure_ascii=False,indent=2))+'</pre><p>recipeKey '+
            case['recipeKey']+'; HDR SHA '+case['hdrSha256']+'</p></section>')
    (job/'comparison.html').write_text('<!doctype html><meta charset="utf-8"><h1>LightTry 整包取回</h1><p>方位坐标未校准；结构通过不等于视觉可控。角尺寸改变总能量，不能独立证明物理柔光。</p>'+''.join(sections),encoding='utf-8')
    if plan.get('version')=='direction-energy-calibration-five-v2':
        from runtime.calibration import finalize
        finalize(package)
    return {case['id'] for case,record in records}

def execute(package,config_path):
    plan=verify_joint(package/'packet');run,config,settings,timing,deadline=authorization(config_path)
    job=package/'execution';authorized=True
    try:
        job.mkdir() # no ambiguous launch replay
        timer=Timeline(job/'local-timing.jsonl','joint-driver')
        if config.get('jointPackageSha256')!=read(package/'bundle.json')['sha256'] or config.get('jointTaskId')!=plan['taskId']:
            raise ValueError('EXACT_JOINT_PACKAGE_AUTHORIZATION_REQUIRED')
        bundle=read(package/'bundle.json');data=(package/'inference-code.tar.gz').read_bytes()
        if hashlib.sha256(data).hexdigest()!=bundle['sha256']:raise ValueError('FROZEN_JOINT_ARCHIVE_CHANGED')
        for name in ('cloud/install_bundle.py','project/runtime/joint_launch.py',
            'project/runtime/joint_inspect.py','project/runtime/joint_results.py', 'project/runtime/joint_bundle.py',
            'cloud/Retrieve-JointBundle.ps1', 'cloud/joint_bundle_bridge.py',
            'cloud/Prepare-JointWatch.ps1', 'cloud/joint_watch_bridge.py',
            'project/runtime/joint_watch.py', 'project/runtime/status_stream.py'):
            if (ROOT/name).read_bytes()!=(package/'packet'/name).read_bytes():
                raise ValueError('TRANSPORT_PROGRAM_CHANGED_REPREPARE_BEFORE_START')
        for p in (run/'inference-code.tar.gz',run/'bundle.json'):
            if p.exists():raise ValueError('PRESERVE_EXISTING_GUARD_BUNDLE')
        shutil.copyfile(package/'inference-code.tar.gz',run/'inference-code.tar.gz')
        atomic(run/'bundle.json',{**bundle,'archive_path':str((run/'inference-code.tar.gz').resolve())})
        def call(operation,program=None,value=None,flag=None,part=None):
            authorization(config_path)
            if time.time()>=deadline:raise TimeoutError('FIXED_WORK_WINDOW_ENDED')
            args=['powershell.exe','-NoProfile','-File',str(ROOT/('cloud/Prepare-JointWatch.ps1' if operation=='prepare_watch' else 'cloud/Retrieve-JointBundle.ps1' if operation=='retrieve_joint_bundle' else 'cloud/Invoke-ScaleRemote.ps1')), '-RunDirectory',str(run),'-Execute']
            if operation not in ('retrieve_joint_bundle','prepare_watch'):args+=['-Operation',operation]
            if part:args+=['-SourceRunId',run.name,'-ControlPart',part]
            if program:args+=['-ContainerProgramPath',str(ROOT/program)]
            if value is not None:
                p=job/(operation+'-'+str(part)+'-request.json');atomic(p,value);args+=['-RequestPath',str(p)]
            if flag:args.append(flag)
            with timer.span('transfer' if flag else operation):
                with (job/(operation+'-'+str(part)+'.log')).open('ab') as log:
                    result=subprocess.run(args,stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,timeout=min(120,max(.1,deadline-time.time())),shell=False)
            if result.returncode:raise ValueError('GUARDED_TRANSPORT_FAILED_'+operation)
            if operation=='prepare_watch':return read(run/'watch-command.json')
            if operation=='retrieve_joint_bundle':return read(run/(operation+'-result.json'))
            if program:return json.loads(read(run/(operation+'-result.json'))['output'])
        call('upload_directory');call('upload',flag='-UploadArchive')
        installed=call('install_bundle','cloud/install_bundle.py',{'run_id':run.name,'data_root':settings['container_data_dir'],'archive_sha256':bundle['sha256']})
        prep=installed['preparation'];q={'prep':prep,'deadline_utc':timing['work_deadline_utc'],'repo':settings['container_repo'],
            'checkpoint_dir':settings['container_checkpoint_dir'],'cuda_home':settings['cuda_home'],'model_license_ack':True,'weights_mode':'historical_metadata'}
        # Persistent attempt BEFORE launch: unknown response must never relaunch.
        atomic(job/'launch-attempt.json',q)
        try:call('launch','project/runtime/joint_launch.py',q)
        except ValueError:timer.emit('launch_response_uncertain_inspect_only')
        retrieved=set();root=job/'results';root.mkdir()
        spec=call('prepare_watch',value={'prep':prep,'taskId':plan['taskId'],'nonce':plan['nonce']})
        while True:
            with timer.span('single_ssh_status_watch'):
                remote=observe(spec,run,plan,deadline,job)
            if (remote['taskId'],remote['nonce'])!=(plan['taskId'],plan['nonce']):raise ValueError('REMOTE_JOINT_IDENTITY_MISMATCH')
            atomic(job/'last-observed.json',remote)
            if remote['status'] in ('succeeded','failed'):
                metadata=call('retrieve_joint_bundle',value={'root':prep+'/run',
                    'data_root':settings['container_data_dir'],'taskId':plan['taskId'],'nonce':plan['nonce']})
                retrieved=consume_bundle(package,job,root,remote,metadata)
                if remote['status']=='failed':raise ValueError('JOINT_WORKER_FAILED_PREVIOUS_COMPLETED_RESULTS_PRESERVED')
                if len(retrieved)!=len(plan['cases']):raise ValueError('JOINT_RESULTS_INCOMPLETE')
                events=[json.loads(line) for line in (root/'forward-timing.jsonl').read_text(encoding='utf-8').splitlines()]
                counts=[e for e in events if e.get('event')=='joint_complete']
                if len(counts)!=1 or counts[0]['initializationCount']!=1 or counts[0]['forwardCount']!=len(plan['cases']) or counts[0]['inverseCount']!=0:
                    raise ValueError('OBSERVED_MODEL_EXECUTION_COUNTS_MISMATCH')
                prior=read(job/'summary.json') if (job/'summary.json').exists() else {}
                atomic(job/'summary.json',{**prior,'structure':'passed','visual':prior.get('visual','pending'),'observedCounts':counts[0],'retrieved':sorted(retrieved)});break
            raise ValueError('WATCH_RETURNED_NONTERMINAL_NO_RECONNECT')
    except BaseException as error:
        atomic(job/'failure.json',{'type':type(error).__name__,'error':str(error),'relaunch':False});raise
    finally:
        if authorized:shutdown(run,job,timing)
    if plan.get('version')=='direction-energy-calibration-five-v2':
        from runtime.calibration import stage_import
        stage_import(package)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--package',type=Path,required=True);p.add_argument('--config',type=Path);p.add_argument('--execute',action='store_true');o=p.parse_args()
    if not o.execute:
        plan=verify_joint(o.package.resolve()/'packet');print('LOCAL_PLAN_ONLY; no API/SSH/GPU; forward target',len(plan['cases']),'; retrieval=terminal-single-ssh-v1; progress=single-ssh-status-stream-v1')
    elif not o.config:p.error('--config required for explicit execution')
    else:execute(o.package.resolve(),o.config.resolve())
