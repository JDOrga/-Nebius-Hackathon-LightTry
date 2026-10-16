// Submit once, then navigate. Server preflight/guard/start runs off the HTTP thread.
const button=document.getElementById('start-gpu');
button.addEventListener('click',async()=>{
 if(button.disabled)return;
 button.disabled=true;
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),5000);
 let message='GPU 启动请求尚未确认，请在工作台查看状态，不要重复启动。';
 try{
  const response=await fetch('/api/gpu/entry-start',{method:'POST',headers:{'Content-Type':'application/json','X-LightTry-Token':document.getElementById('gpu-entry').dataset.token},body:JSON.stringify({requestId:crypto.randomUUID().replaceAll('-','')}),signal:controller.signal});
  if(response.ok){const value=await response.json();message=value.status==='already_active'?'GPU 已处于活动状态。':value.status==='failed'?'GPU 启动未成功，仍可编辑方案。':'GPU 启动请求已提交，准备完成前可先编辑方案。';}
  else message='GPU 启动请求未被接受，你仍可以编辑方案。';
 }catch{ /* Unknown outcome is never retried automatically. */ }
 finally{clearTimeout(timer);try{sessionStorage.setItem('lighttry.gpuEntryNotice',message);}catch{}location.replace('/');}
});
