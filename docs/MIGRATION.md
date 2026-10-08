# WJC 迁移

1. 项目仓库直接位于 `C:\Project\Nebius`，已有本地提交，远程尚未配置。远程明确后执行 `git clone <用户确认的远程> "C:\Project\Nebius"`；当前可从本地仓库 clone 做离线验证。历史数据和机器配置受 .gitignore 排除，不随 clone 复制。
2. 使用已有 Windows PowerShell 5.1；已有 PowerShell 7 也支持，UTC 回归覆盖两者。准备自己的 Python 3.10+ 和 `requirements/offline.txt` 中列出的 CPU 检查依赖。可在自己选择的虚拟环境执行 `python -m pip install -r requirements/offline.txt`。不会默认安装 WSL、OpenSSH、CUDA、驱动或系统组件。离线自检的 Windows 原生测试需要已安装的 OpenSSH `ssh-keygen.exe`，只对合成公钥计算指纹。
3. `Copy-Item -LiteralPath '.\config\local.example.json' -Destination '.\config\local.json'`，仅在目标不存在时执行。模板不能作为真实配置使用，不含真实资源或认证。
4. 填写已有 CLI 在 WSL 中的绝对位置、已安装 WSL 发行版、自己的 profile、目标 tenant/project/devlab、自己的私钥路径和公钥指纹、自己的认证配置路径、known_hosts 路径、数据目录和固定上游目录。认证配置路径供离线元数据检查，可为 `\\wsl.localhost\<distro>\...`；工具不读取其中内容。本轮不会自动登录、生成凭据、设置权限或切换 profile。
5. 填写现有推理环境的 container_python/container_repo/container_checkpoint_dir/container_data_dir/cuda_home。Linux 路径只在显式远端请求中使用。所有真实机器信息只放 `config/local.json`。若配置存放在另一个本地位置，设置 `NEBIUS_LOCAL_CONFIG` 为该 JSON 路径。
6. `python -B scripts/local_config.py` 检查字段及本地路径元数据；缺认证时明确报错且不会调用云端。`python -B scripts/selftest.py` 用合成配置与替身验证迁移。可选 GPU/upstream 检查缺依赖时会明确 skip。

每次换 VM 都需重新核对目标 VM 与准确的 SHA256 主机指纹，按 CLOUD.md 的显式流程创建单次 pin。WJC 使用自己的认证和钥匙；不得复制 WJX 的 key、token、OAuth、known_hosts、旧授权、心跳或运行收据。

路径含空格时，PowerShell 参数用 `-LiteralPath` 或独立带引号参数；不要拼接 shell 字符串。Python 的 subprocess 使用 argv 列表。仓库路径与脚本依赖从自身位置解析，不要求固定盘符或用户名。
