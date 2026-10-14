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
  workspace.sqlite3            # SQLite：方案版本、照片身份/哈希/元数据
  workspace.sqlite3-wal/-shm    # SQLite 运行文件；备份必须保持一致
  photos/<sha256>              # 原始照片字节，只经认证的 /api/photos/<id> 读取
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

访问账号为 `lighttry`，密码由 `LIGHTTRY_ACCESS_PASSWORD` 提供（最少24位；未配置或仍为占位密码则拒绝启动）。浏览器 HTTP Basic 登录后，所有静态页面、照片、HDR、任务与结果 API 均受认证保护。直接 HTTP 仅用于受信任的私网/本机验收；公网必须先配 HTTPS。`LIGHTTRY_PUBLIC_ORIGIN` 是精确的受信任入口，例如 `https://studio.example.com`；Host、Origin 和原 CSRF token 都继续校验。HTTPS 代理保留真实 Host/Origin，不依赖随意改写 Origin，也不信任客户端 Forwarded 头。防火墙限制8080只允许指定入口访问。这是单用户/可信小组共享工作区，不是多租户隔离服务。

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
