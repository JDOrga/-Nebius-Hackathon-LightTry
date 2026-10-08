"""Executable NumPy math model, NOT execution of the PyTorch implementation.

Uses explicit four-tap interpolation; it serves as a specification and analytic
test harness. Agreement with this model alone does not establish torch parity.
"""
import math
import numpy as np


def face_directions(face, s, t):
    one = np.ones_like(s)
    return np.stack(((one, -t, -s), (-one, -t, s), (s, one, t),
                     (s, -one, -t), (s, -t, one), (-s, -t, -one))[face], axis=-1)


def locate(d):
    valid = np.isfinite(d).all(axis=-1) & (np.max(np.abs(d), axis=-1) > 0)
    d = np.where(valid[..., None], d, 0)
    scale = np.max(np.abs(d), axis=-1, keepdims=True)
    d = d / np.where(scale > 0, scale, 1)
    axis = np.argmax(np.abs(d), axis=-1)
    major = np.take_along_axis(d, axis[..., None], axis=-1)[..., 0]
    face = 2 * axis + (major < 0)
    x, y, z = np.moveaxis(d, -1, 0)
    pairs = np.stack([np.stack(p, -1) for p in ((-z, -y), (z, -y), (x, z),
                                               (x, -z), (x, -y), (-x, -y))], -2)
    st = np.take_along_axis(pairs, np.broadcast_to(face[..., None, None], (*face.shape, 1, 2)), -2)[..., 0, :]
    return face, st, valid


def _broadcast(tex, q):
    b = max(tex.shape[0], q.shape[0])
    if tex.shape[0] not in (1, b) or q.shape[0] not in (1, b):
        raise ValueError("batch mismatch")
    return np.broadcast_to(tex, (b, *tex.shape[1:])), np.broadcast_to(q, (b, *q.shape[1:]))


def bilinear_pixels(tex, xy, wrap_x=False, wrap_y=False):
    """BHWC + pixel indices B...2. Centers are integer pixel indices."""
    tex, xy = _broadcast(tex, xy)
    b, h, w, c = tex.shape
    base = np.floor(xy).astype(np.int64)
    frac = xy - base
    batch = np.arange(b).reshape(b, *([1] * (xy.ndim - 2)))
    out = np.zeros((*xy.shape[:-1], c), dtype=np.result_type(tex, xy))
    for dy in (0, 1):
        for dx in (0, 1):
            x, y = base[..., 0] + dx, base[..., 1] + dy
            x = x % w if wrap_x else np.clip(x, 0, w - 1)
            y = y % h if wrap_y else np.clip(y, 0, h - 1)
            weight = (frac[..., 0] if dx else 1 - frac[..., 0]) * (frac[..., 1] if dy else 1 - frac[..., 1])
            out += tex[batch, y, x] * weight[..., None]
    return out


def sample_latlong(tex, uv, latitude_mode="wrap"):
    if latitude_mode not in ("wrap", "clamp"):
        raise ValueError("invalid latitude mode")
    tex, uv = _broadcast(tex, uv)
    valid = np.isfinite(uv).all(axis=-1)
    uv = np.where(valid[..., None], uv, 0)
    q = uv.copy()
    q[..., 0] %= 1
    q[..., 1] = q[..., 1] % 1 if latitude_mode == "wrap" else np.clip(q[..., 1], 0, 1)
    xy = q * np.array([tex.shape[2], tex.shape[1]]) - .5
    out = bilinear_pixels(tex, xy, True, latitude_mode == "wrap")
    return np.where(valid[..., None], out, 0).astype(tex.dtype)


def latlong_to_cubemap(tex, res, latitude_mode="wrap"):
    if len(res) != 2 or res[0] <= 0 or res[0] != res[1]:
        raise ValueError("square positive resolution required")
    single = tex.ndim == 3
    tex = tex[None] if single else tex
    r = res[0]
    p = (np.arange(r) + .5) * (2 / r) - 1
    s, t = np.meshgrid(p, p)
    d = np.stack([face_directions(f, s, t) for f in range(6)])
    d /= np.linalg.norm(d, axis=-1, keepdims=True)
    uv = np.stack((np.arctan2(d[..., 0], -d[..., 2]) / (2 * math.pi) + .5,
                   np.arccos(np.clip(d[..., 1], -1, 1)) / math.pi), -1)
    out = sample_latlong(tex, uv[None], latitude_mode)
    return out[0] if single else out


def _vertex_addresses(face, s, t, r):
    xyz = ((1, -t, -s), (-1, -t, s), (s, 1, t), (s, -1, -t),
           (s, -t, 1), (-s, -t, -1))[face]
    x, y, z = xyz
    projected = ((-z, -y), (z, -y), (x, z), (x, -z), (x, -y), (-x, -y))
    result = []
    for axis, sign in enumerate(xyz):
        f = 2 * axis + int(sign < 0)
        u, v = projected[f]
        result.append((f, 0 if v < 0 else r - 1, 0 if u < 0 else r - 1))
    return result


def pad_cube(cube):
    b, _, r, _, c = cube.shape
    p = np.pad(cube, ((0, 0), (0, 0), (1, 1), (1, 1), (0, 0)))
    centers = (np.arange(r) + .5) * (2 / r) - 1
    outer = np.full_like(centers, 1 + 1 / r)
    ss = np.stack((centers, centers, -outer, outer))
    tt = np.stack((-outer, outer, centers, centers))
    d = np.stack([face_directions(f, ss, tt) for f in range(6)])
    faces, st, _ = locate(d)
    xy = np.clip(np.floor((st + 1) * r / 2).astype(np.int64), 0, r - 1)
    edge = cube[:, faces, xy[..., 1], xy[..., 0], :]
    p[:, :, 0, 1:-1] = edge[:, :, 0]
    p[:, :, -1, 1:-1] = edge[:, :, 1]
    p[:, :, 1:-1, 0] = edge[:, :, 2]
    p[:, :, 1:-1, -1] = edge[:, :, 3]
    for f in range(6):
        for row, t in ((0, -1), (r + 1, 1)):
            for col, s in ((0, -1), (r + 1, 1)):
                p[:, f, row, col] = sum(cube[:, a, y, x] for a, y, x in _vertex_addresses(f, s, t, r)) / 3
    return p


def sample_cubemap(cube, directions):
    cube, d = _broadcast(cube, directions)
    b, faces, r, w, c = cube.shape
    if faces != 6 or r != w:
        raise ValueError("six square faces required")
    face, st, valid = locate(d)
    p = pad_cube(cube).reshape(b, 6 * (r + 2), r + 2, c)
    xy = np.stack(((st[..., 0] + 1) * r / 2 + .5,
                   face * (r + 2) + (st[..., 1] + 1) * r / 2 + .5), -1)
    out = bilinear_pixels(p, xy)
    return np.where(valid[..., None], out, 0).astype(cube.dtype)


def direction_cube(r, dtype=np.float64):
    p = (np.arange(r) + .5) * (2 / r) - 1
    s, t = np.meshgrid(p, p)
    d = np.stack([face_directions(f, s, t) for f in range(6)])
    d /= np.linalg.norm(d, axis=-1, keepdims=True)
    return ((d + 1) / 2)[None].astype(dtype)


def direction_latlong(h, w):
    theta = (np.arange(h) + .5) * math.pi / h
    phi = ((np.arange(w) + .5) / w - .5) * 2 * math.pi
    phi, theta = np.meshgrid(phi, theta)
    d = np.stack((np.sin(theta) * np.sin(phi), np.cos(theta), -np.sin(theta) * np.cos(phi)), -1)
    return (d + 1) / 2
