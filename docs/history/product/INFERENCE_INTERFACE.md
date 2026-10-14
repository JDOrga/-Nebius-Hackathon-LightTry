# LightTry 推理适配器接口

## 2026-10-10 文字方案接口

新增 `GET /api/language` 与 `POST /api/language/recommend`，共用本机 Host/Origin/CSRF 限制，独立于推理启用状态。请求只有本条 text、当前有序预设/排除项与显式比较三个标志，不传图片或资源身份。响应经过后端严格校验，再修改可编辑方案；固定函数名只是模型输出的数据载体，没有执行分发器，也没有 TaskStore 访问。只有用户另行点击确认才调用原 `POST /api/tasks`，只提交缺少有效结果的选择。详细字段/边界/配置与未验证项见 [文字方案交付](LANGUAGE_CONTROL_20261010.md)。原推理协议与守护没有变动。

## 2026-10-10 正式多灯光接入

继续使用原 TaskStore、POST `/api/tasks`、driver/worker/batch；一个照片任务可含 `presets: Preset[]`（1–3项）及 `presetResults: {[presetId]: {preset,status,result,error}}`。原 `preset/result` 保留为首项兼容视图。批次终态增加 `partial`；每项分别保存 `queued/pending/running/succeeded/failed/expired`。未取回的项只表示等待完成记录，不根据整批 stage 或经过时间声称正在生成或成功。

POST 元数据可用 `presetIds: string[]`，服务器去重并从 catalog 确定 HDR/index/hash。仍支持旧 `presetId`；若两者同时给出，presetId 必须等于列表首项。列表原始长度须1–3，未知预设拒绝。相同 requestId、输入和有序预设返回同任务；改内容409。整个列表一次传给 executor，再经同一 request.json 进入已有批量执行入口，前端不拆单。

每项新增 GET `/api/tasks/<taskId>/presets/<presetId>/{result,download,result-region,download-region}`，只接受 catalog 预设及固定文件种类。旧 result/download 路径读取首项。每次读结果验证对应 SHA256、大小、完整解码和尺寸；部分成功仍可下载完成项，失效或缺文件只使对应项不可用。裁剪从该任务 input.canvas.validRegion 读取，完整 JPEG 保持源字节，裁剪 PNG 不增加有损编码但不恢复 JPEG 丢失的信息。文件名含 taskId、presetId 与 full/photo-region。

本地 CLI `scripts/register_lighttry_results.py --job <workspace/.local 下相对目录> --run <runId> --original-task <原照来源任务>` 是正式历史登记入口，不提供浏览器登记端点。它校验 run归档哈希及归档request、launch目标run、task/nonce/input/原照/配置、catalog映射、五通道inverse来源、每项完成标记及输出哈希/尺寸/解码/非恒定；保留实际生成时间、原task/run和inverse来源。只在未发布 staging 内复制受控证据，再原子发布到原任务目录；同taskId已存在须登记身份、状态/生成来源和内容一致，不覆盖；重复登记不延长结果期限。失败批次可登记已完成项，未完成/失败项保留各自状态。任务与历史文件不自动清理。

页面区分上方“切换查看”和“勾选准备生成”；只有生成按钮发一个批次。运行中勾选锁定，查看可切换；重复点击由 pending 与服务端requestId双重保护。默认未连接仍禁用提交。恢复只保存任务/预设引用并重新查服务端，结果事实不保存在浏览器。当前执行端整批结束后取回结果，不支持首张流式出现，不宣称6秒网页出图或常驻模型。成功批次退出后新预设仍可能重新加载forward。

真实结果登记与本地验收见 [PRODUCT_BATCH_ACCEPTANCE_20261010.md](PRODUCT_BATCH_ACCEPTANCE_20261010.md)。下文2026-10-09单任务说明为旧兼容契约；新的每项结果在partial时仍可用。

2026-10-09：扩展既有 InputImage / Preset / Result / PreviewTask、sources.js 适配器和 state.js 状态管理，没有建立第二套产品协议。样例来源只读 catalog；未连接适配器仍返回 not_connected、result=null，不上传图片。真实服务默认关闭。

## 数据契约

```ts
type InputImage = {
  id: string; name: string; url: string; width: number; height: number; kind: 'upload';
  originalUrl?: string; sha256?: string; canvas?: object;
};
type Preset = { id: string; name: string; hdr: string; index: number; sha256: string };
type Result = {
  taskId: string; url: string; downloadUrl: string; width: number; height: number;
  inputId: string; presetId: string; sha256: string; bytes: number; validation: string;
};
type PreviewTask = {
  taskId: string; input: InputImage; preset: Preset;
  status: 'not_connected' | 'queued' | 'running' | 'succeeded' | 'failed' | 'expired';
  stage?: 'preflight' | 'weights' | 'inverse' | 'forward' | 'validating' | 'transferring' | null;
  result: Result | null; error: { code: string; message: string } | null;
  createdAt?: number; updatedAt?: number; expiresAt?: number; // UTC epoch seconds
  executionUncertain?: boolean; runConfig?: object;
};
interface InferenceAdapter {
  submit(input: InputImage, preset: Preset, file?: File, requestId?: string): Promise<PreviewTask>;
  getTask(taskId: string): Promise<PreviewTask>;
  cancelTask?(taskId: string): Promise<PreviewTask>;
}
```

未连接任务身份仍是 local-UUID，不代表云任务。真实 inputId/requestId/taskId 是 32 位小写 UUID hex。submit 的 file/requestId 是本机传输参数，核心任务结构不变。预设只接受 catalog 中 sunny/sunrise/street，服务器决定 HDR、索引和哈希，不接受客户端模型配置。

## 本机 HTTP 适配器

|接口|行为|
|---|---|
|GET `/api/inference`|启用状态、取消能力、开发测试标志、服务的 CSRF token；不含云配置|
|POST `/api/tasks`|原始图片字节 body；Content-Type 与内容一致；202 + PreviewTask|
|GET `/api/tasks/<taskId>`|查询/恢复，只由执行端真实事件推动阶段|
|GET `/api/requests/<requestId>`|恢复响应丢失的提交，不再次执行|
|POST `/api/tasks/<taskId>/cancel`|当前 409 CANCEL_UNSUPPORTED；任务未取消|
|GET `/api/tasks/<taskId>/input`|本次 1280×704 实际预处理 PNG|
|GET `/api/tasks/<taskId>/original`|本次原照字节，不用原始名称寻址|
|GET `/api/tasks/<taskId>/result`|校验后、未过期的本次 JPEG|
|GET `/api/tasks/<taskId>/download`|同一 JPEG 下载，每次重新校验身份与哈希|

POST 要求 X-LightTry-Token，以及与本机 URL 一致的浏览器 Origin。服务只绑定 127.0.0.1，Host 只接受实际端口的 127.0.0.1/localhost。图片 POST 另带 X-LightTry-Request：UTF-8 JSON `{inputId,presetId,name,requestId}` 的 base64，最多 4096 字符。名称只作显示，不作路径或命令。请求限 20 MiB、10 秒读取预算，拒绝分块传输。错误结构为 `{error:{code,message}}`，不返回执行命令、路径或原始 stderr。

内容只接受静态 JPG/PNG/WebP；后端完整解码，宽高至少 32、最多 4000 万像素、单边不超过 16384。EXIF 转正、嵌入 ICC → sRGB、LANCZOS 等比缩放、中性灰 (127,127,127) 居中留白，复用历史验证流程。保留原字节与画布记录；生成比较双方使用同一 1280×704 画布，可另看原照。

## 状态、归属与失败

单任务串行；文件锁阻止两个服务共享任务目录。相同 requestId/输入/预设返回同任务；同 key 改数据为 409 IDEMPOTENCY_CONFLICT。活动任务或执行端状态不确定时新提交为 TASK_BUSY，不排复杂队列。失败重试用明确的新 requestId；云适配器每个独立授权 run 只接收一次任务，不复用完成的上传目录/费用窗口。

任务状态写入原子 JSON；浏览器只保存 taskId/待确认 requestId，刷新查询服务。driver 独立于 UI 服务进程，关闭页面/服务不代表取消。没有真实执行事件时保持 queued，不根据耗时猜阶段、无百分比。失败、无效输出、服务错误、超时均无可下载结果。

发布要求 taskId、不可预测执行 nonce、inputId、presetId、原照/实际输入哈希、运行配置、两个进程 exit=0、固定 result.jpg、文件大小/SHA256、完整 JPEG 解码、1280×704 与非近似常量检查全部匹配；输出目录本次新建。前端再次核对 taskId/inputId/presetId，丢弃旧任务晚返回。统计/身份通过仅为结构成功，视觉质量仍待检查。

超时为 failed/TASK_TIMEOUT；未确认执行端退出时 executionUncertain=true，阻止新提交。晚结果不能把超时逆转为成功。只有执行端明确停止终态，或本次绑定的独立 API STOPPED/instances=[] + 守护释放证据，才能解除不确定状态。取消不能保证终止远端，409 如实告知。成功结果默认 24 小时后 expired、result=null，结果与下载为 410；留存文件供本地审计，不自动删除。

## 执行边界

inference/driver.py 复用 cloud/Invoke-ScaleRemote.ps1 的目标核对、精确 SSH pin、传输预算与独立守护，不创建认证/信任；产品没有 start/restart API。仅显式本机配置、当前费用授权、固定窗口、守护和新主机确认满足时可执行。正常启动无云调用。

driver 打包本次预处理图及白名单代码，安装到本次新目录，发送 remote_launch.py，查询 remote_inspect.py 的真实事件，导出/下载后只读允许的 result.jpg/receipt.json/execution.json。参数用 argv 列表或既有编码 JSON 传输，不拼用户命令。浏览器接触不到 SSH 私钥、云令牌、VM 地址或完整命令。实际命令、环境与验证报告留在私有任务/授权 run。

worker 固定上游 commit 与独立 HDR patch，检查既有环境，inverse → 验证五通道 → 独立进程 forward 单预设。默认完整扫描既有权重；显式 historical_metadata 模式复用已验证算法和另行提供的历史证据，仅确认同一模型身份与当前文件大小，记录 weightContentHashesChecked=false，不声称本轮内容完整性。没有安装/下载模型、自动 OOM 重试或两套 7B 同驻留。

2026-10-09 本轮验收准备：成功写 inference-finished.json，独立守护继续有效，操作者完成本地网页验收后立即写 complete.json 请求停机。本轮真实 driver 要求 receipt 的五个 gBuffers，下载后逐文件复核哈希、JPEG 解码和尺寸，审计文件保留在任务 remote-evidence；原 results.tar.gz 保留。模糊 launch 先 inspect 同任务 nonce，禁止重复 launch。已确认模型结束后的本地 KeyError/JSON 字段问题可保留 transferring 并等待一次显式 repair 记录，仅重试结果传输；未知传输/认证/信任/完整性错误仍走保护性停机。重试不延长截止，不逆转已超时任务。

真实推理默认关闭，无产品假结果模式。tests/serve_fixture.py 是独立离线 UI 测试入口，developmentTestMode=true 且有醒目标识，产品启动无法选此替身。它不能证明云端/GPU 成功。

## 样例目录

2026-10-09 同图复用扩展：完整规则及离线测试见 [REUSE_PREPARATION.md](REUSE_PREPARATION.md)。PNG 预处理记录增加 preprocessingVersion 与 RGB 像素哈希，复用仍先核对本次编码哈希。Result 可选 inverseReuse `{reused,sourceTaskId,key}`；真实复用 receipt 的 processExitCodes 为 `[null,0]`，必须同时校验历史来源和五通道原子完成记录。单任务 HTTP 提交契约不变，浏览器不提供自动多预设生成。受守护 worker 支持显式 presets 列表（1–3 项），各项状态和产物独立，部分失败保留阶段证据。默认生产仍不连接推理。

catalog 的素材 allowlist 与样例下载路径不变。默认 demo-assets 是独立离线包，不读 controlled-tests 或其他历史目录；启动逐文件校验 20 张图片和来源记录。样例只代表对应历史任务，不能成为用户照片的结果。
