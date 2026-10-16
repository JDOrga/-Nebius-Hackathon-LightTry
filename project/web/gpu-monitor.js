// Display-only views. No fetch, control actions, inference POSTs or guessed timers.
const stageNames={environment_setup:'设置运行环境',module_import:'导入模型模块',argument_setup:'准备固定参数',
 model_config:'构建模型配置',network_setup:'构造网络与设备初始化',checkpoint_read:'读取主模型权重',
 parameter_apply:'应用模型参数',tokenizer_load:'加载编码器 / 解码器',cuda_synchronize:'等待 CUDA 完成',
 preload_total:'预加载',pipeline_init:'初始化 Pipeline',network_load:'加载主网络',device_move:'迁移至 GPU',
 tokenizer_setup:'构造编码器 / 解码器',tokenizer_checkpoint_read:'读取编码器 / 解码器权重'};
const stateNames={STOPPED:'已停止',STARTING:'正在启动',LOADING:'正在准备模型',READY:'模型已就绪',
 EXECUTING:'正在生成',STOPPING:'正在停止',UNKNOWN:'状态未知'};
const taskStages=['inverse','forward','validating','transferring'];
const taskNames={inverse:'分析照片',forward:'生成光照效果',validating:'校验生成结果',transferring:'取回生成结果'};
export function inferenceProgress(task){
 if(!task||task.status!=='running'||task.executionUncertain||task.progressStale||!taskStages.includes(task.stage))return null;
 const ordinal=taskStages.indexOf(task.stage)+1;
 return {stage:task.stage,ordinal,total:4,label:taskNames[task.stage],percent:null};
}
export function paintGenerationButton(button,task,{simulation=false}={}){
 const progress=inferenceProgress(task);
 for(const attr of ['role','aria-valuemin','aria-valuemax','aria-valuenow','aria-valuetext','aria-label'])button.removeAttribute(attr);
 button.classList.toggle('generation-progress',!!progress);button.removeAttribute('aria-busy');
 if(!progress){delete button.dataset.progressActive;
  if(task?.executionUncertain||task?.progressStale){button.textContent=task.progressStale?'进度暂不可用 · 待核实':'执行状态待核实';button.disabled=true;}
  else if(task&&['queued','running'].includes(task.status)){button.textContent=task.status==='queued'?'等待推理接收':'正在准备推理';button.disabled=true;}
  return;}
 button.dataset.progressActive='true';button.disabled=true;
 button.setAttribute('role','progressbar');button.setAttribute('aria-busy','true');
 const label=`${simulation?'模拟 · ':''}${progress.label} · 阶段 ${progress.ordinal}/${progress.total}`;
 button.setAttribute('aria-label',label);button.setAttribute('aria-valuetext',label+'，本阶段百分比未知');
 button.title='按已确认的服务端阶段更新，不是耗时百分比；不会重复提交';
 const fill=button.ownerDocument.createElement('span');fill.className='generation-progress-fill';fill.setAttribute('aria-hidden','true');
 const text=button.ownerDocument.createElement('span');text.className='generation-progress-label';text.textContent=label;
 const track=button.ownerDocument.createElement('span');track.className='generation-progress-track';track.setAttribute('aria-hidden','true');
 const done=button.ownerDocument.createElement('span');done.className='generation-progress-completed';done.style.width=`${(progress.ordinal-1)/progress.total*100}%`;
 const current=button.ownerDocument.createElement('span');current.className='generation-progress-current';current.style.left=done.style.width;current.style.width=`${100/progress.total}%`;
 track.append(done,current);button.replaceChildren(fill,text,track);
}
const finite=value=>typeof value==='number'&&Number.isFinite(value);
const time=value=>finite(value)&&value>0?new Date(value*1000).toLocaleString('zh-CN',{hour12:false}):'未记录';
const duration=value=>finite(value)?value<60000?`${(value/1000).toFixed(1)} 秒`:`${Math.floor(value/60000)} 分 ${Math.floor(value/1000)%60} 秒`:'未采集';
const size=value=>finite(value)?`${(value/1024**3).toFixed(2)} GiB`:'未采集';
const phaseNames={inverse:'Inverse · 照片分析模型',forward:'Forward · 光照生成模型'};
const phaseStates={loading:'加载中',ready:'已就绪',busy:'推理中',failed:'失败 / 已退出',unknown:'等待状态'};
export function consoleView(info={},now=Date.now()/1000){
 const monitor=info.monitor||{},worker=monitor.worker,host=monitor.host||{},deadlines=monitor.deadlines||{};
 const stale=info.stale===true||info.state==='UNKNOWN'||!finite(info.observedAt)||now-info.observedAt>60||now-info.observedAt< -5;
 const workerStale=stale||monitor.workerStale!==false;
 return {title:stale?'状态未知':stateNames[info.state]||'状态未知',stale,workerStale,
  message:info.message||'监控只读取当前快照；不会启动服务器或重新提交任务。',
  observed:info.observedAt?`最近观测 ${time(info.observedAt)}${finite(now-info.observedAt)?` · ${Math.max(0,Math.floor(now-info.observedAt))} 秒前`:''}`:'尚无可靠观测',
  model:workerStale?'未确认 / 快照过期':worker?.modelLoaded?'实际加载完成':worker?.modelState==='failed'?'加载失败':worker?.modelState==='loading'?'正在加载':'尚未就绪',
  budget:finite(info.budgetUsdIncludingTax)?`$${info.budgetUsdIncludingTax.toFixed(2)} 含税`:'未配置',
  details:[['会话',info.sessionId||'无活动会话'],['供应商状态',monitor.providerState||'UNKNOWN'],
   ['部署 / 连接',info.hostConfirmation?.stage||'未配置'],['本轮主机',host.vmId||'尚未取得'],['地址',host.ip||'尚未取得'],
   ['身份确认',monitor.hostConfirmed?'本轮已确认':'未确认，不继承旧信任'],
   ['可靠 RUNNING',time(deadlines.runningAt)],['启动等待截止',time(deadlines.startupDeadline)],
   ['工作截止',time(deadlines.workDeadline)],['停机目标',time(deadlines.stopDeadline)],
   ['核验目标',time(deadlines.verifyDeadline)],['绝对截止',time(deadlines.absoluteDeadline)],
   ['停止请求',monitor.stopRequested?'已提交（不等于释放）':'未提交'],
   ['资源释放',monitor.verifiedStopped&&monitor.instancesEmpty?'已确认 STOPPED + 空实例':'尚未确认'],
   ['管理保护',info.protectionMode==='cpu-only'?'CPU 同机管理；CPU 整机失效无独立兜底':'未报告'],
   ['GPU 利用率 / 显存 / 温度','未接入采集，不作估算']],
  phases:['inverse','forward'].map(phase=>{
   const item=worker?.loadingProgress?.phases?.find(p=>p.phase===phase);
   const completed=Array.isArray(item?.completedStages)?new Set(item.completedStages.filter(s=>Object.hasOwn(stageNames,s))).size:0;
   return {phase,title:phaseNames[phase],state:workerStale?'快照未确认':phaseStates[item?.state]||'等待采集',
    active:workerStale?'等待新的可靠观测':stageNames[item?.activeStage]|| (item?.state==='ready'?'已加载，等待任务':item?.state==='busy'?'执行当前任务':item?.state==='failed'?'加载失败；不会自动重载':'等待加载阶段记录'),
    completed:Math.min(9,completed),total:9,available:!!item&&!workerStale&&['loading','ready','busy','failed'].includes(item.state),
    elapsed:duration(item?.elapsedMs),cpu:duration(item?.cpuMs),read:size(item?.ioReadBytes),updated:time(item?.updatedAt)};
  })};
}
export function paintGpuConsole(document,info){
 const dialog=document.getElementById('gpu-console-dialog');if(!dialog)return;
 const view=consoleView(info),set=(id,value)=>{document.getElementById(id).textContent=value;};
 dialog.dataset.state=view.stale?'UNKNOWN':info.state||'UNKNOWN';
 set('gpu-console-state',view.title);set('gpu-console-message',view.message);
 set('gpu-console-observed',(view.stale?'状态不可靠 · ':'')+view.observed);
 set('gpu-console-model',view.model);set('gpu-console-budget',view.budget);
 set('gpu-console-mode',info.simulation?'离线演示 · 非真实 GPU':'只读监控 · 不触发启动或推理');
 const details=document.getElementById('gpu-console-details');details.replaceChildren();
 for(const [label,value] of view.details){const dt=document.createElement('dt'),dd=document.createElement('dd');
  dt.textContent=label;dd.textContent=value;details.append(dt,dd);}
 for(const phase of view.phases){
  const key=phase.phase;
  set(`gpu-load-${key}-state`,phase.state);set(`gpu-load-${key}-stage`,phase.active);
  set(`gpu-load-${key}-count`,phase.available?`已完成 ${phase.completed}/${phase.total} 个观测阶段`:'暂无可靠的加载进度');
  const bar=document.getElementById(`gpu-load-${key}-progress`);
  if(phase.available){bar.value=phase.completed;bar.max=phase.total;}else bar.removeAttribute('value');
  bar.setAttribute('aria-label',`${phase.title}，${phase.completed}/${phase.total} 个观测阶段，非耗时比例`);
  set(`gpu-load-${key}-metrics`,`累计主机耗时 ${phase.elapsed} · CPU ${phase.cpu} · 读盘 ${phase.read}`);
  set(`gpu-load-${key}-updated`,'阶段记录更新 '+phase.updated);
 }
}
