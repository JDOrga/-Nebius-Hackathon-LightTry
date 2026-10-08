# 当前工程边界

本项目沿用 Cosmos，提供有限保真度的灯光预览。默认 1280×704、单帧、15 步、seed 1000。先生成 basecolor/normal/depth/roughness/metallic，再以三个 HDR 做 forward 预览。结构检查只确认尺寸、完整性、非恒定输出与灯光差异；几何、文字、微小材质、阴影、高光和色温仍需人工看图。不是物理渲染或高保真修复工具。

`scripts/run_experiment.py` 保留原有 Cosmos 调用和恢复约束，输入改为显式本地数据路径。`validate_outputs.py` 保留结构验收和 contact sheet。没有纳入裁剪放大、融合、latent 分析或高分辨率补丁链。

`prototype/env_sampling.py` 是独立的 PyTorch/grid_sample HDR 替代实现；`patches/` 仅修改上游两个调用文件并添加一个采样模块。支持 base-level 双线性采样，明确纬度 wrap/clamp、面朝向和角点平均规则；不承诺与原 nvdiffrast 的逐位一致或接缝梯度一致。NumPy 数学参考及字面真值测试独立保留。

`cloud/` 是一套统一的守护执行链，由 `Invoke-Cloud.ps1` 提供入口，内部模块负责等待、主机捕获、所属进程预算、API 校验、停机守护和 UTC 请求转发。源指针的 14 个代码 SHA-256 已核对一致；历史修订来源只记录在 extraction.json，不作为运行版本或分支。旧 Capture-SessionHost 不在执行链或测试依赖内。

改动集中于相对路径、本地配置、显式执行门槛、统一 JSON UTC 解析、传输预算与绝对截止上限。首次独立 API RUNNING 锚点不重设，工作最多 18 分钟、停机触发最多 25 分钟；硬截止可进一步缩短窗口，并在 STARTING 阶段生效。启动时必需提供不超过一小时的 UTC 绝对截止和费用授权。守护使用 monotonic 计时和 UTC 截止双重约束，最终要求独立 STOPPED 且 instances=[]，再释放防休眠。

主机捕获只发布候选公钥，不创建信任。API 身份、项目所属租户、当前 VM、地址、公钥映射、用户、容器 image 与唯一可写 /home 都需核对。精确指纹由操作者独立确认；SSH 使用 StrictHostKeyChecking=yes 和单次 run 的 pin，不复用另一台电脑的信任记录。

原生 Windows 进程先挂起、加入私有 Job、再恢复；执行、管道读取和所属进程清理共用预算。残留管道、输出截断、读取失败和清理不完整均不能成为成功结果。SSH/SCP 复用同一机制，单次传输有 90 秒上限和固定窗口限制。

本次指定源目录未找到独立的在用产品 UI 工程；历史验收 HTML 不作为产品 UI。没有新建 UI。未来若 UI 位于另一目录，需给出实际入口再按白名单补入。
