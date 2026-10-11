"""Local quantitative comparison + contact sheets; never an AI/human quality verdict."""
import argparse
import html
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'project'))
from inference.jobs import atomic, read
from inference.images import digest
from inference.reuse import safe_file
from experiments.controls import CASES
from experiments.worker import verify_packet


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--packet', type=Path, required=True)
    p.add_argument('--results', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args(); a.out.mkdir(parents=True, exist_ok=False)
    import numpy as np
    from PIL import Image, ImageDraw, ImageFilter
    plan = verify_packet(a.packet)
    prepared = plan['input']['preprocessing']
    mask_image = Image.open(a.packet / 'inputs/interior-mask.png').convert('L')
    mask = np.asarray(mask_image) > 127
    if mask.shape != (704, 1280) or mask.sum() < 100:
        raise ValueError('ACTUAL_INTERIOR_MASK_REQUIRED')
    region = prepared['valid_region_xyxy']
    valid = np.zeros(mask.shape, dtype=bool)
    valid[region[1]:region[3], region[0]:region[2]] = True
    ys, xs = np.where(mask)
    cx, cy = (xs.min() + xs.max()) / 2, (ys.min() + ys.max()) / 2
    yy, xx = np.indices(mask.shape)
    masks = {'subject': mask, 'photoRegion': valid,
             'left': mask & (xx < cx), 'right': mask & (xx >= cx),
             'top': mask & (yy < cy), 'bottom': mask & (yy >= cy)}
    images, arrays, results = {}, {}, {}
    for case in CASES:
        directory = a.results / 'controls' / case['id']
        completed = read(safe_file(directory / '0', 'complete.json'))
        record = completed['result']
        frame = safe_file(directory / '0' / completed['attempt'], record['path'])
        if digest(frame.read_bytes()) != record['sha256']:
            raise ValueError('RETURNED_FRAME_HASH_MISMATCH')
        image = Image.open(frame); image.load()
        if image.mode != 'RGB' or image.size != (1280, 704):
            raise ValueError('RETURNED_FRAME_SIZE_MISMATCH')
        images[case['id']] = image
        arrays[case['id']] = np.asarray(image).astype('float32') / 255
        results[case['id']] = {'parameters': case, 'frameSha256': record['sha256'],
            'condition': read(directory / 'condition.json'),
            'modelCondition': read(directory / 'model-condition.json')}
    base = arrays['baseline']
    def linear(rgb):
        return np.where(rgb <= .04045, rgb / 12.92, ((rgb + .055) / 1.055) ** 2.4)
    def luma(rgb):
        return linear(rgb) @ np.array([.2126, .7152, .0722])
    for case in CASES:
        name = case['id']; rgb = arrays[name]; lum = luma(rgb)
        metrics = {}
        edges = np.asarray(images[name].convert('L').filter(ImageFilter.FIND_EDGES)).astype(float)
        base_edges = np.asarray(images['baseline'].convert('L').filter(ImageFilter.FIND_EDGES)).astype(float)
        for part, m in masks.items():
            metrics[part] = {'pixels': int(m.sum()), 'sRGB_MAE_vs_baseline': float(np.abs(rgb[m] - base[m]).mean()),
                'linearLumaMean': float(lum[m].mean()),
                'linearLumaP10P50P90': [float(x) for x in np.quantile(lum[m], [.1, .5, .9])],
                'channelMeanRGB': [float(x) for x in rgb[m].mean(axis=0)],
                'whiteClippedFraction': float((rgb[m].max(axis=1) >= 254 / 255).mean()),
                'edgeMAEvsBaseline': float(np.abs(edges[m] - base_edges[m]).mean() / 255)}
        results[name]['metrics'] = metrics
    repeat = results['baseline-repeat']['metrics']['subject']
    repeat_luma = abs(repeat['linearLumaMean'] - results['baseline']['metrics']['subject']['linearLumaMean'])
    threshold = max(2 / 255, 3 * repeat['sRGB_MAE_vs_baseline'])
    delta_threshold = max(.01, 3 * repeat_luma)
    for name in arrays:
        results[name]['machineDiscernibleScreen'] = results[name]['metrics']['subject']['sRGB_MAE_vs_baseline'] >= threshold
    low, mid, high = [results[n]['metrics']['subject']['linearLumaMean']
                      for n in ('strength-low', 'baseline', 'strength-high')]
    screen = {'discernibilityThreshold': threshold, 'linearLumaDeltaThreshold': delta_threshold,
        'strengthOrdered': low <= mid <= high,
        'strengthAtLeastOneUsefulDelta': max(mid-low, high-mid) >= delta_threshold,
        'rotationMinusDiscernible': results['rotation-minus45']['machineDiscernibleScreen'],
        'rotationPlusDiscernible': results['rotation-plus45']['machineDiscernibleScreen'],
        'NOT_A_PRODUCT_CAPABILITY_VERDICT': True}
    output = {'scope': 'REAL_RETURNED_GPU_IMAGES; automatic metrics not human visual acceptance',
        'sampleId': plan['sampleId'], 'cases': results, 'screen': screen,
        'humanVisualAcceptance': 'PENDING', 'assistantVisualObservation': 'NOT_YET_RECORDED',
        'limitations': 'sRGB-derived luma, JPEG, fixed approximate mask; no photometry or exact contour/texture preservation proof'}
    atomic(a.out / 'analysis.json', output)
    tiles = [('original prepared', Image.open(a.packet / 'inputs/photo.png'))] + [
        (case['id'], images[case['id']]) for case in CASES]
    sheet = Image.new('RGB', (960, 4 * 290), '#eff3f6'); draw = ImageDraw.Draw(sheet)
    for i, (name, image) in enumerate(tiles):
        x, y = (i % 2) * 480, (i // 2) * 290
        draw.text((x+12, y+8), name, fill='#102030')
        thumb = image.copy(); thumb.thumbnail((456, 251)); sheet.paste(thumb, (x+12, y+30))
    sheet.save(a.out / 'contact-sheet.jpg', quality=95)
    crops = Image.new('RGB', (960, 3*280), '#eff3f6'); draw = ImageDraw.Draw(crops)
    roi = prepared['derived_roi_xyxy'].get('surface_texture', [int(xs.min()), int(ys.min()), int(xs.max())+1, int(ys.max())+1])
    for i, case in enumerate(CASES):
        x, y = (i % 2)*480, (i//2)*280
        draw.text((x+12,y+8), case['id'], fill='#102030')
        crop = images[case['id']].crop(roi); crop.thumbnail((456,240)); crops.paste(crop,(x+12,y+30))
    crops.save(a.out / 'subject-crops.jpg', quality=95)
    body = '<h1>Controlled HDR comparison</h1><p>Real returned GPU frames. Metrics are not human acceptance.</p>'
    body += '<img style="max-width:100%" src="contact-sheet.jpg"><img style="max-width:100%" src="subject-crops.jpg">'
    body += '<pre>'+html.escape(json.dumps(screen, indent=2))+'</pre>'
    (a.out / 'report.html').write_text('<!doctype html><meta charset="utf-8"><title>HDR control experiment</title>'+body,encoding='utf-8')
    print(json.dumps(screen))


if __name__ == '__main__':
    main()
