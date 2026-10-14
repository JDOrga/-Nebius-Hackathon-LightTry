# LightTry 可演示候选基线（2026-10-10）

这是WJX上的已验收候选，不是发布版本、Git标签或已推送版本。HEAD `93c23724ec85addfcd2f5bad971aef329bd6d502` / main 加当前未提交差异组成候选：主机捕获API诊断/启动过渡修复、对应回归、前后两轮验收报告和本说明。Git暂存区保持空；原修改保留，没有提交、打标签、推送或部署。开始/收尾状态与diff在 `.local/web-batch-20261010-retry2/`，候选文件哈希清单为candidate-files.json。

## 最短启动

WJX已有素材和Pillow的环境，在 `C:\Project\Nebius` 运行：

```powershell
.local/review-venv/Scripts/python.exe -X utf8 -B project/server.py --port 8774
```

打开 [本轮已验收任务](http://127.0.0.1:8774/?task=e7ca7776b5094aba8ea1008c8421f456) 或首页。只绑定127.0.0.1，Ctrl+C停止；这条命令不读推理配置，不启动云机、不上传、不生成。已存结果可查看/下载，约2026-10-11 16:49:09.966后正常过期，证据和已下载文件仍保留；不改时间或状态来伪装可用。

其他本机样例演示只需Python3.11和独立本地素材包：

```powershell
python -X utf8 -B project/install_demo_assets.py "<已有素材包绝对路径>"
python -X utf8 -B project/server.py
```

已有demo-assets无需重复安装。打开 http://127.0.0.1:8765 ，无需npm install/build、认证、WSL、SSH或GPU。单独素材迁移步骤和校验见 LOCAL_DEMO_MIGRATION.md；其旧HEAD和旧包名是历史记录，本候选代码范围以本文件为准。未重新打包、传输或验收WJC迁移。

## 样例与真实模式

样例模式展示四组历史实测JPEG及来源，切灯光/比较/下载在本机完成，不代表当场GPU生成。载入新照片默认仅本机预览，不借用样例结果。

真实模式需要本机既有Pillow、用户的新收费窗口授权、现有Devlab、独立守护、固定截止和当前主机信任，以及显式 `--inference-config "<本轮配置>"`。配置模板 inference.example.json；真实机器配置、凭证、私钥和pin不属于候选。每轮建立新run，一次网页POST建立新task/nonce；指定同图历史inverse复用，失败拒绝，historical_metadata明确不验证本轮权重内容。候选不提供自动开机，不复制或重用已结束run授权配置。

已验证的本轮真实路径是 sunny、sunrise 一批，只创建一个forward对象、顺序生成两项。整批结束后取回校验发布，刷新/关闭恢复同任务；下载原JPEG和按记录裁剪的PNG。选第三灯光仅查看，不冒用已有结果或自动提交；新的真实灯光需要下一轮明确授权，本轮不追加。执行取消未支持，多用户/常驻模型/流式图片未验收或未实现。

## 成本与保真度

本轮网页等待471.211秒，第二预设执行端增量5.903秒；两者不是已有结果切换速度。模型冷加载、准备、传输及整批发布决定真实用户等待，不承诺秒切。模型退出后的新批次仍可能重新加载forward。

本轮保守估计$0.4407税前，含过渡/50%不确定性余量约$0.6806；实际账单未核实，不能据此承诺未来同价。原授权$3只用于该轮一次启动，不能继承。守护沿RUNNING+18/+25/+27与更早绝对截止；现有停止资源存储仍约$0.01945/h税前收费。

这是有限主体保真度的氛围、色温、明暗预览，非物理精确渲染；文字、纹理、材质与局部形状可能变化，不能直接替代商品实拍。1280×704模型画布保留；原照区域只是按记录裁剪，PNG不增加有损编码，也不恢复JPEG已经丢失的信息。historical_metadata只能检查历史引用与现有文件存在/大小，不能检测同大小内容变化或bitrot，本轮content_verified=false。

## 候选文件范围

只整理清单和文档，不自行复制整个工作区或生成新发布包。

|范围|文件|
|---|---|
|产品启动/素材工具|project/README.md、server.py、build_catalog.py、install_demo_assets.py、package.json、.gitignore、inference.example.json|
|前端|project/web/index.html、app.js、state.js、sources.js、styles.css、about.html、favicon.svg|
|元数据|project/data/catalog.json、demo-package.json|
|真实推理代码|project/inference/内的Python源文件；脚本打包白名单、prototype/env_sampling.py、patches/replace_hdr_sampling.patch、必要manifests及Cosmos-LICENSE|
|云执行/守护|现有cloud内的PowerShell/Python/C#源文件，尤其本次Capture-TeaHost.ps1、host_capture_api.py；config/local.example.json|
|回归|project/tests源文件及tests/test_api_worker.py、test_host_capture.py、test_host_transition.py、test_host_transition_capture.py|
|文档|产品README及project/docs内说明，尤其本轮GPU验收、主机修复和本候选说明；已有依赖/许可/迁移边界保留|

实际候选清单枚举为candidate-files.json，不包含真实config/local.json、inference.local.json、auth、私钥、known_hosts、guard收据、cloud-runs、.tasks、.inverse-cache、.local、权重、HDR、虚拟环境、运行日志和媒体本体。demo-assets、照片和结果仅本地保留；公开分发结果及独立HDR许可缺口仍存在，不以本次技术验收替代许可核实。本候选没有宣布发布。

## 本轮收尾补充（2026-10-10）

上文为此前验收时的基线。本轮已保存独立白蓝杯历史样例，不再以有期限的任务链接作为长期演示入口。新版素材与相对路径启动方式、实际隔离验证、公开候选排除项和建议分组以 [本地候选交付](DEMO_HANDOFF_20261010.md) 为准。原包和任务证据保留，主机捕获修改未被遗漏；没有提交、标签、推送、Release 或部署。
