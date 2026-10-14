# LightTry 限定文字演示 · 本地收尾与冻结（2026-10-11）

本地准备完成，真实复验尚未获准或执行。R2 原验收仍为失败，原始分类、费用、响应和停止原因不变。本轮真实请求 0、费用 0；没有 GPU、照片上传、依赖安装、提交或推送。原有工作区修改全部保留。

当前独立候选：**`lighttry-nemotron-a755c1ca7f99ff17`**，完整代码、提示词、schema、配置与用例 SHA256 见 [冻结清单](LANGUAGE_CANDIDATE_20261011_DEMO.json)。未提交代码，以工作文件哈希冻结；真实验收不得边测边改。历史 R2 清单及报告仍保留。早期本轮离线报告属于准备阶段，只有 `offline-final-*` 与这份最终清单对应，不能混合结果。

## 本次变化与产品边界

产品修改集中在 `language.py`：理由简短描述公园日光、粉色日出氛围、夜间路灯；粉色日出的近似暖感可接受。不再强制每句话附“暖色/广告不保证”等固定免责声明。仍禁止广告适用性、材质保真、精确灯位/角度/强度/色温等无依据承诺。中文提示要求避免 lighting 等普通英文，技术 ID 保留。模型实际理由原样返回，不用固定理由替换。

保留明显错语言拒绝、严格单函数/完整 schema 校验。格式、语义、语言与本轮安全边界共同最多一次修复，操作共用 60 秒总期限，修复只用剩余时间，网页 65 秒取消。模型、thinking on、40960、auto、parallel false、store false 均不变。普通启动文字和推理仍默认关闭。

下一候选仅在无关/注入用例允许 `unsupported/unrelated` 或灯光选择澄清。`demo_policy.py` 不以出现“灯光”就判成功：股票建议续问、命令、凭据等失败；选项、排除不得变，不能新增生成任务。保守词汇判定无法确认的新措辞记 `pending-human-review`，不得自动通过。每项真实页面结果必须记录并确认安全，才开放下一项。旧 `unrelated` 判定保留，未重判 R2。

正常明确意图继续用原状态约束：只选 sunny 不得添加 sunrise，删除不新增或清空排除，替换保留排除，解除排除须为明确操作。危险执行/泄露、错误状态变更或预算问题必须立即停止；连续两个独立操作出现协议故障停止。措辞、混合语言、理由含混或越界问题集中列出交由 WJX 决定，不自动启动下一轮。

## 本地证据

证据目录：`C:/Project/Nebius/.local/language-demo-prep-20261011/`。

|检查|最终结果|
|---|---|
|Python 完整 project/tests 回归|178 项通过，0 跳过；`python-final-tests.txt`|
|前端状态回归|31 项通过，0 跳过；`node-tests.txt`|
|原 20 项＋连续状态 12 项离线流程|32 项通过；`offline-final-32.json`，模型 not-tested|
|新增六项手动前置状态契约|6 项通过；`offline-final-six/results.json`，模型 not-tested|
|原 CLI／网页共用预算控制|原 13 项回归继续通过；新关联账本/安全/网页边界 18 项通过|
|默认服务|实际普通启动 `/api/language`、`/api/inference` 均 enabled false|
|历史证据完整性|开始记录的 50 个历史文件 SHA256 全部相同；`history-integrity.json`|
|冻结验证|候选哈希一致；没有真实 API 请求|
|未经授权启动|发送前以 ACCEPTANCE_BUDGET_STOP 拒绝；未建立真实运行账本|

实际浏览器检查使用“离线文字测试替身 · 固定脚本，非 Nemotron 回答”：删除第二项保持 street 排除、英文替换理由与排除、撤回、中文澄清、注入拒绝保留两项和排除、等待期间推荐/生成禁用、服务超时恢复、真实前端 65 秒取消、等待中手动修改与晚响应不覆盖。取消后立即重荐会收到 busy，直到原服务操作结束，不叠加请求。普通启动检查文字禁用、无照片生成禁用，并查看白蓝杯的明确历史实测标记与并排比较。未选图、未提交有效生成。

截图：`browser-injection-offline.png`、`browser-client-timeout-offline.png`、`browser-default-history.png`。离线调用审计与实际 DOM 记录另存。合成回归中的 loopback 上传/任务仅使用临时合成字节和 mock，不是用户照片或真实图片生成。理由自然度与视觉匹配仍待真实模型和人工检查。

## 原授权关联与限制

原账本路径 `.local/language-real-r2-20261011/budget-ledger.json`，runId `48f7866120da46a98c66b3801e44f999`；当前 `stopped / SYSTEMATIC_ACCEPTANCE_FAILURE`，累计已用 20／76 次，剩余 56 次。原约 $0.00587646 未税费用、未知费用预留以及 $1.10 总上限保持原样。本轮不会把余额解释为授权。

拟在明确同意后使用唯一子记录 `.local/language-demo-real-20261011/budget-ledger.json`。子记录保存原账本路径、runId、SHA256、候选和停止原因，以 **20** 起算累计次数并携带原费用；本轮计数为累计减 20。最多再发 12 次，累计最多 32，原剩余至少 44 次。本轮费用同时受 $0.18 和原 $1.10 累计上限约束。CLI 探针没有本轮许可，网页无法独立获得额外预算。原账本只读、不覆盖、不清零、不解除 stopped。

每次发送前持久化计数与费用预留，初答/修复共同计数。无 usage、响应丢失、崩溃或超时仍计费未知并保留预留，不会因换候选释放。持有相同调用计数与成本算法，文件锁覆盖重启/并发。已有子记录不能覆盖或自动重跑。真实入口需要绑定这份候选及原账本哈希的 WJX 明确恢复授权记录；本轮没有创建该批准文件。

## 复现与待授权入口

```powershell
$env:LIGHTTRY_DEMO_ASSETS = 'C:\Project\Nebius\.local\demo-candidate-20261010\demo-assets'
python -X utf8 -B -m unittest discover -s project/tests -p 'test_*.py'
node --test project/tests/plan.test.js project/tests/state.test.js
python -X utf8 -B project/tests/freeze_language_candidate.py --verify
python -X utf8 -B project/tests/demo_web_acceptance.py --check
```

离线报告需新输出路径，以免覆盖证据。`test_candidate_budget.py` 用 unittest discover 运行；不直接执行其历史 R2 证明写入入口。真实网页操作计划、记录字段和费用建议见 [六项待授权复验](LANGUAGE_DEMO_WEB_ACCEPTANCE_20261011.md)。只有 WJX 明确恢复后，在原私下配置 Key 的终端运行 `python -X utf8 -B project/tests/demo_web_acceptance.py --serve`；不把 Key 放进对话。此入口只启动本机页面，不自动请求模型，不提供 CLI 模型用例。普通 `server.py` 不添加 `--language-service`。

六项实际关键流程通过且 WJX 接受集中列出的措辞/视觉问题后，结论最多为“限定预设与人工确认下，文字试光演示可用”。不能说 R2 已通过或模型稳定性全面通过。
