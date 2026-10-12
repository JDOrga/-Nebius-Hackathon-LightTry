import {schemeWire} from './scheme-state.js';
import {differences} from './console.js';
import {uid,sameParameters} from './scheme-state.js';
const $=id=>document.getElementById(id);
export const sessionKey=s=>s.inputId+':'+s.planId;
export const sensitive=t=>/(?:[A-Za-z]:[\\/]|(?:sk-|hf_|ghp_)[A-Za-z0-9_-]+|-----BEGIN|https?:\/\/|\/Users\/|\/home\/)/.test(t);
export const boundedMessages=items=>{let total=0;return items.filter(m=>m.role==='user'||m.role==='assistant').slice(-8).reverse().filter(m=>{total+=m.text.length;return total<=2400;}).reverse().map(m=>({role:m.role,text:m.text.slice(0,320)}));};
export const applicable=(m,live,draftEpoch)=>!live.busy&&m.value?.status==='ready'&&!m.state&&m.ref===live.reference&&m.draftEpoch===draftEpoch&&!sameParameters(m.value.parameters,live.scheme.parameters);
export function createChat({get,api,environmentLabel,apply}){
 const storage='lighttry.chat.tab.v1';let sessions={},selected=null,ref=null,pending=false,editEpoch=0,composing=false,drag=null;
 try{const saved=JSON.parse(sessionStorage.getItem(storage)||'{}');if(saved&&typeof saved==='object'&&!Array.isArray(saved))for(const [k,v] of Object.entries(saved).slice(-4)){if(/^[a-f0-9]{32}:[a-f0-9]{32}$/.test(k)&&/^[a-f0-9]{32}$/.test(v.id)&&Array.isArray(v.items))sessions[k]={id:v.id,items:v.items.filter(m=>['user','assistant','notice'].includes(m.role)&&typeof m.text==='string'&&m.text.length<=600&&!sensitive(m.text)).slice(-8),draft:''};}}catch{}
 // Reloaded proposal cards are inert: only live validated responses can apply.
 for(const v of Object.values(sessions))for(const m of v.items){delete m.value;delete m.ref;if(m.operationId&&!['applied','rejected'].includes(m.state))m.state='stale';}
 function save(){try{const entries=Object.entries(sessions).slice(-4);sessionStorage.setItem(storage,JSON.stringify(Object.fromEntries(entries.map(([k,v])=>[k,{id:v.id,items:v.items.slice(-8).map(m=>({role:m.role,text:m.text.slice(0,600),operationId:m.operationId,state:m.state||'stale',appliedVersion:m.appliedVersion}))}]))));}catch{$('chat-status').textContent='标签会话存储不可用；关闭后文字不会保留。';}}
 function session(){const live=get();if(!live)return null;const k=sessionKey(live.scheme);if(k!==selected){if(selected&&sessions[selected])sessions[selected].draft=$('chat-input').value;selected=k;sessions[k]??={id:uid(),items:[],draft:''};for(const old of Object.keys(sessions).slice(0,-4))if(old!==k)delete sessions[old];$('chat-input').value=sessions[k].draft;editEpoch++;}
 if(ref&&ref!==live.reference&&sessions[k].items.length){sessions[k].items.push({role:'notice',text:'编辑上下文已改变，下一次请求使用当前版本。旧建议不能直接应用。'});sessions[k].items=sessions[k].items.slice(-12);}ref=live.reference;return sessions[k];}
 function textNode(tag,text,cls){const e=document.createElement(tag);e.textContent=text;if(cls)e.className=cls;return e;}
 function update(){const live=get(),s=session();if(!live||!s)return;
 $('chat-context').textContent=live.label;$('chat-service').textContent=live.language.enabled?(live.language.developmentTestMode?'隔离测试 transport · 非 Nemotron / GPU':'Nemotron 文字服务已启用 · 发送可能产生文字费用，不生成图片'):'Nemotron 未配置 · 可浏览会话，仍可手动调光';
 $('chat-send').disabled=pending||!live.language.enabled;$('chat-send').textContent=pending?'等待中…':'发送';$('chat-send').title=!live.language.enabled?'服务未配置，未发出模型请求':pending?'请求仍在等待，不重复发送':'发送文字，不生成图片';
 const log=$('chat-history'),previousScroll=log.scrollTop,atEnd=log.scrollHeight-log.scrollTop-log.clientHeight<40;log.replaceChildren();if(!s.items.length)log.append(textNode('p','从一个想法开始，也可以询问理由。未配置时不会伪造回复。','chat-empty'));
 for(const m of s.items){const bubble=textNode('article',m.text,'chat-bubble '+m.role);log.append(bubble);
 if(m.value?.status==='ready'){
 const v=m.value,card=document.createElement('div');card.className='chat-suggestion';bubble.append(card);
 card.append(textNode('strong','建议差异 · '+(v.source==='OFFLINE_SYNTHETIC'?'隔离替身':'文字服务')));
 for(const line of differences(m.before,v.parameters))card.append(textNode('p',line));
 if(v.parameters.schemaVersion===2)card.append(textNode('p','连续输入参数／程序化远场布光为工程实验范围；非精确照片曝光或物理灯位。','chat-experimental'));
 let why=live.busy?'真实任务处理中，稍后应用；不改变运行中的参照。':m.state==='applied'?('已应用到 v'+m.appliedVersion+'，尚未生成。'):m.state==='rejected'?'已拒绝，当前方案不变。':m.ref!==live.reference||m.draftEpoch!==editEpoch?'旧上下文／需求已变，需基于当前状态重新请求。':sameParameters(v.parameters,live.scheme.parameters)?'参数相同，无需修改或创建版本。':'尚未应用，当前配置不变。';card.append(textNode('p',why));
 const button=textNode('button','应用到当前方案');button.type='button';button.disabled=!applicable(m,live,editEpoch);card.append(button);
 button.onclick=()=>{const now=get();if(!applicable(m,now,editEpoch))return;const result=apply(v,m.ref);if(result){m.state='applied';m.appliedVersion=result.version;$('chat-status').textContent='实际应用：方案 '+result.planId.slice(0,8)+' / v'+result.version+'。未提交生成。';save();update();}};
 const reject=textNode('button','拒绝建议');reject.type='button';reject.disabled=!!m.state;card.append(reject);reject.onclick=()=>{m.state='rejected';save();update();};
 }
 }
 log.scrollTop=atEnd?log.scrollHeight:previousScroll;
 }
 async function send(e){e?.preventDefault();const live=get(),s=session(),text=$('chat-input').value.trim();if(pending||!live?.language.enabled||!text)return;if(sensitive(text)){$('chat-status').textContent='请去除密钥、网址或机器路径；仅发送光照文字。';return;}
 const captured=live.reference,epoch=editEpoch,rid=uid(),sk=selected;pending=true;
 const messages=boundedMessages(s.items.map(m=>({...m,text:m.text+(m.operationId?'（建议状态：'+(m.state==='applied'?'已应用到v'+m.appliedVersion:m.state==='rejected'?'已拒绝':m.ref===captured?'尚未应用':'旧上下文')+'）':'')}))),operations=s.items.filter(m=>m.operationId).slice(-4).map(m=>({operationId:m.operationId,state:m.state|| (m.ref===captured?'proposed':'stale')}));
 s.items.push({role:'user',text});$('chat-input').value='';s.draft='';$('chat-status').textContent='正在等待文字服务；收起或关闭不会取消上游请求。';save();update();$('chat-history').scrollTop=$('chat-history').scrollHeight;
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),65000);
 try{
 const safeScheme={...schemeWire(live.scheme),name:'当前方案'};const normalized=await api('/api/lighting/normalize',{method:'POST',headers:{'Content-Type':'application/json','X-LightTry-Token':live.token},body:JSON.stringify(safeScheme)});
 if(get().reference!==captured||selected!==sk||editEpoch!==epoch)throw Error('准备期间上下文已改变，尚未发送模型请求。');
 const snapshot=Object.fromEntries(['inputId','planId','version','recipeKey'].map(k=>[k,normalized[k]]));
 const body={currentScheme:safeScheme,currentResult:live.result,text,history:[],replyLanguage:'zh',chat:{schemaVersion:1,sessionId:s.id,requestId:rid,snapshot,messages,operations}};
 const value=await api('/api/lighting/recommend',{method:'POST',headers:{'Content-Type':'application/json','X-LightTry-Token':live.token},body:JSON.stringify(body),signal:controller.signal});
 if(value.sessionId!==s.id||value.requestId!==rid)throw Error('响应关联身份不一致，未应用。');
 s.items.push({role:'assistant',text:[value.reason,value.question].filter(Boolean).join(' ')||'此需求暂无可执行建议。',value,operationId:value.status==='ready'?value.operationId:undefined,ref:captured,draftEpoch:epoch,before:live.scheme.parameters});
 $('chat-status').textContent=(value.source==='OFFLINE_SYNTHETIC'?'隔离测试 transport 返回，非真实模型。':'文字响应已返回。')+' 未自动应用或生成。'+(get().reference!==captured||selected!==sk||epoch!==editEpoch?'旧上下文响应仅保留在原会话。':'');
 }catch(err){s.items.push({role:'notice',text:err.name==='AbortError'?'本机等待超时，上游可能已计费或仍在处理；不会自动重试，也未声称取消上游。':err.message});$('chat-status').textContent='请求未产生可应用结果；当前方案不变。'}
 finally{clearTimeout(timer);pending=false;s.items=s.items.slice(-12);save();update();}
 }
 $('chat-form').onsubmit=send;$('chat-input').oncompositionstart=()=>composing=true;$('chat-input').oncompositionend=()=>composing=false;
 $('chat-input').oninput=()=>{editEpoch++;if(selected)sessions[selected].draft=$('chat-input').value;update();};
 $('chat-input').onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing&&!composing&&e.keyCode!==229){e.preventDefault();send();}};
 const panel=$('chat-panel');function clamp(){if(matchMedia('(max-width:700px)').matches){panel.style.left='';panel.style.top='';return;}const b=panel.getBoundingClientRect();panel.style.left=Math.max(8,Math.min(b.left,innerWidth-b.width-8))+'px';panel.style.top=Math.max(8,Math.min(b.top,innerHeight-b.height-8))+'px';}
 function center(){if(matchMedia('(max-width:700px)').matches)return;const b=panel.getBoundingClientRect();panel.style.left=Math.max(8,(innerWidth-b.width)/2)+'px';panel.style.top=Math.max(8,(innerHeight-b.height)/2)+'px';clamp();}
 function open(){panel.hidden=false;$('chat-open').setAttribute('aria-expanded','true');$('chat-open').title='收起 AI 试光助手';update();if(!panel.style.left)center();clamp();$('chat-input').focus();}
 function close(){panel.hidden=true;$('chat-open').setAttribute('aria-expanded','false');$('chat-open').title='打开 AI 试光助手';$('chat-open').focus();}
 $('chat-open').onclick=()=>panel.hidden?open():close();$('chat-close').onclick=()=>close();
 document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!panel.hidden&&!e.isComposing&&!composing&&!document.querySelector('dialog[open]')){e.preventDefault();close();}});
 panel.onkeydown=e=>{if(e.key==='Escape'&&!e.isComposing&&!composing){e.preventDefault();close();}};
 $('chat-handle').onpointerdown=e=>{if(e.target.closest('button')||matchMedia('(max-width:700px)').matches)return;const b=panel.getBoundingClientRect();drag={x:e.clientX,y:e.clientY,left:b.left,top:b.top};$('chat-handle').setPointerCapture(e.pointerId);};
 $('chat-handle').onpointermove=e=>{if(drag){panel.style.left=drag.left+e.clientX-drag.x+'px';panel.style.top=drag.top+e.clientY-drag.y+'px';clamp();}};
 $('chat-handle').onpointerup=$('chat-handle').onpointercancel=()=>drag=null;
 addEventListener('resize',()=>{if(!panel.hidden)clamp();});visualViewport?.addEventListener('resize',()=>{panel.style.setProperty('--chat-vh',(visualViewport.height*.01)+'px');if(!panel.hidden)clamp();});
 return {update};
}
