"""One-time, read-only import of existing full-frame Cosmos preview identities.

Writes only project/data/catalog.json. Never runs models or cloud tooling.
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
SOURCE = REPO / 'controlled-tests/20261007-four-materials/executions/2aa06a2c4e154ad0b03424c0d1d3dcca'


def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def build():
    from PIL import Image
    prepared = json.loads((SOURCE / 'prepared_inputs.json').read_text(encoding='utf-8'))
    config = json.loads((SOURCE / 'configuration.json').read_text(encoding='utf-8'))
    integrity = json.loads((SOURCE / 'local_integrity.json').read_text(encoding='utf-8'))
    known = {item['path'].replace('\\', '/'): item['sha256'] for item in integrity['files']}
    performance = json.loads((SOURCE / 'run/forward-performance/performance.json').read_text())
    assert performance['state'] == 'official_entry_completed'
    names = [('sunny', '晴日公园', '自然日光的氛围'), ('sunrise', '粉色晨光', '偏粉色的晨光氛围'), ('street', '夜间街灯', '街灯环境的明暗与色调')]
    expected = ['sunny_vondelpark_2k.hdr', 'pink_sunrise_2k.hdr', 'street_lamp_2k.hdr']
    assert [h['filename'] for h in config['hdrs']] == expected
    presets = [dict(id=names[i][0], name=names[i][1], description=names[i][2], hdr=h['filename'], index=i, sha256=h['sha256']) for i, h in enumerate(config['hdrs'])]
    labels = [('陶罐', '哑光陶器'), ('茶盒', '印刷金属盒'), ('金属壶', '反光金属'), ('玻璃杯', '效果不稳定')]
    assets, samples = {}, []

    def asset(key, path, sha):
        assert digest(path) == sha, f'Source identity mismatch: {path}'
        with Image.open(path) as image:
            width, height = image.size
            image.verify()
        assets[key] = dict(path=path.relative_to(REPO).as_posix(), sha256=sha, bytes=path.stat().st_size, width=width, height=height)
        return dict(assetId=key, url='/assets/' + key, width=width, height=height, sha256=sha)

    for i, item in enumerate(prepared['images']):
        sid = Path(item['file']).stem
        assert performance['generation_counts'][sid] == 3
        original = asset(sid + '-original', SOURCE / 'originals' / item['file'], item['sha256'])
        input_image = asset(sid + '-input', SOURCE / 'inputs-srgb' / (sid + '.png'), item['derived_sha256'])
        assert (input_image['width'], input_image['height']) == (1280, 704)
        results = {}
        for preset in presets:
            j = preset['index']
            flat = f'run/forward/{sid}__0000.relit_{j:04d}.jpg'
            frame = SOURCE / f'run/forward/relit_frames_{j:04d}/{sid}/0000.0000.jpg'
            # The exported JPEG and canonical frame copy must be identical.
            assert digest(frame) == known[flat] == digest(SOURCE / flat)
            result = asset(sid + '-' + preset['id'], frame, known[flat])
            assert (result['width'], result['height']) == (1280, 704)
            results[preset['id']] = result
        samples.append(dict(id=sid, name=labels[i][0], material=labels[i][1], date='2026-10-07',
            runId=SOURCE.name, original=original, input=input_image, results=results,
            unstable=i == 3, warning='透明边缘与透射背景明显变化，效果不稳定。' if i == 3 else '',
            canvas=dict(width=1280, height=704, validRegion=item['valid_region_xyxy'], paddingRgb=item['padding_rgb'], policy='按记录等比缩放，保留中性灰留白；完整画布，无主体裁切。'),
            credit={k: item[k] for k in ('title', 'creator', 'license', 'license_url', 'source_url', 'color_handling')}))
    catalog = dict(version=1, renderer='Cosmos Diffusion Renderer', presets=presets, samples=samples, assets=assets,
        provenance=dict(runId=SOURCE.name, sourceDirectory=SOURCE.relative_to(REPO).as_posix(),
            checkedRecords=[str((SOURCE / p).relative_to(REPO).as_posix()) for p in ('prepared_inputs.json', 'configuration.json', 'local_integrity.json', 'run/forward-performance/performance.json')],
            note='Full-frame forward JPEG only. Later tea basecolor, local-scale crops and CPU fusion candidates are excluded. Historical final acceptance process failed; forward generation completed, hashes verified.'))
    (ROOT / 'data/catalog.json').write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Checked {len(samples)} sample groups / 12 HDR results / {len(assets)} image identities.')


if __name__ == '__main__':
    build()
