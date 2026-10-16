import {canonical,validateLibrary,restoreInputStub,schemeWire} from './scheme-state.js';

// Parameters and references only: never serialize File/blob URLs, chat or credentials.
export function archive(schemes,inputs=[],taskIds=[]) {
 return {schemaVersion:1,schemes:schemes.map(s=>({...schemeWire(s),
  ...(s.recipeKey?{recipeKey:s.recipeKey}:{}),
  ...(s.importedResultSha256?{importedResultSha256:s.importedResultSha256}:{}),
  ...(s.provenance?{provenance:Object.fromEntries(['taskId','caseId','cohort'].filter(k=>k in s.provenance).map(k=>[k,s.provenance[k]]))}:{})})),
  photos:inputs.map(restoreInputStub).filter(Boolean),
  taskIds:taskIds.filter(id=>/^[a-f0-9]{32}$/.test(id))};
}
export function readArchive(value,environments) {
 if(Array.isArray(value))value={schemaVersion:1,schemes:value};
 if(!value||value.schemaVersion!==1||!Array.isArray(value.schemes))throw Error('需要 v1 方案库 JSON。');
 const schemes=validateLibrary(value.schemes,environments);
 if(schemes.length!==value.schemes.length||schemes.some(s=>
  !s.name.trim()||/[\x00-\x1f\x7f]/.test(s.name)||
  !(s.parentVersion===null||Number.isInteger(s.parentVersion)&&s.parentVersion>0&&s.parentVersion<s.version)))throw Error('方案库含无效版本；未部分导入。');
 const cleaned=archive(schemes,value.photos||[],value.taskIds||[]);
 // Same identity cannot quietly replace different content, even within one import.
 cleaned.schemes=mergeLibraries([],cleaned.schemes);
 return cleaned;
}
export function mergeLibraries(existing,incoming) {
 const merged=new Map();
 for(const s of [...existing,...incoming]) {
  const key=s.planId+':'+s.version,old=merged.get(key);
  const clean=archive([s]).schemes[0];
  if(old&&canonical(archive([old]).schemes[0])!==canonical(clean))throw Error('同一方案版本内容冲突，请先创建新版本或分开导出。');
  merged.set(key,clean);
 }
 if(merged.size>200)throw Error('方案库最多200个版本。');
 return [...merged.values()];
}

// Local-only: never sends a request or changes service-side data.
export function resetClientStorage(local,session,namespace='') {
 const keys=['schemeLibrary','schemeCursor','schemeTasks','schemeSubmission','schemeOrigins','deletedFamilies','photoStubs','workspaceSplit'].map(k=>'lighttry.'+k+'.v1');
 for(const key of keys)local.removeItem(namespace+key);
 // Layout is initialized before account discovery in the existing workbench.
 local.removeItem('lighttry.workspaceSplit.v1');
 session.removeItem('lighttry.chat.tab.v1');
}
