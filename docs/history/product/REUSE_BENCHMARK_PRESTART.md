# 2026-10-10 同图双预设测速：收费前准备报告

本轮停在本地准备。没有继承旧的一次启动或预算，没有启动、上传、GPU 推理、安装、权重下载、提交或推送，也没有修改认证、停机守护或旧证据。当前另有认证阻塞：已有只读 Status 查询返回 CLI exit 7（认证不可用）；实例当前状态、配置和账户价格尚不能通过 API 再核实。认证恢复后必须先重新只读核对，不能凭昨天的 STOPPED 开机。

## 历史复用与执行包

复核源任务 `6d541112fa164c099d9fc06c560b464d` 与旧 run、原 request/receipt/代码包、实际模型输入和五通道哈希。登记缓存键仍为 `155868063db861b7513f9c78dd0161da123cf3542ee7b72620f6a83c01e318e5`，五个 JPEG 完整、RGB、1280×704、同一 clip/frame，来源记录相符。原任务/request/receipt/结果、权重与补丁 manifest 哈希保持不变。

本轮新准备的私有执行任务为 `1214fe9e4efb49a6913730a3d657dc35`，使用新 nonce/inputId；尚未提交或创建收费 run。仅顺序 sunny、sunrise，historical_metadata、content_verified=false、reset-before-forward-generate-v1。`requiredInverseReuse` 绑定指定键与完整来源；本地打包和云端编排都在复用缺失/失效时停止，不会 fallback 到 inverse。旧晴日结果不会进入本轮生成结果目录。

本地冻结包为 `.local/reuse-benchmark-20261010/package/inference-code.tar.gz`，638625 字节；清单和完整 SHA256 见该目录 bundle.json 与上级 preparation.json。包含预处理输入、五个历史 G-buffer/完成来源标记、白名单代码、模型/补丁 manifest、历史权重检查引用，没有原始照片或权重。冻结包绑定新 run 的真实代码路径已在本地调用检查，未连接云端。开机前/执行前检查代码、任务和包哈希；代码改变则需在开机前重新准备。

## 本机浏览器实际验收

使用默认 executor=None 的真实产品 Handler 与原 `.tasks`，没有模拟任务/结果。独立 QA 初始化页只设置浏览器上次 taskId，使新浏览器能进入现有 GET 恢复路径；没有改任务记录。随后刷新由产品自身恢复。

- sunny 恢复到自身历史 task/result，切未生成 sunrise 不继承结果、下载禁用，提示连接授权后仍需显式提交；切回 sunny 恢复正确结果。
- 自动刷新恢复正确 sunny 任务。完整画布滑杆/并排检查为 1280×704；原照片区域双方为 396×704；原始照片为 2988×5312。
- 真实浏览器下载完整 JPEG，SHA256 为 `c52e2fc9a67e279389dc5925f4738623bbfb493dc69048711c2065480a18cae6`，与旧 receipt 一致；下载裁剪 PNG，与完整 JPEG 按 `[442,0,838,704]` 裁剪后的解码像素完全一致。
- 发现并修复一个局部缺陷：裁剪查看时切到未连接的未生成预设，曾把 local taskId 用于服务端裁剪 URL；现在只使用真实模型输入的来源路径，未生成预设仍无结果。修复后浏览器复测通过。
- 当前只有杯子照片的真实 sunny，尚不能验收该照片两个真实结果的切换。本轮未来 batch 是私有执行端测速，不通过手改 task.json 登记到网页。批量结果产品登记、网页双结果切换及交互式模型常驻分别列为未支持/待测，不能报成功。

浏览器截图、逐项记录及下载验真保存在 `.local/reuse-benchmark-20261010/browser-*.png`、browser-verification.json、download-verification.json。产品默认未连接时没有 POST 生成或云操作。

## 观察、取回与停机已准备

`.local/reuse-benchmark-20261010/approved-run.ps1` 默认只打印计划。必须在本轮明确费用批准后才使用执行动作：Arm → Restart → Capture → 本轮精确主机确认 → Run → Observe → 提前 Stop → 独立 ConfirmStopped。沿用现有守护和一次 restart marker；认证、信任、环境/资源范围异常或执行状态不确定时不重 launch。Restart 前核对原单 L40S/16 vCPU/64 GiB/200 GiB SSD 范围，若改变则停止，不重新估价后自行开机。

启动等待沿用最近成功轮次的 1800 秒上限，独立 RUNNING 起 +18 分钟不发起长操作、+25 分钟触发停机、+27 分钟目标核实，守护 arm 时一次写死 +60 分钟绝对截止，更早截止优先。没有延长原 RUNNING 窗口。完成立即提前停机；必须得到独立 STOPPED/instances=[]、守护退出和防休眠释放证据，不以 stop accepted 冒充完成。

已增加实际 pipeline_ready/reused 与 generate 的对象 ID、进程 ID、实际随机重置记录、逐预设校验及原子完成时刻。remote_inspect 返回各项真实状态；driver 在同一本机单调时钟上记录批量提交入口、首次观察到首项可用、每次传输和本地验证完成。首次可用观测包含轮询/传输延迟，不能伪装为无误差的服务器完成时间；跨主机墙钟差异不假定为零。

`summarize_reuse_benchmark.py --job <private-job>` 在实际取回后验证两个结果的 task/nonce/input/config/HDR、尺寸、解码、非恒定与哈希，以及 inverse 来源和实际子进程次数；核对同一进程、同一模型对象、构造一次。第一项成功第二项失败时保留第一项和失败/pending 记录，不重新 inverse 或成功预设。嵌套时间不相加，无 CUDA 同步的函数主机时间不称为纯 GPU kernel 时间。未产生真实数据时没有首张等待、第二张增量或本轮初始化验收数值。

## 费率、估算及待批准范围

2026-10-10 查阅 [Nebius 官方 Compute 定价](https://docs.nebius.com/compute/resources/pricing)：L40S GPU $1.35/小时；Intel CPU $0.012/vCPU/小时、AMD $0.01；RAM $0.0032/GiB/小时；Network SSD $0.071/GiB/730小时。价格税前，停止计算后存储继续收费。基于历史配置，保守取较高 Intel CPU 项，计算加现有 200 GiB 存储约 **$1.7663/小时税前**；当前账户折扣、税额和实际实例配置因认证阻塞未确认。

估计从一次启动请求到停机核实约 **10–15 分钟**，相应税前约 **$0.29–0.44**。只是预算估计，不是 GPU 性能承诺。保守将 arm 至可能计费的启动、RUNNING、停机过渡/核实全部按 60 分钟计算，再加 50% 税费/不确定性余量约 **$2.65**，拟申请本次含税上限 **$3**。未知停止过渡不能当成固定扣费时长；未核实 STOPPED 时继续保护性停机核实并报告。已有存储停止后约 $0.01945/小时持续计费，不删除以消除费用。详见 fee-estimate.json。

待用户一次明确批准：用户指定现有 Devlab 启动一次、本轮含税 $3 上限，上传这次必要预处理输入、五个历史 G-buffer、来源/权重引用与白名单执行代码，完成或失败由现有守护停机。旧预算不继承。批准后仍必须先恢复已有 CLI 认证并通过只读核对、守护及本轮主机信任，才可真正启动/上传。

本地产品 Python **69/69**、Node **16/16**；PowerShell 执行卡语法和默认无执行计划检查通过。仓库文本审计与 diff --check 通过，暂存区空。所有替身检查均离线，不记为 GPU 验收。当前停在等待本轮费用授权及认证恢复。
