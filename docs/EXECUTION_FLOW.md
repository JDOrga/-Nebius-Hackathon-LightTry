> 2026-10-19 英文追问补光方案修复已仅切换 CPU 网页上线：针对明确指向现有程序化补光区的减弱请求，模型若误把光区强度写成超界的整体倍率，服务端在同一选中快照上保守重建待确认的 `edit_zone` 建议；不自动应用、不生成、不多发收费调用。不能确定目标、原值不符、环境模式或越界时仍不给可应用参数；无效参数的英文降级说明改为英文，不加严模型正文语言判断。原/改/回滚相同英文输入分别为不可应用且夹中文 / `ready`、key=6、fill=4、纯英文说明 / 原行为；本地 Python 定向 50 项、Node 97 项通过，候选镜像内聊天 21 项与配方 29 项通过。源码提交 `3d1cfba` 已推送 `origin/main`；从当前线上镜像 `sha256:bf34334d37cdc471e6e7e1fe3eacc4c071651684aff8ee8e695d940f8f34e3fc` 仅叠加 `recipe_language.py`，新镜像 `sha256:f1930837fa66719ff0948811d1bcb7aa719a9112db1faa52383fe4e084aa5e85` 已运行，线上源码 SHA `9c2cb88898fa7b982588c0a39d0e24ef7a8662386820551bb20626410937a738`。旧网页容器 `lighttry-cpu-before-chat-followup-9c2cb88-20261019` 已停止并保留回滚；切换前后独立守护 STOPPED、instances=[]、verifiedStopped=true、instancesEmpty=true、sleepHeld=false，活动队列和文字在途均为0，守护容器 ID 未变。本机登录200、匿名健康401、公网 HTTPS 登录200 且 TLS 校验0；未启停 GPU，未由执行者发起收费模型请求。真实登录态聊天效果待用户刷新/重新登录后验证，不冒充已验收。沿用 `artifacts/chat-followup-fix-20261019/` 原四角色，部署补充证据在 `.local/chat-followup-live/`。

> 2026-10-19 英文界面刷新短暂闪中文已仅切换 CPU 网页上线：静态 `index.html` 在翻译完成前用首屏隐藏门控，`workbench.js` 调用 `installI18n()` 后立即解除；不改语言 cookie、模型正文或 GPU 控制。首次本地方案用内联模块，但生产 CSP `script-src 'self'` 禁止内联，故在部署前改为原外部模块并重新验收，未将该失败方案上线。使用生产同款 CSP、英文 cookie、真实前端模块延迟 1400ms 的 Chrome 检查，原版首屏可见中文、修改版首屏隐藏且加载后英文、回滚副本恢复原行为；本地 Node 97 项通过，两文件补丁重建与回滚哈希一致。源码提交 `84f3703` 已推送 `origin/main`；以线上镜像 `sha256:28aab94785a6d843ce3811fe4207ca3512f6098fd44815f04847feac3156f68c` 为基线只叠加 `index.html`、`workbench.js`，新镜像 `sha256:bf34334d37cdc471e6e7e1fe3eacc4c071651684aff8ee8e695d940f8f34e3fc` 已运行，两文件线上 SHA 分别为 `ec17338fb02e4c867f17ab7548838946eda513f6e722aa0e5411c36389df9c1e`、`53898323aa55cf83a19fc4eb919abed2e2e6576302510f1eb07cea62b1d01f18`，`i18n.js` 未变。旧网页容器 `lighttry-cpu-before-locale-flash-84f3703-20261019` 已停止并保留回滚；切换前后独立守护 STOPPED、instances=[]、verifiedStopped=true、instancesEmpty=true、sleepHeld=false，活动队列及文字在途均为 0，守护容器 ID 未变。公网 HTTPS `/login` 200、TLS 验证 0，未登录首页 401；登录态生产浏览器刷新效果仍待用户自行验收，不冒充已完成。未启停 GPU、未发起收费模型调用；证据续写 `.local/locale-flash/` 原四角色及部署记录。

> 2026-10-19 英文界面聊天状态与系统性漏译审计已仅切换 CPU 网页上线：截图中的编辑上下文变更、已应用但尚未生成提示补译；另覆盖受控状态/错误/恢复文案、GPU 进度和嵌套过期观测、原生确认框与参数校验、英文默认光区名称，并将用户聊天及模型正文排除界面翻译。扫描前端 679 个唯一中文源码字符串/片段，剩余 73 个不在孤立片段上直接翻译的项目已分类为 66 个拼接片段、5 个持久方案身份/来源名称、语言选项“中文”及内部模型协议标签；不是 73 条已确认可见漏译。Node 97 项、服务端语言 3 项通过；本地 DOM 检查静态页面、12 个动态样本、真实聊天已应用/只读/上下文变更状态及中英往返切换无受控中文残留，模型正文保持原样。六文件原/改/回滚同输入和补丁重建通过。源码提交 `ecb449d` 已推送 `origin/main`；以线上镜像 `sha256:3476a57716f97eb161b62e44a1a1aad716103ae7fcaa0f3878cd10b9f9ee521b` 为基线仅叠加五个网页脚本，新镜像 `sha256:28aab94785a6d843ce3811fe4207ca3512f6098fd44815f04847feac3156f68c`，线上逐文件 SHA 与候选清单一致，旧网页容器 `lighttry-cpu-before-english-audit-ecb449d-20261019` 保留回滚。切换前后独立守护 STOPPED、instances=[]、verifiedStopped=true、instancesEmpty=true、sleepHeld=false，活动队列与文字在途为 0，守护容器 ID 未变；公网 HTTPS `/login` 200、TLS 验证 0。用户 Edge 页面刷新后要求重新登录，故登录态生产浏览器视觉检查待用户自行登录后继续，不能冒充完成。未启停 GPU、未调用收费模型；证据复用 `.local/english-ui-20261019/` 的原四角色及补充审计记录。

> 2026-10-19 英文界面三处残留中文已上线：`project/web/i18n.js` 补译 GPU 启动收费提示、未载入原图的禁用提示，并递归翻译模型监控耗时中的“分／秒”（含小数秒）。源码提交 `55ba96b` 已推送 `origin/main`，本地 Node 94 项通过；原/改/回滚同输入分别显示中文/英文/中文，回滚哈希等于原版。以当时线上 CPU 网页镜像 `sha256:39b64149a21f580a9e6de944eb5266c09bbab1d071abc1e413d224209cbbafd3` 为基线仅覆盖 `i18n.js`，新镜像 `sha256:3476a57716f97eb161b62e44a1a1aad716103ae7fcaa0f3878cd10b9f9ee521b`；线上脚本 SHA 为 `bb7509b7dee95ad5bdb3f479836f05f9d119832804ef4ee38d37de802c23edcf`，其他核对的前端文件不变。首次构建因把镜像 ID 当作 Dockerfile 仓库名，在切换前退出 1；首次切换因沿用旧 CSS/聊天哈希预检退出 17，线上未改；修正后切换退出 0。切换前后独立守护 STOPPED、instances=[]、verifiedStopped=true、instancesEmpty=true、sleepHeld=false，队列及文字在途均为 0，守护容器 ID 未变；公网 HTTPS `/login` 200、TLS 验证 0，受保护的 `/i18n.js` 匿名请求 401，故登录态视觉效果仍待用户刷新验收。未启停 GPU、未调用收费模型；旧网页容器 `lighttry-cpu-before-english-ui-55ba96b-20261019` 保留，证据续写 `.local/english-ui-20261019/` 原四角色记录。

> 2026-10-19 Nemotron 聊天 Markdown 已仅切换 CPU 网页上线：源码提交 `62f3e6d` 已推送 `origin/main`，94 项 Node 测试通过。先只读确认线上语言镜像 `sha256:17208c2d94562bae312678854a5375b96b2c8bae8816411c9c4418b4b4caedc7` 的聊天、CSS、翻译脚本与提交前源码规范化内容一致，因此没有全量覆盖，仅叠加 `chat.js` 与 `workbench.css`。首次候选构建因归档成员检查在切换前退出 10，修正后隔离构建并核对候选镜像 `sha256:39b64149a21f580a9e6de944eb5266c09bbab1d071abc1e413d224209cbbafd3`，翻译脚本哈希不变。切换 exit 0，运行中 `chat.js` SHA 为 `ad96533a297e621162c1bd5997a803306480e865121486cdb2431cb9d1b0f80a`、CSS 为 `bf307305ffc16503e86d39fd727f138687354a15ea1dbe56e59eafb5a5d19b46`；公网 HTTPS `/login` 200、TLS 验证 0。切换前后守护 STOPPED、instances=[]、verifiedStopped=true、instancesEmpty=true、sleepHeld=false，GPU 队列及 Nemotron 在途均为 0，守护 ID 未变；未启停 GPU、未调用付费模型。旧网页容器 `lighttry-cpu-before-chat-markdown-62f3e6d-20261019` 留作回滚。真实模型回复与登录态浏览器视觉效果待用户刷新后验收，证据扩展原 `artifacts/chat-markdown-20261019/` 四角色记录。

> 2026-10-19 英文界面遗漏补译续修已上线：聊天等待/完成状态、预览待生成、照片下拉与方案库草稿标签新增英文映射；前端请求 `replyLanguage` 改随所选界面语言，不再固定中文。方案库参数摘要的内置环境/默认光照与 GPU 停止诊断后追加的过期快照、断连说明也按句翻译，不翻译模型正文及用户自定义方案名。修前/修后/回滚同输入分别显示中文/英文/中文，前端 93 项 Node 测试通过。仅切换 CPU 网页，镜像 `sha256:17208c2d94562bae312678854a5375b96b2c8bae8816411c9c4418b4b4caedc7`，线上文件 SHA 一致，公网 HTTPS 登录200；切换前后独立守护 STOPPED、实例空、队列空且守护 ID 未变。未启停 GPU、未进行收费模型调用；英文真实模型回复与登录态视觉效果仍待用户刷新验收。证据复用 `.local/ui-language-fix-20261019/`，旧容器保留。

> 2026-10-19 英文界面漏译修复已同步远端源码并保持线上：四个前端文件的累积补丁在独立工作树通过 91 项 Node 测试与动态方案差异核查，提交 `5c9c01c` 已快进推送 `origin/main`。生产网页仍运行同内容镜像 `sha256:f3af76c85336a2d368b4ed23ceaa507c4e6b704685141a00c747d7b9b1780be2`；只读确认镜像文件哈希及公网 HTTPS 登录，无 GPU 启停或收费模型调用。原工作区保留历史文件不动，后续从远端 main 构建已含修复。

> 2026-10-19 英文界面 Nemotron 方案差异中文标签漏译已补充上线：问题来自前端 `userDifferences()` 的动态文案而非模型正文。仅在前端翻译脚本对方案差异标题、受控字段名和状态值作白名单翻译，不改用户自定义名称。前一线上版/修复/回滚同输入分别中文/英文/中文；候选 91 项 Node 通过。基于上一网页镜像仅覆盖 `web/i18n.js`，新镜像 sha256:f3af76c85336a2d368b4ed23ceaa507c4e6b704685141a00c747d7b9b1780be2，线上脚本 SHA 与候选一致，本机及公网 HTTPS 登录200。切换前后独立守护 STOPPED、实例空、队列空，守护 ID 未变；未启停 GPU、未调用收费模型。登录态英文视觉验收需用户刷新；Git 原前端源码未改，累积补丁与四角色在 `.local/ui-language-fix-20261019/`，未来源码部署前须应用补丁。

> 2026-10-19 英文界面三处漏译已仅切换 CPU 网页容器上线：工作台 GPU 启动/停止提交提示补充英文精确映射；HDR 文件选择改为可翻译的自定义可见标签，原生 file input 保留可访问与上传行为。候选副本原/改/回滚同输入分别中文/英文/中文，Node 91 项通过；从当前线上镜像叠加三个前端文件，镜像 sha256:894c2b2fc6c56d4f2514a80d0380b3e93a8dae92e4388e248bc5e69a1a6c1d68，线上逐文件 SHA 匹配。切换前后独立守护 STOPPED、实例空、队列空，守护 ID 未变；本机登录及公网 HTTPS 登录均 200。未启停 GPU、未调用收费模型；需用户刷新后做英文登录态视觉验收。原 Git 源码未改，补丁与四角色验证在 `.local/ui-language-fix-20261019/`，未来源码部署前须应用该补丁。

> 2026-10-19 单次文字调用保护修复已部署：用户真实请求“给我一个方案，帮场景调暗些”在上版线上触发 `LANGUAGE_MISMATCH`，私有账本只读元数据确认该次合法 `ready` 候选为英文说明，`repairLimitThisOperation=0`、attempt0、仅一条记录、约4.52秒完成；此前离线默认一次修正测试不能代表生产零修正配置，原失败收据保持只读。新逻辑在生产零修正配置下不因语言单独拒绝有界 `ready` 参数，而用服务端明确的中文通用提示引导用户核对差异；中英混用和明确英文请求照常通过。对用户明确新增光区、原方案为环境模式且没有要求保持环境时，已校验的环境光区候选在本地转换为程序化候选，清除 HDR 环境引用并提示替换影响；只返回待确认建议，不自动应用、生成或额外调用模型。显式“保持环境模式”仍不强转。原/改/回滚同输入及补丁重建在本地通过，新增生产零修正回归后，本地与 Python 3.14 隔离网络候选各通过聊天20项、配方29项；未运行全量套件或真实模型重试。以当前线上 `chat-zone-language-6f31764` 为基线仅覆盖 `recipe_language.py`，新网页镜像 `lighttry-cpu:one-shot-chat-50b0b97` 为 `sha256:85cd11392038d5bdd88cf8d332baa8c166d98661f20e8d008f27711b6060523e`，源码 SHA `50b0b978be688b9ea62736a994e38539d31f049efc65881a27e24cf4de0c8f3d`。切换前后独立守护均为 STOPPED、instances=[]、verifiedStopped=true、instancesEmpty=true、sleepHeld=false，活动队列和文字在途为0，client0/operator25 调用计数未增加；只切换网页，旧容器 `lighttry-cpu-before-one-shot-chat-20261019` 保留，守护 ID 未变。本机登录200、匿名健康401、公网 HTTPS 登录200 且 TLS 校验通过。未启停 GPU、未由执行者调用付费模型；修后真实聊天效果待用户刷新重新登录后验证。证据补充 `.local/chat-zone-language-fix/one-shot/` 及服务器 `/srv/lighttry-backups/before-one-shot-chat-20261019/`。

> 2026-10-19 聊天语言与光区方案修复已部署（其生产零修正失配已由上方记录更正）：中文聊天请求只在主要答复完全无中文时要求一次修正，允许少量英文混用及明确英文请求；用户在环境模式要求新增光区时，提示模型直接提出程序化布光及原 HDR 环境替换，并将原先立即降级解释的 `INACTIVE_ZONE_CHANGE` 改为先使用既定一次修正机会，仍须用户确认应用。原/修改/回滚同输入离线验证：原版英文答复直接接受、光区仅解释；修改版分别修成中文答复及程序化 `ready` 方案；回滚复现原行为。Git 源码与新增回归、Python 3.14 候选镜像在隔离网络内各通过聊天18项、配方29项；未运行全量套件，也未调用真实模型。严格 SSH pin 传输核验后，以线上 `ready-question-8265b5c` 镜像为基线仅覆盖 `recipe_language.py`，新网页镜像 `lighttry-cpu:chat-zone-language-6f31764` 为 `sha256:3efb639ccc1fdf2d6f1410220060808c8366c57baf1b091c1e3d3c077e3ab096`，源码 SHA `6f31764b293acdc0c536d3d70d2e9fdb9f551b7944a25664cf7b8a4d40dc00bf`。切换前后守护均为 STOPPED、instances=[]、verifiedStopped=true、instancesEmpty=true、sleepHeld=false，活动队列与文字在途为0，文字调用计数保持 client0/operator24；仅切换网页，旧容器 `lighttry-cpu-before-chat-zone-20261019` 保留，守护 ID 未变。新网页本机登录200、匿名健康401、公网 HTTPS 登录200 且 TLS 校验通过。未启停 GPU、未发起付费模型调用；真实 Nemotron 输出质量当时尚未验证，后续失败见上方记录。证据扩展 `.local/chat-zone-language-fix/` 及服务器 `/srv/lighttry-backups/before-chat-zone-20261019/`。

> 2026-10-18 聊天方案追问修复已上线：在原 `nemotron-chat-29efc0f` 网页镜像上仅替换 `recipe_language.py`，允许聊天 `ready` 方案携带可选追问，仍拒绝无理由方案；非聊天方案继续要求空追问。原/修复/回滚同输入分别拒绝/接受/拒绝；本地聊天与配方 45 项、线上候选镜像隔离网络 45 项定向测试通过。全量本机测试因当前 Python 缺少 numpy、waitress 等依赖失败，未声称全量通过；首次候选测试因镜像不含测试目录失败，后将两测试文件只读挂载复跑通过，错误记录保留。严格 SSH pin 传输并核验哈希，候选镜像 `lighttry-cpu:ready-question-8265b5c` 为 `sha256:44dc03c4fbee0c27d7b59285449d5559af459623196d47f1ec3a70d48673deab`。切换前后独立守护均为 STOPPED、instances=[]、verifiedStopped=true、instancesEmpty=true、sleepHeld=false，活动队列为空；仅切换网页容器，旧容器 `lighttry-cpu-before-ready-question-20261018` 保留回滚，守护 ID 未变。新网页源码 SHA `8265b5cf222512c65c047ebc51213742c2a90ad8893887cb62a8039911c6db43`，本机登录200、匿名健康401、公网 HTTPS 登录200 且 TLS 校验通过。未启停 GPU、未调用付费模型；真实 Nemotron 对话效果仍待用户刷新后验收。证据复用 `.local/chat-ready-question-fix/` 及服务器 `/srv/lighttry-backups/before-ready-question-20261018/`。

> 2026-10-18 Nemotron 聊天修复已部署：先 git pull --ff-only origin main 确认最新提交 29efc0f，再以现有线上 manual-stop-3568229 镜像仅覆盖 language.py、recipe_language.py、web/chat.js、web/i18n-en.js、web/index.html；五文件原基线规范化 SHA 均匹配 Git 上版，保留其他生产修复、素材、配置和数据。源码经严格 SSH pin 的 SCP 传至阿里云后本机构建 lighttry-cpu:nemotron-chat-29efc0f，镜像 sha256:463cabcd8830ae1e9d2e50dd8e07c8d82c3b6eb826a98bf64b6c5150ae4b276b；未推送镜像注册仓库。候选在实际 Python 3.14 镜像中隔离网络运行 50 项聊天/协议/配方测试通过（既有 light_console.py 无效转义警告仍在）；此前本地 91 项前端测试通过。部署前读取独立守护收据确认 STOPPED、instances=[]，持久会话 verifiedStopped=true、instancesEmpty=true、sleepHeld=false，活动队列为空并备份 SQLite；只切换网页容器，7.14 秒内验证登录恢复，公网 HTTPS /login 200。新网页容器 f135a3f21db72e00f3ff7c1db25c5a819bd381b7a2a3f4f85db686e46bd24df6，原网页保留 lighttry-cpu-rollback-chat-29efc0f。守护容器 ID、GPU 会话、原截止与供应商尝试记录均未改变，未发起启停或真实模型调用；五文件部署后哈希匹配。普通文字回复及宽松聊天已上线，真实模型聊天质量尚待用户刷新重新登录后验收。证据复用服务器原账本 nemotron-chat-29efc0f/ 的 before-inspect.json、build.log、offline-tests.log、workspace-before.sqlite3 和 verified.json。

> 2026-10-18 22:39 CST 手动停机入口修复已上线（GPU/守护未重启）：用户明确要求STARTING、LOADING、UNKNOWN均能手动停机，构建前拉取代码且不得重启GPU。提交 `3568229` 移除canStop对网页内存中旧scopeId必须等于最新持久会话scopeId的依赖；仍要求已登录、同一配置资源、已知当前会话、未确认释放且未提交停机，普通用户他人任务保护不变。当前会话ID由服务端最新快照返回，POST继续在队列锁内核对最新ID并检查其他用户任务；旧ID404、已发停机请求保持幂等，不以状态新鲜/READY/启动预算有效为停机前提。62项Python回归通过（跳过1项），18项前端按钮测试通过，覆盖旧/过期scope下STARTING/LOADING/UNKNOWN（含陈旧快照）、资源/身份不匹配、重复停机条件及既有权限。初次新增测试因Mock保护模式不可序列化导致422，修正测试fixture后复跑通过，生产代码不受该fixture故障影响。已先git pull --ff-only确认最新，提交推送后再次pull确认，再构建 `lighttry-cpu:manual-stop-3568229`。镜像以当前线上基线仅覆盖service.py；生产基线与Git上版仅CRLF/LF不同，规范化SHA一致，差异检查确认仅该条件及注释变化，其他生产功能未覆盖。候选隔离网络读取当前真实会话快照，以过期旧scope验证canStop=true，无云控制调用。仅切换网页容器，约6.47秒内恢复CPU心跳；旧网页保留 `lighttry-cpu-rollback-stop-3568229`。守护ID保持ea5e3a511cabd84a97075c3b99135cedb90ca7b30d1646ade0bb45adade65f18，GPU会话3280eef2ad9a4a1081a6d10ce7a39481的runningAt/workDeadline/stopDeadline、restart尝试1与stop尝试0均未改，无启停请求；原23:28:17 CST截止不变。切换前后GPU均READY，切换后固定证书pin认证worker健康GET匹配会话/资源/主机、modelState=ready/modelLoaded=true，网页HTTPS登录200；生产方法线上只读复核当前与过期旧scope均canStop=true。未实际点击停机按钮，以遵守保持GPU运行要求；浏览器刷新重新登录后可用，不能声称已在本轮停机实机验收。helper与GPU冻结包未改。新网页容器ID ceb8671f7825b1d23a0518ac2d5bb791bcb5e6ab915aaa56d78d6871eec83809，镜像sha256:ee5a2a1a4f872b6fba9ae0799da6730699543d7bea0505b4b0731ec43d83cce8。证据复用服务器原账本manual-stop-3568229/：inspect、构建日志、基线源码、SQLite快照、candidate-live-cache-read、cutover、verified.json。其他用户工作区未提交改动保持原状。

> 2026-10-18 22:30 CST 启动字段缺失改进已上线并通过15秒复测（模型加载中）：用户确认“现在停机上线，并新启动一次”。拉取时远端新增 `45095b7` 安全CLI错误分类，已在不覆盖其他工作区改动的情况下合并为 `2216543`，重跑58项定向测试通过（跳过1项），再次git pull --ff-only确认最新后再构建。候选仅覆盖nebius_provider.py，同时包含 `d456f84` 启动映射与安全错误分类；两镜像隔离重放通过，helper/冻结GPU包未改。旧会话f1ea82b0aa7844a29956dbb0a72445c9仅停机一次，独立确认STOPPED、instances=[]、sleepHeld=false，CPU守护仍空闲；随后切换网页/守护为 `lighttry-cpu:startup-pending-2216543-web`、`lighttry-cpu:startup-pending-2216543-guard`，旧容器保留后缀 `-rollback-startup-2216543`，配置/挂载逐项相同，约9.04秒完成，实际两端引导预检通过。按本轮新授权，经现有scope/预检/单次start控制链创建会话 `3280eef2ad9a4a1081a6d10ce7a39481`，restart命令真实进入runner时间1792333605.5270758；+15.000110秒采样，供应商原始STARTING且instances字段省略，CPU实时缓存已为STARTING/providerState=STARTING、error=null/lastObservationFailure=null；生产gpu_entry_info应用同一实时快照输出STARTING、active=true、diagnostic=null、stale=false、canStart=false、canGenerate=false。此处为生产序列化方法与实时数据的实机集成验证，未冒充重新登录后浏览器实际HTTP正文验收。启动后整体RUNNING但无法确定唯一RUNNING实例仍会短暂UNKNOWN（NEBIUS_CURRENT_VM_NOT_UNIQUE），此处保留严格主机校验，未扩大本次放行；其后自动恢复并完成同一安装。22:28:17首次可靠RUNNING，原最晚停机23:28:17 CST，22:28:50部署完成；22:30:09核对LOADING/providerRUNNING、stopSent=false、restart尝试1、dispatches=0、活动队列0，两个模型checkpoint_read 5/9，公网HTTPS登录200。没有重复启动、提交生成或改截止；模型READY与图片结果尚未验收。网页重启后需刷新重新登录。证据复用服务器原账本startup-pending-d456f84/merged-2216543/的构建/离线重放、cutover、single-start-and-signal15、new-session-followup和verified.json；原停机证明在上层目录，旧失败证据保留。

> 2026-10-18 启动期缺实例字段状态改进已准备（未上线）：提交 `d456f84` 仅允许已通过项目/资源/公钥校验的PROVISIONING、STARTING、IMAGE_PULLING在instances字段省略时继续映射STARTING，明确instances=null和instancesProof=startup-instance-list-pending，不伪造空实例、不赋予hostIdentity/READY/生成许可。显式null/格式错误仍拒绝，RUNNING主机验证和STOPPED独立空实例证明不变；STARTING也不能满足新开机所需STOPPED预检。测试覆盖原始阶段省略字段、错误字段、项目/密钥拒绝、守护不进入UNKNOWN、前端接口active=true/diagnostic=null/canGenerate=false以及禁止重复启动；57项定向测试通过（跳过1项）。最初一次因测试插入位置错误产生KeyError，已修正并重跑通过，不算生产故障。按用户新增要求，构建前执行git fetch与git pull --ff-only（already up to date），保留工作区其他未提交改动；在拉取后重建服务器候选 `lighttry-cpu:startup-pending-d456f84-web` 与 `lighttry-cpu:startup-pending-d456f84-guard`，以现有生产基线仅覆盖nebius_provider.py。两镜像隔离网络离线重放已观测到的STARTING缺列表形状通过，helper保持ff867dd0219fe2ff2c07e5d538fe938aa6bf069369c2f34a85f868e0f4211f41、冻结GPU包未改。当前会话f1ea82b0aa7844a29956dbb0a72445c9仍为LOADING/providerRUNNING，无stopSent，原23:17:07 CST截止不改；未切换运行守护或重发开机。已呈现候选变更，等待用户决定是否停机上线并新授权启动一次；不继承已执行完毕的15秒测试启动授权。证据复用服务器原账本bootstrap-recovery-63384bc/startup-pending-d456f84/，其中prepared-after-pull.json和*-build-after-pull.log记录先拉取后构建。

> 2026-10-18 22:18 CST 单次重启后15秒信号实测（未修改状态映射）：用户先要求接口恢复则仅启动一次；新会话 `1b19fa3544fe4247a7d70058e6be0c9a` 于22:07:39创建并单次启动，22:09:11可靠RUNNING、22:09:51部署完成，随后用户明确改为停机重启测15秒信号，未验收其模型READY。按新指令仅停止一次，独立守护核实STOPPED、instances=[]、sleepHeld=false，CPU守护保持空闲，再从用户已登录Edge页面正常点击启动及确认（不是构造认证旁路），建立会话 `f1ea82b0aa7844a29956dbb0a72445c9`。真实entry-start响应为HTTP202 application/json，仅说明请求受理。CLI restart成功收据结束时间减593ms单调耗时，估算命令发出时间22:15:44.242347（有毫秒舍入误差）；22:15:59.243497即约+15.00115秒发出唯一一次额外只读DevLab采样，+15.41956秒收到响应。资源/项目身份匹配，原始status.state=STARTING，status.instances字段尚缺失，不能把缺失当作已释放空实例；同刻CPU持久化state=UNKNOWN/providerState=null/error=OBSERVATION_UNCERTAIN/lastFailure=NEBIUS_INSTANCES_PROOF_REQUIRED、startSent=true/stopSent=false/runningAt=null。代码_read对任何非STOPPED状态省略instances均拒绝，因此云端STARTING被映射成查询不确定，这是本次已证明的早期告警触发条件；未凭此放宽RUNNING身份或STOPPED释放证明。浏览器定点GET受到CDP paused-response阻塞，未取得15秒精确HTTP响应正文；保留网络元数据中+11.694秒、+26.760秒entry-status均HTTP200 application/json（Fetch）；不能声称直接验收了15秒响应body。用户提供22:15:53“发生故障/GPU状态无法确认”及22:16:48“启动中”两张截图作真实前端显示证据。随后22:17:07可靠RUNNING，原最晚停机23:17:07 CST，22:17:46部署完成，22:18:02本地快照LOADING/providerRUNNING，无停机/重发，provider_attempts仅restart=1。模型加载与生成结果尚未验收；未再启动补测、未提交生成。本轮没有改代码或切换镜像。证据继续复用服务器原账本auth-timeout-76913b1/下signal15-backend-observation.jsonl、signal15-frontend-evidence.json、signal15-after-sample-local.jsonl、旧会话停机证明；原失败采样证据保留。用户工作区其他文件持续改动，未纳入提交。

> 2026-10-18 22:02 CST GPU已停机、超时改动已部署，新启动被项目API预检截断：用户明确选择“现在停机更新，并新启动一次”。以候选镜像的一次性控制器提交唯一停机请求，旧会话 `56b8863528af4178864fd6c2d56ae536` 保持restart=1/stop=1；未提交新生成。旧守护2秒查询持续超时，候选5秒查询进一步返回gRPC Unavailable/exitCode20；仅增大认证等待不能视作彻底解决。一次候选poll遇SESSION_CHANGED，其失败证据保留，未当作释放证明。随后停机专用资源查询在原resource/project/公钥匹配下，真实DevLab STOPPED且省略空instances；经项目级compute空实例列表及相同spec的STOPPED复核，独立确认空实例；已用原子change写入OPERATOR_STOP_ONLY_RESOURCE_PROOF，verifiedStopped=true/instancesEmpty=true/sleepHeld=false，未借此绕过新启动所需IAM项目归属检查。原核验目标两分钟已超过后，仍只做停机核实，未延长工作或启动窗口。确认释放后才切换网页/守护为 `lighttry-cpu:auth-timeout-76913b1-web`、`lighttry-cpu:auth-timeout-76913b1-guard`；旧容器保留后缀 `-rollback-auth-76913b1`，配置/挂载保持相同，helper与冻结包未改。切换约11.43秒，公网HTTPS登录200，CPU守护常驻且凭据新鲜，guardExited=false。完整新版本预检仍在project_get返回Unavailable，守护idle观测为null；未签发新scope、未发送新start，不能声称GPU重新启动或候选修复已实机解决卡片跳动。用户授权的单次新启动仍受成功完整预检约束，禁止因资源API可用而跳过IAM检查。原账本 `bootstrap-recovery-63384bc/auth-timeout-76913b1/` 保留single-stop-receipt、失败poll、stop-only-devlab-proof、完整预检失败、cutover及停机后本地观察。当前阻塞为Nebius项目服务恢复，不要求用户再次提供凭据或重复点启动；最终账单金额未知。

> 2026-10-18 GPU卡片READY/UNKNOWN间歇跳动诊断（候选镜像已准备，未上线）：同一会话 `56b8863528af4178864fd6c2d56ae536` 出现连续provider project_get失败，exitCode=12、stderrSummary=timeout、每次约2.08秒；会话为OBSERVATION_UNCERTAIN，并非模型退出证明。阿里云公网HTTPS登录200，本机访问200约0.57秒；21:51:54 CST固定证书pin认证worker健康GET约1.07秒，session/resource/host均匹配、modelState=ready/modelLoaded=true。守护后续本地快照继续在READY/UNKNOWN切换，无stopSent，不能把旧模型快照当新鲜云运行证明。命令认证上限为2秒，是与失败时长吻合的候选瓶颈，尚未独立证明所有超时均发生于认证。提交 `76913b1` 仅将auth-timeout改为5秒，保留进程6秒/每次调用原deadline及重试/状态拒绝规则；18项离线回归通过。服务器候选镜像 `lighttry-cpu:auth-timeout-76913b1-web`、`lighttry-cpu:auth-timeout-76913b1-guard` 已构建并离线验证，helper/冻结包均未改，当前运行容器未替换。升级guard前必须独立确认GPU已停，且不得自动再次启动；已向用户呈现候选变更，等待其选择是否停机更新并新开一次预算3美元会话，不继承旧scope或改原22:35:34截止。证据继续复用原账本 `bootstrap-recovery-63384bc/`，其中intermittent-provider-diagnostics.json、intermittent-worker-health.txt及auth-timeout-76913b1/保留诊断/构建/候选凭据。另有用户工作区recipe_language.py及其测试改动，未纳入本提交。

> 2026-10-18 21:46 CST GPU启动暂态恢复修复已上线（实机READY，未执行生成）：用户报告连续启动后被BOOTSTRAP_FAILED停机。最近两个失败会话 `85a52ce988d64f2db42bf0a56d886c54`、`f45310d7a9074def9983461683dd91c9` 的安装前失败均为 `TRANSIENT_STATE_TIMEOUT`；独立新鲜收据确认STOPPED、instances=[]、verifiedStopped=true、sleepHeld=false，CPU守护继续空闲。提交 `63384bc` 将同一安装线程读取本地守护状态的等待从15秒增至60秒，逐轮取原work/absolute/scope/deployment截止更早值，全部身份/pin/授权校验不变，既有远端命令不重发、不新增云轮询；新增仅计数和白名单状态的实例绑定诊断。64项离线定向测试通过。网页/守护分别切为 `lighttry-cpu:bootstrap-recovery-63384bc-web`、`lighttry-cpu:bootstrap-recovery-63384bc-guard`，两端实际引导预检通过，旧容器保留后缀 `-rollback-bootstrap-63384bc`；helper SHA `ff867dd0219fe2ff2c07e5d538fe938aa6bf069369c2f34a85f868e0f4211f41`，GPU源码包字节未改，SHA仍 `b1df101b6ef5f161cf66e4081c3ce1eaec51a345bab7a17cca46d0dfac24b8bf`。构建初次COPY权限不足与新包目录权限预检失败均保留，已在启动前修正并复核。按用户本轮明确要求经固定pin SSH调用现有控制器新scope/单次start路径（记录owner=operator-ssh:user-request-20261018），沿用现有3美元估算预算与4200秒scope，不复用关闭会话；没有改参数、重复启动或提交生成。新会话 `56b8863528af4178864fd6c2d56ae536` 于21:33:59创建，21:35:34首次可靠RUNNING，原工作/停机截止22:35:34 CST。实机新增诊断确认DevLab为RUNNING时仅1实例，其state短暂STARTING而computeState=RUNNING，产生activeCount=0；同一引导线程等待恢复后21:36:14完成部署，未触发停机、未重发安装。此前15秒窗口不足与本次可恢复暂态已证实，供应商为何短暂回退状态仍未知。加载期间只读固定pin GPU检查确认两个PID活着、各已读约8GB、显存28630/46068MiB。21:45左右两阶段完成9/9、各加载约566.6秒；21:46:32 CST通过固定证书pin认证worker健康GET，session/resource/host均匹配、modelState=ready/modelLoaded=true，守护状态READY/providerState=RUNNING、stopSent=false、restart尝试1、stop尝试0、dispatches=0、活动队列0，公网HTTPS登录200。监控期间记录在场心跳，未更改原work/stop截止；GPU继续按用户要求运行，页面刷新重新登录即可使用，无需再次启动。仅启动/安装/预载得到实机验证；未提交新图片推理、未验收生成结果或浏览器拖放。证据复用服务器原账本下 `bootstrap-recovery-63384bc/`，保留快照/构建日志/单次启动收据/状态流与实例状态诊断，最终认证健康及容器镜像身份见verified-ready.json。

> 2026-10-18 当前会话CPU派发修复已上线（GPU未重启、生成仍待验证）：会话 `76f03db61d2147dca42bf401bd74088a` 的首个任务 `f0f42c82122f442db424c03eaad59506` 已真实完成五次逆向通道推理，但depth JPEG值域0–2、标准差约0.099，被 `GBUFFER_CONSTANT` 拦截，未进入forward；两阶段进程仍活着且READY，未放宽质量阈值。用户换图后的任务 `9c482accc8934682947b2c1f73d21371` 于19:27:49 CST创建，在派发前查询发生TLS失败；本次没有TASK_ATTEMPT_LATCHED事件，GPU的任务账本/执行目录均无此ID，后续固定pin认证GET返回not_found。CPU却把uncertain回执当作成功排队，造成UNKNOWN与队列占用；未自动重发POST。提交 `2b00d17` 串行产品侧提交/查询、停止查询已闭合的历史任务、将uncertain派发回执明确视为失败；55项定向测试通过（跳过1项）。GPU私有TLS仅2个并发槽，产品请求并发是已确认的容量风险；本次握手失败的更底层原因仍未知，不声称已证明所有TLS异常根因。仅切换CPU网页为 `lighttry-cpu:transport-20261018-2b00d17`（镜像 `sha256:a9bca9de19e3b2a4b90a37d580e8c9165e07a31f97a6f7bb8a1156f20f1c8122`），只改https_executor.py，重启约5.81秒；GPU、模型、独立守护容器与冻结包均未重启/替换，原运行/工作截止保持20:09:59 CST。旧网页容器保留 `lighttry-cpu-rollback-transport-2b00d17`。停止网页写入后再次核对持久化“无POST尝试”记录与同一任务身份，将该未发出任务按闭合失败处理并记录dispatchNotSentProof，原不确定记录、任务快照与GPU账本诊断保留；不重新提交。实测认证worker健康GET身份匹配、modelState=ready/modelLoaded=true；守护会话READY/providerState=RUNNING，队列done=4、活动0，公网可信TLS登录200。证据继续复用服务器 `/srv/lighttry-backups/before-dispatch-diagnostics-20261018/photo-drop-856efd2/`。用户需刷新重新登录后确认新任务；改图后的真实生成尚未验收成功，不继承已失败任务的自动重试权限。

> 2026-10-18 常驻模型IPC截止时间舍入修复已部署（实机生成待新会话验收）：当前故障会话 `d6eca30435564702bc00e6317e5b2755` 的任务 `26a5d54dc2924b8b8f9beef1b26ac68d` 已经连接到真实GPU并完成两阶段模型预载，随后 inverse 进程拒绝请求并退出：真实授权截止 `1792323463.8967068` 经 ISO 微秒时间往返变为 `1792323463.896707`，向上增加 `2.384185791015625e-07` 秒，触发严格的 `RESIDENT_REQUEST_BINDING_INVALID`；请求ID/bootId均匹配。worker仍在线但两个模型进程最终均退出，旧forward state.json的ready不能作为活进程证明。代码提交 `cfb361d` 在生成runtime/receipt时间时仅向前截断最多1微秒，保留原数值截止及全部身份、授权和单次执行校验，不放宽容差。47项不重复定向回归通过；两张容器镜像均用真实失败数值离线重放通过。仅提交一次 `MODEL_PROCESS_FAILED` 停机；独立确认STOPPED、instances=[]、verifiedStopped=true、sleepHeld=false，CPU守护继续常驻。原失败日志/IPC请求/attempt与原任务快照留存；独立停止确认后为同一任务写入带会话/资源证明的失败事件，原task nonce保持，无结果、不重投，现队列done=2、活动0。网页镜像 `lighttry-cpu:resident-deadline-20261018-cfb361d`（`sha256:adcee9bc07d3bf0c2390d465531e67e01556d739db7b962ccd4951efec698e24`），守护镜像同标签加 `-guard`（`sha256:d66489b5fb0ef961225f4d837316d38e19f5a27f6cb161b06fe34c6dbf2b598b`）；仅更新gpu_model.py，原应用配置/凭据挂载与HDR保留。新GPU源码包只替换同一gpu_model.py并更新内容清单，SHA-256 `b1df101b6ef5f161cf66e4081c3ce1eaec51a345bab7a17cca46d0dfac24b8bf`，helper保持 `3a185466d1fa98c96ae7dd473dae11ddb1d6f52777b49c71d6aaa19b120dd5ad`。部署后两端实际本地引导预检及公网可信TLS登录200通过；旧容器保留为 `lighttry-cpu-rollback-deadline-cfb361d` 和 `lighttry-gpu-guard-rollback-deadline-cfb361d`。证据继续复用服务器 `/srv/lighttry-backups/before-dispatch-diagnostics-20261018/photo-drop-856efd2/`。没有复用旧会话再次加载/开机，也未重提交任务；修复后的真实模型推理尚未验收，需要用户另开新会话并明确确认新任务。

> 2026-10-18 启动预检哈希不一致已修复（未重试GPU启动）：用户新点击的会话 `b93706399872422aabf3c3ff5147c34a` 在 `bootstrap_preflight` 失败，`startSent=false`、无启动尝试事件。实际本地复核为 `FROZEN_BOOTSTRAP_CODE_CHANGED`：网页侧上次派发诊断更新了 `project/worker_link.py`，但守护和冻结清单仍为旧 helper；旧网页回滚镜像也同样不匹配，本次四个拖放文件不是该不一致的来源。通过原会话停机入口只提交一次停止，独立确认 STOPPED、instances=[]、verifiedStopped=true、sleepHeld=false；CPU守护继续常驻，guardExited=false。现守护镜像为 `lighttry-cpu:helper-alignment-20261018-856efd2-guard`（`sha256:d031021c084ab4333148aef73ad1890d8bb0b5f2175abc8c4021994fce447f94`），仅同步 worker_link；网页拖放镜像不变。新源码包仅在原已验证包中替换同一 worker_link 并更新内容清单，SHA-256 `01285e9f81536bb7d0da8e590af1b1feaae3e292a87a7cabbe1453f0073ac572`，两端 helper 均为 `3a185466d1fa98c96ae7dd473dae11ddb1d6f52777b49c71d6aaa19b120dd5ad`。52项离线回归通过（跳过1项），两端隔离预检及部署后实际本地引导预检通过；公网可信TLS登录页200。首次回环健康探针漏Host头触发自动回滚，修正探针后切换成功；失败日志、原包、原清单和旧网页/守护容器均保留，守护回滚名 `lighttry-gpu-guard-rollback-helper-856efd2`。证据继续复用服务器 `/srv/lighttry-backups/before-dispatch-diagnostics-20261018/photo-drop-856efd2/`。未重新启动GPU、未调用付费模型；新清单的付费实机部署未验证，旧会话/预算/主机信任不续用。网页重启后需重新登录，浏览器拖放验收仍待完成。

> 2026-10-18 拖放照片版本已切换线上（浏览器验收待登录）：阿里云网页 `lighttry-cpu` 使用 `lighttry-cpu:photo-drop-20261018-856efd2-online`（镜像 `sha256:fdcf47a228ce1b47bbd084f7e39bb73c3ebf9e91c4aa89442a88a3bf58a48d6e`）。部署镜像以原线上基线构建，仅替换提交 `856efd2` 的四个前端文件，其余应用文件及三张 HDR 逐字节一致；容器启动参数、环境与数据/凭据挂载保留。旧容器已停止并保留为 `lighttry-cpu-rollback-photo-drop-856efd2`，切换前 inspect 和 SQLite 备份留存；独立 GPU 守护 ID 未变。切换前后新鲜守护快照均 STOPPED、instances=[]，活动队列0；公网可信 TLS 登录页200、匿名API401通过。本地89项Node与21项Python回归通过，另复跑5项拖放行为测试通过；真实浏览器拖放仍等待用户在已打开页面完成登录，不视作已验收。未启动 GPU、未提交生成、未调用付费模型。证据复用服务器 `/srv/lighttry-backups/before-dispatch-diagnostics-20261018/photo-drop-856efd2/`，首次基于裸镜像ID构建失败的日志保留，失败未触碰运行容器。

> 2026-10-18 GPU 任务派发诊断与前端失败复位已部署（最新）：针对真实任务 `10f6148df0a04e0f8065f08034dd4fb2`，原收据仅能确认 `artifact_upload / WORKER_RESPONSE_UNCERTAIN`，会话 `dispatches=0`、无结果；旧异常已被封装，无法倒推出超时或具体网络原因。用户报告后按失败保护只提交一次停机，独立确认 STOPPED、instances=[]、sleepHeld=false，常驻 CPU 守护空闲。现 CPU 网页 `lighttry-cpu:dispatch-diagnostics-20261018`（镜像 `sha256:542e29c0a04394b867d721fed60b079dbc4f3bdbe98e888aec293c641fd10aed`）仅覆盖传输诊断、任务公开安全诊断与前端脚本；未来 worker 错误按超时、连接、TLS/证书、HTTP 状态、协议回执和阶段白名单记录，不保存原始异常、URL、令牌或响应正文，不自动重发上传/派发。工作台收到 failed 立即提示，failed+executionUncertain 仅继续查询原任务；独立停机确认后复位禁用态、保留失败与无结果提示，GPU 状态刷新不覆盖。旧失败任务公网 GET200 可见其原始泛化代码，已清除不确定标记；新分类的收费实机触发尚未验证。离线 Python 767 项（跳过3）、Node 84 项及基线/修改/回滚十文件字节核对通过。切换前后 GPU STOPPED、空实例、活动队列0；独立守护镜像未变，Nemotron 服务保留。旧网页容器与 root-only inspect 留作回滚；本轮未启动 GPU、未调用 GPU 模型，账单金额未知。证据复用 `.local/dispatch-recovery-20261018/transaction/`。
> 2026-10-18 Nemotron 阿里云网页已接入（最新）：用户提供仓库外本机密钥文件后，仅将凭据通过固定指纹 SSH 输入流装入阿里云 CPU 服务器私有文件 `/etc/lighttry/nemotron/api-key`（UID10001/0600），原文件未改，未输出 token；v2 角色策略同为私有文件。容器 UID10001 离线读取通过，Nebius Token Factory 模型列表只读 GET 200 且找到 `nvidia/Nemotron-3_5-Lightning`，未调用收费推理。用户要求等 GPU 停机后切换；独立守护/会话确认 STOPPED、实例空、sleepHeld=false，队列 active=0 后，才切换网页容器，独立守护 ID 未变。首次脚本因旧镜像预检值过期退出6，未触碰运行容器，错误留存；修正后切换成功。公网 AD/operator 与 CL/user 的 `/api/lighting` 均返回 enabled=true、unbounded=true、developmentTestMode=false；管理员无应用层次数/费用/频率限制，普通用户无总额但按稳定浏览器身份每60秒最多10条并受常规访问频率限制。两套 REAL_PROVIDER 账本分离且 calls=0。旧网页容器及 root-only inspect 留作回滚。**真实付费 Nemotron 推理输出尚未验证**；用户刷新页面后可自行发送第一条文字。助手未启动/停止 GPU，也未发送模型请求。四角色审计见 `.local/nemotron-deploy-20261018/transaction/`。
> 2026-10-18 15:52 CST 中英界面已部署（最新）：按用户确认，首访使用浏览器语言偏好（服务端 Accept-Language、前端 navigator.languages），不单独读取系统语言；非中/英文默认英文。页面手动中/英切换优先，`lighttry_lang` 一方浏览器 Cookie 长期保存，登录页、GPU 入口、工作台及常见服务端错误均按此显示；不自动翻译用户照片名、方案名或 AI 原文。本地实际浏览器逐屏检查中英切换、刷新保留、登录、调光台、监控、方案库、聊天与对话框；81 项 Node、765 项 Python（跳过3）通过。阿里云只切换网页为 `lighttry-cpu:i18n-20261018`（镜像 `sha256:26fa27013646e390e32c2664e9578e51459bcf9c7962aff341c28698df88e1bf`），旧网页容器及 inspect 保留回滚，独立守护未切换。公网匿名 en/zh 登录、AD 英文/CL 中文、英文错误404、三张环境图 PNG200 均通过；切换前后独立 GPU STOPPED、实例空、活动队列0。助手本轮未启动/停止 GPU、未调用收费模型。英语真实收费生成过程和罕见动态文案尚未实机覆盖，不能声称该部分验收。
> 2026-10-18 14:58 CST 第二次 GPU 实机复测安全收尾与网页修复（最新）：用户点击一次启动，会话 `6087fde1fd6247d18a7e7cc8094dff37` 经短暂 UNKNOWN→STARTING→RUNNING→部署→READY，用户随后点击停止。网页和独立 CPU 守护在 14:36:24、14:58:33 CST 连续核实 STOPPED、instances=[]、verifiedStopped=true、sleepHeld=false、活动队列0；守护容器继续常驻，这是 CPU-only 设计，`guardExited=false`，不得称守护已退出或异机保护。账单最终金额未知；未成功提交生成任务，助手未调用收费模型。环境库三张预览原因是网页容器缺官方 HDR，在线热补后 3 个接口 PNG/200，新未来镜像已包含素材。用户 JPEG 扩展名文件实际为 PNG 字节，原 422 无任务入队；旧浏览器却保留待确认 ID、阻止换图。已部署网页修复：明确 INVALID_IMAGE/422 清除待确认状态；旧请求可经显式按钮调用服务端原子 tombstone，已受理请求拒绝作废，绝不自动重试。只切换网页容器，旧网页留存回滚，独立守护未切换；AD/CL 公网与合成作废接口验收通过。GPU 页眉“启动请求已提交”曾覆盖 STOPPING，现仅在 STOPPED 且未请求停机时使用该标签；JS 已热更新且公网哈希核对，未重启容器，旧浏览器页面需刷新。
> 2026-10-18 14:31 CST 实机复测进行中（最新）：用户在网页只点击一次，新的 GPU 会话 `6087fde1fd6247d18a7e7cc8094dff37` 于 14:16:35 短暂 `UNKNOWN` 并触发网页“状态无法确认”，14:17:27 恢复 STARTING，14:18:09 观察 RUNNING，14:18:30 引导部署完成，14:28:01 达到 READY/canGenerate=true。尚未由助手调用收费模型或请求停机；本轮仍在 RUNNING，不能写安全收尾。守护最晚停机约 15:18:04 CST，非账单硬封顶。环境库三张预览曾因 CPU 容器缺少三个官方 HDR 返回422；三个素材哈希验证后热复制到运行中的网页容器，现均返回200 image/png，网页和独立守护未重启。已构建含素材的新镜像并把未来部署标签指向它，旧镜像保留回滚；当前运行容器镜像 ID 未改变。后续需优先跟踪用户使用与独立 STOPPED/空实例/守护退出/防休眠释放，不自动重启或延长窗口。
> 2026-10-18 GPU 引导本地修复已部署（新付费验收待授权）：针对首次 RUNNING 后的 `CURRENT_RUNNING_HOST_REQUIRED` 永久锁存，CPU `SSHBootstrap.check()` 现为各拒绝条件写固定私有 `precondition` 枚举；仅当同一会话/资源/主机/镜像/原截止均仍有效、状态因供应商观测暂态为 `UNKNOWN`（`OBSERVATION_UNCERTAIN`）或已确认 RUNNING 后短暂回到 `STARTING` 时，在**同一安装线程**最多等待15秒读取既有本地守护快照，不增加云轮询、不重发 prepare/upload/install、不延长原窗口。状态恢复后才执行尚未发出的唯一远端命令；其他不匹配或超时仍锁存失败。独立守护遇到该会话 `failed.json` 后一次性请求 `BOOTSTRAP_FAILED` 停机并持续核实，不把请求当作 STOPPED。离线定向54项、UTF-8 全量759项（跳过3项）、前端76项通过；第一次全量因 Windows 默认GBK产生53个解码错误退出1，已保留并以UTF-8重跑通过。新版冻结包 SHA-256 `3a26eb8d302577dc67b681dc8225ff4bf7b0fc9e0d5eec1c604c0418cd01e0ed`，helper SHA-256 `5c18df9ac105f06550f7bcc87d81c16ff114a65008ea764b845944f4f5f4f458`，不含凭据/权重，旧包仍保留。阿里云 `lighttry-cpu:gpu-bootstrap-fix-20261018` 已同时部署网页和守护；切换前后均确认独立 STOPPED、instances=[]，公网 AD/CL 登录及新包预检通过，旧容器、inspect 与旧清单备份可回滚。**本次修复尚未进行第二次 GPU 收费实机验收；旧失败会话与尝试闩锁不可复用，任何新启动必须新点击/新 scope。**
> 2026-10-18 首次用户启动实机失败与释放（最新，覆盖下方“未做收费 RUNNING 验收”）：用户在网页触发一次新 scope 与 GPU 启动，独立守护首次于北京时间 12:53:35 确认 RUNNING。本轮主机候选指纹捕获并由守护自动绑定，远程准备和上传返回成功；12:53:54 写入唯一安装尝试闩锁。12:53:59 CPU 引导器在发出远端安装 SSH 子进程前以 `ValueError('CURRENT_RUNNING_HOST_REQUIRED')` 拒绝本轮会话，网页显示 `SESSION_OR_BINDING_REJECTED`，未执行远端容器安装或模型 launch，不允许复用该闩锁重试。守护在失败后曾记录 `NEBIUS_CURRENT_VM_NOT_UNIQUE`，提示供应商实例列表可能短暂不一致，但它发生在安装失败后，不能倒填为直接根因；`check()` 的具体拒绝谓词未被旧版记录，仍未知。随后守护新鲜收据和会话状态均确认 `STOPPED`、`instances=[]`、`verifiedStopped=true`；常驻 CPU 守护继续空闲运行。会话 `stopSent=false` 且无网页停机闩锁事件，尽管用户点过“停止”，不能声称该请求导致资源停止，停机来源未知。禁止再次启动或续接本轮，先做离线失败谓词分类、暂态观测处理与引导失败只停机保护，任何新的付费实测都须用户重新明确点击。只读取证详见 `.local/nebius-sa-20261018/bootstrap-failure-20261018T051350Z/REPORT.md`；私钥、token 和签名密钥未输出。
> GPU 卡片停机倒计时（2026-10-18，已部署阿里云网页，未做收费 RUNNING 验收）：首次可靠 RUNNING 后服务端已有 `runningAt`、`stopDeadline` 与每次网页快照的 `serverNow`。网页页眉 GPU 卡片新增“最晚自动停机 HH:MM:SS”，以服务端时间锚定、本机每秒递减，不增加云 API 轮询；断连/快照过期显示“自动停机时间待核实”，到零仅显示“已到最晚停机时间 · 待核实”，STOPPING/STOPPED 不展示倒计时。断连、空闲及保护异常可能提前触发停机，所以这是最晚窗口提示，不是保证 GPU 在倒数完前持续可用或账单硬封顶。本地合成 RUNNING 测试验证 01:00:00→00:00:01→待核实及各状态隐藏；阿里云网页镜像 `lighttry-cpu:gpu-countdown-20261018` 已切换，公网 AD/CL 登录只读检查确认 `serverNow` 新鲜、HTML/JS/CSS 新版本、GPU STOPPED、未签发 scope；真实 RUNNING 后的 UI 视觉与供应商停机仍待用户后续明确启动时验收。本次未启动/重启/停止 GPU，未调用收费模型。
> 最新阿里云 GPU 接线（2026-10-18，覆盖下方“只读守护/网页未挂载”阶段）：用户报告当前 DevLab 价格 $1.75/小时；该数字不是独立核验的含税账单。为留余量，新的逐次点击策略按含税估算 $2.50/小时、单会话预算 $3.00、停机预留 120 秒计算，scope 最长 4200 秒，且不视作供应商硬封顶。阿里云 `lighttry-gpu-guard` 独立容器现使用服务账号与真实 DevLab 接口保持守护，已读到 STOPPED、instances=[] 的新鲜收据；原只读守护已停止留作回滚。网页 `lighttry-cpu` 已挂载同一活动控制配置和模型授权路径，受信任 HTTPS 下 AD、CL 分别登录后对 `/api/gpu/entry-status` 只读验收均显示 configured=true、canStart=true、STOPPED、verifiedStopped=true、cpu-only、自动本轮主机绑定；初始 scope 仍 budgetApproved=false、expiresAt=0，未产生新会话授权或 GPU 开机。只有浏览器用户后续明确点击才签发新 scope 并尝试一次启动；本轮未调用收费模型。实际 DevLab restart/stop 权限、GPU SSH 安装及模型生成尚未用付费实机验证，失败必须保留原收据并执行原停机保护；阿里云整机失联仍无异机停机保证。
> 最新权限与 GPU 接线状态（2026-10-18）：用户已把 `lighttry-controller` 移出租户 `admins`，只保留自定义组 `lighttry-devlab-operators`；控制台核对该组唯一许可是 `project-e00cydn2pr00f38xvq3j95` 上的 `editor`。服务账号重新获取 token 并调用实际 `nebius.ai.v1.DevlabService/Get` 成功，资源 STOPPED、实例列表空；列出 IAM 许可返回 403，未自动加权。经用户许可，现有 DevLab SSH 私钥由本机使用阿里云服务器的 RSA 公钥封装为 RSA-OAEP-SHA256+A256GCM 密文，密文通过云助手传至服务器后仅在服务器内解密，公钥匹配且安装为 `/etc/lighttry/gpu/keys/id_ed25519_devlab` root/600，密文已删除；私钥内容没有进入聊天、仓库或命令输出。GPU 控制配置、当前 scope、worker CA/token 和独立守护单元在服务器上仍不存在，因此**尚未接通或启用生产 GPU 控制**，没有 GPU 电源动作。SSH 22 端口此前握手阶段间歇性关闭/超时（退出255），配置有效、sshd active、端口监听；获准重启一次后首次仍失败，随后两次严格 pin 公钥认证成功，根因未知，不能宣称重启修复；未开放 2222。

> Nebius 服务账号认证历史验收（2026-10-18）：`lighttry-controller`（`serviceaccount-e00ybpfwg84xtz6dd6`）的 `publickey-e00gdw8z6bkh7b5agw` 已注册且 ACTIVE/4096；服务端独立 root/600 配置 `/etc/lighttry/nebius/service-account.json` 只引用 root/600 私钥，不读取个人 OAuth 配置或静态 IAM token。官方 Python SDK 0.6.24 以该身份取得约12小时 token，`Profile/Get`、实际 `nebius.ai.v1.DevlabService/Get`、项目 `Get`、公钥 `Get` 均成功；DevLab `devlab-e00mt1pp6rph9z4qyv` 属项目 `project-e00cydn2pr00f38xvq3j95`，查询时 STOPPED、实例列表空。公钥元数据无非零 `expires_at`，不代表不可吊销。全新进程重取 token、SDK 强制刷新及合成过期/认证失败测试通过，**自动续签实现已检查／模拟通过，真实跨期续签尚未验证**。网页实际容器 UID10001 在只读密钥/配置挂载下执行同一只读探针成功；独立守护等价容器经用户、镜像、环境、数据卷、挂载核对一致后探针成功，但真正的停机守护及 GPU 控制尚未配置/运行，不能称生产控制链路已接通。旧容器和原 `docker inspect` 已保留用于回滚；未启动/重启/停止 GPU，未调用收费模型。

> Nebius 持续化公钥准备（2026-10-18，已由上项认证验证推进）：已在阿里云 CPU 服务器本机生成专用 RSA 4096 密钥对，`/etc/lighttry/nebius/private.pem` 仅 root/600 可读，父目录 root/700；`public.pem` 经 OpenSSL 公私钥匹配与 4096 位检查，SHA-256 为 `33c2f0be46e801e02523978197916204056042fafdbfee730faf18cf00698524`，公钥副本交付到 `C:\Users\WJX\Desktop\public.pem`。私钥未传出服务器；用于容器只读挂载的专用副本仍留在该服务器，权限为 root:10001/640。

> CPU 公网 HTTPS 已验收（2026-10-18）：受信任 IP 证书、443 Nginx 和应用 HTTPS Origin 已启用；外部登录200/TLS校验通过，匿名API401、HTTP登录404；AD/CL 与浏览器隔离经公网实测。生产短期证书至 2026-10-24 16:29:22 UTC，两次每日的 systemd 续期 timer 已启用，Certbot 干跑及部署重载钩子、服务单元均通过。SSH 曾于密钥交换断开，现严格 pin 连接成功但偶发重置，不能称稳定修复；守护/GPU 与付费 Nemotron 仍关闭。

> CPU 证书告警（2026-10-18）：QQ SMTP 授权码由用户以仓库外文件提供，服务端仅 root 可读的 `/etc/lighttry/secrets/qq-smtp-auth.txt` 与 `/etc/lighttry/cert-alert.json` 权限均为600；脚本 `/usr/local/libexec/lighttry-cert-alert.py`、`lighttry-cert-alert.service` 与 `.timer` 已安装。定时器每日北京时间 04:15、16:15 检查本机可信 IP TLS 证书、72小时临期和上次 Certbot 服务结果；失败状态最多每24小时发送一次告警，恢复后重新武装。离线4项测试通过，真实 SMTP 测试返回 `TEST_EMAIL_SENT` 且用户确认收件；健康服务返回 `HEALTHY`，timer enabled+active，HTTPS 登录200。临时上传目录已清理；仅 SMTP 测试投递和正常状态已实测，真实续期故障触发邮件尚未实测。授权码不得进入源码、日志、聊天或归档；吊销须在 QQ 邮箱端操作并替换服务端密钥。Let’s Encrypt 不再发送到期邮件，不以证书账户邮箱代替此告警。

> CPU HTTPS 历史中断点（同日已通过云助手完成发布，SSH 故障仍待查）：外部 HTTP-01 路径通过，生产 IP 证书已签发；服务仍仅绑定 127.0.0.1:8080，HTTP 登录 404、443 无监听。SSH 密钥交换阶段主动断开，连续复测退出255，故没有做 443 切换或自动续期配置。恢复严格 pin SSH 后继续已预检的 Nginx/容器切换；外部可信证书和续期演练成功前不得称公网可用。

> CPU 内网部署状态（2026-10-18）：最新源码镜像已在目标 CPU 机运行，仅 `127.0.0.1:8080`，已保留原数据冷备份和旧容器；远端 AD/CL 登录、浏览器身份隔离及服务重启恢复已实测。公网 80/443 尚未开放，HTTPS、Nemotron Key、GPU 守护的当前云凭据/授权均未配置；不得将内网服务状态当成公开可用或付费能力已验收。

> 最新本地权限取舍（2026-10-18）：普通用户 Nemotron 不设美元预算或总次数上限，仅每浏览器身份滚动60秒最多10条且保留普通访问限流；管理员也无应用层次数/费用上限。私有 AD 与共享 CL 密钥已准备并绑定本地配置，CL 内容及停机任务归属按持久浏览器身份隔离，同浏览器重登录可恢复。GPU 费用由运营方承担，但每次启动仍须原有安全门槛；当前主机无 Nemotron 服务端凭据，文字策略文件已准备但未绑定本地启动入口；未部署公网、未开机、未发起收费文字调用。仅分享地址不是防火墙白名单。此条覆盖下方“未签发新密钥”历史说明。

> 主机信任产品取舍（2026-10-17，本地实现）：用户明确要求去掉面向浏览器用户的逐轮 SSH/TLS 指纹确认，并由运营方承担首次连接身份风险。只有私有 `autoHostTrust.enabled=true` 且 `operatorAcceptsFirstContactMitmRisk=true` 时，独立守护在本轮供应商 API 确认 RUNNING/VM/IP 后，取得本轮候选指纹、重新核对会话/主机/窗口、自动写入本轮 pin 并记录 `guard-tofu`，然后才允许原有单次部署。网页不提供该确认操作；失败则截断部署并请求停机，不继承旧指纹、不禁用 SSH 严格主机校验。首次 `ssh-keyscan` 本身不能证明真伪，存在首次连接中间人风险；这是明确接受的产品取舍，不是安全等价替代。本轮仅离线和本机验证，未启动 GPU 实机验收。

> 权限组准备（2026-10-18，本地代码）：受保护账号文件的 operator 为管理员、user 为普通用户，不在本轮签发新密钥。两组启动 GPU 均受当前 scope、预算、独立 STOPPED/空实例预检、守护及单次启动闩锁约束；管理员可在任务运行或排队时请求停止，普通用户只有在全部运行/不确定/排队任务均属自己时可停，其他账号或归属不明即拒绝并在网页弹窗提示。管理员登录后免应用层访问限流，Nemotron 无限额仅由显式私有 v2 配置与独立新账本启用，仍记录用量；普通用户 Nemotron 滚动60秒最多10条并保留正常访问限流。登录防暴力破解保护不取消。此为本地代码/离线验证，不是新增云启动或收费授权。

> 引导错误分类（2026-10-17）：用户要求先停机后补分类，已独立确认STOPPED+instances=[]后执行本地修改。新增固定错误码与阶段、异常类型、有限退出码/耗时；覆盖SSH命令超时、认证/主机指纹/网络、远端helper或非零退出、JSON回执/本地JSON、文本编码、文件/权限、端口及本地程序错误。原始命令、stdout/stderr、异常文本、密钥和授权内容不写入新诊断。网页显示阶段、原因、错误码与计费/停止提示，监控详情保留最近引导错误；旧BOOTSTRAP_UNCERTAIN不补猜原因。保留失败锁存，超时/丢回执不重试、不续窗、不自动启动。冻结新源码包并重载Web与空闲守护，不做GPU开机验收。

> 后台连接修复（2026-10-17）：工作台新增带同源认证的持续HTTP在线连接；服务器每10秒确认连接仍有效并续在线状态，不依赖后台页面定时器。关闭/断开最后一条连接后从后端观察到断连起算300秒宽限；其他标签页仍连接则不触发。恢复可见、focus、online、pageshow立即补报，陈旧连接重建，pagehide关闭；POST补报保留但不再是后台在线唯一来源。Waitress启用lookahead=1、16线程、最多8条在线流，预留普通请求/停机容量。失联、5分钟空闲、一小时窗口、CPU心跳丢失、授权截止、用户停机分别显示；旧DEADLINE_OR_CPU_LEASE记录只能标旧版未细分，不能补造原因。连接续期不能复活已过期会话或延长原工作/预算截止。验证仅替身时钟和真实本机HTTP连接，无GPU开机；浏览器真正丢弃页面、断网或电脑休眠造成真实断连仍按宽限保护停机，不承诺在物理断网时保持在线。

> 最新用户选择（2026-10-17）：停止推进云端预装，恢复原SSH首次连接方式与网页GPU启动入口。firstConnect不启用；当前源码冻结包预检通过后已重载Web与空闲守护，实测canStart=true、STOPPED且instances=[]。只有用户在网页明确点击才签发新scope并启动；不自动开机、不重试旧请求。保留网页常驻故障提示、计费风险、停止/释放提示及10秒状态请求超时。此前“云端预装前禁止恢复入口”已由本次明确用户要求覆盖，不声称独立首次连接已云部署。

> 首次连接修复（2026-10-17）：本轮用户要求先停机后修复，已从守护确认STOPPED、instances=[]。新增镜像启动mTLS引导入口（8443）和CPU firstConnect接线；有效证书/当前API VM身份/人工TLS指纹确认/当次grant后才允许固定安装，443 mTLS承接worker，无SSH网络依赖。身份GET不可达时仅允许一次SSH指纹捕获；证书/身份错误不降级；安装POST丢回执不切SSH、不重复安装。13项离线与4项真实本机mTLS测试通过，不是云端验收。尚未预装云镜像、证书和CPU来源CIDR的L4入口；现有CLI无devlab update、restart不能修改启动配置，未擅自创建/删除替代资源。GPU网页控制暂时摘除（文字网页保持可用），守护空闲；禁止在云端预装完成前恢复启动按钮。

> 最新用量规则（2026-10-17，本地实现）：新会话首次独立确认 RUNNING 后工作/停机上限为3600秒，停机核验预留120秒；启动等待仍为1800秒，总绝对保护5520秒，均受当次有效授权/预算更早截止约束，不续期历史会话。工作台通过认证POST每15秒报告在线，服务端连续300秒未收到任何工作台心跳即停机，包括模型加载或执行中；CPU守护心跳、任务活动、GET查询不视为客户端在线。后台标签页仍发送心跳，但浏览器挂起/断网可能被视为离线。未进行真实云验收或新增收费授权。

> 最新澄清（2026-10-16）：等待与RUNNING后计时独立。新会话最多等1800秒；首次可靠RUNNING后分别绑定工作1080秒、停机1500秒、核验1620秒。取消旧40分钟总上限对新会话的截断；新会话绝对保护为创建后3420秒（30+27分钟），scope上限3600秒用于预检/守护准备余量，仍受3美元预算与既有CPU租约保护。只改变尚未提交的新会话；历史会话/原始证据不续期。本条覆盖下述旧40分钟说明及前一次“仍40分钟”的误解。

> 当前覆盖规则（2026-10-16，用户最新明确要求）：新会话启动等待上限为1800秒（30分钟），取scope到期更早者。下文600秒为此前策略，不适用于新会话；历史会话不改、不续期。总绝对窗口仍不超过初始40分钟，预算和RUNNING后的工作/停机保护不变，晚启动会截短剩余工作时间。

# 云执行快速衔接规范（2026-10-13）

本规范是当前云执行的首要流程入口，优先于 RUNBOOK 中历史一小时/四素材说明。适用于已准备好的五项包；不更改实验范围、预算、启动等待或安全保护。它是执行者必须遵守的调度规范，不代表下面所有衔接已经由程序自动实现。

## 0. 先分清状态

一条当前状态记录必须分别保存：准备、认证、守护、启动请求、可靠 RUNNING、当前主机确认、上传、模型 launch、已取回结果、视觉判定、工作台导入、停机四项核验。只有完成的步骤标完成；计划、请求接受、历史证据和离线替身不能代替实测。

当前记录入口：`C:\Project\Nebius\.local\calibration-20261013\checkpoint.json`。每次只读它指向的最新状态，复用已确认的包、哈希、输入、脚本与完成项，不重新搜索整个项目。旧流水与失败记录保留，当前摘要可以更新且必须与证据一致。

## 1. 所有非付费准备移到授权之前

在等待授权时完成：代码修复、受影响测试、新包冻结/解包/worker 核查、上传清单、许可范围、预算估算、CLI 的准确路径与已验证认证入口、守护启动方法、停止/释放核验方法和旧 run 的只读检查程序。

明确冻结 taskId、包 SHA 与五项顺序；输入/inverse/配方等已确认字段只复用。不能在授权后才跑无关回归、写报告、研究 CLI 命令或重建相同包。若授权后的确发现必要修复，说明阻塞原因，先完成修复且记录新包 SHA，再启动；不得上传旧包或偷换授权范围。

文字与 GPU 独立。文字需要人确认时不启动 GPU 等待回复；单纯“再次授权启动”不自动授权文字超时重试。

## 2. 授权 → 认证：失败即转登录，不绕圈

收到授权后先绑定新范围、预算、窗口、当前包和一次启动限制。第一条真实检查只验证当前 CLI 认证/项目归属/STOPPED/公钥与资源范围。不能把预检失败放进不检查退出码的复合命令，继续创建守护或启动 VM。

若现有 CLI 返回认证错误：立即使用已验证的**现有 profile 更新入口**拉起登录，只确认现有 endpoint/tenant/project，不安装 CLI、不新建或切换项目。不要反复查帮助、猜 `iam login` 或依赖 PATH。当前已验证入口：

```powershell
wsl.exe -d Ubuntu-26.04 -- /home/wjx/.nebius/bin/nebius profile update wjx --no-check-update --auth-timeout 5m
```

只在本轮已获授权/沿用明确的 CLI 登录授权时执行；用户在浏览器完成认证，不在聊天粘贴验证码、回调或 Token。认证密钥不打印、不上传。登录参数/profile 变动或 CLI 入口确实失效时才查当前帮助并说明阻塞，不盲目重试。

**执行者响应目标（不是网络性能保证）**：工具返回认证错误后，30 秒内启动已知登录入口或报告具体阻塞；用户说认证完成后，30 秒内恢复 CLI 收尾/必要预检。不能让用户再次提醒才推进。

## 3. 认证完成 → 单次启动：连续短链

按顺序连续完成：

`浏览器回调/CLI exit0 → 保留原 tenant/project → 必要真实预检成功 → 守护 ready → 单次 restart`

这条链中不夹杂文档整理、无关测试、价格闲聊或重复读取已有资产。项目/公钥/资源身份检查不能省；不得把浏览器成功当成 API 认证成功。只重新验证会因登录/资源变化失效的字段。

守护启动脚本在同一个 PowerShell 进程内调用，避免用嵌套 `powershell.exe` 捕获后台守护后代的 stdout，阻塞在 EOF。实际 RunDirectory/PID 必须及时持久化，必要时读取收据确认已启动，不凭命令是否返回推断。未确认某个调用的结果时不得重发。

认证未通过不得创建守护。守护未 ready、已停止锁存、心跳过期或防休眠未就绪，不得 restart。若预启动守护需要替换，先核实旧守护停止/防休眠释放、确认从未发出 restart，替换仍绑定**原绝对截止**；不借替换续时。不得绕过 restart-attempt 独占标记。

**响应目标**：必要预检与守护 ready 均已返回后，15 秒内提交一次启动，或明确报告挡住提交的保护条件。网络、CLI、资源等待另行计时，不能承诺在固定秒数内实际开机。

## 4. 启动等待与付费工作

startup 请求时间独立记录，等待上限600秒；首次可靠独立 API RUNNING 才绑定工作18/停机25/核验27分钟。绝对保护不晚于初始守护窗口40分钟，所有时限取较早者，写明北京时间与 UTC，不延期、不再次启动。

守护拥有状态 API 心跳。执行者以本地心跳/收据获知状态，不额外开重复 API/SSH轮询；不因等待而重新启动。阶段变化立即报告，PROVISIONING/IMAGE_PULLING不能称为运行成功。接近600秒时主动提醒，到限执行保护，不把决定推给用户。

可靠 RUNNING 后核对本轮 VM/IP，守护按上方显式运维许可捕获并自动绑定本轮 SSH 指纹；不要求浏览器用户确认。原指纹不继承，后续 SSH 必须严格匹配本轮 pin。绑定成功后才执行预先准备的只读旧 run 检查；旧完成项/进程不明时保留证据并停，不盲重 launch。没有私有风险许可时不自动绑定。

无旧完成项或按已批准恢复路径衔接后，上传精确新包、核对 SHA/实际 worker、先写 launch-attempt 再仅 launch 一次。使用单一有界状态流；观察失败、身份/哈希错误或远端进程不明即停止，不用重连掩盖不确定性。

只做范围明确、能快速处理且不会重复 launch 的小修复，并受剩余固定窗口约束。完成即触发提前停机，不能为了写报告、等文字或做前端展示保持 GPU 开着。

## 5. STOPPED → 四项释放：最高收尾优先级

看到 STOPPED 后不再讨论方案、不写报告、不补跑测试。立即连续执行：

1. 独立 API 核实 STOPPED **且 instances=[]**；不能用 stop 请求成功替代。
2. 保留独立释放收据，通知正在等待该收据的守护。
3. 核实该守护 PID 已退出，最终心跳 stopped_verified=true、sleep_held=false。
4. 若三者尚未齐，状态保持 stop-unverified，保持独立监督；在原核验/绝对边界内继续必要核验，不因报告而中断。

**响应目标**：获得 STOPPED 状态后，15 秒内开始独立释放核验；四项证据齐全后，15 秒内告诉用户“已安全收尾”。进程退出/网络/API等待不包含在执行者人为延迟目标中；等待时必须说明缺哪一项。

`awaiting_independent_stopped` 心跳可能在等释放收据时变旧：不能因为原观察等待器报心跳过期就停止独立停机监督。保留错误记录，独立确认释放，不重新启动观察器、VM 或模型。

如果到核验/绝对边界仍未释放，立即报告保护异常，继续**只停机的独立监督**；不能宣布安全、放弃监督、继续推理或把这段等待称为工作窗口延期。时间/预算保护不是供应商账单硬封顶。

首次独立停止检查未通过可能只是 STOPPING 过渡，不等于最终停机失败，也不允许宣布完成。确认最终四项后新增证明并更新当前摘要，保留此前 stop-unverified 证据。

## 6. 先报安全状态，再整理

安全收尾消息必须包含：执行成败、已确认的启动/launch/结果计数、是否有新结果、四项释放结论、未验证部分。不知道的计数写未知，不能写0。

随后才做本地摘要、对照页、视觉审阅、导入/幂等核查、费用估算、补丁/回滚与文件打包。别在第一条安全消息前罗列角色文件和长文档。如果导入需要刷新用户浏览器，明确“后端就绪/前端待刷新”，不冒充同步完成。

已有四角色与原始记录只重新打开和核对，补充记录扩展它们，不反复跑已完成的原事务。费用把启动等待、推理、停机过渡分别列明；未知账单/超时请求保留预留，不称免费。

## 7. 可见进度与异常

- 每个实质状态转换立即更新当前状态；进行下一步前先落最小收据，不先写长报告。
- 工具已经返回、下一步可执行时，连续推进；不用额外 sleep 或频繁查相同状态。
- 超过30秒没有新结果，说明正在等哪个进程/网络/资源及截止；较长启动等待至少每60秒报告一次阶段、已等待时间与剩余上限，不能把它实现为新云轮询。
- 必须停下时立即说明：具体阻塞、已尝试的真实动作、费用/进程是否确定、守护是否保持、需要用户补什么。用户只需做认证与明确参数应用等必要决策；主机首次信任由私有运维许可和守护承担，不交给浏览器用户。
- STOPPED 后不要让“整理证据”变成无解释沉默；先发四项核验状态，再完成报告。

## 8. 下一次执行验收

新增阶段时间戳：authorization_received、auth_check_start/end、login_opened、user_auth_done、CLI_auth_verified、guard_ready、restart_submitted、RUNNING_confirmed、host_confirmed、worker_launch、stop_requested、STOPPED_observed、independent_empty_verified、guard_exit_verified、sleep_release_verified、safe_status_reported、report_completed。

分别统计执行者衔接间隔、工具/网络耗时和用户等待，不把整段延迟统称“云端慢”。记录时间戳只用可靠时间；不能补造过去时间。30/15秒目标未达到时记录原因并修正，不通过延长工作窗口补偿。

### 当前实现边界

已存在的代码保护：单次 restart/launch标记、API归属/主机 pin、600秒启动与RUNNING锚定、时间/费用授权检查、提前停机、独立停止收据、防休眠释放、新wire六位精度、有界白名单stderr记录。

尚非全自动：交互认证后的衔接、阶段延迟指标、最终核验后的即时用户消息、跨阶段统一控制器。以上流程要求现在由执行者遵守；若将来写控制器，另做离线状态机/中断/超时/重复启动回归，不把本文或模拟测试当成自动化上线/实机通过。

现有守护收据中的 verification_target_utc 可能直接记录 RUNNING+27，而非已裁剪的绝对边界；执行者必须另计算 `min(核验目标, 原绝对截止)`。本文没有修改守护实现，也不声称已修复该元数据裁剪问题。


## CPU 服务接口离线实现补充（2026-10-14）

CPU服务新接口选用受认证HTTPS worker；会话/任务副作用在SQLite持久化，GET仅查快照，应用重启不续窗口。同一新范围只有一次start，任务ACK丢失先查原jobId，不盲目重POST。独立Linux守护入口为根start.py --guard；STOPPING正常等待有界，到限UNKNOWN后仅停机核实，不续工作。当前七状态、接口、异机deadman参考模型及本机独立进程检查是离线模拟，不代表Nebius/GPU真实验收；真实适配器、CPU心跳、守护与GPU HTTPS链路尚未部署；本地接线与同机守护实现不代表真实云验收。

当前采用用户于2026-10-16明确选择的CPU主机统一管理方案：Web与守护是同一CPU主机上的独立进程，不要求第三台主机。服务端私有配置必须显式标记 protection.mode=cpu-only、cpuHostRiskAccepted=true，守护存活/资源绑定凭据有效且独立API预检确认STOPPED+空实例后才允许单次启动；缺少同机守护ready即截断。该策略不是异机兜底：CPU整机宕机、断电或无法访问云API可能导致GPU继续计费，不能保证费用硬封顶。不允许伪造 independentHost=true，旧off-host模式仍拒绝同机收据。原600秒、首次可靠独立RUNNING起算18/25/27分钟、初始40分钟及当前主机确认和四项释放保持不变。细节见现有README的CPU→GPU章节，不新增平行执行规范或继承已关闭范围。


## CPU同机管理准备（2026-10-16）

本轮只做代码、配置模板与离线验证，不连接真实CPU/GPU、不启动GPU、不生成可用的新收费授权。Web服务和常驻guard都从根start.py启动，共用私有gpu-control.json及sessions.sqlite3。guard持有OS进程锁并每5秒发布有界存活凭据；初始空会话只由guard读供应商预检，页面只读本地快照。CPU Web后台每5秒续当前会话心跳，心跳停止30秒后由同机guard请求停机。已核实停止后guard留在空闲状态，不自动开启新会话；守护/服务重启不重置截止、不重复start/launch。过期或撤销的scope仍可供stop-only观察器恢复已有会话，但Web不能据此获准启动。

guard正常退出时只提交一次当前会话stop请求，不把提交当作STOPPED；单次网络调用必须有界。生产运维应在停guard/升级前确认GPU已停，不能用systemd服务退出代替资源释放核验。当前CPU常驻guard不必在每次GPU停止后退出，因此报告“GPU已停、实例已释放、guard仍在空闲监控”，不得伪报guard已退出。历史实验的四项停机证据和旧授权保持只读；需要结束整个实验守护时仍按原四项流程记录。CPU整机失效时没有独立控制平面接管；人工从云控制台停机是应急手段，不属于已实现的自动保证。


## 真实对接代码的启用边界（2026-10-16）

新增nebius_provider、HTTPSCosmosExecutor、CosmosWorkerExecutor与TLS/worker模板，但当前只完成本地代码和离线/loopback TLS验证，不代表云端部署。默认不注册模型，不执行CLI；模板enabled=false、零模型预算、hostConfirmed=false且expiresAt=0。CPU侧显式配置模型grant后仍需当前scope/READY/本轮守护自动主机绑定/精确owner与fingerprint/原图及recipeKey批准。GPU入队检查独立私有grant，保存dispatching后只执行一次现有参数化worker，不接受远端脚本或命令。

执行前必须补齐本轮真实资源与安装CLI版本、CPU来源CIDR、GPU当前CA/证书pin、独立worker token、会话/resource绑定和精确模型grant。新会话不继承旧worker.env或证书信任，现有启动/主机确认/固定窗口/停机核验流程不变。本轮不得据此启动GPU或加载模型；后续真实执行仍需新的明确授权。源码实现、替身通过、本地TLS通过、远端部署、真实模型结果和视觉验收必须分别记录。


### 2026-10-16：网页启动链衔接（尚未实机验收）
已实现守护收到 RUNNING 后捕获当前 SSH 指纹；显式私有风险许可下自动绑定本轮 pin，再单次上传冻结源码包、严格主机校验 SSH 隧道、私网 HTTPS worker 与常驻模型启动衔接。健康查询不加载模型；只有当前会话隧道及两阶段模型实际 ready 才允许生成。慢云查询与 CPU 心跳并发已用独立 liveness 表修复，原截止时间不延长。
验证仅包含离线替身、并发回归与真实本机 TLS；未启动 GPU、未远程部署、未加载实际模型，Docker 镜像未构建。3 美元含税仅为未来每会话预算偏好，不是启动授权或供应商硬封顶。当前私有控制和模型授权仍未启用；尚需补齐每次点击的新 scope 与动态逐任务授权，再做经授权的真实端到端验收。CPU 整机故障下无独立停机保证，不能声称已有独立守护。


#### 当前会话模型授权衔接（2026-10-16，本地代码验证）
可选私有 `modelPolicyFile` 明确模型许可与任务上限，并与 `scopePolicyFile`、SSH bootstrap 同时配置后，CPU 守护在本轮主机绑定通过后创建本次 v2 模型授权。每会话独立随机签名密钥与原截止时间不可续期；保存原始授权，重启复用，不把历史主机信任或预算带到新会话。新照片任务通过签名传到 GPU 校验，无需修改常驻模型的启动授权。缺许可、当前点击、主机确认或新鲜状态时拒绝；删除/撤销本次已发布授权不会自动补发。仍未实际开机、部署或加载模型，私有运行配置未启用。

## 2026-10-18：阿里云独立守护只读上线（未开放 GPU 启动）

在现有已固定 ED25519 指纹的 SSH 22 通道间歇可用期间，已用服务账号 `lighttry-controller` 的官方 CLI 对 `devlab-e00mt1pp6rph9z4qyv` 执行真实 DevLab 只读查询，核对为 STOPPED、实例列表为空；同运行身份下冻结 GPU worker 包、SSH 引导和 TLS pin 预检通过。没有启动、重启或停止 GPU，也没有调用收费模型。

阿里云 CPU 上独立容器 `lighttry-gpu-guard-readonly` 已运行，持有同机守护锁并每轮写新鲜收据；其控制配置 `enabled=false`，初始 scope `budgetApproved=false`、`expiresAt=0`，不签发网页启动授权。网页容器已切为 host 网络和 host PID 命名空间，仅监听 127.0.0.1:8080；与守护共用 loopback 是未来 SSH 隧道必要条件。两个容器 UID 10001、去除 Linux capabilities、禁止提权；公网仍只经 Nginx HTTPS，实测 `/login` 200、匿名 `/api/health` 401。网页目前**未挂载 GPU 控制配置**，不应称 GPU 控制可用。原网页容器保存在 `lighttry-cpu-before-gpu-hostnet-20261018`，Docker inspect 备份在 `/srv/lighttry-backups/before-gpu-hostnet-20261018/docker-inspect.json`。

首次切换检查误用本机 Host 头，应用按域名校验返回 403，切换脚本 exit 11 并自动回滚；改为正式 Host 头后重试一次，切换 exit 0、HTTPS 证书验证通过。该 403 不是 SSH 或认证故障。当前 SSH 22 无新故障；不开放 2222，也不再重启 SSH。

尚需根据当前 `gpu-l40s-a`/`1gpu-16vcpu-64gb` DevLab 的实际含税费率建立新的逐次点击策略。历史本地 `$1.7343/h` 费率低于 Nebius 2026-10-01 起 AMD L40S 公开的 *from $1.82/h（未含税）*，因此不能把历史数字当作当前预算硬上界；公开价格页也不是该 DevLab 的确切账单。未取得该值前不把只读守护改成可启动配置；即使以后启用，供应商费用也不是软件硬封顶。阿里云整机失联仍无异机自动停机保障，用户已明确接受 CPU-only 风险。
