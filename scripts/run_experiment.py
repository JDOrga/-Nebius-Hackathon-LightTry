"""Plan or execute one official image -> five G-buffers -> three HDR images.

Never manages VM lifecycle. The independent Windows guard owns the cloud stop.
Use the previously prepared Python 3.10 venv. No dependency installation here.
"""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from weights import parse_deadline, verify, check_time
from validate_outputs import validate_inverse, validate_forward, contact_sheet

ROOT = Path(__file__).resolve().parents[1]


def run_bounded(command, repo, logfile, env, deadline):
    check_time(deadline)
    kwargs = {"start_new_session": True} if os.name != "nt" else {}
    with logfile.open("w", encoding="utf-8") as output:
        process = subprocess.Popen(command, cwd=repo, env=env, stdout=output,
                                   stderr=subprocess.STDOUT, **kwargs)
        try:
            process.wait(timeout=max(0.1, deadline - time.time()))
        except BaseException:
            if os.name != "nt":
                os.killpg(process.pid, signal.SIGTERM)
            else:
                process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                if os.name != "nt":
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
            raise
    if process.returncode:
        raise RuntimeError(f"Inference exited {process.returncode}; inspect {logfile}")


def commands(args):
    common = [sys.executable, "-B", "cosmos_predict1/diffusion/inference/", "--checkpoint_dir",
              str(args.checkpoint_dir), "--num_video_frames", "1", "--height", str(args.height),
              "--width", str(args.width), "--num_steps", "15", "--seed", "1000", "--save_image=True"]
    if args.offload:
        common.extend(["--offload_diffusion_transformer", "--offload_tokenizer"])
    inverse = common.copy()
    inverse[2] += "inference_inverse_renderer.py"
    inverse.extend(["--diffusion_transformer_dir", "Diffusion_Renderer_Inverse_Cosmos_7B",
                    "--dataset_path", str(args.input_dir), "--group_mode", "webdataset",
                    "--inference_passes", "basecolor", "normal", "depth", "roughness", "metallic",
                    "--video_save_folder", str(args.run_dir / "inverse"), "--save_video=False"])
    forward = common.copy()
    forward[2] += "inference_forward_renderer.py"
    forward.extend(["--diffusion_transformer_dir", "Diffusion_Renderer_Forward_Cosmos_7B",
                    "--dataset_path", str(args.run_dir / "inverse/gbuffer_frames"),
                    "--envlight_ind", "0", "1", "2", "--use_custom_envmap=True",
                    "--video_save_folder", str(args.run_dir / "forward")])
    return inverse, forward


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--repo", required=True, type=Path)
    p.add_argument("--checkpoint-dir", required=True, type=Path)
    p.add_argument("--run-dir", required=True, type=Path)
    p.add_argument("--input-dir", required=True, type=Path)
    p.add_argument("--input-image", required=True, type=Path)
    p.add_argument("--stage", choices=["inverse", "forward", "all"], default="all")
    p.add_argument("--height", type=int, default=704)
    p.add_argument("--width", type=int, default=1280)
    p.add_argument("--offload", action="store_true")
    p.add_argument("--cuda-home", type=Path)
    p.add_argument("--deadline-utc")
    p.add_argument("--license-ack", choices=["nvidia-open-model-license"])
    p.add_argument("--execute", action="store_true")
    p.add_argument("--guard-launch-receipt", type=Path)
    args = p.parse_args()
    for name in ("repo", "checkpoint_dir", "run_dir", "input_dir", "input_image"):
        setattr(args, name, getattr(args, name).resolve())
    if args.height <= 0 or args.width <= 0 or args.height % 16 or args.width % 16:
        p.error("height and width must be positive multiples of 16")
    if args.execute and (not args.license_ack or not args.deadline_utc or not args.cuda_home or not args.guard_launch_receipt):
        p.error("execution requires confirmed license, fixed UTC deadline, verified CUDA toolkit, and guarded budget receipt")
    deadline = parse_deadline(args.deadline_utc) if args.deadline_utc else None
    if args.execute:
        receipt=json.loads(args.guard_launch_receipt.read_text(encoding='utf-8-sig'))
        if receipt.get('offline') or not receipt.get('single_run') or receipt.get('budget_usd_including_tax',0)<=0 or not receipt.get('approval_reference') or deadline>parse_deadline(receipt['deadline_utc']):
            raise ValueError('CURRENT_GUARDED_BUDGET_RECEIPT_REQUIRED')
    inverse, forward = commands(args)
    plan = {"repo": str(args.repo), "python": sys.executable, "stage": args.stage,
            "deadline_utc": args.deadline_utc, "height": args.height, "width": args.width,
            "steps": 15, "seed": 1000, "inverse_argv": inverse, "forward_argv": forward,
            "cloud_lifecycle": "external independent guard required; no restart/stop calls in this script",
            "security_note": "pinned upstream DiffusionRendererPipeline defaults disable_guardrail=True; no override added"}
    if not args.execute:
        print(json.dumps(plan, indent=2))
        return
    if os.name != "posix" or sys.version_info[:2] != (3, 10):
        raise RuntimeError("Execute only in the verified Linux Python 3.10 environment")
    check_time(deadline)
    # Read-only targeted patch check, then authoritative hashes for every checkpoint.
    subprocess.run([sys.executable, "-B", str(ROOT / "scripts/apply_hdr_patch.py"), "--repo", str(args.repo)], check=True)
    manifest = json.loads((ROOT / "manifests/patch_manifest.json").read_text())
    import hashlib
    for entry in manifest["files"]:
        if hashlib.sha256((args.repo / entry["path"]).read_bytes()).hexdigest() != entry["after_sha256"]:
            raise ValueError("HDR patch not applied")
    for entry in json.loads((ROOT / "manifests/weights_manifest.json").read_text())["files"]:
        if not verify(args.checkpoint_dir / entry["path"], entry, deadline):
            raise ValueError("Unverified checkpoint: " + entry["path"])
    if args.stage in ("inverse", "all"):
        if args.run_dir.exists():
            raise FileExistsError("Use a new run directory; preserve previous partial results")
        args.run_dir.mkdir(parents=True)
        (args.run_dir / "plan.json").write_text(json.dumps(plan, indent=2))
    else:
        prior = json.loads((args.run_dir / "plan.json").read_text())
        if any(prior[k] != plan[k] for k in ("height", "width", "steps", "seed", "repo")):
            raise ValueError("Forward recovery settings differ from prior inverse run")
        if (args.run_dir / "forward").exists():
            raise FileExistsError("Preserve old forward directory before retrying")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(args.repo)
    # Select the previously installed toolkit, without changing the venv/Jupyter environment.
    env["CUDA_HOME"] = str(args.cuda_home.resolve())
    env["PYTHONUNBUFFERED"] = "1"
    status = {"state": "started", "started_utc": dt.datetime.now(dt.timezone.utc).isoformat()}
    try:
        if args.stage in ("inverse", "all"):
            run_bounded(inverse, args.repo, args.run_dir / "inverse.log", env, deadline)
        status["inverse"] = validate_inverse(args.run_dir / "inverse", args.height, args.width)
        (args.run_dir / "inverse_acceptance.json").write_text(json.dumps(status["inverse"], indent=2))
        if args.stage in ("forward", "all"):
            # Only the three explicitly approved official HDR files are installed by the operator.
            for name in ("sunny_vondelpark_2k.hdr", "pink_sunrise_2k.hdr", "street_lamp_2k.hdr"):
                if not (args.repo / "asset/examples/hdri_examples" / name).is_file():
                    raise FileNotFoundError(name)
            run_bounded(forward, args.repo, args.run_dir / "forward.log", env, deadline)
            status["forward"] = validate_forward(args.run_dir / "forward", args.height, args.width)
            contact_sheet(args.input_image, args.run_dir / "inverse", args.run_dir / "forward", args.run_dir / "contact_sheet.png")
        status["state"] = "structural_checks_passed"
    except BaseException as exc:
        status.update(state="failed", error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        status["finished_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
        (args.run_dir / "status.json").write_text(json.dumps(status, indent=2))


if __name__ == "__main__":
    main()
