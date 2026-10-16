"""GPU-only phase daemon. Explicit start; no inference until a validated job arrives."""
import argparse
import contextlib
import functools
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


def process_io():
    """Small Linux process counters only; never open checkpoints or launch probes."""
    try:
        with open('/proc/self/io',encoding='ascii') as stream:
            values=dict(line.strip().split(': ',1) for line in stream)
        return {name:int(values[name]) for name in ('read_bytes','rchar')}
    except (OSError,ValueError,KeyError):
        return None


class LoadTiming:
    """Bounded, private, best-effort spans. Durations are inclusive, not additive.

    Host wall/CPU time and process I/O deltas are measurements, NOT GPU kernel
    timings. Only the existing final CUDA synchronize waits for device completion.
    A missing finish record means interrupted/unknown, never successful READY.
    """
    def __init__(self,root,phase,*,clock=time.perf_counter,wall=time.time,cpu=time.process_time,io=process_io):
        self.clock,self.wall,self.cpu,self.io=clock,wall,cpu,io
        self.phase=phase if phase in ('inverse','forward') else 'unknown'
        self.stack=[];self.serial=0;self.events=0;self.bytes=0;self.stream=None
        try:
            # Exclusive creation also refuses a stale file or symlink; no overwrite.
            path=root/'loading-timing.jsonl'
            fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            self.stream=os.fdopen(fd,'w',encoding='utf-8',newline='\n')
        except OSError:
            pass

    def emit(self,value):
        if self.stream is None or self.events>=128:return
        try:
            raw=json.dumps(dict(schemaVersion=1,phase=self.phase,pid=os.getpid(),**value),
                           separators=(',',':'),allow_nan=False)+'\n'
            size=len(raw.encode('utf-8'))
            if self.bytes+size>65536:return
            self.stream.write(raw);self.stream.flush()
            self.events+=1;self.bytes+=size
        except Exception:
            self.close()

    @contextlib.contextmanager
    def span(self,stage):
        self.serial+=1;identity=self.serial;parent=self.stack[-1] if self.stack else None
        started=self.clock();cpu=self.cpu();before=self.io()
        self.emit(dict(stage=stage,event='started',spanId=identity,parentSpanId=parent,
                       at=self.wall(),monotonic=started))
        self.stack.append(identity);outcome='failed'
        try:
            yield
            outcome='finished'
        finally:
            elapsed=self.clock()-started;cpu_elapsed=self.cpu()-cpu;after=self.io()
            self.stack.pop()
            delta=lambda key:max(0,after[key]-before[key]) if before is not None and after is not None else None
            self.emit(dict(stage=stage,event=outcome,spanId=identity,parentSpanId=parent,
                           at=self.wall(),elapsedMs=round(max(0,elapsed)*1000,3),
                           cpuMs=round(max(0,cpu_elapsed)*1000,3),
                           ioReadBytes=delta('read_bytes'),ioRchar=delta('rchar')))

    def wrap(self,function,stage):
        @functools.wraps(function)
        def measured(*args,**kwargs):
            with self.span(stage):return function(*args,**kwargs)
        return measured

    def close(self):
        stream,self.stream=self.stream,None
        if stream is not None:
            try:stream.close()
            except Exception:pass


class _TimingProxy:
    """Local module alias proxy, never monkey-patch torch globally."""
    def __init__(self,original,**overrides):self.original,self.overrides=original,overrides
    def __getattr__(self,name):return self.overrides[name] if name in self.overrides else getattr(self.original,name)


@contextlib.contextmanager
def load_hooks(module,timing):
    """Only already-imported pinned loader sites; restore aliases/methods on all exits.

    No change to arguments, device, dtype, weights_only fallback, return values,
    exceptions, concurrency or synchronization. No additional model imports.
    """
    with contextlib.ExitStack() as cleanup:
        def replace(owner,name,value):
            owned=name in vars(owner);original=getattr(owner,name)
            setattr(owner,name,value)
            def restore():
                if owned:setattr(owner,name,original)
                else:delattr(owner,name)
            cleanup.callback(restore)
        def hook(owner,name,stage):
            function=getattr(owner,name,None)
            if callable(function):replace(owner,name,timing.wrap(function,stage))
        cls=module.DiffusionRendererPipeline
        for name,stage in (('_load_model','model_config'),('_load_network','network_load'),
                           ('_load_tokenizer','tokenizer_load')):
            hook(cls,name,stage)
        model_module=sys.modules.get('cosmos_predict1.diffusion.model.model_diffusion_renderer')
        model=getattr(model_module,'DiffusionRendererModel',None)
        if model is not None:
            for name,stage in (('set_up_model','network_setup'),('set_up_tokenizer','tokenizer_setup'),
                               ('cuda','device_move')):
                hook(model,name,stage)
        utils=sys.modules.get('cosmos_predict1.diffusion.inference.inference_utils')
        if utils is not None:
            hook(utils,'non_strict_load_model','parameter_apply')
            torch=getattr(utils,'torch',None)
            if callable(getattr(torch,'load',None)):
                replace(utils,'torch',_TimingProxy(torch,load=timing.wrap(torch.load,'checkpoint_read')))
        # The pinned renderer uses pretrained_vae.torch.load for JIT archives.
        # Also cover the already-imported optional tokenizer utility's jit.load.
        for name in ('cosmos_predict1.diffusion.module.pretrained_vae',
                     'cosmos_predict1.tokenizer.inference.utils'):
            tokenizer=sys.modules.get(name);torch=getattr(tokenizer,'torch',None)
            if torch is None:continue
            overrides={};jit=getattr(torch,'jit',None)
            if callable(getattr(torch,'load',None)):
                overrides['load']=timing.wrap(torch.load,'tokenizer_checkpoint_read')
            if callable(getattr(jit,'load',None)):
                overrides['jit']=_TimingProxy(jit,load=timing.wrap(jit.load,'tokenizer_checkpoint_read'))
            if overrides:replace(tokenizer,'torch',_TimingProxy(torch,**overrides))
        yield


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
    timing=LoadTiming(root,phase);cache=None
    try:
        with timing.span('preload_total'):
            with timing.span('environment_setup'):
                os.environ.update(CUDA_HOME=config['cudaHome'],HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
                repo=Path(config['repo']);os.chdir(repo);sys.path.insert(0,str(repo))
            with timing.span('module_import'):
                module=importlib.import_module('cosmos_predict1.diffusion.inference.inference_'+phase+'_renderer')
            with timing.span('argument_setup'):
                sys.path.insert(0,str(ROOT/'scripts'))
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
            with load_hooks(module,timing),timing.span('pipeline_init'):
                cache=PipelineCache(module.DiffusionRendererPipeline,{key:getattr(parsed,name) for key,name in mapping.items()})
            with timing.span('cuda_synchronize'):
                module.torch.cuda.synchronize()
            if time.time()>=deadline:raise TimeoutError('RESIDENT_LOAD_DEADLINE')
            return cache,module
    except BaseException:
        if cache:cache.close()
        raise
    finally:timing.close()


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
