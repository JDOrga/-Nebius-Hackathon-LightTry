# Cosmos 本地光照预览

有限主体保真度的 AI 光照预览工具，用于比较氛围、色温和明暗。沿用现有 Cosmos 真实结果；无云机、付费 API、GPU 模型或公网部署。产品源码与实验/历史证据分开，全部位于本目录。

## 启动

使用 Python 3.11（本轮实测 3.11.9），启动、导入素材与 Python 测试均只用标准库，无需 pip 安装。先取得本轮候选代码及单独提供的本地素材包，在代码根目录运行：

```powershell
python -X utf8 -B project/install_demo_assets.py "<lighttry-demo-assets-20261009.zip 的路径>"
python -X utf8 -B project/server.py
```

打开 <http://127.0.0.1:8765>。仅绑定本机 127.0.0.1，Ctrl+C 停止。端口占用时使用 `--port 8766`。不需要 npm install 或 build，不需要原项目配置/认证文件。

## 使用

- 样例演示：陶罐、茶盒、金属壶、玻璃杯，各有三张历史全画布 forward JPEG。玻璃标明效果不稳定。
- 晴日公园 / 粉色晨光 / 夜间街灯，分别映射原 HDR 索引 0 / 1 / 2。可滑杆/并排比较、查看原图或结果、放大/平移、适合窗口。并排按可用宽度左右或上下排列，手机在预览附近直接切换灯光。
- “查看原始照片”打开未经本工具改写的原照；比较区使用既有实际输入 PNG，保留记录中的灰色留白和颜色处理。
- “载入照片预览 · 暂不支持生成”：点击或拖入 JPG/PNG/WebP，最多 20 MB、宽高至少 32 px、最多 4000 万像素/单边 16384 px。显示本机预览及尺寸，不上传文件。
- 新图明确显示“已载入，尚未连接推理服务”，不会出现样例生成结果、假进度或可用的结果导出。
- 下载当前样例实际 JPEG，字节与源结果一致，中文文件名包含样例和光照。说明页保留署名、许可与预览边界。

## 验证

```powershell
python -X utf8 -B -m unittest discover -s project/tests -p 'test_*.py' -v
node --test project/tests/state.test.js
```

测试只用 unittest、node:test。`qa/` 保存本轮实际 UI 截图、检查记录和原文件保存验收，忽略入库。开发记录见 [DEVELOPMENT.md](DEVELOPMENT.md)，适配器说明见 [docs/INFERENCE_INTERFACE.md](docs/INFERENCE_INTERFACE.md)。

## 独立素材与迁移

默认从被忽略的 `project/demo-assets/` 读取 4 张原照、4 张实际模型输入和 12 张历史结果，以及署名与来源记录。复制保持原字节，启动逐文件校验 SHA256；缺失或改动会明确报错并显示安装指引，不回退到其他图片。`build_catalog.py` 现在只验证独立素材及来源记录，不再读取历史实验或生成/改写目录清单，也不需要 Pillow。

可用 `--assets-dir "<自己的素材目录>"` 或环境变量 `LIGHTTRY_DEMO_ASSETS` 配置独立位置。优先级：命令参数、环境变量、默认目录；相对路径始终从 `project/` 解析，支持空格。无需 Nebius 登录、SSH、GPU、云配置或历史目录。

普通演示只展示已有 JPEG，**不附带 HDR 本体**，仅保留三个预设名称、索引、哈希和来源。原照许可与处理说明已记录；结果公开分发及 HDR 独立许可仍待核实，整个素材包仅本地保留，不入库、不上传。

当前 origin 为 `https://github.com/JVerdL/-Nebius-Hackathon-LightTry`，HEAD 为 `71fe251`。本轮修改尚未提交，GitHub 当前代码不包含此次迁移支持。已完成的是候选交付目录验收，**WJC 实机待验收**。最短接手步骤和包校验见 [本地演示迁移](docs/LOCAL_DEMO_MIGRATION.md)，范围见 [交付边界](docs/DELIVERY_BOUNDARIES.md)，许可依据见 [素材分发核对](docs/DEMO_ASSET_LICENSES.md)。

这不是物理精确渲染，细小文字、纹理和材质可能变化，不能直接替代商品实拍。真实推理、任务排队/进度、失败重试还未接入；本轮只保留数据契约，不提供云执行逻辑。
