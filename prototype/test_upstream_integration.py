"""Real patched upstream caller checks, requiring only the approved IO packages."""
import builtins
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
import os
import sys
sys.path.insert(0, str(ROOT / 'scripts'))
from local_config import upstream
UPSTREAM = upstream()
AVAILABLE = all(importlib.util.find_spec(name) is not None for name in ("torch", "cv2", "imageio", "PIL"))


@unittest.skipUnless(AVAILABLE and UPSTREAM.is_dir(), "approved CPU/image packages are unavailable")
class UpstreamIntegrationTests(unittest.TestCase):
    def test_literal_camera_and_environment_rotation_contract(self):
        import torch
        sys.path.insert(0, str(UPSTREAM))
        original = builtins.__import__
        def guard(name, *args, **kwargs):
            if name.startswith("nvdiffrast"):
                raise AssertionError("unexpected nvdiffrast import")
            return original(name, *args, **kwargs)
        with patch("builtins.__import__", guard):
            from cosmos_predict1.diffusion.inference.diffusion_renderer_utils import utils_env_proj as proj
            markers = torch.arange(1, 7, dtype=torch.float32).view(6, 1, 1, 1)
            channels = torch.tensor([1., 2., 3.]).view(1, 1, 1, 3)
            cube = (markers * channels).expand(6, 4, 4, 3)
            vec = torch.tensor([[[-1., 0, 0], [0, -1., 0], [0, 0, -1.]],
                                [[1., 0, 0], [0, 1., 0], [0, 0, 1.]]])
            camera = torch.tensor([[0., 0, 1, 0], [0, 1., 0, 0], [-1., 0, 0, 0], [0, 0, 0, 1.]])
            environment = torch.tensor([[0., -1, 0, 0], [1., 0, 0, 0], [0, 0, 1., 0], [0, 0, 0, 1.]])
            projected = proj.process_projected_envmap(cube, vec, camera, environment, 2, 3)
            # Handlisted face markers after camera Y90 then environment Z90,
            # query negation and the projected output's two-axis flip.
            expected_proj = torch.tensor([[4., 1., 5.], [3., 2., 6.]])[..., None] * channels[0]
            torch.testing.assert_close(projected, expected_proj, atol=2e-5, rtol=0)
            ball = proj.process_ball_envmap(cube, vec, camera, environment, 2, 3)
            # Ball's two negations cancel; it applies no output flip.
            expected_ball = torch.tensor([[5., 1., 4.], [6., 2., 3.]])[..., None] * channels[0]
            torch.testing.assert_close(ball, expected_ball, atol=2e-5, rtol=0)
            for output in (projected, ball):
                self.assertEqual(tuple(output.shape), (2, 3, 3))
                self.assertEqual(output.dtype, torch.float32)
                self.assertEqual(output.device.type, "cpu")

    def test_real_small_hdr_roundtrip_and_preprocessing(self):
        result = subprocess.run([sys.executable, "-B", str(ROOT / "prototype/upstream_hdr_smoke.py")],
                                capture_output=True, text=True, encoding="utf-8", errors="replace")
        if result.returncode == 77:
            self.skipTest("installed OpenCV has no HDR writer")
        (ROOT / "artifacts/hdr_smoke_process.txt").write_text(result.stdout + result.stderr, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        data = json.loads((ROOT / "artifacts/hdr_smoke/results.json").read_text(encoding="utf-8"))
        self.assertEqual(data["status"], "passed")
        self.assertFalse(data["mocked_file_decoder"])
        self.assertEqual(data["nvdiffrast_import_attempts"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
