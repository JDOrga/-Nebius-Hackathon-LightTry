"""Read-only cloud/container preflight. No install, credentials, or lifecycle."""
import argparse
import builtins
import hashlib
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

from weights import plan

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--repo", type=Path, required=True)
    p.add_argument("--checkpoint-dir", type=Path, required=True)
    p.add_argument("--cuda-home", type=Path)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    report = {"python": sys.version, "executable": sys.executable, "prefix": sys.prefix,
              "platform": platform.platform(), "cwd": str(Path.cwd()), "errors": []}
    if os.name != "posix" or sys.version_info[:2] != (3, 10):
        report["errors"].append("Not the verified Linux Python 3.10 venv")
    original_import = builtins.__import__
    def guard(name, *a, **kw):
        if name.startswith("nvdiffrast"):
            raise RuntimeError("Unexpected dependency import: " + name)
        return original_import(name, *a, **kw)
    builtins.__import__ = guard
    sys.path.insert(0, str(args.repo.resolve()))
    report["imports"] = {}
    for name in ("torch", "transformer_engine.pytorch", "torchvision", "cv2", "imageio", "av",
                 "cosmos_predict1.diffusion.inference.inference_inverse_renderer",
                 "cosmos_predict1.diffusion.inference.inference_forward_renderer"):
        try:
            importlib.import_module(name)
            report["imports"][name] = "passed"
        except Exception as exc:
            report["imports"][name] = type(exc).__name__ + ": " + str(exc)[:500]
            report["errors"].append("Import failed: " + name)
    try:
        import torch
        report["torch"] = {"version": torch.__version__, "cuda": torch.version.cuda,
                            "available": torch.cuda.is_available()}
        if not torch.cuda.is_available() or not torch.__version__.startswith("2.6.") or torch.version.cuda != "12.4":
            raise ValueError("Torch/CUDA does not match previous validation")
        report["torch"].update(gpu=torch.cuda.get_device_name(0),
                               memory_bytes=torch.cuda.get_device_properties(0).total_memory)
        if "L40S" not in report["torch"]["gpu"]:
            raise ValueError("Unexpected GPU")
        value = torch.arange(16, device="cuda", dtype=torch.float32).reshape(4, 4)
        assert torch.isfinite(value @ value).all().item()
        torch.cuda.synchronize()
        report["cuda_tensor"] = "passed"
        import transformer_engine.pytorch as te
        layer = te.Linear(16, 16, params_dtype=torch.float32, device="cuda")
        assert torch.isfinite(layer(torch.ones(2, 16, device="cuda"))).all().item()
        torch.cuda.synchronize()
        report["te_linear"] = "passed"
    except Exception as exc:
        report["errors"].append(type(exc).__name__ + ": " + str(exc)[:500])
    candidates = []
    if args.cuda_home:
        candidates.append(args.cuda_home / "bin/nvcc")
    if os.environ.get("CUDA_HOME"):
        candidates.append(Path(os.environ["CUDA_HOME"]) / "bin/nvcc")
    candidates += [Path(sys.prefix) / "bin/nvcc",
                   Path(sys.prefix) / "lib/python3.10/site-packages/nvidia/cuda_nvcc/bin/nvcc"]
    if shutil.which("nvcc"):
        candidates.append(Path(shutil.which("nvcc")))
    report["nvcc_candidates"] = []
    for path in dict.fromkeys(candidates):
        if path.is_file():
            r = subprocess.run([str(path), "--version"], capture_output=True, text=True, timeout=15)
            report["nvcc_candidates"].append({"path": str(path), "exit": r.returncode, "version": r.stdout[-1000:]})
    if not any(r["exit"] == 0 and "release 12.4" in r["version"] for r in report["nvcc_candidates"]):
        report["errors"].append("CUDA 12.4 toolkit path not verified")
    report["weights_space"] = plan(args.checkpoint_dir.resolve(), json.loads((ROOT / "manifests/weights_manifest.json").read_text()))
    if not report["weights_space"]["space_ok"]:
        report["errors"].append("Insufficient persistent disk space")
    report["patch_files"] = []
    for entry in json.loads((ROOT / "manifests/patch_manifest.json").read_text())["files"]:
        path = args.repo / entry["path"]
        valid = path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == entry["after_sha256"]
        report["patch_files"].append({"path": entry["path"], "valid": valid})
        if not valid:
            report["errors"].append("HDR patch file mismatch: " + entry["path"])
    report["ready"] = not report["errors"]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"ready": report["ready"], "errors": report["errors"], "out": str(args.out)}, indent=2))
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
