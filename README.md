# LightTry

本地照片光照预览工作室。Nemotron 只提文字方案；Cosmos 提供受守护的 AI 重布光。不是物理精确渲染，文字、纹理和材质可能变化。

## 唯一启动入口

```powershell
python -X utf8 -B start.py
```

打开 http://127.0.0.1:8785 。普通启动不读取 Key、不连接云端、不启动 GPU，不安装依赖。`npm start` 使用同一入口。

本机路径仅在被忽略的 `.local/studio.json`；模板见 `config/studio.example.json`。`python -B start.py --paths` 只展示路径。`python` 指已有产品 CPU 环境，`offline_python` 指已有基础离线环境；venv 不搬迁。`assets_dir`、`tasks_dir`、`inverse_cache_dir` 指唯一实际数据目录，现有本机复用原数据，不再复制一份；新环境默认任务/缓存在 `.local/state/`。

## 目录与职责

- `project/studio.py` / `shared_http.py`：工作室及共享 HTTP 接口；`project/web/` 是唯一前端。
- `scheme_store.py` / `recipe_language.py` / `language.py`：方案持久化、上下文校验、文字协议与预算。
- `project/inference/`：共享任务、照片、缓存、守护校验和打包/提取；`runtime/`：参数化与联合实验适配。
- `project/experiments/`、`scripts/`、`cloud/`：实验和显式云工具，不属于普通启动链。
- `prototype/`、`patches/`、`manifests/`、`third_party/`：正式推理仍使用的 HDR 适配及固定来源/许可，不能因名称像旧稿就删。

## 验证与维护

```powershell
python -X utf8 -B scripts/selftest.py
npm test
```

自检覆盖 `prototype/`、`tests/`、`project/tests/`；基础组用配置中的离线环境，产品组用 CPU 环境。素材检查显式设置 `LIGHTTRY_DEMO_ASSETS`。离线替身/CPU 检查不等于实机视觉验收。

当前说明只维护此首页与 [云执行规范](docs/EXECUTION_FLOW.md)，不再追加平行交付、收尾、final 文档或 next 产品树。运行证据追加原账本；可执行回退复用项目外同一事务。只清理已确认冗余的副本/缓存，不删除原始素材、任务、账本、失败和停机证据。

旧说明和冻结清单原文移到被忽略的 `.local/history/documents/`，路径映射在其中的 `paths.json`；需要时只读查询，不作为当前启动或授权。素材公开分发许可仍未完全核实。原始云实验和已验收包保留原处、原字节；读取器兼容旧冻结包布局，源代码改变不能复用已关闭预算或主机信任。

云执行前先读上述规范与 `.local/calibration-20261013/checkpoint.json` 指向的最新状态；摘要不一致保留原证据，未知结果写未知。本轮结构维护不调用云端、不收费、不代表新的实机成功。
