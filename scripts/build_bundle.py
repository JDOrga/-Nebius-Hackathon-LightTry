"""Create a local inference code archive from a second explicit allowlist."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import tarfile

ROOT=Path(__file__).resolve().parents[1]
FILES=['scripts/run_experiment.py','scripts/weights.py','scripts/validate_outputs.py',
       'scripts/preflight.py','scripts/apply_hdr_patch.py','prototype/env_sampling.py',
       'patches/replace_hdr_sampling.patch','manifests/patch_manifest.json',
       'manifests/weights_manifest.json','manifests/upstream.json','third_party/Cosmos-LICENSE']

def main():
    p=argparse.ArgumentParser();p.add_argument('--run-directory',type=Path,required=True);a=p.parse_args()
    run=a.run_directory.resolve()
    if run.parent != ROOT/'cloud-runs' or len(run.name)!=32 or any(c not in '0123456789abcdef' for c in run.name):
        raise ValueError('RUN_DIRECTORY_MUST_BE_CURRENT_LOCAL_GUARDED_RUN')
    archive=run/'inference-code.tar.gz'
    if archive.exists() or (run/'bundle.json').exists():raise FileExistsError('Preserve prior bundle')
    entries=[{'path':rel,'sha256':hashlib.sha256((ROOT/rel).read_bytes()).hexdigest()} for rel in FILES]
    with archive.open('xb') as out, tarfile.open(fileobj=out,mode='w:gz') as t:
        for rel in FILES:
            if (ROOT/rel).is_symlink():raise ValueError('SYMLINK_NOT_ALLOWED')
            t.add(ROOT/rel,arcname=rel,recursive=False)
        data=json.dumps({'files':entries}).encode();info=tarfile.TarInfo('bundle_contents.json');info.size=len(data);t.addfile(info,io.BytesIO(data))
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    (run/'bundle.json').write_text(json.dumps({'archive':archive.name,'archive_path':str(archive),'sha256':digest},indent=2))
    print(json.dumps({'local_only':True,'cloud_calls':0,'files':len(FILES),'sha256':digest}))

if __name__=='__main__':main()
