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

## Linux CPU 服务与持久化

唯一启动入口仍是根 `start.py`。本地预览保持原命令；部署使用显式 `--service`，由 Waitress WSGI HTTP 服务监听 **0.0.0.0:8080**，复用 `studio.Handler` 业务路由，不使用开发用 ThreadingHTTPServer 承担部署流量。`--service` 在读取本机配置之前分流，不读取 `.local/studio.json`，不执行 PowerShell，不依赖任何个人 Windows 路径。前端仍仅为 `project/web/`，无需 Node 构建。

### 统一私有数据根目录

默认 `LIGHTTRY_DATA_ROOT=/var/lib/lighttry`，也可用 `--data-root /绝对路径`。必须位于代码树和演示素材目录之外，不接受符号链接。以专用账号运行，umask 0077；整个目录用持久卷或宿主机持久磁盘，不放进镜像。

```text
/opt/lighttry/                  # 只读代码 + 独立 Linux Python venv
/var/lib/lighttry/              # 私有持久化根，目录 0700
  workspace.sqlite3            # SQLite：方案版本、照片元数据、归属、限流窗口、GPU队列
  workspace.sqlite3-wal/-shm    # SQLite 运行文件；备份必须保持一致
  auth/accounts.json           # 运行时账号哈希，0600，不进镜像/Git
  queue/<job-id>/original       # 私有排队原图；派发前核验，未知派发锁存
  photos/<sha256>              # 原始照片字节，只经认证及归属检查读取
  environments-v2/             # 导入 HDR 原件、派生 HDR 和元数据
  tasks/<task-id>/              # 原照片、预处理输入、request/task/execution JSON
                               # 结果、receipt、执行证据；保持既有验证语义
  inverse-cache/               # 必要缓存，受持久根边界约束
  logs/service.log[.1..3]       # 轮转：阶段、方法、状态；不记录密码/正文/照片名
  tmp/                         # HTTP 上传临时缓冲；同样不可公开
```

任务状态及结果继续使用原任务记录和哈希核验，不为结构整理改写历史事实；SQLite 不取代执行/失败/停机证据。服务默认不开启模型或文字付费接口，不接受 Windows 推理配置。新任务若由适配器显式产生，默认结果留存上限为100年；历史任务原过期时间及执行截止窗口不重置。重启不会自动重算、重新授权或重启 GPU；未完成任务按原事件/截止时间核实，不能把服务重启当作模型成功。

### Linux 独立启动

Python 3.11+；本轮 Linux 验证环境为 Python 3.14。依赖固定在 `requirements-cpu.txt`。部署前按操作系统安装 Python venv 支持，然后在代码根目录执行：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-cpu.txt
# 从受保护的主机环境/密码管理器注入 LIGHTTRY_ACCESS_PASSWORD，24..256 位 ASCII。
# 不使用源码模板中的占位密码，不把真密码写入命令历史或镜像。
export LIGHTTRY_DATA_ROOT=/var/lib/lighttry
export LIGHTTRY_PUBLIC_ORIGIN=https://YOUR_HOST
.venv/bin/python -X utf8 -B start.py --service
```

无 `--assets-dir` 时为空演示目录模式，能直接用用户照片，不依赖本机演示包。可选 `--assets-dir /只读授权素材目录` 和 `--accepted-package /只读验收包` 仍需许可/清单/哈希验证；不复制本机路径或已关闭云授权。内置 HDR 缩略图需要对应经许可的 `upstream/asset/examples/hdri_examples` 文件，默认镜像不带这些媒体；缺失时不会用假图冒充。用户导入 HDR 独立保存在私有数据根。

当前临时账号为 `lighttry`，运行时账号文件由 `LIGHTTRY_ACCOUNTS_FILE` 提供（创建和交付见下文）；兼容受控的 `LIGHTTRY_ACCESS_PASSWORD` 环境注入，未配置或仍为占位密码则拒绝启动。浏览器 HTTP Basic 登录后，所有静态页面、照片、HDR、任务与结果 API 均受认证保护。直接 HTTP 仅用于受信任的私网/本机验收；公网必须先配 HTTPS。`LIGHTTRY_PUBLIC_ORIGIN` 是精确的受信任入口，例如 `https://studio.example.com`；Host、Origin 和原 CSRF token 都继续校验。HTTPS 代理保留真实 Host/Origin，不依赖随意改写 Origin，也不信任客户端 Forwarded 头。防火墙限制8080只允许指定入口访问。这是单用户/可信小组共享工作区，不是多租户隔离服务。

### systemd 服务化与镜像边界

模板：`deploy/lighttry.service`、`deploy/service.env.example`。代码安装到 `/opt/lighttry`，venv 建在该主机；不要搬 Windows venv。不存在时创建专用 `lighttry` 系统账号，并准备 `/etc/lighttry/service.env`（root:root，0600），填写新密码、公开 Origin 和数据根。然后：

```sh
sudo install -m 0644 deploy/lighttry.service /etc/systemd/system/lighttry.service
sudo systemctl daemon-reload
sudo systemctl enable --now lighttry
sudo systemctl status lighttry
# 验收阶段可手动重启一次，随后核对原任务与结果哈希；不涉及 GPU launch。
sudo systemctl restart lighttry
```

单进程、4个 HTTP 工作线程，任务库持有 OS 排他锁；不能对同一数据根启动多个进程。systemd 使用 StateDirectory、私有权限、只读代码、限定可写根、异常自动重启及30秒停止上限。SIGTERM 正常退出并释放任务锁；状态不随进程销毁。HTTP 请求体最大32MiB，照片接口20MiB，方案 JSON 1MiB；照片/HDR 解码另有尺寸限制。systemd 日志另可从 `journalctl -u lighttry` 查看。

可选容器模板为 `deploy/Dockerfile`，配套 `.dockerignore` 为代码允许清单。镜像不含 `.local`、演示照片、验收照片、用户上传、任务、venv、凭据或云实验。运行时必须挂载私有数据卷到 `/var/lib/lighttry` 并注入访问密码/Origin；容器依旧从 `start.py --service` 启动。容器模板和 systemd 安装是否在目标部署主机成功，须单独验收，不能用本地进程测试代替。

### 旧浏览器方案迁移与跨浏览器找回

- 原浏览器中的草稿不会自动上传。在“方案库”点击“导出浏览器方案 JSON”，到新浏览器点击“导入方案 JSON”；保留 planId、版本、名称、参数、照片哈希和任务引用。也接受旧 `lighttry.schemeLibrary.v1` 原始数组导出。相同 planId/version 内容冲突则拒绝覆盖；无效导入不部分成功。
- 旧页面若尚无导出按钮，可在该原浏览器控制台执行 `JSON.parse(localStorage.getItem('lighttry.schemeLibrary.v1') || '[]')`，将数组保存为 JSON 后通过新页面导入；仅这个数组没有原照片字节，需要重新选择原照片并显式关联到原方案，不会猜测或借用另一张图。
- JSON **不含照片像素、HDR 字节、浏览器凭据、聊天或云 Key**。完整迁移旧上传草稿时还需同一原照片；有 originalSha 的导出可按原哈希恢复关联。导入 HDR 方案应先在目标服务导入同一 HDR。跨服务迁移时任务引用不等于结果已经搬迁。
- 点击“保存到服务（含当前照片）”并确认，才会把当前原照片上传到私有数据根，并将全部方案版本保存到 SQLite；照片与方案分两步，失败会明确提示可能已保存照片，不伪称全部成功。浏览器里的“保存方案”仍是本地草稿操作。
- 换浏览器登录**同一服务**后，页面加载服务方案库、已保存照片及任务编号；照片可从私有接口重新读取。任务与结果再由服务核验，不信任导入 JSON 的成功断言。多张尚未上传照片须逐张选择并保存。
- “导出服务方案 JSON”只导出参数/照片元数据/引用，不是完整数据备份。完整换机需在停止 CPU 服务后备份**整个数据根**（含 SQLite/WAL、照片、HDR、任务、结果、日志），恢复所有权和0700权限；再启动服务，不触发模型执行。

### 验证范围

新增 `project/tests/test_linux_service.py` 验证认证、Host/Origin/CSRF、路径隔离、SQLite版本冲突/事务回退、照片哈希和真实 Linux Waitress 进程重启。重启验收使用明确标注的离线执行替身生成测试图片，不能当作 Cosmos 实机成功。浏览器迁移纯逻辑测试见 `workspace-portability.test.js`；真实浏览器交互和目标主机上线仍需独立验收。本轮不创建云实例、不复用历史授权、不收费。

## 临时账号与服务安全边界

部署入口仍是 `start.py --service`，页面、静态脚本、业务 API、照片、HDR、任务和结果下载统一先认证；没有公开照片目录或例外下载入口。认证失败为401，限流为429（Retry-After:60），不存在/非本账号对象统一404。HTTP Basic 只用于本机/可信私网；公网必须经过 HTTPS 和防火墙，不能在公网明文发送登录密码。

### 运行时临时账号

可在服务账号下执行一次以下命令，创建7天有效的 `lighttry` 普通用户账号；不启动服务、不读取云凭据、不启用收费：

```sh
.venv/bin/python -X utf8 -B start.py --service --init-account \
  --data-root /var/lib/lighttry --account-output /var/lib/lighttry/private-temporary-login.txt
```

登录密码为随机生成的高熵密码，只写指定的私有交付文件，不打印到 stdout；服务保存独立随机盐的 scrypt 哈希于 `/var/lib/lighttry/auth/accounts.json`（0600）。账号文件与交付文件须由服务 UID 持有，私有目录0700。已有文件拒绝覆盖。通过 `LIGHTTRY_ACCOUNTS_FILE=/var/lib/lighttry/auth/accounts.json` 注入，模板见 `deploy/service.env.example`；旧 `LIGHTTRY_ACCESS_PASSWORD` 环境注入仅作为受控兼容，不存在源码默认密码。改账号后重启 CPU 服务；退出/撤销不能仅靠关掉浏览器标签，HTTP Basic 缓存需由浏览器清除，服务端账号期限仍强制检查。

账号角色由受保护运行时文件提供，不接受网页修改/注册。临时账号角色为 user；operator 也不能绕过未配置的守护、预算或当前主机确认。`GET /api/me` 只返回用户名/角色，不返回密码、哈希或云凭据。

### 归属、限额与路径

SQLite ownership 表绑定照片、方案、导入 HDR 和任务。任务/结果/下载/请求恢复先检查当前账号归属，猜到别人的 UUID 也不可读取。共享许可演示样例可由已登录者浏览；历史验收包与实测结果仅给配置的旧数据 owner。旧工作区启动迁移用 `LIGHTTRY_LEGACY_OWNER`（默认 lighttry，必须是已配置账号），只补齐未绑定对象，不改写已有归属、任务事实或原始证据。换账号时浏览器缓存按用户名分开；旧未分账号库使用“导出未分账号的旧浏览器库”后显式导入，不自动收编为另一个账号所有。

照片最大20MiB，只接受与声明 MIME 一致的单帧 JPG/PNG/WebP，宽高32..16384、最多4000万像素；HDR最大32MiB，限Radiance RGBE、指定2:1布局和解码维度/扫描行；方案 JSON 最大1MiB，文字/条件 JSON 最大8KiB。至多两个并行解码通道，忙时429。每账号最多200个私有照片身份，照片字节总配额512MiB。文件名不作为磁盘路径：照片用SHA，任务用服务生成UUID；禁止路径遍历、编码绕过、任意文件下载及符号链接，并核验原图/结果哈希。HTTP缓冲仍受Waitress 32MiB上限控制；在代理侧也应限制请求体、连接数和超时，应用认证不能阻止HTTP服务器先接收请求体。

限流存入SQLite，CPU服务重启不重置窗口；按真实网络REMOTE_ADDR而非客户端X-Forwarded-For计数。每分钟上限：IP240、账号120、登录失败10、写请求30、上传8、生成/文字建议3；限流失败不继续解码或派发。反向代理下IP预算会共享，需由部署入口补充可信代理/WAF策略，不能为了绕限流直接信任客户端转发头。

### 单 GPU 串行队列与收费边界

`POST /api/tasks` 需认证、同源、CSRF、对象归属及服务端逐项授权；浏览器不能传owner、命令、预算、云控制或守护替代字段。持久化FIFO队列最多20项，跨账号只有一条GPU执行通道；同账号requestId幂等，任务身份由服务生成并在派发前持久化。队列读取是只读，真正派发只由独立服务器工作线程执行；每次派发重新检查 adapter.authorize_job 的当前范围/预算/守护授权。现有真实适配器未接入该授权协议，默认仍为OFF；提供凭据不等于提供授权。

原任务库单进程OS锁和串行检查继续生效。派发前提交dispatching闩锁；异常、进程退出或执行状态未知会阻塞通道，不自动重发launch；已有旧执行/未知执行也会占住通道。只有执行端真实结束且结果通过原校验，才推进下一项。等待项授权撤销/过期则不派发，不继承旧实验的预算或时限。队列验证用离线替身，不能当成GPU实机验收。

生成、启动、停止没有普通页面GET控制路径；GET控制请求为404/405。普通账号POST云start/stop为403，operator仍因未接入受审计控制器而503，绝不隐式调用CLI。任何后续真实云控制都必须重新走 `docs/EXECUTION_FLOW.md`，本轮不登录、不收费、不启停GPU。

### Nemotron / Nebius 凭据

只支持受保护的服务端运行时文件 `LIGHTTRY_NEMOTRON_KEY_FILE`、`LIGHTTRY_NEBIUS_CREDENTIAL_FILE`，或服务端环境 `NEMOTRON_API_KEY`、`NEBIUS_IAM_TOKEN`。文件必须在代码树外、普通文件、无符号链接、0600；建议只读挂载到 `/run/secrets/`，而非复制进镜像。代码只保存变量名与接口，不保存实际值，不从网页提供/返回凭据，也不记录请求正文、Authorization、URL查询或异常原文。账号文件、交付文件和service.env不入Git；镜像允许清单不含这些文件。环境/文件读取入口已离线验证，实际服务仍未开启两家收费适配器。

验证：`test_service_security.py` 覆盖匿名访问、GET/POST收费控制、越权对象、重启后限流、上传/路径限制、FIFO串行/不确定闩锁和凭据泄露检查；Linux真实HTTP重启检查继续验证原图、HDR、方案及结果找回。本轮临时账号由本机Linux运行时生成，私有交付路径不纳入源码、补丁或验证正文。

## CPU→GPU HTTPS 协议与独立守护（仅离线验收）

当前代码新增 `worker_link.py`、`gpu_session.py`、`guard_runtime.py`，仍由唯一根入口 `start.py` 分流。没有注册真实 Nebius 控制器、真实模型执行器或新的收费授权；默认 Web 服务仍拒绝实际启动/生成。现有安全队列不因本节或凭据存在而自动连接真实 GPU。下面“通过”只指离线替身/本机进程实验，不是云启动、模型加载或停机实机验收。

### 接口与身份

选择受认证的 HTTPS worker，而不是从网页传 SSH 命令。CPU `HTTPSWorker` 强制 https、CA/主机名校验、精确 origin，无账号嵌入 URL、无重定向、无自动重试；单次网络超时5秒（最大10秒）。worker token 仅通过服务端运行时私有文件 `LIGHTTRY_WORKER_TOKEN_FILE` 提供，不复用浏览器登录密码，不返回页面，不记录到日志。TLS 入口只将认证后的指定 `/v1/` 路由转发到 worker 的本机127.0.0.1:9080，9080不对公网开放。

| 接口 | 行为 |
| --- | --- |
| GET /v1/health | sessionId/resourceId/模型状态，仅查询，不加载模型 |
| PUT /v1/blobs/{sha256} | ≤32MiB、内容哈希命名的受认证制品上传；无文件路径/命令字段 |
| POST /v1/jobs | 精确 jobId/sessionId/resourceId/artifactSha256/requestSha256 绑定 |
| GET /v1/jobs/{jobId} | 查询原任务，恢复响应丢失；不产生执行 |
| GET /api/gpu/status | CPU 登录后读SQLite快照，不轮询云、不续租、不启动 |
| POST /api/gpu/start | operator + 同源/CSRF；仅接受requestId；范围/预算来自服务端 |
| POST /api/gpu/confirm-host | operator 确认本会话首次可靠RUNNING的当前主机身份 |
| POST /api/gpu/stop | operator 指定当前sessionId；持久化单次stop闩锁 |

未配置控制器时POST控制仍503；普通账号仍403，未登录仍401，控制GET仍404/405。离线HTTPS协议测试使用明确的连接替身，不宣称已部署真实TLS入口。`start.py --worker --data-root /var/lib/lighttry-worker --session-id SESSION --resource-id RESOURCE --worker-token-file /run/secrets/worker-token` 可运行受保护协议壳；默认模型适配器未设置，不会加载/执行GPU模型。制品内的模型请求/结果收据导入需要后续正式适配器遵守现有哈希、原图、配方和实际结果验证，不能用worker成功状态替代产品视觉验收。

### 持久化会话与单次副作用

会话数据库在私有guard目录 `sessions.sqlite3`：保存session/scope/resource、七种状态、首个启动时间、首次可靠RUNNING时间、固定截止、空闲期限、主机确认、启动/停机闩锁、任务派发表和逐步事件。worker另存 `worker.sqlite3` 和只读内容寻址制品。SQLite同步提交，更新使用revision比较，跨进程的过期快照不能覆盖新状态。

状态为 STOPPED停止、STARTING启动中、LOADING模型加载中、READY就绪、EXECUTING执行中、STOPPING停机中、UNKNOWN异常待核实。初始STOPPED只是未建立软件会话，providerState=null、verifiedStopped=false，不代表云API已确认资源停止。

同一服务端scopeId无论多少点击/requestId/标签页都复用一个sessionId；启动前先持久化会话和start-attempt，独立守护/整机兜底ready且独立预检STOPPED+空实例后，只发一次start。启动响应丢失或断线记UNKNOWN，后续只观察原资源/操作，不能restart。已关闭scope不会因再次点击创建新会话；新范围必须另获新的服务端授权，未确认停机的资源禁止新scope。

任务先按原jobId查询，再持久化attempted后仅POST一次。若提交响应丢失，重启后查询同一jobId和完整哈希绑定；即使返回404，也不能证明前一个请求没有被接收，保留uncertain，不自动重POST。worker相同jobId相同哈希幂等，改内容409；真正执行前保存dispatching，进程退出后的dispatching变uncertain并占住单通道，不能靠重启再执行。模型调用只由受审计的服务器执行器触发，GET从不调用run_one。

### 独立守护与不可续期时间

当前默认上限沿用 `docs/EXECUTION_FLOW.md`：启动等待600秒；首次可靠独立API RUNNING起算工作18分钟、停机25分钟、核验27分钟；绝对保护取初始40分钟与本轮授权截止的较早值。worker ready不等于资源RUNNING。加载/空闲默认由本次服务端范围指定10..300秒；任务完成后才建立新的空闲期限，绝不延长会话工作/绝对截止。GET、浏览器刷新、应用/守护重启和心跳均不重置上述时间，也不继承主机确认到新会话。

CPU进程以显式server heartbeat接口续30秒短租约；它只表示当前CPU存活，不续绝对时间。该心跳需要未来可信服务端接线/定时器调用，不能由普通页面GET代发。本轮默认控制器未接线，不能假称该生产链路已经运行。守护进程独立于Web进程，`deploy/lighttry-guard.service` 无 PartOf/BindsTo lighttry.service。绑定配置是代码树外0600的受保护文件，factory必须是经过审计的provider/worker/fallback适配器；未配置就拒绝启动，不猜CLI，不自动找历史profile。唯一命令入口：

```sh
.venv/bin/python -X utf8 -B start.py --guard --data-root /var/lib/lighttry/guard --guard-config /etc/lighttry/guard.json
```

守护独占观察职责；Web只读快照，不再加云轮询。STOPPING普通等待上限120秒，同时不超过原verify/absolute界限。到界限立即持久化UNKNOWN/STOPPING_BOUND_EXCEEDED，不伪称成功、不延长工作/核验；之后独立监督继续仅核实停机，晚到STOPPED+instances=[]仍可确认。安全收尾另外需要外部监督者证明守护PID已退出、防休眠已释放；守护不能在还活着时自称退出。这里不获取防休眠锁，sleepHeld=false仍须与部署方式核实。

### CPU整台失联的兜底方案

同机systemd守护只防Web进程退出，**不防CPU整机断电、网络失联或磁盘丢失**。真实启动前必须在CPU/GPU之外的管理主机或供应商独立控制平面预置stop-only租约：绑定resource/session与不晚于40分钟的绝对截止，CPU心跳30秒过期即执行同一幂等stop操作；管理主机使用单独的最小停机权限和独立持久盘。必须先拿到经认证、与本会话/资源/截止完全匹配的ready收据，再允许云start。若无法预置，启动拒绝，不能降级为只靠CPU/GPU自身shutdown。

离线 `Deadman` 参考实现展示不可延长的绝对截止、短租约失联触发、停机闩锁和独立STOPPED+空实例核实；本地替身标记simulation=true，不能充当真实异机部署证明。`deploy/lighttry-deadman.service` 只能装在独立管理主机，入口 `start.py --deadman`，真实provider/factory、认证收据通道和供应商侧定时停机保底尚需后续部署验收。若管理主机或供应商API也同时失联，软件不能保证账单硬封顶；必须预置供应商侧硬到期/定时停机（若支持并验证）、控制面告警和人工停机流程。未知stop响应不写成功、不发新start；真实兜底未就绪则不开GPU。

### 本轮验证

`test_worker_guard.py` 覆盖七状态、24次并发/多标签启动只有一次模拟start、启动ACK丢失、断线、重启固定截止、任务ACK丢失先查询、404/不确定不重跑、worker执行闩锁、STOPPING有界等待后停机核实、CPU整机失联的异机兜底逻辑、时钟回退和未ready截断。独立进程用真实本机Linux CPU HTTP服务及守护进程，provider/模型仍是离线替身；不把这项本机进程通过写成真实云验收。后续真实接线必须重新完成当前授权、独立预检、守护ready、单次启动、当前主机确认与四项释放，不能使用旧已关闭预算。
# CPU 镜像构建与本地容器验证（2026-10-14）

镜像版本 `lighttry-cpu:2026.10.14-cpu.1`。入口仍为根 `start.py --service`，容器内监听 `0.0.0.0:8080`。
已构建镜像归档位于 `deploy/images/lighttry-cpu-2026.10.14-cpu.1.tar.gz`（76,764,481字节），校验文件为同目录 `SHA256SUMS`。
在 Linux 执行 `cd deploy/images && sha256sum -c SHA256SUMS && docker load -i lighttry-cpu-2026.10.14-cpu.1.tar.gz` 即可导入，不必重新构建。
导入后镜像 ID 应为 `sha256:d6ac0b3cee445fa5f9d335f8241a566069db2e393a5134d2d7519e790a9bb5b2`；镜像不包含运行时数据、账户文件或模型权重。
基础镜像为固定摘要的 Python 3.14.0 / Debian bookworm slim；Python 依赖见根 `requirements-cpu.txt`，全部固定版本。
构建上下文采用 `.dockerignore` 逐层白名单：不包括 `.local`、历史报告、私钥、任务、照片、测试替身或模型权重。
约 60GB 权重仍留在 GPU 存储，CPU 镜像不含 CUDA、模型权重和云凭据。

以下命令在安装 Docker Engine 的 Linux 主机运行；只新增此前获准的 Docker 系统运行组件及上述固定依赖。

```sh
docker build -f deploy/Dockerfile -t lighttry-cpu:2026.10.14-cpu.1 .
sudo install -d -m 700 -o 10001 -g 10001 /srv/lighttry-data
docker run --rm --network none -v /srv/lighttry-data:/var/lib/lighttry \
  lighttry-cpu:2026.10.14-cpu.1 python -B start.py --service \
  --init-account --account-output /var/lib/lighttry/temporary-login.txt
# 配置只含绑定路径，不把密码/云凭据放进 env 文件或命令行。
sudo install -m 600 deploy/service.env.example /etc/lighttry-cpu.env
docker run -d --name lighttry-cpu --restart unless-stopped \
  --read-only --cap-drop ALL --security-opt no-new-privileges \
  --pids-limit 128 --memory 512m -p 127.0.0.1:8080:8080 \
  --env-file /etc/lighttry-cpu.env \
  -v /srv/lighttry-data:/var/lib/lighttry lighttry-cpu:2026.10.14-cpu.1
docker logs lighttry-cpu
docker restart lighttry-cpu
```

临时账号7天到期，交付文件仅在私有挂载目录读取，不贴入日志或 Git。将 `LIGHTTRY_PUBLIC_ORIGIN` 改为实际外部 HTTPS origin；生产由受控 TLS 反向代理转发到本地8080。
HTTP Basic 只能用于本机 HTTP 测试；远程必须 HTTPS。账户文件、SQLite、照片、HDR、方案版本、任务结果和必要日志均在挂载目录。
挂载目录必须归 UID10001 所有；备份时停服务或用 SQLite backup，不只复制主数据库而忽略 WAL。
换浏览器通过同一账号读取服务端方案；未迁移的浏览器方案先导出 JSON 后导入，私人素材不放在网页静态目录。

本地真实容器验收（需要 Linux Python 和固定依赖，仅作测试客户端）：

```sh
sudo env PYTHON=/path/to/validated/python RUN=/var/tmp/lighttry-fresh-acceptance \
  sh deploy/verify_container.sh
```

验收使用外部只读挂载的合成任务替身，不改变生产镜像，也无生产启用开关。
脚本测试网页、登录、上传、方案保存、任务提交/合成结果下载；随后移除替身改用生产入口并重新创建和重启容器，检查持久化数据及原始/结果哈希。
普通生产入口收费服务仍关闭；真实 GPU、云认证、异机守护和公网 TLS 部署不属于本次容器验收。
