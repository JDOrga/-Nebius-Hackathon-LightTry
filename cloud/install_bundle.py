"""Reviewed installer contract extracted from the existing tar/stdin installer.
Runs only when explicitly sent through the guarded remote transport.
"""
import base64
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tarfile

def main(q):
    rid=q['run_id']
    if len(rid)!=32 or any(c not in '0123456789abcdef' for c in rid):raise ValueError('INVALID_RUN_ID')
    base=Path(q['data_root']).resolve()
    if not base.is_relative_to('/home/jovyan') or not base.is_dir():raise ValueError('PERSISTENT_DATA_ROOT_REQUIRED')
    if shutil.disk_usage(base).free<1024**3:raise ValueError('PERSISTENT_SPACE_REQUIRED')
    dest=base/('preview-'+rid);dest.mkdir();archive=dest/'received.tar.gz';h=hashlib.sha256()
    size=0
    with archive.open('xb') as f:
        for block in iter(lambda:sys.stdin.buffer.read(8*1024**2),b''):
            size+=len(block)
            if size>100*1024**2:raise ValueError('CODE_ARCHIVE_TOO_LARGE')
            h.update(block);f.write(block)
    if h.hexdigest()!=q['archive_sha256']:raise ValueError('BUNDLE_SHA256_MISMATCH')
    with tarfile.open(archive,'r:gz') as t:
        members=t.getmembers();names=set()
        if sum(m.size for m in members)>100*1024**2:raise ValueError('EXPANDED_ARCHIVE_TOO_LARGE')
        for m in members:
            if not m.isfile() or Path(m.name).is_absolute() or '..' in Path(m.name).parts or ':' in m.name or '\\' in m.name or m.name in names or (dest/m.name).exists():raise ValueError('UNSAFE_ARCHIVE_MEMBER')
            names.add(m.name)
        t.extractall(dest,filter='data')
    contents=json.loads((dest/'bundle_contents.json').read_text())['files']
    if names!={e['path'] for e in contents}|{'bundle_contents.json'}:raise ValueError('BUNDLE_CONTENTS_MISMATCH')
    for e in contents:
        if hashlib.sha256((dest/e['path']).read_bytes()).hexdigest()!=e['sha256']:raise ValueError('BUNDLE_FILE_HASH_MISMATCH')
    print(json.dumps({'preparation':str(dest),'files_verified':len(names)}))

if __name__=='__main__':main(json.loads(base64.b64decode(sys.argv[1])))
