# LightTry

本地照片光照预览工作室：Nemotron 提供文字方案，Cosmos 提供受守护的光照预览。不是物理精确渲染；细字、纹理、材质和灯光效果有已知限制。

## 本地启动

```powershell
python -X utf8 -B start.py
```

打开 http://127.0.0.1:8785 。普通启动不读取 Key、不连接云端、不启动 GPU。Python 环境需已有 NumPy/Pillow；不会自动安装依赖。

本机路径集中在被忽略的 `.local/studio.json`；模板见 `config/studio.example.json`。命令行 `--assets-dir` 等显式参数优先。`python -B start.py --paths` 只展示路径，不启动服务。无配置时素材默认 `project/demo-assets/`，任务默认 `.local/state/tasks/`；缺素材明确报错，不回退到历史目录。

配置可指定已有 `python`（产品/CPU）和 `offline_python`（基础离线回归）环境；入口和自检复用它们，不搬迁 venv，也不自动安装依赖。

## 唯一正式源码

- `project/studio.py`：HTTP 工作室入口；`shared_http.py`：共享素材/任务接口。
- `project/web/`：唯一前端；`scheme_store.py`、`recipe_language.py`：方案与文字建议。
- `project/inference/`：共享任务、守护校验、打包/提取；`runtime/`：参数化及联合实验适配。
- `project/experiments/`、`scripts/`、`cloud/`：实验与显式云执行工具，非普通启动链。
- `prototype/`、`patches/`、`manifests/`：固定上游 HDR 适配和来源校验，不是另一套产品。

## 验证

```powershell
python -X utf8 -B scripts/selftest.py
npm test
```

Python 自检发现三个测试区域：`prototype/`、`tests/`、`project/tests/`；Node 测试覆盖正式前端。部分 CPU 测试需既有 PyTorch、NumPy/Pillow/PyYAML 和 Windows PowerShell；离线替身不是实机验收。

## 只读这些当前文档

- [架构与目录边界](docs/ARCHITECTURE.md)
- [本地开发与维护规则](docs/DEVELOPMENT.md)
- [云执行规范](docs/EXECUTION_FLOW.md)：收费、登录、开停机前必读；历史授权不可复用。
- [历史记录索引](docs/history/README.md)：旧文档仅作证据，不是当前启动说明。

素材、任务、原始云结果、账本和失败证据不入库，不因结构清理而删除。既有运行记录仍在本地历史目录；正式状态依据 `.local/calibration-20261013/checkpoint.json` 及其指针读取，遇到摘要不同步保留原证据，不伪造实机成功。公开分发素材的许可边界仍见历史许可记录。
