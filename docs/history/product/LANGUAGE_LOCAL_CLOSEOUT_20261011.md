# Nemotron 文字方案本地收尾 · 2026-10-11

本地修复完成；**真实 Nemotron 复验尚未执行、尚未通过**。本轮真实请求 0、费用 0；没有 GPU、照片上传、依赖安装、认证/权限变更、提交或推送。起始工作区已有 7 个修改文件及未跟踪真实总结，均保留；没有适用于本项目路径的 AGENTS.md，读取了全局 `C:/Users/WJX/.codex/AGENTS.md`（空文件）。以本地最新代码及 [真实总结](LANGUAGE_REAL_SUMMARY_20261011.md)、[协议调查](LANGUAGE_PROTOCOL_INVESTIGATION_20261011.md) 为依据，旧报告及真实响应不改写。

## 实际修改

- 保留唯一 `propose_lighting_plan` 数据函数和六字段输出 schema，未换模型、未切 JSON 输出协议。候选设置为 `nvidia/Nemotron-3_5-Lightning`、thinking on、40960、auto、60 秒；普通启动仍关闭文字服务和推理。示例配置与默认工具选择对齐 auto。
- 新增请求侧结构化 `select/remove/replace/exclude/unexclude` 操作及服务端当前状态校验。删除/替换必须保持已有排除；排除与解除只通过可验证的明确操作改变。有限、全字符串命令包括 `只选 sunny`、`删掉第二项`、`不要再推荐夜景`、`解除夜景排除`；不是通用中文关键词解析。其他自然语言及理由仍由模型完成。无法验证的自由文本排除变更会被拒绝，或要求使用排除控件澄清；不单凭模型自述判断语义。最后一个选择可手动取消；当前单工具协议不能表示 ready 空选择，服务端不会假称删除成功。
- 页面增加持续排除/解除控件，手动删除和替换不会隐式清除排除；解除及排除均可撤回。跨照片保留选择与排除，不复用其他照片结果。请求被编辑、切图、手动修改或撤回后失效；旧成功/错误不会覆盖新状态。
- 请求明确传入回复语言：文字中明确要求优先，否则使用页面语言设置（缺省中文）。混合语言、只有预设 ID 的输入也使用该设置；英文测试显式选择 English。逐条检查理由和澄清问题，技术标识允许保留。明显错语言拒绝；混合普通英文词、短句等边界保留 `review`，不能保证措辞质量。不支持仅返回枚举码，页面以“系统能力说明”本地化，语言检查记 `not-applicable`。错误加“系统提示”；不冒充模型理由。澄清保留旧方案时，旧理由标注来源语言，不会翻译或改写为新模型回答。
- 多工具、额外工具、多个 choice、额外 assistant 正文、非法 JSON、截断仍整份拒绝。没有取第一个、拼接参数、提取片段或执行工具。格式、语义和明显错语言共用最多一次新完整回答修复；截断、鉴权、限流、超时、连接错误不重试。
- 每次推荐最多 2 次调用，合用 60 秒截止时间，前端等 65 秒；修复只获得剩余时间。发送前预留全部可能调用费用，默认单操作 $0.022；输入上下文按序列化 UTF-8 15,000 字节上限防止失控。`qa/language-operations.jsonl` 只保存操作 ID、预留次数、耗时、错误码、协议形态、usage 与估算费用，不存 Key、原始非法正文、reasoning 或用户文本。按唯一 operationId/call 去重读取快照，最后快照是当前状态；崩溃、响应丢失和超时保留未知计费预留。上游仍在运行时保持 busy，避免客户端超时立即重叠调用。
- 验收维度独立：协议/结构、明确选择与排除、回复语言、预设能力理由、交互流程。模糊氛围可有多个合理答案，但仅结构有界不等于理由质量通过；澄清必须指向灯光意图，不能把任意 unsupported/clarification 记成功。`constraintCheck:false` 强制失败。理由与未测交互保留人工复核，历史跨版本记录不会并入候选通过率。旧付费入口拒绝真实传输，原 40 次授权不可再用。

## 回归证据

- Python 完整本地回归：147 项通过，0 跳过（包含 60 项语言、协议、计数及候选测试）；Node 前端状态回归：30 项通过，0 跳过。完整素材目录逐文件 SHA256 校验通过：27 张图片、5 组样例。单元测试仅使用临时目录、合成字节、离线执行器和 mock，不发送真实照片或调用模型。
- 固定脚本跑完原 20 项与新增 12 项，共 32 项，离线约束/流程通过；报告的 `modelAcceptance` 恒为 `not-tested`、`realRequests:0`。连续链实际传递前项状态，失败依赖不得用固定初始状态假装接续成功。
- 实际浏览器使用醒目的“离线文字测试替身 · 固定脚本，非 Nemotron 回答”页面：等待时推荐与生成禁用、重复点击、模拟服务超时与恢复、真实 65 秒前端等待上限、删除后再次推荐、替换保留排除、解除与撤回、中文澄清/英语理由、等待中手动修改及晚响应不覆盖均验收。只做历史样例切换和本地文字操作，没有选图上传。
- 白蓝杯历史完整 JPEG、396×704 区域 PNG 从页面实际下载，哈希与 catalog 一致；晴日/晨光并排比较正常，第三灯光没有借用其他结果。普通启动的 `/api/inference` 和 `/api/language` 均 `enabled:false`。
- 任务恢复与显式生成隔离通过离线自动回归；浏览器检查了无照片时确认按钮禁用、推荐成功/失败均无任务提交。遵守本轮不上传照片约束，**未在浏览器新增照片任务或点击执行有效生成**，也未复验真实 Cosmos/GPU。

证据位于 `.local/language-finish-20261011/`：Python 日志、离线 suite、浏览器截图及离线调用审计。此前两个测试服务启动后的浏览器取消曾出现断开连接 traceback，本轮修复了重复写错误响应；最终候选浏览器取消复查无该异常。两份本轮下载是历史原字节；历史素材目录完全未覆盖。

## 如何复现

在 `C:/Project/Nebius` 的现有 PowerShell 运行，使用既有 Python/Node，不安装依赖：

```powershell
$env:LIGHTTRY_DEMO_ASSETS = 'C:\Project\Nebius\.local\demo-candidate-20261010\demo-assets'
python -X utf8 -B -m unittest discover -s project/tests -p 'test_*.py'
node --test project/tests/plan.test.js project/tests/state.test.js
python -X utf8 -B project/tests/freeze_language_candidate.py --verify
python -X utf8 -B project/tests/run_candidate_offline.py --output .local/language-finish-20261011/offline-new.json
python -X utf8 -B project/tests/serve_language_fixture.py --port 8788 --tasks-dir C:\Project\Nebius\.local\language-finish-20261011\tasks --assets-dir C:\Project\Nebius\.local\demo-candidate-20261010\demo-assets
```

打开 `http://127.0.0.1:8788`。`slow` 是 8 秒脚本，`timeout` 是服务端超时替身，`error` 是限流替身；`client-timeout` 在 HTTP 层故意扣留响应 70 秒，测试真实前端 65 秒取消，并非生产适配器花了 70 秒推理。输入 sunny 推荐，然后勾第二项、输入“删掉第二项”，再“只选 sunrise”验证删除后再次推荐。排除控件、替换和撤回可继续验证。恶意删除加排除、多工具与错语言的失败/一次修复在 `test_language_candidate.py` 用完整离线响应复现，没有真实调用入口。Ctrl+C 停止。本轮自启的 8788/8789 服务已关闭。

离线 runner：0 表示离线机制全部完成，绝不代表模型通过；1 为失败、2 为预检拒绝/候选变更/文件已存在、3 为未完成。语义验收 runner 的 0 必须所有五维都完成并通过，1 包括 constraintCheck false/其他失败，2 为预检拒绝，3 为未完成或待人工复核。历史协议诊断入口的 0 仅指协议探针执行完成，报告明确不能用于模型质量通过；真实传输已被关闭。

## 候选与限制

当前候选为 R2 `lighttry-nemotron-54a45a831ff37856`，见 [文件及配置哈希](LANGUAGE_CANDIDATE_20261011_R2.json)，包括 Git HEAD、未提交工作区文件、实际构造的 system prompt、schema、原始用例、新回归、网页用例哈希。初次本地冻结后复查修正了审计 I/O 失败时锁释放和验收 not-applicable 使用范围，因此另存 R2；`LANGUAGE_CANDIDATE_20261011.json` 及早期 offline-frozen.json 仅为先前本地版本，不合并为当前模型通过率。R2 的 prompt/schema/web 文件哈希与早期版相同，浏览器交互证据沿用相同页面代码，R2 重启后另复查成功、超时恢复和连续状态。完整自动回归与 32 项离线流程均按 R2 重跑。

冻版验证只读且不访问 API；修改任一冻结文件需新候选与新结果分组。真实服务必须核对实际进程配置及环境变量，不能仅按缺省值推断（旧终端可能仍有旧变量）。普通启动不要加 `--language-service`。

没有任何新的 Nemotron 能力、语言质量、统一候选 20 项通过率、费用账单或延迟稳定性结论。文本语言脚本检查不能保证自然措辞，主观氛围和解释实际能力仍需逐项人工复核；自由表述的排除意图可能要求澄清。下一步只需 Token Factory，按 [真实复验授权计划](LANGUAGE_NEXT_ACCEPTANCE_20261011.md) 获得新的次数和含税费用授权后再执行。
