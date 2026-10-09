"""Bounded decoding and the established EXIF/sRGB/neutral-gray preprocessing."""
import hashlib
import io
import warnings
from pathlib import Path

MAX_BYTES = 20 * 1024**2
MAX_PIXELS = 40_000_000
FORMATS = {'JPEG': 'image/jpeg', 'PNG': 'image/png', 'WEBP': 'image/webp'}


class InputError(ValueError):
    pass


def digest(data):
    return hashlib.sha256(data).hexdigest()


def decode(data, mime=None):
    from PIL import Image, ImageOps
    if not data or len(data) > MAX_BYTES:
        raise InputError('图片为空或超过 20 MB。')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                if image.format not in FORMATS or (mime and FORMATS[image.format] != mime):
                    raise InputError('只接受内容与格式一致的 JPG、PNG、WebP。')
                w, h = image.size
                if min(w, h) < 32 or max(w, h) > 16384 or w * h > MAX_PIXELS:
                    raise InputError('图片宽高须至少 32 px，最多 4000 万像素，单边不超过 16384 px。')
                if getattr(image, 'n_frames', 1) != 1:
                    raise InputError('只接受静态单帧图片。')
                image.verify()
            with Image.open(io.BytesIO(data)) as image:
                image.load()
                profile = image.info.get('icc_profile')
                orientation = image.getexif().get(274, 1)
                rgb = ImageOps.exif_transpose(image).convert('RGB')
                return rgb, profile, {'width': rgb.width, 'height': rgb.height,
                    'mime': FORMATS[image.format], 'sha256': digest(data), 'bytes': len(data),
                    'exifOrientation': orientation}
    except InputError:
        raise
    except Exception as error:
        raise InputError('图片无法完整解码，可能损坏或包含无效元数据。') from error


def prepare(data, target):
    # Extracted from the validated finalize_inputs.py algorithm, without its
    # historical paths, ROI diagnostics or asset-pack dependencies.
    from PIL import Image, ImageCms
    rgb, profile, metadata = decode(data)
    srgb = ImageCms.createProfile('sRGB')
    icc = ImageCms.ImageCmsProfile(srgb).tobytes()
    if profile:
        try:
            rgb = ImageCms.profileToProfile(rgb, ImageCms.ImageCmsProfile(io.BytesIO(profile)),
                                            srgb, renderingIntent=1, outputMode='RGB')
        except Exception as error:
            raise InputError('嵌入的颜色配置无效，无法转换到 sRGB。') from error
    w, h = rgb.size
    scale = min(1280 / w, 704 / h)
    nw, nh = max(1, round(w * scale)), max(1, round(h * scale))
    x, y = (1280 - nw) // 2, (704 - nh) // 2
    canvas = Image.new('RGB', (1280, 704), (127, 127, 127))
    canvas.paste(rgb.resize((nw, nh), Image.Resampling.LANCZOS), (x, y))
    buffer = io.BytesIO()
    canvas.save(buffer, format='PNG', icc_profile=icc)
    payload = buffer.getvalue()
    Path(target).write_bytes(payload)
    return {'width': 1280, 'height': 704, 'sha256': digest(payload), 'bytes': len(payload),
        'validRegion': [x, y, x + nw, y + nh], 'paddingRGB': [127, 127, 127],
        'colorHandling': 'embedded ICC to sRGB, relative colorimetric' if profile else 'decoded RGB assumed sRGB',
        'orientationHandling': 'EXIF transpose', 'scaleXY': [nw / w, nh / h],
        'resize': 'LANCZOS; nearest-pixel rounding; centered padding; no crop',
        'original': metadata}
