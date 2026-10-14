> 2026-10-12 更新：旧 project/web 页面与 state/plan 专属测试已删除；正式前端为 project/next/web，旧快照和下文清单仅为历史记录。当前测试使用 node --test project/tests/*.test.js。

# 本轮候选公开文件与本地材料

2026-10-11 本地收尾 R2：启动文字适配器还需新增 `project/language_contract.py`，不能只复制 `language.py`。新增候选冻结/离线验收文件见 `tests/freeze_language_candidate.py`、`run_candidate_offline.py`、`acceptance_checks.py`、`test_language_candidate.py`、`language_regressions.json`、`language_browser_cases.json`；当前配置及文件哈希见 [LANGUAGE_CANDIDATE_20261011_R2.json](LANGUAGE_CANDIDATE_20261011_R2.json)，交付与复现见 [本地收尾](LANGUAGE_LOCAL_CLOSEOUT_20261011.md)，收费范围见 [新的真实复验计划](LANGUAGE_NEXT_ACCEPTANCE_20261011.md)。早期无 R2 后缀的本地冻结记录为历史；本次真实请求为 0，不代表真实复验通过。

2026-10-11 真实文字增量还包括 `tests/run_language_probe.py`、`diagnose_language_protocol.py`、`finish_language_acceptance.py`、对应`test_language_acceptance_runner.py`/`test_language_protocol.py`/`test_language_finish.py`，以及`LANGUAGE_REAL_ACCEPTANCE_20261011.md`、`LANGUAGE_PROTOCOL_INVESTIGATION_20261011.md`、`LANGUAGE_REAL_SUMMARY_20261011.md`。paid入口必须显式执行，旧报告存在即禁止重复；本轮40次预算已到，不继续运行。真实脱敏用量/模型方案/复核记录在忽略的`project/qa/language-real-20261011`，不包含Key或推理正文。

2026-10-10 文字选光候选增量：`project/language.py`、`language.example.json`、`web/plan.js`、`tests/test_language.py`、`tests/plan.test.js`、`tests/language_cases.json`、`tests/serve_language_fixture.py` 及两份 `LANGUAGE_*_20261010.md`。调整 server 和既有 app/state/sources/index/styles；README/DEVELOPMENT/接口/架构文档更新。无新增依赖，测试入口不能由产品参数选用。截图/合成任务/日志均在忽略的 `project/qa/language-20261010/`；没有复制密钥、HDR、云任务证据或历史结果进入 Git。下列旧列表保留为上一轮历史范围。

本轮没有暂存、提交或推送。候选代码包只复制下列 `project/` 文件，不复制整个工作区。它适合后续入库审核；自有代码未因第三方代码许可证自动取得新的总体许可。

- `project/.gitignore`、`README.md`、`DEVELOPMENT.md`、`package.json`
- `project/server.py`、`install_demo_assets.py`、`build_catalog.py`
- `project/data/catalog.json`、`data/demo-package.json`（图片/来源校验元数据，无图片本体）
- `project/web/index.html`、`about.html`、`app.js`、`state.js`、`sources.js`、`styles.css`、`favicon.svg`
- `project/tests/test_catalog.py`、`test_install.py`、`state.test.js`
- `project/docs/INFERENCE_INTERFACE.md`、`DELIVERY_BOUNDARIES.md`、`LOCAL_DEMO_MIGRATION.md`、`DEMO_ASSET_LICENSES.md`、`DELIVERY_FILES.md`

仓库级必要更新：根 `.gitignore` 补充独立素材/机器配置排除；`README.md`、`docs/MIGRATION.md` 与 `docs/CANDIDATES.md` 区分普通本地演示与既有云工具迁移，并链接当前交付清单。旧连接/停机脚本和配置模板未改动。

只本地保留、受忽略规则排除：

- `project/demo-assets/`：20 张真实图片 + `source-records.json`、`ATTRIBUTION.txt`、`LOCAL_ONLY.md`。原照与输入有已记录的许可依据；12 结果公开分发仍待核实，全包没有纳入媒体公开候选。
- `.local/demo-delivery/`：本轮候选代码 ZIP、素材 ZIP、准备脚本与交付校验收据；本轮不执行任何包的传输。
- `project/qa/migration-20261009/`：候选文件大小/哈希、复制核对、历史保留核对、隔离和浏览器验收、截图/测试日志。
- 历史实验、原始证据、HDR、模型权重、缓存、虚拟环境、诊断包、运行日志，以及所有真实机器配置、私钥、认证、known_hosts、主机批准和守护状态。没有为清理移走、删除或重写历史文件。

忽略规则不是素材许可证。外部素材目录应放在仓库外；切勿把素材复制到其他 Git 可见目录。审计只读取 Git 可见候选文本，不读取认证/私钥内容；哈希保留核对只针对本次历史实验文件，避开认证文件。候选扫描是启发式检查，不能证明任意敏感信息绝对不存在。
