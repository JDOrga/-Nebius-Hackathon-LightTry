# LightTry 光照方案工作台（候选版）

原固定预设应用完整保留；新增入口是 `project/next/server.py`。不提交、不推送，不创建评委仓库。普通启动不读取 Key、不上传照片、不启动 GPU。

## 在当前工作目录启动

```powershell
Set-Location C:\Project\Nebius
python -X utf8 -B project/next/server.py --assets-dir .local/demo-candidate-20261010/demo-assets --evidence-config .local/lighttry-development-20261011/workbench-evidence.local.json --tasks-dir .local/lighttry-development-20261011/workbench-tasks
```

打开 http://127.0.0.1:8785 。Python 3.11 + Pillow；普通服务不需要 torch、Node 或新增账号。当前已有独立 CPU 测试环境可代替 `python`：`.local/lighttry-development-20261011/cpu-venv/Scripts/python.exe`。不安装到系统环境。

省略 `--evidence-config` 时新参数关闭，仍可浏览三个历史固定环境。不能把结果图片路径直接塞进正式任务回执；独立实验和在线生成有不同来源标记。

### 明确启用文字服务（GPU 仍关闭）

在本机私下设置 `LIGHTTRY_KEY_FILE` 为既有 Key 文件路径，再在上述命令末尾加：

```powershell
--language-key-file $env:LIGHTTRY_KEY_FILE --language-ledger .local/lighttry-development-20261011/nemotron-new-ledger.json --language-max-calls 12 --language-budget 0.20
```

程序直接读文件；浏览器、公开候选、记录、模型上下文都不接收 Key。既有账本只能续记，不能重置；12 次含修复，独立于旧文字验收账本。真实模型可能失败/超时；最多一次修复，共享60秒，未知费用保留预留，不假定超时取消供应商计算。

### 在线 Cosmos

`--inference-config <本机新的受守护配置>` 才启用单方案提交。旧窗口、已完成守护、已停止 VM 均拒绝；应用不启动/重启 VM。参数适配器已离线检查，**尚未经过新工作台的真实 GPU 联合链路验收**，不得把独立实验图宣称为网页刚生成。当前候选默认关闭此路径；不要为界面讨论、人工看图而开着 GPU。

沿用已有 `cloud/Start-TeaRunningGuard.ps1` 与当前 VM/API/公钥/主机信任验证；完成取回立即请求停止并独立核实 STOPPED/instances=[]。生产适配器仍保留官方 commit/blob/patch/HDR/权重/inverse 校验，没有放松源码准入。请求最多1个缺失方案；完成后不能复用同一已终结的付费窗口。严格 inverse key 不包含 forward 灯光参数，跨照片、预处理/模型版本不同不能复用。

## 手动/语言流程

1. 选来源明确素材或本机照片；主预览旁只有一套编辑参照。
2. 修改产生新版本，另存变体产生新 planId；旧图归原版本。
3. 选择两方案对照/原图对照，完整画布或无调色的原照片区域，缩放与拖动。
4. 文字只提数据建议；先确认应用，再单独确认生成。已有有效匹配结果不再算。
5. 本机保存方案/任务引用；刷新先查原 requestId 和任务状态。未确认提交保存原照片 SHA，重新载入同一文件才可沿用身份重试，不自动执行。
6. 在另一照片复用参数会新建方案并绑定新 inputId；不带入旧 inverse 或旧结果。JPEG 下载是实际原字节，区域 PNG 是按记录 validRegion 无损裁出。

浏览器 localStorage 最多200版本；不是账号/协作服务，不上传库。当前查看身份显示 planId/v；文字上下文包含参数、inputId、recipeKey、结果 SHA 身份和最多3条参数修改历史，不包含图片。

## 文件分工

- `project/lighting.py`：规范化、recipeKey、版本与历史兼容描述。
- `project/next/store.py`：原 TaskStore 上的身份/幂等/参数回执验证。
- `project/next/runtime/`：单方案受守护 worker/entry/driver；不是换模型。
- `project/next/language.py`：普通服务 schema、范围/组合、文字安全/能力声明校验；没有测试专属 response_guard。
- `project/experiments/`、`scripts/*controls*`：独立实验适配、预备、CPU 检查、结果取回与分析。
- `project/docs/LIGHTING_SCHEME_V1.md`、`LIGHTTRY_DELIVERY_20261011.md`：身份/迁移、证据和剩余限制。

## 回归

```powershell
$env:PYTHONUTF8='1'
$env:LIGHTTRY_DEMO_ASSETS=(Resolve-Path .local/demo-candidate-20261010/demo-assets).Path
python -m unittest discover -s project/tests -p 'test_*.py'
node --test project/tests/*.test.js
```

实验/入口 CPU 测试需要独立环境中的 torch2.6.0+cpu、numpy/Pillow；替身测试都明确标注 OFFLINE/SYNTHETIC，不能当真实 Cosmos/Nemotron。
