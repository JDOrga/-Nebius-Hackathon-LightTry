import {test} from 'node:test';
import assert from 'node:assert/strict';
import {WorkbenchPresence} from '../web/workbench-presence.js';
import {gpuNotice} from '../web/gpu-monitor.js';
import {readFileSync} from 'node:fs';
const flush=()=>new Promise(resolve=>setImmediate(resolve));
function fixture(){
 let now=0,next=0;const timers={jobs:new Map(),setTimeout(fn){this.jobs.set(++next,fn);return next;},clearTimeout(id){this.jobs.delete(id);},setInterval(){return ++next;},clearInterval(){}};
 const calls=[],states=[],readers=[];
 const fetchImpl=async(path,options)=>{
  calls.push({path,options});if(options.method==='POST')return {ok:true};
  const reader={waiting:null,read(){return new Promise(resolve=>{this.waiting=resolve;});},push(){this.waiting?.({done:false,value:new Uint8Array([1])});},async cancel(){this.waiting?.({done:true});}};
  readers.push(reader);options.signal.addEventListener('abort',()=>reader.cancel());
  return {ok:true,headers:{get:()=> 'text/event-stream'},body:{getReader:()=>reader}};
 };
 const presence=new WorkbenchPresence({token:()=> 'SYNTHETIC_CSRF',onState:s=>states.push(s),fetchImpl,timers,now:()=>now});
 return {presence,calls,states,readers,timers,setNow:v=>now=v};
}
test('persistent connection remains open without executing any page interval',async()=>{
 const f=fixture();f.presence.start();await flush();f.readers[0].push();await flush();
 f.setNow(600000); // A hidden page ran no heartbeat timers for ten minutes.
 assert(f.presence.connected);assert.equal(f.calls.filter(x=>x.path.includes('stream')).length,1);f.presence.stop();
});
test('foreground resume immediately posts heartbeat and replaces a stale connection',async()=>{
 const f=fixture();f.presence.start();await flush();f.readers[0].push();await flush();f.setNow(60000);
 const before=f.calls.length;f.presence.resume();await flush();
 assert(f.calls.slice(before).some(x=>x.options.method==='POST'));assert.equal(f.readers.length,2);f.presence.stop();
});
test('EOF reports lost connection; stop prevents reconnect and never starts GPU',async()=>{
 const f=fixture();f.presence.start();await flush();f.readers[0].waiting({done:true});await flush();
 assert(f.states.includes('lost'));f.presence.stop();await flush();assert.equal(f.timers.jobs.size,0);
 assert(f.calls.every(x=>['/api/gpu/presence','/api/gpu/presence-stream'].includes(x.path)));
 const notice=gpuNotice({clientConnection:'lost',state:'LOADING'});assert.match(notice.title,/断开/);assert.match(notice.text,/5分钟/);assert.match(notice.text,/不会自动开机/);
});
test('visibility, focus, online and bfcache recovery explicitly resume; hidden does not stop',()=>{
 const source=readFileSync(new URL('../web/workbench.js',import.meta.url),'utf8');
 for(const event of ['focus','online','pageshow'])assert(source.includes(`addEventListener('${event}',()=>workbenchPresence.resume())`));
 assert(source.includes("visibilitychange',()=>{if(!document.hidden)workbenchPresence.resume();}"));
 assert(source.includes("pagehide',()=>workbenchPresence.stop()"));
});
test('foreground heartbeat replaces a hung background POST immediately',async()=>{
 const f=fixture(),base=f.presence.fetchImpl;let posts=0;
 f.presence.fetchImpl=(path,options)=>{
  if(options.method==='POST'&&++posts===1)return new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>reject(Error('aborted'))));
  return base(path,options);
 };
 f.presence.start();await flush();f.readers[0].push();await flush();assert(f.presence.beatBusy);
 f.presence.resume();await flush();assert.equal(posts,2);assert.equal(f.presence.beatBusy,false);assert.equal(f.presence.connected,true);f.presence.stop();
});
