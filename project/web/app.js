import { createState, reduce, selection, currentTask, recordedRegion, validateFile, validateDimensions, fitSize, previewLayout } from './state.js';
import { sampleSource, disconnectedInference, serviceInference, recoverTask, decodeUpload } from './sources.js';

const $ = id => document.getElementById(id);
const escape = value => String(value).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
let catalog, state, renderVersion = 0, uploadVersion = 0, renderedResult = null;
let capabilities = { enabled: false }, uploadFile = null, pending = false, pollVersion = 0;
let requestId = null, restoring = false, fileSelectionRequested = false;
const savedTaskKey = 'lighttry.lastTask';
const requestKey = 'lighttry.pendingRequest';
const relatedKey = 'lighttry.relatedTasks';
const viewedKey = 'lighttry.viewedPreset';
const active = () => restoring || pending || ['queued', 'running'].includes(state?.task?.status) || state?.task?.executionUncertain;
const storageGet = key => { try { return localStorage.getItem(key); } catch { return null; } };
const storageSet = (key, value) => { try { value === null ? localStorage.removeItem(key) : localStorage.setItem(key, value); } catch {} };
const surface = $('preview-surface');

function dispatch(event) {
  state = reduce(state, event);
  if (['TASK', 'RESTORE_TASK', 'RELATED_TASK'].includes(event.type) && state.upload) {
    storageSet(relatedKey, JSON.stringify({ inputId: state.upload.id,
      taskIds: Object.values(state.tasks || {}).filter(t => /^[0-9a-f]{32}$/.test(t.taskId)).map(t => t.taskId) }));
  }
  if (['VIEW', 'FIT'].includes(event.type)) return applyView();
  if (event.type === 'ERROR') return renderStatus();
  render();
}

function renderStatus() {
  const generate = state.mode === 'generate';
  $('upload-error').hidden = !state.error;
  $('upload-error').textContent = state.error || '';
  $('upload-status').hidden = !generate;
  $('upload-status').replaceChildren();
  const title = document.createElement('strong');
  const task = currentTask(state);
  const titles = { queued: '已提交，等待此灯光完成记录', running: '该灯光正在执行', succeeded: '本次光照结果已通过校验',
    failed: '该灯光失败', expired: '结果已过期', pending: '该灯光尚未完成', partial: '部分灯光完成', not_connected: '已载入，尚未连接推理服务' };
  title.textContent = restoring ? '正在恢复上次任务…' : pending ? '正在提交本次任务…' : task ? titles[task.status] || '任务状态待核实' :
    state.upload ? capabilities.enabled ? '照片已载入，选择预设后提交' : '已载入，尚未连接推理服务' : '载入照片，在本机预览';
  if(state.task?.status==='running' && !pending && !restoring) title.textContent='批次正在执行；各灯光完成状态待取回确认';
  const detail = document.createElement('span');
  const stages = { preflight: '执行端正在检查现有环境', weights: '执行端正在校验现有权重', inverse: '执行端正在运行光照分解',
    forward: '执行端正在运行所选光照', validating: '执行端正在校验输出', transferring: '正在取回本次结果' };
  detail.textContent = task?.status === 'not_connected' ? (Object.keys(state.tasks || {}).length ? '此灯光尚未生成；连接并授权后仍需显式提交。真实推理默认关闭，不发送照片。' : '当前仅显示你的原图。真实推理默认关闭，不发送照片。') : task?.error?.message || (task?.status === 'running' ? stages[task.stage] || '等待执行端报告阶段，不推测百分比。' :
    task?.status === 'queued' ? '刷新后可恢复查询。没有执行端事件时不显示进度。' :
    task?.status === 'succeeded' ? (task.result?.inverseReuse?.reused ? '本次复用了已校验的 G-buffer。' : '') + '可比较和下载；新灯光仍需显式生成，模型退出后需重新加载 forward。视觉质量仍需你检查。' :
    state.upload ? capabilities.enabled ? '此灯光尚未生成；请显式提交。符合条件时复用 G-buffer；模型退出后仍需加载 forward，不承诺秒切。' : '当前仅显示你的原图。真实推理默认关闭，不发送照片。' : '选择一张 JPG、PNG 或 WebP。');
  if (capabilities.enabled && state.upload && !uploadFile && !task) detail.textContent = '刷新后原始文件不在浏览器内，请重新载入照片再提交新任务。';
  if(!task && state.upload && state.task?.presetResults) detail.textContent='此灯光尚未生成；勾选仅准备，必须点击生成按钮显式提交。默认未连接时不能提交，不发送照片。';
  if(state.task?.status==='running') detail.textContent=(stages[state.task.stage] || '等待执行端报告阶段。')+' 整批结束取回后确认各灯光结果，不根据经过时间推测完成。';
  $('upload-status').append(title, detail);
  if (capabilities.developmentTestMode) {
    const badge = document.createElement('strong'); badge.textContent = '离线测试替身 · 非 GPU 结果';
    $('upload-status').prepend(badge);
  }
  $('submit-task').hidden = !generate;
  const plannedAlreadyComplete=state.plannedPresets.length>0 && state.plannedPresets.every(id=>state.task?.presetResults?.[id]?.status==='succeeded');
  $('submit-task').disabled = !capabilities.enabled || !state.upload || !uploadFile || active() || !state.plannedPresets.length || plannedAlreadyComplete;
  $('submit-task').textContent = `生成勾选的 ${state.plannedPresets.length} 种灯光（提交一批）`;
  $('batch-plan').hidden = !generate;
  $('batch-options').innerHTML = catalog.presets.map(p=>`<label><input type="checkbox" data-plan="${escape(p.id)}" ${state.plannedPresets.includes(p.id)?'checked':''} ${active()?'disabled':''}> ${escape(p.name)}</label>`).join('');
  if (state.task?.presetResults) {
    const summary = document.createElement('span');
    summary.textContent = '批次：'+Object.values(state.task.presetResults).map(i=>`${i.preset.name}：${titles[i.status] || i.status}`).join('；') + '。整批结束并取回校验后可显示；未完成项不会自动重试。';
    $('upload-status').append(summary);
    const provenance = task?.result?.source;
    if (provenance) {
      const source=document.createElement('span');
      source.textContent=`来源任务 ${provenance.taskId} · run ${provenance.runId} · 实际生成 ${new Date(task.result.generatedAt*1000).toLocaleString()}${state.task.registeredAt?' · 已登记历史真实结果':''}`;
      $('upload-status').append(source);
    }
  }
  $('cancel-task').hidden = !generate || !['queued', 'running'].includes(task?.status);
  $('restore-task').hidden = !storageGet(savedTaskKey) || storageGet(savedTaskKey) === task?.taskId;
  $('view-upload-original').hidden = !generate || !state.upload;
  $('sample-mode').disabled = $('generate-mode').disabled = !!active();
  // Keep the displayed selection bound to the submitted task until it ends.
  document.querySelectorAll('[data-preset]').forEach(button => { button.disabled = false; });
}

async function render() {
  const version = ++renderVersion;
  const { sample, preset, input, result } = selection(state, catalog);
  const generate = state.mode === 'generate';
  const hasResult = !!result;
  const originalOnly = generate && !hasResult;
  const regionAvailable = generate && !!recordedRegion(state.upload);
  const cropped = regionAvailable && state.region === 'photo';
  $('region-controls').hidden = !regionAvailable;
  document.querySelectorAll('[data-region]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.region === (cropped ? 'photo' : 'full'))));
  const displayName = sample?.name || input?.name || '照片';
  renderedResult = null;
  $('export').disabled = true;
  $('sample-mode').setAttribute('aria-pressed', String(!generate));
  $('generate-mode').setAttribute('aria-pressed', String(generate));
  $('samples-panel').hidden = generate;
  $('source-label').textContent = generate ? '我的照片 · ' + (hasResult ? state.task?.registeredAt ? '已登记历史真实结果' : '本次结果' : '本机预览') : '样例演示 · 历史实测';
  $('image-title').textContent = generate ? `${input?.name || '载入你的产品照片'} / ${preset.name}` : `${sample.name} / ${preset.name}`;
  $('image-size').textContent = input ? `${input.width} × ${input.height} px` : '';
  $('canvas-note').textContent = cropped ? '原照片区域 · 输入与结果按同一记录裁剪 · 不修复生成伪影' : generate && !state.task?.input?.canvas ? '本机原图预览 · 等比显示' : '完整画布 · 等比显示 · 保留灰色留白';
  $('sample-warning').hidden = !sample?.unstable;
  $('sample-warning').textContent = sample?.warning || '';
  $('export').textContent = cropped ? '↓ 下载原照片区域 PNG' : '↓ 下载完整光照结果 JPEG';
  $('export-note').textContent = originalOnly ? '尚无此灯光有效结果，不能下载光照结果' : cropped ? '按记录裁剪 · 不再增加有损编码，不恢复 JPEG 已丢失信息' : '下载校验后的实际 JPEG 原字节，保留完整画布';
  $('hdr-note').textContent = `环境文件：${preset.hdr}`;
  $('compact-light-label').textContent = generate ? '目标光照' : '光照方案';
  $('compact-preset-list').innerHTML = catalog.presets.map(p => `<button class="compact-preset" data-preset="${escape(p.id)}" aria-pressed="${p.id === preset.id}" aria-label="${escape(p.name)}">${escape(p.name)}</button>`).join('');
  surface.dataset.mode = originalOnly ? 'original' : state.comparison;
  surface.dataset.width = input?.width || 1280;
  surface.dataset.height = input?.height || 704;
  document.querySelectorAll('[data-comparison]').forEach(button => {
    button.disabled = originalOnly && button.dataset.comparison !== 'original';
    button.setAttribute('aria-pressed', String(button.dataset.comparison === (originalOnly ? 'original' : state.comparison)));
  });
  $('slider-controls').hidden = originalOnly || state.comparison !== 'slider';
  $('preset-list').innerHTML = catalog.presets.map(p => {
    const thumbnail = generate ? `<span class="environment environment-${p.id}" aria-hidden="true">☼</span>` : `<img src="${sample.results[p.id].url}" alt="">`;
    return `<button class="preset" data-preset="${escape(p.id)}" aria-pressed="${p.id === preset.id}" aria-label="${escape(p.name)}">${thumbnail}<span><strong>${escape(p.name)}</strong><small>${escape(p.description)}</small></span>${p.id === preset.id ? '<span class="tick" aria-hidden="true">✓</span>' : ''}</button>`;
  }).join('');
  $('sample-list').innerHTML = catalog.samples.map(s => `<button class="sample-button ${s.unstable ? 'unstable' : ''}" data-sample="${escape(s.id)}" aria-pressed="${s.id === state.sampleId}" aria-label="${escape(s.name)}${s.unstable ? '，效果不稳定' : ''}"><img src="${s.original.url}" alt=""><span>${escape(s.name)}</span></button>`).join('');
  renderStatus();
  if (!input) {
    surface.innerHTML = '<div class="empty"><span class="empty-icon">↥</span><h3>载入照片预览</h3><p>选择或拖入一张图片。<br>提交前只在本机显示。</p></div>';
    applyView();
    return;
  }
  surface.innerHTML = '<div class="empty"><p>读取本地图片…</p></div>';
  applyView();
  try {
    // Decode both identities before showing either, so a rapid switch never pairs an old result with a new input.
    await Promise.all([input, ...(result ? [result] : [])].map(async record => {
      const image = new Image(); image.src = record.url; await image.decode();
      if (image.naturalWidth !== record.width || image.naturalHeight !== record.height) throw new Error('图片尺寸与样例记录不一致，请检查素材。');
    }));
    if (version !== renderVersion) return;
    const img = (record, label, cls = '') => `<img class="${cls}" src="${escape(record.url)}" alt="${escape(label)}" draggable="false">`;
    const mode = originalOnly ? 'original' : state.comparison;
    const originalLabel = generate ? state.task?.input?.canvas ? '实际模型输入' : '载入原图' : '原图 · 等比适配';
    surface.dataset.mode = mode;
    if (mode === 'side') {
      surface.innerHTML = `<div class="view-panel"><span class="image-tag left">${originalLabel}</span><div class="image-canvas">${img(input, `${displayName}实际输入`)}</div></div><div class="view-panel"><span class="image-tag left">${escape(preset.name)} · AI 预览</span><div class="image-canvas">${img(result, `${displayName}${preset.name}光照结果`)}</div></div>`;
    } else {
      const content = mode === 'original' ? img(input, originalLabel) : img(result, `${displayName}${preset.name}光照结果`);
      const overlay = mode === 'slider' ? `<div class="original-layer">${img(input, `${displayName}实际输入`)}</div><div class="split-line"><span class="split-knob">‹ ›</span></div>` : '';
      surface.innerHTML = `<div class="view-panel"><span class="image-tag left">${mode === 'result' ? escape(preset.name) + ' · AI 预览' : originalLabel}</span>${mode === 'slider' ? `<span class="image-tag right">${escape(preset.name)} · AI 预览</span>` : ''}<div class="image-canvas">${content}${overlay}</div></div>`;
    }
    surface.dataset.width = input.width;
    surface.dataset.height = input.height;
    renderedResult = result;
    $('export').disabled = !result;
    applyView();
  } catch (error) {
    if (version !== renderVersion) return;
    surface.innerHTML = '<div class="empty"><h3>图片无法载入</h3><p>请确认本地素材完整后重新启动应用。</p></div>';
    dispatch({ type: 'ERROR', message: error.message || '图片读取失败。' });
  }
}

function applyView() {
  if (!state) return;
  const { view } = state;
  const layout = previewLayout(surface.dataset.mode, surface.clientWidth, Number(surface.dataset.width), Number(surface.dataset.height));
  surface.classList.toggle('is-stacked', layout.stacked);
  // The border is outside the panel height. ResizeObserver settles again if the width changes.
  surface.style.height = `${layout.height + 2}px`;
  surface.classList.toggle('is-pannable', view.zoom > 1);
  $('zoom-label').textContent = `${Math.round(view.zoom * 100)}%`;
  $('zoom-in').disabled = view.zoom >= 3;
  $('zoom-out').disabled = view.zoom <= 1;
  $('compare-range').value = view.split;
  $('view-hint').textContent = view.zoom > 1 ? '已放大 · 拖动平移 · 适合窗口可恢复完整画布' : state.mode === 'generate' && !selection(state, catalog).result ? '仅输入预览，尚无本次有效结果' : state.comparison === 'slider' ? '拖动滑杆比较光照差异' : layout.stacked ? '上下比较 · 完整画布' : '完整显示，可放大查看';
  surface.querySelectorAll('.view-panel').forEach(panel => {
    const canvas = panel.querySelector('.image-canvas');
    if (!canvas) return;
    const panelRect = panel.getBoundingClientRect();
    const size = fitSize(Number(surface.dataset.width), Number(surface.dataset.height), panelRect.width, panelRect.height);
    canvas.style.width = `${size.width}px`; canvas.style.height = `${size.height}px`;
    canvas.style.transform = `translate(${view.panX * size.width}px, ${view.panY * size.height}px) scale(${view.zoom})`;
    const original = canvas.querySelector('.original-layer');
    if (original) original.style.clipPath = `inset(0 ${100 - view.split}% 0 0)`;
    const line = canvas.querySelector('.split-line');
    if (line) line.style.left = `${view.split}%`;
  });
}

function zoom(delta) {
  const z = Math.max(1, Math.min(3, state.view.zoom + delta));
  const bound = (z - 1) / 2;
  dispatch({ type: 'VIEW', value: { zoom: z, panX: Math.max(-bound, Math.min(bound, state.view.panX)), panY: Math.max(-bound, Math.min(bound, state.view.panY)) } });
}

async function loadFile(file) {
  if (!catalog || !state) return;
  if (active()) return dispatch({ type: 'ERROR', message: '任务仍在提交、执行或待核实，请先查看当前任务。' });
  const version = ++uploadVersion;
  uploadFile = null; requestId = null; ++pollVersion;
  if (state.upload) URL.revokeObjectURL(state.upload.url);
  dispatch({ type: 'UPLOAD_START' });
  const error = validateFile(file);
  if (error) return dispatch({ type: 'ERROR', message: error });
  let input;
  try {
    input = await decodeUpload(file);
    if (version !== uploadVersion) { URL.revokeObjectURL(input.url); return; }
    const dimensionsError = validateDimensions(input.width, input.height);
    if (dimensionsError) { URL.revokeObjectURL(input.url); return dispatch({ type: 'ERROR', message: dimensionsError }); }
    dispatch({ type: 'UPLOAD', input });
    uploadFile = file; renderStatus();
    await disconnectedTask();
  } catch (error) {
    if (version === uploadVersion) dispatch({ type: 'ERROR', message: error.message });
  }
}

async function disconnectedTask() {
  const { preset } = selection(state, catalog);
  const input = state.upload;
  if (!input || state.mode !== 'generate' || capabilities.enabled || active()) return;
  const task = await disconnectedInference.submit(input, preset);
  if (state.mode === 'generate' && state.upload?.id === input.id && state.presetId === preset.id) dispatch({ type: 'TASK', task });
}

async function pollTask(taskId, version) {
  while (version === pollVersion) {
    try {
      const task = await serviceInference.getTask(taskId);
      if (version !== pollVersion) return;
      const previous = state.task;
      if (JSON.stringify([previous?.status, previous?.stage, previous?.result, previous?.error, previous?.executionUncertain,previous?.presetResults]) !==
          JSON.stringify([task.status, task.stage, task.result, task.error, task.executionUncertain,task.presetResults])) dispatch({ type: 'TASK', task });
      if (!['queued', 'running', 'succeeded','partial'].includes(task.status) && !task.executionUncertain) return;
      if (['succeeded','partial'].includes(task.status)) {
        await new Promise(resolve => setTimeout(resolve, Math.max(100, Math.min(30000, (task.expiresAt * 1000 - Date.now())))));
        continue;
      }
    } catch (error) {
      if (version !== pollVersion) return;
      dispatch({ type: 'ERROR', message: '状态查询失败，未认定任务成功或取消：' + error.message });
    }
    await new Promise(resolve => setTimeout(resolve, 2000));
  }
}
async function restoreTask() {
  const related = storageGet(relatedKey);
  if (active()) return;
  const id = storageGet(savedTaskKey);
  if (!id) return;
  const version = ++uploadVersion;
  const poll = ++pollVersion;
  restoring = true; dispatch({ type: 'RESTORE_START' });
  try {
    const task = await recoverTask(id, () => version === uploadVersion);
    if (!task || version !== uploadVersion) return;
    uploadFile = null; requestId = null;
    dispatch({ type: 'RESTORE_TASK', task });
    const viewed=storageGet(viewedKey);
    if(catalog.presets.some(p=>p.id===viewed)) dispatch({type:'PRESET',id:viewed});
    try {
      const history = JSON.parse(related || 'null');
      if (history?.inputId === task.input.id && Array.isArray(history.taskIds)) {
        for (const otherId of history.taskIds.slice(0, 3)) {
          if (otherId === task.taskId || version !== uploadVersion) continue;
          try { dispatch({ type: 'RELATED_TASK', task: await serviceInference.getTask(otherId) }); } catch {}
        }
      }
    } catch {}
    pollTask(id, poll);
  } catch (error) { if (version === uploadVersion) dispatch({ type: 'ERROR', message: '上次任务暂时不能恢复：' + error.message }); }
  finally { restoring = false; renderStatus(); }
}
$('restore-task').onclick = restoreTask;
$('view-upload-original').onclick = () => {
  const input = state.upload;
  if (!input) return;
  $('original-photo').src = input.originalUrl || input.url;
  $('original-photo').alt = '本次原始照片';
  $('original-detail').textContent = input.name + ' · 原始上传字节保留；比较区使用灰色留白的实际模型输入。';
  $('original-dialog').showModal();
};
$('submit-task').onclick = async () => {
  if (!capabilities.enabled || !uploadFile || !state.upload || active()) return;
  const input = state.upload;
  const presets = catalog.presets.filter(p=>state.plannedPresets.includes(p.id));
  if(!presets.length) return;
  if(state.task && ['succeeded','partial','failed','expired'].includes(state.task.status)) requestId=null;
  dispatch({ type: 'NEW_TASK' });
  requestId ||= crypto.randomUUID().replaceAll('-', '');
  storageSet(requestKey, JSON.stringify({ inputId: input.id, presetIds: presets.map(p=>p.id), requestId }));
  pending = true; renderStatus();
  try {
    const submissionVersion=uploadVersion;
    const task = await serviceInference.submit(input, presets, uploadFile, requestId);
    if(submissionVersion!==uploadVersion || state.upload?.id!==input.id) return;
    storageSet(savedTaskKey, task.taskId); storageSet(requestKey, null);
    if (state.mode !== 'generate') dispatch({ type: 'RESTORE_TASK', task });
    else dispatch({ type: 'TASK', task });
    pollTask(task.taskId, ++pollVersion);
  } catch (error) {
    dispatch({ type: 'ERROR', message: error.message + ' 可再次提交同一请求以核对，服务会避免重复执行。' });
  } finally { pending = false; renderStatus(); }
};
$('cancel-task').onclick = async () => {
  if (!state.task) return;
  try { dispatch({ type: 'TASK', task: await serviceInference.cancelTask(state.task.taskId) }); }
  catch (error) { dispatch({ type: 'ERROR', message: error.message }); }
};

$('sample-mode').onclick = () => { if (active() || state.mode === 'sample') return; ++uploadVersion; ++pollVersion; dispatch({ type: 'MODE', mode: 'sample' }); };
$('generate-mode').onclick = () => { if (active() || state.mode === 'generate') return; ++uploadVersion; dispatch({ type: 'MODE', mode: 'generate' }); disconnectedTask(); };
$('sample-list').onclick = event => {
  const button = event.target.closest('[data-sample]');
  if (button && !active()) { ++uploadVersion; ++pollVersion; dispatch({ type: 'SAMPLE', id: button.dataset.sample }); }
};
function selectPreset(event) {
  const button = event.target.closest('[data-preset]');
  if (button && !pending && !restoring) {
    const wasActive=active();
    if(!wasActive) ++pollVersion;
    storageSet(viewedKey,button.dataset.preset);
    dispatch({ type: 'PRESET', id: button.dataset.preset });
    if (state.task && state.task.status !== 'not_connected') {
      storageSet(savedTaskKey, state.task.taskId);
      if(!wasActive) pollTask(state.task.taskId, pollVersion);
    } else disconnectedTask();
  }
}
$('preset-list').onclick = $('compact-preset-list').onclick = selectPreset;
$('batch-options').onchange = event => {
  if(active() || !event.target.dataset.plan) return;
  requestId=null;
  dispatch({type:'PLAN_PRESETS',ids:[...$('batch-options').querySelectorAll('input:checked')].map(i=>i.dataset.plan)});
};
document.querySelectorAll('[data-comparison]').forEach(button => button.onclick = () => dispatch({ type: 'COMPARE', value: button.dataset.comparison }));
document.querySelectorAll('[data-region]').forEach(button => button.onclick = () => dispatch({ type: 'REGION', value: button.dataset.region }));
$('zoom-in').onclick = () => zoom(.25);
$('zoom-out').onclick = () => zoom(-.25);
$('fit').onclick = () => dispatch({ type: 'FIT' });
$('compare-range').oninput = event => dispatch({ type: 'VIEW', value: { split: Number(event.target.value) } });
$('export').onclick = () => {
  const { exportUrl, result } = selection(state, catalog);
  if (!result || result.url !== renderedResult?.url || result.taskId !== renderedResult?.taskId || !exportUrl) return;
  const link = document.createElement('a'); link.href = exportUrl; link.download = ''; link.click();
};
$('view-original').onclick = () => {
  const { sample } = selection(state, catalog);
  if (!sample) return;
  $('original-photo').src = sample.original.url;
  $('original-photo').alt = `${sample.name}原始照片`;
  $('original-detail').textContent = `${sample.name} · ${sample.original.width} × ${sample.original.height} px · ${sample.credit.creator} · ${sample.credit.license}`;
  $('original-dialog').showModal();
};
$('close-original').onclick = () => $('original-dialog').close();
$('original-dialog').onclick = event => { if (event.target === $('original-dialog')) $('original-dialog').close(); };
function chooseFile() { if (!active()) { fileSelectionRequested = true; $('file-input').value = ''; $('file-input').click(); } }
$('drop-zone').onclick = chooseFile;
$('drop-zone').onkeydown = event => { if (['Enter', ' '].includes(event.key)) { event.preventDefault(); chooseFile(); } };
$('file-input').onchange = event => {
  const requested = fileSelectionRequested; fileSelectionRequested = false;
  const file = event.target.files[0]; event.target.value = '';
  // Browser form restoration is not a new user selection and must not clear a restored task.
  if (requested && file) loadFile(file);
};
$('file-input').oncancel = () => { fileSelectionRequested = false; };
document.addEventListener('dragover', event => {
  event.preventDefault(); $('drop-zone').classList.add('dragover');
});
document.addEventListener('dragleave', event => { if (!event.relatedTarget) $('drop-zone').classList.remove('dragover'); });
document.addEventListener('drop', event => {
  event.preventDefault(); $('drop-zone').classList.remove('dragover');
  if (!state) return;
  if (active()) return dispatch({ type: 'ERROR', message: '任务仍在执行或待核实，不能替换当前照片。' });
  if (event.dataTransfer.files.length !== 1) {
    ++uploadVersion;
    if (state.upload) URL.revokeObjectURL(state.upload.url);
    dispatch({ type: 'UPLOAD_START' }); dispatch({ type: 'ERROR', message: '一次请选择一张图片。' }); return;
  }
  loadFile(event.dataTransfer.files[0]);
});
let drag = null;
surface.onpointerdown = event => {
  if (!state || !surface.querySelector('.image-canvas')) return;
  const canvas = event.target.closest('.view-panel')?.querySelector('.image-canvas');
  if (!canvas) return;
  drag = { kind: surface.dataset.mode === 'slider' && (event.target.closest('.split-knob') || state.view.zoom === 1) ? 'split' : 'pan', x: event.clientX, y: event.clientY, view: { ...state.view }, canvas };
  surface.setPointerCapture(event.pointerId);
  if (drag.kind === 'split') move(event);
};
function move(event) {
  if (!drag) return;
  if (drag.kind === 'split') {
    const rect = drag.canvas.getBoundingClientRect();
    dispatch({ type: 'VIEW', value: { split: Math.max(0, Math.min(100, (event.clientX - rect.left) / rect.width * 100)) } });
  } else if (state.view.zoom > 1) {
    const bound = (state.view.zoom - 1) / 2;
    dispatch({ type: 'VIEW', value: { panX: Math.max(-bound, Math.min(bound, drag.view.panX + (event.clientX - drag.x) / drag.canvas.offsetWidth)), panY: Math.max(-bound, Math.min(bound, drag.view.panY + (event.clientY - drag.y) / drag.canvas.offsetHeight)) } });
  }
}
surface.onpointermove = move;
surface.onpointerup = surface.onpointercancel = () => { drag = null; };
new ResizeObserver(applyView).observe(surface);

try {
  catalog = await sampleSource.catalog();
  state = createState(catalog);
  try { capabilities = await serviceInference.capabilities(); }
  catch { capabilities = { enabled: false }; }
  $('generate-mode').querySelector('span').textContent = capabilities.developmentTestMode ? '离线测试' : capabilities.enabled ? '推理已配置' : '推理默认关闭';
  render();
  if (capabilities.developmentTestMode) document.querySelector('.local-badge').textContent = '离线测试替身 · 非 GPU';
  const pendingRequest = storageGet(requestKey);
  const linkedTask = new URLSearchParams(location.search).get('task');
  if (/^[0-9a-f]{32}$/.test(linkedTask || '')) storageSet(savedTaskKey,linkedTask);
  if (pendingRequest) {
    try {
      const task = await serviceInference.getRequest(JSON.parse(pendingRequest).requestId);
      storageSet(savedTaskKey, task.taskId); storageSet(requestKey, null);
    } catch (error) { dispatch({ type: 'ERROR', message: '上次提交状态：' + error.message }); }
  }
  if (storageGet(savedTaskKey)) await restoreTask();
} catch (error) {
  surface.innerHTML = `<div class="empty"><h3>本地样例无法读取</h3><p>${escape(error.message)}</p></div>`;
  document.querySelectorAll('button,[tabindex]').forEach(el => { el.disabled = true; el.setAttribute('aria-disabled', 'true'); });
}
