# LightTry 本地演示迁移（2026-10-09）

仅需 Python 3.11（实测 3.11.9）、候选代码和独立素材。启动和安装无第三方 Python 依赖，不需要 pip、Nebius 登录、WSL、SSH、GPU、模型、云环境或历史实验目录。Node 仅用于可选前端状态回归，本轮实测 v24.19.0。

## 本轮版本状态

origin 为 `https://github.com/JVerdL/-Nebius-Hackathon-LightTry`，main/HEAD 为 `71fe251262f23c04105562f9e7d667cc46c102bb`。本轮修改尚未提交、推送。GitHub 当前 HEAD 仍是原版本；本轮验收名称为“候选交付目录验收”，不是 GitHub 克隆验收。WJC 实机待验收。

WJC 可以先 `git clone https://github.com/JVerdL/-Nebius-Hackathon-LightTry "<自己的新代码目录>"`，但还需取得本轮候选代码。现准备了 `lighttry-demo-code-candidate-20261009.zip`（仅含 `project/` 代码/文档/测试）。将它解压到另一个新目录用于本轮演示，避免覆盖既有 clone 的修改。未来本轮改动真正入库后可直接使用包含这些改动的 clone；本轮没有执行提交或传输。

## 最短接手步骤

1. 准备自己的 Python 3.11，确认 `python --version`。
2. 取得候选代码包，解压到一个新目录；取得单独的 `lighttry-demo-assets-20261009.zip`，保持原包并校验下列 SHA256。素材包仅限本地保留，许可缺口见 [分发核对](DEMO_ASSET_LICENSES.md)，不得据此公开发布。
3. 在包含 `project/` 的代码根目录运行（所有占位符用自己的路径替换，不含真实个人配置）：

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath "<素材包路径>"
python -X utf8 -B project/install_demo_assets.py "<素材包路径>"
python -X utf8 -B project/build_catalog.py
python -X utf8 -B project/server.py
```

4. 打开 <http://127.0.0.1:8765>。端口占用时加 `--port 8766` 并打开对应地址。Ctrl+C 停止。
5. 切换四样例和三个灯光，比较实际输入/结果；手机窗口确认上下比较可用。载入自己的照片应仅显示原图、“已载入，尚未连接推理服务”，结果下载禁用。样例可下载原始 JPEG，用 `Get-FileHash` 与 `project/data/catalog.json` 对应结果 SHA256 核对。

素材包：14,286,952 字节（约 13.63 MiB）；解包 14,422,082 字节。23 文件：4 原照、4 实际模型输入、12 历史结果、3 份精简来源/署名/本地范围说明；无 HDR、G-buffer、中间文件或运行日志。

```text
ed34c7ea71740ed2176d2ba18bc88d1f6da51baed6c46be962d93bc9e88922df
```

导入器只接受固定清单，校验每个文件大小和 SHA256 后安装；拒绝额外文件、路径越界、损坏包和已有目标，不覆盖现有素材。也可自行解压包顶层 `demo-assets/` 到 `project/demo-assets/`，随后运行 `build_catalog.py` 验证。启动同样校验图片和来源记录；不会寻找旧实验或其他替代图片。

## 外部目录配置示例

无需创建真实账号配置文件。默认无需任何变量。外部素材路径可在 PowerShell 当前会话中配置：

```powershell
$env:LIGHTTRY_DEMO_ASSETS = "<自己的独立素材目录>"
python -X utf8 -B project/install_demo_assets.py "<素材包路径>"
python -X utf8 -B project/server.py
```

或显式参数：

```powershell
python -X utf8 -B project/install_demo_assets.py "<素材包路径>" --assets-dir "<自己的新素材目录>"
python -X utf8 -B project/server.py --assets-dir "<自己的素材目录>"
```

相对路径从 `project/` 解析；显式参数优先于环境变量。含空格路径作为一个带引号参数传入。不要用 `config/local.json` 配置演示；那是既有云工具配置。机器专属 `.env*`、`demo.local.json` 和素材目录被忽略，不放入候选代码。自定义外部目录应放在仓库外，不要将素材解压到其他 Git 可见目录。

不得复制 WJX 认证、SSH 私钥、known_hosts、主机批准记录、守护状态、PID、云收据或历史日志。本轮没有改动现有连接和停机工具，没有传输任何包。代码包的大小/哈希另保存在本机交付收据，避免包内记录自身哈希造成循环。

## 验证范围

```powershell
python -X utf8 -B -m unittest discover -s project/tests -p 'test_*.py' -v
node --test project/tests/state.test.js
```

Python 14 项、Node 8 项通过。未安装素材时，来源/HTTP 集成测试会明确跳过并提示安装；配置与合成安装测试仍运行。跳过不等于样例验收通过。

WJX 上的新目录包含空格、只复制候选 `project/` 文件，无 `controlled-tests/` 和机器配置。实际测试了缺素材提示、导入、启动、4×3×2 桌面与手机映射/比较、未连接照片预览、实际下载及哈希。另在含空格的外部素材目录、从候选目录之外的工作目录启动，环境变量和命令参数覆盖均通过；配置错误时即使默认素材存在也不会回退。WJC 未实际操作，仍需在其电脑执行以上步骤并验收。
