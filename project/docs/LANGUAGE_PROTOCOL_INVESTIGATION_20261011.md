# Token Factory 工具协议定位，2026-10-11

## 补测10次结果与最后7项覆盖（最新）

`completion-suite.json` 实际执行10次后停止：前9项工具协议与自动选择约束均通过，第10项replace-en返回**2个工具调用**，尽管请求禁用了并行调用，仍被程序拒绝；不能去重或合并未保存的参数、不能记为通过。reasoning和输出没有截断，协议稳定性仍存在偶发失败。

精确30度现正确返回unsupported/precision，不是unrelated；英文氛围理由现为pink sunrise且明确warmth not guaranteed，符合素材边界。中文氛围“温暖感，广告适用性不确定”比先前更保守，但暖色近似说明仍不如英文明确，保留措辞限制。中文clarification混用了lighting单词，属语言润色问题；中文remove-zh理由全部为英文，语言要求未通过，且把删除的sunny加入excludedIds，可能使后续替换过度排除，属于待修正方案语义。其余合法理由限于自然日光/粉色晨光，没有精确控制或修复承诺。

本轮已知价格估算$0.00297258；累计有usage价格估算**$0.00654288**，首次HTTP费用未知仍预留$0.00376608。累计预留**33次，剩余最多7次**。原20项已有13个独立用例被尝试，剩余7项未执行；不能把停止状态称为验收全通过。

最后覆盖入口：

```powershell
python -X utf8 -B project/tests/finish_language_acceptance.py --remaining
```

只发送尚未尝试的seven cases：three-zh/en、precision-en、irrelevant-zh/en、injection-zh/en。维持40960/thinking on/auto/60秒/零修复，最多7次，累计最多**40次**。最坏新增费用预留$.0751128，连同已知usage与未知预留约$.08542176，仍低于$.10；按实际usage继续释放预留。未知usage、网络/鉴权/限流/预算错误即停；某项格式/截断失败会记录为失败并继续下一项独立用例，**不会重试失败项**，这样不把未测安全类别一直留空。

报告`project/qa/language-real-20261011/final-coverage.json`存在后不可重复执行。旧replace-en失败保留，不能覆盖为pass；达到40次后停止所有收费调用，需要新的授权才能再做实机修复/浏览器付费测试。GPU始终关闭。语言/预算回归**38项通过，0跳过**；本轮代理没有新增收费调用。

## thinking on 六项实际结果与后续预算（最新）

`thinking-suite.json`：六项全部返回完整单工具方案，无截断，无额外assistant content；自动约束5/6、语言形态6/6。reasoning tokens每项373–1359，供应商completion（包含thinking）每项464–1445，总耗时2.938–6.375秒。实际六项输入6945、completion5673、其中reasoning5140 tokens；按公开费率六项约**$0.00177822**。40960是输出上限，没有按上限全部收费。

人工复核：明确sunny、不要夜景（选择sunny并排除street）、删除第二个（保留sunny）通过，理由限于已知日光素材。两个主观氛围选择sunny本身可以接受，但“温暖的日光，适合生活方式广告”和“natural daylight warmth”把素材效果说得过于确定，**解释诚实性需修正**。精确旋转30度返回unsupported/unrelated，拒绝动作本身安全，但应该归为precision，**分类约束失败**。不能把六项全部记为质量通过，不能宣称thinking单一参数已证明解决所有质量问题。

代码提示进一步要求暖色/广告用途只能条件性近似说明、不能承诺；明确“精确旋转30度 / rotate exactly 30 degrees”属于lighting precision，而非unrelated。仍真实调用Nemotron，没有按规则改写输出或把固定答案冒充模型。

当前累计预留**23次，剩余最多17次**。所有有usage请求累计价格估算**$0.00357030**；首次HTTP仍未知，保留其最多2次旧4096预算的保守费用预留**$0.00376608**。已完成六次的大额规划预留可以按已报告usage释放，不能把未花的钱持续当作已经支出。账单与价格估算仍有区别。

下一步在已配置Key的原终端运行：

```powershell
python -X utf8 -B project/tests/finish_language_acceptance.py
```

保持40960/thinking on/auto/60秒/不重试，先重验precision-zh、mood-zh、mood-en，再补六项之外的14项，共最多17次。全部跑完累计恰好最多40次。每次发出前检查“已完成请求usage费用＋未知费用预留＋下一次最坏费用预留”不超过$.10；下一次按输入15000/输出40960预留$.0107304。完成收到整型usage后用实际用量估算替换预留，允许继续；未知usage保留该次完整预留并立即停，错误亦停。若真实用量较大则可能不足17次，应如实报告预算停止，不扩大授权。

报告 `project/qa/language-real-20261011/completion-suite.json` 不可覆盖或重复。已有auto-suite等其他付费记录时拒绝旧基线；原已接受三项引用前一轮，新增14项和三个修正用例在本轮人工审查，最终注明证据来源，不声称20项全在同一提示版本一次通过。没有新增GPU或图片操作。

语言/预算离线测试**37项通过、0跳过**，包含费用预留释放、未知usage不释放、发送前计数、累计40次上限。原thinking报告保持原样，人工复核另存review-thinking-suite.json。这里还没有执行新的17次调用。

## 用户明确要求 thinking on / 40960（最新设置）

现将适配器可配置及缺省输出上限设为**40960 tokens**，thinking缺省 **on**，显式发 enable_thinking true；auto仅表示省略thinking模板参数、沿用供应商默认，不再暗中等于off。普通演示仍不创建语言适配器，服务仍默认关闭。旧终端若已设600/auto等环境变量，重启不会自动抹掉它们；正式本机启用时应明确更新环境变量。

```powershell
$env:LIGHTTRY_LANGUAGE_MAX_TOKENS = '40960'
$env:LIGHTTRY_LANGUAGE_THINKING = 'on'
$env:LIGHTTRY_LANGUAGE_TIMEOUT = '60'
```

服务端超时允许1–60秒，默认60；前端等待65秒，编辑/切图取消及防旧响应机制保留。供应商envelope硬上限提升至1MiB以容纳thinking输出，只记录reasoning长度/整数用量，不保存或显示思考正文。最终工具arguments仍4096字符、理由60/问题100字符；多调用、其他函数或length依然拒绝。这些变化不启动GPU、图片生成或云资源。

**原40次/$0.10总费用边界不提高。** 每项最坏输出40960按公开价格为$.0098304；把20项都按新上限运行会超原授权，因此当前不要执行旧auto整套入口。准备了6项显式thinking验收：英文明确选择、中英文氛围、中文不要夜景、英文删除第二项、中文精确控制。

```powershell
python -X utf8 -B project/tests/run_language_probe.py --thinking-suite
```

入口强制40960 / thinking on / auto / 60秒 / 不重试，最多新增6次，累计最多23次。已确认auto-suite还没执行；若之后出现auto报告则拒绝使用旧17次预算基线。此前17次按<=4096 token的保守规划预留约$.03201168，新6次按每次15000输入+40960输出预留$.0643824，累计约**$.09639408**，低于原$.10。费用条件在发送前检查，不把已经完成的旧请求用新输出上限重算。真实usage/账单与预留分开记录，初次HTTP未知usage保留。

报告：`project/qa/language-real-20261011/thinking-suite.json`，存在就拒绝再运行。完成后评估quality与thinking耗时，再决定如何分配剩余授权预算；不能因为6项运行完就宣称原20项全部通过。本轮没有发出新的收费请求。

语言/预算离线回归**35项通过**、前端状态回归**26项通过**，无跳过。旧的off、1000、4096设置是阶段历史，下方操作命令不要继续照旧执行。

## 输出预算调整：用户要求提高上限（当前执行设置）

用户指出不应持续卡1000输出上限。1000是本地适配器原限制，不是模型能力上限；此前以这个小上限反复判断真实请求可靠性并不充分。已把适配器可配置上限扩展至 **4096**（默认仍600，服务仍默认关闭），未运行的 `--auto-suite` 现在显式用 **4096 tokens / 20秒 / auto / 0修复**。仍是原20用例、最多新增20次，累计最多37次，绝不提高原40次/$0.10费用授权。

公开费率 $0.06/百万输入、$0.24/百万输出（[官方价格来源](https://nebius.com/services/token-factory/models/nvidia-nemotron-models-inference) 本次只读复核）。按每次输入15000、输出4096的保守规划预留为 $0.00188304/次；20项约$0.0376608，给全37次统一使用新预算预留约**$0.06967248**，低于$.10。这是规划预留；实际usage/未知首次请求仍分别记录，不能称为实际账单。max_tokens是上限，短回复并不会按4096全部收费。

影响：更多输出空间会增加最坏情况延迟和费用，不能保证修复重复正文或语义错误。wall timeout提升至原已允许的20秒，客户端已有25秒等待；不无限等。供应商envelope硬上限同步从32KiB升至64KiB以容纳较长JSON编码，不保存原始回复；工具arguments仍最多4096字符，理由60/问题100字符不放宽。

auto不是“无影响”：模型可以不调用工具或输出多个调用；程序仍拒绝这些响应，只接受唯一propose_lighting_plan、完整合法有界方案。没有任意工具执行或自动生成，也不改变Cosmos/GPU链；语义选择可能变化，须看这20项实际报告。禁止因为JSON片段看似完整就接受finish reason length。

命令仍为 `python -X utf8 -B project/tests/run_language_probe.py --auto-suite`。旧的1000描述是阶段历史，本次报告记录实际4096/20秒设置。已确认auto-suite尚未执行，旧报告没有改写。语言/预算回归**34项通过**，0跳过。此调整本身没有发出新的收费请求。

## 完整语义验收的新证据与 auto 对照（最新）

`reviewed-suite.json` 执行 3 项后停止：中英文明确选择均返回 sunny，语言与理由均通过人工复核（中文只描述公园日光场景；英文为 Daytime park natural daylight mood），没有精确参数或材质修复承诺。中文氛围项却被截断。

这次摘要提供更精确的失败形态：氛围项 **reasoning tokens 为 0、reasoningChars 为 0，arguments 为完整 132 字符 JSON、六字段齐全、2 项预设/2 条理由，理由分别 7 和 9 字符；assistant content 达 932 字符**，总 completion tokens 达 1000，finish reason length。说明工具参数本身并不需要更大输出预算，输出消耗还来自独立 assistant content。不能从长度猜测这部分是解释、重复 JSON 或其他正文，因为未保存它。仍拒绝整个 length 回复，不截取合法片段当作通过、不让它进入生成。

新增3次，价格估算 $0.00048102；累计预留**17次，最多剩余23次**。已知 usage 价格估算累计 **$0.00179208**，首个 HTTP 的用量未知。原20项仍只有前三项被尝试，17项未执行。当前验收不能记为完整通过。

此前 full-auto 对照 contentChars 为0、方案合法，这为 auto 路径提供了候选依据；不是自动工具选择必然稳定的证明。代码增加环境变量 `LIGHTTRY_LANGUAGE_TOOL_CHOICE=fixed|auto`（默认 fixed）；auto 仍只提供一个固定数据函数，响应端仍拒绝无工具、多个工具、其他函数、截断及非法方案。无工具执行分发，不能调用生成、云资源或其他动作。新增提示不输出工具调用前后的 assistant 正文。

下一步在原私下配置 Key 的 PowerShell 执行：

```powershell
python -X utf8 -B project/tests/run_language_probe.py --auto-suite
```

该入口显式采用 auto、thinking off、1000 token、不重试，对20项同配置重验。最多新增20次，累计最多**37次**，保留剩余3次；规划预留约 $0.04218，仍受原40次/$0.10预算约束。任意接口/截断/结构错误即停，语义或语言失败如实记录。报告 `project/qa/language-real-20261011/auto-suite.json`，不得删除旧报告重跑。普通产品默认仍 fixed/600 token/关闭文字服务；是否建议改为 auto 须根据此真实报告决定，不偷偷切换正式默认路径。

语言/预算离线回归**33项通过，0跳过**；尚未真实执行 auto 整套用例。没有 GPU、照片或生成任务。以下为阶段历史，最新入口以上述 `--auto-suite` 为准。

## 六组真实对照的结果（最新）

操作者完成 `protocol-matrix.json`：**6/6 工具协议均合法**，每项恰好一个固定函数名，参数 JSON 完整，没有额外字段；最小方案全部选 sunny，两个完整方案也只选 sunny。reasoning_tokens 均为 0、reasoningChars 均为 0，完成输出仅 29–120 tokens，延迟约 1.078–1.968 秒。不存在这六项必须花满 1000 token 的事实。

新增 6 次请求，usage 价格估算 $0.0002994；累计预留 **14 次**、最多剩余 26 次。有 usage 的累计价格估算 **$0.00131106**，最初 HTTP 的 usage 仍未知。

结论：这组没有复现截断，不能确认固定 tool_choice、顶层模板参数或单工具 schema 是必然故障，也不能证明不存在间歇性问题。关 thinking 在这些响应中的证据是供应商报 reasoning 0。嵌套参数和 force_nonempty 与最小基线都成功，没有证据说明其中一个选项更好，因此不采用它们作为产品修复。原模板解析不兼容只是待证实假设，此次没有支持其为确定根因。

两个完整方案理由仍为中文，与英文 sunny 输入不符，语义/语言验收未通过。功能完整报告有效不等于产品能力已通过。full-forced 的 contentChars 为 101，但正文没有保存，不能断言其中是什么；产品只消费合法工具 arguments，从不执行或显示这部分任意正文。

对照请求均包含 store false，之前验收请求没有显式 store，因此存在这个请求差异和模型随机性；不能把“同 prompt 一次成功”解读为之前错误自动消失。产品现已显式 store false，与对照的隐私设置一致；这不是已证实的截断修复。

## 下一步：回复语言修正后的完整语义验收

预设素材描述统一为英文，中/英文输入根据是否含汉字提供显式 responseLanguage。这个确定性处理只指定回复语言，不选择任何灯光，也不替代真实模型回答；范围为当前中英用例，不宣称完整语言识别。中文交互中的 catalog 标签不改变。短理由/问题边界和非法输出拒绝保持不变。

在此前私下配置 Key 的同一个 PowerShell 执行：

```powershell
python -X utf8 -B project/tests/run_language_probe.py --reviewed-suite
```

运行更新后 20 项全部用例（因为语言上下文改了，需要同时验证中英文），固定原模型、工具路径、thinking off、1000 输出上限、不重试；最大新增20次，累计最多**34次**。规划预留约 $0.03876，非账单保证。接口/结构错误仍即停；语义 false、语言形态 false 和解释待人工审查分别记录，不一律记作通过。语言形态检测只查汉字与期望相符，不能替代人工语言/语义审查。

报告为 `project/qa/language-real-20261011/reviewed-suite.json`，发送前计数，不覆盖旧报告，不自动生成图片或启动 GPU。旧诊断入口禁止重复。新语言/预算回归 **31 项通过，0 跳过**；真实新上下文未执行。本轮不宣称已经定位唯一根因，也不默认开放真实文字演示。

状态：已完成官方资料与本地代码检查，已准备有界最小复现；本轮代理进程没有私下配置 Key，产品服务器当前也未运行，因此尚未发送新的收费请求。用户的“查吧”沿用原最多 40 次、$0.10、GPU 关闭授权；已预留 8 次，最多剩余 32 次。不得把下面的研究结论称为提供商故障已证实或验收通过。

## 官方材料支持什么

1. [NVIDIA 官方模型卡](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16) 说明 thinking 默认开启，提供关 thinking 示例；其工具调用示例还使用 `force_nonempty_content:true`，并说明需要配套工具/推理解析器。这个选项的效果和 Nebius 内部配置尚未验证。
2. [NVIDIA 当前原生 chat template](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16/raw/main/chat_template.jinja) 在无 thinking 时使用空 thinking 边界，工具正文使用 XML 标签及参数块。这说明推理后端须解析模型原生格式，不能断言 API 返回 JSON arguments 等同于模型原生生成 JSON。不能从公开模板推断 Nebius 实际部署的具体模板版本；当前原始模板也没有 force_nonempty_content 的显式分支，不能仅靠客户端发送该项保证有效。
3. [Nebius 函数文档](https://docs.tokenfactory.nebius.com/ai-models-inference/function-calling) 列出 auto 和固定函数选择。[REST 参数参考](https://docs.tokenfactory.nebius.com/api-reference/inference/create-chat-completion) 列出 extra_body；其页面没有展示 parallel_tool_calls，tool_choice 展示也比功能说明窄。公开文档不足以验证每种具体模型参数组合。
4. [OpenAI SDK 当前实现](https://github.com/openai/openai-python/blob/main/src/openai/_base_client.py) 把 SDK extra_body 合并进实际 JSON body。因而 NVIDIA 的 SDK 示例不代表 raw REST 必须把 chat_template_kwargs 放在名为 extra_body 的嵌套对象里；现有程序放在顶层符合 SDK 合并语义。nested 对照仅检查 Nebius REST 文档歧义，不能直接视为正确修复。
5. [Nebius JSON 指南](https://docs.tokenfactory.nebius.com/ai-models-inference/json) 要求按模型卡 JSON mode 标签选择支持模型；此前 Lightning 公开详情没有确认这个标签。因此本轮不默认切换 JSON schema、不更换 Nemotron、不依赖 prompt 输出任意 JSON 来绕过工具校验。

## 从已有报告能确定什么

固定函数工具路径存在单次成功、多工具、截断，以及合法结构却不遵循明确选择的结果。1000 token 下的最新失败仍为 length；返回一个预期工具调用不代表 arguments 完整合法。先前摘要没有 arguments 长度/JSON 完整性、reasoning token 或 reasoning 长度，无法区分生成过长、格式循环、解析问题及参数被忽略。不能根据未保存的原文做判断。

## 这次最小复现

独立 `project/tests/diagnose_language_protocol.py` 只在显式执行时调用官方 endpoint。固定模型、同一英文 sunny 输入、上限 1000、单工具、关 thinking、不重试；6 项为：

|对照|schema|选择方式|变化|
|---|---|---|---|
|minimal-forced-top|仅 presetId 枚举|固定函数|顶层模板参数基线|
|minimal-auto-top|同上|auto|只改变 tool_choice|
|minimal-forced-nested|同上|固定函数|模板参数嵌套 extra_body|
|minimal-forced-nonempty|同上|固定函数|增加 force_nonempty_content|
|full-forced-top|当前完整方案|固定函数|当前生产路径对照|
|full-auto-top|同上|auto|只改变 tool_choice|

完整请求通过现有适配器构造，不复制另一套业务提示。构造时使用明确标注的离线返回值，仅为取出请求 payload；报告的响应仍来自真正付费调用，离线构造值不会作为能力证据。所有请求不包含图片、路径、身份、日志、云资源或历史消息；Key 仅在 Authorization 中使用。store false，不引入 SDK 或依赖。

报告只存固定案例、时间、finish reason、工具数量、函数名是否匹配、content/reasoning 字符数、arguments 字符数与 JSON 完整性、已知字段名/数量/字符串与列表长度、reasoning token 整数（若供应商提供），以及 usage/价格估算。不会保存原始无效回复、任意字段名、任意工具名、content 或 reasoning 正文。完整方案只有通过现有严格校验与凭据回显检测才保存。没有工具执行、生成或任务接口。

格式和截断失败是这些不同对照的观察结果，继续下一项不是同一请求的自动修复。鉴权、限流、网络、超时、预算错误立即停。最多新增 6 次，总计最多 **14 次**；按输入 15000/output 1000 的规划预留，累计约 $0.01596，不是最终账单。请求发送前持久化计数，报告存在时禁止重复运行。达到原40次或规划费用$.10立即停止，旧报告保留。

在已私下配置 Key 的原 PowerShell 中执行：

```powershell
python -X utf8 -B project/tests/diagnose_language_protocol.py
```

结果：`project/qa/language-real-20261011/protocol-matrix.json`。完成后先审查差异，再决定修正哪个产品参数。脚本不会自动继续整套语义验收、改模型、开服务器或 GPU。原费用授权仍有效，不索要密钥正文；需要同终端执行是凭据环境传递限制，并非再次申请授权。

## 本轮离线验证

语言/协议/预算离线测试 **30 项通过、0 跳过**，新增覆盖比较变量独立性、发送前计数、六次上限、重复运行阻止、鉴权立即停、已知 Key 回显阻止保存、结构摘要不泄露 content/reasoning/未知键或工具名称。没有将离线结果记为真实 API 成功。GPU 与 Cosmos 后端不改。
