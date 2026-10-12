"""Four new forwards only: two missing azimuths, two equal-emitted-energy widths."""
import copy
from light_console import synthesize, encode_hdr, decode_hdr, normalize
from next.runtime.joint import matrix, energy

VERSION = 'direction-energy-key-unknowns-v1'


def recipes(environments):
    base = matrix(environments)['C']  # actual 135deg case, not a brighter-intensity rule
    target = energy(decode_hdr(encode_hdr(synthesize(base))))['sphericalIntegralRGB'][0]
    out = {}
    for azimuth in (225, 315):
        p = copy.deepcopy(base); p['zones'][0]['azimuthDeg'] = azimuth
        out['direction-' + str(azimuth)] = normalize(p, environments)
    for width in (45, 70):
        p = copy.deepcopy(base); p['zones'][0]['sizeDeg'] = width
        lo, hi = 0., 3.
        # Account for actual RGBE quantization, not just analytic Gaussian area.
        candidates = []
        for _ in range(24):
            strength = (lo + hi) / 2; p['zones'][0]['strength'] = strength
            actual = energy(decode_hdr(encode_hdr(synthesize(p))))['sphericalIntegralRGB'][0]
            candidates.append((abs(actual-target),strength))
            if actual < target:lo = strength
            else:hi = strength
        p['zones'][0]['strength'] = min(candidates)[1]
        out['width-' + str(width)] = normalize(p, environments)
        actual = energy(decode_hdr(encode_hdr(synthesize(out['width-' + str(width)]))))['sphericalIntegralRGB'][0]
        if abs(actual / target - 1) > .005:
            raise ValueError('ENERGY_CONTROL_TOLERANCE_FAILED')
    return out
