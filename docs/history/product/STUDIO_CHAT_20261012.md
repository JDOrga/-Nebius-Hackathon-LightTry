# 正式照片工作室 · Nemotron浮动会话（2026-10-12）

## 启动与边界

```powershell
python -X utf8 -B C:\Project\Nebius\project\start_studio.py
```
地址 http://127.0.0.1:8785 。已用这条命令重启最终源码。Nemotron/GPU默认关闭，无外部调用；独立测试8898已停止。不建新产品入口、不迁移存储或后端架构、不安装、不提交/推送。

本轮开始和最终HEAD均ef1ea5fc4e8d168abbce4ada8e10a7b670564e18，以实际Git核查为准。开始时STUDIO_INTEGRATION报告与CSS已有未提交修改，完整保留在本轮baseline；未reset。67份历史正式任务文件哈希全等。

## 实际修改

- C:\Project\Nebius\project\next\web\index.html：删除右栏旧输入/建议区域，右栏仅手动调光、保存/生成、下载/详情；增加全局助手入口和一个非模态浮层。
- C:\Project\Nebius\project\next\web\chat.js：唯一会话控制器、文本安全渲染、请求/响应关联、建议差异、显式应用、拖动/收起/关闭/重置/视口约束。
- C:\Project\Nebius\project\next\web\workbench.js：删旧推荐/输入/应用事件绑定，接入现有方案版本/白名单/来源逻辑；不新增生成路径。
- C:\Project\Nebius\project\next\web\workbench.css：纸白绿浮层与底部窄屏面板；保留完整画布、validRegion、共同比例、下载逻辑。
- C:\Project\Nebius\project\next\language.py：复用RecipeLanguage、同一模型适配/结构校验/组合白名单，增加可选聊天契约及解释状态、去重和服务记录关联。
- C:\Project\Nebius\project\next\server.py：服务新模块；原recommend路由/本机来源令牌/8KiB边界保留，超长文字错误更明确。
- C:\Project\Nebius\project\tests\test_studio_chat.py、studio-chat.test.js、serve_chat_fixture.py：独立离线测试与显式transport替身，无生产场景开关。
- C:\Project\Nebius\project\docs\STUDIO_INTEGRATION_20261011.md：仅追加本报告链接，不改历史结论。

## 会话/界面规则

默认不弹出。首次打开工作区中央，无背景遮罩，仍可操作工作台；桌面可拖动、收起/恢复、关闭、重置位置，窗口变化限制可见范围。窄屏近全屏底部面板，固定可见关闭入口，采用dvh/visualViewport响应可视高度。Escape关闭并回焦入口；Enter发送，Shift+Enter换行，composition/isComposing/229不发送。

会话按inputId+planId，版本变化仍在同一会话；切换比较对象不切编辑会话。换照片/家族明确换上下文；下一请求以当前版本配方为准。只在本标签sessionStorage保存最近8条文字、服务建议ID与状态，最多4会话，不保存照片、名字标签、路径、认证或密钥。刷新保留短会话文字，但已保存旧卡不具有直接应用权限；已应用/拒绝状态区别保留，未知建议标旧上下文。关闭面板不清会话也不取消上游。

建议卡显示环境/加载偏移/HDR倍率前后值、理由、实验性说明与应用/拒绝。普通解释/澄清/拒绝无参数卡不产生版本。同参数禁用应用；成功应用显示实际方案ID与版本，再点禁用。应用、保存、生成独立；聊天代码没有任务提交接口。无匹配真实结果仍仅输入/待生成、禁下载。

手动变化、换参照、继续编辑文字会使旧建议不可直接应用。过期响应仍进入其原会话，标旧上下文，不覆盖新照片或参数；沿用需基于当前状态重新请求。关闭不假装上游取消，65秒仅停止本机等待，不自动重试。

## 请求契约和兼容

旧五字段currentScheme/currentResult/text/history/replyLanguage保持兼容，旧单轮响应仍只允许ready/clarification/unsupported。不改配置文件、模型、thinking、40960输出上限、60秒总超时、最多一次修复、12次/.20预算信封、未知费用保留、日志边界。正在运行的服务需重启加载新源码，但不得重置旧账本。

同一POST /api/lighting/recommend可增加chat：
```
{schemaVersion:1,sessionId:HEX32,requestId:HEX32,
 snapshot:{inputId,planId,version,recipeKey},
 messages:[{role:'user'|'assistant',text}],
 operations:[{operationId,state:'proposed'|'applied'|'rejected'|'stale'}]}
```

发送前调用既有normalize接口，服务再次规范化currentScheme、重新算recipeKey，快照不一致拒绝。currentScheme是现有客户端方案业务快照，不是声称服务已有权威用户库；服务校验结构/范围/身份关联，不信任客户端“validated”。发送给模型的selectedScheme含规范化配方/HDR身份，优先于所有历史；不发送名称、路径、图片字节，也不把照片标签当看图证据。

最多8条、每条320字、合计2400字历史，最多4操作；当前需求600字，HTTP8KiB、总模型请求15000 UTF-8字节上限，响应原始4096字符、理由180字/问题100字。截断只丢最老文字，没有虚构总结。操作ID必须来自当前服务已接受账本，并核对照片/方案家族；具体建议由服务账本解析，不采信客户端建议参数。“已应用”是客户端本地动作报告，明确为reportedState而非服务端落库证明；实际当前规范化配方始终优先，之后的手动变化不被旧建议覆盖。

聊天schema追加explanation（null参数）；仍单个有界结构响应，不是无限自由文本/自动工具代理。所有输出校验语言、参数组合、能力/看图承诺；HTML标签/秘密标记拒绝；前端所有聊天按textContent渲染。请求ID冲突拒绝，相同接受请求复用已接受响应（跨服务重启也可）；重复等待/失败/不确定请求不再发送，保留计费不确定性。新请求仍须用户明确发送。服务私有账本只新增关联ID/指纹，不记录完整会话/图片。

## 已观察的验收（不等于真实Nemotron质量）

Python220全部通过，Node52全部通过，语法检查/git diff --check通过。新增Python6组、Node5组；保留旧冻结候选，显式离线当前snapshot测试通过，旧候选不匹配仍拒绝。没有改历史冻结JSON或模型验收报告。

真实浏览器1280×900、1440×900、390×844：无横向溢出，工作室完整图/右栏/方案卡保留；浮层可拖动（实测x772/y149）、收起/恢复/关闭、重置，缩放到窄屏后仍在视口。窄屏374×约759.6、top76.4/bottom836，关闭与输入可见。正文/按钮层级可读，浮层初始可遮部分照片，主动拖动/收起即可继续比较，不使用cover裁图或遮罩。

正式实际点击：收起聊天→两份历史白蓝杯比较→切另一对象，编辑参照不变；保存/刷新仍02f137df/v2，模式按既有约定回当前结果且助手不自动打开；JPEG实际下载，源仍为原历史晨光结果。正式服务未配置的发送禁用，未伪造回复。任务恢复/身份/区域导出由既有回归覆盖，本轮没有重复收费任务或重新执行历史恢复。

隔离8898使用同一前端/RecipeLanguage的真实测试transport，接收记录在fixture/received-context.jsonl。第一轮偏暗、第二轮询问理由的真实请求带前一轮对话与proposed操作；解释不新增版本，方向备选有实验性提示；显式应用至v2和v4、重复应用禁用、不触发生成，无结果不能下载。另测同参数、澄清、色温拒绝、4秒延迟期间关闭/改版本/换照片/改文字，旧响应留原会话且不可应用；超时明确失败不自动重试。预算到12次真实替身调用后拒绝追加，未重置账本。危险用户HTML按文字显示，DOM无注入img；危险模型HTML/非法参数/过长历史/重复ID/重启去重由独立transport回归覆盖，不冒充正式模型验收。

错误记录保留：最初用系统Python默认GBK读UTF-8测试文件失败，改-X utf8；review-venv缺CPU torch导致一个回归错误，使用已有cpu-venv修复，未安装；替身相对assets路径按project根解析导致缺素材，改绝对路径；初版替身回复夹transport英文被语言校验拒绝，改中文、保留两次失败/计数；IME测试假DOM遗漏value造成异步测试错误，补空值后通过。没有权限拒绝或绕过。

## 真实截图

均来自运行页面，无合成：C:\Project\Nebius\.local\lighttry-chat-20261012
- chat-desktop.jpg、chat-desktop-1440.jpg：正式8785打开聊天，服务关闭。
- chat-suggestion-fixture.jpg：**隔离8898测试transport**的真实页面建议差异，不是Nemotron响应。
- chat-collapsed.jpg：正式8785收起后的真实历史双方案比较。
- chat-narrow.jpg：正式8785窄屏面板。

未测：真实收费Nemotron多轮理解/解释质量、供应商工具schema中新增explanation的实际接受度、真实网络超时/断线计费恢复、不同操作系统实际中文IME及手机软键盘/触控长拖、完整辅助技术/WCAG。组合事件用离线DOM处理器测试；实际浏览器中文输入和Shift+Enter/Enter/Escape均有观察，不能把fill中文当实际IME验收。以后真实付费验收需要先显式授权次数/预算，确认真实数据范围仅文字/配置，再检查两三轮保环境/理由/不应用备选、同参数、schema修复、语言与能力拒绝、延迟/不确定计费和应用后版本。不开放GPU自动生成。

## 回退和四角色

本轮原始字节是开始时带用户未提交修改的baseline，不是Git HEAD。补充四角色（不替代历史记录）：
- MODIFIED_FILE：C:\Project\Nebius\.local\lighttry-chat-20261012\MODIFIED_FILE
- DIFF_FILE：C:\Project\Nebius\.local\lighttry-chat-20261012\DIFF_FILE.patch
- VERIFICATION.txt：C:\Project\Nebius\.local\lighttry-chat-20261012\VERIFICATION.txt
- ROLLBACK.sh：C:\Project\Nebius\.local\lighttry-chat-20261012\ROLLBACK.sh

同命令chat-source-v1：BASELINE floatingChat/boundedConversation/requestDedup=false、oldSidebarInput=true；MODIFIED前三true、oldSidebarInput=false；ROLLBACK恢复BASELINE，exit0、stderr空。仅静态结构；实际视觉/transport证据另列。独立副本回退恢复原始SHA，原生patch重建源码/文档字节全等；改版源码仍保留。回退先停止8785、复制当前工作区、对目标副本执行bash ROLLBACK.sh TARGET_COPY，再核对哈希及后续用户变动后选择性恢复，不覆盖后续改动或任务数据。新增文件不删除，但旧索引不引用聊天。

历史四角色已再次重开、不覆盖：
C:\Project\Nebius\project\experiments\measured_controls.py
C:\Project\Nebius\.local\lighttry-development-20261011\DIFF_FILE.patch
C:\Project\Nebius\.local\lighttry-development-20261011\VERIFICATION.txt
C:\Project\Nebius\.local\lighttry-development-20261011\ROLLBACK.sh
历史fixed-fixture-v1 BASELINE1/MODIFIED6/ROLLBACK1，各exit0/初始化1/空stderr；恢复SHA110519556d5f93949d6c47fa0a4df45a04d76c09b97fba7cd1c7fbd6e6d8fc9d，未重跑，非本轮GPU证据。既有integration及polish四角色也保留重开。

停止于本地交付/交互评审，不宣称真实模型通过或整个比赛项目完成。
