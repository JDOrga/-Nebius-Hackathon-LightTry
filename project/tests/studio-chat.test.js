import test from 'node:test';import assert from 'node:assert/strict';
import {sessionKey,sensitive,boundedMessages,applicable} from '../web/chat.js';
test('session keyed by photo/family not comparison or version',()=>{const s={inputId:'a',planId:'b',version:1};assert.equal(sessionKey(s),sessionKey({...s,version:2,compare:'x'}));assert.notEqual(sessionKey(s),sessionKey({...s,inputId:'c'}));});
test('bounded text context has no fabricated summary',()=>{const m=Array.from({length:30},(_,i)=>({role:'user',text:String(i).repeat(200)}));const result=boundedMessages(m);assert.ok(result.length<=8);assert.ok(result.reduce((n,m)=>n+m.text.length,0)<=2400);assert.ok(result.every(m=>Object.keys(m).sort().join()==='role,text'));});
test('credentials excluded while links paths and technical discussion are plain text',()=>{for(const s of ['hf_secret','-----BEGIN'])assert.ok(sensitive(s));for(const s of ['C:\\test\\demo','https://example.com','SSH 和 powershell 有什么区别','保留环境，试偏暗版本'])assert.ok(!sensitive(s));});
test('conversation history keeps longer answers within total bound',()=>{const text='聊聊今天的想法。'.repeat(90);assert.equal(boundedMessages([{role:'assistant',text}])[0].text,text);});
test('stale reference, typing, same parameters, applied/rejected card never applies',()=>{const live={reference:'v1',scheme:{parameters:{environmentId:'sunny',offsetDeg:0,strength:1}}};const m={ref:'v1',draftEpoch:1,value:{status:'ready',parameters:{environmentId:'sunny',offsetDeg:0,strength:.7}}};assert.ok(applicable(m,live,1));assert.ok(!applicable(m,{...live,busy:true},1));assert.ok(!applicable(m,live,2));assert.ok(!applicable({...m,state:'applied'},live,1));assert.ok(!applicable({...m,state:'rejected'},live,1));assert.ok(!applicable({...m,ref:'v0'},live,1));assert.ok(!applicable({...m,value:{status:'ready',parameters:live.scheme.parameters}},live,1));});
test('assistant Markdown creates safe structure without interpreting model HTML',async()=>{
 const {renderAssistantMarkdown}=await import('../web/chat.js');
 class Node{constructor(tag){this.tag=tag;this.children=[];this.value='';}set textContent(value){this.value=String(value);this.children=[];}get textContent(){return this.value+this.children.map(n=>n.textContent).join('');}append(...nodes){this.children.push(...nodes);}}
 const old=globalThis.document;globalThis.document={createElement:tag=>new Node(tag),createTextNode:value=>{const node=new Node('#text');node.textContent=value;return node;}};
 try{
  const root=new Node('article');renderAssistantMarkdown(root,'## 标题\n\n**重点**、*强调*、`代码`\n\n- 第一\n- 第二\n\n```js\nconst x = 1;\n```\n\n[安全](https://example.com) [危险](javascript:alert(1)) <img src=x>');
  const all=[];const walk=node=>{all.push(node);node.children.forEach(walk);};walk(root);
  assert.ok(all.some(n=>n.tag==='h4'&&n.textContent==='标题'));
  for(const tag of ['strong','em','ul','li','pre','code'])assert.ok(all.some(n=>n.tag===tag),tag);
  assert.deepEqual(all.filter(n=>n.tag==='a').map(n=>n.href),['https://example.com/']);
  assert.ok(!all.some(n=>n.tag==='img'));
  assert.match(root.textContent,/<img src=x>/);
  assert.equal(all.find(n=>n.tag==='pre').textContent,'const x = 1;');
 }finally{globalThis.document=old;}
});
test('IME composition Enter is not send; Enter and Shift+Enter rules',async()=>{
 const {createChat}=await import('../web/chat.js');const nodes=new Map();const old={document:globalThis.document,sessionStorage:globalThis.sessionStorage,addEventListener:globalThis.addEventListener,visualViewport:globalThis.visualViewport};
 globalThis.document={getElementById:id=>{if(!nodes.has(id))nodes.set(id,{value:''});return nodes.get(id);},addEventListener(){}};globalThis.sessionStorage={getItem:()=>null};globalThis.addEventListener=()=>{};globalThis.visualViewport=null;
 try{createChat({get:()=>null});const input=nodes.get('chat-input');let prevented=0;const key=extra=>({key:'Enter',preventDefault(){prevented++;},...extra});input.oncompositionstart();input.onkeydown(key({}));assert.equal(prevented,0);input.oncompositionend();input.onkeydown(key({isComposing:true}));input.onkeydown(key({keyCode:229}));input.onkeydown(key({shiftKey:true}));assert.equal(prevented,0);input.onkeydown(key({}));assert.equal(prevented,1);}finally{Object.assign(globalThis,old);}
});

