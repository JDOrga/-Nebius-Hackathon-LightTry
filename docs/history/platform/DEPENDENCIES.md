# 安装与固定上游

项目不会在 import、离线检查、安装说明或默认命令中安装包、下载模型或管理 VM。

离线依赖：Python 3.10+，NumPy 1.26.4、Pillow 11.1.0、PyYAML 6.0.2；Windows PowerShell 5.1，PowerShell 7 可选。PyTorch、OpenCV、imageio 是 HDR 动态集成检查的可选依赖；缺少时报告 skip。PyYAML 是真实主机映射校验的必要依赖，WSL 中也必须具备。

推理基线来自现有链：Linux Python 3.10、PyTorch 2.6.0/cu124、torchvision 0.21.0、CUDA toolkit 12.4、L40S。授权的远端检查实测 Python 3.10.21、Transformer Engine 1.12.0、av 17.1.0，已写入 `manifests/runtime-baseline.json` 与附加依赖约束。`requirements/inference-upstream.txt` 保留固定提交的逐项版本。**尚未形成包含全部 wheel 哈希的完整推理锁文件**；完整 renderer 入口、TE Linear 与新机器 GPU 环境仍需单独预检，版本核对和 Tokenizer 小任务不能替代完整灯光推理验收。

准备上游是手动、明确的联网步骤；不是离线初始化的一部分：

```powershell
git clone --no-checkout https://github.com/nv-tlabs/cosmos-transfer1-diffusion-renderer "<配置中的独立 upstream_repo>"
git -C "<独立 upstream_repo>" checkout --detach 0f3e2dc435032ecbad654c2fc2153df85384b138
git -C "<独立 upstream_repo>" rev-parse HEAD
python -B scripts/apply_hdr_patch.py --repo "<独立 upstream_repo>"
# 审核补丁计划后才应用；未知修改会拒绝覆盖。
python -B scripts/apply_hdr_patch.py --repo "<独立 upstream_repo>" --apply
```

上游必须在独立目录，不能把嵌套 `.git` 加入本工程。`manifests/patch_manifest.json` 固定补丁及前后 SHA-256，已应用状态会复验。安装 CUDA 版 torch 时使用用户选择的官方 CUDA12.4 wheel 源，再准备上游依赖；不要为了整理或移植新增 apex/nvdiffrast。不要把虚拟环境当作完整 CUDA toolkit。

真实推理前运行 `scripts/preflight.py --repo ... --checkpoint-dir ... --cuda-home ... --out ...`，核查实际解释器、完整上游入口导入、torch/CUDA、L40S、小张量、TE Linear、nvcc 12.4、HDR 文件补丁及磁盘空间。这里不安装、修复或登录。预检失败就停止，保留自己的本地诊断。

权重清单位于 `manifests/weights_manifest.json`，固定官方仓库 revision、大小与 SHA/Git blob/MD5。`weights.py` 默认 plan；verify 流式校验。download 是另一个显式动作，要求模型许可确认与固定 UTC 截止，401/403 不自动认证，保留 partial、损坏 final 和锁所有权。下载不管理 VM。
