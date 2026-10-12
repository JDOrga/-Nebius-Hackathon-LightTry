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

---

# 本轮正式前端视觉收尾与同杯真实比较（2026-10-11，22时段）

继续原项目、原 start_studio.py 与8785。保留开始时所有未提交修改；不新建页面/原型、不改后端架构/认证/配方/模型/恢复证明。当前轮修改仅 next/web/index.html、workbench.css、workbench.js、scheme-state.js（追加显示纯函数），新增 tests/studio-presentation.test.js，并追加本报告。

## 显示与交互

- 主标题为照片：白蓝杯等显示名称按catalog稳定sampleId映射；未知来源使用完整结构化name，不拆分字符串。日期移到历史小标签，实际源与SHA仍在详情。
- 方案短名称原样显示；长名称用**参数显示摘要**（默认方案、晨光方案、偏暗备选等），不是改名。完整名称可展开、点标题仍编辑完整原名。重复摘要加库内家族序号区分，同家族旧版本共享序号，原planId/version/name不改变。未从名称猜日期或“变体”后缀。
- 晴日公园/粉色晨光/夜间街灯分段按钮：aria-pressed、Tab/箭头/Home/End焦点、Enter/Space激活。箭头只移动焦点，不改参数。重新点已选环境不改变方向或倍率；换环境沿用默认档/白名单/revise逻辑，不生成。
- 右栏字级/控件高度/间距回到A的清晰层级，编辑参照在侧栏滚动中保持可见。重复默认说明移除、完整名称放在结果动作后；真实推理关闭、Nemotron未配置、实验性/失败/不确定仍及时显示，按钮如实禁用。
- 主图fit/common-scale/validRegion/下载逻辑不改；杯子左右结果填充原样保留。方案卡先名称/状态，再完整名称/来源参数。当前旧版本即使折叠旧库仍显示其活动卡，不藏编辑对象。

## 正式真实比较（非替身）

实际目录/catalog有同一白蓝杯两个真实历史结果：sunny与sunrise，日期2026-10-10，均1280×704。通过正式“另存变体→粉色晨光”展示已有匹配结果，没有生成新图。

左：plan02f137df34f54c05a6423eb5ea595c08/v2，sunrise/0/1，JPEG SHA8a36f406aa5ac867ba52d11ea4eea097948e41542c9a037a125d2ba650eba1f2。
右：planaa4dae71891b45cf88e74d2c8d7290c1/v3，sunny/0/1，JPEG SHA080bb85e9d13cabdfefc6037276552bebba1dfb38ff43373ee0aba65053b5668。
输入同为1a7b31e4bbf0ca4478534552c63f2159（catalog输入SHA派生）；完整名称、参数、来源、图SHA见comparison-source.json，HTTP字节SHA分别验证。来源为历史固定预设，不补写实验参数实测记录，不改任务有效期。

真实点击：两方案比较→切对照目标（编辑identity不变）→有效区域→适合窗口→区域PNG下载。两边完整图1280×704共同比例/中心；区域均396×704，按原validRegion裁出。实际PNG下载逐像素匹配记录区域，未美化/调色。窄屏实际上下排列，额外narrow-compare.jpg为运行页面全页截图，不合成。

保存/刷新：当前参照保持相同；按照既有约定刷新返回“当前结果”，不持久化比较模式/对照下拉。这不是换了编辑目标。查看旧版本可准确显示版本与旧卡；折叠后当前旧卡保留。夜间街灯无本批结果：只输入、待生成、下载禁用；保存刷新identity相等仍待生成。没有借旧结果。

## 实际画面与回归

检查1280×900、1440×900、390×844，内容宽1265/1425/375，无横向溢出；不是浏览器缩放。完整杯子与左右实际填充均可见。首屏方案名/状态保留；侧栏较长内容仍为单独滚动，窄屏正常页面滚动，不宣称所有内容无需滚动。

本轮截图目录：C:\Project\Nebius\.local\lighttry-integration-20261011\polish
- white-cup-first.jpg：正式白蓝杯1280首屏，与上一轮同素材/视口；用户截图本身尺寸未提供，不宣称像素级同视口重现。
- white-cup-1440.jpg：1440首屏。
- white-cup-compare.jpg：正式两份已核验真实历史结果比较。
- white-cup-region-compare.jpg：实际区域双图。
- narrow-first.jpg、narrow-controls.jpg、narrow-compare.jpg：窄屏首屏、操作焦点、上下比较。
- pending-long-name.jpg：正式待生成与可展开完整长名称，原名仍完整。

Python214回归通过；Node47通过（原39+8新增显示/环境/名称/比较回归）。新增检查长名称不被拆分/改写、稳定sampleId显示、摘要不改身份、合法环境默认档与谱系、未知环境拒绝、已选环境不复位实验档、比较cursor独立、重复摘要区分。实际键盘箭头聚焦粉色晨光但选中仍晴日；Enter激活才改环境；Tab跳过关闭的生成到下载，焦点轮廓明确。

原冻结JSON与历史模型报告未覆盖；Python继续沿用显式当前离线snapshot。所有离线结果不是模型验收。本轮收费模型/GPU/云/上传/安装/提交/推送均0。当前后端/参数/素材/任务证据未修改。

## 角色与可回退

上轮四角色仍保留，未替换：C:\Project\Nebius\.local\lighttry-integration-20261011\MODIFIED_FILE、DIFF_FILE.patch、VERIFICATION.txt、ROLLBACK.sh。本轮补充polish子目录同四角色，回滚基线是本轮开始时带未提交集成的前端，不回退上轮业务集成。源码检查同输入presentation-v1：BASELINE四显示机制false，MODIFIED true，ROLLBACK恢复false，exit0、stderr空；静态检查不是视觉验收。独立副本回退恢复SHA，原生patch重建源码字节相等。不能在用户后续改动上盲目覆盖回退，先复制比较。

原实验四角色也再次读取：C:\Project\Nebius\project\experiments\measured_controls.py；C:\Project\Nebius\.local\lighttry-development-20261011\DIFF_FILE.patch；VERIFICATION.txt；ROLLBACK.sh。历史合成fixed-fixture-v1 BASELINE1/MODIFIED6/ROLLBACK1，各初始化1/exit0/stderr空，恢复SHA110519556d5f93949d6c47fa0a4df45a04d76c09b97fba7cd1c7fbd6e6d8fc9d，未重跑且不是本轮GPU。

未穷尽：全部触屏/辅助技术/系统高对比/200版本性能，真实付费链路。用户白蓝杯截图的实际像素视口未知。完成的是本轮正式前端打磨与真实已有结果比较，不是整个比赛项目验收完成。正式启动命令/地址仍见报告顶部。

### 最终Git状态补充

本轮开始HEAD为cef70911aa8ec54f4bc5971b0c98dff49c1638c0，已有未提交集成。最终核查发现执行期间HEAD变为ef1ea5fc4e8d168abbce4ada8e10a7b670564e18（Integrate the local LightTry photo studio，22:20:26+0800），本助手工具没有执行commit/push，不能判定外部操作主体。当前源码与本轮验收快照字节一致；最后仅本报告追加部分仍未提交。没有reset、改写或撤销该提交。本报告“提交/推送0”指本助手执行动作，不是声称HEAD在整个会话期间没有外部变化。回退仍仅在独立副本验证，不对当前已提交源码盲目覆盖。

最终视觉补充：下载区需要更多侧栏高度，因此桌面侧栏上限调至600px；仅缩略图高度微调，不缩小全局字体或裁主图。执行期间外部提交之后，这项CSS收尾与报告补充仍未提交；最终以git status和本轮源码快照为准，不再只列报告。


## 2026-10-12 Nemotron浮动会话
正式入口继续8785，移除旧右栏输入，新增非模态浮动聊天与同一recommend接口的有界多轮契约。详见STUDIO_CHAT_20261012.md。旧报告/外部HEAD/用户修改原样保留；没有新的真实模型或GPU验收。
