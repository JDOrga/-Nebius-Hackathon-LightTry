# 新网页双预设验收：主机验证失败，已停机

本轮获得用户一次明确批准，现有 Devlab 启动一次、含税上限 $3、必要上传和守护停机。未继承旧费用授权。本验收代理没有执行提交、推送或公开部署，保留现有文件。开机前记录 HEAD：`e6fa4e4a2b72d3a1dc30f718b4a267c7153ce93f`；收尾观察 HEAD 已变为 `93c23724ec85addfcd2f5bad971aef329bd6d502`（Add multi-preset batch inference and result delivery）。该提交不是本验收代理发起，未回退或改写。收尾未提交差异为本报告及 PRODUCT_BATCH_ACCEPTANCE_20261010.md 的后续说明，暂存区空。

## 结论与范围

**本轮验收未通过。** 主机捕获在网页点击生成和任何上传之前失败。错误 `VM_CHANGED_DURING_VALIDATION` 来自 `cloud/host_capture_api.py`：同一次定位流程的前后独立 Devlab API 读数，其 state 或 instances 列表不同。列表比较包含 VM ID、状态、公私 IP。失败快照没有存储，因此不能断言确实更换 VM ID，也不能确定只是启动状态过渡。没有绕过该校验、创建主机信任、连接 SSH、上传、发起模型或再次开机。

新 run：`cada754c3bb143d9bd8743a59796485d`。已观察 VM：`computeinstance-e00h9f95pfgmqr1r36`，用户 nebius。捕获未完成，无可信本轮 host candidate/trust。独立 API 先成功验证资源、项目归属和公钥映射，后续一致性验证失败。扫描到的公开主机密钥保留为未信任证据，未写入 known_hosts。

|项目|本轮结果|
|---|---|
|同一瓷杯照片、历史五通道及来源|开机前通过，未重算 inverse|
|权重 historical_metadata|本地引用通过；content_verified=false；无全量扫描|
|sunny、sunrise 网页待选批次|通过，两项勾选，street 未勾选|
|网页点击提交、新 task/nonce|未执行；没有新产品 task/nonce|
|实例启动请求|恰好一次，已有实例，无资源扩容|
|主机身份/信任|失败，已保护性停机|
|inverse 执行|实际 0 次|
|forward 初始化|实际 0 次，要求的 1 次未达到|
|同对象两个预设完成|未测，完成项 0|
|输出归属、解码/尺寸/非恒定/传输哈希|未测，无本轮输出|
|切换、刷新/关闭恢复、滑杆/并排/区域|本轮结果未测；不继承历史验收结论|
|两份 JPEG 字节及两份裁剪 PNG 像素|未测，没有本轮下载|
|第三灯光不得冒用或自动提交|本轮未提交任何灯光；真实结果状态未测|
|独立 STOPPED/instances=[]、守护退出、防休眠释放|通过|

网页点击到结果展示等待和第二预设增量耗时均为 null，没有有效测量值；不把启动等待、停机等待或页面切换误称为生成/切灯光速度。历史结果和本地预检查包未被用作本轮 GPU 成功证据。

## 固定窗口与实际停机

以下为北京时间：

- 16:24:37.436 守护 arm，绝对截止固定为 17:24:37.385；启动等待上限 1800 秒。
- 16:24:56.601 唯一启动请求开始，返回 accepted=true、restart_attempts=1。
- 16:26:19.557 独立 RUNNING 锚点。+18 截止 16:44:19.557，+25 停机触发 16:51:19.557，+27 目标 16:53:19.557；未重置。
- 16:26:40.044 主机捕获失败，同 run 写保护性 complete.json。
- 16:26:41.877 守护发出停机，16:26:45.357 请求被接受。
- 首次独立确认过程三次仍见 STOPPING，未当作已停止；保留守护并按原确认工具再次请求保护性 stop，没有再次 launch。
- 16:27:33.659 独立 API 确认 STOPPED、instances=[]。
- 16:27:36.930 守护最终 heartbeat：stopped_verified=true、sleep_held=false；16:27:37.225 核对守护 PID 28664 已退出并记录 finalization。

已关闭本轮授权本地服务进程，8774 恢复默认真实推理关闭的本地服务。批准配置作为证据保留；原 run 已 complete，不可用来再次执行。

## 费用与证据

公开价保守组合含现有存储约 $1.7663/h 税前。唯一启动请求到独立 STOPPED 为 157.058 秒，按此全过程保守按全价估计约 **$0.0771 税前**；arm 到守护退出验证约 179.789 秒，乘 50% 税费/不确定性余量约 **$0.1323**。这不是账单，实际计费起止、税额、账户折扣均未核实。既有存储停止后仍约 $0.01945/h 税前；没有删除资源。

证据在 `.local/web-batch-20261010/final-verification.json` 和 `cloud-runs/cada754c3bb143d9bd8743a59796485d/`。关键文件：startup.json、restart-attempt.json、running-confirmation.json、timing.json、host-capture-events.jsonl、host-capture-error.json、complete.json、stop-attempt-*.json、independent-stopped-release.json、heartbeat.json、benchmark-finalization.json。

桌面和390×844截图为收尾的**原照/未生成状态**，不能交付不存在的本轮结果截图：

![桌面：本轮未生成](C:/Project/Nebius/.local/web-batch-20261010/final-desktop-not-generated.jpg)

![窄屏：本轮未生成](C:/Project/Nebius/.local/web-batch-20261010/final-narrow-not-generated.jpg)

## 本地改动

开机前补齐本机 operator 配置的指定历史 inverse 和精确双预设约束：`project/inference/executor.py`、`project/inference/jobs.py`，新增 `project/tests/test_web_reuse_policy.py`。策略失败在可执行 request 写入之前拒绝，不上传/执行；既有无限制配置行为保持。对应离线回归 49/49 通过，前一轮已有 Node 等未变化部分未重复跑。运行中没有修模型、守护或信任逻辑，没有新测试矩阵。

本轮不满足通过条件，因此不整理或宣布“可演示候选基线”。本轮到此结束，不自动收费重试。下一次若安排验收，需要新的明确费用/启动授权；本报告仅列具体缺口，不自动调查、修改主机校验或新增研究。
