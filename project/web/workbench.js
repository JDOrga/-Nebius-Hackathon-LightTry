import {resetClientStorage} from './workspace-portability.js';
import {archive,readArchive,mergeLibraries} from './workspace-portability.js';
import {createConsole} from './console.js';
import {createChat} from './chat.js';
import {allowed,removeFamily,createScheme,revise as reviseBase,variant,sameParameters,matchingTask,validateLibrary,referenceKey,uid,restoreInputStub,photoTitle,schemePresentation,environmentEdit,comparisonCursor,schemeCaption,mergeAcceptedLibrary,schemeWire} from './scheme-state.js';
const $=id=>document.getElementById(id), esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let catalog,lighting,inference,schemes=[],current,input,file=null,tasks=[],mode='result',compareKey=null,pending=false,requestId=null,region=false,zoom=1,pan={x:0,y:0};
const libraryKey='lighttry.schemeLibrary.v1',cursorKey='lighttry.schemeCursor.v1',tasksKey='lighttry.schemeTasks.v1',submissionKey='lighttry.schemeSubmission.v1',originsKey='lighttry.schemeOrigins.v1';
let accountNamespace='';
let schemeOrigins={},draftDirty=false,serverWorkspace=null,serverPhotos=[],pendingPhotoAssociation=null;
let deletedFamilies=[];
const deletedKey='lighttry.deletedFamilies.v1';
const visibleFamilies=values=>values.filter(s=>!deletedFamilies.some(d=>d.planId===s.planId));
const photoStubsKey="lighttry.photoStubs.v1";
async function chooseUploadDraft(){
 if(!catalog||!inference)return;
 if(input?.unbound){workspaceView('preview');return;}
 if(current&&input)persist();
 pendingPhotoAssociation=null;file=null;$('file').value='';requestId=null;
 input={id:uid(),name:'待上传照片',width:1280,height:704,unbound:true};
 current=createScheme(catalog.presets[0].id,'未命名草稿',input.id);
 mode='result';compareKey=null;region=false;zoom=1;pan={x:0,y:0};
 invalidateAI();error(null);await render();workspaceView('preview');
}
$('load-photo').onclick=chooseUploadDraft;
const revise=(s,p,n=s.name)=>reviseBase(s,p,n,schemes);
const key=s=>s.planId+':'+s.version;
const storageGet=k=>{try{return JSON.parse(localStorage.getItem(accountNamespace+k)||'null')}catch{return null}};
function persist(){try{if(input&&!input.sampleId&&/^[a-f0-9]{64}$/.test(input.originalSha||'')){const stubs=storageGet(photoStubsKey)||[];localStorage.setItem(accountNamespace+photoStubsKey,JSON.stringify(stubs.filter(p=>p.id!==input.id).concat({id:input.id,name:input.name,width:input.width,height:input.height,originalSha:input.originalSha}).slice(-200)));}localStorage.setItem(accountNamespace+libraryKey,JSON.stringify(schemes));localStorage.setItem(accountNamespace+cursorKey,JSON.stringify({key:key(current),sampleId:input?.sampleId,inputId:input?.id,inputStub:input&&!input.sampleId?{id:input.id,name:input.name,width:input.width,height:input.height,originalSha:input.originalSha}:null}));localStorage.setItem(accountNamespace+tasksKey,JSON.stringify(tasks.map(t=>t.taskId)));localStorage.setItem(accountNamespace+originsKey,JSON.stringify(schemeOrigins));$('storage-note').textContent='方案已自动保存到本机浏览器。'}catch{$('storage-note').textContent='本地存储不可用；本页仍可操作，刷新可能丢失未保存状态。'}}
function error(message){$('error').hidden=!message;$('error').textContent=message||''}
function rememberSubmission(value){if(value)localStorage.setItem(accountNamespace+submissionKey,JSON.stringify(value));else localStorage.removeItem(accountNamespace+submissionKey);}
async function api(path,options={}){const r=await fetch(path,{cache:'no-store',...options});let body;try{body=await r.json();}catch{const e=Error('服务返回无效数据（HTTP '+r.status+'）');e.status=r.status;throw e;}if(!r.ok){const e=Error(body.error?.message||'服务请求失败');e.status=r.status;throw e;}return body;}
function effectLabel(p){if(p.schemaVersion===2)return (p.mode==='procedural'?'实验性程序化布光':catalog.presets.find(e=>e.id===p.environmentId)?.name||'导入环境')+' / '+p.offsetDeg+'° / HDR ×'+Number(p.strength.toFixed(3));return (catalog.presets.find(e=>e.id===p.environmentId)?.name||p.environmentId)+' / '+(p.offsetDeg===45?'实验性方向探索 +45°':p.strength===.7?'近似偏暗（HDR 0.7）':'默认光照');}
function selectedSample(){return catalog.samples.find(s=>s.id===input?.sampleId)}
function displayInput(){const sample=selectedSample();if(region&&sample?.canvas){const b=sample.canvas.validRegion;return {...input,url:'/sample-region/'+sample.id+'/input',width:b[2]-b[0],height:b[3]-b[1]};}if(region&&input.canvas&&/^\/api\/tasks\/[0-9a-f]{32}\/input$/.test(input.url)){const box=input.canvas.validRegion;return {...input,url:input.url+'-region',width:box[2]-box[0],height:box[3]-box[1]};}return input;}
function displayResult(result,scheme=current){if(!result||!region||result.simulation)return result;const sample=selectedSample();if(result.study){const box=result.study.canvas.validRegion;return {...result,url:result.regionUrl,downloadUrl:result.regionDownloadUrl,width:box[2]-box[0],height:box[3]-box[1]};}if(result.task&&input.canvas){const b=input.canvas.validRegion;return {...result,url:result.regionUrl||result.url+'-region',downloadUrl:result.regionDownloadUrl||result.downloadUrl+'-region',width:b[2]-b[0],height:b[3]-b[1]};}if(sample?.canvas){const b=sample.canvas.validRegion;return {...result,url:'/sample-region/'+sample.id+'/'+scheme.parameters.environmentId,downloadUrl:'/sample-region/'+sample.id+'/'+scheme.parameters.environmentId+'?download=1',width:b[2]-b[0],height:b[3]-b[1]};}if(sample?.regionResults?.[scheme.parameters.environmentId])return {...sample.regionResults[scheme.parameters.environmentId],downloadUrl:'/download/'+sample.id+'/'+scheme.parameters.environmentId+'-region',sourceNote:result.sourceNote};return result;}
function resultFor(s){
  if(!input || s.inputId!==input.id) return null;
  // Imported results are pinned artifacts, not interchangeable recipe matches.
  if(Object.prototype.hasOwnProperty.call(s,'importedResultSha256')){
    const sample=selectedSample(), hash=s.importedResultSha256;
    if(!sample||!/^([a-f0-9]{64})$/.test(hash)||!s.recipeKey||!s.provenance?.taskId||!s.provenance?.caseId)return null;
    const exact=lighting.studies.filter(x=>x.sampleId===sample.id&&x.inputSha256===sample.input.sha256&&
      sameParameters(x.parameters,s.parameters)&&x.recipeKey===s.recipeKey&&x.result?.recipeKey===s.recipeKey&&
      x.result?.inputId===s.inputId&&x.result?.sha256===hash&&x.taskId===s.provenance.taskId&&
      x.result?.taskId===s.provenance.taskId&&x.caseId===s.provenance.caseId);
    if(exact.length!==1)return null;
    const study=exact[0];return {...study.result,sourceNote:'历史生成结果 · '+new Date(study.generatedAt*1000).toLocaleString()+' · 非本次生成',study};
  }
  const t=tasks.filter(t=>!input.originalSha||t.originalInput?.sha256===input.originalSha).map(t=>[t,matchingTask(t,input.id,s.parameters)]).find(x=>x[1]);
  if(t)return {...t[1],sourceNote:(t[0].simulation?'离线模拟任务 · 非模型结果 ':'正式任务 ')+t[0].taskId.slice(0,8)+(t[0].transferRecovery?' · 原生成已取回，未重算':'')+' · 源方案版本 '+(t[0].lightingScheme?.version||'旧固定预设'),task:t[0]};
  const sample=selectedSample();if(!sample)return null;
  const study=lighting.studies.find(x=>x.sampleId===sample.id&&x.inputSha256===sample.input.sha256&&sameParameters(x.parameters,s.parameters));
  if(study)return {...study.result,sourceNote:'历史生成结果 · '+new Date(study.generatedAt*1000).toLocaleString()+' · 非本次生成',study};
  if(s.parameters.schemaVersion!==2&&s.parameters.offsetDeg===0&&s.parameters.strength===1){const old=sample.results[s.parameters.environmentId];if(old)return {...old,downloadUrl:'/download/'+sample.id+'/'+s.parameters.environmentId,sourceNote:'历史样例 '+sample.date+''};}
  return null;
}
function transferFailure(t){return t.status==='failed'&&t.stage==='transferring'&&!t.executionUncertain;}
function activeTask(){return tasks.find(t=>t.input?.id===input?.id&&(['queued','running'].includes(t.status)||t.executionUncertain))}
function statusFor(s){if(input?.unbound&&s.inputId===input.id)return '草稿 / 待上传';const r=resultFor(s);if(r)return r.simulation?'模拟完成':'已生成';const t=tasks.filter(t=>t.input?.id===input?.id&&t.lightingScheme?.planId===s.planId&&t.lightingScheme?.version===s.version).sort((a,b)=>b.createdAt-a.createdAt)[0];if(t&&transferFailure(t))return '取回失败 · 可恢复';return t?({queued:'待生成',running:'运行中',failed:'失败',expired:'已过期',partial:'部分完成'}[t.status]||t.status):'草稿 / 待生成';}
function invalidateAI(){} // Chat checks live snapshot; no fake upstream cancellation.
function put(s,force=false){if(!s.name.trim()||/[\x00-\x1f\x7f]/.test(s.name)){error('名称需为1–60字且不含控制字符。');return;}if(!force&&current&&s.parentVersion===current.version&&s.planId===current.planId&&s.name===current.name&&sameParameters(s.parameters,current.parameters))return;if(s.version>1000||s.name.length>60||schemes.length>=200){error('方案版本/名称或本地库已到有限上限；未更改。');return;}error(null);invalidateAI();current=s;if(!schemes.some(x=>key(x)===key(s)))schemes.push(s);requestId=null;persist();render();}
function workspaceView(value){document.body.dataset.workspaceView=value;document.querySelectorAll('[data-workspace-view]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.workspaceView===value)));requestAnimationFrame(applyView);}
function saveDeleted(value){try{localStorage.setItem(accountNamespace+deletedKey,JSON.stringify(value));return true;}catch{error('本机存储不可用；删除状态未更改。');return false;}}
function deleteVariant(planId){
 const versions=schemes.filter(s=>s.planId===planId);if(!versions.length)return;
 const latest=versions.reduce((a,b)=>a.version>b.version?a:b);
 $('delete-summary').textContent='删除“'+latest.name+'”及其全部 '+versions.length+' 个版本？';
 $('delete-dialog').dataset.planId=planId;$('delete-dialog').showModal();
}
$('cancel-delete').onclick=()=>$('delete-dialog').close();
$('confirm-delete').onclick=()=>{const planId=$('delete-dialog').dataset.planId;$('delete-dialog').close();confirmDeleteVariant(planId);};
function confirmDeleteVariant(planId){
 const versions=schemes.filter(s=>s.planId===planId);if(!versions.length)return;
 if(pending||tasks.some(t=>t.lightingScheme?.planId===planId&&(['queued','running'].includes(t.status)||t.executionUncertain))){error('该变体有未结束或状态不确定的任务，暂不能删除。');return;}
 if(deletedFamilies.length>=200){error('可撤销删除记录已满，请先撤销并整理。');return;}
 const latest=versions.reduce((a,b)=>a.version>b.version?a:b);
 const nextDeleted=deletedFamilies.concat({planId,versions:structuredClone(versions)});
 if(!saveDeleted(nextDeleted))return;
 deletedFamilies=nextDeleted;
 const next=removeFamily(schemes,planId,current,input.id,catalog.presets[0].id);schemes=next.library;current=next.current;
 compareKey=null;mode='result';requestId=null;zoom=1;pan={x:0,y:0};invalidateAI();error(null);persist();render();
 $('delete-note').textContent='已删除“'+latest.name+'”的全部版本，可撤销。';
}
$('undo-delete').onclick=()=>{
 const record=deletedFamilies.at(-1);if(!record)return;
 let restored;try{restored=mergeLibraries(schemes,record.versions);}catch(e){error(e.message);return;}
 try{localStorage.setItem(accountNamespace+libraryKey,JSON.stringify(restored));}catch{error('本机存储不可用；未撤销删除。');return;}
 const nextDeleted=deletedFamilies.slice(0,-1);if(!saveDeleted(nextDeleted))return;
 deletedFamilies=nextDeleted;schemes=restored;persist();render();error(null);$('delete-note').textContent='已恢复上次删除的变体及全部版本。';
};
let libraryCloseTimer=null;
function openLibrary(){const drawer=$('library-drawer');clearTimeout(libraryCloseTimer);libraryCloseTimer=null;drawer.classList.remove('is-closing');if(!drawer.open)drawer.showModal();}
function closeLibrary(){const drawer=$('library-drawer');if(!drawer.open||libraryCloseTimer!==null)return;if(matchMedia('(prefers-reduced-motion: reduce)').matches){drawer.close();return;}drawer.classList.add('is-closing');libraryCloseTimer=setTimeout(()=>{libraryCloseTimer=null;drawer.close();drawer.classList.remove('is-closing');},220);}
$('open-library').onclick=openLibrary;
$('close-library').onclick=closeLibrary;
$('library-drawer').addEventListener('cancel',e=>{e.preventDefault();closeLibrary();});
$('library-drawer').addEventListener('click',e=>{if(e.target===$('library-drawer')){const r=e.target.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)closeLibrary();}});
document.querySelector('.skip').onclick=()=>workspaceView('lighting');
document.querySelectorAll('[data-workspace-view]').forEach(b=>b.onclick=()=>workspaceView(b.dataset.workspaceView));
$('expand-preview').onclick=()=>{const preview=document.querySelector('.preview'),expanded=preview.classList.toggle('expanded-preview');$('expand-preview').setAttribute('aria-expanded',String(expanded));$('expand-preview').textContent=expanded?'收起预览':'展开预览';if(!expanded){zoom=1;pan={x:0,y:0};}applyView();};
const lightConsole=createConsole({get:()=>current,apply:p=>put(revise(current,p)),api,token:()=>inference.csrfToken,error,onDraftChange:dirty=>{draftDirty=dirty;$('action-draft-status').hidden=!dirty;$('action-draft-status').textContent=dirty?'有未应用修改 · 左侧显示上一方案结果':'';$('generation-summary').hidden=dirty;if(dirty)$('generate').textContent='先应用参数';$('generate').disabled=dirty||$('generate').dataset.baseDisabled==='true';}});
function parametersOptions(){lightConsole.render();const p=current.parameters;const all=[[0,1],...(lighting.capabilities.approvedVariants[p.environmentId]||[])];const offsets=[...new Set(all.map(x=>x[0]))];const strengths=[...new Set(all.filter(x=>x[0]===p.offsetDeg).map(x=>x[1]))];$('offset').innerHTML=offsets.map(o=>`<option value="${o}">${o===0?'默认加载方位':'方向变体 · 环境偏移 +'+o+'°'}</option>`).join('');$('offset').value=p.offsetDeg;$('strength').innerHTML=strengths.map(v=>`<option value="${v}">${v===1?'默认光照':'近似偏暗 · HDR 0.7'}</option>`).join('');$('strength').value=p.strength;$('offset').disabled=offsets.length<2;$('strength').disabled=strengths.length<2;$('range-note').textContent=p.offsetDeg===45?'实验性方向探索 · 非物理灯位':p.strength===.7?'近似偏暗 · HDR 0.7，非精确 EV':'';}
async function render(){
  if(!current||!input)return;
  if(!input.sampleId){if(!$('photo-select').querySelector('option[value="__upload"]'))$('photo-select').add(new Option(input.unbound?'待上传照片':'我的照片 · 本机草稿','__upload'));$('photo-select').value='__upload';$('photo-select').querySelector('option[value="__upload"]').textContent=input.unbound?'待上传照片':'我的照片 · 本机草稿';}else{$('photo-select').value=input.sampleId;$('photo-select').querySelector('option[value="__upload"]')?.remove();}
  $('original').disabled=!input.originalUrl&&!input.url;
  const env=catalog.presets.find(p=>p.id===current.parameters.environmentId),r=resultFor(current),shown=displayResult(r),din=displayInput(),busy=!!activeTask()||pending;
  $('plan-name').value=current.name;$('environment').value=current.parameters.environmentId;parametersOptions();document.querySelectorAll('[data-environment]').forEach(b=>{b.setAttribute('aria-pressed',String(b.dataset.environment===current.parameters.environmentId));b.disabled=busy;});
  const display=schemePresentation(current);$('view-title').textContent=photoTitle(selectedSample(),input);$('preview-context').textContent='当前方案：'+schemeCaption(current,schemes)+' · v'+current.version;$('rename').textContent=schemeCaption(current,schemes);$('rename').title='编辑完整名称：'+current.name;$('full-name-text').textContent=current.name;$('full-scheme-name').hidden=!display.summary;
  $('view-state').textContent=statusFor(current)+(current.parameters.offsetDeg===45?' · 实验性':'');
  $('identity').textContent='方案编号 '+current.planId.slice(0,8)+' / v'+current.version;
  $('source-note').textContent=r?.sourceNote||'当前方案尚未生成。';
  $('generation-summary').textContent=r?'结果已就绪，无需重新生成':`新方案待生成：${schemeCaption(current,schemes)} · v${current.version}（仅此方案）。`;
  const generationBlocked=busy||tasks.some(t=>t.input?.id===input.id&&t.lightingScheme?.planId===current.planId&&t.lightingScheme?.version===current.version&&transferFailure(t))||!inference.enabled||!file||!!r||!allowed(current.parameters,lighting.capabilities);
  $('generate').dataset.baseDisabled=String(generationBlocked);$('generate').disabled=draftDirty||generationBlocked;
  const failed=tasks.find(t=>t.input?.id===input.id&&t.lightingScheme?.planId===current.planId&&t.lightingScheme?.version===current.version&&t.status==='failed'&&!t.executionUncertain);$('generate').textContent=draftDirty?'先应用参数':r?'结果已就绪':failed?'确认重试此方案':inference.developmentTestMode?'确认模拟生成':'确认生成';
  const transfer=tasks.find(t=>t.input?.id===input.id&&t.lightingScheme?.planId===current.planId&&t.lightingScheme?.version===current.version&&transferFailure(t));$('recover').hidden=!transfer;$('recover').dataset.task=transfer?.taskId||'';if(transfer){$('generation-summary').textContent='执行已结束，结果取回失败；恢复取回，不重新生成。';$('generate').textContent='取回失败，请使用恢复';}
  const t=activeTask();const stages={preflight:'准备生成',weights:'准备模型',inverse:'分析照片',forward:'生成效果',validating:'检查结果',transferring:'下载结果'};
  $('stage').textContent=transfer?'结果下载失败，请使用“恢复取回”，无需重新生成。':pending?'正在提交；尚未确认执行…':t?'正在'+(stages[t.stage]||t.status)+(t.executionUncertain?'；执行状态不确定，禁止重复提交':''):inference.enabled?!file?'恢复后需重新载入同一原始文件才能提交。':'生成可能需要几分钟，请耐心等待。':'暂不支持生成，可继续编辑方案和查看已有结果。';
  if(inference.developmentTestMode)$('stage').textContent=busy?'演示图生成中':'离线模拟 · 仅生成带水印的演示图，不代表实际重布光效果。';
  ['environment','offset','strength','rename','clone','reuse'].forEach(id=>$(id).disabled=busy||(['offset','strength'].includes(id)&&$(id).options.length<2));
  $('download').disabled=!r;$('download').title=r?'下载当前来源的实际字节':'请先生成此方案，再下载结果';$('generate').title=!inference.enabled?'生成服务暂不可用':r?'已有有效结果':!file?'需载入原始照片':'提交当前方案';
  $('download').textContent=r?.simulation?'下载模拟演示图':region?'下载区域 PNG':'下载结果 JPEG';$('region').disabled=!!r?.simulation||(!selectedSample()?.canvas&&!input.canvas);
  $('region').textContent=region?'原照片区域 · 返回完整画布':'完整画布 · 查看原照片区域';
  $('compare-plan').innerHTML=schemes.filter(s=>s.inputId===input.id&&key(s)!==key(current)&&resultFor(s)&&($('show-history').checked||!schemes.some(n=>n.planId===s.planId&&n.version>s.version))).map(s=>`<option value="${key(s)}">${esc(schemeCaption(s,schemes))} · v${s.version} · ${esc(effectLabel(s.parameters))}</option>`).join('');
  compareKey=comparisonCursor([...$('compare-plan').options].map(o=>o.value),compareKey);
  $('compare-plan').value=compareKey||'';if(mode==='plans'&&!compareKey)$('source-note').textContent+=' · 暂无另一份有效结果可比较。';$('compare-plan').hidden=mode!=='plans';
  document.querySelectorAll('[data-mode]').forEach(b=>{b.classList.toggle('selected',b.dataset.mode===mode);b.setAttribute('aria-pressed',String(b.dataset.mode===mode));});
  let panels=[];
  if(mode==='original')panels=[[din,'输入 / 原照片画布']];
  else if(mode==='original-side')panels=[[din,'实际输入'],[shown||din,r?(r?.simulation?'模拟演示图 · 非模型结果':'当前方案实际结果'):transfer?'取回失败 · 仅显示输入':'待生成 · 仅显示输入']];
  else if(mode==='plans'){const other=schemes.find(s=>key(s)===compareKey),or=other&&displayResult(resultFor(other),other);panels=[[shown||din,r?schemeCaption(current,schemes)+' · v'+current.version+' · '+effectLabel(current.parameters):'当前待生成 · 输入'],...(or?[[or,schemeCaption(other,schemes)+' · v'+other.version+' · '+effectLabel(other.parameters)]]:[])];}
  else panels=[[shown||din,r?(r?.simulation?'模拟演示图 · 非模型结果':'当前方案实际结果'):transfer?'取回失败 · 仅显示输入':'待生成 · 仅显示输入']];
  $('preview-panels').innerHTML=`<div class="${panels.length===2?'panels':''}">${panels.map(([img,label])=>`<div class="panel"><span class="label">${esc(label)}</span>${img.url?`<div class="image-viewport"><img src="${esc(img.url)}" alt="${esc(label)}" width="${img.width}" height="${img.height}"></div>`:'<div class="empty">请重新载入原照片，继续编辑此方案。</div>'}</div>`).join('')}</div>`;
  if(input.unbound){$('preview-panels').innerHTML='<div class="upload-draft-panel"><div class="upload-draft-empty"><svg viewBox="0 0 48 48" width="48" height="48" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><rect x="6" y="8" width="36" height="32" rx="7"/><circle cx="17" cy="19" r="3"/><path d="m8 34 11-10 8 7 6-5 7 8"/></svg><h2>从一张照片开始</h2><p>当前为未绑定照片的草稿，载入照片后开始调光。</p><button id="upload-draft-photo">载入照片</button></div></div>';$('upload-draft-photo').onclick=()=>$('file').click();$('source-note').textContent='照片载入后仅保留在本机，确认生成时上传。';$('generation-summary').textContent='草稿待上传 · 请先载入照片';$('generate').textContent='请先载入照片';$('generate').disabled=true;$('stage').textContent='可以先调整布光参数，载入照片后再应用和生成。';}
  $('plan-list').innerHTML=schemes.slice().reverse().filter(s=>$('all-photos').checked||s.inputId===input.id).filter(s=>$('show-history').checked||key(s)===key(current)||!schemes.some(n=>n.planId===s.planId&&n.version>s.version)).map(s=>{const old=schemes.some(n=>n.planId===s.planId&&n.version>s.version),rr=resultFor(s);return `<article class="plan-card ${key(s)===key(current)?'active':''}">${s.inputId===input.id&&(rr?.url||input.url)?`<button class="plan-thumb" data-plan="${key(s)}" aria-label="选择方案：${esc(schemeCaption(s,schemes))}"><img src="${esc(rr?.url||input.url||'')}" alt="${rr?'真实结果':'待生成，仅输入'}"></button>`:''}<div><strong title="${esc(s.name)}">${esc(schemeCaption(s,schemes))}</strong><span class="badge">${s.inputId===input.id?statusFor(s):'另一照片 · 参数可复用'}</span>${schemePresentation(s).summary?`<details class="card-full-name"><summary>完整名称</summary><span>${esc(s.name)}</span></details>`:''}<p>${esc(effectLabel(s.parameters))} · v${s.version}${old?' · 旧版本':''}</p><div class="plan-card-actions"><button class="plan-open" data-plan="${key(s)}">打开方案 <span aria-hidden="true">↗</span></button><div class="plan-secondary-actions"><button data-copy="${key(s)}" ${s.inputId!==input.id?'disabled':''}>复制</button><button data-compare="${key(s)}" ${s.inputId!==input.id||key(s)===key(current)||!rr||!r?'disabled':''}>比较</button>${old?`<button data-restore="${key(s)}">恢复为新版本</button>`:''}<button class="delete-variant" data-delete="${s.planId}" ${pending||tasks.some(t=>t.lightingScheme?.planId===s.planId&&(['queued','running'].includes(t.status)||t.executionUncertain))?'disabled':''}>删除变体</button></div></div></div></article>`}).join('');
  if(!$('plan-list').children.length)$('plan-list').innerHTML='<div class="library-empty"><svg viewBox="0 0 48 48" width="40" height="40" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true"><rect x="7" y="9" width="34" height="32" rx="6"/><path d="M16 9V6h16v3M17 24h14M24 17v14"/></svg><h3>这里还没有方案</h3><p>载入照片并应用布光参数后，方案会自动保存在本机。<br>也可以切换“全部照片”查看已有收藏。</p></div>';
  $('undo-delete').hidden=!deletedFamilies.length;
  document.querySelectorAll('[data-delete]').forEach(b=>b.onclick=()=>deleteVariant(b.dataset.delete));
  document.querySelectorAll('[data-copy]').forEach(b=>b.onclick=()=>{const s=schemes.find(s=>key(s)===b.dataset.copy);if(s.inputId!==input.id)return;put(variant(s,s.name.slice(0,55)+' · 副本'));closeLibrary();workspaceView('lighting');});
  document.querySelectorAll('[data-compare]').forEach(b=>b.onclick=()=>{const s=schemes.find(s=>key(s)===b.dataset.compare);if(s.inputId!==input.id||!resultFor(s)||!resultFor(current))return;compareKey=key(s);mode='plans';zoom=1;pan={x:0,y:0};render();closeLibrary();workspaceView('preview');});
  document.querySelectorAll('[data-restore]').forEach(b=>b.onclick=()=>{const s=schemes.find(s=>key(s)===b.dataset.restore);if(s.inputId===input.id)put(revise(s,s.parameters),true);});
  document.querySelectorAll('[data-plan]').forEach(b=>b.onclick=async()=>{const s=schemes.find(s=>key(s)===b.dataset.plan);if(s.inputId!==input.id){const sample=catalog.samples.find(x=>x.input.sha256.slice(0,32)===s.inputId);if(sample){await chooseSample(sample.id);}else {const savedPhoto=serverPhotos.find(p=>p.id===s.inputId);if(savedPhoto){await chooseStoredPhoto(savedPhoto.id);}const restored=tasks.find(t=>t.input?.id===s.inputId);if(savedPhoto){}else if(restored){input={...restored.input,originalSha:restored.originalInput?.sha256,originalUrl:restored.input.url.replace(/\/input$/,'/original'),needsFile:true};file=null;}else {const stub=restoreInputStub((storageGet(photoStubsKey)||[]).find(p=>p.id===s.inputId));if(!confirm(stub?'请重新选择此方案使用的原照片。':'此旧方案无法自动核对原照片，请确认所选文件正确后继续。'))return;input=stub||{id:s.inputId,name:'待关联原照片',width:1280,height:704,needsFile:true};file=null;current=s;pendingPhotoAssociation={inputId:s.inputId,originalSha:stub?.originalSha||null};persist();render();$('file').click();closeLibrary();return;}}}current=s;zoom=1;pan={x:0,y:0};invalidateAI();persist();render();closeLibrary();workspaceView('preview');});
  $('photo-note').textContent=input.unbound?'请先载入照片':serverPhotos.some(p=>p.id===input.id)?'照片已保存到服务，仅本人登录后可查看':input.sampleId?'历史样例 · '+selectedSample().date:input.canvas?'已保存的任务照片':'照片仅保存在本机，确认生成时上传';
  chat.update();applyView();
}
async function chooseSample(sampleId){pendingPhotoAssociation=null;error(null);const s=catalog.samples.find(s=>s.id===sampleId);file=null;input={...s.input,id:s.input.sha256.slice(0,32),sampleId:s.id,name:s.name,originalUrl:s.original.url};if(inference.developmentTestMode){const response=await fetch(s.original.url);if(!response.ok)throw Error('模拟样例原图读取失败');const blob=await response.blob();const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',await blob.arrayBuffer()))).map(x=>x.toString(16).padStart(2,'0')).join('');if(hash!==s.original.sha256)throw Error('模拟样例原图校验失败');file=new File([blob],s.id+'.'+(blob.type==='image/png'?'png':'jpg'),{type:blob.type});input.originalSha=hash;}$('photo-select').value=s.id;const found=schemes.find(x=>x.inputId===input.id&&!schemes.some(y=>y.planId===x.planId&&y.version>x.version));current=found||createScheme(catalog.presets[0].id,s.name+' · 默认',input.id);if(!found)schemes.push(current);$('editor').scrollTop=0;compareKey=null;zoom=1;pan={x:0,y:0};invalidateAI();persist();render();}
function selectEnvironment(id){const s=environmentEdit(current,id,catalog.presets.map(p=>p.id),lighting.capabilities,schemes);if(s)put(s);}
$('environment').onchange=()=>selectEnvironment($('environment').value);
$('offset').onchange=()=>put(revise(current,{...current.parameters,offsetDeg:Number($('offset').value),strength:1}));
$('strength').onchange=()=>put(revise(current,{...current.parameters,strength:Number($('strength').value)}));
$('rename').onclick=()=>{$('rename-value').value=current.name;$('rename-dialog').showModal();$('rename-value').focus();};
$('rename-dialog').addEventListener('close',()=>{if($('rename-dialog').returnValue==='save')put(revise(current,current.parameters,$('rename-value').value));});
$('show-history').onchange=()=>render();$('all-photos').onchange=()=>render();
$('clone').onclick=()=>put(variant(current,$('plan-name').value.trim()+' · 变体'));
$('reuse').onclick=()=>put({...variant(current,$('plan-name').value),inputId:input.id});
$('photo-select').onchange=()=>{const value=$('photo-select').value;if(value.startsWith('__saved_'))chooseStoredPhoto(value.slice(8)).catch(e=>error(e.message));else if(value!=='__upload')chooseSample(value);};
$('original').onclick=()=>window.open(input.originalUrl||input.url,'_blank','noopener');
$('download').onclick=()=>{const r=displayResult(resultFor(current));if(r)location.href=r.downloadUrl;};
$('region').onclick=()=>{region=!region;zoom=1;pan={x:0,y:0};render();};
function applyView(){const imgs=[...$('preview-panels').querySelectorAll('img')];if(!imgs.length)return;const scale=Math.min(...imgs.map(i=>{const b=i.parentElement.getBoundingClientRect();return Math.min((b.width-1)/(i.naturalWidth||Number(i.width)),(b.height-1)/(i.naturalHeight||Number(i.height)));}));$('zoom-label').textContent=Math.round(zoom*100)+'%';imgs.forEach(i=>{i.style.width=(i.naturalWidth||Number(i.width))*scale+'px';i.style.height=(i.naturalHeight||Number(i.height))*scale+'px';i.style.transform=`translate(-50%,-50%) translate(${pan.x}px,${pan.y}px) scale(${zoom})`;if(!i.complete)i.onload=applyView;});}
new ResizeObserver(applyView).observe($('preview-panels'));
$('preview-panels').onkeydown=e=>{if(zoom<=1)return;const d={ArrowLeft:[-20,0],ArrowRight:[20,0],ArrowUp:[0,-20],ArrowDown:[0,20]}[e.key];if(d){e.preventDefault();pan.x+=d[0];pan.y+=d[1];applyView();}};
$('zoom-in').onclick=()=>{zoom=Math.min(3,zoom+.25);applyView()};$('zoom-out').onclick=()=>{zoom=Math.max(1,zoom-.25);applyView()};$('fit').onclick=()=>{zoom=1;pan={x:0,y:0};applyView()};
let drag=null;$('preview-panels').onpointerdown=e=>{if(zoom>1){drag={x:e.clientX,y:e.clientY,px:pan.x,py:pan.y};$('preview-panels').setPointerCapture(e.pointerId)}};$('preview-panels').onpointermove=e=>{if(drag){pan={x:drag.px+e.clientX-drag.x,y:drag.py+e.clientY-drag.y};applyView()}};$('preview-panels').onpointerup=()=>drag=null;
document.querySelectorAll('[data-mode]').forEach(b=>b.onclick=()=>{mode=b.dataset.mode;zoom=1;pan={x:0,y:0};render();});
$('compare-plan').onchange=()=>{compareKey=$('compare-plan').value;zoom=1;pan={x:0,y:0};render();};
$('file').onchange=async()=>{const f=$('file').files[0];if(!f)return;if(!['image/jpeg','image/png','image/webp'].includes(f.type)||f.size>20*1024*1024){error('请选择不超过20MB的 JPG、PNG、WebP。');return}try{const url=URL.createObjectURL(f),image=new Image();image.src=url;await image.decode();if(Math.min(image.naturalWidth,image.naturalHeight)<32||Math.max(image.naturalWidth,image.naturalHeight)>16384||image.naturalWidth*image.naturalHeight>40000000)throw Error('照片尺寸不在允许范围。');const unfinished=storageGet(submissionKey);if(unfinished){const bytes=await f.arrayBuffer(),sha=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))).map(x=>x.toString(16).padStart(2,'0')).join('');if(sha!==unfinished.originalSha)throw Error('上次提交状态待恢复；请重新载入同一文件，避免重复费用。');file=f;input={id:unfinished.meta.inputId,name:f.name,width:image.naturalWidth,height:image.naturalHeight,url,originalUrl:url};current=unfinished.meta.lightingScheme;requestId=unfinished.meta.requestId;persist();render();error('原请求身份已恢复；再次提交将沿用同一身份，不自动执行。');return;}const sourceBytes=await f.arrayBuffer(),originalSha=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',sourceBytes))).map(x=>x.toString(16).padStart(2,'0')).join('');if(pendingPhotoAssociation){if(pendingPhotoAssociation.originalSha&&originalSha!==pendingPhotoAssociation.originalSha)throw Error('所选文件不是此方案的原照片，请重新选择。');file=f;input={id:pendingPhotoAssociation.inputId,name:f.name,width:image.naturalWidth,height:image.naturalHeight,originalSha,url,originalUrl:url,needsFile:false};pendingPhotoAssociation=null;persist();render();error(null);return;}if(input.needsFile&&originalSha===input.originalSha){file=f;input={...input,needsFile:false,url:input.canvas?input.url:url,originalUrl:url};persist();render();error(null);return;}file=f;mode='result';zoom=1;pan={x:0,y:0};input={id:uid(),originalSha,name:f.name,width:image.naturalWidth,height:image.naturalHeight,url,originalUrl:url};put({...variant(current,f.name+' · '+current.name),inputId:input.id});error(null)}catch(e){error(e.message)}};
async function poll(taskId){for(;;){const t=await api('/api/tasks/'+taskId);tasks=tasks.filter(x=>x.taskId!==taskId).concat(t);if(t.input.id===input?.id&&['queued','running','succeeded'].includes(t.status))input={...input,...t.input};persist();render();if(!['queued','running'].includes(t.status))return;await new Promise(r=>setTimeout(r,2500));}}
async function submitGeneration(){if(pending||activeTask()||!file||resultFor(current))return;pending=true;requestId=requestId||uid();render();try{const submittedFile=file,snapshot=schemeWire(structuredClone(current)),meta={inputId:input.id,requestId,name:input.name,lightingScheme:snapshot,...(schemeOrigins[key(snapshot)]?{languageProposalId:schemeOrigins[key(snapshot)]}: {})};const bytes=await submittedFile.arrayBuffer(),originalSha=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))).map(x=>x.toString(16).padStart(2,'0')).join('');rememberSubmission({meta,originalSha});const encoded=btoa(unescape(encodeURIComponent(JSON.stringify(meta))));const task=await api('/api/tasks',{method:'POST',headers:{'Content-Type':submittedFile.type,'X-LightTry-Token':inference.csrfToken,'X-LightTry-Request':encoded},body:submittedFile});tasks.push(task);rememberSubmission(null);requestId=null;pending=false;persist();await poll(task.taskId)}catch(e){pending=false;error(e.message+'；请求身份保留，不自动重试。');render();}};
$('generate').onclick=()=>{if(inference.developmentTestMode){$('generate-dialog').querySelector('h2').textContent='确认离线模拟';$('generate-dialog').querySelectorAll('p')[1].textContent='仅生成带水印的演示图，不调用真实模型，不收费。';$('confirm-generate').textContent='提交模拟生成';}$('confirm-summary').textContent=$('generation-summary').textContent;$('generate-dialog').dataset.ref=referenceKey(current,input.id);$('generate-dialog').showModal();};
$('cancel-generate').onclick=()=>$('generate-dialog').close();
$('confirm-generate').onclick=()=>{$('generate-dialog').close();if($('generate-dialog').dataset.ref!==referenceKey(current,input.id)){error('编辑参照已改变，请重新确认。');return;}submitGeneration();};
const chat=createChat({
 get:()=>current&&input&&lighting?{scheme:structuredClone(current),reference:referenceKey(current,input.id),confirmedApplication:schemeOrigins[key(current)]?{operationId:schemeOrigins[key(current)],version:current.version}:null,label:photoTitle(selectedSample(),input)+' · '+schemeCaption(current,schemes)+' · v'+current.version,language:lighting.language,busy:!!activeTask()||pending,token:inference.csrfToken,result:{status:statusFor(current),kind:resultFor(current)?.study?'study':resultFor(current)?'generated':'none',artifactId:resultFor(current)?.sha256||null}}:null,
 api, environmentLabel:id=>catalog.presets.find(p=>p.id===id)?.name||id,
 apply:(value,ref)=>{if(activeTask()||pending||ref!==referenceKey(current,input.id)||!allowed(value.parameters,lighting.capabilities)||sameParameters(value.parameters,current.parameters))return null;
 const next=value.action==='save_variant'?variant(current,value.name||current.name+' · AI变体'):revise(current,value.parameters);next.parameters=value.parameters;
 if(value.source==='Nemotron'&&value.operationId)schemeOrigins[key(next)]=value.operationId;put(next);return {planId:current.planId,version:current.version};}
});
async function chooseStoredPhoto(id){
 pendingPhotoAssociation=null;
 const saved=serverPhotos.find(p=>p.id===id);if(!saved)throw Error('服务照片不存在。');
 const response=await fetch(saved.originalUrl,{cache:'no-store'});if(!response.ok)throw Error('照片读取失败。');
 const blob=await response.blob();file=new File([blob],saved.name,{type:blob.type});
 input={...saved,needsFile:false};mode='result';
 const versions=schemes.filter(s=>s.inputId===id);current=versions.reduce((a,b)=>!a||b.version>a.version?b:a,null)||createScheme(catalog.presets[0].id,saved.name+' · 默认',id);
 if(!versions.length)schemes.push(current);persist();render();
}
function downloadJSON(value,name){const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
$('export-legacy-library').onclick=()=>{try{const old=JSON.parse(localStorage.getItem(libraryKey)||'[]'),cursor=JSON.parse(localStorage.getItem(cursorKey)||'null');downloadJSON(archive(validateLibrary(old,catalog.presets.map(p=>p.id)),cursor?.inputStub?[cursor.inputStub]:[]),'lighttry-legacy-browser-schemes.json');}catch(e){error(e.message);}};
$('export-library').onclick=()=>downloadJSON(archive(schemes,[...(storageGet(photoStubsKey)||[]),...(input&&!input.sampleId?[input]:[])],tasks.map(t=>t.taskId)),'lighttry-browser-schemes.json');
$('import-library').onclick=()=>$('import-library-file').click();
$('import-library-file').onchange=async()=>{try{const f=$('import-library-file').files[0];if(!f)return;if(f.size>1024*1024)throw Error('方案 JSON 超过1MiB。');const value=readArchive(JSON.parse(await f.text()),catalog.presets.map(p=>p.id));const importedVisible=visibleFamilies(value.schemes);const merged=mergeLibraries(schemes,importedVisible);schemes=merged;$('all-photos').checked=true;const oldStubs=storageGet(photoStubsKey)||[];localStorage.setItem(accountNamespace+photoStubsKey,JSON.stringify([...oldStubs.filter(p=>!value.photos.some(n=>n.id===p.id)),...value.photos]));for(const id of value.taskIds){try{if(!tasks.some(t=>t.taskId===id))tasks.push(await api('/api/tasks/'+id));}catch{}}if(importedVisible.length){const selected=importedVisible.at(-1),sample=catalog.samples.find(s=>s.input.sha256.slice(0,32)===selected.inputId),photo=serverPhotos.find(p=>p.id===selected.inputId),stub=value.photos.find(p=>p.id===selected.inputId);if(sample)await chooseSample(sample.id);else if(photo)await chooseStoredPhoto(photo.id);else if(stub){input=stub;file=null;}if(input.id===selected.inputId)current=selected;}persist();render();$('storage-note').textContent='已导入浏览器草稿。照片/HDR 不在 JSON 内；请重新载入同一原文件或先导入 HDR，再点保存到服务。';}catch(e){error(e.message);}finally{$('import-library-file').value='';}};
$('save-server').onclick=async()=>{const button=$('save-server');if(button.disabled||!serverWorkspace)return;if(!confirm('保存全部方案到服务；若当前为用户照片，会上传原照片到私有数据目录。不会生成或收费。继续？'))return;button.disabled=true;try{if(file&&!input.sampleId){const photo=await api('/api/photos/'+input.id,{method:'POST',headers:{'Content-Type':file.type,'X-LightTry-Token':inference.csrfToken,'X-LightTry-Photo':btoa(unescape(encodeURIComponent(JSON.stringify({name:input.name}))))},body:file});serverPhotos=serverPhotos.filter(p=>p.id!==photo.id).concat(photo);}serverWorkspace=await api('/api/workspace',{method:'POST',headers:{'Content-Type':'application/json','X-LightTry-Token':inference.csrfToken},body:JSON.stringify({schemaVersion:1,schemes:archive(schemes).schemes})});serverPhotos=serverWorkspace.photos;persist();$('storage-note').textContent='已保存到服务私有目录；换浏览器登录同一服务可找回方案与已上传照片。';}catch(e){error(e.message+'；可能已保存照片，方案未全部保存，请核对后重试。');}finally{button.disabled=false;}};
$('export-server').onclick=()=>{location.href='/api/workspace/export';};
async function init(){try{try{const me=await api('/api/me');accountNamespace='lighttry.user.'+me.username+'.';$('logout').hidden=false;}catch(e){if(e.status!==404)throw e;}[catalog,lighting,inference]=await Promise.all([api('/api/catalog'),api('/api/lighting'),api('/api/inference')]);if(lighting.language.developmentTestMode)document.querySelector('.boundary').textContent+=' · 演示模式（不调用真实模型）';await lightConsole.load();try{serverWorkspace=await api('/api/workspace');serverPhotos=serverWorkspace.photos||[];$('save-server').hidden=false;$('export-server').hidden=false;}catch(e){if(e.status!==404)throw e;}deletedFamilies=(storageGet(deletedKey)||[]);if(!Array.isArray(deletedFamilies))deletedFamilies=[];deletedFamilies=deletedFamilies.filter(d=>d&&/^[a-f0-9]{32}$/.test(d.planId)&&Array.isArray(d.versions)).slice(-200).map(d=>({...d,versions:validateLibrary(d.versions,catalog.presets.map(p=>p.id)).filter(s=>s.planId===d.planId)}));schemeOrigins=storageGet(originsKey)||{};schemes=visibleFamilies(validateLibrary(storageGet(libraryKey),catalog.presets.map(p=>p.id)));if(serverWorkspace)schemes=mergeLibraries(schemes,visibleFamilies(validateLibrary(serverWorkspace.schemes,catalog.presets.map(p=>p.id))));schemes=mergeAcceptedLibrary(schemes,visibleFamilies(validateLibrary(lighting.importedSchemes||[],catalog.presets.map(p=>p.id))));schemes=visibleFamilies(schemes);$('photo-select').innerHTML=catalog.samples.map(s=>`<option value="${s.id}">${esc(photoTitle(s,null))}${s.unstable?' · 材质不稳定':''}</option>`).join('');$('environments').innerHTML=catalog.presets.map(p=>`<button type="button" data-environment="${p.id}" aria-pressed="false">${esc(p.name)}</button>`).join('');document.querySelectorAll('[data-environment]').forEach(b=>{b.onclick=()=>selectEnvironment(b.dataset.environment);b.onkeydown=e=>{const buttons=[...document.querySelectorAll('[data-environment]')];let i=buttons.indexOf(b);if(['ArrowLeft','ArrowRight','Home','End'].includes(e.key)){e.preventDefault();i=e.key==='Home'?0:e.key==='End'?buttons.length-1:(i+(e.key==='ArrowLeft'?-1:1)+buttons.length)%buttons.length;buttons[i].focus();}};});$('environment').innerHTML=catalog.presets.map(p=>`<option value="${p.id}">${esc(p.name)}</option>`).join('');for(const id of [...new Set([...(serverWorkspace?.taskIds||[]),...(storageGet(tasksKey)||[])])].slice(0,200)){if(/^[0-9a-f]{32}$/.test(id)){try{tasks.push(await api('/api/tasks/'+id))}catch{}}}const cursor=storageGet(cursorKey),unfinished=storageGet(submissionKey);if(unfinished?.meta?.requestId){try{const recovered=await api('/api/requests/'+unfinished.meta.requestId);if(!tasks.some(t=>t.taskId===recovered.taskId))tasks.push(recovered);rememberSubmission(null)}catch{error('上次提交未得到确认；请求身份保留，重新载入同一照片才可手动重试。')}}for(const photo of serverPhotos){$('photo-select').add(new Option(photo.name,'__saved_'+photo.id));}
input={id:uid(),name:'待上传照片',width:1280,height:704,unbound:true};file=null;current=createScheme(catalog.presets[0].id,'未命名草稿',input.id);mode='result';compareKey=null;zoom=1;pan={x:0,y:0};await render();refreshGpuMonitor();
// Keep saved libraries and unsettled request evidence, but never auto-select their photos.
for(const task of tasks.filter(t=>['queued','running'].includes(t.status)||t.executionUncertain))poll(task.taskId).catch(e=>error('恢复任务失败：'+e.message));
}catch(e){error(e.message)}}
init();

$('details').onclick=()=>{const r=resultFor(current);$('detail-body').textContent=['方案：'+current.name,'版本：'+current.version,'照片：'+input.name,'状态：'+statusFor(current),r?'来源：'+(r.sourceNote||'当前方案生成结果'):'当前方案尚无生成结果。',r?.width&&r?.height?'尺寸：'+r.width+' × '+r.height:'',r?.task?.taskId?'任务编号：'+r.task.taskId:'','AI 生成可能改变颜色、文字和材质细节。'].filter(Boolean).join('\n');$('detail-dialog').showModal();};
$('close-details').onclick=()=>$('detail-dialog').close();

async function recoverTask(guard){const id=$('lookup-dialog').dataset.task;if(!id||!guard)return;try{const t=await api('/api/tasks/'+id+'/recover-transferred',{method:'POST',headers:{'Content-Type':'application/json','X-LightTry-Token':inference.csrfToken},body:JSON.stringify({recoveryGuardRunId:guard})});tasks=tasks.filter(x=>x.taskId!==id).concat(t);persist();render();}catch(e){error(e.message)}};

async function restoreTask(id){if(!id)return;if(!/^[0-9a-f]{32}$/.test(id)){error('任务编号格式不正确，请检查后重试。');return;}try{const t=await api('/api/tasks/'+id);tasks=tasks.filter(x=>x.taskId!==id).concat(t);input={...t.input,originalSha:t.originalInput?.sha256,originalUrl:t.input.originalUrl||t.input.url.replace(/\/input$/,'/original'),needsFile:true};file=null;const s=t.lightingScheme||{...createScheme(t.preset.environmentId||t.preset.id,t.input.name+' · 已有任务',t.input.id)};mode='result';zoom=1;pan={x:0,y:0};current=s;put(s,true);}catch(e){error(e.message)}};

function openLookup(kind){$('lookup-dialog').dataset.kind=kind;$('lookup-dialog').dataset.task=$('recover').dataset.task||'';$('lookup-title').textContent=kind==='task'?'找回本机既有任务':'恢复凭据编号';$('lookup-value').value='';$('lookup-dialog').showModal();$('lookup-value').focus();}
$('restore-task').onclick=()=>openLookup('task');$('recover').onclick=()=>openLookup('recover');
$('lookup-dialog').addEventListener('close',()=>{if($('lookup-dialog').returnValue==='confirm'){const id=$('lookup-value').value;$('lookup-dialog').dataset.kind==='task'?restoreTask(id):recoverTask(id);}});

// Persistent layout state is independent of recipe and task identities.
const divider=$('workspace-divider'), splitGrid=document.querySelector('.work-grid');
let splitRatio=55;
try{const n=Number(localStorage.getItem(accountNamespace+'lighttry.workspaceSplit.v1'));if(n>=40&&n<=68)splitRatio=n;}catch{}
function setSplit(n){
 splitRatio=Math.max(40,Math.min(68,n));
 splitGrid.style.setProperty('--preview-share',splitRatio+'fr');
 splitGrid.style.setProperty('--lighting-share',(100-splitRatio)+'fr');
 divider.setAttribute('aria-valuenow',String(Math.round(splitRatio)));
 $('layout-ratio').textContent='预览 '+Math.round(splitRatio)+'% / 调光 '+(100-Math.round(splitRatio))+'%';
 document.querySelectorAll('[data-layout]').forEach(b=>b.setAttribute('aria-pressed',String(Number(b.dataset.layout)===Math.round(splitRatio))));
 try{localStorage.setItem(accountNamespace+'lighttry.workspaceSplit.v1',String(splitRatio));}catch{}
 requestAnimationFrame(()=>applyView());
}
document.querySelectorAll('[data-layout]').forEach(b=>b.onclick=()=>setSplit(Number(b.dataset.layout)));
divider.onpointerdown=e=>{if(e.button!==0)return;divider.setPointerCapture(e.pointerId);divider.classList.add('dragging');};
divider.onpointermove=e=>{if(!divider.hasPointerCapture(e.pointerId))return;const r=splitGrid.getBoundingClientRect();setSplit((e.clientX-r.left)/r.width*100);};
divider.onpointerup=e=>{if(divider.hasPointerCapture(e.pointerId))divider.releasePointerCapture(e.pointerId);divider.classList.remove('dragging');};
divider.onpointercancel=()=>divider.classList.remove('dragging');
divider.onkeydown=e=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(e.key)){e.preventDefault();setSplit(e.key==='Home'?40:e.key==='End'?68:splitRatio+(e.key==='ArrowLeft'?-1:1));}};
setSplit(splitRatio);

const resetBlocked=()=>!inference||pending||!!storageGet(submissionKey)||tasks.some(t=>['queued','running'].includes(t.status)||t.executionUncertain||transferFailure(t));
$('reset-client').onclick=()=>{const blocked=resetBlocked();$('confirm-reset-client').disabled=blocked;$('reset-client-warning').textContent=blocked?'当前有未完成、待取回或状态不确定的任务，暂不能重置。请先核实或取回结果。':'';$('reset-client-dialog').showModal();};
$('confirm-reset-client').onclick=()=>{if(resetBlocked()){$('reset-client-warning').textContent='任务状态已变化，暂不能重置。';$('confirm-reset-client').disabled=true;return;}try{resetClientStorage(localStorage,sessionStorage,accountNamespace);location.reload();}catch(e){$('reset-client-warning').textContent='本机存储清理失败，未完成重置：'+e.message;}};

$('logout').onclick=async()=>{try{await api('/auth/logout',{method:'POST',headers:{'X-LightTry-Token':inference.csrfToken}});location.replace('/login');}catch(e){error('退出失败，请稍后重试。');}};

try{const message=sessionStorage.getItem('lighttry.gpuEntryNotice');if(message){$('gpu-entry-notice').textContent=message;$('gpu-entry-notice').hidden=false;sessionStorage.removeItem('lighttry.gpuEntryNotice');}}catch{}

// Read one local guard-snapshot stream; never asks the cloud provider to poll.
let gpuMonitorInfo=null,gpuMonitorBusy=false,gpuStartBusy=false,gpuMonitorTimer=null;
function paintGpuMonitor(info){
 gpuMonitorInfo=info;
 const labels={STOPPED:'已停止',STARTING:'启动中',LOADING:'准备中',READY:'运行中',EXECUTING:'生成中',STOPPING:'关闭中',UNKNOWN:'状态未知'};
 let label=info.providerConnected?labels[info.state]||'状态未知':info.configured===false?'未连接':info.stale?'状态已过期':labels[info.state]||'状态未知';
 if(info.startStatus==='requested'&&!info.active)label='启动请求已提交';
 if(info.startStatus==='failed'&&!info.active)label='启动未成功';
 $('gpu-monitor').dataset.state=info.configured===false&&!info.providerConnected?'DISCONNECTED':info.state||'UNKNOWN';
 $('gpu-monitor').title=info.message||'GPU 服务器状态';
 $('gpu-monitor-state').textContent=label;
 $('gpu-monitor-demo').hidden=!info.simulation;
 $('gpu-monitor-time').textContent=info.observedAt?'更新于 '+new Date(info.observedAt*1000).toLocaleTimeString('zh-CN',{hour12:false}):'';
 $('gpu-monitor-start').disabled=gpuStartBusy||!info.canStart||!inference?.csrfToken;
 $('gpu-monitor-start').title=info.canStart?'启动 GPU 可能产生费用':info.message||'当前不可启动';
}
async function refreshGpuMonitor(){
 if(gpuMonitorBusy)return;
 gpuMonitorBusy=true;$('gpu-monitor-refresh').disabled=true;
 try{paintGpuMonitor(await api('/api/gpu/entry-status'));}
 catch(e){paintGpuMonitor({state:'UNKNOWN',configured:e.status===404?false:undefined,canStart:false,message:e.status===404?'本地预览未连接 GPU 服务。':'暂时无法读取 GPU 状态，请稍后刷新。'});}
 finally{gpuMonitorBusy=false;$('gpu-monitor-refresh').disabled=false;clearTimeout(gpuMonitorTimer);if(!document.hidden)gpuMonitorTimer=setTimeout(refreshGpuMonitor,15000);}
}
$('gpu-monitor-refresh').onclick=refreshGpuMonitor;
$('gpu-monitor-start').onclick=()=>{if(gpuStartBusy||!gpuMonitorInfo?.canStart)return;$('gpu-monitor-warning').textContent='';$('gpu-monitor-confirm').disabled=false;$('gpu-monitor-dialog').showModal();};
$('gpu-monitor-confirm').onclick=async()=>{
 if(gpuStartBusy||!gpuMonitorInfo?.canStart||!inference?.csrfToken)return;
 gpuStartBusy=true;$('gpu-monitor-confirm').disabled=true;$('gpu-monitor-start').disabled=true;
 $('gpu-monitor-dialog').close();
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),5000);
 try{
  const response=await fetch('/api/gpu/entry-start',{method:'POST',headers:{'Content-Type':'application/json','X-LightTry-Token':inference.csrfToken},body:JSON.stringify({requestId:uid()}),signal:controller.signal});
  if(!response.ok)throw Error('GPU 启动请求未被接受，请刷新状态后核实。');
  const value=await response.json();
  $('gpu-entry-notice').textContent=value.status==='already_active'?'GPU 已处于活动状态。':value.status==='failed'?'上次 GPU 启动未成功，请联系管理员核实。':'GPU 启动请求已提交，你可以继续编辑方案。';
 }catch(e){$('gpu-entry-notice').textContent=e.name==='AbortError'?'启动请求结果尚未确认，请勿重复提交，稍后刷新状态。':e.message;}
 finally{clearTimeout(timer);gpuStartBusy=false;$('gpu-entry-notice').hidden=false;await refreshGpuMonitor();}
};
document.addEventListener('visibilitychange',()=>{clearTimeout(gpuMonitorTimer);if(!document.hidden)refreshGpuMonitor();});
window.addEventListener('pagehide',()=>clearTimeout(gpuMonitorTimer));
