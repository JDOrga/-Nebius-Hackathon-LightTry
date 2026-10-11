# 可控性实验 v1（先验冻结）

对象仍为 Cosmos Diffusion Renderer；有限保真度，不替换主路线。2026-10-11 开始 HEAD `49d97ad34b72ffe81c8d79ff6151f0348c1fb9e4`，工作区干净；未发现适用的 AGENTS.md。最新现状调查保留在忽略的 `.local/product-audit-20261011/LightTry-现状调查-20261011.md`。旧失败验收及旧文字账本不改判、不续用。

## 第一小矩阵

先用既有 CC0 来源哑光陶罐、sunny，6 次 forward：基线、方向偏移 −45°、+45°、倍率 0.7、1.4、基线重复。不做全排列。第二材质金属壶只准备，第一矩阵有清楚响应才扩展。杯子不是判断基线。历史 inverse 子进程真实 exit=0，五通道和输入逐文件对照原始完整性账本；独立实验来源类型 `historical-four-materials`，不伪造产品 task，不放松普通 inverse 缓存规则。

保持输入 PNG 原字节、预处理、1280×704、15 steps、seed1000、guidance0、单帧、无 offload、五通道不变。每次 generate 前仍采用已有 `reset-before-forward-generate-v1`。新适配器包装官方 helper 调用，不编辑官方入口或 HDR 补丁。全部官方源码哈希、补丁后哈希与 HDR 内容哈希仍硬校验。

上游加载原始环境的约定是 `env_rot=180/env_flip=true`；方向偏移加在 180 上，最终 135/180/225，不是把 rotate_light 布尔当角度。变换顺序：解码浮点 → 倍率 → NaN/Inf 清理及 [0,65504] clamp → flip → 整像素 roll → 512 cubemap → 固定视角投影 → LDR/log 映射。倍率不是 EV，也不承诺成图亮度等比。

CPU 在实际 helper、完整模型条件分辨率上检查所有六项，记录 roll 的整数像素量、原始溢出比例、映射零值/饱和比例、条件哈希和差值。神经调用入口另逐元素检查 helper 输出确实变成实际 `data_batch` 中的 env_ldr/log（×2−1、维度转置），记录 env_nrm 哈希。输入条件有响应不代表成图有用。

## 冻结判断标准（不为通过而改）

1. 重复对照：照片有效区和既有主体内部 mask 上，记录 sRGB MAE、线性亮度分位数/均值、左右/上下分区、颜色通道和边缘差值；重复噪声作为参考，不只算全画布亮度。
2. 可辨性初筛：变体主体 MAE ≥ max(2/255, 3×重复 MAE)，且局部至少一个区域响应明显。此数字仅是进入视觉复核的阈值，不自动宣布用户可控。
3. 明暗趋势：低倍率主体线性亮度均值不高于基线、高倍率不低于基线；至少一档变化超过 max(0.01, 3×重复亮度差)，并检查10/50/90分位和高光剪切，不用平均值掩盖局部反向。
4. 方向：左右/上下空间差异或高光位置的变化需要对照图复核；不能从“+45”推断物理灯的左右位置。镜面与哑光分别报告；单材质通过不扩推所有图片。
5. 氛围/漂移：并排基线、原图、每档、差分及主体局部；观察轮廓、原颜色、纹理、材质、高光、背景、标签。任何新增明显轮廓断裂或材质重绘都留下失败项，不挑图。
6. 人工视觉判定与自动指标分开。助手看图只能标“助手视觉观察”；人工确认未取得时标待人工复核，不用模型自评充当人类结论。
7. 初筛失败不扩矩阵；有效档位待跨材质检查后才考虑生产能力白名单。能力尚未通过时，不大改 UI，不制造新参数效果预览。

## 执行边界

用户追加授权允许合理费用自主执行；本轮不复用旧预算。首次只启动现有 Devlab 一次，L40S AMD 1GPU/16vCPU/64GiB、既有200GiB SSD，不扩容。公开价税前 GPU $1.35/h + CPU $0.16/h + RAM $0.2048/h + SSD约 $0.01945/h，共约 $1.73425/h。保守按Intel CPU价包络 $1.76625/h。来源：[Nebius 当前公开价](https://docs.nebius.com/compute/resources/pricing)，不代表实际账单或确认税率。

本轮上限 $3（含税/不确定性包络），50%余量；约10–15分钟预计 $0.44–0.67 包络。首次独立 RUNNING 起工作18分钟、停止触发25分钟、核实目标27分钟；启动等待600秒，arm起45分钟绝对UTC保护截止。时间守护不是账单硬限；启动/停止过渡也入估算。完成马上取回、stop，不在 GPU 上等看图/讨论/写UI。安全、状态不明、认证拒绝、环境严重损坏或时间不足时保护性停止。现有守护先就绪，API归属/当前VM/公钥映射/精确本轮host pin后才上传。主机信任来源与是否独立验证明确记录。

上传白名单是冻结包的 `bundle_contents.json`：已有运行代码、独立实验适配层、来源证明JSON、单张既有预处理PNG、既有主体mask、五通道JPEG及权重参考；不上传原始大图、全部素材、秘密、历史机器日志或权重。取回限定JPEG/PNG/JSON/JSONL/log，不取原始张量。输出按case ID分目录，基线重复有独立身份。

认证已按用户授权在现有 wjx profile 恢复，并选回项目配置指定租户/项目；只读 API 已确认 STOPPED/instances=[]、资源与公钥匹配。Nemotron 后续若需要：新独立账本，最多12次、$0.20包络，最多一次修复/共享60秒；不关联旧账本、不先行发送。实验阶段不需要 Nemotron。

## 复现入口

- `python -X utf8 -B scripts/prepare_controls.py --out <新的忽略目录> --history <既有四素材执行目录> --config project/inference.local.json`
- 可选 `--sample 03_glossy_metal_teapot` 只准备第二材质。
- CPU依赖独立在 `.local/lighttry-development-20261011/cpu-venv`，没有改系统Python或云环境。版本与安装日志本地保留。
- `python -X utf8 -B scripts/check_controls_cpu.py --repo upstream --out <新目录>` 需要CPU torch/numpy/OpenCV/imageio/Pillow；实际执行与未执行项以本地进度和ledger为准。
- 使用既有 `cloud/Invoke-Cloud.ps1` 守护/捕获/传输/停机链；独立 `project/experiments/remote_launch.py` 只发起已受限实验进程，不管理VM。

最后交付的运行版、能力取舍、方案schema/迁移、真实桌面/窄屏截图、语言/产品/联合链路、费用和云终态仍分别验收。准备包不是最终产品交付。
