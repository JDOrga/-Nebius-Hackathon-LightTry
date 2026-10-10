import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createState, reduce, selection, recordedRegion, validateFile, validateDimensions, fitSize, previewLayout } from '../web/state.js';
import { disconnectedInference, serviceInference, recoverTask } from '../web/sources.js';
const catalog = JSON.parse(readFileSync(new URL('../data/catalog.json', import.meta.url), 'utf8'));

test('batch switching binds each result, third preset never inherits, and stale responses are ignored',()=>{
  const id='a'.repeat(32),input={id:'photo',url:`/api/tasks/${id}/input`,width:1280,height:704,canvas:{width:1280,height:704,validRegion:[100,0,900,704]}};
  const items=Object.fromEntries(catalog.presets.slice(0,2).map(p=>[p.id,{preset:p,status:'succeeded',error:null,result:{taskId:id,inputId:input.id,presetId:p.id,url:`/${p.id}`,downloadUrl:`/${p.id}/full`,regionUrl:`/${p.id}/region`,regionDownloadUrl:`/${p.id}/png`}}]));
  const task={taskId:id,input,preset:catalog.presets[0],presetResults:items,status:'succeeded',updatedAt:20};
  let state=reduce(createState(catalog),{type:'RESTORE_TASK',task});
  state=reduce(state,{type:'PRESET',id:'sunrise'});assert.equal(selection(state,catalog).result.url,'/sunrise');
  state=reduce(state,{type:'REGION',value:'photo'});assert.equal(selection(state,catalog).exportUrl,'/sunrise/png');
  assert.equal(selection(state,catalog).input.width,800);
  state=reduce(state,{type:'PRESET',id:'street'});assert.equal(selection(state,catalog).result,null);
  assert.equal(reduce(state,{type:'TASK',task:{...task,updatedAt:10,status:'running'}}),state);
  assert.equal(reduce(state,{type:'TASK',task:{...task,input:{...input,id:'old'}}}),state);
  const failed={...task,presetResults:{...items,sunrise:{...items.sunrise,status:'failed',result:null}}};
  state=reduce(state,{type:'TASK',task:failed});state=reduce(state,{type:'PRESET',id:'sunrise'});
  assert.equal(selection(state,catalog).exportUrl,null);
});

test('one batch adapter request with frozen deduplicated preset list',async()=>{
  const original=global.fetch;const calls=[];
  try{
    global.fetch=async(url,options)=>{calls.push({url,options});return {ok:true,json:async()=>({taskId:'batch'})};};
    await serviceInference.submit({id:'one',name:'photo'},[catalog.presets[0],catalog.presets[1],catalog.presets[0]],{type:'image/png'},'req');
    assert.equal(calls.length,1);
    const metadata=JSON.parse(Buffer.from(calls[0].options.headers['X-LightTry-Request'],'base64').toString());
    assert.deepEqual(metadata.presetIds,['sunny','sunrise']);
  }finally{global.fetch=original;}
});

test('restored success survives selecting current mode and regions share one rectangle', () => {
  const input={id:'one',name:'cup.png',width:1280,height:704,url:'/input',canvas:{width:1280,height:704,validRegion:[442,0,838,704]}};
  const task={taskId:'a'.repeat(32),input,preset:catalog.presets[0],status:'succeeded',result:{taskId:'a'.repeat(32),inputId:'one',presetId:'sunny',width:1280,height:704,url:'/result',downloadUrl:'/download'}};
  let state=reduce(createState(catalog),{type:'RESTORE_TASK',task});
  assert.equal(reduce(state,{type:'MODE',mode:'generate'}),state);
  state=reduce(state,{type:'REGION',value:'photo'});
  const photo=selection(state,catalog);
  assert.deepEqual([photo.input.width,photo.input.height],[396,704]);
  assert.deepEqual([photo.result.width,photo.result.height],[396,704]);
  assert.match(photo.input.url,/input-region$/);assert.match(photo.result.url,/result-region$/);assert.match(photo.exportUrl,/download-region$/);
  state=reduce(state,{type:'REGION',value:'full'});assert.equal(selection(state,catalog).exportUrl,'/download');
  assert.equal(recordedRegion({...input,canvas:{...input.canvas,validRegion:[0,0,1281,704]}}),null);
  assert.equal(recordedRegion({...input,canvas:null}),null);
});

test('automatic recovery retries transient reads only and drops stale replies', async () => {
  const original=serviceInference.getTask;
  const delays=[];let calls=0,current=true;
  const task={taskId:'a'.repeat(32),status:'succeeded'};
  try {
    serviceInference.getTask=async()=>{calls++;if(calls<3)throw new Error('temporary read');return task;};
    assert.equal(await recoverTask(task.taskId,()=>current,async ms=>delays.push(ms)),task);
    assert.equal(calls,3);assert.deepEqual(delays,[1000,2000]);
    calls=0;serviceInference.getTask=async()=>{calls++;const e=new Error('missing');e.code='TASK_NOT_FOUND';throw e;};
    await assert.rejects(recoverTask(task.taskId,()=>current,async()=>{}),/missing/);assert.equal(calls,1);
    serviceInference.getTask=async()=>{current=false;return task;};
    assert.equal(await recoverTask(task.taskId,()=>current,async()=>{}),null);
  } finally {serviceInference.getTask=original;}
});

test('only matching current task success exposes a real download and expires cleanly', () => {
  const input = {id:'new-input',name:'new.png',kind:'upload',width:1280,height:704,url:'/input'};
  let state = reduce(createState(catalog), {type:'UPLOAD',input});
  const task = {taskId:'current-task',input,preset:catalog.presets[0],status:'running',result:null};
  state = reduce(state,{type:'TASK',task});
  for (const status of ['queued','running','failed','expired','not_connected']) {
    const next = reduce(state,{type:'TASK',task:{...task,status}});
    assert.equal(selection(next,catalog).result,null);
    assert.equal(selection(next,catalog).exportUrl,null);
  }
  const result = {taskId:task.taskId,inputId:input.id,presetId:task.preset.id,url:'/current-result',downloadUrl:'/current-download'};
  state = reduce(state,{type:'TASK',task:{...task,status:'succeeded',result}});
  assert.equal(selection(state,catalog).exportUrl,'/current-download');
  for (const key of ['taskId','inputId','presetId']) {
    const wrong = {...result,[key]:'previous-task'};
    assert.equal(selection({...state,task:{...state.task,result:wrong}},catalog).result,null);
  }
  state = reduce(state,{type:'TASK',task:{...task,status:'expired',result:null}});
  assert.equal(selection(state,catalog).exportUrl,null);
});

test('late tasks cannot replace current input, preset or task; restore is explicit', () => {
  const input = {id:'new',kind:'upload',name:'new.png',url:'/input',width:1280,height:704};
  let state=reduce(createState(catalog),{type:'UPLOAD',input});
  const task={taskId:'one',input,preset:catalog.presets[0],status:'running',result:null};
  state=reduce(state,{type:'TASK',task});
  for (const bad of [{...task,input:{...input,id:'old'}},{...task,preset:catalog.presets[1]},{...task,taskId:'old'}]) {
    assert.equal(reduce(state,{type:'TASK',task:bad}),state);
  }
  const sample=reduce(state,{type:'MODE',mode:'sample'});
  assert.equal(reduce(sample,{type:'TASK',task}),sample);
  const restored=reduce(sample,{type:'RESTORE_TASK',task});
  assert.equal(restored.mode,'generate');assert.equal(restored.upload.id,'new');
  assert.equal(selection(restored,catalog).sample,null);
});

test('HTTP adapter sends file and IDs, preserves task contract and safe errors', async () => {
  const realFetch=globalThis.fetch;
  const calls=[];
  globalThis.fetch=async (url,options) => {
    calls.push({url,options});
    return {ok:true,json:async()=>url==='/api/inference'?{enabled:true,csrfToken:'local-token'}:{taskId:'a'.repeat(32),status:'queued'}};
  };
  try {
    await serviceInference.capabilities();
    const file=new Blob(['synthetic'],{type:'image/png'});
    await serviceInference.submit({id:'b'.repeat(32),name:'中文照片.png'},catalog.presets[0],file,'c'.repeat(32));
    const submit=calls[1];assert.equal(submit.url,'/api/tasks');assert.equal(submit.options.body,file);
    assert.equal(submit.options.headers['X-LightTry-Token'],'local-token');
    const meta=JSON.parse(Buffer.from(submit.options.headers['X-LightTry-Request'],'base64').toString('utf8'));
    assert.equal(meta.name,'中文照片.png');assert.equal(meta.presetId,'sunny');
    assert.equal(Object.keys(meta).sort().join(','),'inputId,name,presetId,requestId');
    await serviceInference.getTask('a'.repeat(32));
    await assert.rejects(serviceInference.getTask('../private'));
    globalThis.fetch=async()=>({ok:false,json:async()=>({error:{code:'TASK_BUSY',message:'任务正在执行'}})});
    await assert.rejects(serviceInference.submit(meta,catalog.presets[0],file,'c'.repeat(32)),/任务正在执行/);
  } finally {globalThis.fetch=realFetch;}
});

test('each sample selects its own three forward results and exact HDR mapping', () => {
  assert.deepEqual(catalog.presets.map(p => [p.id, p.hdr, p.index]), [
    ['sunny', 'sunny_vondelpark_2k.hdr', 0], ['sunrise', 'pink_sunrise_2k.hdr', 1], ['street', 'street_lamp_2k.hdr', 2],
  ]);
  for (const sample of catalog.samples) for (const preset of catalog.presets) {
    const state = reduce(reduce(createState(catalog), { type: 'SAMPLE', id: sample.id }), { type: 'PRESET', id: preset.id });
    const selected = selection(state, catalog);
    if (!sample.results[preset.id]) { assert.equal(selected.result, undefined); continue; }
    assert.equal(selected.result.assetId, `${sample.id}-${preset.id}`);
    assert.equal(selected.input.assetId, `${sample.id}-input`);
    assert.equal(selected.exportUrl, `/download/${sample.id}/${preset.id}`);
    assert.equal(catalog.assets[selected.result.assetId].path, `results/${sample.id}-${preset.id}.jpg`);
    assert.equal(catalog.assets[selected.result.assetId].sha256, selected.result.sha256);
  }
});
test('new upload cannot inherit sample results, even after selecting a preset', () => {
  let state = createState(catalog);
  state = reduce(state, { type: 'UPLOAD_START' });
  assert.equal(selection(state, catalog).input, null);
  assert.equal(selection(state, catalog).result, null);
  const input = { id: 'my-image', url: 'blob:local', width: 900, height: 1200, kind: 'upload' };
  state = reduce(state, { type: 'UPLOAD', input });
  state = reduce(state, { type: 'PRESET', id: 'street' });
  assert.equal(selection(state, catalog).input, input);
  assert.equal(selection(state, catalog).sample, null);
  assert.equal(selection(state, catalog).result, null);
  assert.equal(selection(state, catalog).exportUrl, null);
});

test('same photo remembers generated presets without relabeling a result or submitting', () => {
  const input = { id: 'same-photo', width: 1280, height: 704, url: '/input' };
  const makeTask = (preset, taskId) => ({ taskId, input, preset, status: 'succeeded', expiresAt: Date.now() / 1000 + 60,
    result: { taskId, inputId: input.id, presetId: preset.id, url: '/' + preset.id, downloadUrl: '/download/' + preset.id } });
  const sunny = makeTask(catalog.presets[0], 'sunny-task'), sunrise = makeTask(catalog.presets[1], 'sunrise-task');
  let state = reduce(createState(catalog), { type: 'RESTORE_TASK', task: sunny });
  state = reduce(state, { type: 'PRESET', id: 'sunrise' });
  assert.equal(selection(state, catalog).result, null);
  assert.equal(selection(state, catalog).exportUrl, null);
  state = reduce(state, { type: 'TASK', task: sunrise });
  state = reduce(state, { type: 'PRESET', id: 'sunny' });
  assert.equal(selection(state, catalog).result.taskId, sunny.taskId);
  assert.equal(selection(state, catalog).exportUrl, '/download/sunny');
  state = reduce(state, { type: 'PRESET', id: 'street' });
  assert.equal(selection(state, catalog).result, null);
  // Refresh restoration can collect only same-input tasks, through read-only GETs.
  state = reduce(createState(catalog), { type: 'RESTORE_TASK', task: sunrise });
  state = reduce(state, { type: 'RELATED_TASK', task: sunny });
  state = reduce(state, { type: 'RELATED_TASK', task: { ...sunny, input: { ...input, id: 'different-photo' } } });
  state = reduce(state, { type: 'PRESET', id: 'sunny' });
  assert.equal(selection(state, catalog).result.taskId, sunny.taskId);
  state = reduce(state, { type: 'UPLOAD', input: { ...input, id: 'new-photo' } });
  assert.equal(selection(state, catalog).result, null);
  assert.deepEqual(state.tasks, {});
});

test('expired remembered preset and failed preset never expose prior downloads', () => {
  const input = { id: 'own', width: 1280, height: 704 };
  const task = { taskId: 'own-task', input, preset: catalog.presets[0], status: 'succeeded', expiresAt: 1,
    result: { taskId: 'own-task', inputId: 'own', presetId: 'sunny', url: '/result', downloadUrl: '/download' } };
  let state = reduce(createState(catalog), { type: 'RESTORE_TASK', task });
  assert.equal(selection(state, catalog).result, null);
  state = reduce(state, { type: 'TASK', task: { ...task, status: 'failed', result: null } });
  state = reduce(state, { type: 'PRESET', id: 'sunrise' });
  state = reduce(state, { type: 'PRESET', id: 'sunny' });
  assert.equal(selection(state, catalog).exportUrl, null);
});

test('ungenerated disconnected preset crops only the previous real input, never local task ID', () => {
  const id = 'a'.repeat(32);
  const input = { id:'cup',width:1280,height:704,url:`/api/tasks/${id}/input`,
    canvas:{width:1280,height:704,validRegion:[442,0,838,704]} };
  const task = {taskId:id,input,preset:catalog.presets[0],status:'succeeded',
    result:{taskId:id,inputId:'cup',presetId:'sunny',url:`/api/tasks/${id}/result`}};
  let state = reduce(createState(catalog),{type:'RESTORE_TASK',task});
  state = reduce(state,{type:'REGION',value:'photo'});
  state = reduce(state,{type:'PRESET',id:'sunrise'});
  assert.equal(selection(state,catalog).input.url,`/api/tasks/${id}/input-region`);
  state = reduce(state,{type:'TASK',task:{taskId:'local-uuid',input,preset:catalog.presets[1],status:'not_connected',result:null}});
  assert.equal(selection(state,catalog).input.url,`/api/tasks/${id}/input-region`);
  assert.equal(selection(state,catalog).input.width,396);
  assert.equal(selection(state,catalog).result,null);
  assert.equal(selection(state,catalog).exportUrl,null);
});
test('disconnected adapter produces a real local task identity without result or progress', async () => {
  const task = await disconnectedInference.submit({ id: 'upload' }, catalog.presets[0]);
  assert.match(task.taskId, /^local-/);
  assert.equal(task.status, 'not_connected');
  assert.equal(task.result, null);
  assert.equal(task.error.code, 'SERVICE_NOT_CONNECTED');
  assert.equal(task.error.message, '已载入，尚未连接推理服务');
  assert.equal(task.progress, undefined);
});
test('preset and comparison switches preserve zoom, pan and split; fit restores complete frame', () => {
  let state = reduce(createState(catalog), { type: 'VIEW', value: { zoom: 2, panX: .2, panY: -.1, split: 77 } });
  const view = state.view;
  state = reduce(state, { type: 'PRESET', id: 'sunrise' });
  state = reduce(state, { type: 'COMPARE', value: 'side' });
  assert.deepEqual(state.view, view);
  state = reduce(state, { type: 'FIT' });
  assert.deepEqual(state.view, { zoom: 1, panX: 0, panY: 0, split: 77 });
  state = reduce(state, { type: 'SAMPLE', id: catalog.samples[2].id });
  assert.equal(state.view.split, 50);
});
test('sample and real modes are explicit; switching back restores only sample identity', () => {
  let state = reduce(createState(catalog), { type: 'UPLOAD', input: { id: 'own' } });
  state = reduce(state, { type: 'TASK', task: { status: 'not_connected' } });
  state = reduce(state, { type: 'MODE', mode: 'sample' });
  assert.equal(state.task, null);
  assert.equal(selection(state, catalog).input.assetId, catalog.samples.find(s=>s.id===(catalog.preferredSample || catalog.samples[0].id)).input.assetId);
  state = reduce(state, { type: 'MODE', mode: 'generate' });
  assert.equal(selection(state, catalog).input.id, 'own');
  assert.equal(selection(state, catalog).result, null);
});
test('format, empty, oversized, too-small and oversized pixel inputs have clear errors', () => {
  assert.equal(validateFile({ type: 'image/png', size: 2048 }), null);
  assert.match(validateFile({ type: 'image/gif', size: 2048 }), /格式不支持/);
  assert.match(validateFile({ type: 'image/png', size: 0 }), /文件为空/);
  assert.match(validateFile({ type: 'image/jpeg', size: 20 * 1024 * 1024 + 1 }), /20 MB/);
  assert.match(validateDimensions(10, 100), /图片太小/);
  assert.match(validateDimensions(9000, 9000), /尺寸过大/);
  assert.equal(validateDimensions(900, 1200), null);
});
test('fit preserves image aspect ratio in large and narrow panels without cropping', () => {
  for (const dims of [[1000, 600], [175, 245], [360, 240]]) {
    const fitted = fitSize(1280, 704, ...dims);
    assert.ok(Math.abs(fitted.width / fitted.height - 1280 / 704) < 1e-10);
    assert.ok(fitted.width <= dims[0] + .00001 && fitted.height <= dims[1] + .00001);
  }
});
test('side comparison fills two wide panels or two stacked narrow panels with complete canvases', () => {
  for (const width of [300, 390, 639, 640, 833, 1200]) {
    const side = previewLayout('side', width);
    const panelWidth = side.stacked ? width : (width - 1) / 2;
    const panelHeight = side.stacked ? (side.height - 1) / 2 : side.height;
    const fitted = fitSize(1280, 704, panelWidth, panelHeight);
    assert.ok(Math.abs(fitted.width - panelWidth) < .00001);
    assert.ok(Math.abs(fitted.height - panelHeight) < .00001);
    assert.equal(side.stacked, width < 640);
    if (width >= 640) assert.ok(side.height < previewLayout('slider', width).height);
  }
});

test('historical mug region uses recorded assets and never lends third light a result', () => {
 let state=createState(catalog); state=reduce(state,{type:'REGION',value:'photo'});
 for(const id of ['sunny','sunrise']) { state=reduce(state,{type:'PRESET',id}); const v=selection(state,catalog); assert.equal(v.result.width,396); assert.equal(v.input.height,704); assert.equal(v.exportUrl,`/download/05_white_blue_mug/${id}-region`); }
 state=reduce(state,{type:'PRESET',id:'street'}); assert.equal(selection(state,catalog).result,undefined); assert.equal(selection(state,catalog).exportUrl,null);
});
