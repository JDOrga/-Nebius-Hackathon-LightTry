"""Strict parameter facade over original worker; does not edit official source."""
import argparse
import json
import re
from pathlib import Path
import sys

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT))
from inference import worker, batch
from inference.jobs import read, atomic
from lighting import normalize_parameters

VERSION='single-scheme-hdr-adapter-v1'

def install_legacy_imports():
    # The original executable's script directory supplied this top-level name.
    # In a facade execution, bind the SAME bundled module explicitly, never an
    # installed lookalike and never weaken its weight/reference verification.
    from inference import weights_reuse
    existing=sys.modules.get('weights_reuse')
    if existing is not None and Path(existing.__file__).resolve()!=Path(weights_reuse.__file__).resolve():
        raise ValueError('LEGACY_WEIGHT_MODULE_IDENTITY_MISMATCH')
    sys.modules['weights_reuse']=weights_reuse


def main():
    parser=argparse.ArgumentParser(add_help=False)
    parser.add_argument('--request',type=Path,required=True)
    options,_=parser.parse_known_args()
    job=read(options.request)
    policy=read(Path(__file__).with_name('policy.json'))
    presets=json.loads((PROJECT/'data/catalog.json').read_text())['presets'] if (PROJECT/'data/catalog.json').exists() else None
    # Remote archive intentionally carries a tiny environment catalog, not demo
    # photos or machine configuration.
    if presets is None:presets=read(Path(__file__).with_name('environments.json'))
    environments={p['id']:p for p in presets}
    if len(job.get('presets',[]))!=1 or job['runConfig'].get('lightingAdapterVersion')!=VERSION:
        raise ValueError('SINGLE_REVIEWED_SCHEME_REQUIRED')
    p=job['preset']; raw=p['scheme']['parameters']
    if p.get('sourceEnvironment'):environments[p['sourceEnvironment']['id']]=p['sourceEnvironment']
    expected=normalize_parameters(raw,environments,policy)
    if p['parameters']!=expected or p['environmentId']!=raw['environmentId']:
        raise ValueError('SCHEME_PARAMETERS_MISMATCH')
    old_command=batch.measured_command
    def command(argv,phase,run,state_root=None):
        result=old_command(argv,phase,run,state_root)
        if phase=='forward':result[2]=str(Path(__file__).with_name('entry.py'))
        return result
    batch.measured_command=command
    original_atomic=worker.atomic; finished=None
    def deferred(path,value):
        nonlocal finished
        if path.name=='execution.json' and value.get('status')=='succeeded':finished=dict(value);return
        return original_atomic(path,value)
    worker.atomic=deferred
    try:
        install_legacy_imports()
        worker.main()  # original commit/blob/patch/HDR/weight/inverse/deadline checks
        prep=Path(__file__).resolve().parents[2];run=prep/'run'
        directory=run/'presets'/str(p['index'])
        condition=read(directory/'condition.json');model=read(directory/'model-condition.json')
        from light_console import preprocessing_parameters
        if condition['parameters']!=preprocessing_parameters(raw):
            raise ValueError('ACTUAL_CONDITION_PARAMETERS_MISMATCH')
        if any(model[k]['shape']!=[1,3,1,704,1280] for k in ('env_ldr','env_log','env_nrm')):
            raise ValueError('ACTUAL_MODEL_CONDITION_MISMATCH')
        receipt=read(run/'receipt.json')
        receipt['lighting']={'recipeKey':p['recipeKey'],'parameters':expected,'adapterVersion':VERSION,
            'actualCondition':condition,'actualModelCondition':model,'derivedHdrSha256':p.get('derivedHdrSha256')}
        atomic(run/'receipt.json',receipt)
        atomic(run/'parameter-proof.json',receipt['lighting'])
        if finished is None:raise ValueError('ORIGINAL_EXECUTION_COMPLETION_MISSING')
        original_atomic(run/'execution.json',finished)
    except BaseException as error:
        prep=Path(__file__).resolve().parents[2]
        if (prep/'run').is_dir():
            message=str(error)
            atomic(prep/'run/facade-error.json',{'type':type(error).__name__,
                'module':getattr(error,'name',None),
                'code':message if re.fullmatch('[A-Z0-9_]{1,100}',message) else 'WORKER_REJECTED',
                'rawTraceNotExposed':True})
        if finished is not None:
            # Original model children already exited; reject a missing/mismatched
            # parameter proof rather than publishing an early success event.
            prep=Path(__file__).resolve().parents[2]
            event={**finished,'status':'failed','stage':'validating','executionStopped':True,
                   'error':'PARAMETER_PROOF_REJECTED_'+type(error).__name__}
            original_atomic(prep/'run/execution.json',event)
        raise
    finally:
        worker.atomic=original_atomic;batch.measured_command=old_command


if __name__=='__main__':main()
