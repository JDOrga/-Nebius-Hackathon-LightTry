"""Decode the three actual official HDRs and exercise patched caller on CPU/CUDA."""
import argparse
import builtins
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
import os
import sys
sys.path.insert(0, str(ROOT / 'scripts'))
from local_config import upstream
UPSTREAM = upstream()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--device", choices=["cpu", "cuda"], default="cpu")
    p.add_argument("--out", type=Path, default=ROOT / "evidence/official_hdr_cpu.json")
    args = p.parse_args()
    original = builtins.__import__
    attempts = []
    def guarded(name, *a, **kw):
        if name.startswith("nvdiffrast"):
            attempts.append(name)
            raise RuntimeError("nvdiffrast import forbidden")
        return original(name, *a, **kw)
    builtins.__import__ = guarded
    import cv2
    import imageio.v3 as iio
    import numpy as np
    import torch
    sys.path.insert(0, str(UPSTREAM))
    from cosmos_predict1.diffusion.inference.diffusion_renderer_utils.utils_env_proj import process_environment_map
    records = []
    for index, name in enumerate(("sunny_vondelpark_2k.hdr", "pink_sunrise_2k.hdr", "street_lamp_2k.hdr")):
        path = UPSTREAM / "asset/examples/hdri_examples" / name
        decoded = iio.imread(str(path), flags=cv2.IMREAD_UNCHANGED, plugin="opencv")
        assert decoded.dtype == np.float32 and np.isfinite(decoded).all() and decoded.max() > 1
        started = time.perf_counter()
        result = process_environment_map(str(path), resolution=(33, 65), num_frames=1,
                                         env_format=["proj"], device=args.device)
        fields = {}
        for key in ("env_ldr", "env_log"):
            value = result[key]
            assert tuple(value.shape) == (1, 33, 65, 3) and torch.isfinite(value).all()
            assert value.device.type == args.device
            fields[key] = {"min": float(value.min()), "max": float(value.max()), "mean": float(value.mean())}
            preview = (value[0].clamp(0, 1).cpu().numpy() * 255).astype(np.uint8)
            from PIL import Image
            Image.fromarray(preview).save(ROOT / "evidence" / f"hdr_{args.device}_{index}_{key}.png")
        records.append({"path": str(path), "decoded_shape": list(decoded.shape),
                        "hdr_max": float(decoded.max()), "caller_fields": fields,
                        "seconds": time.perf_counter() - started})
    report = {"status": "passed", "device": args.device, "torch": torch.__version__,
              "nvdiffrast_import_attempts": attempts, "files": records,
              "scope": "real RGBE IO + patched projection; no neural inference or original-operator comparison"}
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
