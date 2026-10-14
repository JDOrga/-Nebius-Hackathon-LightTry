# 新网页双预设 GPU 验收：通过

2026-10-10，WJX；本轮另获一次现有 Devlab 启动、含税 $3、指定上传及守护停机授权。前次失败及本地状态过渡修复记录保留。没有第二次启动本轮实例，没有安装依赖、下载权重/HDR、增加资源、重算 inverse、导入历史 forward、手改成功状态、提交、打标签、推送或公开部署。

## 新任务与实际执行

浏览器通过文件选择器载入同一白蓝瓷杯原照，勾选 sunny、sunrise，点击生成一次。服务日志有一次 `POST /api/tasks` 返回202。新 task `e7ca7776b5094aba8ea1008c8421f456`，requestId `da04ea4c1d454422b4e0585e1c9fd429`，nonce `46bcb159dcab4f60812f59120dfcb0f4`；新 run `01725f1eeab34d899ad7ba02a9124745`。与开机前目录列表比较，生产 `.tasks` 只新增该任务。两项精确列表贯穿网页请求、执行包、runtime-binding 和本轮配置，单次 executor/driver 调度、一次 remote launch。

本轮 VM `computeinstance-e00v9j527bcn0q8hxj`，容器 `3d94c2598e895929e2fd7e0140550dbee506a2a5748395c8198c2074c327fee2`，容器用户 jovyan，worker PID527，本机 driver PID19352。当前 API 归属、公钥映射和完整前后校验通过；候选捕获期间出现短暂 VM_INFO_PENDING，在原截止内第5次捕获尝试恢复至同一 VM，没有重开或延时。用户准确确认本轮候选指纹后才建立 pin 并上传。成功前后白名单快照与差异记录保留；本轮没有人为制造状态过渡，不能声称实际复现了 STARTUP_STATE_TRANSITION 分类。

原照 SHA256 `9b01bfe7afd72e56c0b1ff95de93e78594aa82d743a2baa120e151e1ca913028`；本轮预处理 PNG SHA256 `1a7b31e4bbf0ca4478534552c63f2159ec992540d8709fe1283aaf4aae295051`，RGB SHA256 `c5c63421e8c93a11d08cf54a74174659dd8e79eae1738e8109009c44c219bf24`。PNG 编码哈希随本地预处理记录可不同；实际像素、canvas 和 inverse identity/key 校验相同。五通道来源仍为 task `6d541112fa164c099d9fc06c560b464d` / run `dc011af5186c492d8ffd2f6342e5c07f`，键 `155868063db861b7513f9c78dd0161da123cf3542ee7b72620f6a83c01e318e5`，requiredInverseReuse 强制绑定，无冷启动 fallback。

本轮上传包 SHA256 `7a76e39527053473a6f7792ab01e9e2ae3512fed0471b9471dec30c20f495b7f`，只包含预处理输入、历史五通道、来源/权重引用与白名单代码，无原照、权重或旧 forward 结果。weights 为 historical_metadata，content_verified=false；执行证据证明本轮 checkpoint content bytes read=0，只有既有文件存在/大小检查。

实际事件核实 **inverse=0、forward 初始化=1、forward 进程=1**。模型对象 `0x74758dbb7fa0`，forward process `cb37a59a687e41c1bbd84af7e4ab8efd`，顺序完成两个预设。

|预设|实际生成完成（北京时间）|JPEG字节|JPEG SHA256|
|---|---|---|---|
|sunny|16:47:42.747|38520|`080bb85e9d13cabdfefc6037276552bebba1dfb38ff43373ee0aba65053b5668`|
|sunrise|16:47:48.650|38854|`8a36f406aa5ac867ba52d11ea4eea097948e41542c9a037a125d2ba650eba1f2`|

两张JPEG均1280×704，解码、非恒定检查、task/nonce/input/preset/config/HDR/随机策略归属通过。结果归档400728字节，传输SHA256 `142f5f2a0ebb606a9dd96e2d11fd63623a380ba1d38877b53c2aafd2ff5bf9bf` 通过。相同 seed 可能重复历史字节，判断依据是本轮执行事件、attempt、模型对象和来源共同绑定，非只比较哈希。

## 正式产品路径和浏览器

driver 整批结束后 export/download/extract，TaskStore 在正常 GET 轮询时自动 evidence merge，逐项校验后发布。本轮没有运行历史登记 CLI，也没有改 task.json 成功状态。旧汇总器仍有私有测速语义的 `productBatchRegistered=false` / `productDisplayTime=null` 字段，本轮不改写旧字段；独立 `download-verification.json`、`browser-verification.json` 和 `web-first-display.json` 记录本轮直接网页任务的自动发布与展示。

|验收项|结果|
|---|---|
|网页新批次，恰好sunny/sunrise，一次调度|通过|
|inverse=0，forward初始化=1，同对象顺序完成|通过|
|两项输出身份、尺寸、解码、非恒定与传输哈希|通过|
|两灯光来回切换，不串图|通过，逐项DOM图片URL及尺寸记录|
|刷新及关闭后重新打开|通过，同task/run，恢复所查看sunrise|
|滑杆、并排、完整画布及原照片区域|通过，滑杆0/100，桌面左右/窄屏上下，无横向溢出|
|两份完整JPEG下载|通过，实际浏览器下载与各自本轮产品/阶段输出逐字节一致|
|两份裁剪PNG下载|通过，RGB像素与对应JPEG按任务有效区 `[442,0,838,704)` 裁剪完全一致，396×704|
|未生成street|通过，只显示输入、下载禁用、无新增task或自动提交|

PNG SHA256：sunny `f776e04998fa2b4bf35b6df0b8ef73009382441a19b198a37f2ac3c02fbc7358`；sunrise 见本轮 download-verification.json。下载文件名含本轮 task、preset、full/photo-region；原文件保留在用户 Downloads，核对副本在本轮证据目录。

网页唯一点击到首次观察到结果可显示为 **471.211秒（7分51.21秒）**，包含提交、准备、加载/执行、整批取回、产品校验、浏览器轮询/渲染和观测延迟。浏览器可见结果用同一本机单调时钟记录；首次可见观测不宣称零观测误差。driver入口至本地验证468.566秒是另一个起止，不与网页等待混用。

执行端第二预设完成相对第一预设完成的单调时间增量 **5.903秒**，包含切换、随机重置、生成和写出，不称为纯 GPU kernel 时长。两项均不是“切灯光速度”；已有结果的本地切换不执行模型。整批结束前没有流式图片或常驻模型服务。

![桌面本轮晨光结果](C:/Project/Nebius/.local/web-batch-20261010-retry2/sunrise-desktop.jpg)

![390×844窄屏本轮晨光有效区域](C:/Project/Nebius/.local/web-batch-20261010-retry2/sunrise-narrow.jpg)

## 时间、费用及停机

以下为北京时间：守护arm16:38:04.953；唯一启动请求16:38:21.438；独立RUNNING锚点16:39:46.146。+18截止16:57:46.146、+25停机触发17:04:46.146、+27核实目标17:06:46.146；arm时固定+60分钟绝对截止，更早截止优先。启动等待1800秒有界；没有重置或延长。

16:52:13.504验收完成发出提前停机信号；守护16:52:21.961请求停机，16:52:25.336 accepted。第一次独立三次查询仍STOPPING，未记为完成，按既有确认工具补保护性stop请求并保留监督；没有再次launch。**16:53:19.651 独立 API 确认STOPPED、instances=[]**。16:53:29.390最终heartbeat stopped_verified=true、sleep_held=false，16:53:29.825核对守护PID25804已退出并写finalization。

现有资源规格未变：单L40S、16vCPU、64GiB、200GiB NETWORK_SSD。依据同会话核对的 [官方价格](https://docs.nebius.com/compute/resources/pricing)，保守采用Intel CPU价，含现有存储约$1.7663/h税前。启动请求到独立STOPPED898.214秒，保守整个过渡按全价估算 **$0.4407税前**；arm到守护退出924.872秒加50%税费/不确定性余量约 **$0.6806**，本轮授权含税上限$3。**实际账单、税额、折扣和计费起止未核实**；该余量不是实际税率。现有存储停止后约$0.01945/h税前持续计费，没有删除资源。

本地8774已恢复默认真实推理关闭的服务，仍可从既有本轮任务查看/下载校验结果；新收费执行入口不再就绪。本轮结果默认24小时过期（约2026-10-11 16:49:09.966），原始证据和实际下载文件保留，不延长任务状态。过期后不手改任务时间；可用样例模式演示。

## 文件与版本

机器可读证据：`.local/web-batch-20261010-retry2/final-verification.json`、execution-summary.json、bundle-verification.json、download-verification.json、browser-verification.json、download-paths.json、web-click.json、web-first-display.json；cloud-runs本轮目录包含授权、锚点、捕获、pin、上传/launch/取回、停机和释放原始记录。

HEAD保持 `93c23724ec85addfcd2f5bad971aef329bd6d502` / main。既有未提交的主机捕获修复与回归、前次报告全部保留。本轮GPU执行后只补文档和候选文件清单，未修改模型/产品功能，未新增测试矩阵。候选说明见 [可演示候选基线](DEMO_CANDIDATE_BASELINE_20261010.md)，本轮到此结束。
