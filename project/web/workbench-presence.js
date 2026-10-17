// Connection liveness is independent of background JavaScript timers.
// The server's open streaming socket keeps presence alive. No GPU mutations.
export class WorkbenchPresence{
 constructor({token,onState=()=>{},fetchImpl=(...a)=>fetch(...a),timers=globalThis,now=()=>Date.now()}){
  Object.assign(this,{token,onState,fetchImpl,timers,now});this.epoch=0;this.beatSerial=0;this.stopped=true;this.connected=false;this.beatBusy=false;this.lastFrame=0;
 }
 state(value){this.connected=value==='connected';this.onState(value);}
 start(){
  if(!this.stopped)return;
  this.stopped=false;this.connect();this.beat();this.beatTimer=this.timers.setInterval(()=>this.beat(),15000);
 }
 stop(){
  this.stopped=true;this.epoch++;this.beatSerial++;this.controller?.abort();this.beatController?.abort();this.beatBusy=false;this.timers.clearTimeout(this.retry);this.timers.clearTimeout(this.watchdog);this.timers.clearInterval(this.beatTimer);this.connected=false;
 }
 async beat(force=false){
  if(this.stopped||(!force&&this.beatBusy)||!this.token())return;
  if(force)this.beatController?.abort();
  const serial=++this.beatSerial;
  this.beatBusy=true;const controller=new AbortController(),timer=this.timers.setTimeout(()=>controller.abort(),8000);this.beatController=controller;
  try{const r=await this.fetchImpl('/api/gpu/presence',{method:'POST',headers:{'X-LightTry-Token':this.token()},signal:controller.signal});if(!r.ok&&!this.connected)this.onState('lost');}
  catch{if(serial===this.beatSerial&&!this.connected&&!this.stopped)this.onState('lost');}
  finally{this.timers.clearTimeout(timer);if(serial===this.beatSerial)this.beatBusy=false;}
 }
 resume(){
  if(this.stopped){this.start();return;}
  this.beat(true);
  if(!this.connected||this.now()-this.lastFrame>30000){this.controller?.abort();this.connect();}
 }
 async connect(){
  if(this.stopped)return;
  const epoch=++this.epoch;this.timers.clearTimeout(this.retry);this.timers.clearTimeout(this.watchdog);
  this.controller?.abort();const controller=new AbortController();this.controller=controller;
  const arm=ms=>{this.timers.clearTimeout(this.watchdog);this.watchdog=this.timers.setTimeout(()=>controller.abort(),ms);};
  try{
   if(!this.token())throw Error('not_ready');
   arm(10000);
   const response=await this.fetchImpl('/api/gpu/presence-stream',{headers:{'X-LightTry-Token':this.token()},signal:controller.signal,cache:'no-store'});
   if(!response.ok||!response.headers.get('Content-Type')?.includes('text/event-stream')||!response.body)throw Error('stream_unavailable');
   const reader=response.body.getReader();
   try{
    while(!this.stopped&&epoch===this.epoch){
     const {done,value}=await reader.read();if(done)throw Error('stream_closed');
     if(epoch!==this.epoch)return;
     if(value?.length){this.lastFrame=this.now();this.state('connected');arm(30000);}
    }
   }finally{try{await reader.cancel();}catch{}}
  }catch{if(!this.stopped&&epoch===this.epoch&&this.token())this.state('lost');}
  finally{
   if(epoch===this.epoch){this.timers.clearTimeout(this.watchdog);controller.abort();
    if(!this.stopped)this.retry=this.timers.setTimeout(()=>this.connect(),3000);
   }
  }
 }
}
