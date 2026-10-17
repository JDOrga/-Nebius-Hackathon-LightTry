// Pure versioned plan/identity transitions. No image effects or GPU calls.
export function canonical(value) {
  if (Array.isArray(value)) return '['+value.map(canonical).join(',')+']';
  if (value && typeof value==='object') return '{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+canonical(value[k])).join(',')+'}';
  if(typeof value==='number'&&!Number.isFinite(value)) throw Error('参数不是有限数字');
  return JSON.stringify(value);
}
export const uid=()=>crypto.randomUUID().replaceAll('-','');
export const digest=async value=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(canonical(value))))).map(b=>b.toString(16).padStart(2,'0')).join('');
export function allowed(parameters,policy) {
  const {offsetDeg:o,strength:s,environmentId:e}=parameters;
  if(policy.parameterized||parameters.schemaVersion===2)return Number.isFinite(o)&&Number.isFinite(s)&&o>=0&&o<360&&s>=.25&&s<=4;
  return typeof o==='number'&&Number.isFinite(o)&&typeof s==='number'&&Number.isFinite(s)&&
    ((o===0&&s===1)||(policy.approvedVariants?.[e]||[]).some(p=>p[0]===o&&p[1]===s));
}
export function createScheme(environmentId,name='新方案',inputId=null) {
  return {schemaVersion:1,planId:uid(),version:1,name,parameters:{environmentId,offsetDeg:0,strength:1},inputId,parentVersion:null};
}
export function revise(scheme,parameters,name=scheme.name,existing=[]) {
  const latest=Math.max(scheme.version,...existing.filter(s=>s.planId===scheme.planId).map(s=>s.version));
  return {...structuredClone(scheme),version:latest+1,parentVersion:scheme.version,
    parameters:{...parameters},name:name.trim()||scheme.name};
}
export function variant(scheme,name) {
  return {...structuredClone(scheme),planId:uid(),version:1,parentVersion:null,name:(name.trim()||scheme.name+' 副本').slice(0,60)};
}
export function removeFamily(library,planId,current,inputId,environmentId) {
  const remaining=library.filter(s=>s.planId!==planId);
  if(remaining.length===library.length)return {library,current};
  if(current.planId!==planId)return {library:remaining,current};
  const next=remaining.filter(s=>s.inputId===inputId).sort((a,b)=>b.version-a.version)[0];
  if(next)return {library:remaining,current:next};
  const replacement=createScheme(environmentId,'新方案',inputId);
  return {library:remaining.concat(replacement),current:replacement};
}
export function sameParameters(a,b) {return canonical(a)===canonical(b);}
export function matchingTask(task,inputId,parameters,now=Date.now()) {
  if(task.input?.id!==inputId || task.status!=='succeeded' || task.executionUncertain ||
    task.expiresAt*1000<=now) return null;
  const p=task.preset;
  if(parameters.schemaVersion===2){const r=task.result;return p.recipeKey&&r?.recipeKey===p.recipeKey&&sameParameters(p.scheme?.parameters,parameters)&&sameParameters(r.parameters,parameters)&&r.taskId===task.taskId&&r.inputId===inputId?r:null;}
  const actual=p.parameters?{environmentId:p.environmentId,offsetDeg:p.parameters.offsetDeg,strength:p.parameters.strength}:
    {environmentId:p.id,offsetDeg:0,strength:1};
  const r=task.result;
  if(p.parameters && (!p.recipeKey || r?.recipeKey!==p.recipeKey || !sameParameters(r?.parameters,p.parameters))) return null;
  return sameParameters(actual,parameters)&&r?.taskId===task.taskId&&r.inputId===inputId&&r.presetId===p.id?r:null;
}
export function validateLibrary(value,environments) {
  if(!Array.isArray(value)||value.length>200) return [];
  return value.filter(s=>s&&s.schemaVersion===1&&/^[0-9a-f]{32}$/.test(s.planId)&&
    Number.isInteger(s.version)&&s.version>0&&s.version<=1000&&typeof s.name==='string'&&s.name.length<=60&&
    (environments.includes(s.parameters?.environmentId)||s.parameters?.schemaVersion===2&&(s.parameters.mode==='procedural'||/^hdr-[a-f0-9]{64}$/.test(s.parameters.environmentId)))&&typeof s.parameters.offsetDeg==='number'&&
    Number.isFinite(s.parameters.offsetDeg)&&typeof s.parameters.strength==='number'&&Number.isFinite(s.parameters.strength)&&
    (s.inputId===null||/^[0-9a-f]{32}$/.test(s.inputId)));
}
export const referenceKey=(s,inputId)=>canonical({planId:s.planId,version:s.version,parameters:s.parameters,inputId});
export function mergeAcceptedLibrary(existing, incoming) {
 const out=[...existing];
 for(const s of incoming){
  const old=out.find(x=>x.planId===s.planId&&x.version===s.version);
  if(old){if(old.inputId!==s.inputId||!sameParameters(old.parameters,s.parameters)||old.importedResultSha256!==s.importedResultSha256)throw Error('实测导入身份冲突；已有方案未覆盖');continue;}
  if(out.length>=200)throw Error('方案库已满；未覆盖已有方案，请先整理');
  out.push(structuredClone(s));
 }
 return out;
}
export function restoreInputStub(s){
  if(!s||!/^[0-9a-f]{32}$/.test(s.id)||!/^[0-9a-f]{64}$/.test(s.originalSha)||
    !Number.isInteger(s.width)||!Number.isInteger(s.height)||Math.min(s.width,s.height)<32||
    Math.max(s.width,s.height)>16384||s.width*s.height>40000000)return null;
  return {id:s.id,name:typeof s.name==='string'?s.name.slice(0,100):'我的照片',width:s.width,height:s.height,originalSha:s.originalSha,needsFile:true};
}

// Presentation only. No splitting user names, no changes to persisted identities.
export function photoTitle(sample,input){
 const names={'01_matte_terracotta':'陶罐','02_text_tea_tin':'茶盒','03_glossy_metal_teapot':'金属壶','04_transparent_glass':'玻璃杯','05_white_blue_mug':'白蓝杯'};
 return names[sample?.id]||sample?.name||input?.name||'我的照片';
}
export function schemePresentation(s){
 if(s.provenance?.cohort==='current-calibration-20261013'&&s.name===s.provenance.caseId+' · 本轮五项校准实测')return {title:s.provenance.caseId+' · 本轮校准',fullName:s.name,summary:false};
 if(s.provenance?.caseId&&s.name===s.provenance.caseId+' · 2026-10-12实测')return {title:s.provenance.caseId+' · 10-12实测',fullName:s.name,summary:false};
 if(s.name.length<=16)return {title:s.name,fullName:s.name,summary:false};
 const p=s.parameters;return {title:p.offsetDeg===45?'方向探索方案':p.strength===.7?'偏暗备选':({'sunny':'默认方案','sunrise':'晨光方案','street':'夜景方案'}[p.environmentId]||'光照方案'),fullName:s.name,summary:true};
}
export function environmentEdit(s,id,environments,policy,existing){
 if(!environments.includes(id)||s.parameters.environmentId===id)return null;
 const parameters={environmentId:id,offsetDeg:0,strength:1};
 if(!allowed(parameters,policy)||sameParameters(s.parameters,parameters))return null;
 return revise(s,parameters,s.name,existing);
}
export function comparisonCursor(keys,requested){return keys.includes(requested)?requested:keys[0]||null;}

export function schemeCaption(s,all){
 const d=schemePresentation(s);if(!d.summary)return d.title;
 const families=[...new Set(all.filter(x=>x.inputId===s.inputId).map(x=>x.planId))];
 const latest=families.map(id=>all.filter(x=>x.planId===id).reduce((a,b)=>a.version>b.version?a:b));
 return latest.filter(x=>schemePresentation(x).title===d.title).length>1?d.title+' · '+(families.indexOf(s.planId)+1):d.title;
}

export const schemeWire=s=>Object.fromEntries(["schemaVersion","planId","version","name","parameters","inputId","parentVersion"].map(k=>[k,s[k]]));

// Restore only an exact saved version bound to an available sample; never guess a plan.
export function savedSampleSelection(cursor,schemes,samples){
 if(!cursor||typeof cursor.key!=='string'||typeof cursor.inputId!=='string')return null;
 const scheme=schemes.find(s=>s.planId+':'+s.version===cursor.key&&s.inputId===cursor.inputId);
 if(!scheme)return null;
 const sample=samples.find(s=>s.id===cursor.sampleId&&s.input?.sha256?.slice(0,32)===scheme.inputId);
 return sample?{scheme,sample}:null;
}
