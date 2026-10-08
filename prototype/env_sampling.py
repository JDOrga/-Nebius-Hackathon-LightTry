"""Independent, base-level HDR samplers using PyTorch tensors and grid_sample.

Array rows follow the caller's storage order: v=0 addresses row 0. No implicit
vertical flip, tone mapping, clipping, mipmapping or gamma conversion is applied.
Cube faces are +X,-X,+Y,-Y,+Z,-Z, with the orientation used by the fixed caller.
This is a prototype, not a claim of bitwise equivalence to another operator.
"""
import math

import torch
import torch.nn.functional as F


def _working_dtype(t):
    if t.dtype not in (torch.float16, torch.bfloat16, torch.float32, torch.float64):
        raise TypeError("texture must have a supported floating dtype")
    return torch.float64 if t.dtype == torch.float64 else torch.float32


def _batch(tex, query, rank, channels):
    if tex.ndim != rank or query.ndim < 3 or query.shape[-1] != channels:
        raise ValueError("invalid texture/query shape (queries need an explicit batch)")
    if tex.device != query.device:
        raise ValueError("texture and queries must share a device")
    if not query.is_floating_point():
        raise TypeError("queries must be floating point")
    if any(n <= 0 for n in tex.shape) or any(n <= 0 for n in query.shape):
        raise ValueError("empty dimensions are unsupported")
    b = max(tex.shape[0], query.shape[0])
    if tex.shape[0] not in (1, b) or query.shape[0] not in (1, b):
        raise ValueError("batch sizes must match or be one")
    dtype = _working_dtype(tex)
    return tex.to(dtype).expand(b, *tex.shape[1:]), query.to(dtype).expand(b, *query.shape[1:])


def face_directions(face, s, t):
    """Unnormalized direction for face-plane coordinates in [-1,1]."""
    one = torch.ones_like(s)
    components = ((one, -t, -s), (-one, -t, s), (s, one, t),
                  (s, -one, -t), (s, -t, one), (-s, -t, -one))
    if face not in range(6):
        raise ValueError("face must be 0..5")
    return torch.stack(components[face], dim=-1)


def _locate(d):
    valid = torch.isfinite(d).all(dim=-1) & (d.abs().amax(dim=-1) > 0)
    d = torch.where(valid[..., None], d, torch.zeros_like(d))
    scale = d.abs().amax(dim=-1, keepdim=True)
    d = d / torch.where(scale > 0, scale, torch.ones_like(scale))
    axis = d.abs().argmax(dim=-1)  # deterministic X, then Y, then Z tie priority
    major = torch.gather(d, -1, axis[..., None])[..., 0]
    face = axis * 2 + (major < 0).long()
    x, y, z = d.unbind(dim=-1)
    candidates = torch.stack((torch.stack((-z, -y), -1), torch.stack((z, -y), -1),
                              torch.stack((x, z), -1), torch.stack((x, -z), -1),
                              torch.stack((x, -y), -1), torch.stack((-x, -y), -1)), -2)
    st = torch.gather(candidates, -2, face[..., None, None].expand(*face.shape, 1, 2))[..., 0, :]
    return face, st, valid


def sample_latlong(texture, uv, latitude_mode="wrap"):
    """BHWC texture + B...2 UV -> B...C; U wraps, V wraps or clamps.

    UV texel centers are ((j+.5)/W,(i+.5)/H). The wrap default preserves
    the fixed upstream call's two-axis wrap, including its pole blending.
    Invalid UV returns zero. Finite texture data is a caller precondition.
    """
    if latitude_mode not in ("wrap", "clamp"):
        raise ValueError("latitude_mode must be wrap or clamp")
    original_dtype = texture.dtype
    tex, q = _batch(texture, uv, 4, 2)
    b, h, w, c = tex.shape
    valid = torch.isfinite(q).all(dim=-1)
    q = torch.where(valid[..., None], q, torch.zeros_like(q))
    u = torch.remainder(q[..., 0], 1)
    v = torch.remainder(q[..., 1], 1) if latitude_mode == "wrap" else q[..., 1].clamp(0, 1)
    p = tex.permute(0, 3, 1, 2)
    p = torch.cat((p[..., -1:], p, p[..., :1]), dim=-1)
    if latitude_mode == "wrap":
        p = torch.cat((p[..., -1:, :], p, p[..., :1, :]), dim=-2)
    else:
        p = torch.cat((p[..., :1, :], p, p[..., -1:, :]), dim=-2)
    grid = torch.stack((2 * (u * w + 1) / (w + 2) - 1,
                        2 * (v * h + 1) / (h + 2) - 1), dim=-1)
    out = F.grid_sample(p, grid.reshape(b, 1, -1, 2), mode="bilinear",
                        padding_mode="border", align_corners=False)
    out = out[:, :, 0, :].transpose(1, 2).reshape(*q.shape[:-1], c)
    return torch.where(valid[..., None], out, torch.zeros_like(out)).to(original_dtype).contiguous()


def latlong_to_cubemap(latlong_map, res, latitude_mode="wrap"):
    """HWC or BHWC -> 6RRC or B6RRC; preserves input dtype/device."""
    if len(res) != 2 or not all(isinstance(n, int) and n > 0 for n in res) or res[0] != res[1]:
        raise ValueError("cubemap resolution must be two positive equal integers")
    single = latlong_map.ndim == 3
    tex = latlong_map.unsqueeze(0) if single else latlong_map
    if tex.ndim != 4:
        raise ValueError("latlong_map must be HWC or BHWC")
    dtype = _working_dtype(tex)
    r = res[0]
    p = (torch.arange(r, device=tex.device, dtype=dtype) + .5) * (2 / r) - 1
    t, s = torch.meshgrid(p, p, indexing="ij")
    d = torch.stack([face_directions(f, s, t) for f in range(6)])
    d = d / torch.linalg.vector_norm(d, dim=-1, keepdim=True)
    uv = torch.stack((torch.atan2(d[..., 0], -d[..., 2]) / (2 * math.pi) + .5,
                      torch.acos(d[..., 1].clamp(-1, 1)) / math.pi), dim=-1)
    cube = sample_latlong(tex, uv.unsqueeze(0), latitude_mode)
    return cube[0] if single else cube


def _corner_addresses(face, s, t, r):
    # Pure geometry: three texels meeting at the geometric cube vertex.
    xyz = ((1, -t, -s), (-1, -t, s), (s, 1, t), (s, -1, -t),
           (s, -t, 1), (-s, -t, -1))[face]
    x, y, z = xyz
    projected = ((-z, -y), (z, -y), (x, z), (x, -z), (x, -y), (-x, -y))
    addresses = []
    for axis, value in enumerate(xyz):
        f = 2 * axis + int(value < 0)
        u, v = projected[f]
        addresses.append((f, 0 if v < 0 else r - 1, 0 if u < 0 else r - 1))
    return addresses


def _pad_cube(cube):
    """One-texel gutters: adjacent nearest centers, three-face corner mean.

    Only O(R) geometry is built. The face interiors are copied into an atlas.
    This independently chosen corner rule is explicitly part of this sampler.
    """
    b, _, r, _, c = cube.shape
    p = F.pad(cube.permute(0, 1, 4, 2, 3).reshape(b * 6, c, r, r), (1, 1, 1, 1))
    p = p.reshape(b, 6, c, r + 2, r + 2).permute(0, 1, 3, 4, 2)
    centers = (torch.arange(r, device=cube.device, dtype=cube.dtype) + .5) * (2 / r) - 1
    outer = torch.full_like(centers, 1 + 1 / r)
    ss = torch.stack((centers, centers, -outer, outer))
    tt = torch.stack((-outer, outer, centers, centers))
    d = torch.stack([face_directions(f, ss, tt) for f in range(6)])
    faces, st, _ = _locate(d)
    xy = torch.floor((st + 1) * r / 2).long().clamp(0, r - 1)
    edge = cube[:, faces, xy[..., 1], xy[..., 0], :]
    p[:, :, 0, 1:-1, :] = edge[:, :, 0]
    p[:, :, -1, 1:-1, :] = edge[:, :, 1]
    p[:, :, 1:-1, 0, :] = edge[:, :, 2]
    p[:, :, 1:-1, -1, :] = edge[:, :, 3]
    for f in range(6):
        for row, t in ((0, -1), (r + 1, 1)):
            for col, s in ((0, -1), (r + 1, 1)):
                addresses = _corner_addresses(f, s, t, r)
                p[:, f, row, col] = sum(cube[:, a, y, x] for a, y, x in addresses) / 3
    return p


def sample_cubemap(texture, directions):
    """B6RRC + B...3 directions -> B...C, with batch-one broadcasting.

    Square faces, base-level bilinear filtering only. Zero/nonfinite directions
    return zero. Half/bfloat16 arithmetic is promoted to float32, then restored.
    Face selection is discrete; gradient equivalence at seams is not promised.
    """
    original_dtype = texture.dtype
    cube, d = _batch(texture, directions, 5, 3)
    b, faces, r, w, c = cube.shape
    if faces != 6 or r != w:
        raise ValueError("cubemap must have six square faces")
    face, st, valid = _locate(d)
    p = _pad_cube(cube)
    atlas = p.permute(0, 4, 1, 2, 3).reshape(b, c, 6 * (r + 2), r + 2)
    x = 2 * (((st[..., 0] + 1) * r / 2) + 1) / (r + 2) - 1
    y = 2 * (face * (r + 2) + ((st[..., 1] + 1) * r / 2) + 1) / (6 * (r + 2)) - 1
    grid = torch.stack((x, y), dim=-1).reshape(b, 1, -1, 2)
    out = F.grid_sample(atlas, grid, mode="bilinear", padding_mode="border", align_corners=False)
    out = out[:, :, 0, :].transpose(1, 2).reshape(*d.shape[:-1], c)
    return torch.where(valid[..., None], out, torch.zeros_like(out)).to(original_dtype).contiguous()
