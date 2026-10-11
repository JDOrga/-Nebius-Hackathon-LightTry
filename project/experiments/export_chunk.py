"""Small, allowlisted recovery exports through the SAME guarded SSH/SCP channel.

No changed execution, regenerated case, enlarged transfer timeout or VM lifecycle.
Skip full-resolution HDR conditioning PNGs; their numeric/model-entry proof stays.
"""
import base64
import gzip
import io
import json
from pathlib import Path
import sys
import tarfile

PAIRS = {
    'pair0': ('baseline', 'rotation-minus45'),
    'pair1': ('rotation-plus45', 'strength-low'),
    'pair2': ('strength-high', 'baseline-repeat'),
    'case0': ('baseline',),
    'case1': ('rotation-minus45',),
    'case2': ('rotation-plus45',),
    'case3': ('strength-low',),
    'case4': ('strength-high',),
    'case5': ('baseline-repeat',),
}


def payload(root, part):
    if part not in ('metadata', *PAIRS):
        raise ValueError('ALLOWLISTED_RESULT_CHUNK_REQUIRED')
    selected = []
    fixed = {'execution.json', 'configuration.json', 'weights_verification.json',
             'preflight.json', 'preflight.log', 'forward-timing.jsonl', 'presets/identities.json'}
    for path in sorted(root.rglob('*')):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix(); parts = path.relative_to(root).parts
        take = part == 'metadata' and (rel in fixed or
            (len(parts) == 1 and rel.startswith(('forward-', 'preflight-')) and rel.endswith('.log')))
        if part in PAIRS and len(parts) >= 3 and parts[0] == 'controls' and parts[1] in PAIRS[part]:
            # Official writer also saves a byte-identical flat JPEG. Export only
            # the canonical frame selected and hashed by complete.json.
            take = path.suffix == '.json' or (path.suffix == '.jpg' and 'relit_frames_0000' in parts)
        if take:
            if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()) or path.stat().st_size > 1024**2:
                raise ValueError('INVALID_EXPERIMENT_EXPORT_FILE')
            selected.append((path, rel))
    if not selected or sum(p.stat().st_size for p, _ in selected) > 2*1024**2:
        raise ValueError('EXPERIMENT_EXPORT_CHUNK_SIZE_INVALID')
    stream = io.BytesIO()
    with gzip.GzipFile(fileobj=stream, mode='wb', compresslevel=6, mtime=0) as zipped:
        with tarfile.open(fileobj=zipped, mode='w|') as tar:
            for path, rel in selected:
                tar.add(path, arcname=rel, recursive=False)
    data = stream.getvalue()
    if len(data) > 160*1024:
        raise ValueError('SMALL_CHUNK_EXCEEDS_160_KIB_NO_TIMEOUT_INCREASE')
    return data


def main(q):
    root = Path(q['root']).resolve(); base = Path(q['data_root']).resolve()
    if not base.is_relative_to('/home/jovyan') or not root.is_relative_to(base) or root.name != 'run':
        raise ValueError('EXACT_EXPERIMENT_RESULT_ROOT_REQUIRED')
    sys.stdout.buffer.write(payload(root, q['part']))


if __name__ == '__main__':
    main(json.loads(base64.b64decode(sys.argv[1])))
