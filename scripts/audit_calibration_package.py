"""Unpack/hash/entry audit OFFLINE. Dispatch fixture intercepts Popen, no launch."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tarfile
import tempfile
import types
from unittest.mock import patch


def audit(package,output):
    package=package.resolve();output.mkdir();receipt=json.loads((package/'bundle.json').read_text(encoding='utf-8'))
    archive=package/'inference-code.tar.gz';digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    if digest(archive)!=receipt['sha256'] or archive.stat().st_size!=receipt['bytes']:raise ValueError('ARCHIVE_IDENTITY_MISMATCH')
    unpack=output/'unpacked';unpack.mkdir();inventory=[]
    with tarfile.open(archive,'r:gz') as tar:
        names=set()
        for member in tar.getmembers():
            rel=PurePosixPath(member.name)
            if not member.isfile() or rel.is_absolute() or '..' in rel.parts or ':' in member.name or '\\' in member.name or member.name in names:
                raise ValueError('UNSAFE_OR_DUPLICATE_ARCHIVE_MEMBER')
            names.add(member.name);p=unpack.joinpath(*rel.parts);p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(tar.extractfile(member).read())
            inventory.append({'path':member.name,'bytes':p.stat().st_size,'sha256':digest(p)})
    contents=json.loads((unpack/'bundle_contents.json').read_text(encoding='utf-8'))['files']
    if {e['path'] for e in contents}!={e['path'] for e in inventory if e['path']!='bundle_contents.json'}:raise ValueError('EXACT_ARCHIVE_MANIFEST_REQUIRED')
    for e in contents:
        if digest(unpack/e['path'])!=e['sha256'] or (unpack/e['path']).stat().st_size!=e['bytes']:raise ValueError('UNPACKED_HASH_MISMATCH')
    commands=[]
    def run(args):
        p=subprocess.run(args,capture_output=True,text=True,encoding='utf-8',timeout=60)
        commands.append({'argv':args,'stdout':p.stdout,'stderr':p.stderr,'exitStatus':p.returncode})
        if p.returncode:raise ValueError('OFFLINE_ENTRY_CHECK_FAILED')
        return p.stdout
    script="import sys,json;from pathlib import Path;sys.path.insert(0,sys.argv[1]);from next.runtime.joint import verify_joint;p=verify_joint(Path(sys.argv[2]));print(json.dumps({'version':p['version'],'cases':[c['id'] for c in p['cases']],'counts':[p['initializationsTarget'],p['forwardTarget'],p['inverseExecutionsTarget']]}))"
    actual=json.loads(run([sys.executable,'-X','utf8','-B','-c',script,str(unpack/'project'),str(unpack)]))
    if actual['counts']!=[1,5,0] or actual['cases']!=['C-repeat','direction-225','direction-315','width-45','width-70']:raise ValueError('UNPACKED_BATCH_UNSUPPORTED')
    help_text=run([sys.executable,'-X','utf8','-B',str(unpack/'project/next/runtime/joint_worker.py'),'--help'])
    if 'five-case calibration' not in help_text:raise ValueError('WRONG_WORKER_ENTRY')
    # Exercise the unpacked actual launch function, but intercept the OS launch.
    sys.path.insert(0,str(unpack/'scripts'))
    spec=importlib.util.spec_from_file_location('unpacked_launch',unpack/'project/next/runtime/joint_launch.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory() as t:
        base=Path(t);prep=base/'packet';prep.mkdir()
        class FixturePath(type(Path())):
            def is_relative_to(self,other,*args):
                return True if str(other)=='/home/jovyan' else super().is_relative_to(other,*args)
        q={'prep':str(prep),'deadline_utc':'2099-01-01T00:00:00Z','guard_launch_receipt':{'offline':False,
            'single_run':True,'budget_usd_including_tax':3,'approval_reference':'OFFLINE_SYNTHETIC_NOT_AUTHORIZATION','deadline_utc':'2099-01-01T00:00:00Z'}}
        with patch.object(module,'Path',FixturePath),patch.object(module.subprocess,'Popen',return_value=types.SimpleNamespace(pid=12345)) as launch:
            module.main(q)
            dispatched=launch.call_args.args[0]
        if '--joint' not in dispatched or not dispatched[3].endswith('joint_worker.py'):raise ValueError('WRONG_DISPATCH_WORKER')
    for src,needle in [('project/next/runtime/joint_worker.py','joint_entry.py'),('project/next/runtime/joint_entry.py','entry.run_forward = session')]:
        if needle not in (unpack/src).read_text(encoding='utf-8'):raise ValueError('WRONG_FORWARD_ENTRY')
    record={'status':'OFFLINE_PACKAGE_AUDIT_PASSED','archive':str(archive),'archiveSha256':digest(archive),
        'archiveBytes':archive.stat().st_size,'archiveFiles':inventory,'actualUnpackedPlan':actual,
        'workerSha256':digest(unpack/'project/next/runtime/joint_worker.py'),
        'workerMatchesWorkspace':digest(unpack/'project/next/runtime/joint_worker.py')==digest(Path(__file__).resolve().parents[1]/'project/next/runtime/joint_worker.py'),
        'realEntryChain':['scripts/run_joint_batch.py','joint_launch.py','joint_worker.py --joint','joint_entry.py','joint.session'],
        'dispatchFixture':'OFFLINE_SYNTHETIC; Popen intercepted; NO VM/GPU/provider launch','interceptedArgv':dispatched,
        'commands':commands,'realGPUVerified':False}
    (output/'audit.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    print(record['status'],record['archiveSha256'],'files',len(inventory),'worker',record['workerSha256'])

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--package',type=Path,required=True);p.add_argument('--out',type=Path,required=True);o=p.parse_args();audit(o.package,o.out.resolve())
