# Cosmos 灯光预览工程

有限保真度的灯光预览，默认 1280×704。当前提供 Cosmos 推理、HDR 替代采样、验收和显式守护执行链；产品 UI 开发暂停。

先阅读 [迁移步骤](docs/MIGRATION.md) 与 [依赖说明](docs/DEPENDENCIES.md)。复制配置模板到不入库的 config/local.json，并填写自己的现有路径与目标。默认命令均不启动、重启或停止云资源：

```powershell
python -B scripts/local_config.py
python -B scripts/selftest.py
powershell.exe -NoProfile -File cloud/Invoke-Cloud.ps1
python -B scripts/audit_repository.py
```

配置校验只检查元数据，不读取私钥、认证配置或 known_hosts 的内容；缺少配置时明确报错。自检使用合成配置，详细日志在忽略的 .local 下。真实 API、SSH、下载、GPU 推理及许可确认另见 [显式云流程](docs/CLOUD.md)，本轮没有执行。

[架构与预览边界](docs/ARCHITECTURE.md) · [第三方许可与素材](docs/THIRD_PARTY.md) · [故障处理](docs/TROUBLESHOOTING.md) · [候选文件完整清单](docs/CANDIDATES.md)

[验证范围与已知限制](docs/VALIDATION.md)：云连接、代码传输和停机验收已验证；模型小任务没有成功，完整灯光推理仍待验收。

仓库直接位于当前项目目录，统一入口为 cloud/Invoke-Cloud.ps1。原 scripts/HOST_CAPTURE_NEXT.json 保留为忽略的历史指针，不作为当前入口。Git 文件选择使用 .gitignore，审计命令检查 Git 可见文件；历史数据、旧实验与真实配置保留本地并忽略。提交身份由操作者明确指定；远程、团队归属和公开/私有设置另行确认，不自动配置远程或推送。
