import { createState, reduce, selection, validateFile, validateDimensions, fitSize } from './state.js';
import { sampleSource, disconnectedInference, decodeUpload } from './sources.js';

const $ = id => document.getElementById(id);
const escape = value => String(value).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
let catalog, state, renderVersion = 0, uploadVersion = 0, renderedResult = null;
const surface = $('preview-surface');

function dispatch(event) {
  state = reduce(state, event);
  if (['VIEW', 'FIT'].includes(event.type)) return applyView();
  if (event.type === 'TASK' || event.type === 'ERROR') return renderStatus();
  render();
}

function renderStatus() {
  const generate = state.mode === 'generate';
  $('upload-error').hidden = !state.error;
  $('upload-error').textContent = state.error || '';
  $('upload-status').hidden = !generate;
  $('upload-status').replaceChildren();
  const title = document.createElement('strong');
  title.textContent = state.upload ? '已载入，尚未连接推理服务' : '真实生成尚未连接';
  const detail = document.createElement('span');
  detail.textContent = state.upload ? '当前仅显示你的原图。连接服务后才能生成光照结果。' : '选择一张图片，先在本机预览原图。';
  $('upload-status').append(title, detail);
}

async function render() {
  const version = ++renderVersion;
  const { sample, preset, input, result } = selection(state, catalog);
  const generate = state.mode === 'generate';
  renderedResult = null;
  $('export').disabled = true;
  $('sample-mode').setAttribute('aria-pressed', String(!generate));
  $('generate-mode').setAttribute('aria-pressed', String(generate));
  $('samples-panel').hidden = generate;
  $('source-label').textContent = generate ? '真实生成 · 服务未连接' : '样例演示 · 历史实测';
  $('image-title').textContent = generate ? input?.name || '载入你的产品照片' : `${sample.name} / ${preset.name}`;
  $('image-size').textContent = input ? `${input.width} × ${input.height} px` : '';
  $('canvas-note').textContent = generate ? '本机原图预览 · 等比显示' : '完整画布 · 等比显示 · 保留已有留白';
  $('sample-warning').hidden = !sample?.unstable;
  $('sample-warning').textContent = sample?.warning || '';
  $('export-note').textContent = generate ? '尚无生成结果，暂不能导出重打光结果' : '导出实际结果 JPEG，保留完整画布';
  $('hdr-note').textContent = `环境文件：${preset.hdr}`;
  document.querySelectorAll('[data-comparison]').forEach(button => {
    button.disabled = generate && button.dataset.comparison !== 'original';
    button.setAttribute('aria-pressed', String(button.dataset.comparison === (generate ? 'original' : state.comparison)));
  });
  $('slider-controls').hidden = generate || state.comparison !== 'slider';
  $('preset-list').innerHTML = catalog.presets.map(p => {
    const thumbnail = generate ? `<span class="environment environment-${p.id}" aria-hidden="true">☼</span>` : `<img src="${sample.results[p.id].url}" alt="">`;
    return `<button class="preset" data-preset="${escape(p.id)}" aria-pressed="${p.id === preset.id}" aria-label="${escape(p.name)}">${thumbnail}<span><strong>${escape(p.name)}</strong><small>${escape(p.description)}</small></span>${p.id === preset.id ? '<span class="tick" aria-hidden="true">✓</span>' : ''}</button>`;
  }).join('');
  $('sample-list').innerHTML = catalog.samples.map(s => `<button class="sample-button ${s.unstable ? 'unstable' : ''}" data-sample="${escape(s.id)}" aria-pressed="${s.id === state.sampleId}" aria-label="${escape(s.name)}${s.unstable ? '，效果不稳定' : ''}"><img src="${s.original.url}" alt=""><span>${escape(s.name)}</span></button>`).join('');
  renderStatus();
  if (!input) {
    surface.innerHTML = '<div class="empty"><span class="empty-icon">↥</span><h3>从一张产品照片开始</h3><p>点击右侧选图，或把图片拖到页面。<br>图片只在本机预览，推理服务尚未连接。</p></div>';
    applyView();
    return;
  }
  surface.innerHTML = '<div class="empty"><p>读取本地图片…</p></div>';
  try {
    // Decode both identities before showing either, so a rapid switch never pairs an old result with a new input.
    await Promise.all([input, ...(result ? [result] : [])].map(async record => {
      const image = new Image(); image.src = record.url; await image.decode();
      if (image.naturalWidth !== record.width || image.naturalHeight !== record.height) throw new Error('图片尺寸与样例记录不一致，请检查素材。');
    }));
    if (version !== renderVersion) return;
    const img = (record, label, cls = '') => `<img class="${cls}" src="${escape(record.url)}" alt="${escape(label)}" draggable="false">`;
    const mode = generate ? 'original' : state.comparison;
    const originalLabel = generate ? '上传原图' : '原图 · 等比适配';
    surface.dataset.mode = mode;
    if (mode === 'side') {
      surface.innerHTML = `<div class="view-panel"><span class="image-tag left">${originalLabel}</span><div class="image-canvas">${img(input, `${sample.name}实际输入`)}</div></div><div class="view-panel"><span class="image-tag left">${escape(preset.name)} · AI 预览</span><div class="image-canvas">${img(result, `${sample.name}${preset.name}光照结果`)}</div></div>`;
    } else {
      const content = mode === 'original' ? img(input, originalLabel) : img(result, `${sample.name}${preset.name}光照结果`);
      const overlay = mode === 'slider' ? `<div class="original-layer">${img(input, `${sample.name}实际输入`)}</div><div class="split-line"><span class="split-knob">‹ ›</span></div>` : '';
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
  surface.classList.toggle('is-pannable', view.zoom > 1);
  $('zoom-label').textContent = `${Math.round(view.zoom * 100)}%`;
  $('zoom-in').disabled = view.zoom >= 3;
  $('zoom-out').disabled = view.zoom <= 1;
  $('compare-range').value = view.split;
  $('view-hint').textContent = view.zoom > 1 ? '已放大 · 拖动平移 · 适合窗口可恢复完整画布' : state.mode === 'generate' ? '仅原图预览，尚无光照结果' : state.comparison === 'slider' ? '拖动滑杆比较光照差异' : '完整显示，可放大查看';
  surface.querySelectorAll('.view-panel').forEach(panel => {
    const canvas = panel.querySelector('.image-canvas');
    if (!canvas) return;
    const size = fitSize(Number(surface.dataset.width), Number(surface.dataset.height), panel.clientWidth, panel.clientHeight);
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
  const version = ++uploadVersion;
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
    await disconnectedTask();
  } catch (error) {
    if (version === uploadVersion) dispatch({ type: 'ERROR', message: error.message });
  }
}

async function disconnectedTask() {
  const { input, preset } = selection(state, catalog);
  if (!input || state.mode !== 'generate') return;
  const task = await disconnectedInference.submit(input, preset);
  if (state.mode === 'generate' && state.upload?.id === input.id && state.presetId === preset.id) dispatch({ type: 'TASK', task });
}

$('sample-mode').onclick = () => { ++uploadVersion; dispatch({ type: 'MODE', mode: 'sample' }); };
$('generate-mode').onclick = () => { ++uploadVersion; dispatch({ type: 'MODE', mode: 'generate' }); disconnectedTask(); };
$('sample-list').onclick = event => {
  const button = event.target.closest('[data-sample]');
  if (button) { ++uploadVersion; dispatch({ type: 'SAMPLE', id: button.dataset.sample }); }
};
$('preset-list').onclick = event => {
  const button = event.target.closest('[data-preset]');
  if (button) { dispatch({ type: 'PRESET', id: button.dataset.preset }); disconnectedTask(); }
};
document.querySelectorAll('[data-comparison]').forEach(button => button.onclick = () => dispatch({ type: 'COMPARE', value: button.dataset.comparison }));
$('zoom-in').onclick = () => zoom(.25);
$('zoom-out').onclick = () => zoom(-.25);
$('fit').onclick = () => dispatch({ type: 'FIT' });
$('compare-range').oninput = event => dispatch({ type: 'VIEW', value: { split: Number(event.target.value) } });
$('export').onclick = () => {
  const { exportUrl, result } = selection(state, catalog);
  if (!result || result !== renderedResult || !exportUrl) return;
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
$('drop-zone').onclick = () => $('file-input').click();
$('drop-zone').onkeydown = event => { if (['Enter', ' '].includes(event.key)) { event.preventDefault(); $('file-input').click(); } };
$('file-input').onchange = event => { const file = event.target.files[0]; event.target.value = ''; if (file) loadFile(file); };
document.addEventListener('dragover', event => {
  event.preventDefault(); $('drop-zone').classList.add('dragover');
});
document.addEventListener('dragleave', event => { if (!event.relatedTarget) $('drop-zone').classList.remove('dragover'); });
document.addEventListener('drop', event => {
  event.preventDefault(); $('drop-zone').classList.remove('dragover');
  if (!state) return;
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
  render();
} catch (error) {
  surface.innerHTML = `<div class="empty"><h3>本地样例无法读取</h3><p>${escape(error.message)}</p></div>`;
  document.querySelectorAll('button,[tabindex]').forEach(el => { el.disabled = true; el.setAttribute('aria-disabled', 'true'); });
}
