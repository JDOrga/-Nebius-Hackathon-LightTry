# 故障与恢复

- LOCAL_CONFIG_MISSING / LOCAL_AUTH_PATH_MISSING / LOGIN_REQUIRED：检查自己的本地配置、现有登录和钥匙路径。工具不自动登录、生成密钥或修改权限；不要贴出认证内容。
- UTC 请求失败：截止必须显式 UTC；PowerShell7 支持 DateKind String 时强制使用，否则使用 PS5 兼容解析。不要把日期转成本地时间再序列化。
- API_AUTH_OR_PERMISSION：停止捕获；API_TRANSIENT/API_TIMEOUT 只有限重试。连续三次监督失败、身份映射变化、多 VM、输出不完整、清理失败均不能放行 SSH。
- 主机信任变化：保留本次失败 run，重新核对资源、VM 和准确指纹；不得自动接受新 key、删除 known_hosts 或复制另一台电脑的 pin。
- 未完成传输/导出：保留 partial/failed 包，不把非零退出、截断或 SHA 不符当成功。采用新的独立目标目录或由操作者审核后保留旧文件，不能批量清理。
- inverse 不完整：新 run 重试，保留旧目录。forward 恢复仅在原五个 G-buffer、计划参数与尺寸核验后进行；已有 forward 目录不能覆盖。
- OOM：停止本次工作，保留日志。显式 offload 是现有上游选项，但耗时未承诺。截止不足即退出，不延长或重启收费资源。
- 停机验收失败：继续独立监督，STOPPED 且 instances=[] 才能签发释放收据；手动处理故障，不杀守护进程、不把 stop 提交收据当验收。

不会执行 git clean、历史重写、系统组件安装或认证修复。
