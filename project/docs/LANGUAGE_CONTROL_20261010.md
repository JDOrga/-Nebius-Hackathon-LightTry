# LightTry 文字灯光方案：本地交付，2026-10-10

**当前配置（用户后续明确要求）：输出上限40960，thinking on，默认60秒超时。** 服务仍默认关闭；原40次/$0.10总验收授权不变，最新显式入口为 `--thinking-suite`（最多6次），详见协议调查最新段落。旧off/1000/4096与25秒等待均为阶段历史。后续本机服务器启用时需更新原终端已有环境变量，否则旧变量优先。

**2026-10-11 最新结论：真实文字验收未通过，暂停付费重跑。** 累计预留最多 8 次；原 20 个用例只有 3 个独立用例被尝试，其余 17 项未执行。存在多工具、截断及明确选择不遵循问题，1000 token 下仍截断。手动选光和默认关闭服务继续可用，不能把离线交付写成真实 Nemotron 推荐已稳定。详见下面链接的最新结论；其中后续命令为阶段历史，当前不要重复运行。

2026-10-11 已获得小规模 Token Factory 费用授权，并进行首项真实请求；返回无效输出后按计划停止。当前结果与下一步诊断见 [LANGUAGE_REAL_ACCEPTANCE_20261011.md](LANGUAGE_REAL_ACCEPTANCE_20261011.md)。下文“未授权、未执行”及离线交付范围是 10 月 10 日的历史记录，不代表新验收已通过。

最新长度边界：理由 60 字符、澄清问题 100 字符，schema/服务端/前端均收紧；下文 180 字符是原离线交付的历史上限。真实验收默认关 Lightning thinking、禁用并行工具调用；普通产品输出 token 默认仍 600，独立 `--bounded-suite` 验收入口显式 1000，累计请求预算按此前记录扣除。

用户后续要求提高输出预算：适配器现在允许128–4096 tokens，未运行的 `--auto-suite` 显式4096/20秒/不重试；原40次/$0.10总授权不变。envelope硬上限现64KiB，方案JSON仍4096字符，理由/问题限制不放宽。下文旧1000/32KiB为历史限制，最新定位记录说明影响与费用预留。

本轮在 `C:\Project\Nebius` 当前代码上继续开发，开始时 Git 干净，未找到仓库或上级适用的 AGENTS.md。已阅读根/产品 README、DEVELOPMENT、架构、INFERENCE_INTERFACE、DEMO_HANDOFF、交付边界及最新批次说明；没有按历史交接重做迁移。未安装依赖、读取现有秘密、调用收费 API、启动云机/GPU、充值、创建 Key、修改权限、提交或推送。

## 实际职责与参赛演示

Nemotron 的职责是把用户文字和当前有限方案转换为现有 HDR 预设选择、简短理由、排除项、不支持项或一个必要澄清问题。Cosmos 的职责仍是既有 inverse / forward 重布光，沿用 TaskStore、driver、worker、多灯光批次、缓存、恢复、身份/哈希/过期/下载校验及守护链。文字服务没有图片输入，没有生成、开机或云资源控制工具，也不裁定照片的物理正确性。

这支持 Best Apps and Agents 方向的产品演示：需求 → 受约束的可编辑方案 → 人工选择/撤回 → 显式生成 → 已有比较与下载。不是通用聊天产品，也不声称主办方认可。Cosmos 真实历史批次证据继续使用原记录；本轮文字部分只做替身和离线契约验收，尚未完成真实 Nemotron 能力验收。

## 用法与本地启动

普通演示仍关闭推理及文字服务，打开页面和刷新均不会自动请求模型。若已装新版完整素材包，在仓库根运行：

```powershell
python -X utf8 -B project/server.py --assets-dir demo-assets-20261010
```

本机当前默认 `project/demo-assets` 是旧包，缺少白蓝杯文件；不会自动补图或覆盖。已有完整包可用：

```powershell
python -X utf8 -B project/server.py --assets-dir C:/Project/Nebius/.local/demo-candidate-20261010/isolated/project/demo-assets
```

路径可换成操作者自己的既有素材目录。新机器的素材导入步骤沿用 README；无云依赖。默认地址 `http://127.0.0.1:8765`，Ctrl+C 停止。端口占用加 `--port 8766`。`GET /api/inference` 与 `GET /api/language` 均应 `enabled:false`。

独立离线入口需要既有 Pillow，不新增依赖；不会被产品启动参数选择：

```powershell
python -X utf8 -B project/tests/serve_language_fixture.py --port 8788 --tasks-dir project/qa/language-20261010/new-test-tasks --assets-dir C:/Project/Nebius/.local/demo-candidate-20261010/isolated/project/demo-assets
```

打开 `http://127.0.0.1:8788`。页面醒目标识“离线文字测试替身 · 固定脚本，非 Nemotron 回答”，生成状态另有“非 GPU 结果”。替身是固定脚本与合成输出，只用于界面/协议验收，不是模型能力评测。测试任务与真实 `.tasks`、历史文件、完成/过期时间隔离；新目录便于重复验收。

在选光附近输入需求，点击“推荐 / 修改方案”，查看有序方案和理由。可勾选调整、撤回上一次方案修改，再另行点击“确认生成”。样例模式也能准备方案，原灯光按钮只切换查看。默认推荐 1–2 项；明确勾选“比较三个”或文字要求比较三个才允许三个。跟进只发送本条输入和当前有序选择/排除项，不拼接聊天历史。换照片保留方案，清空生成状态及本条输入、使旧推荐失效；复用的只有灯光选择。刷新后任务按已有引用恢复，推荐理由/撤回栈不持久化，恢复的任务选择标记为手动方案。

同照片已取回、身份相符、未过期的成功预设优先显示；确认只提交缺少结果的预设，仍是一个现有批次。后台每次结果访问继续验证文件，前端不会更改任务事实、完成时间或有效期。刷新后原文件不在浏览器时，缺少预设依旧需重新载入照片才能提交。没有符合条件的跨照片结果复用。

## 预设与能力边界

|ID|对应 HDR|允许说明|
|---|---|---|
|sunny|sunny_vondelpark_2k.hdr|晴日公园、自然日光氛围|
|sunrise|pink_sunrise_2k.hdr|粉色晨光、偏粉色晨光氛围；不能保证暖色或广告效果|
|street|street_lamp_2k.hdr|夜间街灯、街灯环境明暗与色调|

候选从真实 catalog 取 ID，只有与已知 HDR 文件名匹配的项才提供给模型；生成后端仍从 catalog 确定 index/hash。文字适配器不传 HDR 路径或照片路径，也不检查/上传 HDR 本体。不存在角度、强度、Kelvin、灯位或阴影数值参数。精确控制只能标明 `precision` 并说明近似，无法满足则拒绝；文字/材质/几何修复标明 `material_detail`。主观需求允许多个合理选择，以约束和诚实解释为准。

## 官方只读核对与真实配置模板

2026-10-10 只读访问公开 [模型 catalog](https://tokenfactory.nebius.com/models/catalog) 及 [Lightning 模型详情](https://tokenfactory.nebius.com/models/catalog/text2text/nvidia%2FNemotron-3_5-Lightning)，确认模型 ID `nvidia/Nemotron-3_5-Lightning`、Text-to-text、Public endpoint、Tool calling Available。这次是当前公开目录重新核对，不沿用历史候选假设。未登录、创建 Key、运行 Playground 或调用认证模型目录 API。公开目录不能证明用户账号当前有权调用。

[官方接口 quickstart](https://docs.tokenfactory.nebius.com/quickstart) 确认 Chat Completions 地址；[工具调用文档](https://docs.tokenfactory.nebius.com/ai-models-inference/function-calling) 给出明确函数 `tool_choice` 格式。模型详情没有明确展示 JSON mode，因此第一候选使用一个固定名称 `propose_lighting_plan` 的函数返回数据，后端只读取 arguments，**没有工具执行分发器**。任意其他名称、多工具、拒绝或截断都拒绝。可显式配置 `json_schema`，依据 [结构化输出文档](https://docs.tokenfactory.nebius.com/ai-models-inference/json)，但须另行验证选定模型，不能把通用文档视为该模型实测。

模板 [language.example.json](../language.example.json) 只说明环境变量，不会被服务器加载。普通启动连这些变量也不读取；必须显式加 `--language-service`。由操作者在服务端私下填写自己的现有 Token Factory Key，本轮不索要正文、不搜索文件、不创建 Key。不要把它放入前端、URL、日志、报告或配置模板。

|环境变量|默认/需填写|
|---|---|
|LIGHTTRY_LANGUAGE_ENABLED|`0`，授权后才设 `1`|
|LIGHTTRY_LANGUAGE_MODEL|程序默认为空；候选填 `nvidia/Nemotron-3_5-Lightning`|
|LIGHTTRY_LANGUAGE_ENDPOINT|`https://api.tokenfactory.nebius.com/v1/chat/completions`；仅 HTTPS，无凭据/query/fragment，禁止重定向|
|LIGHTTRY_TOKEN_FACTORY_KEY|操作者私下设置现有服务端凭据；无默认值|
|LIGHTTRY_LANGUAGE_TIMEOUT|默认 `60` 秒，允许 1–60 秒，整个推荐/格式修复共享预算|
|LIGHTTRY_LANGUAGE_MAX_TOKENS|默认 `40960`，允许 128–40960，每次调用硬输出 token 上限|
|LIGHTTRY_LANGUAGE_REPAIRS|默认 `1`，仅允许 0 或 1；总请求最多 2 次|
|LIGHTTRY_LANGUAGE_OUTPUT_MODE|默认 `tool`，或显式 `json_schema`|
|LIGHTTRY_LANGUAGE_THINKING|默认 `on`：明确发送 enable_thinking true；可显式 off。auto省略模板参数、沿用模型默认|
|LIGHTTRY_LANGUAGE_TOOL_CHOICE|默认 fixed，或显式 auto；两者均只允许一个固定数据函数，仍严格拒绝其他/多个调用。auto 的完整能力验收尚未通过|

授权后启用文字服务的启动形式为 `python -X utf8 -B project/server.py --assets-dir <目录> --language-service`；没有 `--inference-config` 时图片推理仍关闭。文字推荐只有按钮动作才发送，启动/刷新不会调用。模板不是授权，也不是已验证模型连接。

## 协议与校验

`GET /api/language` 仅返回 `enabled/developmentTestMode/message`。`POST /api/language/recommend` 沿用本机 Host、Origin、X-LightTry-Token 检查；UTF-8 JSON body 最多 8192 bytes、读取限 5 秒，拒绝分块和额外字段。请求恰为 `{text,currentPlan:{presetIds,excludedIds},compareThree}`：text 1–600 字，两个有界、去重的当前列表，显式比较布尔值。默认不发送照片、原照名称/路径、身份、云资源、日志、认证或历史消息。已知服务凭据误粘到输入时阻止发送。

模型只能给出六个字段：`status` 枚举 `ready/clarification/unsupported`、`presetIds`、与之对应的 `reasons`、`excludedIds`、`unsupported` 枚举列表 `precision/material_detail/unrelated`、`question`。严格验证字段集合、类型、当前候选枚举、数量、重复 JSON 字段/列表项、选择与排除冲突、理由和问题长度（180 字）、状态间约束。解释为简短纯文本，拒绝控制字符、代码围栏、URL、明显绝对路径和常见shell命令标识。文本模式检查不能保证语义诚实，实际理由仍需真实用例人工验收；任何文本均不执行。非法回复不改变方案，更不能进入生成。前端再次检查并使用 textContent 显示理由。

一次初始请求，只有格式/结构非法才最多补一次；补请求仅带原始有限上下文和固定格式提示，不回传非法回复。鉴权、限流、网络/超时/上游错误不自动重试。返回 envelope 最多 32 KiB、方案 JSON 最多 4096 字符；truncated/refusal 拒绝。响应正文及错误不入日志，错误仅用固定脱敏消息。服务端排他锁防并发点击；前端请求令牌、取消和方案修订防晚返回覆盖，手动修改/撤回/换图或等待期间编辑输入/比较选项都会废弃旧推荐。推荐不导入任务执行模块，不持有 TaskStore。真实网络调用另有墙钟等待上限，慢 DNS/响应头或分段回复不能无限挂住 HTTP 请求；超时不取消供应商已经接受的推理。网络操作尚未结束时保持文字服务排他锁，返回 busy 阻止重叠付费请求，不自动再调用。

## 已验证与未验证

最终测试结果及截图见 [LANGUAGE_ACCEPTANCE_20261010.md](LANGUAGE_ACCEPTANCE_20261010.md)。中英固定用例在 `tests/language_cases.json`，20 个文字输入，覆盖选择、主观氛围、模糊、否定、后续删除/替换、三个比较、精确控制、无关和注入。撤回/跨图/晚响应/任务复用另由 Node 与浏览器检查。替身通过不表示 Nemotron 理解这些表达；它只说明协议和界面能处理这些情形。

未验证：真实 Key/账号授权、模型具体函数/schema 行为、推理 token 消耗与实际推荐品质、真实限流和实际网络延迟、文字方案到 Cosmos 的新 GPU 批次、跨机器实机。本轮不重新验收既有真实生成矩阵或云守护停机。原图文字/材质/几何变化仍是产品已知局限。

## 下一轮小规模 Token Factory 验收计划（未授权、未执行）

建议先使用当前公开可用的 Lightning 固定函数模式。价格来自公开 [模型详情](https://tokenfactory.nebius.com/models/catalog/text2text/nvidia%2FNemotron-3_5-Lightning) 及 [官方 Nemotron 价格页](https://nebius.com/services/token-factory/models/nvidia-nemotron-models-inference)：输入 $0.06 / 1M tokens、输出 $0.24 / 1M tokens（2026-10-10 核对）。开测前重新核对账号可用性和费率。

20 个中英文用例，各一次主请求；最多每项一次格式修复，**总计最多 40 次付费请求**，包含首个协议连通用例，不额外发测试/自动重试。若首项拒绝函数/schema，先停止分析，不自动换模型。每次输出 600 tokens，总预算 12 秒；输入按每次约 2500 tokens 估算（包含修复），上限场景估算 `40 × (2500 × 0.06 + 600 × 0.24) / 1e6 = $0.01176`，约 $0.012。输入 token 是估算，实际计费/推理 token 以供应商 usage 为准；建议批准费用上限 **$0.10**，达到 40 次或费用上限即停止。不同模型/更大输出预算需要新的决定。

记录仅保存用例 ID、合法方案、调用计数、延迟、usage、估算金额和脱敏错误；人工检查否定/连续修改遵循及解释诚实，不把 subjective mood 设为唯一预设答案，不评判图片物理正确性。测试照片与 GPU 保持关闭。必要授权：允许通过本机现有私下环境凭据向该官方 endpoint 发送这 20 条非敏感测试文字及当前方案；批准最多 40 次、$0.10 的 Token Factory 费用；无需开云机/GPU、无需新 Key 或账号权限变更。真实图片生成另需按既有守护流程获得独立授权。
