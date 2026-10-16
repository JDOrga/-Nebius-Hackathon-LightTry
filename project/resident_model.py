"""GPU-only phase daemon. Explicit start; no inference until a validated job arrives."""
import argparse
import contextlib
import hashlib
import importlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import time
import uuid

from inference.jobs import atomic,read,RUN_CONFIG,ID
from model_contract import grant_file
from resident_ipc import safe,phase_command

ROOT=Path(__file__).resolve().parent.parent


class PipelineCache:
    """Keep the original class/method instrumentation and reuse one initialized object."""
    def __init__(self,cls,kwargs):
        self.cls,self.kwargs=cls,dict(kwargs)
        self.instance=cls(**kwargs)
        self.original_new=cls.__new__;self.original_init=cls.__init__
        self.had_new='__new__' in cls.__dict__
        instance=self.instance;expected=self.kwargs
        def reuse_new(kind,*args,**actual):
            if args or actual!=expected:raise ValueError('RESIDENT_MODEL_CONFIGURATION_CHANGED')
            return instance
        cls.__new__=staticmethod(reuse_new)
        cls.__init__=lambda instance,**actual:None

    def reset(self):
        # Per-job condition hooks must never leak into the next user's request.
        self.instance.__dict__.pop('generate_video',None)

    def close(self):
        if self.original_new is object.__new__:
            # CPython retains an updated tp_new slot after assigning __new__;
            # deleting the attribute alone breaks keyword construction.
            self.cls.__new__=staticmethod(lambda kind,*args,**kw:object.__new__(kind))
        else:self.cls.__new__=staticmethod(self.original_new)
        self.cls.__init__=self.original_init


def verify_runtime(config,deadline):
    """Same fixed commit, unmodified entry, HDR patch and full weight checks as jobs."""
    repo=Path(config['repo']);checkpoints=Path(config['checkpointDir'])
    sys.path.insert(0,str(ROOT/'scripts'))
    from weights import verify,check_time
    check_time(deadline)
    head=subprocess.run(['git','-C',str(repo),'rev-parse','HEAD'],capture_output=True,
                        text=True,check=True,timeout=10).stdout.strip()
    if head!=RUN_CONFIG['upstreamCommit']:raise ValueError('UPSTREAM_COMMIT_MISMATCH')
    for phase in ('inverse','forward'):
        rel='cosmos_predict1/diffusion/inference/inference_'+phase+'_renderer.py'
        raw=subprocess.run(['git','-C',str(repo),'show',head+':'+rel],capture_output=True,check=True,timeout=10).stdout
        if (repo/rel).read_bytes()!=raw:raise ValueError('MODEL_ENTRY_MODIFIED')
    for item in read(ROOT/'manifests/patch_manifest.json')['files']:
        if hashlib.sha256((repo/item['path']).read_bytes()).hexdigest()!=item['after_sha256']:
            raise ValueError('EXISTING_HDR_PATCH_MISMATCH')
    for item in read(ROOT/'manifests/weights_manifest.json')['files']:
        if not verify(checkpoints/item['path'],item,deadline):raise ValueError('MODEL_WEIGHT_UNVERIFIED')
    check_time(deadline)


def preload(config,phase,root,deadline):
    # Production hot path: load directly; no weight/source scans or preflight subprocess.
    if time.time()>=deadline:raise TimeoutError('RESIDENT_LOAD_DEADLINE')
    os.environ.update(CUDA_HOME=config['cudaHome'],HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
    repo=Path(config['repo']);os.chdir(repo);sys.path.insert(0,str(repo))
    module=importlib.import_module('cosmos_predict1.diffusion.inference.inference_'+phase+'_renderer')
    from run_experiment import commands
    args=argparse.Namespace(checkpoint_dir=Path(config['checkpointDir']),input_dir=root/'unused-input',
        run_dir=root/'unused-run',width=1280,height=704,offload=False)
    command=commands(args)[0 if phase=='inverse' else 1]+['--guidance','0.0']
    original=sys.argv
    try:sys.argv=[command[2],*command[3:]];parsed=module.parse_arguments()
    finally:sys.argv=original
    # The pinned upstream demo constructs this same class before opening any input.
    mapping={'checkpoint_dir':'checkpoint_dir','checkpoint_name':'diffusion_transformer_dir',
        'offload_network':'offload_diffusion_transformer','offload_tokenizer':'offload_tokenizer',
        'offload_text_encoder_model':'offload_text_encoder_model','offload_guardrail_models':'offload_guardrail_models',
        'guidance':'guidance','num_steps':'num_steps','height':'height','width':'width',
        'fps':'fps','num_video_frames':'num_video_frames','seed':'seed'}
    cache=PipelineCache(module.DiffusionRendererPipeline,{key:getattr(parsed,name) for key,name in mapping.items()})
    module.torch.cuda.synchronize()
    if time.time()>=deadline:raise TimeoutError('RESIDENT_LOAD_DEADLINE')
    return cache,module


def execute(body,config,phase,session_root,cache,module):
    if not isinstance(body,dict) or set(body)!={'id','prep','argv','logfile','deadline','bootId'} or not ID.fullmatch(body['id']):
        raise ValueError('RESIDENT_COMMAND_INVALID')
    prep=safe(body['prep'],session_root/'executions')
    if prep.parent!=session_root/'executions' or not ID.fullmatch(prep.name):raise ValueError('RESIDENT_JOB_INVALID')
    command=body['argv']
    if phase_command(command,prep)!=phase or Path(command[0]).resolve()!=Path(config['python']).resolve():
        raise ValueError('RESIDENT_PHASE_INVALID')
    entry=Path(command[2]);installed=ROOT/entry.relative_to(prep)
    if entry.read_bytes()!=installed.read_bytes():raise ValueError('RESIDENT_ENTRY_CHANGED')
    log=safe(body['logfile'],prep/'run')
    argv=sys.argv
    try:
        cache.reset();module.misc.set_random_seed(1000)
        sys.argv=[str(entry),*command[3:]]
        with log.open('x',encoding='utf-8') as out,contextlib.redirect_stdout(out),contextlib.redirect_stderr(out):
            runpy.run_path(str(entry),run_name='__main__')
            module.torch.cuda.synchronize()
        if time.time()>=body['deadline']:raise TimeoutError('RESIDENT_RESULT_OUTSIDE_WINDOW')
    finally:sys.argv=argv;cache.reset()


def serve(args,*,load=preload,run=execute,clock=time.time,sleep=time.sleep):
    config=read(args.worker_config)
    session_root=Path(args.data_root)
    root=safe(session_root/'resident'/args.phase,session_root);root.mkdir(parents=True,exist_ok=True,mode=0o700)
    # A service restart may not reload models or consume a second paid attempt.
    with (root/'boot-attempt').open('x'):pass
    for name in ('requests','responses','attempts'):(root/name).mkdir(mode=0o700)
    boot=uuid.uuid4().hex;cache=None
    def state(value):atomic(root/'state.json',{'state':value,'modelLoaded':value in ('ready','busy'),
        'bootId':boot,'pid':os.getpid(),'phase':args.phase,'sessionId':args.session_id,'resourceId':args.resource_id})
    try:
        grant=grant_file(config['grantFile'],args.session_id,args.resource_id)
        deadline=grant['expiresAt'];state('loading')
        cache,module=load(config,args.phase,root,deadline)
        if clock()>=deadline:raise TimeoutError('RESIDENT_LOAD_DEADLINE')
        if grant_file(config['grantFile'],args.session_id,args.resource_id)!=grant:
            raise ValueError('RESIDENT_GRANT_CHANGED')
        state('ready')
        while clock()<deadline:
            current=grant_file(config['grantFile'],args.session_id,args.resource_id)
            if current['hostIdentity']!=grant['hostIdentity'] or current['expiresAt']!=deadline:
                raise ValueError('RESIDENT_GRANT_CHANGED')
            for request in sorted((root/'requests').glob('*.json')):
                if not ID.fullmatch(request.stem) or request.is_symlink():raise ValueError('RESIDENT_REQUEST_UNSAFE')
                attempt=root/'attempts'/request.stem
                if attempt.exists():continue
                with attempt.open('x'):pass
                body=read(request)
                if body.get('id')!=request.stem or body.get('bootId')!=boot or type(body.get('deadline')) not in (int,float) or not clock()<body['deadline']<=deadline:
                    raise ValueError('RESIDENT_REQUEST_BINDING_INVALID')
                state('busy')
                run(body,config,args.phase,session_root,cache,module)
                atomic(root/'responses'/request.name,{'id':request.stem,'bootId':boot,'exitCode':0,
                    'phase':args.phase,'pid':os.getpid(),'modelObjectId':hex(id(cache.instance)),
                    'cudaSynchronized':True,'completedAt':clock()})
                state('ready')
            sleep(.1)
    except BaseException:
        state('failed');raise
    finally:
        if cache:cache.close()
        state('failed')


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--model-phase',choices=('inverse','forward'),required=True)
    parser.add_argument('--worker-config',type=Path,required=True)
    parser.add_argument('--data-root',type=Path,required=True)
    parser.add_argument('--session-id',required=True);parser.add_argument('--resource-id',required=True)
    args=parser.parse_args(argv);args.phase=args.model_phase
    if not ID.fullmatch(args.session_id) or not args.resource_id:raise ValueError('RESIDENT_IDENTITY_REQUIRED')
    if not args.data_root.is_absolute() or args.data_root.resolve().is_relative_to(ROOT):raise ValueError('PRIVATE_RUNTIME_ROOT_REQUIRED')
    from security import runtime_file
    config=json.loads(runtime_file(args.worker_config,ROOT).decode())
    if config.get('enabled') is not True or config.get('executionMode')!='resident':raise ValueError('EXPLICIT_RESIDENT_ENABLE_REQUIRED')
    os.umask(0o077);os.environ['LIGHTTRY_MODEL_RESIDENT']='1';serve(args)
