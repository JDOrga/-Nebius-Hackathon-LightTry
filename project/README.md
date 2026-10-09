# Cosmos 本地光照预览

有限主体保真度的 AI 光照预览工具，用于比较氛围、色温和明暗。沿用现有 Cosmos 真实结果；无云机、付费 API、GPU 模型或公网部署。产品源码与实验/历史证据分开，全部位于本目录。

## 启动

在 PowerShell 中运行（已有 Python 3.11，启动没有第三方依赖）：

```powershell
cd C:\Project\Nebius
python -X utf8 -B project/server.py
```

打开 <http://127.0.0.1:8765>。仅绑定本机 127.0.0.1，Ctrl+C 停止。端口占用时使用 `--port 8766`。不需要 npm install 或 build，不需要原项目配置/认证文件。

## 使用

- 样例演示：陶罐、茶盒、金属壶、玻璃杯，各有三张历史全画布 forward JPEG。玻璃标明效果不稳定。
- 晴日公园 / 粉色晨光 / 夜间街灯，分别映射原 HDR 索引 0 / 1 / 2。可滑杆/并排比较、查看原图或结果、放大/平移、适合窗口。
- “查看原始照片”打开未经本工具改写的原照；比较区使用既有实际输入 PNG，保留记录中的灰色留白和颜色处理。
- 点击或拖入 JPG/PNG/WebP，最多 20 MB、宽高至少 32 px、最多 4000 万像素/单边 16384 px。显示本机预览及尺寸，不上传文件。
- 新图明确显示“已载入，尚未连接推理服务”，不会出现样例生成结果、假进度或可用的结果导出。
- 下载当前样例实际 JPEG，字节与源结果一致，中文文件名包含样例和光照。说明页保留署名、许可与预览边界。

## 验证

```powershell
python -X utf8 -B -m unittest discover -s project/tests -p 'test_*.py' -v
node --test project/tests/state.test.js
```

测试只用 unittest、node:test。`qa/` 保存本轮实际 UI 截图、检查记录和原文件保存验收，忽略入库。开发记录见 [DEVELOPMENT.md](DEVELOPMENT.md)，适配器说明见 [docs/INFERENCE_INTERFACE.md](docs/INFERENCE_INTERFACE.md)。

## 已有素材要求

`data/catalog.json` 指向项目既有历史运行目录。服务器启动会验证 20 张图片的 SHA256，缺失或改动即拒绝启动。`build_catalog.py` 可在需要时重新核对来源目录并生成目录记录，使用项目既有 Pillow，不下载任何素材。

这不是物理精确渲染，细小文字、纹理和材质可能变化，不能直接替代商品实拍。真实推理、任务排队/进度、失败重试还未接入；本轮只保留数据契约，不提供云执行逻辑。
