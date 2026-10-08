"""Handwritten orientation/marker cases; no direction-generation helper.

Face order and row conventions come from the fixed caller's public contract.
These cases are literal off-axis directions paired with literal pixel positions.
They do not derive inputs with face_directions, locate, or direction_cube.
"""
import importlib.util
import math
from pathlib import Path
import subprocess
import sys
import unittest

import numpy as np

import numpy_reference

HAS_TORCH = importlib.util.find_spec("torch") is not None
if HAS_TORCH:
    import torch
    import env_sampling


# (face, row, column, world direction), face resolution is exactly four.
# s/t pixel centers are -.75, -.25, +.25, +.75. Two asymmetric probes per face.
CASES = (
    (0, 0, 1, (1., .75, .25)),
    (0, 3, 2, (1., -.75, -.25)),
    (1, 1, 3, (-1., .25, .75)),
    (1, 2, 0, (-1., -.25, -.75)),
    (2, 0, 2, (.25, 1., -.75)),
    (2, 3, 1, (-.25, 1., .75)),
    (3, 1, 0, (-.75, -1., .25)),
    (3, 2, 3, (.75, -1., -.25)),
    (4, 0, 3, (.75, .75, 1.)),
    (4, 3, 0, (-.75, -.75, 1.)),
    (5, 1, 1, (.25, .25, -1.)),
    (5, 2, 2, (-.25, -.25, -1.)),
)
PATTERN = np.array([[3., 17., 5., 29.], [41., 7., 53., 11.],
                    [13., 67., 19., 83.], [97., 23., 101., 31.]])
OFFSETS = (1000., 2000., 3000., 4000., 5000., 6000.)


def marker_cube():
    # This builds image values only, never a direction or inverse face lookup.
    return np.stack([np.stack((PATTERN + offset, PATTERN ** 2 + 2 * offset), -1)
                     for offset in OFFSETS])[None]


class GoldenAssertions:
    def test_literal_six_face_off_axis_pixel_markers(self):
        directions = np.array([[case[3] for case in CASES]])
        expected = np.array([[[OFFSETS[f] + PATTERN[row, col],
                               2 * OFFSETS[f] + PATTERN[row, col] ** 2]
                              for f, row, col, _ in CASES]])
        cube = marker_cube()
        for multiplier in (.001, 1., 1000.):
            out = self.cube_sample(cube, directions * multiplier)
            np.testing.assert_allclose(out, expected, atol=1e-9, rtol=0)

    def test_literal_six_face_subpixel_four_tap_truth(self):
        # All six directions select s=-.5,t=0: rows 1/2, columns 0/1,
        # with exactly .25 per texel. Values are hand-summed, not interpolated.
        directions = np.array([[(1., 0., .5), (-1., 0., -.5), (-.5, 1., 0.),
                                (-.5, -1., 0.), (-.5, 0., 1.), (.5, 0., -1.)]])
        # First channel: (41+7+13+67)/4=32.
        # Second channel: (1681+49+169+4489)/4=1597.
        expected = np.array([[[offset + 32, 2 * offset + 1597] for offset in OFFSETS]])
        np.testing.assert_allclose(self.cube_sample(marker_cube(), directions), expected, atol=1e-9, rtol=0)

    def test_conversion_against_literal_world_directions(self):
        h, w = 64, 128
        u = np.broadcast_to((np.arange(w) + .5) / w, (h, w))
        v = np.broadcast_to(((np.arange(h) + .5) / h)[:, None], (h, w))
        cube = self.convert(np.stack((u, v), -1), [4, 4])
        for f, row, col, (x, y, z) in CASES:
            # Closed-form spherical coordinates of a literal world vector.
            length = math.sqrt(x * x + y * y + z * z)
            expected = [math.atan2(x, -z) / (2 * math.pi) + .5,
                        math.acos(y / length) / math.pi]
            np.testing.assert_allclose(cube[f, row, col], expected, atol=2e-14, rtol=0)

    def test_latlong_asymmetric_marker_literal_truth(self):
        tex = PATTERN[:3, :, None][None]
        uv = np.array([[[0., 1 / 6], [1., 1 / 6], [.25, .5], [.375, 0.]]])
        # Row 0 seam=(3+29)/2=16; row 1 midpoint=(41+7)/2=24;
        # V wrap at column 1=(17+67)/2=42. Clamp instead yields row 0=17.
        np.testing.assert_allclose(self.lat_sample(tex, uv, "wrap")[0, :, 0], [16, 16, 24, 42], atol=1e-12)
        np.testing.assert_allclose(self.lat_sample(tex, uv, "clamp")[0, :, 0], [16, 16, 24, 17], atol=1e-12)


class NumPyGoldenTests(GoldenAssertions, unittest.TestCase):
    cube_sample = staticmethod(numpy_reference.sample_cubemap)
    lat_sample = staticmethod(numpy_reference.sample_latlong)
    convert = staticmethod(numpy_reference.latlong_to_cubemap)


@unittest.skipUnless(HAS_TORCH, "CPU PyTorch not installed")
class TorchGoldenTests(GoldenAssertions, unittest.TestCase):
    @staticmethod
    def cube_sample(cube, directions):
        return env_sampling.sample_cubemap(torch.from_numpy(cube), torch.from_numpy(directions)).numpy()

    @staticmethod
    def lat_sample(tex, uv, mode):
        return env_sampling.sample_latlong(torch.from_numpy(tex), torch.from_numpy(uv), mode).numpy()

    @staticmethod
    def convert(tex, res):
        return env_sampling.latlong_to_cubemap(torch.from_numpy(tex), res).numpy()

    def test_caller_512_shape_cpu_hdr_constant(self):
        # Actual caller face/output size, using the literal six-face probes.
        # The truth is a constant HDR value; no geometry helper is involved.
        value = torch.tensor([.125, 16., 65504.], dtype=torch.float32)
        cube = value.expand(1, 6, 512, 512, 3)
        probes = torch.tensor([case[3] for case in CASES], dtype=torch.float32)
        indices = torch.arange(512 * 512) % len(CASES)
        query = probes[indices].reshape(1, 512, 512, 3)
        out = env_sampling.sample_cubemap(cube, query)
        self.assertEqual(tuple(out.shape), (1, 512, 512, 3))
        self.assertEqual(out.device.type, "cpu")
        self.assertEqual(out.dtype, torch.float32)
        self.assertTrue(torch.isfinite(out).all())
        # Absolute HDR tolerance is a few float32 ULPs at 65504.
        torch.testing.assert_close(out, value.expand_as(out), atol=.02, rtol=0)

    def test_fresh_real_sampler_import_with_nvdiffrast_guard(self):
        # Independent runtime import only; no cv2/imageio stubs or dependencies.
        prototype = str(Path(__file__).resolve().parent)
        code = """import builtins, sys
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name.startswith('nvdiffrast'):
        raise AssertionError('unexpected nvdiffrast import')
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
sys.path.insert(0, sys.argv[1])
import torch
import env_sampling
out = env_sampling.sample_cubemap(torch.ones((1,6,4,4,2)), torch.tensor([[[1.,.2,.3]]]))
torch.testing.assert_close(out, torch.ones((1,1,2)))
print('real CPU sampler import/call passed; torch=' + torch.__version__)
"""
        result = subprocess.run([sys.executable, "-B", "-c", code, prototype], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("real CPU sampler import/call passed", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
