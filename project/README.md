# Cosmos 本地光照预览

2026-10-10 新增有边界的文字选光方案：推荐、有限后续修改、手动编辑、撤回和跨照片复用选择，再显式确认接入现有批次。Nemotron 仅负责文字方案，Cosmos 负责既有重布光；普通启动两者均不自动调用。文字真实 API 未验收，离线脚本明确标识。启动、环境模板、当前素材路径及下一轮最多40次/$0.10计划见 [文字方案交付](docs/LANGUAGE_CONTROL_20261010.md)，本轮结果见 [本地验收](docs/LANGUAGE_ACCEPTANCE_20261010.md)。

有限主体保真度的 AI 光照预览工具。保留 Cosmos 历史样例；真实任务默认关闭。2026-10-10 已验收一次新网页 sunny/sunrise 批次：复用历史inverse、一个forward对象顺序生成，结果自动取回展示；已独立确认停机。普通启动不连接云端、不启动云机。最短启动、两种模式和限制见 [可演示候选基线](docs/DEMO_CANDIDATE_BASELINE_20261010.md)，实际证据见 [新批次验收](docs/WEB_BATCH_ACCEPTANCE_RETRY2_20261010.md)。候选尚未发布。

## 启动

使用 Python 3.11（实测 3.11.9），样例启动和素材导入只用标准库；真实模式及相关Python测试需要既有Pillow。先取得候选代码及单独提供的本地素材包，在代码根目录运行：

```powershell
python -X utf8 -B project/install_demo_assets.py "<素材包路径>" --assets-dir demo-assets-20261010
python -X utf8 -B project/server.py --assets-dir demo-assets-20261010
```

打开 <http://127.0.0.1:8765>。仅绑定本机 127.0.0.1，Ctrl+C 停止。端口占用时使用 `--port 8766`。不需要 npm install 或 build，不需要原项目配置/认证文件。

## 使用

- 默认白蓝杯：2026-10-10 已完成的真实历史样例，sunny、sunrise 两张 1280×704 结果；第三灯光没有本批结果，只显示输入、不能下载。可查看和导出按记录裁剪的 396×704 原照片区域。其余四组历史样例保留，玻璃效果不稳定。
- 晴日公园 / 粉色晨光 / 夜间街灯，分别映射原 HDR 索引 0 / 1 / 2。可滑杆/并排比较、查看原图或结果、放大/平移、适合窗口。并排按可用宽度左右或上下排列，手机在预览附近直接切换灯光。
- “查看原始照片”打开未经本工具改写的原照；比较区使用既有实际输入 PNG，保留记录中的灰色留白和颜色处理。
- “载入照片”：点击或拖入 JPG/PNG/WebP，最多 20 MB、宽高至少 32 px、最多 4000 万像素/单边 16384 px。显示本机预览及尺寸，不上传文件。
- 默认新图显示“已载入，尚未连接推理服务”，提交与下载禁用。只有显式指定自己的有效推理配置后才能提交；真实状态、刷新恢复、已校验结果、滑杆/并排比较和下载共用既有界面。
- 下载当前样例实际 JPEG，字节与源结果一致，中文文件名包含样例和光照。说明页保留署名、许可与预览边界。

## 验证

```powershell
python -X utf8 -B -m unittest discover -s project/tests -p 'test_*.py' -v
node --test project/tests/state.test.js
node --test project/tests/plan.test.js
```

测试只用 unittest、node:test。`qa/` 保存本轮实际 UI 截图、检查记录和原文件保存验收，忽略入库。开发记录见 [DEVELOPMENT.md](DEVELOPMENT.md)，适配器说明见 [docs/INFERENCE_INTERFACE.md](docs/INFERENCE_INTERFACE.md)。

## 独立素材与迁移

默认从被忽略的 `project/demo-assets/` 读取旧四组和白蓝杯的 27 张图片（含记录区域 PNG）、14 张完整历史结果，以及署名与来源记录。复制保持原字节，启动逐文件校验 SHA256；缺失或改动会明确报错并显示安装指引，不回退到其他图片。`build_catalog.py` 现在只验证独立素材及来源记录，不再读取历史实验或生成/改写目录清单，也不需要 Pillow。

可用 `--assets-dir "<自己的素材目录>"` 或环境变量 `LIGHTTRY_DEMO_ASSETS` 配置独立位置。优先级：命令参数、环境变量、默认目录；相对路径始终从 `project/` 解析，支持空格。无需 Nebius 登录、SSH、GPU、云配置或历史目录。

普通演示只展示已有 JPEG，**不附带 HDR 本体**，仅保留三个预设名称、索引、哈希和来源。原照许可与处理说明已记录；结果公开分发及 HDR 独立许可仍待核实，整个素材包仅本地保留，不入库、不上传。

2026-10-09 本轮核对：LAPTOP-WJX 的 main/HEAD 为 `17d1fe0c35ef8eb25aa0c3fcd6654468751e043b`，开始时工作区干净。按用户确认，origin 已改为 `https://github.com/JDOrga/-Nebius-Hackathon-LightTry`；未 fetch/pull/reset/提交/推送。独立样例迁移已在当前 HEAD 中，本轮推理接入修改尚未提交。WJC 未操作；旧文档中的 `71fe251` 是当时历史记录。最短接手步骤和包校验见 [本地演示迁移](docs/LOCAL_DEMO_MIGRATION.md)，范围见 [交付边界](docs/DELIVERY_BOUNDARIES.md)，许可依据见 [素材分发核对](docs/DEMO_ASSET_LICENSES.md)。

这不是物理精确渲染，细小文字、纹理和材质可能变化，不能直接替代商品实拍。已验收一次真实网页双预设批次、取回、展示、恢复及下载；不代表所有灯光/输入或故障已做GPU矩阵验收。无账号、支付、多用户、复杂队列或自动开机。

## 真实任务的本地准备

普通样例演示继续只需 Python 标准库。启用真实任务需要既有 Pillow（离线测试使用 Pillow 11.1.0），不安装模型、Torch 或 SSH 客户端到浏览器。`inference.example.json` 是占位模板；复制到被忽略的 `inference.local.json` 后，仅在另行获得收费窗口授权、守护和本轮主机确认就绪时启用。普通启动不会读取它，须显式 `--inference-config inference.local.json`。本次授权run已结束，配置和授权证据仅本地保留，不可用作下一轮授权。

任务保存在被忽略的 `project/.tasks/`；默认可用结果保留 24 小时，过期后禁用访问，不自动删除原始证据。超时不表示远端已停止。执行取消暂不支持；界面会如实告知。详情与最小验收步骤见 [INFERENCE_READINESS.md](docs/INFERENCE_READINESS.md)。

## 2026-10-10 本地候选收尾

当前 HEAD 为 `93c23724ec85addfcd2f5bad971aef329bd6d502`，上文 17d1fe0 为10月9日历史记录。已有旧素材目录不会被覆盖，请将新版包安装到新的 `demo-assets-20261010`；命令和环境变量的相对目录均从 `project/` 解析，WJX/WJC 相同。普通启动不读取真实配置；打开 `/api/inference` 应为 `enabled:false`。

完整最短步骤、许可边界、候选分组和隔离验证见 [本地候选交付](docs/DEMO_HANDOFF_20261010.md)。首次真实生成需要等待模型初始化；约5.9秒是已加载模型下第二预设执行增量，非端到端响应。本轮网页约7分51秒仅代表该次测量，不是服务承诺。任务会过期，长期演示使用独立样例。
