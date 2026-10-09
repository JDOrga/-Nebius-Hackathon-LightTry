# 本轮交付边界核对（2026-10-09）

## 当前仓库与独立本地交付

实际 origin 为 `https://github.com/JVerdL/-Nebius-Hackathon-LightTry`，main/HEAD 为 `71fe251262f23c04105562f9e7d667cc46c102bb`，与用户报告一致。本轮开始已有上一轮未提交修改（DEVELOPMENT、README、状态测试、web 下 app/about/index/state/styles，及未跟踪的本文档），均保留。没有切分支、reset、clean、暂存、提交、推送或改远程/全局身份。

此前 catalog/server 的历史目录运行依赖已移除：默认独立 `project/demo-assets/`，可用 `--assets-dir` / `LIGHTTRY_DEMO_ASSETS`。相对路径从 project 解析；源目录只保留为审计引用，运行和测试不读取历史文件。只用 Python 3.11 标准库，不需要登录、SSH、云机、GPU 或模型。缺素材或哈希不符会报安装指引，不使用替代图片。

20 图片按原字节复制，逐文件 SHA256 与原照/输入记录、历史 flat JPEG/canonical frame 核对：4 原照、4 实际输入、12 全画布历史结果。独立包附精简来源映射、原署名文件与本地范围说明；不附 HDR、G-buffer、中间文件或日志。来源摘录去掉个人绝对路径，保留原记录哈希、作者/许可/处理信息和历史最终验收失败事实。历史目录没有删除、移动或重写。

素材位于被忽略的 `project/demo-assets/`；ZIP 位于被忽略的 `.local/demo-delivery/lighttry-demo-assets-20261009.zip`，14,286,952 字节，SHA256 `ed34c7ea71740ed2176d2ba18bc88d1f6da51baed6c46be962d93bc9e88922df`；解包 14,422,082 字节。另准备候选代码包，不含图片或任何真实机器配置。许可不足的结果及整个素材包只本地保留，详情见 [分发核对](DEMO_ASSET_LICENSES.md)。

已在含空格的新临时目录做“候选交付目录验收”：只含拟交付 project 代码与安装后的最小素材，没有 controlled-tests 或真实机器配置。实际缺素材提示、校验导入、启动、桌面/390×844手机各4×3×2映射与比較、未连接照片、样例下载和哈希均通过；Python14项、Node8项通过。验收证据在被忽略的 `project/qa/migration-20261009/`。

本轮代码尚未提交，不能宣称 GitHub 当前 HEAD 已支持此次独立启动或已通过干净克隆验收。**WJC 实机待验收**，本轮没有操作该电脑，也未向其传输任何包。接手步骤见 [本地演示迁移](LOCAL_DEMO_MIGRATION.md)。

## HDR 来源与许可记录

核对已有 `manifests/assets.json`、`evidence/example_assets.json`、`upstream/README.md`、本地三个 HDR 文件及头部。下载地址均固定在上游 commit `0f3e2dc435032ecbad654c2fc2153df85384b138` 的 `asset/examples/hdri_examples/`，文件大小和 SHA-256 与清单一致。

|文件|字节数|SHA-256|独立作者/素材许可|
|---|---:|---|---|
|sunny_vondelpark_2k.hdr|7594746|581d9338941a7c387aaa99f331b956473aa80559ae767c012034ef0fe30bb4d5|待核实|
|pink_sunrise_2k.hdr|6622693|7f8a5cce3b934313337a89c9df0418e5fc82e98856a2accecc9d2eb1204586a2|待核实|
|street_lamp_2k.hdr|7097695|012584d8e6c7c9050ce4dbf43654443481c39b31886183c78c5d1d2f1634652b|待核实|

现有记录给出来源 URL、大小、Git blob、SHA-256，未给出每个 HDR 独立作者和授权依据；文件头部也没有补充该依据。上游 README 分别声明代码 Apache-2.0 与模型 NVIDIA Open Model License，不能把这些声明作为三个 HDR 独立许可的证明。没有从文件名猜测作者、素材站或 CC0。

说明页已补齐三项具体固定版本来源链接，独立作者与许可逐项标为“待核实”。本地演示完成不代表已经具备公开分发素材/部署的条件。本轮只读核对原照来源页与 NVIDIA 官方模型输出条款，没有补齐 HDR 独立许可，没有公开发布。
