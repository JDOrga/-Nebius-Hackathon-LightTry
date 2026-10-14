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
            'project/runtime/joint_inspect.py','project/runtime/joint_results.py'):
            if (ROOT/name).read_bytes()!=(package/'packet'/name).read_bytes():
                raise ValueError('TRANSPORT_PROGRAM_CHANGED_REPREPARE_BEFORE_START')
        for p in (run/'inference-code.tar.gz',run/'bundle.json'):
            if p.exists():raise ValueError('PRESERVE_EXISTING_GUARD_BUNDLE')
        shutil.copyfile(package/'inference-code.tar.gz',run/'inference-code.tar.gz')
        atomic(run/'bundle.json',{**bundle,'archive_path':str((run/'inference-code.tar.gz').resolve())})
        def call(operation,program=None,value=None,flag=None,part=None):
            authorization(config_path)
            if time.time()>=deadline:raise TimeoutError('FIXED_WORK_WINDOW_ENDED')
            args=['powershell.exe','-NoProfile','-File',str(ROOT/('cloud/ControlChunkTransport.ps1' if part else 'cloud/Invoke-ScaleRemote.ps1')),
                '-RunDirectory',str(run),'-Operation',operation,'-Execute']
            if part:args+=['-SourceRunId',run.name,'-ControlPart',part]
            if program:args+=['-ContainerProgramPath',str(ROOT/program)]
            if value is not None:
                p=job/(operation+'-'+str(part)+'-request.json');atomic(p,value);args+=['-RequestPath',str(p)]
            if flag:args.append(flag)
            with timer.span('transfer' if flag else operation):
                with (job/(operation+'-'+str(part)+'.log')).open('ab') as log:
                    result=subprocess.run(args,stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,timeout=min(120,max(.1,deadline-time.time())),shell=False)
            if result.returncode:raise ValueError('GUARDED_TRANSPORT_FAILED_'+operation)
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
        while True:
            remote=call('inspect','project/runtime/joint_inspect.py',{'prep':prep})
            if (remote['taskId'],remote['nonce'])!=(plan['taskId'],plan['nonce']):raise ValueError('REMOTE_JOINT_IDENTITY_MISMATCH')
            atomic(job/'last-observed.json',remote)
            for name in remote['completed']:
                if name in retrieved:continue
                part=next(p for p,n in PARTS.items() if n==name)
                metadata=call('export_control_chunk','project/runtime/joint_results.py',{'root':prep+'/run','data_root':settings['container_data_dir'],'part':part},part=part)
                atomic(job/('export-'+part+'.json'),metadata)
                call('download_control_chunk',flag='-DownloadResults',part=part)
                archive=run/('control-canonical-'+run.name+'-'+part+'.tar.gz')
                if archive.stat().st_size!=metadata['bytes']:raise ValueError('TRANSFER_BYTES_MISMATCH')
                extract(archive,root,metadata['sha256'])
                record=validate_case(package/'packet',root,next(c for c in plan['cases'] if c['id']==name))
                atomic(job/(name+'-retrieval.json'),record);retrieved.add(name)
                comparison(package/'packet',job/'comparison.html',root)
            if remote['status'] in ('succeeded','failed'):
                metadata=call('export_control_chunk','project/runtime/joint_results.py',{'root':prep+'/run','data_root':settings['container_data_dir'],'part':'metadata'},part='metadata')
                call('download_control_chunk',flag='-DownloadResults',part='metadata')
                extract(run/('control-canonical-'+run.name+'-metadata.tar.gz'),root,metadata['sha256'])
                if remote['status']=='failed':raise ValueError('JOINT_WORKER_FAILED_PREVIOUS_COMPLETED_RESULTS_PRESERVED')
                if len(retrieved)!=len(plan['cases']):raise ValueError('JOINT_RESULTS_INCOMPLETE')
                events=[json.loads(line) for line in (root/'forward-timing.jsonl').read_text(encoding='utf-8').splitlines()]
                counts=[e for e in events if e.get('event')=='joint_complete']
                if len(counts)!=1 or counts[0]['initializationCount']!=1 or counts[0]['forwardCount']!=len(plan['cases']) or counts[0]['inverseCount']!=0:
                    raise ValueError('OBSERVED_MODEL_EXECUTION_COUNTS_MISMATCH')
                atomic(job/'summary.json',{'structure':'passed','visual':'pending','observedCounts':counts[0],'retrieved':sorted(retrieved)});break
            time.sleep(min(4,max(0,deadline-time.time())))
    except BaseException as error:
        atomic(job/'failure.json',{'type':type(error).__name__,'error':str(error),'relaunch':False});raise
    finally:
        if authorized:shutdown(run,job,timing)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--package',type=Path,required=True);p.add_argument('--config',type=Path);p.add_argument('--execute',action='store_true');o=p.parse_args()
    if not o.execute:
        plan=verify_joint(o.package.resolve()/'packet');print('LOCAL_PLAN_ONLY; no API/SSH/GPU; forward target',len(plan['cases']))
    elif not o.config:p.error('--config required for explicit execution')
    else:execute(o.package.resolve(),o.config.resolve())
