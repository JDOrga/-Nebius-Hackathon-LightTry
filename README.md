# Cosmos 灯光预览工程

LightTry 本地样例演示入口在 [project/README.md](project/README.md)。普通演示只需 Python 3.11 和单独提供的本地素材包，无需云认证、SSH、GPU 或历史目录。WJC 的最短接手步骤见 [本地演示迁移](project/docs/LOCAL_DEMO_MIGRATION.md)。本机 main/HEAD 为 17d1fe0，独立素材支持已在此版本中；本轮真实任务接入尚未提交。origin 已按用户确认改为 JDOrga/-Nebius-Hackathon-LightTry，没有拉取或推送。

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
