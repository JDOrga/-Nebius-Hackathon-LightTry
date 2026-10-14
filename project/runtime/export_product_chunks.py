"""Five small immutable product archives; same pinned transport, no VM lifecycle.

Transport part names are compatibility labels, NOT lighting experiment cases.
No tensors/duplicate flat JPEGs/PNG diagnostics are exported. Original exporter
and transport verification remain unchanged.
"""
import base64,gzip,hashlib,io,json
from pathlib import Path
import sys,tarfile
PARTS=('metadata','case0','case1','case2','case3')
MAX_BYTES=163840

def archive_bytes(root,part,data_root):
 root=Path(root).resolve();base=Path(data_root).resolve()
 if not base.is_relative_to('/home/jovyan') or not root.is_relative_to(base):raise ValueError('RESULT_ROOT_OUTSIDE_DATA_ROOT')
 return payload(root,part)

def payload(root,part):
 root=Path(root).resolve()
 if part not in PARTS:raise ValueError('PRODUCT_PART_INVALID')
 all_files=[p for p in root.rglob('*') if p.is_file()]
 if any(p.is_symlink() or not p.resolve().is_relative_to(root) for p in all_files):raise ValueError('RESULT_SYMLINK_FORBIDDEN')
 gbuf=sorted(p for p in all_files if p.relative_to(root).parts[:2]==('inverse','gbuffer_frames') and p.suffix=='.jpg')
 if len(gbuf)!=5:raise ValueError('EXACT_FIVE_GBUFFERS_REQUIRED')
 canonical=[p for p in all_files if p.relative_to(root).parts[0]=='presets' and 'relit_frames_' in p.as_posix() and p.suffix=='.jpg']
 if len(canonical)!=1 or not (root/'result.jpg').is_file():raise ValueError('ONE_CANONICAL_PRODUCT_RESULT_REQUIRED')
 if (root/'result.jpg').read_bytes()!=canonical[0].read_bytes():raise ValueError('CURRENT_RESULT_CANONICAL_MISMATCH')
 groups={'metadata':[p for p in all_files if p.suffix in ('.json','.jsonl','.log')],
         'case0':gbuf[:2],'case1':gbuf[2:4],'case2':gbuf[4:],'case3':[root/'result.jpg',canonical[0]]}
 selected=groups[part]
 if sum(p.stat().st_size for p in selected)>20*1024**2:raise ValueError('PRODUCT_PART_SOURCE_TOO_LARGE')
 stream=io.BytesIO()
 with gzip.GzipFile(fileobj=stream,mode='wb',compresslevel=9,mtime=0) as gz,tarfile.open(fileobj=gz,mode='w|') as tar:
  for p in sorted(selected):
   data=p.read_bytes();info=tarfile.TarInfo(p.relative_to(root).as_posix());info.size=len(data);tar.addfile(info,io.BytesIO(data))
 data=stream.getvalue()
 if len(data)>MAX_BYTES:raise ValueError('PRODUCT_CHUNK_EXCEEDS_160K')
 return data

def combine(paths,target):
 """Called locally only after exact remote bytes/hash receipts have passed."""
 files={};total=0
 for archive in paths:
  with tarfile.open(archive,'r:gz') as tar:
   for member in tar:
    from pathlib import PurePosixPath
    p=PurePosixPath(member.name);total+=member.size
    if not member.isfile() or p.is_absolute() or '..' in p.parts or ':' in member.name or '\\' in member.name or total>512*1024**2:raise ValueError('UNSAFE_PRODUCT_CHUNK')
    if member.name in files:raise ValueError('DUPLICATE_PRODUCT_MEMBER')
    files[member.name]=tar.extractfile(member).read()
 if not {'result.jpg','receipt.json','execution.json','parameter-proof.json'}<=set(files):raise ValueError('PRODUCT_RESULT_PROOF_MISSING')
 with Path(target).open('xb') as stream,gzip.GzipFile(fileobj=stream,mode='wb',compresslevel=9,mtime=0) as gz,tarfile.open(fileobj=gz,mode='w|') as tar:
  for name,data in sorted(files.items()):
   info=tarfile.TarInfo(name);info.size=len(data);tar.addfile(info,io.BytesIO(data))
 return {'bytes':Path(target).stat().st_size,'sha256':hashlib.sha256(Path(target).read_bytes()).hexdigest(),'members':len(files),'parts':len(paths)}

if __name__=='__main__':
 q=json.loads(base64.b64decode(sys.argv[1]));sys.stdout.buffer.write(archive_bytes(q['root'],q['part'],q['data_root']))
