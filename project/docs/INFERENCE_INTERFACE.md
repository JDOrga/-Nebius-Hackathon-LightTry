# 后续推理适配器接口

本轮数据来源分离在 `web/sources.js`：`sampleSource.catalog()` 只读取内置目录；`disconnectedInference.submit(input, preset)` 只返回本地未连接任务。上传文件使用浏览器 object URL，不上传到 Python 服务，无模拟进度或结果。界面通过 `web/state.js` 的明确 mode 隔离样例与真实生成，真实生成模式永远不读取样例结果。

## 数据契约

```ts
type InputImage = { id: string; name: string; url: string; width: number; height: number; kind: 'upload' };
type Preset = { id: string; name: string; hdr: string; index: number };
type Result = { url: string; width: number; height: number; inputId: string; presetId: string };
type PreviewTask = {
  taskId: string;
  input: InputImage;
  preset: Preset;
  status: 'not_connected' | 'queued' | 'running' | 'succeeded' | 'failed';
  result: Result | null;
  error: { code: string; message: string } | null;
};
interface InferenceAdapter {
  submit(input: InputImage, preset: Preset): Promise<PreviewTask>;
  getTask(taskId: string): Promise<PreviewTask>;
  cancelTask?(taskId: string): Promise<PreviewTask>;
}
```

当前只实现 `submit` 的未连接返回，`getTask/cancelTask` 留待真实服务，不提供网络实现。`taskId=local-UUID` 是本地状态身份，不是云任务。`error.code=SERVICE_NOT_CONNECTED`、`status=not_connected`、`result=null`；不创建队列、不发送请求。

未来接入时用新的服务适配器实现契约，仍沿用 Cosmos。排队/运行/失败 UI 可由 task.status 驱动；进度只能来自服务，字段缺失时不推测百分比。展示成功结果前必须核对 taskId、input.id、preset.id，防止旧任务晚返回造成错配。结果应携带画布/预处理记录，按双方一致画布进行完整比较；成功前不启用下载。当前生成区保持原图与未连接提示。

本目录不提供开机、付费 API、GPU 执行、自动连接或绕过守护的实现。以后真实服务的生命周期由已存在的独立授权/守护链管理，本产品不改写其配置。

## 素材目录

`data/catalog.json` 保存输入、原照、预设、结果、完整画布有效区域、来源路径及 SHA256。界面只接收 `/api/catalog` 的公开结构和 `/assets/<assetId>`，不在组件里硬编码实验路径。Python 服务器仅按目录 allowlist 读取素材，启动时验证全部 20 张图片的哈希；下载路线仅接受已有 sampleId + presetId。

`build_catalog.py` 是一次性本地来源核对工具，需要已有 Pillow；普通启动与 HTTP 测试仅用 Python 标准库，UI 无 npm 依赖或构建步骤。原始素材不复制到产品目录，不改写或覆盖。目录移动需要带上现有历史素材路径，缺失时启动明确失败。
