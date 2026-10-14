## 当前云执行流程（2026-10-13）

云实验/认证/停机衔接以 [执行快速衔接规范](docs/EXECUTION_FLOW.md) 为准：准备在授权前完成，认证与启动走必要短链，停机四项核验先于报告整理。旧 RUNBOOK 一小时窗口仅作历史记录；不继承已结束授权。该文档明确执行者响应目标与自动化尚未实现的边界，不代表新云授权或实机成功。

## 2026-10-12 工作区清理

正式前端仅保留 `project/next/web/`，启动使用 `python -X utf8 -B project/start_studio.py`（默认端口 8785）。旧 `project/web/` 页面、资源及专属 state/plan JavaScript 测试已删除；共享 `project/server.py` 的 Handler、素材校验和任务 API 保留供工作室与后端回归使用，旧静态路由返回 404，未使用的旧 main 函数已移除。`npm test` 运行全部保留的前端回归；`npm start` 使用正式入口。候选快照改为跟踪正式前端，旧冻结记录仅作历史证据，不应复用为当前源码授权。

仅清理 `project/qa/` 中 2026-10-11 之前的 `.log`；截图、报告、任务数据、素材、云运行及历史推理证据均保留。历史文档中的旧页面路径和测试数字仅描述当时状态，不再作为当前入口。

# LightTry 正式照片工作室（本地集成）

唯一推荐启动命令：

```powershell
python -X utf8 -B C:\Project\Nebius\project\start_studio.py
```

打开 http://127.0.0.1:8785 。默认关闭 Nemotron 与 GPU，无外部请求。复用现有 next.server、SchemeStore 与共享任务/照片服务；不导入设计预览存储。已有正式任务目录原样保留。旧 project/server.py CLI 转接同一工作室，旧 web 页面及专属测试已删除，共享后端保留。旧语言参数不兼容，必须使用下文 next 的显式配置。

本地无素材时须提供现有素材包；此命令不安装依赖、不调用云。独立副本验收与回退见 project/docs/STUDIO_INTEGRATION_20261011.md。以下为历史说明，启动以本节为准：

---

# Cosmos 灯光预览工程

2026-10-11 Nemotron文字选光已完成预算内真实调用，20个原始用例均尝试，最新结果19/20合法；重复工具调用、中文理由语言与删除排除仍需修正，完整质量验收未通过。保守计数40次授权已到，停止收费调用，GPU始终关闭。配置保持thinking on、40960上限，普通演示仍关闭文字/图片推理。见[真实验收总结](project/docs/LANGUAGE_REAL_SUMMARY_20261011.md)与[文字方案交付](project/docs/LANGUAGE_CONTROL_20261010.md)。

LightTry 本地样例演示入口在 [project/README.md](project/README.md)。普通演示只需 Python 3.11 和单独提供的本地素材包，无需云认证、SSH、GPU 或历史目录。WJC 的最短接手步骤见 [本地候选交付](project/docs/DEMO_HANDOFF_20261010.md)。2026-10-10 当前 main/HEAD 为 93c23724ec85addfcd2f5bad971aef329bd6d502；真实 sunny/sunrise 网页批次已验收并停机，本轮只整理未提交的本地候选。origin 已按用户确认改为 JDOrga/-Nebius-Hackathon-LightTry，没有拉取或推送。

有限保真度的灯光预览，默认 1280×704。下文为既有 Cosmos 推理、HDR 替代采样、验收和显式守护执行链，普通本地演示无需执行这些流程。

先阅读 [迁移步骤](docs/MIGRATION.md) 与 [依赖说明](docs/DEPENDENCIES.md)。复制配置模板到不入库的 config/local.json，并填写自己的现有路径与目标。默认命令均不启动、重启或停止云资源：

```powershell
python -B scripts/local_config.py
python -B scripts/selftest.py
powershell.exe -NoProfile -File cloud/Invoke-Cloud.ps1
python -B scripts/audit_repository.py
```

配置校验只检查元数据，不读取私钥、认证配置或 known_hosts 的内容；缺少配置时明确报错。自检使用合成配置，详细日志在忽略的 .local 下。真实 API、SSH、下载、GPU 推理及许可确认另见 [显式云流程](docs/CLOUD.md)，本轮没有执行。

[架构与预览边界](docs/ARCHITECTURE.md) · [第三方许可与素材](docs/THIRD_PARTY.md) · [故障处理](docs/TROUBLESHOOTING.md) · [候选文件完整清单](docs/CANDIDATES.md)

[验证范围与已知限制](docs/VALIDATION.md)：云连接、代码传输、停机验收与 Tokenizer GPU 编码/解码小任务已验证；迁移守护链上的完整灯光推理仍待验收；另有四素材历史完整推理证据，云端最终验收失败、本地结构验收通过且视觉质量混合。新用户照片任务链路本轮只做本地准备，见 [推理准备记录](project/docs/INFERENCE_READINESS.md)。

仓库直接位于当前项目目录，统一入口为 cloud/Invoke-Cloud.ps1。已废弃脚本和历史指针移至忽略的 `.local/legacy-source/`，保留原目录结构及哈希清单，仅供查阅，不作为运行入口。Git 文件选择使用 .gitignore，审计命令检查 Git 可见文件；历史数据、旧实验与真实配置保留本地并忽略。远程、团队归属和公开/私有设置另行确认，不自动配置远程或推送。

自检先检查 `requirements/offline.txt` 中的依赖，再自动发现 `prototype/` 和 `tests/` 顶层的 `test_*.py`。支持 unittest 与现有独立测试脚本；每组单独运行，失败或超时仍写入报告并继续后续组。缺依赖时先在自己的虚拟环境中安装，工具不会自动安装。
