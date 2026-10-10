/** @typedef {{id:string,name:string,url:string,width:number,height:number,kind:'upload'}} InputImage */
/** @typedef {{id:string,name:string,hdr:string,index:number}} Preset */
/** @typedef {{taskId:string,input:object,preset:Preset,status:'not_connected'|'queued'|'running'|'succeeded'|'failed',result:object|null,error:{code:string,message:string}|null}} PreviewTask */

// Sample lookup never receives an uploaded image. Future inference uses a separate adapter.
export const sampleSource = {
  async catalog() {
    const response = await fetch('/api/catalog');
    if (!response.ok) throw new Error('样例数据无法读取，请确认本地服务和素材完整。');
    return response.json();
  },
};
export const disconnectedInference = {
  async submit(input, preset) {
    return { taskId: `local-${crypto.randomUUID()}`, input, preset, status: 'not_connected', result: null,
      error: { code: 'SERVICE_NOT_CONNECTED', message: '已载入，尚未连接推理服务' } };
  },
};
async function responseJSON(response) {
  let value;
  try { value = await response.json(); } catch { throw new Error('服务返回无效，请查看本次任务状态后重试。'); }
  if (!response.ok) {
    const error = new Error(value.error?.message || '任务请求失败。');
    error.code = value.error?.code; throw error;
  }
  return value;
}
export const serviceInference = {
  token: null,
  async capabilities() {
    const value = await responseJSON(await fetch('/api/inference'));
    this.token = value.csrfToken;
    return value;
  },
  async submit(input, preset, file, requestId) {
    if (!file) throw new Error('刷新后原始文件不在浏览器内，请重新载入照片再提交新任务。');
    const selected = Array.isArray(preset) ? preset : [preset];
    const metadata={inputId:input.id,presetId:selected[0].id,name:input.name,requestId};
    if(Array.isArray(preset)) metadata.presetIds=[...new Set(selected.map(p=>p.id))];
    const bytes = new TextEncoder().encode(JSON.stringify(metadata));
    return responseJSON(await fetch('/api/tasks', { method: 'POST', headers: {
      'Content-Type': file.type, 'X-LightTry-Token': this.token, 'X-LightTry-Request': btoa(String.fromCharCode(...bytes)),
    }, body: file }));
  },
  async getTask(taskId) {
    if (!/^[0-9a-f]{32}$/.test(taskId)) throw new Error('任务身份无效。');
    return responseJSON(await fetch(`/api/tasks/${taskId}`));
  },
  async getRequest(requestId) {
    if (!/^[0-9a-f]{32}$/.test(requestId)) throw new Error('请求身份无效。');
    return responseJSON(await fetch(`/api/requests/${requestId}`));
  },
  async cancelTask(taskId) {
    return responseJSON(await fetch(`/api/tasks/${taskId}/cancel`, {
      method: 'POST', headers: { 'X-LightTry-Token': this.token },
    }));
  },
};
export async function recoverTask(taskId, isCurrent = () => true, delay = ms => new Promise(resolve => setTimeout(resolve, ms))) {
  for (let attempt = 0; attempt < 3; attempt++) {
    if (!isCurrent()) return null;
    try {
      const task = await serviceInference.getTask(taskId);
      return isCurrent() ? task : null;
    } catch (error) {
      if (!isCurrent()) return null;
      if (attempt === 2 || ['TASK_NOT_FOUND', 'RESULT_EXPIRED'].includes(error.code)) throw error;
      await delay(1000 * (attempt + 1));
    }
  }
}
export async function decodeUpload(file) {
  const url = URL.createObjectURL(file);
  try {
    const image = new Image();
    image.src = url;
    await image.decode();
    return { id: crypto.randomUUID().replaceAll('-', ''), name: file.name, url, width: image.naturalWidth, height: image.naturalHeight, kind: 'upload' };
  } catch {
    URL.revokeObjectURL(url);
    throw new Error('图片无法解码，文件可能损坏。请重新选择 JPG、PNG 或 WebP 图片。');
  }
}
