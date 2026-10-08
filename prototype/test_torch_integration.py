"""Real torch tests. Entire cases explicitly skip when torch is unavailable."""
import importlib.util
import unittest

import numpy as np
import numpy_reference as ref
from test_math_numpy import all_edges, all_corners

HAS_TORCH = importlib.util.find_spec("torch") is not None
HAS_CALLER_PACKAGES = all(importlib.util.find_spec(name) is not None for name in ("cv2", "imageio"))
if HAS_TORCH:
    import torch
    import env_sampling as actual


@unittest.skipUnless(HAS_TORCH, "PyTorch is not installed in the existing runtime")
class TorchTests(unittest.TestCase):
    def test_latlong_grid_sample_against_explicit_four_taps(self):
        rng = np.random.default_rng(2)
        tex = rng.uniform(0, 100, (2, 11, 17, 3))
        uv = rng.uniform(-2, 3, (2, 9, 13, 2))
        for mode in ("wrap", "clamp"):
            out = actual.sample_latlong(torch.from_numpy(tex), torch.from_numpy(uv), mode).numpy()
            np.testing.assert_allclose(out, ref.sample_latlong(tex, uv, mode), atol=2e-12, rtol=1e-12)

    def test_cubemap_grid_sample_matches_math_model(self):
        rng = np.random.default_rng(3)
        cube = rng.uniform(0, 10, (1, 6, 16, 16, 4))
        q = rng.normal(size=(2, 23, 31, 3))
        out = actual.sample_cubemap(torch.from_numpy(cube), torch.from_numpy(q)).numpy()
        np.testing.assert_allclose(out, ref.sample_cubemap(cube, q), atol=1e-12, rtol=1e-12)
        a, b = all_edges(eps=1e-9)
        for query in (a[None], b[None], all_corners()[None]):
            actual_out = actual.sample_cubemap(torch.from_numpy(cube), torch.from_numpy(query)).numpy()
            np.testing.assert_allclose(actual_out, ref.sample_cubemap(cube, query), atol=1e-12, rtol=1e-12)

    def test_latlong_conversion_and_batch(self):
        tex = ref.direction_latlong(128, 256)
        cube = actual.latlong_to_cubemap(torch.from_numpy(tex), [32, 32])
        np.testing.assert_allclose(cube.numpy(), ref.latlong_to_cubemap(tex, [32, 32]), atol=1e-13)
        batch = actual.latlong_to_cubemap(torch.from_numpy(np.stack((tex, tex * 3))), [32, 32])
        self.assertEqual(tuple(batch.shape), (2, 6, 32, 32, 3))
        torch.testing.assert_close(batch[1], batch[0] * 3)

    def test_dtypes_noncontiguous_and_query_broadcast(self):
        for dtype in (torch.float16, torch.bfloat16, torch.float32, torch.float64):
            cube = torch.full((2, 6, 8, 8, 3), 16., dtype=dtype).transpose(2, 3)
            q = torch.tensor([[[[1., 0, 0], [0, 1., 0]]]], dtype=torch.float32)
            out = actual.sample_cubemap(cube, q)
            self.assertEqual(out.dtype, dtype)
            self.assertEqual(out.device, cube.device)
            self.assertEqual(tuple(out.shape), (2, 1, 2, 3))
            torch.testing.assert_close(out, torch.full_like(out, 16))
        with self.assertRaises(ValueError):
            actual.sample_cubemap(torch.ones((3, 6, 8, 8, 3)), torch.ones((2, 7, 3)))
        with self.assertRaises(TypeError):
            actual.sample_cubemap(torch.ones((1, 6, 8, 8, 3), dtype=torch.int32), torch.ones((1, 7, 3)))

    def test_finite_invalid_directions_and_extreme_scale(self):
        q = torch.tensor([[[0., 0, 0], [float("nan"), 1, 0], [float("inf"), 0, 1],
                           [1e30, -2e30, 3e30], [1e-30, 0, 0]]])
        out = actual.sample_cubemap(torch.full((1, 6, 8, 8, 3), 16.), q)
        self.assertTrue(torch.isfinite(out).all())
        torch.testing.assert_close(out[0, :3], torch.zeros((3, 3)))
        torch.testing.assert_close(out[0, 3:], torch.full((2, 3), 16.))

    def test_autograd_interior_smoke(self):
        cube = torch.rand((1, 6, 8, 8, 3), dtype=torch.float64, requires_grad=True)
        q = torch.tensor([[[1., .13, .27]]], dtype=torch.float64, requires_grad=True)
        self.assertTrue(torch.autograd.gradcheck(actual.sample_cubemap, (cube, q), eps=1e-6, atol=1e-4))

    @unittest.skipUnless(HAS_CALLER_PACKAGES, "Caller additionally requires cv2 and imageio")
    def test_patched_caller_real_import_and_projection(self):
        import pathlib
        import sys
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'scripts'))
        from unittest.mock import patch
        if not __import__('local_config').upstream().is_dir():
            self.skipTest('external patched upstream not configured')
        sys.path.insert(0, str(__import__('local_config').upstream()))
        # A guard proves real module imports and calls never request nvdiffrast.
        import builtins
        original_import = builtins.__import__
        def guarded(name, *args, **kwargs):
            if name.startswith("nvdiffrast"):
                raise AssertionError("unexpected nvdiffrast import")
            return original_import(name, *args, **kwargs)
        with patch("builtins.__import__", guarded):
            from cosmos_predict1.diffusion.inference.diffusion_renderer_utils import rendering_utils as util
            from cosmos_predict1.diffusion.inference.diffusion_renderer_utils import utils_env_proj as proj
            cube = torch.from_numpy(ref.direction_cube(64)[0]).float()
            h, w = 17, 29
            vec = util.latlong_vec((h, w), device="cpu")
            result = proj.process_projected_envmap(cube, vec, torch.eye(4), torch.eye(4), h, w)
            truth = ((-vec + 1) / 2).flip((0, 1))
            torch.testing.assert_close(result, truth, atol=2e-3, rtol=0)
            normal, _ = util.get_ideal_ball(17)
            reflected = util.get_ref_vector(normal, torch.tensor([0., 0, 1]))
            ball = proj.process_ball_envmap(cube, reflected, torch.eye(4), torch.eye(4), 17, 17)
            torch.testing.assert_close(ball, (reflected + 1) / 2, atol=2e-3, rtol=0)
            converted = util.latlong_to_cubemap(torch.ones((32, 64, 3)), [16, 16])
            self.assertEqual(converted.device.type, "cpu")
            torch.testing.assert_close(converted, torch.ones_like(converted))
            # Entire environment preprocessing with self-generated image data;
            # only file decoding is mocked. This is still not model inference.
            source = ref.direction_latlong(128, 256).astype(np.float32)
            with patch.object(proj.imageio_v3, "imread", return_value=source):
                frames = proj.process_environment_map("synthetic.hdr", resolution=(17, 17),
                    num_frames=2, env_flip=False, env_rot=0., device="cpu")
            self.assertEqual(tuple(frames["fixed"]["env_hdr"].shape), (17, 17, 3))
            for key in ("env_ldr", "env_log", "ball_env_ldr", "ball_env_log"):
                self.assertEqual(tuple(frames[key].shape), (2, 17, 17, 3))
                self.assertTrue(torch.isfinite(frames[key]).all())

    @unittest.skipUnless(HAS_TORCH and torch.cuda.is_available(), "CUDA not available")
    def test_cuda_dtype_device_parity(self):
        cube = torch.from_numpy(ref.direction_cube(32).astype(np.float32))
        q = torch.tensor([[[1., .2, -.3], [0., 1, 0]]])
        cpu = actual.sample_cubemap(cube, q)
        gpu = actual.sample_cubemap(cube.cuda(), q.cuda())
        self.assertEqual(gpu.device.type, "cuda")
        torch.testing.assert_close(gpu.cpu(), cpu, atol=1e-5, rtol=1e-5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
