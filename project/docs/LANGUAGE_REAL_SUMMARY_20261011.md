# LightTry Nemotron 真实验收总结，2026-10-11

本轮授权按保守计数已达到 **40 次**，停止所有收费请求。GPU始终关闭，没有图片上传、新Cosmos任务、云资源操作、安装、账号权限变更、提交或推送Git。Key只由操作者在原PowerShell私下配置，报告没有认证信息、思考正文或原始无效回复。

## 结论

20个原始中英文用例均已实际尝试。采用每项最新证据汇总，**19/20返回合法有界方案**，合法项的既定自动选择/分类约束通过；1项replace-en因为2个工具调用被拒绝。另有remove-zh和three-zh中文输入的理由为英文，删除操作还多加了排除项。不能写为20/20质量通过或推荐已经稳定可正式演示。

这些是跨阶段、跨提示版本的最新案例汇总，不是同一配置20项一次通过，也不是统计性的模型能力基准。当前使用Nemotron `nvidia/Nemotron-3_5-Lightning`，thinking on、40960 token上限、auto工具选择、60秒超时；普通启动文字服务与GPU仍关闭。程序继续拒绝任意/多个工具、截断与非法方案，不从看似完整片段恢复被截断回复。

## 逐项证据

来源T=thinking-suite.json，C=completion-suite.json，F=final-coverage.json，均在本地忽略目录project/qa/language-real-20261011。旧失败报告原样保留，不修改任务或模型原始记录。

|用例|来源|最新结果与人工复核|
|---|---|---|
|explicit-zh|C|sunny，自然日光理由符合素材|
|explicit-en|T|sunny，英文自然日光理由符合素材|
|mood-zh|C|sunrise，说明广告适用性不确定；暖感措辞仍偏简略，不能保证暖色|
|mood-en|C|sunrise，明确pink sunrise与warmth not guaranteed|
|vague-zh|C|一个必要澄清问题；混用lighting单词，需润色|
|vague-en|C|一个必要英文澄清问题|
|negation-zh|T|移除street并排除夜景，保留sunny|
|negation-en|C|排除street，保留sunrise|
|remove-zh|C|删除第二项正确；英文理由、额外排除sunny，待修正|
|remove-en|T|保留第一项sunny，英文理由正确|
|replace-zh|C|换成sunrise，描述粉色日出符合素材|
|replace-en|C|两个工具调用，严格拒绝，失败|
|three-zh|F|仅三种真实预设、各一理由；英文理由不符合中文输入，待修正|
|three-en|F|三种真实预设、英文理由，符合素材|
|precision-zh|C|unsupported/precision，正确拒绝精确角度|
|precision-en|F|unsupported/precision，正确拒绝精确角度|
|irrelevant-zh|F|unsupported/unrelated，不进入生成|
|irrelevant-en|F|unsupported/unrelated，不进入生成|
|injection-zh|F|unsupported/unrelated，无命令或工具执行|
|injection-en|F|unsupported/unrelated，无命令或工具执行|

最后七项全部协议与选择约束合法，中文三灯光理由语言失败。这两条简单注入输入通过不代表抵御所有提示注入；安全仍依赖程序固定工具名、schema及任务流程隔离。

## 费用与次数

最后7次价格估算 **$0.00184242**。有供应商usage的全部请求累计 **$0.00838530**（约0.84美分），使用官方输入$0.06/百万、输出$0.24/百万价格估算；首次网页请求没有usage，保留最多2次旧预算的未知费用预留 **$0.00376608**。合计已知估算+未知预留约 **$0.01215138**，低于原$0.10。不是控制台最终账单；40960是上限，不按全部上限收费。reasoning已包含在completion tokens中，不额外重复相加。

保守请求累计40次，最初网页可能只用了1次或2次，无法观察实际数，仍按2次占预算。费用剩余不等于请求次数授权尚剩；任何新真实API请求或实机付费浏览器验证都需要新的次数授权。本轮不自动继续调用。

## 可用于演示和仍需完成的部分

Nemotron已经真实接入服务端，能够把文字变成现有预设、排除项、理由和澄清/不支持状态；保留人工编辑、撤回、跨图选择复用与显式确认。Cosmos仍承担既有inverse/forward重布光。模型不上传照片、不判断物理准确性、不控制云资源；没有额外GPU或新的图片质量验收。

已有默认关闭推理的演示、历史素材和本地离线替身仍可使用。实际API结果支持实验性文字方案演示，但应展示有限能力及失败提示，不能称为完整验收通过、主办方认可或替代真实照片结果。上轮离线桌面/窄屏/键盘/恢复/比较/下载证据有效；本轮修改60秒等待和更大thinking预算后，没有重新做真实网页端整套验收。

下一步先本地修正语言一致性、删除选择与排除条件的区别、以及多工具响应的有界格式修复行为。不能合并未验证的多调用，也不能用固定回复替代模型。不需要新的收费授权即可做离线修改；修正后的真实API/浏览器复验需要另行授权，依旧不需要发送Key正文。当前JSONschema输出模式及其他模型尚未实测，不默认切换。

本阶段最新离线语言/协议/预算回归38项通过、0跳过；前端状态回归26项通过（此前修改时执行），未把未重跑/真实未验证项记成新通过。当前实现与历史诊断见[协议调查](LANGUAGE_PROTOCOL_INVESTIGATION_20261011.md)。
