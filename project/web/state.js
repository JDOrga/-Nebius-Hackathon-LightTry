// Pure state transitions shared by the UI and small node:test regression suite.
export const EMPTY_VIEW = Object.freeze({ zoom: 1, panX: 0, panY: 0, split: 50 });
export function createState(catalog) {
  return { mode: 'sample', sampleId: catalog.samples[0].id, presetId: catalog.presets[0].id,
    upload: null, task: null, tasks: {}, region: 'full', comparison: 'slider', view: { ...EMPTY_VIEW }, error: null };
}
export function reduce(state, event) {
  switch (event.type) {
    case 'SAMPLE': return { ...state, mode: 'sample', sampleId: event.id, task: null, error: null, view: { ...EMPTY_VIEW } };
    case 'MODE': return state.mode === event.mode ? state : { ...state, mode: event.mode, task: null, region: 'full', error: null, view: { ...EMPTY_VIEW } };
    case 'PRESET': return { ...state, presetId: event.id,
      task: state.tasks?.[event.id]?.input?.id === state.upload?.id ? state.tasks[event.id] : null, error: null };
    case 'UPLOAD_START': return { ...state, mode: 'generate', upload: null, task: null, tasks: {}, error: null, view: { ...EMPTY_VIEW } };
    case 'UPLOAD': return { ...state, mode: 'generate', upload: event.input, task: null, tasks: {}, error: null, view: { ...EMPTY_VIEW } };
    case 'TASK': {
      const task = event.task;
      if (state.mode !== 'generate' || task.input?.id !== state.upload?.id || task.preset?.id !== state.presetId ||
          (state.task && state.task.status !== 'not_connected' && state.task.taskId !== task.taskId)) return state;
      return { ...state, task, error: null, upload: task.status === 'not_connected' ? state.upload : task.input,
        tasks: task.status === 'not_connected' ? state.tasks : { ...state.tasks, [task.preset.id]: task } };
    }
    case 'RESTORE_TASK': return { ...state, mode: 'generate', upload: event.task.input,
      presetId: event.task.preset.id, task: event.task,
      tasks: { ...(state.upload?.id === event.task.input.id ? state.tasks : {}), [event.task.preset.id]: event.task },
      error: null, view: { ...EMPTY_VIEW } };
    case 'RELATED_TASK': return event.task.input?.id === state.upload?.id ? { ...state,
      tasks: { ...state.tasks, [event.task.preset.id]: event.task } } : state;
    case 'RESTORE_START': return { ...state, mode: 'generate', upload: null, task: null, error: null, region: 'full' };
    case 'NEW_TASK': return { ...state, task: null, error: null };
    case 'ERROR': return { ...state, error: event.message };
    case 'COMPARE': return { ...state, comparison: event.value };
    case 'REGION': return { ...state, region: event.value, view: { ...EMPTY_VIEW } };
    case 'VIEW': return { ...state, view: { ...state.view, ...event.value } };
    case 'FIT': return { ...state, view: { ...EMPTY_VIEW, split: state.view.split } };
    default: return state;
  }
}
export function selection(state, catalog) {
  const preset = catalog.presets.find(p => p.id === state.presetId);
  if (state.mode === 'generate') {
    const task = state.task;
    const candidate = task?.result;
    const result = task?.status === 'succeeded' && (!task.expiresAt || task.expiresAt * 1000 > Date.now()) && task.input.id === state.upload?.id && task.preset.id === preset?.id &&
      candidate?.taskId === task.taskId && candidate.inputId === state.upload.id && candidate.presetId === preset.id ? candidate : null;
    const box = recordedRegion(state.upload);
    // An ungenerated/disconnected selection has no server task. Its input may
    // still be the verified canvas from the last real task; crop THAT input.
    const realTaskId = /^[0-9a-f]{32}$/.test(task?.taskId || '') ? task.taskId :
      /^\/api\/tasks\/([0-9a-f]{32})\/input$/.exec(state.upload?.url || '')?.[1];
    if (state.region === 'photo' && box && realTaskId) {
      const dims = { width: box[2] - box[0], height: box[3] - box[1] };
      const base = `/api/tasks/${realTaskId}`;
      return { sample: null, preset, input: { ...state.upload, ...dims, url: base + '/input-region' },
        result: result ? { ...result, ...dims, url: base + '/result-region' } : null,
        exportUrl: result ? base + '/download-region' : null };
    }
    return { sample: null, preset, input: state.upload, result, exportUrl: result?.downloadUrl || null };
  }
  const sample = catalog.samples.find(s => s.id === state.sampleId);
  return { sample, preset, input: sample?.input, result: sample?.results[preset?.id],
    exportUrl: sample && preset ? `/download/${sample.id}/${preset.id}` : null };
}
export function recordedRegion(input) {
  const canvas = input?.canvas, box = canvas?.validRegion;
  if (!Array.isArray(box) || box.length !== 4 || !box.every(Number.isInteger) ||
      !Number.isInteger(canvas.width) || !Number.isInteger(canvas.height) ||
      input.width !== canvas.width || input.height !== canvas.height ||
      !(0 <= box[0] && box[0] < box[2] && box[2] <= canvas.width &&
        0 <= box[1] && box[1] < box[3] && box[3] <= canvas.height)) return null;
  return box;
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

// At fit scale, each comparison panel uses its full width and complete image aspect.
// Layout follows the available preview width, including a narrow desktop sidebar layout.
export function previewLayout(mode, availableWidth, imageWidth = 1280, imageHeight = 704) {
  const ratio = imageHeight / imageWidth;
  if (mode === 'side') {
    const stacked = availableWidth < 640;
    return { stacked, height: stacked ? availableWidth * ratio * 2 + 1 : (availableWidth - 1) / 2 * ratio };
  }
  return { stacked: false, height: Math.min(620, Math.max(180, availableWidth * ratio)) };
}
