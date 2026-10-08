"""Extracted streaming results export: bounded size, no symlinks, no raw tensors."""
import base64
import gzip
import json
from pathlib import Path
import sys
import tarfile

def main(q):
    root=Path(q['root']).resolve();base=Path(q['data_root']).resolve()
    if not base.is_relative_to('/home/jovyan') or not root.is_relative_to(base):raise ValueError('RESULT_ROOT_OUTSIDE_DATA_ROOT')
    paths=[p for p in root.rglob('*') if p.is_file() and p.suffix.lower() in ('.jpg','.png','.json','.log')]
    if sum(p.stat().st_size for p in paths)>512*1024**2:raise ValueError('RESULT_EXPORT_TOO_LARGE')
    with gzip.GzipFile(fileobj=sys.stdout.buffer,mode='wb',compresslevel=1) as z,tarfile.open(fileobj=z,mode='w|') as t:
        for p in sorted(paths):
            if p.is_symlink() or not p.resolve().is_relative_to(root):raise ValueError('RESULT_SYMLINK_FORBIDDEN')
            t.add(p,arcname=str(p.relative_to(root)),recursive=False)

if __name__=='__main__':main(json.loads(base64.b64decode(sys.argv[1])))
