"""Deterministic source-only GPU service bundle, built before any paid start."""
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile

from runtime.driver import BUNDLE_FILES
from inference.jobs import atomic

ROOT=Path(__file__).resolve().parent.parent
FILES=sorted(set(BUNDLE_FILES+['start.py','project/guard_runtime.py','project/gpu_session.py','project/worker_link.py',
    'project/gpu_model.py','project/resident_executor.py','project/resident_model.py','project/model_contract.py',
    'project/security.py','project/mtls_relay.py','project/worker_tls.py','project/inference/driver.py','project/runtime/driver.py']))
HELPERS=['cloud/remote_probe.py','project/gpu_bootstrap_vm.py','project/gpu_bootstrap_container.py',
         'project/gpu_bootstrap_ssh.py','project/gpu_bootstrap_package.py','project/gpu_bootstrap.py',
         'project/gpu_session.py','project/worker_link.py','project/direct_bootstrap.py']


def helper_sha():
    return hashlib.sha256(b'\0'.join((ROOT/name).read_bytes() for name in HELPERS)).hexdigest()


def archive(files):
    buffer=io.BytesIO()
    with gzip.GzipFile(fileobj=buffer,mode='wb',mtime=0,filename='') as compressed:
        with tarfile.open(fileobj=compressed,mode='w') as tar:
            for name,raw in sorted(files.items()):
                item=tarfile.TarInfo(name);item.size=len(raw);item.mode=0o600;item.mtime=0
                tar.addfile(item,io.BytesIO(raw))
    return buffer.getvalue()


def build(directory):
    directory=Path(directory)
    if not directory.is_absolute() or directory.resolve().is_relative_to(ROOT) or any(p.is_symlink() for p in (directory,*directory.parents)):
        raise ValueError('PRIVATE_GPU_PREPARATION_ROOT_REQUIRED')
    directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    files={}
    for name in FILES:
        path=ROOT/name
        if any(p.is_symlink() for p in (path,*path.parents)) or not path.is_file():raise ValueError('GPU_SOURCE_UNSAFE')
        raw=path.read_bytes()
        if len(raw)>2*1024**2:raise ValueError('GPU_SOURCE_TOO_LARGE')
        files[name]=raw
    if len(files)>128 or sum(map(len,files.values()))>8*1024**2:raise ValueError('GPU_BUNDLE_TOO_LARGE')
    records=[{'path':n,'sha256':hashlib.sha256(v).hexdigest(),'bytes':len(v)} for n,v in sorted(files.items())]
    files['bundle_contents.json']=json.dumps({'schemaVersion':1,'files':records},sort_keys=True,separators=(',',':')).encode()
    raw=archive(files);target=directory/'gpu-service.tar.gz'
    with target.open('xb') as stream:stream.write(raw)
    target.chmod(0o600)
    value={'schemaVersion':1,'archive':str(target),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),
           'files':records,'helperSha256':helper_sha(),'containsCredentials':False,'containsWeights':False}
    atomic(directory/'bundle.json',value);(directory/'bundle.json').chmod(0o600)
    return value


def freeze(root):
    identity=hashlib.sha256(b'\0'.join((ROOT/name).read_bytes() for name in FILES)+helper_sha().encode()).hexdigest()
    directory=Path(root)/identity
    if (directory/'bundle.json').is_file():
        value=json.loads((directory/'bundle.json').read_text())
        if value['helperSha256']!=helper_sha() or hashlib.sha256(Path(value['archive']).read_bytes()).hexdigest()!=value['sha256']:
            raise ValueError('FROZEN_GPU_BUNDLE_CHANGED')
        return value
    return build(directory)
