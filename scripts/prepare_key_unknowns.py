"""Prepare five targeted GPU cases OFFLINE; no restart, upload, dependency install."""
import argparse,copy,hashlib,pathlib,shutil,sys,uuid
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'project'));sys.path.insert(0,str(ROOT/'scripts'))
from prepare_joint import prepare,freeze
from inference.jobs import read,atomic
from runtime.key_unknowns import recipes,VERSION
from runtime.joint import energy,changes
from light_console import synthesize,encode_hdr,decode_hdr
from lighting import identity

def main(output):
 output.mkdir();seed=output/'seed-local-only';prepare(seed)
 packet=output/'packet';shutil.copytree(seed/'packet',packet,ignore=shutil.ignore_patterns('recipes','bundle_contents.json'))
 envs={e['id']:e for e in read(packet/'project/runtime/environments.json')};actual=recipes(envs)
 reference=ROOT/'.local/lighttry-joint-20261012/ai-confirmed-package';old=read(reference/'packet/joint.json');base=next(c for c in old['cases'] if c['id']=='C')
 cases=[]
 ambient_recipe=copy.deepcopy(base['parameters'])
 for z in ambient_recipe['zones']:z['strength']=0
 ambient_energy=energy(decode_hdr(encode_hdr(synthesize(ambient_recipe))))
 target_energy=energy(decode_hdr(encode_hdr(synthesize(base['parameters']))))
 for name,p in actual.items():
  data=encode_hdr(synthesize(p));f=packet/'recipes'/ (name+'.hdr');f.parent.mkdir(exist_ok=True);f.write_bytes(data)
  cases.append({'id':name,'parameters':p,'recipeKey':identity(p),'comparison':'vs retained C: '+str(changes(base['parameters'],p)), 'source':'targeted manual calibration; not AI; pending actual GPU','hdrFile':f.relative_to(packet).as_posix(),'hdrSha256':hashlib.sha256(data).hexdigest(),'encodedDecodedEnergy':energy(decode_hdr(data)),
   'actualDiffVsC':changes(base['parameters'],p),
   'isolatedAmbientReferenceEnergy':ambient_energy,
   'ambientNote':'Same literal ambient0.03; isolated RGBE reference is not an additive decomposition of quantized final HDR, and not object illumination.',
   'energyRelativeErrorRGB':[a/b-1 for a,b in zip(energy(decode_hdr(data))['sphericalIntegralRGB'],target_energy['sphericalIntegralRGB'])],
   'peakRatioVsC':[a/b for a,b in zip(energy(decode_hdr(data))['peakRGB'],target_energy['peakRGB'])],
   'productionConditionStatistics':'pending actual GPU; decoded emission is NOT projected/model/output energy'})
  if name.startswith('width'):cases[-1]['encodedDecodedEnergy']['sizeSemantics']='FWHM and peak amplitude change together; actual RGBE decoded emitted integral compensated to C within0.5%; not output brightness normalization'
 plan=read(seed/'packet/joint.json');plan.update(version=VERSION,taskId=uuid.uuid4().hex,nonce=uuid.uuid4().hex,cases=cases,forwardTarget=5,AIStatus='no text requests; retained C baseline')
 plan['reusedReferences']=[{'caseId':c['id'],'recipeKey':c['recipeKey'],'outputSha256':read(reference/'execution'/ (c['id']+'-retrieval.json'))['sha256']} for c in old['cases'] if c['id'] in ('B','C')]
 plan['acceptance']={'phaseOrder':['C-repeat','direction-225','direction-315','width-45','width-70'],'emittedSphericalEnergyRelativeTolerance':.005,'direction':'Record image-plane highlight/shadow positions, no preassigned left/right; no calibration claim from four samples without consistent trend','width':'Hold decoded emitted spherical RGB integral; size and compensating amplitude change together; peak changes. Record projected/after-clipping energies and visual penumbra, no physical softness guarantee','fixed':'same photo, five inverse buffers, renderer, seed1000 steps15 guidance0 1280x704; no full A-F or AI rerun','stop':'major identity/hash/hook ambiguity -> stop; same fixed guard, no extra startup'}
 from runtime.calibration import bind_references, prepare_review
 plan['historicalReferences']=bind_references(reference)
 plan['cohort']='2026-10-13 calibration; not yet executed'
 plan['acceptance'].update(direction='8% ROI width centroid shift is auxiliary ONLY; inspect subject light/dark, occlusion, highlights and cast shadows. This photo/pipeline coarse orientation only; unresolved historical drift pauses historical direction inference.', width='Compare CURRENT C-repeat/width-45/width-70 separately even if historical C is incomparable. Equal emitted integral does not equal projected object energy or output brightness. No output normalization; inconclusive response allowed; never physical-softness pass.', baseline='Record file hashes, decoded pixel delta and manual visual delta; same seed is not a byte-equality guarantee. Inspect inputs/conditions/RNG on drift; no extra forwards.')
 atomic(packet/'joint.json',plan)
 prepare_review(packet,output)
 experiment=read(packet/'experiment.json')
 experiment['files']=[{'path':f.relative_to(packet).as_posix(),'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'bytes':f.stat().st_size} for f in sorted(packet.rglob('*')) if f.is_file() and f.name not in ('experiment.json','bundle_contents.json')]
 atomic(packet/'experiment.json',experiment);freeze(packet,output);atomic(output/'preparation.json',plan)
 atomic(output/'execution-disabled.json',{'enabled':False,'model_license_ack':False,'guard_run_directory':'HOST_CURRENT_CONFIRMED_RUN','jointTaskId':plan['taskId'],'jointPackageSha256':read(output/'bundle.json')['sha256']})
 from runtime.calibration import comparison_page
 comparison_page(packet,output/'comparison.html',None)
 print('PREPARED_CALIBRATION_FIVE_ONLY forward=5 inverse=0; retained B/C reuse=2; initialization target=1; no GPU/API/SSH')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',type=pathlib.Path,required=True);main(p.parse_args().out.resolve())
