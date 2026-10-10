# 主机捕获的小范围本地修复

针对上轮 `VM_CHANGED_DURING_VALIDATION`，仅修改主机捕获 API worker 与 PowerShell 捕获入口，保留既有信任确认、SSH pin、归属/公钥校验和计时。没有启动、上传、安装依赖、提交、推送或部署；上轮失败证据不改写。

每次已取得前后两份 Devlab API 数据的校验，在 `host-capture-events.jsonl` 对应 `api_locate/end/details.validation_reads` 保存前后必要字段、classification 和 differences。字段包括 Devlab/项目 ID、镜像、workspace、状态、实例 ID、公私 IP、实例和底层 VM 状态、公钥绑定是否通过。每项差异含 field/before/after；第二份归属校验失败仍保留必要快照及 validation_error。只保存白名单，不保存原始 CLI 输出、认证、完整密钥或 cloud-init。

身份变化（VM ID、地址、镜像、workspace、归属或实例数量）与启动状态变化分开。只有唯一同一 VM 且身份、公钥绑定完全相同，差异只在 STARTING/PROVISIONING/IMAGE_PULLING/RUNNING 状态集合内，才返回可恢复的 STARTUP_STATE_TRANSITION。STOPPING/STOPPED、未知状态、身份变化、公钥/归属错误仍硬失败。状态重读不会创建主机信任或进行 SSH。

捕获入口收到过渡后锁住第一次已经完整验证的 VM/IP/用户/镜像，再沿既有 ready/capture 循环重新读取。每次调用重新检查 profile、项目归属、DevLab 归属、VM 归属、IP、公钥到用户绑定及前后快照一致性。只有完整成功后才进入扫描/候选发布；扫描后过渡会丢弃本次候选，完整重校验后重新扫描。第二个快照也重新调用既有 connection_target 校验。

不重新启动，不延长或重置 t0。沿用原 60 次 readiness 读取、12 次捕获尝试、t0+5 分钟 readiness/t0+6 分钟捕获及更早 work/停机预留截止；原 API 单调用时限、三次通信失败保护和 RUNNING 18/25/27 安排保持。不能确认同一实例时不认定是可恢复状态变化。已有 Confirm-TeaHost 和传输工具的主机信任检查保持不变，不能把扫描成功当作独立信任。

离线验证包含真实 Python worker/bridge 的合成 API 前后变化和真实 PowerShell 5.1/本地合成扫描器。对应回归 **45/45 通过**：API worker 12、原捕获及两项过渡回归25、变化分类5、过渡现场入口3；git diff --check通过。覆盖精确状态差异、同 VM 恢复、VM/地址/镜像/归属/公钥错误、STOPPING/STOPPED、白名单诊断、过渡后的身份锁、扫描后过渡重校验、连续过渡读取耗尽及原 timing.json 字节不变。全部测试不调用云 API、SSH或收费模型。验证记录与本次代码哈希位于 `.local/host-validation-fix-20261010/verification.json`，已有测试日志复制保留于同目录，没有重跑未变化的产品/GPU测试矩阵。

本地修复完成后，重新只读确认现有 Devlab STOPPED、instances=[]。本轮尚无新收费授权；原 $3 授权已用于上轮一次启动，不继承。下一次新网页 sunny/sunrise GPU 验收仍需新一轮一次启动、含税 $3、指定输入/历史五通道/来源/白名单代码上传和守护停机授权，再创建新 run/task/nonce。当前公开保守费率依据同会话已核对的官方定价：约 $1.7663/h 税前，10–15 分钟约 $0.29–0.44；覆盖启动及停机过渡按60分钟加50%余量约 $2.65。实际账单和税率仍未核实。
