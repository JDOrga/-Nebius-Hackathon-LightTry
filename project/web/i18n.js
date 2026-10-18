import {en} from './i18n-en.js';

const cookieName='lighttry_lang';
const attrs=['aria-label','placeholder','title','alt'];
let locale='zh';
const sourceText=new WeakMap(),renderedText=new WeakMap(),sourceAttrs=new WeakMap(),renderedAttrs=new WeakMap();

export function resolveLanguage(preferences=[],manual=null){
 if(manual==='en'||manual==='zh')return manual;
 for(const item of preferences){
  const primary=String(item).toLowerCase().split('-')[0];
  if(primary==='zh'||primary==='en')return primary;
 }
 return 'en';
}
function manualLanguage(){
 const part=document.cookie.split(';').map(x=>x.trim()).find(x=>x.startsWith(cookieName+'='));
 const value=part?.slice(cookieName.length+1);
 return value==='zh'||value==='en'?value:null;
}
const patterns=[
 [/^更新于 (.+)$/u,(_,at)=>`Updated at ${at}`],
 [/^最晚自动停机 (\d\d:\d\d:\d\d)$/u,(_,left)=>`Latest automatic stop ${left}`],
 [/^本次预算 ([\d.]+) 美元（含税）。自动停机不保证账单硬封顶。请求提交后可继续编辑方案。$/u,(_,sum)=>`Session budget $${sum} (including tax). Automatic stop is not a hard billing cap. You may keep editing after submitting.`],
 [/^已完成 (\d+)\/(\d+) 个观测阶段$/u,(_,done,total)=>`${done}/${total} observed stages complete`],
 [/^阶段记录更新 (.+)$/u,(_,at)=>`Stage record updated ${at}`],
 [/^新方案待生成：(.+) · v(\d+)（仅此方案）。$/u,(_,name,version)=>`New plan pending generation: ${name} · v${version} (this plan only).`],
 [/^当前方案已确认应用到 v(\d+)$/u,(_,version)=>`Applied to current plan v${version}`],
 [/^已确认应用到 v(\d+)$/u,(_,version)=>`Applied to v${version}`],
 [/^已应用到版本 (\d+)$/u,(_,version)=>`Applied to version ${version}`],
 [/^(\d+) 秒$/u,(_,seconds)=>`${seconds} sec`],
 [/^(\d+) 分 (\d+) 秒$/u,(_,minutes,seconds)=>`${minutes} min ${seconds} sec`],
 [/^服务返回无效数据（HTTP (\d+)）$/u,(_,code)=>`Invalid service response (HTTP ${code})`],
 [/^历史生成结果 · (.+)$/u,(_,name)=>`Historical generated result · ${name}`],
 [/^离线模拟任务 · 非模型结果 (.+)$/u,(_,name)=>`Offline simulation · not a model result ${name}`],
 [/^正式任务 (.+)$/u,(_,name)=>`Production task ${name}`],
 [/^历史样例 · (.+)$/u,(_,name)=>`Historical sample · ${name}`],
 [/^删除“(.+)”及其全部 (\d+) 个版本？$/u,(_,name,count)=>`Delete “${name}” and all ${count} versions?`],
 [/^已删除“(.+)”的全部版本，可撤销。$/u,(_,name)=>`All versions of “${name}” were deleted; this can be undone.`],
 [/^选择方案：(.+)$/u,(_,name)=>`Select plan: ${name}`],
 [/^恢复任务失败：(.+)$/u,(_,detail)=>`Task recovery failed: ${detail}`],
 [/^最近观测 (.+) · (\d+) 秒前$/u,(_,at,seconds)=>`Latest observation ${at} · ${seconds} sec ago`],
 [/^最近观测 (.+)$/u,(_,when)=>`Latest observation ${when}`],
 [/^状态不可靠 · (.+)$/u,(_,detail)=>`Status unreliable · ${detail}`],
 [/^累计主机耗时 (.+) · CPU (.+) · 读盘 (.+)$/u,(_,elapsed,cpu,read)=>`Host elapsed ${elapsed} · CPU ${cpu} · Disk read ${read}`],
 [/^(.+)数值$/u,(_,label)=>`${translateString(label,'en')} value`],
 [/^\$([\d.]+) 含税$/u,(_,amount)=>`$${amount} incl. tax`],
 [/^方向变体 · 环境偏移 \+([\d.]+)°$/u,(_,degrees)=>`Direction variant · environment offset +${degrees}°`],
 [/^(.+) · 旧版本$/u,(_,name)=>`${name} · Older version`],
 [/^(.+) · 材质不稳定$/u,(_,name)=>`${name} · Unstable material`],
 [/^(.+) · 属性$/u,(_,name)=>`${translateString(name,'en')} · Properties`],
 [/^预览 (\d+)% \/ 调光 (\d+)%$/u,(_,preview,lighting)=>`Preview ${preview}% / Lighting ${lighting}%`],
 [/^当前方案：(.+) · v(\d+)$/u,(_,name,version)=>`Current plan: ${translateString(name,'en')} · v${version}`],
 [/^编辑完整名称：(.+)$/u,(_,name)=>`Edit full name: ${translateString(name,'en')}`],
 [/^(.+) · (.+) · v(\d+)$/u,(_,photo,plan,version)=>`${translateString(photo,'en')} · ${translateString(plan,'en')} · v${version}`],
];
const fragments=[
 ['GPU 启动服务暂不可用，可以先进入工作台。','GPU start is unavailable. You can still use the workbench.'],
 ['GPU启动暂不可用','GPU start unavailable'],
 ['尚无可靠观测','No reliable observation yet'],
 ['照片分析模型','Photo analysis model'],
 ['光照生成模型','Lighting generation model'],
 ['个观测阶段，非耗时比例','observed stages, not an elapsed-time ratio'],
 ['未采集','Not collected'],
 ['未记录','Not recorded'],
];
export function translateString(value,language=locale){
 if(language!=='en'||typeof value!=='string')return value;
 const match=value.match(/^(\s*)([\s\S]*?)(\s*)$/u),body=match?.[2]??value;
 let translated=Object.hasOwn(en,body)?en[body]:undefined;
 if(translated===undefined){for(const [pattern,render] of patterns){const found=body.match(pattern);if(found){translated=render(...found);break;}}}
 const matched=translated!==undefined;
 let composite=translated??body;
 for(const [source,target] of fragments)composite=composite.replaceAll(source,target);
 if(matched||composite!==body)translated=composite.replaceAll('：',': ').replaceAll('，',', ');
 return translated===undefined?value:(match?.[1]??'')+translated+(match?.[3]??'');
}
function text(node){
 const current=node.nodeValue??'';
 if(current!==renderedText.get(node))sourceText.set(node,current);
 const original=sourceText.get(node)??current,next=translateString(original);
 if(current!==next)node.nodeValue=next;
 renderedText.set(node,next);
}
function attributes(element){
 let source=sourceAttrs.get(element),rendered=renderedAttrs.get(element);
 if(!source){source=new Map();sourceAttrs.set(element,source);}
 if(!rendered){rendered=new Map();renderedAttrs.set(element,rendered);}
 for(const name of attrs){
  if(!element.hasAttribute(name))continue;
  const current=element.getAttribute(name);
  if(current!==rendered.get(name))source.set(name,current);
  const next=translateString(source.get(name));
  if(current!==next)element.setAttribute(name,next);
  rendered.set(name,next);
 }
}
function translateTree(root){
 if(root.nodeType===Node.TEXT_NODE){
  if(!root.parentElement?.closest('[data-no-i18n],script,style'))text(root);
  return;
 }
 if(root.nodeType!==Node.ELEMENT_NODE)return;
 if(root.closest('[data-no-i18n],script,style'))return;
 attributes(root);
 const walker=document.createTreeWalker(root,NodeFilter.SHOW_ELEMENT|NodeFilter.SHOW_TEXT);
 while(walker.nextNode()){
  const node=walker.currentNode;
  if(node.nodeType===Node.TEXT_NODE){if(!node.parentElement?.closest('[data-no-i18n],script,style'))text(node);}
  else if(!node.closest('[data-no-i18n],script,style'))attributes(node);
 }
}
function choose(next,save){
 locale=next;
 document.documentElement.lang=next==='en'?'en':'zh-CN';
 if(save)document.cookie=`${cookieName}=${next}; Path=/; Max-Age=31536000; SameSite=Lax${location.protocol==='https:'?'; Secure':''}`;
 const selector=document.getElementById('locale-select');if(selector)selector.value=next;
 translateTree(document.documentElement);
}
export function installI18n(){
 choose(resolveLanguage(navigator.languages?.length?navigator.languages:[navigator.language],manualLanguage()),false);
 document.getElementById('locale-select')?.addEventListener('change',event=>choose(event.target.value,true));
 window.addEventListener('languagechange',()=>{if(!manualLanguage())choose(resolveLanguage(navigator.languages),false);});
 new MutationObserver(changes=>{
  for(const change of changes){
   if(change.type==='characterData')translateTree(change.target);
   else if(change.type==='attributes')attributes(change.target);
   else for(const node of change.addedNodes)translateTree(node);
  }
 }).observe(document.documentElement,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:attrs});
 return locale;
}
export const currentLanguage=()=>locale;
