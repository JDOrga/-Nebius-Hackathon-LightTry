"""Install the local-only, separately supplied demo ZIP. Standard library, no network."""
import argparse
import hashlib
import json
import tempfile
import zipfile
from pathlib import Path

from server import ROOT, load_catalog, resolve_assets_dir


def install(archive, destination):
    destination = resolve_assets_dir(destination)
    if destination.exists():
        raise ValueError('目标已存在，不覆盖现有素材。请验证现有目录或选择新的 --assets-dir。')
    catalog = json.loads((ROOT / 'data/catalog.json').read_text(encoding='utf-8'))
    package = json.loads((ROOT / 'data/demo-package.json').read_text(encoding='utf-8'))
    expected = {item['path']: item for item in catalog['assets'].values()}
    expected.update(package['records'])
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='lighttry-install-', dir=destination.parent) as temporary:
        staging = Path(temporary) / 'demo-assets'
        staging.mkdir()
        with zipfile.ZipFile(archive) as bundle:
            infos = bundle.infolist()
            names = [info.filename for info in infos]
            if len(set(names)) != len(names) or set(names) != {'demo-assets/' + name for name in expected}:
                raise ValueError('素材包文件清单不匹配；拒绝额外文件、重复路径或不完整包。')
            for info in infos:
                name = info.filename.removeprefix('demo-assets/')
                record = expected[name]
                if info.file_size != record['bytes']:
                    raise ValueError('素材大小不匹配：' + name)
                payload = bundle.read(info)
                if hashlib.sha256(payload).hexdigest() != record['sha256']:
                    raise ValueError('素材 SHA256 不匹配：' + name)
                target = staging / name
                if not target.resolve().is_relative_to(staging.resolve()):
                    raise ValueError('素材包路径越界')
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(payload)
        load_catalog(staging)
        # Same-volume rename after validation; no overwrite of an existing installation.
        staging.rename(destination)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--assets-dir', help='默认 project/demo-assets；也支持 LIGHTTRY_DEMO_ASSETS')
    args = parser.parse_args()
    try:
        destination = install(args.archive, args.assets_dir)
    except (ValueError, OSError, zipfile.BadZipFile) as error:
        parser.exit(2, str(error) + '\n')
    print('素材图片及来源记录已校验并安装：' + str(destination))


if __name__ == '__main__':
    main()
