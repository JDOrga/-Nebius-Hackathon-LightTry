> 最新实测状态（第九轮，2026-10-16）：已在真实GPU上通过公网443 mTLS健康、缺/错误客户端证书拒绝、错误server pin拒绝、合成字节往返。主动关闭本轮SSH转发后，直连健康、原合成blob下载和不存在任务查询仍通过；无生成请求、未换IP、未确认模型READY。使用轻量stdlib代理，未安装/验收Nginx。联测结束已STOPPED+空实例、释放防休眠、守护退出并撤销本轮配置；不是常驻在线服务。以下Nginx模板说明仍属备选未部署方案。

# 非 SSH GPU HTTPS：动态热点/VPN 的 mTLS 接线（未部署）

CPU -> GPU公网443(mTLS) -> Nginx stream TLS终止 -> 再加密TLS -> 容器私网9443。
来源IP可变化；不依赖固定IP白名单。只有持有本轮CPU客户端证书的连接才可进入代理。
公网只有加密入口；不暴露9080、Docker接口、SSH管理功能或模型管理接口。
Nebius API停机仍独立于SSH/模型通道；整台GPU/容器/网络故障可能同时影响两条数据通道。

## 部署前绑定
- 本轮确认的SESSION_ID、RESOURCE_ID、HOST_IDENTITY、GPU_CURRENT_IPV4和容器私网IP。
- 入口server证书必须有当前GPU公网IP SAN；CPU验证CA+证书SHA256 pin+主机名。
- 专用于本轮的CPU客户端CA/客户端证书，客户端证书只含clientAuth用途；CPU私钥留在CPU。
- 代理只部署CPU CA公证书（不要上传CPU私钥或CA签发私钥）；ssl_verify_client on不可取消。
- 上游worker保持私网TLS；proxy_ssl_verify on，专用worker CA，proxy_ssl_name localhost。
  入口server证书与内部worker证书可以不同，不将旧VM的证书或信任带入新会话。
- 证书/授权不超过本轮原窗口，停机后撤销配置；来源IP改变不续期。
- 公网443在真实Devlab上是否能开放仍需核实。不可用旧VM/IP或Compute一般文档替代验收。

## 本地代码和配置
`gpu_direct_https.render(None, GPU_CONTAINER_IP)` 生成mTLS Nginx stream块；旧CIDR入参拒绝。
需要nginx stream/stream_ssl模块及公网入口配置；本地只检查生成内容，尚未安装或执行nginx -t。
连接/握手超时、并发限制已放入模板；公网网络层DDoS仍需平台防护，mTLS不保证可用性。

可选binding.directWorkerFile默认只有 {"schemaVersion":1,"enabled":false}。
启用记录的准确字段：schemaVersion=1、enabled=true、sessionId、resourceId、hostIdentity、origin、
tokenFile、caFile、certificateSha256、clientCertificateFile、clientKeyFile。
origin=https://GPU_CURRENT_IPV4:443，所有证书/Token路径均在代码目录外的私有配置。
缺少客户端证书/私钥的旧启用记录会被拒绝，而不是降级为无客户端认证。
当前私有配置仍关闭，不要求提供CPU公网出口IP。

## 切换与验收
直连优先，SSH HTTPS备用；每次至多两次有界健康GET，绑定本轮session/resource/host。
热点换IP后可以重新建立TLS连接，但不自动重启GPU/模型、不重发失败POST/PUT、不延长预算。
先查原jobId；未知任务不能当成重新提交许可。模型只有真实READY才允许生成。
先验收正确客户端证书通过、缺证书/错误证书拒绝、错误server pin拒绝，再验收断SSH后直连可用。
最后用原任务状态确认没有重复推理。整个过程仍需下一次明确开机授权；本轮未部署、未开机。

## 无 Nginx 安装的轻量代理（本地验证，未部署）
`project/mtls_relay.py` 提供固定 worker 目标的有界 mTLS HTTP 代理：验证 CPU 证书，转发现有 GET/POST/PUT 路由，再通过校验 CA/主机名的 TLS 连接私网 worker。没有远端代码执行接口，不重试、不加载模型；原固定 deadline 自动结束监听。已验证真实本机 mTLS 健康和合成字节往返。第七轮在云端调配阶段由用户取消，未部署公网代理，公网 443 与断 SSH 验收均未执行。

## 已接入自动启动链（本地验证，自动版未实机验收）
可选私有 `directTLS={"enabled":true,"opensslExecutable":"ABSOLUTE_OPENSSL_PATH"}` 配合 `binding.directWorkerFile`。确认当前主机后，SSHBootstrap.deploy 在标准worker部署后自动调用 DirectBootstrap：每会话独立证书、固定来源无关的443代理、精确健康绑定通过后原子发布直连配置。失败保留attempt，不自动再次部署/启动模型；停止时撤销同一SID配置。CPU客户端私钥和签发CA私钥不发送至GPU。worker初始化/模型加载可能与代理配置并行，本版不声称阻止模型初始化直到代理READY。主机确认、30分钟等待、RUNNING独立窗口和预算保护不变。
