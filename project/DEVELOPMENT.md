# 简明开发记录

## 2026-10-09：本地光照预览原型

产品方向：沿用 Cosmos Diffusion Renderer，以一定主体保真度的灯光氛围、色温和明暗预览为主，不追加逐像素文字/材质保真算法。先读项目 README、架构、验证范围、来源与历史运行代码；现有工程为 Python/静态 HTML，没有在用产品前端。因此用 Python 标准库 HTTP 服务 + 原生 HTML/CSS/ES modules，在 `project/` 独立实现，无新增依赖、框架、构建步骤或外部服务。

### 已完成

- 中文工具界面：大图预览、三个环境光方案、四个样例、滑杆/并排比较、原图/结果单独显示、放大平移、适合窗口、原始照片弹窗。
- 样例来自 `controlled-tests/20261007-four-materials/executions/2aa06a2c4e154ad0b03424c0d1d3dcca`。核对 `prepared_inputs.json`、`configuration.json`、`local_integrity.json`、forward 完成记录及上游 HDR 顺序；20 张原照/实际输入/结果图片身份、12 张结果 SHA256 与导出记录一致，canonical frame 与 flat JPEG 字节一致。
- 预设晴日公园 → `sunny_vondelpark_2k.hdr` / 0；粉色晨光 → `pink_sunrise_2k.hdr` / 1；夜间街灯 → `street_lamp_2k.hdr` / 2。没有杜撰角度、功率或色温值。
- 保留 1280×704 完整模型画布，比较双方使用实际输入/forward 输出。保留记录中的留白、ICC/sRGB 处理与有效区域，不另做裁切或拉伸。原始高分辨率照片可单独打开。
- 茶盒后续基线明确“未复现历史黑块”，但该结果是 basecolor、没有对应三 HDR。没有把旧异常当作当前工程问题，也没有把新 basecolor 冒充光照结果；本轮只展示来源完整的历史三 HDR 光照组，日期可见。局部尺度、融合候选均未使用。
- 玻璃保留真实不稳定效果并明确提示；说明页保留照片作者、许可、修改说明、HDR 许可记录不足的事实和 AI 预览边界。
- 选图/拖入共用格式、文件大小、尺寸和解码校验。上传原图仅使用浏览器 blob URL，显示尺寸和“已载入，尚未连接推理服务”。样例结果从真实生成模式彻底隔离，无假进度，结果下载禁用。
- 下载样例原始结果 JPEG，文件名含样例/中文光照名称。服务只绑定 127.0.0.1，明确文件 allowlist，不提供上传/推理端点。
- `sources.js` 隔离样例来源和未连接适配器；`state.js` 提供可测试的状态转移；输入/预设/任务ID/状态/结果/错误契约在 `docs/INFERENCE_INTERFACE.md`，真实适配器仅说明。

### 实际验证

启动：`python -X utf8 -B project/server.py`；访问 <http://127.0.0.1:8765>，服务本轮保持运行。用 Codex 浏览器实际操作，桌面默认 1280×720，窄窗口 390×844，测试后恢复默认窗口。

- 逐组切换全部 4×3 结果，DOM 图片身份与 HDR 映射正确；所有结果 natural size 1280×704，显示比例约 1.81818，全画布在适配视口内。记录 `qa/ui-mappings.json`。
- 实际并排比较金属壶/茶盒，滑杆键盘 Home/End 检查 0/100% clipping；检查原始照片弹窗。放大 125%，实际鼠标拖动 60/40 px，切换夜间街灯后 transform 完全一致，适合窗口回到 scale(1)、translate(0,0)。记录 `qa/pan-state.json`。
- 文件选择器实际载入独立合成测试图 640×960，新图显示 blob 原图、没有样例结果或样例光照缩略图，切换光照仍无结果，下载禁用。没有调用上传或推理服务。记录 `qa/upload-state.json`。
- 实际选入损坏 PNG、21 MB PNG、20×20 小图、GIF，分别出现明确错误且预览无旧样例结果、导出禁用。记录 `qa/ui-errors.json`。原生文件拖入未单独模拟；实现共用已验收的载入与校验路径。
- 实际点击下载 `金属壶_夜间街灯_AI光照预览.jpg` 到 Downloads，56633 字节，SHA256 `7e3de3557a8d9255f12d1fbf7f3fd05bbad10caae622c4902a737fb7d880d1a6`，与源 JPEG 完全一致。自动 HTTP 检查另外核对全部 12 个下载。
- 390 px 窄窗口无横向溢出，比较工具、光照、样例和导出仍可滚动访问；实际切换样例/灯光和比较方式成功。说明页作者/许可/HDR 表格可查看。浏览器 console 无错误/警告。
- node:test 7 项通过；unittest 7 项通过。覆盖全素材映射、上传/样例隔离、未连接任务、视图保留/复位、格式/尺寸错误、等比适配、真实下载身份与文件名、路径 allowlist、不存在推理端点。日志：`qa/node-tests.txt`、`qa/python-tests.txt`。
- 修改前后对原目录全部 10,647 个非 `.git` 文件逐个比较 SHA256/大小，changed=[]、missing=[]、new_outside_project=[]，全部通过。连接配置、历史实验、结果、证据均保持原样。开始时已存在的 `cloud/Common.ps1` 工作区修改保持原字节；未提交/推送。记录 `qa/preservation-result.json`。

### 截图

- `qa/desktop-slider.jpg`：主界面和滑杆比较。
- `qa/desktop-side.jpg`：金属壶并排比较。
- `qa/upload-not-connected.jpg`：上传原图与未连接状态。
- `qa/mobile-slider.jpg`、`qa/mobile-side.jpg`：窄窗口。
- `qa/glass-unstable.jpg`、`qa/original-photo.jpg`、`qa/upload-format-error.jpg`、`qa/about-mobile.jpg`：玻璃、原始照片、错误及素材说明。

`qa/` 仅为本轮本地验证资料，忽略入库，与既有历史证据分开。

### 未接入与边界

真实推理、排队/服务进度、成功结果和服务失败重试未接入。未开云机、调用付费 API、运行 GPU 模型、修改连接/守护逻辑或云环境，未部署公网。普通启动只用 Python 标准库；目录核对工具复用现有 Pillow。现有素材路径仍须留在工程内；缺失/哈希变化时服务拒绝启动。

本轮交付可操作、来源真实的本地预览工具，不声称物理精确、细字/纹理/材质不变或替代商品实拍。
