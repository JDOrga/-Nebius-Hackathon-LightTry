# 云操作与离线操作分开

统一入口是 `cloud/Invoke-Cloud.ps1`，整套代码作为一个运行链维护，不区分历史修订版本。默认只返回计划；`-Action Status/Arm/Capture/ConfirmHost/Transfer/ConfirmStopped` 选择流程步骤，显式加 `-Execute` 才转交内部模块。内部模块保留独立职责，原预算、截止、UTC、主机校验和停止验收约束继续生效。例如 `Invoke-Cloud.ps1 -Action Arm` 仍然是零云调用计划，其他参数与下文相应步骤一致。

默认 `cloud/Status.ps1`、Start-TeaRunningGuard、TeaRunningGuard、Wait-CaptureTeaHost、Capture-TeaHost、Invoke-ScaleRemote、Confirm-TeaHost、Confirm-RunningStopped 都只返回计划。Python bridge/lifecycle 也需要 `--execute`。下面是将来获得明确费用授权后的流程，**不是本轮已执行步骤，也不是自动初始化**。

1. 准备并校验自己的 local.json、现有 WSL/CLI/PyYAML、钥匙路径与目标。`Status.ps1 -Execute` 只查询，但会访问真实 API；离线模式不用它。
2. 明确费用预算、授权引用与固定 UTC 截止（不晚于当前时间加一小时）。用 `Start-TeaRunningGuard.ps1 -Execute -ApprovedBudgetUsdIncludingTax <预算> -ApprovalReference <授权引用> -DeadlineUtc <带Z或+00:00的UTC>` 创建新 run，先检查守护 heartbeat、PID、防休眠和 ready_waiting_start。
3. `live_session_running.py preflight --execute --settings <run/live-settings.json> --public-key-file <自己的公钥>` 做只读确认。只有确认 STOPPED、守护有效且绝对截止未到，才能显式 `restart --execute --settings ... --run-directory ...`；通过已配置的 WSL Python 运行，Windows 路径先转换成 WSL 路径。排他 restart-attempt 阻止重复启动，即使 API 响应不确定也不自动再启。
4. `Wait-CaptureTeaHost.ps1 -RunDirectory <run> -Execute` 使用独立 API RUNNING 锚点和当前捕获代码。核对候选的 VM/IP/指纹，与独立来源比对。然后显式 `Confirm-TeaHost.ps1 -RunDirectory ... -ExpectedVm ... -ExpectedIp ... -ExpectedFingerprint ... -UserConfirmed -Execute`。它不会把扫描结果视为独立信任证明。
5. `python scripts/build_bundle.py --run-directory <run>` 只在本地生成代码包及 `bundle.json`；不包含配置、权重和数据。`Invoke-ScaleRemote.ps1 -Execute -RunDirectory <run> -Operation upload_directory`，再 `-Operation upload -UploadArchive`。传输前后重查 API 目标，SSH/SCP 严格 pin，单次传输限 90 秒；大数据分包，不能无限等待。
6. 向 `install_bundle.py` 发送本次 `{run_id,data_root,archive_sha256}` 请求，使用 `-Operation install_bundle -ContainerProgramPath ... -RequestPath ...`；在唯一可写 /home 的 jovyan 容器中安装到新 `preview-<run_id>`，不覆盖旧目录。data_root 来自配置中的 container_data_dir，必须在 /home/jovyan 下。输入、HDR 和权重提前放在自己的本地/持久数据目录，并核对清单与许可。
7. `launch_preview.py` 请求包含 `prep/run_dir/repo/checkpoint_dir/input_dir/input_image/cuda_home/deadline_utc/license_ack`，必须使用本次 timing.json 的 work_deadline_utc。转发器拒绝超出固定工作窗口的 UTC 截止。transport 自动附加本次已核验预算/截止收据；worker 复验收据，外部守护的实时存活由 transport 检查。worker 用现有 Python3.10 执行两个 Cosmos 进程，截止时清理自己的进程组。`inspect_preview.py` 只返回紧凑状态。二者经同一显式 transport 发送，分别使用 Operation launch / inspect。
8. `export_results.py` 请求 `{root,data_root}`，只导出 JPEG/PNG/JSON/log，限 512MiB，不导出权重和大型张量；`-Operation export_results` 后 `-Operation download_results -DownloadResults`，下载至 run/results.tar.gz 并核对 SHA-256。解包到新本地目录再做结构验收和人工看图。统计不是视觉成功证明。
9. 成功或失败都给本次 run 写 complete.json（stop_required=true）。守护负责停止并继续监督。`Confirm-RunningStopped.ps1 -Execute -RunDirectory ...` 做独立 API STOPPED 与 instances=[] 验收；stop 被接受不等于停机完成。核对最终 stopped_verified=true、防休眠释放、守护退出。失败时保留监督并人工处理，不延长截止、不自动重启。

迁移版已在显式授权下验证开机、精确主机信任、SSH、容器身份、代码包上传与安装，并核验停机。模型小任务未成功，结果下载与完整灯光推理尚未验收。源代码与离线回归可审核，不能把合成测试当作收费运行的授权或线上验证。
