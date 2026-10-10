# 新网页双预设 GPU 验收：开机前

2026-10-10 16:21–16:24 北京时间。当前尚未授权本轮收费操作，未启动、上传或执行 GPU；没有提交、推送或部署。保留原工作区修改，HEAD 为 `e6fa4e4a2b72d3a1dc30f718b4a267c7153ce93f`。

只读 API：指定 `devlab-e00mt1pp6rph9z4qyv` 为 STOPPED、instances=[]；项目归属通过。只读 preflight 证实 gpu-l40s-a / 1gpu-16vcpu-64gb / 214748364800 bytes NETWORK_SSD，已有本机公钥匹配。开机前仍再次检查守护及资源状态。

历史 inverse 校验通过：键 `155868063db861b7513f9c78dd0161da123cf3542ee7b72620f6a83c01e318e5`，来源 task `6d541112fa164c099d9fc06c560b464d` / run `dc011af5186c492d8ffd2f6342e5c07f`；五通道尺寸、解码、哈希和同帧身份通过。同一原照重新预处理的 PNG 编码哈希为 `7acb5a4440bab934fafebb559ed4d3442f365988c4df1df55bdce3124404ba0b`，与原编码不同，但 RGB 像素和 inverse identity/key 相同，复用验证通过。权重历史引用通过，继续 historical_metadata、content_verified=false，没有全量权重扫描。

发现并补齐网页执行策略缺口：此前只有私有测速请求携带 requiredInverseReuse；现在显式本机配置可在 TaskStore 写入可执行请求前验证指定历史来源和 sunny、sunrise 的精确顺序，并写入同一 request。失败时拒绝，未上传/执行，无 inverse 冷启动 fallback。既有无限制配置行为保留。修改 executor.py、jobs.py，新增离线策略回归；没有新增产品界面。

离线回归：新策略 2/2、test_inference 33/33、test_product_batch 14/14，通过；git diff --check 无错误。没有重跑未改的 Node、GPU、守护测试矩阵。初次新测试因未关闭 TaskStore 导致 Windows 临时锁清理失败，补 store.close 后通过。

本机 Codex 内置浏览器 http://127.0.0.1:8774 已通过照片选择器载入同一原照，并勾选 sunny、sunrise，street 未勾选，生成按钮默认关闭。重新载入文件执行既有 UPLOAD 路径，清空当前页面任务引用，历史文件保留；无需删除结果或改任务状态。截图 `.local/web-batch-20261010/prestart-web.jpg` 仅为待提交状态，绝非生成成功。

已本地调用真实 prepare_request/build_bundle，冻结检查包 640027 bytes；包只有预处理输入、历史五通道/来源标记、权重引用及白名单代码，无权重/原照。该检查任务没有提交，不作为本轮网页任务。实际网页 POST 将创建新 task/nonce，获批后的守护创建新 run；实际 driver 按该网页 request 打包，在开机前已核对代码路径。不得把本地检查包作为旧 task 绑定使用。

产品路径：网页一次 POST → TaskStore 一次 executor.submit → driver 一次 remote launch → 同一 forward 对象顺序执行 → 整批 export/download → extract_stage_evidence → TaskStore._merge_batch/evidence_items → 每项校验自动展示。无需历史登记 CLI 或手改 task 成功。事件与阶段来源用于证明本轮生成，不仅比较 JPEG 哈希。

官方现价 https://docs.nebius.com/compute/resources/pricing ：L40S GPU $1.35/h、保守 Intel CPU $0.012/vCPU/h、RAM $0.0032/GiB/h、NETWORK_SSD $0.071/GiB/730h，税前总计约 $1.7663/h（该 AMD 平台 CPU 公开价更低）。10–15 分钟约 $0.29–0.44；覆盖启动/停机过渡按 60 分钟乘 1.5 余量约 $2.65。拟申请含税上限 $3，实际账户税率、折扣和账单尚未核实。停止后现有存储持续约 $0.01945/h 税前，不删除资源。

待本轮一次明确批准：现有 Devlab 启动一次、含税上限 $3；允许上传必要预处理输入、五个历史 G-buffer、来源/权重引用和白名单代码；完成/失败由守护停机。旧授权不继承。守护 arm 固定绝对 +60 分钟（更早截止优先），启动等待有界 1800 秒，独立 RUNNING 起 +18 停止新长操作、+25 触发停机、+27 核实目标，修复不得重置。需本轮准确 VM/IP/指纹信任核对，不能复用旧主机确认。

本轮实际网页提交、GPU 初始化计数、等待时间、输出及下载校验、桌面/窄屏结果截图、刷新/关闭恢复、独立停机/守护释放均未测。批准后沿原范围执行一次；通过前不整理成已验收候选基线。
