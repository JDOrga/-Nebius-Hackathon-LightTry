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
export async function decodeUpload(file) {
  const url = URL.createObjectURL(file);
  try {
    const image = new Image();
    image.src = url;
    await image.decode();
    return { id: crypto.randomUUID(), name: file.name, url, width: image.naturalWidth, height: image.naturalHeight, kind: 'upload' };
  } catch {
    URL.revokeObjectURL(url);
    throw new Error('图片无法解码，文件可能损坏。请重新选择 JPG、PNG 或 WebP 图片。');
  }
}
