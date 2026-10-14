# LightTry 参数化调光台 + Nemotron：本地准备交付

状态：PREPARED_NOT_AUTHORIZED。没有启动/重启云机、上传、调用文字 API、安装依赖、提交或推送。正式前端完全未改动。准备目录：`C:\Project\Nebius\.local\lighttry-joint-20261012`。

## 代码与已有证据

本轮开始 HEAD：`e4d5fec41c0a65ea5ffd44a85b903afddeab4ecf`，工作区干净；现只新增联合验收模块、脚本、测试及本文。当前正式入口仍是 `C:\Project\Nebius\project\start_studio.py`。最新 parity REPORT/e2e 的六个语言/前端快照与当前字节全部相同；上游 commit 与补丁固定清单一致。旧 237 Python / 63 Node 为上轮有效记录，本轮没有冒充重新执行。

新增：严格 A—F 批次入口、原有守护传输集成、逐项取回、结果/条件证据哈希绑定、两轮真实文字请求门。原始 `C:\Project\Nebius\project\experiments\worker.py` 保持不变，新 `C:\Project\Nebius\project\next\runtime\joint_worker.py` 是其受限副本：`main()` 新增必需 `--joint`，forward child 改为 joint_entry，并在执行前验证联合计划。原生产前端/单方案提交没有改成自动 GPU。

新增测试14项 + 关键回归37项，共51项通过；其中模型、传输替身均明确标为 OFFLINE_SYNTHETIC。真实固定上游 CPU helper 在 704×1280 投影上运行过，验证实际 HDR 解码、乘法、截断、flip/roll、投影与 log 截断 hook。**GPU 条件处理、真实 Nemotron 新 schema 的两轮理解、照片 forward、真实新批次传输/停机仍未执行。** 结构合格、条件变化、视觉可控是三个不同结论。

## 照片、inverse、模型与资源

选择 Miss Kamola 的 CC0 1.0 陶罐，来源与许可由既有 source/proof 记录确认；适合看连续明暗、方向与接触阴影，不要求恢复不存在的细纹。原照 `C:\Project\Nebius\controlled-tests\20261007-four-materials\originals\01_matte_terracotta.jpg`，SHA `5e46330920891b48012b33ea28cf1f34ca282e8936cd2e25f06383681518ba90`。实际输入 SHA `cbbfad2ba8e746586ecf8187a228c4fae5df7c8b41d1ee0b7e441d8006679cb3`，1280×704，原照片有效区域 [112,0,1168,704]，灰色留白，沿用历史预处理。

复用历史 run `2aa06a2c4e154ad0b03424c0d1d3dcca` 的 basecolor/normal/depth/roughness/metallic 五张 JPEG；逐张大小、解码、哈希、共同帧、inverse exit=0、历史完整性账本和输入均已本地验证。历史整轮云验收失败、当地结构通过、质量混合的备注保留，不能改写成历史整轮成功。没有冷 inverse 回退。

当前 `C:\Project\Nebius\project\inference.local.json` enabled=false、weights_mode=historical_metadata；权重 manifest/reference/receipt 存在并通过既有引用校验。本机 upstream/checkpoints 没有真实模型权重，只有记录文件；远端存续与大小待获授权连接后核对。复用历史记录不扫描全文，content_verified_this_run=false；同大小替换不能排除。缺权重/大小变动就停，不下载、不换模型、不重建 inverse。

本地三份既有 HDR 均记录哈希；A 使用 sunny，SHA `581d9338941a7c387aaa99f331b956473aa80559ae767c012034ef0fe30bb4d5`。远端 A/作为载体的 sunny 仍执行原哈希检查；程序化 B—F 必须实际注入派生 HDR，不允许回落载体。HDR 独立素材许可及结果公开分发仍未完整核清，仅现有私有研究范围，上传需明确确认。

## 最小矩阵

固定 Cosmos Diffusion Renderer / upstream `0f3e2dc435032ecbad654c2fc2153df85384b138`，seed1000、steps15、guidance0、1帧、1280×704、无 offload、同一 inverse、同预处理。整体 offset0、strength1，底光0.03/白色。

|项|输入|相对 B 的变化|
|---|---|---|
|A|既有 sunny 环境|来源对照，**不是单变量**|
|B|白主光 key：方位45°、仰角30°、强度3、FWHM25°|程序化基准|
|C|同 B|只把 key 方位45°→135°|
|D|同 B|只把 key 强度3→1.5|
|E|同 B|只把 key FWHM25°→70°|
|F|同 B|仅新增白 fill：方位250°、仰角20°、强度0.7、FWHM55°|

方向是环境坐标，未校准照片左/右。角尺寸维持峰值振幅语义，不是能量归一化；RGBE 解码后的 B/E 每通道球面积积分约1.013829/5.004899、峰值均3.015625。E 能量约增加4.94倍，不能仅凭阴影变化声称物理柔光受控。实际运行另记录变换/截断与映射的统计。

目标：手动6次 forward，加入一条经确认的当次真实 AI 配方后7次；inverse=0；真正构造 forward pipeline 一次。不把每项 facade 的 pipeline_ready 记录当成多次构造；以 joint_pipeline_ready/joint_forward/joint_complete 实际日志验证。即使 AI 参数恰好重复，本实现仍新跑一项，不宣称新增参数能力或复用未发生的推理。

## 真实 Nemotron 闭环：先完成文字验收，再开 GPU 窗口

实际配置沿用 `nvidia/Nemotron-3_5-Lightning`，Nebius Token Factory `https://api.tokenfactory.nebius.com/v1/chat/completions`，thinking on、max_tokens40960、60秒共享超时、单工具结构返回。本轮默认命令不访问 Key。将来仅执行参数才使用现有私有进程 Key 或既有 LIGHTTRY_KEY_FILE，不创建持久认证、不输出 Key、不发照片。

第一轮给出具体 key+fill；第二轮只降低 fill.strength。两轮各1次初始请求、最多1次结构修复，总计最多4次，单独新账本/预算$0.08；语义不合格直接保存失败、不无限重试。认证/上游/限流/超时不自动重试。相同阶段已有 attempt 不能自动再次发出；不重置旧或新账本。正常返回也必须检验ID顺序、范围、唯一结构差异；解释不能代替实际参数修改。

每轮先展示 delta，等待操作者确认准确 operationId 才应用；应用仅保存参数，不生成。第二轮以已确认第一轮为参照。AI生成参数从已接受供应商账本取值，带真实 photoBinding；不预先写死，不从规则模板补答，不回退旧预设。

### 现成命令（未授权时仅使用默认本地命令）

```powershell
$root='C:\Project\Nebius'
$py="$root\.local\lighttry-development-20261011\cpu-venv\Scripts\python.exe"
$state="$root\.local\lighttry-joint-20261012\ai"
$pkg="$root\.local\lighttry-joint-20261012\manual-package-release"
& $py -X utf8 -B "$root\scripts\run_joint.py" --package $pkg
& $py -X utf8 -B "$root\project\next\runtime\joint_language.py" --state $state
# 以下均要下一轮新授权；先文字预算，仍不启 GPU。
& $py -X utf8 -B "$root\project\next\runtime\joint_language.py" --state $state --packet "$pkg\packet" --phase first --execute --approval-reference 'TEXT_APPROVAL'
# 展示差异后，填当次准确 operationId：
& $py -X utf8 -B "$root\project\next\runtime\joint_language.py" --state $state --phase first --apply --confirm-operation 'FIRST_OPERATION_ID'
& $py -X utf8 -B "$root\project\next\runtime\joint_language.py" --state $state --phase second --execute --approval-reference 'TEXT_APPROVAL'
& $py -X utf8 -B "$root\project\next\runtime\joint_language.py" --state $state --phase second --apply --confirm-operation 'SECOND_OPERATION_ID'
# 新鲜目录，保留原六项包；打包当次真实、已确认响应：
& $py -X utf8 -B "$root\scripts\prepare_joint.py" --out "$root\.local\lighttry-joint-20261012\ai-confirmed-package" --ai-applied "$state\second-applied.json"
# 守护、一次启动、新主机信任就绪后，复制 execution-disabled.json 为新的本地配置，
# 仅填已批准 enabled/model_license_ack/current guard directory，保持包SHA/taskId；
# 先验证包，再显式执行，不启动或重启 VM：
& $py -X utf8 -B "$root\scripts\run_joint.py" --package "$root\.local\lighttry-joint-20261012\ai-confirmed-package" --config 'C:\Project\Nebius\.local\JOINT_CURRENT_AUTHORIZATION.json' --execute
```

若 AI 验收失败，保留文字失败证据；可按独立批准范围执行已冻结手动6项包，不替换 AI 标签。新模型/上传/主机许可不能从旧授权继承。

## 条件与逐项结果证据

每项规范化参数、recipeKey、派生HDR SHA、实际 hdr_dir、注入site、envRot/envFlip/envStrength/logScale/版本、模型入口 env_ldr/env_log/env_nrm [1,3,1,704,1280] 的finite/range/float32 SHA、输出身份均持久化。实际解码/乘法/清理前/截断后/flip-roll 后最大值，按像素与按通道的截断比例；投影HDR、Reinhard/log输入截断统计也记录。helper和模型条件完全对齐才能 forward，错误路径/哈希/hook 缺失直接失败。条件和模型证据SHA写入原子完成记录，后续篡改拒绝，不追改历史。

独立单调计时：joint_initialization、condition_processing、joint_forward（CUDA同步边界）；上游 model construction/network/tokenizer nested spans 不能相加；result_write、逐项export-timing与本地transfer各自记录。每项立即写原子complete，并经旧受守护160KiB分块传输自动取回，验证任务/配方/哈希、真实JPEG解码、1280×704与非恒定。后项失败不会丢失先前本地结果。

本地 comparison.html 在完成每项后更新；当前准备页六项均“尚未运行”，不会展示历史图片冒充新结果。方向/明暗/高光/阴影/颜色/主体保真人工逐项记录通过/失败/不确定；结构与视觉分别报告，不扩展材质研究。

## 时长、保护与费用

已实测同图复用两项：初始化275.881秒、首次生成8.123秒、第二项5.432秒、首次结果观察387.687秒、全部取回443.299秒。六/七项新增投影/审计/传输尚未实测，据此估计 RUNNING工作约10—15分钟，非保证。

复用 `C:\Project\Nebius\cloud\Start-TeaRunningGuard.ps1` / TeaRunningGuard / live_session_running：启动前ready、API心跳、防休眠；首次可靠独立RUNNING才锚定工作18/停机25/核验27分钟。启动等待上限600秒；另设不晚于守护启动后40分钟的绝对UTC保护，取较早截止，不重置、不延期、不再次启动。收费估算包含启动与停机过渡；完成取回立即complete提前停机，run_joint自动调用独立 Confirm-RunningStopped 并核验STOPPED/instances=[]、守护PID退出、防休眠释放，任何未核实保存stop-unverified并继续独立监督，不能宣布完成。

同VM里明确可快速修复、不会重复launch的本地小错可在固定剩余窗口内处理；进程不明、身份/哈希错误、重大环境改造、保护失效立即保全证据并停，不跳检查。执行目录排他、launch-attempt先写，不因未知响应重新发launch。

GPU估算沿用既有保守全资源$2.10/小时（不是本轮已确认账户报价）：10—15分钟约税前$0.35—0.525，加50%税费/不确定余量约$0.525—0.788；保守覆盖10分钟启动等待+27分钟RUNNING核验，约$1.295税前/$1.9425带余量。既有200GiB SSD停机仍计费，历史约$0.01945/小时，传输/存储/税率/折扣/账单未知另核对。

文字API沿用既有输入$0.06/百万、输出$0.24/百万估算：每次15000输入+40960输出上界约$0.0107304，4次约$0.0429216税前/$0.0643824含50%余量，建议文字预算$0.08。reasoning已包含completion，不重复计费；usage缺失保留未知费用预留。本轮没有文字消费。

建议下一轮 GPU预算$3 + 文字$0.08，总$3.08；GPU和文字单独账本，旧失败启动费用不并入新授权。预算是授权与估算，时间保护/请求上限**不是账单硬上限**。2026-10-12只读官方价目页说明价格不含税、停止计算不停止存储计费；具体本账户shape/折扣/税费仍未查询。官方来源：[Compute定价](https://docs.nebius.com/compute/resources/pricing)、[Token Factory模型](https://nebius.com/services/token-factory/models/nvidia-nemotron-models-inference)。文字费率为已有实测记录依据，不声称本轮重新读到当前官方模型价格。

## 下一轮一次性确认清单

确认陶罐及上述输入/inverse；上传范围仅准备包 manifest 中代码、现成五G-buffer、已预处理photo.png、已有mask、来源/完整性/权重引用元数据、B—F及实际确认AI派生HDR（不上传原照全文、Key、认证文件或新权重）；确认现有HDR私有使用范围、Cosmos/Tokenizer实际模型许可；确认同一现有资源、仅一次启动、GPU$3/文字$0.08、600秒启动等待、18/25/27窗口及40分钟绝对保护；允许手动A—F和一项当次真实AI forward、无inverse重算/安装/下载/换模型/追加启动。新VM身份/服务器密钥仍按原流程单独确认。两轮建议出现后仍须各自确认参数应用，不由预算授权替代。

本轮停止在等待新授权位置。
