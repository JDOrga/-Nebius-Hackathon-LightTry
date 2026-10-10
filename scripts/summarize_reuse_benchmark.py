"""Read-only verification of real two-HDR stage evidence and observed timings."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'project'))
from inference.jobs import read
from inference.reuse import identity, validate, key, safe_file
from inference.batch import validate_forward_result


def lines(path):
    return [json.loads(line) for line in safe_file(path.parent, path.name).read_text().splitlines() if line.strip()]


def summarize(job):
    request = read(safe_file(job, 'request.json'))
    evidence = job / 'remote-evidence'
    value = identity(request, safe_file(job, 'inputs/photo.png').read_bytes(),
        read(ROOT/'manifests/weights_manifest.json'), read(ROOT/'manifests/patch_manifest.json'))
    inverse = validate(evidence/'inverse', value)
    if request['requiredInverseReuse'] != {'key':key(value),'source':inverse['source']}:
        raise ValueError('BENCHMARK_INVERSE_PROVENANCE_MISMATCH')
    configuration = read(safe_file(evidence, 'configuration.json'))
    minimal = dict(request); minimal['input'] = {k:v for k,v in request['input'].items() if k not in ('name','url','originalUrl')}
    if configuration['request'] != minimal:
        raise ValueError('BENCHMARK_REQUEST_CONFIGURATION_MISMATCH')
    weights = read(safe_file(evidence, 'weights_verification.json'))
    if weights.get('mode') != 'historical_metadata' or weights.get('content_verified_this_run') is not False:
        raise ValueError('BENCHMARK_WEIGHT_POLICY_MISMATCH')
    forward = lines(evidence/'forward-timing.jsonl')
    worker = lines(evidence/'worker-timing.jsonl')
    orchestration = lines(evidence/'orchestration-timing.jsonl')
    local = lines(job/'local-timing.jsonl')
    spawn = [e for e in worker if e['event']=='process_spawn_return']
    inverse_count = sum(e['log']=='inverse.log' for e in spawn)
    ready = [e for e in forward if e['event']=='pipeline_ready']
    if inverse_count != 0 or len(spawn)!=1 or len(ready)!=1 or ready[0]['initializationCount']!=1:
        raise ValueError('ACTUAL_PROCESS_OR_INITIALIZATION_COUNTS_MISMATCH')
    if not any(e['event']=='inverse_reused' for e in orchestration):
        raise ValueError('ACTUAL_INVERSE_REUSE_OBSERVATION_REQUIRED')
    model_id, process = ready[0]['modelObjectId'], ready[0]['process']
    results = []
    for preset in request['presets']:
        index = preset['index']; item = evidence/'presets'/str(index)
        marker = item/'complete.json'
        if not marker.exists():
            results.append({'presetId':preset['id'],'status':read(safe_file(item,'state.json'))['status']})
            continue
        record = read(safe_file(item,'complete.json'))
        expected_request = {'taskId':request['taskId'],'nonce':request['nonce'],'inputId':request['input']['id'],
            'inputSha256':request['input']['sha256'],'originalSha256':request['original']['sha256']}
        binding = record['identity']
        if (binding['request']!=expected_request or binding['hdr']!=preset or binding['config']!=request['runConfig'] or
                binding['inverseKey']!=inverse['key'] or binding['inverseArtifacts']!=inverse['artifacts'] or
                record['source']['modelObjectId']!=model_id or record['source']['process']!=process or
                record['randomPolicy']!='reset-before-forward-generate-v1' or record['seed']!=1000):
            raise ValueError('PRESET_IDENTITY_OR_MODEL_OBJECT_MISMATCH')
        attempt = record['attempt']
        if len(attempt)!=32 or any(c not in '0123456789abcdef' for c in attempt):
            raise ValueError('UNSAFE_PRESET_ATTEMPT')
        output = validate_forward_result(item/attempt)
        if output!=record['result'] or not output['path'].startswith(f'relit_frames_{index:04d}/'):
            raise ValueError('PRESET_RESULT_HASH_MISMATCH')
        results.append({'presetId':preset['id'],'status':'succeeded','taskId':request['taskId'],
            'result':output,'localFile':str(item/attempt/output['path']),'modelObjectId':model_id,
            'sourceProcess':process,'completedEpoch':record['completedEpoch']})
    completions = [e for e in forward if e['event']=='preset_complete']
    generated = [e for e in forward if e['event']=='generation_end' and e.get('success')]
    if any(e.get('modelObjectId')!=model_id or e['process']!=process for e in generated+completions):
        raise ValueError('GENERATION_MODEL_OBJECT_MISMATCH')
    resets = [e for e in forward if e['event']=='random_state_reset']
    if any(e.get('seed')!=1000 or e.get('policy')!='reset-before-forward-generate-v1' for e in resets):
        raise ValueError('ACTUAL_RANDOM_POLICY_MISMATCH')
    submit = next(e for e in local if e['event']=='submission_entry')
    observed = [e for e in local if e['event']=='preset_available_observed']
    available = [e for e in local if e['event']=='results_local_validated']
    return {'mode':'ACTUAL_EXECUTION_EVIDENCE_ONLY','taskId':request['taskId'],
        'actualInverseExecutions':inverse_count,'actualForwardInitializations':len(ready),
        'actualForwardProcesses':len(spawn),'sameModelObjectId':model_id,'results':results,
        'firstAvailableObservedSeconds':observed[0]['monotonicSeconds']-submit['monotonicSeconds'] if observed else None,
        'firstAvailableRangeNote':'local polling observation includes poll/transport delay; remote/local wall-clock skew not assumed zero',
        'secondPresetIncrementSeconds':completions[1]['monotonicSeconds']-completions[0]['monotonicSeconds'] if len(completions)==2 else None,
        'allResultsLocalValidatedSeconds':available[0]['monotonicSeconds']-submit['monotonicSeconds'] if available else None,
        'forwardPhases':[e for e in forward if e['event'].endswith('_end')],
        'localTransportEvents':[e for e in local if e['event'].startswith('transport_')],
        'content_verified':False,'productBatchRegistered':False,'productDisplayTime':None,
        'gpuKernelTiming':False,'nestedTimingsMustNotBeSummed':True}


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--job',type=Path,required=True)
    args=parser.parse_args(); print(json.dumps(summarize(args.job.resolve()),ensure_ascii=False,indent=2))
