"""Read-only actual study frames, separate from production generation receipts."""
import copy
import json
from pathlib import Path

from inference.images import digest
from inference.jobs import read
from inference.reuse import safe_file
from inference.batch import validate_forward_result
from experiments.worker import verify_packet
from experiments.controls import CASES, normalize
from lighting import CLOSED


def load_evidence(config_path=None):
    if config_path is None:
        return copy.deepcopy(CLOSED), [], {}
    config = read(Path(config_path))
    public, files = [], {}
    for study in config['studies']:
        packet, root = Path(study['packetDirectory']), Path(study['resultsDirectory'])
        plan = verify_packet(packet)
        if read(safe_file(root, 'retrieval.json'))['status'] != 'passed':
            raise ValueError('STUDY_RETRIEVAL_NOT_VERIFIED')
        if read(safe_file(root, 'configuration.json'))['experiment'] != plan:
            raise ValueError('STUDY_CONFIGURATION_MISMATCH')
        for case in CASES:
            directory = root / 'controls' / case['id'] / '0'
            completed = read(safe_file(directory, 'complete.json'))
            if completed['identity']['experiment'] != normalize(case['offsetDeg'], case['strength']):
                raise ValueError('STUDY_ACTUAL_PARAMETERS_MISMATCH')
            frame = safe_file(directory / completed['attempt'], completed['result']['path'])
            if validate_forward_result(directory / completed['attempt']) != completed['result']:
                raise ValueError('STUDY_CANONICAL_FRAME_MISMATCH')
            key = plan['sampleId'] + '--' + case['id']
            files[key] = (frame, completed['result']['sha256'])
            public.append({'sampleId': plan['sampleId'], 'caseId': case['id'],
                'parameters': {'environmentId': plan['hdr']['id'], 'offsetDeg': case['offsetDeg'], 'strength': case['strength']},
                'inputSha256': plan['input']['sha256'], 'hdrSha256': plan['hdr']['sha256'],
                'canvas': {'width': 1280, 'height': 704,
                           'validRegion': plan['input']['preprocessing']['valid_region_xyxy']},
                'result': {'url': '/study/' + key, 'downloadUrl': '/study-download/' + key,
                           'regionUrl': '/study-region/' + key,
                           'regionDownloadUrl': '/study-download-region/' + key,
                           'sha256': completed['result']['sha256'], 'width': 1280, 'height': 704},
                'source': 'independent actual controlled experiment; not current web generation',
                'generatedAt': completed['completedEpoch']})
    capabilities = config.get('policy', copy.deepcopy(CLOSED))
    if set(capabilities) != {'revision', 'approvedVariants'}:
        raise ValueError('EXACT_EVIDENCE_POLICY_REQUIRED')
    demonstrated = {(p['parameters']['environmentId'], p['parameters']['offsetDeg'], p['parameters']['strength']) for p in public}
    for env, pairs in capabilities['approvedVariants'].items():
        if any((env, *pair) not in demonstrated for pair in pairs):
            raise ValueError('UNMEASURED_CAPABILITY_NOT_ALLOWED')
    return capabilities, public, files
