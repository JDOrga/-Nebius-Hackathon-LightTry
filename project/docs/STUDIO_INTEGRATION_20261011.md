# LightTry 正式照片工作室：本地集成交付（2026-10-11）

## 运行与当前结论

在 C:\Project\Nebius 执行：

```powershell
python -X utf8 -B C:\Project\Nebius\project\start_studio.py
```

地址 http://127.0.0.1:8785 。这条命令本轮已经实际启动；默认 Nemotron、Cosmos/GPU 均关闭，不读取密钥、不上传照片、不发外部请求。只使用既有 Python/Pillow 等依赖。工作室已进入现有正式业务链，不是设计数据适配器。

本轮 HEAD 实查 cef70911aa8ec54f4bc5971b0c98dff49c1638c0，开始 Git 状态为空；没有 reset、提交、推送、安装或部署。当前有未提交的前端、入口、测试和文档修改。第二轮原型、历史报告、素材与任务不删除。

## 入口保留、转接、停用

|入口|本轮处理|理由|
|---|---|---|
|project/start_studio.py|唯一推荐命令；直接调用既有 next.server.main|只组合路径，无第三套后端、推理或数据规则|
|project/next/server.py + next/web|正式工作室；默认任务目录统一到既有 workbench-tasks|保留 SchemeStore、recipeKey、版本、守护执行、文字校验|
|project/server.py CLI|转接同一 start_studio；旧 --language-service 明确拒绝|不再普通启动第二套界面；导入的 Handler 仍共享/API兼容|
|project/web|文件保留；普通 CLI 不再显示旧 UI|研究与隔离旧测试仍依赖；没有删除旧页面|
|about / 原照 / 下载 / 区域 / study|保持辅助和来源服务|正常辅助不是独立产品；实验与正式结果不混源|
|.local/lighttry-design-preview-20261011|原字节保留，独立设计预览|不导入模拟方案；不成为正式启动入口|
|project/tests/serve_studio_fixture.py|独立8897，显式替身；关闭推理|复用正式前端与校验，只有合成 transport；不接收费接口|

既有正式 v1 浏览器库/光标/任务/来源 namespace 不变，不清空、不重写历史版本；设计 namespace 不读取。替身在不同端口/浏览器 origin，库和任务目录隔离。没有需要强制升级的正式 schema。先在 workbench-tasks 的独立副本验收，再启动原目录；原目录67个既有任务文件 SHA 全等。

更旧 project/.tasks 的历史文件仍保留，没有自动把过期任务导入并伪装成新完成。需要查阅该库时可停止当前服务，以同一命令追加 --tasks-dir C:\Project\Nebius\project\.tasks；通过“版本与能力说明 → 通过任务编号找回”只读恢复状态。有效性仍按原期限/回执判断，不改旧请求。原浏览器固定预设计划不自动升级成参数实测方案，不导入设计模拟库。

## 已接入真实实现

- 历史catalog与原照、本机文件选择、解码尺寸校验/原SHA、同SHA重新载入；正式提交后的EXIF/ICC/等比预处理继续由现有 TaskStore 实现。
- 方案命名、同参数/同名称无变化保护、保存、另存新planId、查看旧版本、恢复为新版本、跨图仅复用参数；任务编号找回及刷新原请求状态。
- 三个默认环境；sunny0.7近似偏暗、sunny+45/1实验性配方。白名单驱动，不新增连续角度/EV/色温/柔光/保色。
- 真实 /api/lighting/recommend 接口、服务端校验及一次修复；当前/建议差异、明确应用、独立保存/生成。请求epoch与参照键共同保护；换照片/改版本/改文字取消或丢弃旧响应。同参数不创建版本；取消浏览器等待不意味着取消上游计费。
- 明确生成对话框，确认参照不能变化；提交固定文件/方案快照。既有 TaskStore/SchemeStore、幂等请求、实际任务轮询、刷新恢复及真实结果核验未替换。
- 已有匹配结果复用，原图/结果及两方案比较、共同fit尺度与中心、记录validRegion、缩放/拖动/键盘平移、完整JPEG/区域PNG下载、来源和限制详情。
- 传输失败按 transferring 阶段区别，不靠通用 EXECUTION_FAILED 文案猜测；禁止盲目重算，提供显式恢复凭据入口。服务端原恢复证明/停机/nonce/回执/期限校验不变。未知/不确定不当作完成。

## 设计收尾与实际浏览器验收

继续纸白/低饱和绿 A 布局：左图、右编辑、下方方案库。简短首次说明不阻挡操作。标题按钮键盘重命名；旧版本默认折叠。缩放只有“− / 相对适配比例 / ＋ / 适合窗口”；100%为适合窗口基准，不是像素1:1。

预览使用固定视口、共同最小fitScale、绝对居中；不使用 cover、保持原比例；原照片区域仍按 validRegion。1280主图实际1280×704，显示约530.906×292，完全在视口内。两图均显示约387.771×213.271，尺度与中心一致；窄屏上下排列无横向溢出。主图不裁切，略减卡片缩略图及合并状态行后，1280首行状态底部约886.5px，名称和状态均可见。

实际测1280×900 / 1440×900 / 390×844，内容宽度分别1265 / 1425 /375（滚动条占用），没有横向溢出。窄屏图完整，预览→编辑→方案列表正常页面滚动；不宣称全操作同屏。

真实点击：选择样例 → 查看整图 → 原图/区域对照 → 另存 → 合法参数变更 → 保存刷新同草稿 → 旧版本恢复 → 独立比较目标 → 缩放与键盘平移/适配 → JPEG/区域PNG下载 → 来源详情。实际文件选择器载入已有授权陶罐原照，仅blob本机预览；刷新显示缺字节，不借旧图；同SHA重载仍同草稿。实际Enter打开/提交重命名，Tab从照片到载入、从保存跳过禁用生成到下载，焦点轮廓清楚。

正式真实恢复任务6705783969e54a5f9b2b4c2b11204f2f通过正式页面找回、显示来源并下载；38462bytes/SHA4dc9204863cdf56982cc5a8b1f6bf09488a1a8da376013705074dbcaedd85f95。不是本轮生成。陶罐JPEG SHA10bc201792f8915e5a00726618c54797359fd277dc2cc09eb9f32a760b64c1c7；实际区域PNG1056×704逐像素等于记录(112,0,1168,704)裁剪。

替身实际点击：有效建议→差异→应用后仍待生成/下载禁用；无变化不应用；非法1.4拒绝；模拟超时不改方案；延迟时改版本/换照片，旧建议失效。替身复用现有 RecipeLanguage transport、schema与校验，不是 Nemotron。用正式历史失败字节的独立任务副本展示取回失败/恢复入口，未修改原失败证据，未重新执行恢复。

## 截图（运行中真实页面，无合成）

位于 C:\Project\Nebius\.local\lighttry-integration-20261011：

1. studio-desktop-1280.jpg；补充studio-desktop-1440.jpg：正式首屏，完整陶罐与主编辑。
2. studio-compare.jpg：正式两方案实测结果，标明名称/版本。
3. studio-pending.jpg：正式待生成，仅输入、服务关闭与下载禁用；studio-proposal-fixture.jpg为**隔离替身**的建议差异/应用补充，不冒充普通服务真实模型调用。
4. studio-narrow.jpg；studio-narrow-actions.jpg：正式窄屏完整图与主要操作/焦点。

browser-geometry.json记录实际视口/矩形。截图使用临时视口，已恢复默认。发现首行状态超过900px后实际压缩缩略图/状态行并重验，不裁主图。

## 回归、错误及未测项

最终Python214通过（209原有+5集成检查），Node39通过；node --check、git diff --check通过。原始首轮Python208通过/1冻结检查失败：修改了冻结覆盖的旧server.py，历史候选当然不同。没有覆盖旧冻结JSON/模型报告；离线runner允许显式新snapshot，单测在临时目录使用当前snapshot，并新增missing/mismatch拒绝测试。默认旧manifest不匹配仍拒绝，不能混合历史收费验收。

工具/代码修正记录：替身100次预算配置被生产边界拒绝exit1，改12/.20，未改生产预算；替身重启旧csrf请求被403拒绝，刷新令牌重测，不弱化来源校验；原生prompt工具未返回对话框，改可访问产品dialog后Enter验收；较早详情点击因页面初始化时序未打开，重新观察后真实打开；视口控制曾作用于当前替身标签，关闭该临时标签后核实正式innerWidth/innerHeight再截图。未遇安全策略拒绝，未绕过。

patch初版缺少无末尾换行标记/new-file mode，随后Git自动文本规范化使README字节重建不一致，校验明确失败；改为带完整行替换/末尾标记的原生patch，最终全部源码字节全等。错误来源/退出见tool-errors.json，成功与字节记录见VERIFICATION.txt。

**本轮未验证：新的真实付费 Nemotron/Cosmos/GPU端到端、云守护恢复、真实网络上传及执行中的GPU视觉反馈。** 这些接口代码保留/接通，但默认关闭；没有新GPU/模型成功声明。完整辅助技术/WCAG、触屏长拖、所有超大库性能也未穷尽；启用文字且长建议时右栏需要单区域滚动。

## 回退与四角色连续性

本轮补充四角色：
- MODIFIED_FILE：C:\Project\Nebius\.local\lighttry-integration-20261011\MODIFIED_FILE（可解析源码快照集合）。
- DIFF_FILE：C:\Project\Nebius\.local\lighttry-integration-20261011\DIFF_FILE.patch（完整字节重建，不是仅视觉差异）。
- VERIFICATION：C:\Project\Nebius\.local\lighttry-integration-20261011\VERIFICATION.txt。
- ROLLBACK：C:\Project\Nebius\.local\lighttry-integration-20261011\ROLLBACK.sh（嵌入原始字节，参数为目标副本目录）。

已在独立修改副本执行ROLLBACK，再用同命令/输入studio-source-v1检查：BASELINE studio/sharedScale/lateGuard/explicitConfirmation=false；MODIFIED这四项true；ROLLBACK恢复false，均exit0/stderr空。只是静态结构，浏览器验收另列。原文件恢复SHA逐一相等，patch重建逐一相等；之后MODIFIED_FILE仍保留新实现。

人工回退：先停止8785，再对有备份的目标副本运行bash ROLLBACK.sh TARGET_COPY_DIRECTORY核对，再按清单恢复本轮改动的源码/README；不删任务/素材/浏览器库。新增launcher、测试和报告保留为不再由旧入口引用的辅助文件。恢复旧server.py后可用旧命令查原project/.tasks；本轮新版本仍在正式v1库中，不清空。不要在其他未提交修改上盲目运行回退，应先复制比对清单。

原四角色再次读取、未替换：
C:\Project\Nebius\project\experiments\measured_controls.py
C:\Project\Nebius\.local\lighttry-development-20261011\DIFF_FILE.patch
C:\Project\Nebius\.local\lighttry-development-20261011\VERIFICATION.txt
C:\Project\Nebius\.local\lighttry-development-20261011\ROLLBACK.sh

历史SYNTHETIC输入fixed-fixture-v1：BASELINE1/MODIFIED6/ROLLBACK1，各初始化1次、exit0、stderr空，恢复SHA110519556d5f93949d6c47fa0a4df45a04d76c09b97fba7cd1c7fbd6e6d8fc9d。未重跑，不能用它证明本轮GPU/前端。

停止点：本地正式集成已可运行；等待用户评审，不自动发布/合并/开下一轮，也不启用付费链路。
