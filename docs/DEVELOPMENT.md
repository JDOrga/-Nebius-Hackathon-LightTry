# 本地开发与维护

## 入口

仓库根目录运行 `python -X utf8 -B start.py`；`npm start` 转接同一入口。路径配置见 `config/studio.example.json`，实际配置放 `.local/studio.json` 并保持 Git 忽略。配置只接受路径，不能在其中开启收费服务或重置账本。

已有环境的路径分别填 `python` 与 `offline_python`。统一自检用 `offline_python` 做基础工具回归，用 `python` 做产品 CPU 回归；也可显式传 `--product-python`，不会安装或下载包。

## 回归范围

`python -X utf8 -B scripts/selftest.py` 自动发现根测试、HDR 参考测试及产品 Python 测试；`npm test` 是 Node 前端回归。产品单独回归：`python -X utf8 -B -m unittest discover -s project/tests -p 'test_*.py' -v`。有界测试、CPU 替身及合成图不能替代实机视觉验收。需要素材的检查须显式配置 `LIGHTTRY_DEMO_ASSETS`；不为测试启动 VM、收费模型或下载权重。

## 防止再次堆积

1. 当前说明更新既有 README/架构/规范，不每轮新建交付、收尾和“final”文档。
2. 历史执行证据保留一次原记录；新增事实追加到该运行的既有验证账本/状态，不复制整套源码。
3. 实验代码若正式复用，合并到功能模块；不再新建 next/v2/final 产品树。
4. 当前机器路径由本地配置传入；新实验包冻结后只读，源代码变化必须重新准备并重新授权，不能篡改旧包。
5. 清理只删除确认无引用的缓存/空目录；原始任务、素材、密钥、账本、失败和云停机证据不得顺手删除。
6. 改动保留补丁与可执行回退，证据放项目外的同一个事务目录；不要把验证副本再次堆进产品源码。

## 历史链接

归档保留原文和哈希，内部旧相对链接可能不再适用。通过 `docs/history/README.md` 与其清单查找旧路径对应的新位置，不把旧日期/旧 HEAD/旧端口当当前状态。
