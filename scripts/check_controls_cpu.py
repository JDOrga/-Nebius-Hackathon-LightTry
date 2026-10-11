"""Actual pinned helper on CPU. Distinguishes input response from neural response."""
import argparse
import builtins
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'project'))
from experiments.controls import CASES, condition_hook, normalize
from inference.jobs import atomic, read


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--repo', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args(); a.out.mkdir(parents=True, exist_ok=False)
    patch = read(ROOT / 'manifests/patch_manifest.json')
    for entry in patch['files']:
        if hashlib.sha256((a.repo / entry['path']).read_bytes()).hexdigest() != entry['after_sha256']:
            raise ValueError('PATCH_CONTENT_CHANGED')
    original = builtins.__import__
    def guarded(name, *args, **kw):
        if name.startswith('nvdiffrast'):
            raise ValueError('NVDIFFRAST_NOT_ALLOWED')
        return original(name, *args, **kw)
    builtins.__import__ = guarded
    import torch
    import numpy as np
    import cv2
    import imageio.v3 as iio
    torch.set_num_threads(4)
    sys.path.insert(0, str(a.repo))
    from cosmos_predict1.diffusion.inference.diffusion_renderer_utils.utils_env_proj import process_environment_map
    hdr = a.repo / 'asset/examples/hdri_examples/sunny_vondelpark_2k.hdr'
    expected_hdr = read(ROOT / 'project/data/catalog.json')['presets'][0]['sha256']
    if hashlib.sha256(hdr.read_bytes()).hexdigest() != expected_hdr:
        raise ValueError('HDR_CONTENT_CHANGED')
    decoded = iio.imread(hdr, flags=cv2.IMREAD_UNCHANGED, plugin='opencv')
    if not np.isfinite(decoded).all() or decoded.dtype != np.float32:
        raise ValueError('HDR_DECODE_INVALID')
    baseline = {}; records = []
    for case in CASES:
        directory = a.out / case['id']; directory.mkdir()
        hook, calls = condition_hook(process_environment_map, case, directory, baseline)
        hook(str(hdr), resolution=(704, 1280), num_frames=1, fixed_pose=True,
             rotate_envlight=False, env_format=['proj'], device='cpu')
        record = calls[0]
        multiplied = decoded * case['strength']
        pixels = int(decoded.shape[1] * normalize(case['offsetDeg'], case['strength'])['envRot'] / 360)
        record.update(rawMin=float(multiplied.min()), rawMax=float(multiplied.max()),
            rawClampedFraction=float(((multiplied < 0) | (multiplied > 65504)).mean()),
            effectiveRollPixels=pixels, hdrWidth=int(decoded.shape[1]),
            effectiveOffsetDeg=(pixels - int(decoded.shape[1] * 180 / 360)) * 360 / decoded.shape[1])
        atomic(directory / 'condition.json', record); records.append(record)
    # Full-resolution exact input repeat and a materially different tensor for each changed factor.
    if records[-1]['fields']['env_ldr']['sha256'] != records[0]['fields']['env_ldr']['sha256']:
        raise ValueError('CPU_BASELINE_REPEAT_DIFFERENT')
    if any(r['fields']['env_ldr']['maeVsBaseline'] <= 0 for r in records[1:5]):
        raise ValueError('CPU_FACTOR_HAS_NO_EFFECT')
    result = {'status': 'passed', 'device': 'cpu', 'resolution': [704, 1280],
        'torch': torch.__version__, 'numpy': np.__version__, 'hdrSha256': expected_hdr,
        'inputConditionResponse': 'observed', 'neuralOutputControl': 'NOT_TESTED',
        'loadingConvention': 'env_rot=180 and env_flip=true means original upstream orientation',
        'rawClamping': 'all checked per case; mapped LDR/log saturation recorded separately',
        'cases': records}
    atomic(a.out / 'report.json', result)
    print(json.dumps({'status': result['status'], 'inputConditionResponse': 'observed',
        'neuralOutputControl': 'NOT_TESTED', 'cases': len(records),
        'maxRawHdr': max(r['rawMax'] for r in records),
        'maxRawClampFraction': max(r['rawClampedFraction'] for r in records)}))


if __name__ == '__main__':
    main()
