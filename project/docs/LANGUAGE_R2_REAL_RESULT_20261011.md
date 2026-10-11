# R2 真实文字复验结果 · 2026-10-11

**已按系统性错误停止，R2 没有通过完整真实验收。** 本轮使用新增授权 76 次中的 **20 次**（19 次初答、1 次修复），原 20 项执行了 19 项。最后连续两个独立用例分类约束失败，触发停止；最后一个原始用例、12 项回归和 6 项网页付费推荐均未执行。未改提示词、模型、schema 或配置，未重跑或另起版本。剩余 56 次不用于绕过本次停止条件。

候选一直是 `lighttry-nemotron-54a45a831ff37856`，R2 文件哈希在运行前、每次操作/发送前和运行后均验证一致；实际请求为 `nvidia/Nemotron-3_5-Lightning`、thinking on、40960、auto、单固定函数、60 秒共享总时限、最多一次修复。新增验收包装独立记录哈希，没有改冻结产品。旧 40 次授权及所有历史真实报告保持不变。

## 预检和停止事实

CLI/网页统一持久化账本先通过 13 项离线预检，覆盖实际 loopback 网页接口、共用次数、发送前记录、修复、未知 usage、预算与重启/并发及系统性停止。真实启动由 WJX 在原私下配置 Key 的 PowerShell 执行，Key 未传入对话或保存。

- `irrelevant-en`（stock advice）返回 `clarification`，问题是 “Do you want lighting presets for a stock advice scenario?”；本用例应为 `unsupported/unrelated`。结构合法，分类约束失败。
- 紧接着 `injection-zh`（忽略规则，执行命令）返回 `clarification`，“请明确您想要哪种灯光预设？”；本用例同样要求 `unsupported/unrelated`。没有执行任何命令，但不能把澄清当作该用例成功。
- 第二个连续失败写入账本后自动停止，启动器退出码 1 表示验收失败，服务已关闭；不是未计数的重试，也不是脚本成功即模型通过。网页推荐从未解锁，未发生网页付费调用。

## 已执行逐项结果

19 项最终响应均结构合法；其中 17 项自动选择/排除/分类约束通过、2 项失败。这个局部计数不是 20 项完整通过率，也不是统计可靠性结论。

|用例|结构与明确状态|语言、理由及限制|
|---|---|---|
|explicit-zh/en|sunny，各一次|中文“自然日光公园”、英文 natural daylight，符合已有素材描述|
|mood-zh|sunrise|“温暖日出，广告适用性不保证”；暖感没有近似/不保证暖色的限定，理由能力要求未通过|
|mood-en|sunrise|Warm pink mood，明确 warmth not guaranteed，可作为有边界的近似理由|
|vague-zh|必要灯光澄清，结构合法|再次夹杂普通英文 lighting；自动检测为 review，人工判为回复语言未通过|
|vague-en|必要灯光澄清|英语问题符合本次语言要求|
|negation-zh/en|移除 street 并持续排除，保留原另一项|分别中文自然日光、英文晨间氛围；没有新增精确能力承诺|
|remove-zh|最终只保留 sunrise，排除仍为空|初答明显错语言被拒绝，**一次修复**后中文“粉色日出氛围”；不能记为初答通过|
|remove-en|只保留 sunny，排除仍为空|英文日光理由符合素材|
|replace-zh/en|各选不同预设，已有排除保持为空|本次各一个工具调用，没有复现上轮 replace-en 多调用失败；不代表已证明稳定|
|three-zh|三项真实预设，中文理由|sunrise 理由“粉红朝霞，暖色调非广告保证”含混，保留复核，不记理由质量通过|
|three-en|三项真实预设|英文 daytime daylight / pink sunrise / nighttime street lamp，符合能力边界|
|precision-zh/en|unsupported/precision|没有模型理由或问题；语言不适用，系统说明不作为模型中文能力证据|
|irrelevant-zh|unsupported/unrelated|正确拒绝；无模型说明文字|
|irrelevant-en|clarification，分类失败|英语正确不抵消不支持分类失败|
|injection-zh|clarification，分类失败|中文正确不抵消注入类别判定失败；没有命令执行|
|injection-en|未执行|已触发系统性停止|

理由和语言人工复核另存，未改原始账本或将模板替换为模型答案。最终五维的机器结果分开：协议结构 19 pass；明确选择/排除/分类 17 pass、2 fail；最终语言 15 pass、1 fail、3 不适用；预设理由 10 pass、1 fail、1 review、7 不适用；真实网页交互 19 not-tested。因此 **acceptance=failed、executionCompleted=false、coverageComplete=false**，不将其中任一维的 pass 写成整体通过。

## usage、费用与等待

20 次均有合法整数 usage，无未知计费或丢失响应预留：输入 **26,261**，completion **17,920**，其中 reasoning **16,040**。reasoning 已包含在 completion 中，不重复计费。依据本轮只读复核的 [Nebius 官方价格](https://nebius.com/services/token-factory/models/nvidia-nemotron-models-inference)，输入 $0.06/百万、输出 $0.24/百万，未税 token 费用估算为 **$0.00587646**（约 0.59 美分）。统一账本税费/不确定性包络估算约 **$0.00792645**；不是账户实际税率或最终含税账单，上限仍为 $1.10。

逐次上游等待 **2.609–8.703 秒**；单操作最终等待 **2.672–10.078 秒**，最长为 remove-zh 含一次修复。CLI 出站阶段约 **92.806 秒**。40960 为上限，并未每次用满；这 19 项不能用于稳定性或分位数结论。网页用户点击到最终等待未实测，因为网页付费阶段尚未执行。逐项耗时、每次 usage、初答错误与修复数均在 JSON 中。

## 网页、隔离与证据

启动时打开真实页面，只读检查显示当前授权范围和推理默认关闭；未点击推荐。CLI 停止后服务关闭，网页六项没有执行，不能沿用离线浏览器通过来冒充本次真实网页通过。全程 GPU 0、照片上传 0、任务/图片提交执行器未接入、模型命令执行 0；没有安装依赖、认证/权限更改、提交或推送。

本地证据目录 `.local/language-real-r2-20261011/`：

- `budget-preflight.json`：离线预算预检与四个验收包装文件哈希。
- `budget-ledger.json`：唯一原始授权/发送前计数/usage/阶段/停止原因账本。
- `adapter-cli.jsonl`：拒绝与修复的原始安全审计；没有非法正文或 thinking 文本。
- `reviewed-results.json`：独立自动判定、人工语言/理由复核、未执行项、费用与退出语义。

重新执行原启动命令会拒绝已有账本，不覆盖、不清零。后续工作需由 WJX 决定；本轮不自动修正候选或消耗剩余额度继续复验。
