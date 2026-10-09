// Pure state transitions shared by the UI and small node:test regression suite.
export const EMPTY_VIEW = Object.freeze({ zoom: 1, panX: 0, panY: 0, split: 50 });
export function createState(catalog) {
  return { mode: 'sample', sampleId: catalog.samples[0].id, presetId: catalog.presets[0].id,
    upload: null, task: null, comparison: 'slider', view: { ...EMPTY_VIEW }, error: null };
}
export function reduce(state, event) {
  switch (event.type) {
    case 'SAMPLE': return { ...state, mode: 'sample', sampleId: event.id, task: null, error: null, view: { ...EMPTY_VIEW } };
    case 'MODE': return { ...state, mode: event.mode, task: null, error: null, view: { ...EMPTY_VIEW } };
    case 'PRESET': return { ...state, presetId: event.id, task: null, error: null };
    case 'UPLOAD_START': return { ...state, mode: 'generate', upload: null, task: null, error: null, view: { ...EMPTY_VIEW } };
    case 'UPLOAD': return { ...state, mode: 'generate', upload: event.input, task: null, error: null, view: { ...EMPTY_VIEW } };
    case 'TASK': return { ...state, task: event.task };
    case 'ERROR': return { ...state, error: event.message };
    case 'COMPARE': return { ...state, comparison: event.value };
    case 'VIEW': return { ...state, view: { ...state.view, ...event.value } };
    case 'FIT': return { ...state, view: { ...EMPTY_VIEW, split: state.view.split } };
    default: return state;
  }
}
export function selection(state, catalog) {
  const preset = catalog.presets.find(p => p.id === state.presetId);
  if (state.mode === 'generate') {
    return { sample: null, preset, input: state.upload, result: null, exportUrl: null };
  }
  const sample = catalog.samples.find(s => s.id === state.sampleId);
  return { sample, preset, input: sample?.input, result: sample?.results[preset?.id],
    exportUrl: sample && preset ? `/download/${sample.id}/${preset.id}` : null };
}
export function validateFile(file) {
  if (!file) return '请选择一张图片。';
  if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) return '格式不支持，请选择 JPG、PNG 或 WebP 图片。';
  if (!file.size) return '图片文件为空，请重新选择。';
  if (file.size > 20 * 1024 * 1024) return '图片超过 20 MB，请缩小文件后重试。';
  return null;
}
export function validateDimensions(width, height) {
  if (width < 32 || height < 32) return '图片太小，请选择宽高至少 32 像素的图片。';
  if (width * height > 40_000_000 || Math.max(width, height) > 16384) return '图片尺寸过大，请缩小到 4000 万像素以内，单边不超过 16384 像素。';
  return null;
}
export function fitSize(width, height, availableWidth, availableHeight) {
  const scale = Math.min(availableWidth / width, availableHeight / height);
  return { width: width * scale, height: height * scale };
}
