# 下一轮五项调光校准 + 独立 Nemotron 上下文验收

2026-10-13 状态：**本地准备与离线验证完成；实机/真实文字调用等待新授权**。本轮云机启动、上传、收费请求、依赖安装、提交和推送均为 0。旧 B/C、七项实测及旧授权/追加账本原样保留；本页和新 checkpoint 是新增汇总，不改写原始历史证据。

## 冻结的唯一下一轮 GPU 包

- 包目录：`C:\Project\Nebius\.local\calibration-20261013\final-five-package`
- 唯一拟上传归档：`C:\Project\Nebius\.local\calibration-20261013\final-five-package\inference-code.tar.gz`
- SHA256：`d6bbe491c660a4610fe8e3b5e75c65ff1e1ffd03659b2d828a1905a3603a054f`；1,344,217 字节；70 个文件，解包后清单集合、每项大小和 SHA 全部核对。
- taskId：`8479bb274c3e40b08c217521deeb21a0`。
- 实际 worker：`C:\Project\Nebius\.local\calibration-20261013\final-five-package\packet\project\next\runtime\joint_worker.py`，SHA256 `b5436b4f5337fbec100c726a304517df7c04c55fe093f1874c09b066bbeb6c34`；与当前源码一致。解包 worker 的真实 `--help` 与解包校验器均执行成功，识别五项版本 `direction-energy-calibration-five-v2`。
- 真实生成链：`C:\Project\Nebius\scripts\run_joint_batch.py` → guarded `joint_launch.py` → 包内 `joint_worker.py --joint` → 包内 `joint_entry.py` → `joint.session` → 固定 upstream forward renderer。不使用旧四项包或旧单方案 worker。
- 无 GPU 调度：解包后的真实 launch 函数通过 **Popen 截获的 OFFLINE_SYNTHETIC** 核对 worker/`--joint`；五项 session 替身验证实际初始化计数 1、forward 5、inverse 0、顺序、逐项原子 complete、每项 RNG 复位与完成项复用。不是云端启动或真实推理。
- 审计：`C:\Project\Nebius\.local\calibration-20261013\final-archive-audit\audit.json`。其他 seed-local-only/早期 release 是本地构建中间件，不在授权范围，不作为执行包。

## 五项完整配方

沿用 Miss Kamola 的陶罐照片。原照 SHA `5e46330920891b48012b33ea28cf1f34ca282e8936cd2e25f06383681518ba90`；预处理 SHA `cbbfad2ba8e746586ecf8187a228c4fae5df7c8b41d1ee0b7e441d8006679cb3`。原照不重新预处理。复用历史 `2aa06a2c4e154ad0b03424c0d1d3dcca` 的五通道 inverse，没有重算或冷 inverse 回退。

全部为 schemaVersion 2、procedural、环境身份 null；稳定单光区 `key`、启用、白色 `#ffffff`、仰角 30°；global offset 0、strength 1、ambient 白色 0.03；全部处理版本与历史 C 原样一致。实际完整字段、recipeKey、HDR SHA、diff 见包内 joint.json，不以本表代替完整配方。

|执行顺序|方位|FWHM|主光 strength|RGBE 解码每通道球面积积分|峰值|
|---|---:|---:|---:|---:|---:|
|C-repeat|135°|25°|3|1.013828988407|3.015625|
|direction-225|225°|25°|3|1.013828988407|3.015625|
|direction-315|315°|25°|3|1.013828988407|3.015625|
|width-45|135°|45°|0.949618399143219|1.013829127662|0.9765625|
|width-70|135°|70°|0.4133734703063965|1.013828801533|0.44140625|

C-repeat 完整参数及实际 HDR SHA 与历史 C 一致。角宽沿用 24 次 RGBE 实际编解码迭代补偿，三个 RGB 通道均检查 ≤0.5%；两项最大相对误差分别约 0.00001374% / 0.00001844%。孤立底光参考的积分约 0.375827651318/通道（约 C 总积分 37.07%）；它不是最终量化 HDR 的精确可加分解，更不是物体受光能量。包内记录峰值比例、底光参考、实际字段 diff 和积分误差；生产投影、乘法、截断、mapping、模型条件统计仍须实机记录。

固定 Cosmos Diffusion Renderer / `Diffusion_Renderer_Forward_Cosmos_7B`，upstream `0f3e2dc435032ecbad654c2fc2153df85384b138`；seed 1000、steps 15、guidance 0、1 帧、1280×704、无 offload。远端权重沿用 historical_metadata：本轮未连接核对存续，也未扫描全部权重内容；同大小替换不能排除。禁止缺权重后下载、改模型或安装依赖。

## 基准、方向和角宽判定

先生成 C-repeat，再生成四个变体。实际同一 pipeline 对象在 retained constructor 中只创建一次；每项复位全局 RNG 后生成，逐项写 condition/model-condition/原子 complete，保留实际 modelObjectId 和初始化/forward 数。上游已有 reset-before-forward-generate-v1 继续保留，五项另记独立 calibration_rng_reset。无追加 forward、无自动再次 launch。

基准报告同时记录历史 C/本轮 C-repeat 的文件 SHA、解码像素 MAE/最大差/变化像素比例、是否解码相同、人工视觉差异。**相同 seed 不保证逐字节相同**。逐项核对原照/预处理、inverse 五通道、upstream/代码 SHA、模型/config、配方、实际 HDR、helper 与模型 env_ldr/env_log/env_nrm 身份、RNG 策略。身份/哈希错误先停止并留证；合法但明显视觉漂移则先核查输入/条件/RNG，解释不了就暂停依赖历史 B/C 的方向结论，不暗中补跑。历史与本轮两套 worker/entry/joint/entry SHA 都记录；本轮调度和观测代码有已知改动，不声称全部代码逐字节未变。

固定 ROI 直接取 2026-10-07 prepared_inputs.json 的 outline `[340,48,896,656]`、surface_texture `[455,242,816,506]`、bottom_contact `[428,545,816,691]` 和原 interior polygon。保存完整图归一化坐标与原照叠加图；每个新结果也保存叠加图。主体统计仅原 mask 与 surface ROI 交集，背景亮区不参与主体质心。ROI 叠加：`C:\Project\Nebius\.local\calibration-20261013\final-five-package\roi-overlay.png`。

方向的质心位移超过 ROI 宽度 8% **仅辅助，不自动通过**。人工必须填写主体明暗分布、遮挡、高光、投影阴影及理由，允许失败/不确定。结论仅这张照片和当前管线的粗方位；不得推广为任意照片准确左/右灯位。

角宽独立比较 **本轮 C-repeat / width-45 / width-70**；即便历史 C 不可比，仍单独核查当轮输入/config/inverse/RNG/normal 条件是否可比，再判断高光范围与阴影边缘。发射球面积积分相同不保证物体受光能量或最终照片亮度相同；绝不归一化输出照片来制造公平。允许无明显响应/不确定；无“物理柔光验证通过”状态。

`visual-review-template.json` 是人工输入模板；未填写不自动通过。结果报告在终态/实际计数/RNG 复位/结构检查均通过后才标 generated-five。execution、visual、workbench 是分开的状态；review_calibration 更新新增 summary，不改写原始 condition/complete/历史记录。

## 独立最小真实 Nemotron 上下文测试

准备状态：`C:\Project\Nebius\.local\calibration-20261013\text\scope.json`。独立入口：`C:\Project\Nebius\scripts\nemotron_context_acceptance.py`。模型仍为 `nvidia/Nemotron-3_5-Lightning`；本轮真实调用 0，未读取 Key。

第一轮明确以 **F 的完整实测方案**为当前方案，仅增加 fill.strength 来尝试改善主体暗面，理由必须与 F 补光抬亮暗面的实测记录一致；不承诺保色/物理准确。继续提供 C/F 两个完整参考和七项观察，绑定照片/recipeKey/输出 SHA；这些是实验文本记录，不是模型看到了照片像素。第二轮只在第一轮真实供应商账本、准确 operationId 确认应用及 scope/照片/当前值核对通过后，以实际已应用配方为输入，仅降低 fill.strength。主光、其他补光字段、全局字段和 ID 顺序不变；实际递归 diff 必须恰好一项。语义检查与完整 schema/范围/保留字段/来源/解释检查一起执行。建议需要逐轮确认；确认仅保存参数，不启动 GPU。

独立两次初始请求，每轮至多一次修复，总计 4 次；60 秒每轮共享超时。认证/超时/限流/上游错误不自动重试，未知请求不重发。新增账本不引用旧追加授权。transport 替身标 OFFLINE_SYNTHETIC_NOT_NEMOTRON，拒绝当作真实建议应用，不生成规则模板来替代模型。

输入完整 payload ≤15KB（包括修复上下文；不是精确 tokenizer 上限），费用暂按保守 15,000 输入 tokens/次与 40,960 输出 tokens/次估算，thinking on。**本轮遵守离线范围，未联网核价**。历史费率输入 $0.06/M、输出 $0.24/M 时：四次税前约 $0.0429216，50% 余量后 $0.0643824；独立建议预算 **$0.08**。授权时必须确认实际当前模型/账户报价；执行入口要求价格确认引用和两项实际报价。若实际报价高于固定会计费率，入口拒绝，先重新定价与申请新范围，不继承旧追加额度。未知 usage 保留费用预留，thinking 不重复计费。预算是授权/估算上限，不是供应商账单硬封顶。

文字先单独完成，GPU 未开启；不得让云机空等文字响应。需要超过四次必须报告具体失败原因，并另行申请新独立调用/预算范围。

## 执行后导入和收尾

复用现有 `next.accepted.load_accepted` 与工作台 mergeAcceptedLibrary；新增 additive load_accepted_many，支持历史包与新包同时导入。新稳定身份按预处理照片 SHA + **完整 recipeKey** + 输出 SHA 绑定，前缀区分本轮与历史；同包重复导入幂等，冲突/库满明确拒绝，不覆盖历史或用户方案。本轮 UI 名称独立显示“本轮校准”；用户重命名仍原样保留。

成功后先独立核实停机，再自动 stage_import 校验新/历史组合和重复导入，写 workbench-import.json；摘要标“verified-import-data-ready; live-studio-not-loaded”，不虚报浏览器已同步。重新打开正式工作室时通过下方 --accepted-package 复用已验证路径导入，浏览器按既有 merge 合并，历史仍显示。没有新照片时，本轮页面明确“尚未运行”，不拿历史 C 冒充 C-repeat。

准备对照页：`C:\Project\Nebius\.local\calibration-20261013\final-five-package\comparison.html`，现有历史 B/C 图可看，本轮五项全部尚未运行。未来取回/人工判定生成 execution/comparison.html，包含历史 B/C、本轮 C-repeat 和四个变体。人工判断不改变输出 JPEG 字节。

## 时间、费用和守护

复用最近真实七项时间证据：pipeline 初始化 **275.295 秒**，首次 forward **8.093 秒**，后续每项 **5.515–5.642 秒**，实际 condition 首次 0.769 秒/随后约 0.065–0.068 秒。此为历史观测，不冒充本轮实测。

一次初始化+五次 forward 的推算：纯推理约 **30.4 秒，建议留 30–60 秒**；模型加载约 **4–6 分钟**；条件/导入/写盘及进程开销另留 **0.5–1.5 分钟**；上传下载及传输握手暂留 **1–4 分钟**（本轮未实测）。保守预计 RUNNING 工作 **10–15 分钟**；启动和停机不计入纯推理，却必须计入费用。真实环境异常不可用这些估算放宽窗口。

建议沿用已验证工作/停机/核验 **18/25/27 分钟**，从首次可靠独立确认 RUNNING 起算；启动等待独立上限 **600 秒**；守护先 ready，API 心跳与防休眠先就绪。绝对保护不晚于守护就绪 UTC + **40 分钟**，取该绝对时刻与各 RUNNING 相对截止的较早者。所有截止一次绑定，不延期、不再启动。完成提前停机；独立核实 STOPPED、instances=[]、守护进程退出和防休眠释放，任何项未知则 stop-unverified，保留独立监督和证据，不宣布云执行完成。

范围明确、能快速修复、不会重复 launch 的小错可在同 VM 剩余固定窗口内处理；身份/哈希错误、远端进程不明、重大环境改造、费用/时间保护失效时停止并保全证据。没有额外推理、下载、安装或新启动。

GPU 独立建议上限 **$3**：按历史保守全资源 $2.10/h，启动等待 10 分钟 + RUNNING 核验 27 分钟约 $1.295 税前/$1.9425 带 50% 余量；按完整 40 分钟绝对保护估算约 $1.40/$2.10。已有 200GiB SSD 停机仍计费，历史约 $0.01945/h；税、传输、折扣及实际当前账户 shape/报价仍待确认。$3 覆盖估算余量但不是账单硬封顶；实际报价/固定资源成本不适配则重新申请，不能沿用旧预算。

## 可复制入口（本轮只执行无 --execute 的本地命令）

```powershell
$root='C:\Project\Nebius'
$py="$root\.local\lighttry-development-20261011\cpu-venv\Scripts\python.exe"
$pkg="$root\.local\calibration-20261013\final-five-package"
$text="$root\.local\calibration-20261013\text"
& $py -X utf8 -B "$root\scripts\run_joint_batch.py" --package $pkg
& $py -X utf8 -B "$root\scripts\nemotron_context_acceptance.py" --state $text

# 以下每项等待下一轮新授权；文字与 GPU 分开。
# $inputPrice/$outputPrice 是确认后的实际 USD/百万 tokens 报价，不猜填。
& $py -X utf8 -B "$root\scripts\nemotron_context_acceptance.py" --state $text --phase first --execute --approval-reference 'NEW_TEXT_SCOPE' --price-confirmed 'CURRENT_PRICE_REFERENCE' --input-price $inputPrice --output-price $outputPrice
& $py -X utf8 -B "$root\scripts\nemotron_context_acceptance.py" --state $text --phase first --apply --confirm-operation 'FIRST_ACTUAL_OPERATION_ID'
& $py -X utf8 -B "$root\scripts\nemotron_context_acceptance.py" --state $text --phase second --execute --approval-reference 'NEW_TEXT_SCOPE' --price-confirmed 'CURRENT_PRICE_REFERENCE' --input-price $inputPrice --output-price $outputPrice
& $py -X utf8 -B "$root\scripts\nemotron_context_acceptance.py" --state $text --phase second --apply --confirm-operation 'SECOND_ACTUAL_OPERATION_ID'

# 守护 ready、一次启动/新 VM 身份及服务器密钥独立确认之后才允许：
# 从 execution-disabled.json 创建新授权配置，填写当前 guard directory、
# enabled/model_license_ack，严格保留 taskId/包 SHA；本命令不启动 VM。
& $py -X utf8 -B "$root\scripts\run_joint_batch.py" --package $pkg --config "$root\.local\CALIBRATION_CURRENT_AUTHORIZATION.json" --execute
# 取回后在原模板副本填写人工观察；不运行模型：
& $py -X utf8 -B "$root\scripts\review_calibration.py" --package $pkg --review "$root\.local\CALIBRATION_VISUAL_REVIEW.json"
# 复用正式工作室导入，默认历史包仍保留，无 inference-config/key：
& $py -X utf8 -B "$root\project\start_studio.py" --accepted-package $pkg
```

### 一次性授权清单

1. 确认仅本包五项顺序，inverse 0 / forward 5 /初始化 1；没有 AI 配方 GPU 扩展或追加推理。
2. 确认拟上传**该 SHA 对应 70 文件清单**：代码/守护传输组件、已预处理 photo.png、已有 mask、现成五 G-buffer、五个派生 HDR、来源/历史完整性/权重引用元数据。历史 B/C 只传身份元数据，不传输出照片全文；不传原照全文、Key、认证文件或新权重。许可仍为现有私有研究范围，需确认现有素材/HDR 与 Cosmos/Tokenizer 许可。
3. 确认具体现有 VM/shape/账户费用、新 IP/VM ID/主机密钥、只启动一次，不沿用旧主机身份或旧范围授权。
4. 确认 GPU $3、600 秒启动等待、18/25/27 分钟窗口、守护 +40 分钟绝对保护、无延期/再次启动、异常停机规则及独立四项释放核验。
5. 独立确认文字模型/实际价格与输入输出上限、$0.08、两轮各最多一次修复/总四次、使用现有私有 Key 配置但不上传，旧追加范围不继承。每轮准确 operationId 的应用确认另给，不由预算授权替代。

## 本轮离线结果、未验证项与事务证据

新增 16 项 Python 测试、49 项受影响关键回归通过；6 项 Node 导入/保留字段/历史与本轮标签回归通过。最后 scope/幂等变动另跑受影响的小子集通过，不重复跑无关大验收。实际本地工作室重复加载历史包 API 返回 HTTP200/7 方案，临时自有进程退出；没有新校准照片。首轮测试替身缺 version/事件名错误已修正，失败记录保留；生产严格计划校验仍在。原四项旧包仍能验证，历史七项仍合法。

包解包/真实 worker help/真实入口默认执行/合成调度全部通过。仍未验证：新五项实际 CUDA forward、远端权重存续/内容、GPU 上实际噪声与历史重复性、真实视觉比较/角宽响应、新包真实上传/取回/停机释放、真实 Nemotron 上下文理解、实际账单价格及浏览器导入新结果。

主事务精确改动 `key_unknowns.recipes(environments, repeat=True)` / VERSION；BASELINE 为四项，MODIFIED 为 C-repeat 起始五项，ROLLBACK 恢复四项，三个相同输入探针 exit0；独立回滚副本 SHA 等于原始快照；原始 baseline 字节保留。原生补丁在仓库外独立 scratch 重建 modified 字节通过（最初仓库子目录 git apply 的路径前缀跳过问题保留错误记录并已纠正）。支持文件另有补丁和完整清单，不以主事务替代所有改动的说明。

新增四角色绝对路径：
- `C:\Project\Nebius\.local\calibration-20261013\MODIFIED_FILE.py`
- `C:\Project\Nebius\.local\calibration-20261013\DIFF_FILE.patch`
- `C:\Project\Nebius\.local\calibration-20261013\VERIFICATION.txt`
- `C:\Project\Nebius\.local\calibration-20261013\ROLLBACK.sh`

既有 status-watch 与 workbench-import 四角色保持原样并重新打开核对；本轮是这些已完成事务的新增补充，不改写历史 BASELINE/MODIFIED/ROLLBACK 行为。
