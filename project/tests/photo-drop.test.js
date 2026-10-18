import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';
import {webcrypto} from 'node:crypto';

const source=readFileSync(new URL('../web/workbench.js',import.meta.url),'utf8');
const code=source.slice(source.indexOf('let photoLoading=false;'),source.indexOf('\nasync function poll('));
function target(){
 const classes=new Set(),listeners={};
 return {classList:{add:c=>classes.add(c),remove:c=>classes.delete(c)},classes,listeners,
  addEventListener:(name,handler)=>listeners[name]=handler};
}
function setup(unfinished=null){
 const zones=[target(),target()],doc=target(),picker={files:[],value:'selected'};
 const errors=[],revoked=[],puts=[];
 const context={document:Object.assign(doc,{querySelector:s=>zones[s==='.photo-bar'?0:1]}),
  $:()=>picker,error:m=>errors.push(m),catalog:{},inference:{},current:{name:'Plan'},
  input:{id:'previous'},file:null,mode:'result',zoom:1,pan:{},pendingPhotoAssociation:null,
  storageGet:()=>unfinished,submissionKey:'request',crypto:webcrypto,
  URL:{createObjectURL:()=> 'blob:photo',revokeObjectURL:u=>revoked.push(u)},
  Image:class{naturalWidth=100;naturalHeight=100;async decode(){}},
  uid:()=> 'new-photo',variant:s=>({...s}),put:s=>puts.push(s),persist(){},render(){}};
 runInNewContext(code,context);
 const event=(files=[],types=['Files'])=>({dataTransfer:{types,files},preventDefault(){this.prevented=true;}});
 const photo={name:'photo.png',type:'image/png',size:12,arrayBuffer:async()=>new Uint8Array([1,2,3]).buffer};
 return {context,zones,doc,picker,errors,revoked,puts,event,photo};
}
test('nested drag highlights until leaving the target, and text drags remain untouched',()=>{
 const {zones,event}=setup(),zone=zones[0];
 zone.listeners.dragenter(event());zone.listeners.dragenter(event());zone.listeners.dragleave();
 assert.ok(zone.classes.has('photo-drag-over'));
 zone.listeners.dragleave();assert.equal(zone.classes.size,0);
 const text=event([],['text/plain']);zone.listeners.dragover(text);assert.equal(text.prevented,undefined);
});
test('single file drop and picker both load through the same validation',async()=>{
 const {context,zones,picker,event,photo,puts}=setup();
 await zones[1].listeners.drop(event([photo]));
 assert.equal(context.file,photo);assert.equal(context.input.originalUrl,'blob:photo');assert.equal(puts.length,1);
 picker.files=[photo];await picker.onchange();
 assert.equal(picker.value,'');assert.equal(puts.length,2);
});
test('multiple files, unsupported types and oversized images preserve the current photo',async()=>{
 const {context,zones,event,photo,errors}=setup();
 zones[0].listeners.drop(event([photo,photo]));
 await context.loadPhoto({...photo,type:'text/plain'});
 await context.loadPhoto({...photo,size:21*1024*1024});
 assert.equal(errors.length,3);assert.equal(context.input.id,'previous');assert.equal(context.file,null);
});
test('an unfinished request rejects another photo and releases its temporary preview',async()=>{
 const {context,photo,errors,revoked}=setup({originalSha:'different'});
 await context.loadPhoto(photo);
 assert.match(errors[0],/上次提交状态待恢复/);assert.equal(context.input.id,'previous');
 assert.deepEqual(revoked,['blob:photo']);
});
test('file drops outside targets prevent navigation and clear highlights without loading',()=>{
 const {context,zones,doc,event,photo}=setup();zones[0].listeners.dragenter(event());
 const drop=event([photo]);doc.listeners.drop(drop);
 assert.equal(drop.prevented,true);assert.equal(zones[0].classes.size,0);assert.equal(context.file,null);
});
