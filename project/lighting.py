"""Versioned lighting identity foundation. Unproven controls remain CLOSED.

No GPU, upload, lifecycle, image effects or implicit historic migration here.
Callers must supply a reviewed capability record and real processing identities.
"""
import copy
import hashlib
import json
import math
import re

SCHEMA = 1
HEX_ID = re.compile(r'^[0-9a-f]{32}$')
CLOSED = {'revision': 'controls-not-validated-v1', 'approvedVariants': {}}


def canonical(value):
    def numeric(v):
        if isinstance(v, dict):
            return {k: numeric(x) for k, x in v.items()}
        if isinstance(v, list):
            return [numeric(x) for x in v]
        if type(v) is float:
            if not math.isfinite(v):
                raise ValueError('FINITE_IDENTITY_REQUIRED')
            return int(v) if v.is_integer() else v
        return v
    return json.dumps(numeric(value), sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def identity(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def normalize_parameters(value, presets, capabilities=CLOSED):
    if not isinstance(value, dict) or set(value) != {'environmentId', 'offsetDeg', 'strength'}:
        raise ValueError('EXACT_LIGHTING_PARAMETERS_REQUIRED')
    env = value['environmentId']
    if not isinstance(env, str) or env not in presets:
        raise ValueError('UNKNOWN_ENVIRONMENT')
    offset, strength = value['offsetDeg'], value['strength']
    if (type(offset) not in (int, float) or type(strength) not in (int, float) or
            not math.isfinite(offset) or not math.isfinite(strength)):
        raise ValueError('FINITE_NUMERIC_PARAMETERS_REQUIRED')
    allowed = capabilities.get('approvedVariants', {}).get(env, [])
    if (offset, strength) != (0, 1) and [offset, strength] not in allowed:
        raise ValueError('LIGHTING_CAPABILITY_NOT_VALIDATED')
    preset = presets[env]
    return {'schemaVersion': SCHEMA, 'environmentId': env, 'hdrSha256': preset['sha256'],
            'offsetDeg': int(offset) if float(offset).is_integer() else offset,
            'strength': int(strength) if float(strength).is_integer() else strength,
            'processing': 'fixed-upstream-loading-v1' if (offset, strength) == (0, 1) else 'hdr-controls-v1',
            'capabilityRevision': 'legacy-fixed-preset' if (offset, strength) == (0, 1) else capabilities['revision']}


def normalize_scheme(value, presets, capabilities=CLOSED):
    fields = {'schemaVersion', 'planId', 'version', 'name', 'parameters', 'inputId', 'parentVersion'}
    if (not isinstance(value, dict) or set(value) != fields or
            type(value.get('schemaVersion')) is not int or value.get('schemaVersion') != SCHEMA):
        raise ValueError('EXACT_VERSIONED_SCHEME_REQUIRED')
    if not isinstance(value['planId'], str) or not HEX_ID.fullmatch(value['planId']):
        raise ValueError('PLAN_ID_REQUIRED')
    version, parent = value['version'], value['parentVersion']
    if (type(version) is not int or not 1 <= version <= 1000 or
            (parent is not None and (type(parent) is not int or not 1 <= parent < version))):
        raise ValueError('PLAN_LINEAGE_INVALID')
    name = value['name']
    if type(name) is not str or not 1 <= len(name.strip()) <= 60 or any(ord(c) < 32 for c in name):
        raise ValueError('PLAN_NAME_INVALID')
    input_id = value['inputId']
    if input_id is not None and (type(input_id) is not str or not HEX_ID.fullmatch(input_id)):
        raise ValueError('INPUT_ASSOCIATION_INVALID')
    params = normalize_parameters(value['parameters'], presets, capabilities)
    return {**copy.deepcopy(value), 'name': name.strip(), 'parameters': params, 'recipeKey': identity(params)}


def result_binding(scheme, input_record, processing_record):
    """Input affinity is not interchangeable with a cross-photo reusable recipe."""
    required_input = {'id', 'sha256', 'canvas'}
    required_processing = {'upstreamCommit', 'forwardModel', 'tokenizer', 'patch',
                           'adapterVersion', 'seed', 'steps', 'guidance', 'width', 'height', 'frames'}
    if not required_input <= set(input_record) or set(processing_record) != required_processing:
        raise ValueError('REAL_PROCESSING_IDENTITY_REQUIRED')
    if scheme['inputId'] != input_record['id']:
        raise ValueError('SCHEME_INPUT_MISMATCH')
    value = {'recipeKey': scheme['recipeKey'],
        'input': {k: input_record[k] for k in ('id', 'sha256', 'canvas')},
        'processing': copy.deepcopy(processing_record)}
    return {'resultKey': identity(value), **value, 'submittedPlan': {
        'planId': scheme['planId'], 'version': scheme['version']}}


def idempotency_fingerprint(scheme, original_sha256):
    return identity({'planId': scheme['planId'], 'version': scheme['version'],
                     'inputId': scheme['inputId'], 'recipeKey': scheme['recipeKey'],
                     'originalSha256': original_sha256})


def legacy_compatibility(preset_id, presets):
    """New compatibility descriptor ONLY; never edits a historical result record."""
    if preset_id not in presets:
        raise ValueError('UNKNOWN_LEGACY_PRESET')
    return {'kind': 'legacy-fixed-preset', 'environmentId': preset_id,
            'hdrSha256': presets[preset_id]['sha256'], 'controlParametersMeasured': False,
            'compatibility': 'nominal original helper loading only; not a control experiment',
            'eligibleOnlyFor': {'environmentId': preset_id, 'offsetDeg': 0, 'strength': 1}}
