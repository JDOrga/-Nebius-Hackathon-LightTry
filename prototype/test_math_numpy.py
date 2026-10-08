"""Analytic tests run with the already available NumPy runtime."""
import itertools
import math
import unittest

import numpy as np
from numpy_reference import (bilinear_pixels, direction_cube, direction_latlong,
                             face_directions, latlong_to_cubemap, locate,
                             sample_cubemap, sample_latlong)


def all_edges(eps=1e-7, n=41):
    """12 geometric edges, approached independently from their two faces."""
    a, b = [], []
    for axis1, axis2 in itertools.combinations(range(3), 2):
        third = 3 - axis1 - axis2
        for sign1, sign2 in itertools.product((-1, 1), repeat=2):
            d = np.zeros((n, 3))
            d[:, axis1], d[:, axis2] = sign1, sign2
            d[:, third] = np.linspace(-.95, .95, n)
            left, right = d.copy(), d.copy()
            left[:, axis1] *= 1 + eps
            right[:, axis2] *= 1 + eps
            a.append(left)
            b.append(right)
    return np.stack(a), np.stack(b)


def all_corners(eps=1e-7):
    d = np.array(list(itertools.product((-1., 1.), repeat=3)))
    approaches = []
    for axis in range(3):
        q = d.copy()
        q[:, axis] *= 1 + eps
        approaches.append(q)
    return np.stack(approaches)


class MathTests(unittest.TestCase):
    def test_latlong_markers_pixel_centers_and_storage_rows(self):
        h, w = 7, 11
        marker = np.arange(h * w * 3, dtype=np.float64).reshape(1, h, w, 3)
        u, v = np.meshgrid((np.arange(w) + .5) / w, (np.arange(h) + .5) / h)
        uv = np.stack((u, v), -1)[None]
        np.testing.assert_allclose(sample_latlong(marker, uv), marker, atol=1e-12)
        # Explicit asymmetric row truth; no hidden OpenGL/image-order flip.
        q = np.array([[[.5 / w, .5 / h], [.5 / w, 1 - .5 / h]]])
        np.testing.assert_allclose(sample_latlong(marker, q)[0], marker[0, [0, -1], 0], atol=1e-12)

    def test_longitude_wrap_and_half_texel_seam(self):
        tex = np.array([[[[1.], [2.], [4.], [9.]]]])
        uv = np.array([[[0., .5], [1., .5], [-1., .5], [2., .5], [.125, .5]]])
        np.testing.assert_allclose(sample_latlong(tex, uv)[0, :, 0], [5, 5, 5, 5, 1])

    def test_latitude_wrap_vs_clamp_poles(self):
        tex = np.array([[[[2.], [2.]], [[10.], [10.]]]])
        uv = np.array([[[.5, 0.], [.5, 1.]]])
        np.testing.assert_allclose(sample_latlong(tex, uv)[0, :, 0], [6, 6])
        np.testing.assert_allclose(sample_latlong(tex, uv, "clamp")[0, :, 0], [2, 10])

    def test_six_axes_and_face_pixel_centers(self):
        r = 9
        rng = np.random.default_rng(9)
        cube = rng.random((1, 6, r, r, 3))
        axes = np.array([[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1]], float)
        np.testing.assert_allclose(sample_cubemap(cube, axes[None])[0], cube[0, :, r // 2, r // 2], atol=1e-12)
        p = (np.arange(r) + .5) * (2 / r) - 1
        s, t = np.meshgrid(p, p)
        dirs = np.stack([face_directions(f, s, t) for f in range(6)])
        np.testing.assert_allclose(sample_cubemap(cube, dirs[None]), cube, atol=2e-14)

    def test_face_geometry_roundtrip_and_tie_priority(self):
        rng = np.random.default_rng(12)
        s, t = rng.uniform(-.98, .98, (2, 100))
        for f in range(6):
            face, st, valid = locate(face_directions(f, s, t))
            np.testing.assert_array_equal(face, np.full(100, f))
            np.testing.assert_allclose(st, np.stack((s, t), -1), atol=1e-15)
            self.assertTrue(valid.all())
        np.testing.assert_array_equal(locate(np.array([[1., 1., 1.], [0., -1., 1.]]))[0], [0, 3])

    def test_constant_hdr_brightness_and_channels(self):
        rng = np.random.default_rng(8)
        d = rng.normal(size=(2, 13, 17, 3))
        value = np.array([.125, 16., 65504., -3.])
        lat = np.broadcast_to(value, (1, 32, 64, 4)).copy()
        cube = latlong_to_cubemap(lat, [16, 16])
        out = sample_cubemap(cube, d)
        self.assertEqual(out.shape, (2, 13, 17, 4))
        np.testing.assert_allclose(out, np.broadcast_to(value, out.shape), atol=2e-10, rtol=1e-14)
        np.testing.assert_allclose(sample_cubemap(cube * 2.5, d), out * 2.5, rtol=1e-14, atol=1e-9)

    def test_direction_color_analytic_accuracy(self):
        rng = np.random.default_rng(77)
        d = rng.normal(size=(1, 20000, 3))
        truth = (d / np.linalg.norm(d, axis=-1, keepdims=True) + 1) / 2
        errors = []
        for r in (16, 32, 64):
            err = np.max(np.abs(sample_cubemap(direction_cube(r), d) - truth))
            errors.append(err)
        # Nearest cross-face gutters guarantee edge continuity but give O(1/R)
        # edge accuracy, unlike the O(1/R^2) smooth face interiors.
        self.assertLess(errors[-1], 2e-3)
        self.assertLess(errors[2], errors[1])
        self.assertLess(errors[1], errors[0])
        st = locate(d)[1]
        interior = (np.abs(st) < 1 - 2 / 64).all(axis=-1)
        error = np.abs(sample_cubemap(direction_cube(64), d) - truth)
        self.assertLess(error[interior].max(), 1.3e-4)
        self.assertLess(np.max(np.abs(sample_cubemap(direction_cube(512), d) - truth)), 2.5e-4)

    def test_latlong_to_cube_analytic_direction_color(self):
        lat = direction_latlong(256, 512)
        cube = latlong_to_cubemap(lat, [64, 64])
        np.testing.assert_allclose(cube, direction_cube(64)[0], atol=3e-5, rtol=0)

    def test_continuous_gradient_inside_faces(self):
        r = 32
        p = (np.arange(r) + .5) * (2 / r) - 1
        s, t = np.meshgrid(p, p)
        # Bilinear interpolation must reproduce an affine face-local field.
        cube = np.stack([np.stack((s + f, 2 * t - f, 3 * s - t), -1) for f in range(6)])[None]
        ss = np.array([-.75, -.23, .14, .63])
        tt = np.array([.42, -.35, .26, -.72])
        for f in range(6):
            q = face_directions(f, ss, tt)[None]
            truth = np.stack((ss + f, 2 * tt - f, 3 * ss - tt), -1)[None]
            np.testing.assert_allclose(sample_cubemap(cube, q), truth, atol=1e-13)

    def test_all_12_edge_seams_with_discontinuous_face_markers(self):
        r = 32
        markers = np.broadcast_to(np.arange(6).reshape(1, 6, 1, 1, 1), (1, 6, r, r, 1)).astype(float)
        a, b = all_edges(eps=1e-9)
        va, vb = sample_cubemap(markers, a[None]), sample_cubemap(markers, b[None])
        self.assertLess(np.max(np.abs(va - vb)), 1e-6)
        fa = locate(a)[0]
        fb = locate(b)[0]
        np.testing.assert_allclose(va[..., 0], ((fa + fb) / 2)[None], atol=1e-7)

    def test_all_8_corner_seams_with_markers(self):
        r = 32
        cube = np.broadcast_to(np.arange(6).reshape(1, 6, 1, 1, 1), (1, 6, r, r, 1)).astype(float)
        q = all_corners()
        out = sample_cubemap(cube, q[None])[0, ..., 0]
        signs = np.array(list(itertools.product((-1, 1), repeat=3)))
        truth = ((signs < 0) + np.array([0, 2, 4])).mean(axis=-1)
        np.testing.assert_allclose(out, np.broadcast_to(truth, out.shape), atol=1e-5)
        self.assertLess(np.max(np.ptp(out, axis=0)), 1e-5)

    def test_random_texture_edge_continuity(self):
        rng = np.random.default_rng(22)
        cube = rng.random((1, 6, 32, 32, 3))
        a, b = all_edges(eps=1e-9, n=137)
        jump = np.max(np.abs(sample_cubemap(cube, a[None]) - sample_cubemap(cube, b[None])))
        self.assertLess(jump, 1e-7)

    def test_invalid_and_extreme_directions_finite(self):
        cube = np.ones((1, 6, 8, 8, 3)) * 16
        q = np.array([[[0, 0, 0], [np.nan, 1, 0], [np.inf, 0, 1], [1e300, 2e300, -1e300], [1e-300, 0, 0]]])
        out = sample_cubemap(cube, q)
        self.assertTrue(np.isfinite(out).all())
        np.testing.assert_array_equal(out[0, :3], np.zeros((3, 3)))
        np.testing.assert_allclose(out[0, 3:], 16)

    def test_batch_broadcast_and_float32(self):
        q = np.array([[[1., 0, 0]], [[0., 0, -1]]], dtype=np.float32)
        cube = np.ones((1, 6, 8, 8, 3), dtype=np.float32) * 7
        self.assertEqual(sample_cubemap(cube, q).dtype, np.float32)
        np.testing.assert_allclose(sample_cubemap(cube, q), 7)
        cube = np.concatenate([cube, cube * 2], axis=0)
        np.testing.assert_allclose(sample_cubemap(cube, q[:1])[:, 0, 0], [7, 14])
        with self.assertRaises(ValueError):
            sample_cubemap(np.ones((3, 6, 8, 8, 3)), q)
        noncontiguous = cube[:, :, ::-1, ::-1, :]
        np.testing.assert_allclose(sample_cubemap(noncontiguous, q), sample_cubemap(cube, q))

    def test_rotation_and_flip_analytic_pipeline(self):
        r = 64
        cube = direction_cube(r)
        h, w = 23, 41
        # Match upstream latlong_vec, including its nonstandard latitude endpoints.
        gy, gx = np.meshgrid(np.linspace(1 / h, 1 - 1 / h, h), np.linspace(-1 + 1 / w, 1 - 1 / w, w), indexing="ij")
        vec = np.stack((np.sin(gy * math.pi) * np.sin(gx * math.pi), np.cos(gy * math.pi),
                        -np.sin(gy * math.pi) * np.cos(gx * math.pi)), -1)
        fixed = sample_cubemap(cube, -vec[None])[0, ::-1, ::-1]
        expected_fixed = ((-vec + 1) / 2)[::-1, ::-1]
        np.testing.assert_allclose(fixed, expected_fixed, atol=2e-3)
        # 90-degree Y rotation, row vectors multiplied by transpose, then negation.
        rot = np.array([[0., 0, 1], [0, 1, 0], [-1, 0, 0]])
        query = -(vec @ rot.T)
        projected = sample_cubemap(cube, query[None])[0, ::-1, ::-1]
        np.testing.assert_allclose(projected, ((query + 1) / 2)[::-1, ::-1], atol=2e-3)
        # Caller applies source horizontal flip and a quantized roll before conversion.
        lat = direction_latlong(128, 256)
        flipped_rolled = np.roll(lat[:, ::-1], 64, axis=1)
        theta, phi = math.pi / 2, .0
        d = np.array([[[math.sin(theta) * math.sin(phi), math.cos(theta), -math.sin(theta) * math.cos(phi)]]])
        uv = np.array([[[.5, .5]]])
        truth = sample_latlong(flipped_rolled[None], uv)
        sampled = sample_cubemap(latlong_to_cubemap(flipped_rolled, [64, 64])[None], d)
        np.testing.assert_allclose(sampled, truth, atol=4e-4)

    def test_chrome_ball_reflection_and_center(self):
        r, size = 64, 31
        x, y = np.meshgrid(np.linspace(-1, 1, size), np.linspace(1, -1, size))
        mask = x * x + y * y <= 1
        n = np.stack((x * mask, y * mask, np.sqrt(np.maximum(1 - x * x - y * y, 0))), -1)
        ref = 2 * n[..., 2:3] * n - np.array([0., 0, 1])
        # Upstream ball function negates ref before rotation and again for sampling.
        out = sample_cubemap(direction_cube(r), ref[None])[0]
        np.testing.assert_allclose(out, (ref + 1) / 2, atol=2e-3)
        np.testing.assert_allclose(out[size // 2, size // 2], [.5, .5, 1], atol=1.3e-4)
        self.assertTrue(np.isfinite(out).all())
        # Existing caller fills outside sphere using -Z instead of masking to black.
        np.testing.assert_allclose(out[~mask], np.broadcast_to([.5, .5, 0], out[~mask].shape), atol=1.3e-4)

    def test_odd_cube_pole_preservation_and_optional_clamp(self):
        lat = direction_latlong(128, 256)
        wrapped = latlong_to_cubemap(lat, [9, 9])
        clamped = latlong_to_cubemap(lat, [9, 9], "clamp")
        self.assertAlmostEqual(wrapped[2, 4, 4, 1], .5)
        self.assertGreater(clamped[2, 4, 4, 1], .9999)


if __name__ == "__main__":
    unittest.main(verbosity=2)
