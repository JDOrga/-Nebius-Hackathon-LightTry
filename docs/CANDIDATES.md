# 完整候选入库清单

首次提交仅使用此白名单。真实配置、认证、运行记录与临时诊断不在此列表。

## (root)

- .gitattributes
- .gitignore
- README.md

## cloud

- cloud/Capture-TeaHost.ps1
- cloud/Common.ps1
- cloud/Confirm-RunningStopped.ps1
- cloud/Confirm-TeaHost.ps1
- cloud/HostCapture.Native.cs
- cloud/HostCapture.Native.ps1
- cloud/Invoke-Cloud.ps1
- cloud/Invoke-ScaleRemote.ps1
- cloud/RequestJson.ps1
- cloud/Start-TeaRunningGuard.ps1
- cloud/Status.ps1
- cloud/TeaRunningGuard.ps1
- cloud/Wait-CaptureTeaHost.ps1
- cloud/cli_bridge.py
- cloud/experiment_vm_bridge.py
- cloud/export_results.py
- cloud/host_capture_api.py
- cloud/inspect_preview.py
- cloud/install_bundle.py
- cloud/launch_preview.py
- cloud/live_session_running.py
- cloud/remote_probe.py

## config

- config/local.example.json

## docs

- docs/ARCHITECTURE.md
- docs/CANDIDATES.md
- docs/CLOUD.md
- docs/DEPENDENCIES.md
- docs/MIGRATION.md
- docs/THIRD_PARTY.md
- docs/TROUBLESHOOTING.md
- docs/VALIDATION.md

## manifests

- manifests/assets.json
- manifests/extraction.json
- manifests/git-allowlist.txt
- manifests/patch_manifest.json
- manifests/runtime-baseline.json
- manifests/upstream.json
- manifests/weights_manifest.json

## patches

- patches/replace_hdr_sampling.patch

## prototype

- prototype/env_sampling.py
- prototype/numpy_reference.py
- prototype/test_golden_cases.py
- prototype/test_math_numpy.py
- prototype/test_patch_static.py
- prototype/test_torch_integration.py
- prototype/test_upstream_integration.py
- prototype/upstream_hdr_smoke.py

## requirements

- requirements/inference-extra.txt
- requirements/inference-upstream.txt
- requirements/offline.txt

## scripts

- scripts/apply_hdr_patch.py
- scripts/audit_repository.py
- scripts/build_bundle.py
- scripts/check_official_hdrs.py
- scripts/inference_plan.py
- scripts/local_config.py
- scripts/preflight.py
- scripts/run_experiment.py
- scripts/selftest.py
- scripts/validate_outputs.py
- scripts/weights.py

## tests

- tests/test_absolute_deadline.py
- tests/test_api_worker.py
- tests/test_budget.py
- tests/test_cli_read_retry.py
- tests/test_host_capture.py
- tests/test_native_failure_metadata.py
- tests/test_output_complete.py
- tests/test_portability.py
- tests/test_preparation.py
- tests/test_running_guard.py
- tests/test_utc_precision.py

## third_party

- third_party/Cosmos-LICENSE
