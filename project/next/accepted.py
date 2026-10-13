"""Import retained real joint results by exact photo/recipe/output identity."""
import copy
import hashlib
from pathlib import Path
from inference.jobs import read
from inference.reuse import safe_file
from next.runtime.joint import verify_joint
from next.runtime.joint_results import validate_case


def load_accepted(package, catalog):
    if package is None:
        return [], {}, []
    package = Path(package).resolve(); packet = package / 'packet'; root = package / 'execution/results'
    plan = verify_joint(packet)
    calibration=plan['version']=='direction-energy-calibration-five-v2'
    summary=read(package/'execution/calibration-summary.json') if calibration else {}
    if calibration and summary['execution']!='generated-five':raise ValueError('CALIBRATION_SUMMARY_NOT_COMPLETE')
    event = read(safe_file(root, 'execution.json'))
    if event.get('status') != 'succeeded' or event.get('executionStopped') is not True:
        raise ValueError('ACCEPTED_TERMINAL_SUCCESS_REQUIRED')
    sample = next((s for s in catalog['samples'] if s['input']['sha256'] == plan['input']['sha256']), None)
    if sample is None:
        raise ValueError('ACCEPTED_PHOTO_NOT_IN_CATALOG')
    original = plan['input']['preprocessing']
    if sample['original']['sha256'] != original['sha256']:
        raise ValueError('ACCEPTED_ORIGINAL_PHOTO_MISMATCH')
    studies, files, schemes = [], {}, []
    for case in plan['cases']:
        record = validate_case(packet, root, case)
        marker = read(safe_file(root / 'cases' / case['id'], '0/complete.json'))
        key = ('calibration-' + hashlib.sha256((plan['input']['sha256']+case['recipeKey']+record['sha256']).encode()).hexdigest() if calibration else 'joint-' + plan['taskId'] + '-' + case['id'])
        files[key] = (Path(record['path']), record['sha256'])
        study = {'sampleId': sample['id'], 'caseId': case['id'],
                 'inputSha256': plan['input']['sha256'], 'originalSha256': original['sha256'],
                 'parameters': copy.deepcopy(case['parameters']), 'recipeKey': case['recipeKey'],
                 'hdrSha256': case['hdrSha256'], 'taskId': plan['taskId'],
                 'canvas': sample['canvas'], 'generatedAt': marker['completedEpoch'],
                 'source': case['source'], 'comparison': case['comparison'],
                 'visualStatus': summary.get('visual','partial; AI dark; no color/detail fidelity guarantee'),
                 'result': {'url': '/study/' + key, 'downloadUrl': '/study-download/' + key,
                            'regionUrl': '/study-region/' + key, 'regionDownloadUrl': '/study-download-region/' + key,
                            'sha256': record['sha256'], 'recipeKey': case['recipeKey'],
                            'taskId': plan['taskId'], 'inputId': plan['input']['sha256'][:32],
                            'width': 1280, 'height': 704}}
        studies.append(study)
        schemes.append({'schemaVersion': 1, 'planId': hashlib.sha256(key.encode()).hexdigest()[:32],
                        'version': 1, 'parentVersion': None, 'name': case['id'] + (' · 本轮五项校准实测' if calibration else ' · 2026-10-12实测'),
                        'parameters': copy.deepcopy(case['parameters']), 'inputId': plan['input']['sha256'][:32],
                        'recipeKey': case['recipeKey'], 'importedResultSha256': record['sha256'],
                        'provenance': {'taskId': plan['taskId'], 'source': case['source'], 'caseId': case['id'], **({'cohort':'current-calibration-20261013'} if calibration else {})}})
    return studies, files, schemes


def measured_context(studies):
    """Trusted text-only case summaries; never encode pixels or invent AI returns."""
    notes = {'A': 'existing HDR reference, different source from B',
             'B': 'dark front and rim lighting', 'C': 'direction-only change vs B improves subject visibility',
             'D': 'strength-only reduction vs B gives weak darkening; not proportional brightness',
             'E': 'larger FWHM increases spherical energy 4.94x; cannot infer physical softness',
             'F': 'fill-only addition vs B raises dark face', 'AI': 'real accepted key0.8 fill0.2 remains overly dark'}
    return [{'inputId': s['inputSha256'][:32], 'recipeKey': s['recipeKey'],
             'parameters': s['parameters'], 'outputSha256': s['result']['sha256'],
             'caseId': s['caseId'], 'observation': notes[s['caseId']],
             'source': 'retained GPU evidence plus operator/agent offline review; not model vision'}
            for s in studies if s.get('recipeKey') and s['caseId'] in notes]


def load_accepted_many(packages,catalog):
    studies,files,schemes=[],{},[]
    for package in packages or []:
        a,b,c=load_accepted(package,catalog)
        known={s['planId']:s for s in schemes}
        for s in c:
            if s['planId'] in known:
                # Stable photo/full-recipe/output identity wins over cohort labels.
                # Same bytes from a later run do not replace the first evidence.
                if any(known[s['planId']][k]!=s[k] for k in ('inputId','parameters','recipeKey','importedResultSha256')):
                    raise ValueError('ACCEPTED_IMPORT_IDENTITY_CONFLICT')
            if s['planId'] not in known:schemes.append(s);known[s['planId']]=s
        for study in a:
            if not any(s['result']['url']==study['result']['url'] for s in studies):studies.append(study)
        for k,v in b.items():
            if k in files and files[k][1]!=v[1]:raise ValueError('ACCEPTED_FILE_IDENTITY_CONFLICT')
            if k not in files:files[k]=v
    return studies,files,schemes
