# R2 新授权与执行入口 · 2026-10-11

WJX 已明确同意新增最多 **76 次** Token Factory 文字复验、**含税 $1.10** 上限。先验证冻结候选和 CLI/网页统一账本；系统性错误及时停止，不改版本重跑。不开 GPU，不上传照片。该授权与已用完的历史 40 次分别记账。

产品候选仍为 `lighttry-nemotron-54a45a831ff37856`，[R2 哈希清单](LANGUAGE_CANDIDATE_20261011_R2.json) 所列文件、提示词、schema、用例及实际运行配置均不改动。新增的 `candidate_budget.py`、`authorized_candidate_run.py`、`test_candidate_budget.py`、`start_authorized_r2.py` 仅为验收计数/启动包装，另存其哈希，不能改变模型请求协议。

## 预检

统一账本的 13 项离线测试通过，包括完整 32 CLI+6 browser 替身共用计数、实际 loopback 网页接口与 CLI 共用账本、修复共享额度、未知 usage 停止、鉴权错误计数、发送前持久化、费用封顶、重启不得覆盖、并发竞争、配置漂移和连续失败停止。证明及启动器哈希在 `.local/language-real-r2-20261011/budget-preflight.json`。预检真实 API 请求为 0；不是模型能力证据。

## 在原私下配置 Key 的 PowerShell 启动

```powershell
python -X utf8 -B C:/Project/Nebius/project/tests/start_authorized_r2.py
```

不需要粘贴或发送 Key。启动器只在子进程中设置 R2 的显式非敏感配置，并复查真实 adapter 值；不会改原终端的 Key 或父进程环境。模型/协议、40960/thinking on/auto/60 秒/一次修复均保持一致。

先运行 20 项完整用例，再运行 12 项依赖回归。服务在 `http://127.0.0.1:8790`，没有推理执行器，图片/任务提交仍禁用。网页推荐起初被阻止；CLI 完成后由操作者阅读结果、再执行 `authorized_candidate_run.py --arm-browser` 才开放已计划的 6 项网页操作。双方都使用同一个 `budget-ledger.json`，不能各拿 76 次。

每次操作先保留 2 个可能调用位置；每个 wire 调用在发出前持久化次数/费用预留。成功用合法整数 usage 更新费用估算；未知 usage 保留整次预留并停止。未知/崩溃/响应丢失不归零；已有账本禁止再次 execute。Key、任意非法正文和 reasoning 不进入账本。税费缓冲沿用已授权计划，不声称已查到账户真实税率或最终账单。

鉴权、限流、网络/超时、截断、未知 usage、实际 token 超出规划、候选或包装代码漂移立即停止；两个连续独立操作最终失败，或三个连续操作均需格式修复，也作为系统性问题停止。单一失败保留原事实，不用规则答案替换；依赖失败后跳过其后续链。

人工可随时执行 `python -X utf8 -B C:/Project/Nebius/project/tests/authorized_candidate_run.py --stop` 阻止后续调用；已发出仍计数。停止后不能自动恢复、改候选或覆盖账本重跑。命令行阶段正常完成不等于模型验收通过，所有理由/语言边界与交互还需单独复核。

执行结果将另存实际报告；本文件仅记录授权、预检与启动方法，不提前宣布真实通过。

执行已结束：20 次调用后因两个连续独立分类失败自动停止，未打开网页付费阶段，未改 R2 或重跑。详见 [R2 真实结果](LANGUAGE_R2_REAL_RESULT_20261011.md)。
