# LightTry 同图真实复用测速（2026-10-10，再次授权）

真实执行成功：inverse=0，forward 子进程=1，实际初始化=1；同一对象 `0x7906824d46a0` 在同一进程顺序生成 sunny、sunrise。任务 `73edd6656f9e47db85578d93e42c1e8b`，run `cdbca2ab59bb44e39537d8d14f2d3552`。仅启动一次。

历史 inverse 来源 `6d541112fa164c099d9fc06c560b464d` / `dc011af5186c492d8ffd2f6342e5c07f`，复用 key `155868063db861b7513f9c78dd0161da123cf3542ee7b72620f6a83c01e318e5`。必需复用校验成功；五通道原子完成记录、输入内容/预处理/有效区域/模型配置/相关补丁与哈希一致。未重算 inverse，未改历史 manifest、receipt、任务或结果；本地历史文件哈希全部保持一致。

- [sunny](C:/Project/Nebius/.local/reuse-benchmark-20261010-retry1/private-job/remote-evidence/presets/0/458ade998de043c88580c8bd3bd2c228/relit_frames_0000/photo/0000.0000.jpg)，SHA256 `4fa20f6f9926e83a4321d1a3d7a3987a4d2fb8277cd6e5fa6300fdb4437f44e6`，1280×704，解码/非恒定/哈希通过。
- [sunrise](C:/Project/Nebius/.local/reuse-benchmark-20261010-retry1/private-job/remote-evidence/presets/1/9238b4defb67463183a5747e64c08fc1/relit_frames_0001/photo/0000.0000.jpg)，SHA256 `23474183ce2dea7df9a2fcfbf40072089708f64e69d9948098b6ebed20e69e18`，1280×704，解码/非恒定/哈希通过。

从本次驱动 submission_entry 到首次观察结果可用 **387.687 秒（6分27.69秒）**，包含上传、执行和轮询/传输延迟；不是无误差的远端首项完成时刻。首项完成至第二项完成同主机单调时钟增量 **5.970 秒**。全部结果传回并校验 **443.299 秒（7分23.30秒）**。结果导出约14.01秒，下载24.07秒，下载结束后本地校验约0.15秒。

| 实际可观察边界 | 预设 index | 秒 |
|---|---|---|
| imports_end |  | 11.860 |
| model_construction_end |  | 0.476 |
| network_load_including_assignment_end |  | 273.538 |
| tokenizer_load_including_assignment_end |  | 1.867 |
| pipeline_initialization_end |  | 275.881 |
| generation_end |  | 8.123 |
| result_write_end |  | 0.081 |
| result_write_end |  | 0.018 |
| preset_validation_end | 0 | 0.006 |
| preset_end | 0 | 285.275 |
| generation_end |  | 5.432 |
| result_write_end |  | 0.018 |
| result_write_end |  | 0.016 |
| preset_validation_end | 1 | 0.006 |
| preset_end | 1 | 5.969 |

最大 torch.load 可观察调用为264.47秒；pipeline 初始化275.88秒、network加载含赋值273.54秒是嵌套范围，不能相加。这支持此次耗时主要落在这些调用范围，但不能进一步断言磁盘慢、缓存失效或纯权重I/O。主机计时未CUDA同步，不称为纯GPU kernel时间。此次是新forward进程，文件系统缓存冷热未知；第二预设真实复用模型对象。

两项均采用 reset-before-forward-generate-v1 / seed1000，实际重置事件已核对；不声称与独立进程逐像素一致，也未拿旧sunny替代新结果。historical_metadata 沿用，实际记录 mode=reuse_historical_without_content_scan，content_verified=false，checkpoint_content_bytes_read=0；未追加权重内容扫描。

执行端 batch 验收成功。结果未通过产品已有路径登记，网页双真实结果切换未验收；productDisplayTime=null。本机文件已可查看，当前报告显示真实输出。历史网页已生成sunny、未生成sunrise不串结果、显式提交、刷新、全画布/裁剪比较与下载的上轮浏览器记录保留，本轮不伪造第二个产品任务。后续接入需要正式批量结果登记路径和页面切换验收；不支持交互式模型常驻，模型退出后的新灯光仍可能重新初始化。

现场只修复本地汇总器与真实权重验证记录的模式字段契约。原始证据保持不变，无远端代码修复、模型重跑、第二次启动或延长窗口。停机首次独立查询仍为STOPPING，未报告为STOPPED；继续守护直到独立确认STOPPED、instances=[]，守护退出/防休眠释放通过。

独立最终核实 UTC `2026-10-10T03:11:02.4652613+00:00`。本轮启动请求至最终核实保守按全部过渡计费，约12.50分钟，税前估算 **$0.368**，50%税费/不确定性余量 **$0.552**，低于本轮$3上限；非实际账单。现有200GiB SSD停机后持续约$0.01945/小时。费率来源 [Nebius官方](https://docs.nebius.com/compute/resources/pricing)。前轮失败启动费用单独保留，未混为本轮预算。

69项Python离线测试通过，执行卡语法/UTF-8检查通过，git diff --check通过，暂存区为空。未提交、推送、清理历史或公开部署。详见 actual-summary.json、verified-report.json、private-job/remote-evidence 和新run目录。
