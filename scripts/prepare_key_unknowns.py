"""Prepare four targeted GPU cases OFFLINE; no restart, upload, dependency install."""
import argparse,copy,hashlib,pathlib,shutil,sys,uuid
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'project'));sys.path.insert(0,str(ROOT/'scripts'))
from prepare_joint import prepare,freeze
from inference.jobs import read,atomic
from next.runtime.key_unknowns import recipes,VERSION
from next.runtime.joint import energy,changes
from light_console import synthesize,encode_hdr,decode_hdr
from lighting import identity

def main(output):
 output.mkdir();seed=output/'seed-local-only';prepare(seed)
 packet=output/'packet';shutil.copytree(seed/'packet',packet,ignore=shutil.ignore_patterns('recipes','bundle_contents.json'))
 envs={e['id']:e for e in read(packet/'project/next/runtime/environments.json')};actual=recipes(envs)
 reference=ROOT/'.local/lighttry-joint-20261012/ai-confirmed-package';old=read(reference/'packet/joint.json');base=next(c for c in old['cases'] if c['id']=='C')
 cases=[]
 for name,p in actual.items():
  data=encode_hdr(synthesize(p));f=packet/'recipes'/ (name+'.hdr');f.parent.mkdir(exist_ok=True);f.write_bytes(data)
  cases.append({'id':name,'parameters':p,'recipeKey':identity(p),'comparison':'vs retained C: '+str(changes(base['parameters'],p)), 'source':'targeted manual calibration; not AI; pending actual GPU','hdrFile':f.relative_to(packet).as_posix(),'hdrSha256':hashlib.sha256(data).hexdigest(),'encodedDecodedEnergy':energy(decode_hdr(data))})
 plan=read(seed/'packet/joint.json');plan.update(version=VERSION,taskId=uuid.uuid4().hex,nonce=uuid.uuid4().hex,cases=cases,forwardTarget=4,AIStatus='no text requests; retained C baseline')
 plan['reusedReferences']=[{'caseId':c['id'],'recipeKey':c['recipeKey'],'outputSha256':read(reference/'execution'/ (c['id']+'-retrieval.json'))['sha256']} for c in old['cases'] if c['id'] in ('B','C')]
 plan['acceptance']={'phaseOrder':['direction-225','direction-315','width-45','width-70'],'emittedSphericalEnergyRelativeTolerance':.005,'direction':'Record image-plane highlight/shadow positions, no preassigned left/right; no calibration claim from four samples without consistent trend','width':'Hold decoded emitted spherical RGB integral; size and compensating amplitude change together; peak changes. Record projected/after-clipping energies and visual penumbra, no physical softness guarantee','fixed':'same photo, five inverse buffers, renderer, seed1000 steps15 guidance0 1280x704; no full A-F or AI rerun','stop':'major identity/hash/hook ambiguity -> stop; same fixed guard, no extra startup'}
 atomic(packet/'joint.json',plan)
 experiment=read(packet/'experiment.json')
 experiment['files']=[{'path':f.relative_to(packet).as_posix(),'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'bytes':f.stat().st_size} for f in sorted(packet.rglob('*')) if f.is_file() and f.name not in ('experiment.json','bundle_contents.json')]
 atomic(packet/'experiment.json',experiment);freeze(packet,output);atomic(output/'preparation.json',plan)
 atomic(output/'execution-disabled.json',{'enabled':False,'model_license_ack':False,'guard_run_directory':'HOST_CURRENT_CONFIRMED_RUN','jointTaskId':plan['taskId'],'jointPackageSha256':read(output/'bundle.json')['sha256']})
 print('PREPARED_KEY_UNKNOWNS_ONLY forward=4 inverse=0; retained B/C reuse=2; initialization target=1; no GPU/API/SSH')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',type=pathlib.Path,required=True);main(p.parse_args().out.resolve())
