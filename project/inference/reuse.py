"""Completed, content-addressed inverse evidence. No HTTP paths or GPU imports."""
import io
import json
import shutil
from pathlib import Path, PurePosixPath

from .jobs import atomic, read, ID
from .images import digest, photo_region, MAX_BYTES, PREPROCESS_VERSION

LABELS = ('basecolor', 'normal', 'depth', 'roughness', 'metallic')


def identity(request, payload, weights, patch):
    """Encoded metadata can vary; bind the exact RGB pixels the dataset sees."""
    from PIL import Image
    if digest(payload) != request['input']['sha256']:
        raise ValueError('INPUT_HASH_MISMATCH')
    canvas = request['input']['canvas']
    photo_region(canvas)
    with Image.open(io.BytesIO(payload)) as image:
        image.load()
        if image.size != (1280, 704) or image.mode != 'RGB':
            raise ValueError('INPUT_CANVAS_MISMATCH')
        pixels = digest(image.tobytes())
    config = request['runConfig']
    model = [{k: e.get(k) for k in ('path', 'revision', 'size', 'sha256', 'git_blob', 'md5')}
             for e in weights['files'] if e['path'].startswith(
                 ('Diffusion_Renderer_Inverse_Cosmos_7B/', 'Cosmos-Tokenize1-CV8x8x8-720p/'))]
    if not all(any(e['path'].startswith(prefix) for e in model) for prefix in
               ('Diffusion_Renderer_Inverse_Cosmos_7B/', 'Cosmos-Tokenize1-CV8x8x8-720p/')):
        raise ValueError('INVERSE_MODEL_IDENTITY_REQUIRED')
    # Inverse imports rendering_utils -> env_sampling. utils_env_proj is forward only.
    inverse_patch = [e for e in patch['files'] if e['path'].endswith(
        ('/rendering_utils.py', '/env_sampling.py'))]
    if len(inverse_patch) != 2:
        raise ValueError('INVERSE_PATCH_IDENTITY_REQUIRED')
    if canvas.get('rgbSha256', pixels) != pixels:
        raise ValueError('INPUT_PIXEL_HASH_MISMATCH')
    return {'schema': 1, 'rgbSha256': pixels, 'preprocessing': canvas.get('preprocessingVersion', PREPROCESS_VERSION),
            'canvas': {k: canvas[k] for k in ('width', 'height', 'validRegion', 'paddingRGB',
                                             'colorHandling', 'orientationHandling', 'resize')},
            'config': {k: config[k] for k in ('upstreamCommit', 'width', 'height', 'frames',
                                             'steps', 'seed', 'guidance', 'offload')},
            'inverseDefaults': {'normalizeNormal': False, 'groupMode': 'webdataset',
                                'passes': list(LABELS), 'randomPolicy': 'upstream-sequential-v1'},
            'model': model, 'patch': inverse_patch}


def key(value):
    return digest(json.dumps(value, sort_keys=True, separators=(',', ':')).encode())


def safe_file(root, relative):
    path = PurePosixPath(relative)
    if path.is_absolute() or '..' in path.parts or ':' in relative or '\\' in relative:
        raise ValueError('UNSAFE_ARTIFACT_PATH')
    target = root.joinpath(*path.parts)
    if any(p.is_symlink() or getattr(p, 'is_junction', lambda: False)() for p in (root, target, *target.parents)) or not target.resolve().is_relative_to(root.resolve()):
        raise ValueError('UNSAFE_ARTIFACT_PATH')
    if not target.is_file() or target.stat().st_size > MAX_BYTES:
        raise ValueError('ARTIFACT_MISSING_OR_OVERSIZED')
    return target


def artifacts(root):
    from PIL import Image, ImageStat
    records = []
    found = sorted(root.rglob('*.jpg'))
    if len(found) != 5:
        raise ValueError('EXACTLY_FIVE_GBUFFERS_REQUIRED')
    for label in LABELS:
        matches = [p for p in found if p.name.endswith('.' + label + '.jpg')]
        if len(matches) != 1:
            raise ValueError('GBUFFER_CHANNEL_MISSING')
        relative = matches[0].relative_to(root).as_posix()
        path = safe_file(root, relative)
        payload = path.read_bytes()
        with Image.open(io.BytesIO(payload)) as image:
            image.load()
            if image.format != 'JPEG' or image.mode != 'RGB' or image.size != (1280, 704):
                raise ValueError('GBUFFER_DECODE_MISMATCH')
            if label not in ('roughness', 'metallic') and max(ImageStat.Stat(image).stddev) < .5:
                raise ValueError('GBUFFER_CONSTANT')
        records.append({'channel': label, 'path': relative, 'bytes': len(payload), 'sha256': digest(payload)})
    # The dataset groups channels by clip/frame; five unrelated files are not a set.
    if len({r['path'].rsplit('.', 2)[0] for r in records}) != 1:
        raise ValueError('GBUFFER_FRAME_MISMATCH')
    return records


def complete(root, value, source):
    """Publish only after the inverse child exited successfully and was validated."""
    marker = root / 'inverse-complete.json'
    if marker.exists():
        return validate(root, value)
    if (not isinstance(source, dict) or not all(isinstance(source.get(k), str) and ID.fullmatch(source[k])
            for k in ('taskId', 'nonce')) or source.get('inverseExitCode') != 0):
        raise ValueError('COMPLETED_SOURCE_REQUIRED')
    record = {'schema': 1, 'identity': value, 'key': key(value), 'source': source,
              'artifacts': artifacts(root / 'gbuffer_frames')}
    atomic(marker, record)
    return record


def validate(root, value):
    marker = safe_file(root, 'inverse-complete.json')
    record = read(marker)
    if not isinstance(record, dict) or record.get('schema') != 1 or record.get('key') != key(value) or record.get('identity') != value:
        raise ValueError('INVERSE_IDENTITY_MISMATCH')
    source = record.get('source')
    if (not isinstance(source, dict) or not all(isinstance(source.get(k), str) and ID.fullmatch(source[k])
            for k in ('taskId', 'nonce')) or source.get('inverseExitCode') != 0):
        raise ValueError('UNKNOWN_INVERSE_SOURCE')
    if artifacts(root / 'gbuffer_frames') != record['artifacts']:
        raise ValueError('INVERSE_ARTIFACT_MISMATCH')
    return record


def copy_completed(source, destination, value):
    record = validate(source, value)
    destination.mkdir()  # exclusive; never merge partial output
    for item in record['artifacts']:
        src = safe_file(source / 'gbuffer_frames', item['path'])
        target = destination / 'gbuffer_frames' / item['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, target)
    if artifacts(destination / 'gbuffer_frames') != record['artifacts']:
        raise ValueError('INVERSE_COPY_MISMATCH')
    atomic(destination / 'inverse-complete.json', record)  # source identity stays historical
    return record
