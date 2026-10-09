import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createState, reduce, selection, validateFile, validateDimensions, fitSize, previewLayout } from '../web/state.js';
import { disconnectedInference } from '../web/sources.js';
const catalog = JSON.parse(readFileSync(new URL('../data/catalog.json', import.meta.url), 'utf8'));

test('each sample selects its own three forward results and exact HDR mapping', () => {
  assert.deepEqual(catalog.presets.map(p => [p.id, p.hdr, p.index]), [
    ['sunny', 'sunny_vondelpark_2k.hdr', 0], ['sunrise', 'pink_sunrise_2k.hdr', 1], ['street', 'street_lamp_2k.hdr', 2],
  ]);
  for (const sample of catalog.samples) for (const preset of catalog.presets) {
    const state = reduce(reduce(createState(catalog), { type: 'SAMPLE', id: sample.id }), { type: 'PRESET', id: preset.id });
    const selected = selection(state, catalog);
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
  assert.equal(selection(state, catalog).input.assetId, catalog.samples[0].input.assetId);
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
