# LightTry 参数化调光台（2026-10-12）

## 运行与范围

`python -X utf8 -B C:\Project\Nebius\project\start_studio.py`，http://127.0.0.1:8785 。默认 Nemotron/GPU 关闭。本机默认 Python 无 NumPy时，启动器只复用既有 `.local/lighttry-development-20261011/cpu-venv`，没有安装。实际已启动正式服务；若该现有环境不存在，明确报错，不静默安装。旧 AI 入口、浮动面板、多轮、预算、去重、显式应用、来源／下载与原照片逻辑保留。

开始 Git status 为空；无 AGENTS 文件（工作区和上级均已检查）。已阅读 README、正式集成与最新聊天记录。原任务、素材、历史证据不迁移覆盖，不 reset、commit 或 push。新增浏览器测试方案为本地参数，没有新生成照片。自建 HDR 的本机导入不是用户照片上传，更没有发送到云。

## 能力表

|能力|已有实际路径|本轮新增|尚待模型验证|
|---|---|---|---|
|环境|路径／倍率／旋转进入上游 helper|内容身份库、RGBE导入、实际缩略图、0–360数值／滑杆、0.25–4倍率／输入−2～+2EV|连续区间的照片质量；方向与照片左右的校准|
|程序化|同一环境条件预处理|线性float32球面Gaussian光区＋底光，最多3灯，颜色、角宽、开关、命名与主补／轮廓起点|照片观感、阴影响应、各材质稳定性|
|任务|严格 inverse 复用、forward身份、守护、结果proof|衍生HDR打包／哈希／worker真实helper替换；有界同pipeline多配方session函数|新的GPU端到端及session真实单初始化|
|聊天|Nemotron结构化、一次修复、多轮和过期机制|完整v2或相对操作，可信快照解析，与手动同入口校验，递归逐项差异|真实付费Nemotron能否稳定遵循新契约|

输入EV仅为HDR倍率对数，**不是输出照片曝光保证**，没有lux、瓦数、近距衰减、真实灯距或柔光箱尺寸。角宽为球面Gaussian FWHM；颜色选择器按sRGB传递函数解码到线性RGB。不提供伪色温。

## Schema 与资源边界

外层方案仍为schemaVersion=1及原planId/version/inputId/parentVersion，以免删除旧浏览器库；parameters新增显式schemaVersion=2：

```json
{"schemaVersion":2,"mode":"procedural","environmentId":null,"environmentSha256":null,"offsetDeg":0,"strength":1,"ambient":{"strength":0.03,"color":"#ffffff"},"zones":[{"id":"key","name":"主光","enabled":true,"azimuthDeg":45,"elevationDeg":30,"strength":3,"color":"#ffffff","sizeDeg":25}],"synthesizerVersion":"sphere-gaussian-rgbe-v1","preprocessingVersion":"flip180-pixel-roll-log10000-v1","colorConvention":"linear-srgb-rgbe;picker-srgb-decoded-v1"}
```

环境模式指定库id和原内容SHA。旋转／方位有限数字规范到[0,360)，360=0、负角周期归一化；倍率0.25–4，底光0–4，单灯0–16，仰角−90～90，角宽2～120°。最多3盏、id唯一、名称40字。拒绝bool冒充数字、NaN、Infinity、未知／缺失字段、未知处理版本、任意路径。

导入只支持 `Radiance RGBE .hdr`、标准`-Y +X`经纬方向、2:1、最大4096×2048、32MiB、有限非负输入≤65504。不支持EXR、其他方向、复杂旧RGBE run或任意格式；明确拒绝，不猜测格式。最多64个新增资源、原文件总额256MiB。程序化固定512×256；RGBE落盘是线性浮点HDR的确定性有损量化，记录衍生字节SHA，CPU实测量化误差有界。原文件单独保留，标签、来源、缩略图、原SHA／衍生SHA分离；同文件名不同内容不合并。

发现现有晴日HDR峰值851968、街灯92672，均超出原helper的65504上限。**保留既有素材与上游clamp，不偷偷归一化原素材**；新导入限制65504。增加强度可能导致条件饱和，实验范围不是无截断或质量保证。兼容旧配方实际输入倍率／偏移不变。

## 身份与兼容

服务端 `lighting.normalize_parameters → light_console.normalize` 是统一入口；前端只能编辑草稿。AI的rotate/exposure/add_zone/edit_zone/remove_zone/set从可信当前快照解析；未指定值保留，非法操作拒绝或修复／澄清。完整建议也会被规范化。

recipeKey包含全部v2字段（包括模式、内容SHA、保留的非活动参数、处理版本和色彩约定）；可保守产生冗余缓存，但不会误借不同条件结果。角度受源图整数像素roll精度约束，亚像素参数可能产生同一条件而不同recipeKey；没有伪称亚像素旋转实现。

程序化／导入衍生HDR按内容SHA校验；`SchemeExecutor.prepare_request`写当前job的`inputs/lighting.hdr`，bundle真实携带字节，worker/entry再次查哈希，替换正在执行的`module.process_environment_map`的`hdr_dir`，再经condition_hook传入旋转、倍率与固定flip。不是改未执行的上游函数。现有固定sunny index仅作为原严格worker预检的载体，`carrierEnvironmentId`与实际环境身份明确分开；载体从不作为新配方照片匹配依据。

forward identities已有整个preset和runConfig，现在覆盖规范配方及衍生SHA。结果proof校验实际helper元数据、env_ldr/env_log/model-entry张量与衍生SHA。inverse身份仍仅由实际RGB、画布、inverse模型／tokenizer、相关patch、seed/steps等构成，光照不进入inverse键。

旧三字段参数没有批量转换；0/45和1/0.7仍产出原规范对象／recipeKey，历史实验专用normalize及CASES保留。编辑时才产生v2新版本，原图、旧版本、来源、任务文件和验收账本不覆盖。新v2不会把旧名义照片当新结果，即使部分输入意义相同也保守待生成。刷新恢复v2及导入库已测。

## 实际验收

- Python237项通过（原220＋新增17）；Node56项通过（原52＋新增4），node语法、git diff --check通过。
- 使用固定commit `0f3e2dc435032ecbad654c2fc2153df85384b138`实际下载的utils_env_proj/rendering_utils，应用**现有**HDR采样patch；9组真实HDR解码＋512cubemap＋64×128投影＋model-entry布局／归一化在CPU上完成，无假helper、无神经模型。0/360 SHA全等；90°、强度边界、蓝色、开关、角宽、主补光都改变env_ldr/env_log与最终布局SHA。见cpu-condition-report.json。
- 非对称单亮点数学检查：32像素宽，flip＋180°后峰值列11，额外+45°后列15；记录的是图像坐标，未标照片左／右。接缝、极点、sRGB线性转换、确定性、资源限制、坏文件、未知路径及旧身份一致性通过。
- 新增真实SchemeStore提交／重启和SchemeExecutor准备的**本地接线**测试，校验衍生字节实际落盘；transport为隔离stub，不等于GPU。session单构造测试同为明确数学stub。
- 正式浏览器实际数值输入123.4°／−0.5EV，360应用归零，拖动主光45→287°且未应用时版本不变；主补光、选补光、角宽65、开关保存刷新、合成HDR导入／来源SHA、CPU验证、旧真实结果比较、390窄屏均操作。窄屏scrollWidth375≤innerWidth390。程序化照片区明确待生成／仅输入，下载禁用；无照片CSS亮度或色调替身。
- 截图：environment.jpg、procedural.jpg、procedural-controls.jpg、narrow.jpg、compare.jpg；都是运行中的正式页面。environment截图的草稿尚未应用，旁边旧真实结果仍明确属于当前方案。

修复保留日志：默认Python缺NumPy；第二服务锁冲突（使用副本验收）；锁文件读PermissionError（排除.server.lock）；旧实验normalize负角回归（恢复原实验函数，连续预处理另分入口）；固定commit patch初次在子目录被Git忽略（改显式--directory并核验代码）；缩略图局部sha变量遮蔽（改digest）；GPU包准备误用默认Python（复用现有CPU环境重跑）。没有以这些错误绕过认证或付费边界。

**未验证**：神经模型照片效果、新Nemotron真实质量、GPU1280×704条件／forward全链、CUDA内存和跨多配方实际模型初始化次数、所有HDR编码变体、真实移动设备软键盘。当前本地upstream Git HEAD不是用户固定commit；没有reset它。CPU测试用独立固定commit源码；以后GPU仍须原guard验证固定commit、权重和patch，不能拿这个本地checkout直接冒充通过。

## 下一轮最小包（不是费用授权）

`.local/lighttry-console-20261012/gpu-minimum/plan.json`与7份规范recipe、2张真实程序化HDR已生成并查SHA。采用一张已有许可且inverse证明完整的哑光照片：环境基准、90°、240°、0.25、4、单主光、主补光，共7次forward，**0次inverse（缓存不匹配就停止）**。相同seed1000/steps15/guidance0/1280×704/1帧。新 `run_recipe_session` 有界≤8，复用一个pipeline；生产HTTP继续单方案提交，不自动打开实验批次入口。真实session须在下一轮新守护授权下把7份state roots与inverse proof绑定，当前包尚不是可直接开云的授权包。

历史matte记录网络加载约273秒，每次生成约5–8秒，仅作估算参照。建议同级环境纯模型约6–10分钟，连预检、传输、启动／停机预留10–20分钟；工作截止30分钟。建议**含税／不确定性上限$3**，先按届时实际HOST_RATE确认可覆盖启动、运行、停止和50%余量，不沿用历史价格或授权；不够就缩短或另请批准，绝不自行提额。不测聊天则Nemotron0次；另测新契约最多4次初始＋各最多1次修复（最多8次），建议新独立$0.20账本，不复用历史账本。

缺新授权、inverse/权重/commit/patch/condition不匹配、非有限值、OOM、守护过期、费用余量不足均停止；单结果失败先留证并停止，不自动全排列重试，也不推论整个参数空间不可用。完成立即取回核验并停机，不在GPU上等讨论。需要额外批准的只有新收费GPU/模型、云机生命周期／相应素材传输；本轮全未执行。

## 四角色与连续性

本轮补充集合：`C:\Project\Nebius\.local\lighttry-console-20261012\MODIFIED_FILE`、`DIFF_FILE.patch`、`VERIFICATION.txt`、`ROLLBACK.sh`。独立副本同一输入continuous-probe-v2：BASELINE拒绝123.4°／0.707输入；MODIFIED接受；ROLLBACK恢复拒绝，均exit0/stderr空；恢复hash与patch重建逐字节核验。这是参数入口行为，不是神经质量测试。回退只对明确目标副本执行，不盲目覆盖用户后续修改。

原聊天四角色仍在 `.local/lighttry-chat-20261012` 并已重新读取，未替换：历史BASELINE旧侧栏、MODIFIED浮动多轮、ROLLBACK旧结构，各exit0。更早集成／polish集合也重新读取；历史实验fixed-fixture-v1仍BASELINE1/MODIFIED6/ROLLBACK1、各初始化1、exit0，未重跑且不当作此次GPU证据。
