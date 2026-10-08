"""Real self-generated Radiance HDR IO and CPU caller smoke test; no mocks."""
import builtins
import json
from pathlib import Path
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
import os
import sys
sys.path.insert(0, str(ROOT / 'scripts'))
from local_config import upstream
UPSTREAM = upstream()
OUT = ROOT / "artifacts/hdr_smoke"


def main():
    original_import = builtins.__import__
    requests = []

    def guarded(name, *args, **kwargs):
        if name.startswith("nvdiffrast"):
            requests.append(name)
            raise AssertionError("unexpected nvdiffrast import")
        return original_import(name, *args, **kwargs)

    start = time.perf_counter()
    with patch("builtins.__import__", guarded):
        import cv2
        import imageio.v3 as iio
        import numpy as np
        import torch
        sys.path.insert(0, str(UPSTREAM))
        from cosmos_predict1.diffusion.inference.diffusion_renderer_utils import utils_env_proj as proj

        OUT.mkdir(parents=True, exist_ok=True)
        probe = OUT / "constant.hdr"
        if not cv2.haveImageWriter(str(probe)):
            print(json.dumps({"status": "not_executed", "reason": "installed OpenCV has no HDR writer"}))
            return 77

        # OpenCV writes BGR; the existing caller reads RGB through imageio's
        # built-in OpenCV plugin. Powers of two are exactly representable RGBE.
        value = np.array([1., 4., 16.], dtype=np.float32)
        constant = np.broadcast_to(value, (16, 32, 3)).copy()
        assert cv2.imwrite(str(probe), constant[..., ::-1])
        decoded = iio.imread(str(probe), flags=cv2.IMREAD_UNCHANGED, plugin="opencv")
        assert decoded.shape == constant.shape and decoded.dtype == np.float32
        np.testing.assert_allclose(decoded, constant, atol=0, rtol=0)
        frames = proj.process_environment_map(str(probe), resolution=(17, 17), num_frames=2,
            env_strength=2., env_flip=False, env_rot=0., device="cpu", save_dir=str(OUT / "constant_outputs"))
        fixed = frames["fixed"]["env_hdr"]
        assert tuple(fixed.shape) == (17, 17, 3) and fixed.dtype == torch.float32 and fixed.device.type == "cpu"
        torch.testing.assert_close(fixed, torch.from_numpy(value * 2).expand_as(fixed), atol=2e-5, rtol=0)
        frame_info = {}
        for key in ("env_ldr", "env_log", "ball_env_ldr", "ball_env_log"):
            tensor = frames[key]
            assert tuple(tensor.shape) == (2, 17, 17, 3)
            assert tensor.dtype == torch.float32 and tensor.device.type == "cpu"
            assert torch.isfinite(tensor).all() and tensor.min() >= 0 and tensor.max() <= 1
            frame_info[key] = {"shape": list(tensor.shape), "dtype": str(tensor.dtype), "device": str(tensor.device)}

        # Generate a colored continuous spherical field without any sampler
        # face-direction helper. Radiance RGBE quantization is measured explicitly.
        h, w = 64, 128
        theta = (np.arange(h) + .5)[:, None] * np.pi / h
        phi = ((np.arange(w) + .5)[None, :] / w - .5) * 2 * np.pi
        dx = np.sin(theta) * np.sin(phi)
        dy = np.broadcast_to(np.cos(theta), (h, w))
        dz = -np.sin(theta) * np.cos(phi)
        field = ((np.stack((dx, dy, dz), -1) + 1) / 2).astype(np.float32)
        field_path = OUT / "direction_field.hdr"
        assert cv2.imwrite(str(field_path), field[..., ::-1])
        field_decoded = iio.imread(str(field_path), flags=cv2.IMREAD_UNCHANGED, plugin="opencv")
        roundtrip_error = float(np.max(np.abs(field_decoded - field)))
        assert roundtrip_error < .004
        direction = proj.process_environment_map(str(field_path), resolution=(33, 33), num_frames=1,
            env_flip=False, env_rot=0., device="cpu", save_dir=str(OUT / "direction_outputs"))
        # Handwritten caller equations: negate transformed latlong direction,
        # then flip both image axes. Output avoids exact pole directions.
        angle = np.linspace(1 / 33, 1 - 1 / 33, 33)[:, None] * np.pi
        azimuth = np.linspace(-1 + 1 / 33, 1 - 1 / 33, 33)[None, :] * np.pi
        expected = np.stack((np.sin(angle) * np.sin(azimuth), np.broadcast_to(np.cos(angle), (33, 33)),
                             -np.sin(angle) * np.cos(azimuth)), -1)
        expected = ((-expected + 1) / 2)[::-1, ::-1]
        direction_hdr = direction["fixed"]["env_hdr"].numpy()
        fixed_error = float(np.max(np.abs(direction_hdr - expected)))
        assert fixed_error < .006
        torch.testing.assert_close(direction["env_ldr"][0], direction["fixed"]["env_ev0"], atol=1e-6, rtol=0)
        for key in ("env_ldr", "env_log", "ball_env_ldr", "ball_env_log"):
            assert tuple(direction[key].shape) == (1, 33, 33, 3) and torch.isfinite(direction[key]).all()

        pngs = sorted(OUT.glob("*_outputs/*.png"))
        assert len(pngs) == 16
        for png in pngs:
            actual = iio.imread(str(png))
            expected_size = 17 if png.parent.name == "constant_outputs" else 33
            assert actual.shape == (expected_size, expected_size, 3) and actual.dtype == np.uint8
        result = {"status": "passed", "mocked_file_decoder": False, "format": "Radiance RGBE .hdr",
                  "not_tested": ["EXR", "CUDA", "model inference", "original nvdiffrast operator"],
                  "opencv_version": cv2.__version__, "torch_version": torch.__version__,
                  "constant_hdr_roundtrip_max_abs_error": float(np.max(np.abs(decoded - constant))),
                  "direction_hdr_roundtrip_max_abs_error": roundtrip_error,
                  "direction_fixed_max_abs_error_vs_analytic": fixed_error,
                  "constant_env_strength": 2., "output_frame_info": frame_info,
                  "png_count": len(pngs), "nvdiffrast_import_attempts": requests,
                  "elapsed_seconds": time.perf_counter() - start,
                  "hdr_files": [{"path": str(p), "bytes": p.stat().st_size} for p in (probe, field_path)],
                  "outputs": [str(p) for p in pngs]}
        (OUT / "results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
