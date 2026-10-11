"""CPU identity foundation; NOT a product-path or GPU acceptance test."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'project'))
import lighting


class LightingIdentityTests(unittest.TestCase):
    def setUp(self):
        self.presets = {p['id']: p for p in json.loads((ROOT / 'project/data/catalog.json').read_text())['presets']}
        self.value = {'schemaVersion': 1, 'planId': 'a'*32, 'version': 1,
            'name': '我的晴日方案', 'parameters': {'environmentId': 'sunny', 'offsetDeg': 0, 'strength': 1},
            'inputId': 'b'*32, 'parentVersion': None}
        self.cap = {'revision': 'OFFLINE_SYNTHETIC_NOT_PRODUCT', 'approvedVariants': {'sunny': [[0, .7], [0, 1.4]]}}

    def test_controls_remain_closed_until_explicit_evidence(self):
        self.value['parameters']['strength'] = 1.4
        with self.assertRaises(ValueError): lighting.normalize_scheme(self.value, self.presets)
        scheme = lighting.normalize_scheme(self.value, self.presets, self.cap)
        self.assertEqual(scheme['parameters']['capabilityRevision'], self.cap['revision'])
        self.value['parameters']['environmentId'] = 'street'
        with self.assertRaises(ValueError): lighting.normalize_scheme(self.value, self.presets, self.cap)

    def test_exact_types_combinations_and_unknown_fields(self):
        for update in [{'offsetDeg': True}, {'strength': '1.4'}, {'strength': float('nan')},
                       {'offsetDeg': 45, 'strength': .7}, {'EV': 2}, {'temperature': 3200}]:
            bad = copy.deepcopy(self.value); bad['parameters'].update(update)
            with self.subTest(update=update), self.assertRaises(ValueError):
                lighting.normalize_scheme(bad, self.presets, self.cap)

    def test_parameter_change_changes_identity_not_name(self):
        base = lighting.normalize_scheme(self.value, self.presets)
        other = copy.deepcopy(self.value); other['name'] = '另一个名字'
        self.assertEqual(base['recipeKey'], lighting.normalize_scheme(other, self.presets)['recipeKey'])
        other['parameters']['strength'] = 1.4; other['version'] = 2; other['parentVersion'] = 1
        modified = lighting.normalize_scheme(other, self.presets, self.cap)
        self.assertNotEqual(base['recipeKey'], modified['recipeKey'])
        self.assertNotEqual(lighting.idempotency_fingerprint(base, 'c'*64),
                            lighting.idempotency_fingerprint(modified, 'c'*64))

    def test_result_affinity_input_versions_and_processing(self):
        scheme = lighting.normalize_scheme(self.value, self.presets)
        inp = {'id': 'b'*32, 'sha256': 'c'*64, 'canvas': {'rgbSha256': 'd'*64, 'preprocessingVersion': 'test'}}
        proc = {k: 'SYNTHETIC' for k in ('upstreamCommit', 'forwardModel', 'tokenizer', 'patch', 'adapterVersion')}
        proc.update(seed=1000, steps=15, guidance=0, width=1280, height=704, frames=1)
        first = lighting.result_binding(scheme, inp, proc)
        changed = copy.deepcopy(proc); changed['adapterVersion'] = 'SYNTHETIC_v2'
        self.assertNotEqual(first['resultKey'], lighting.result_binding(scheme, inp, changed)['resultKey'])
        inp['id'] = 'e'*32
        with self.assertRaises(ValueError): lighting.result_binding(scheme, inp, proc)
        scheme['inputId'] = inp['id']
        self.assertNotEqual(first['resultKey'], lighting.result_binding(scheme, inp, proc)['resultKey'])

    def test_legacy_describes_without_rewriting_evidence(self):
        descriptor = lighting.legacy_compatibility('sunny', self.presets)
        self.assertFalse(descriptor['controlParametersMeasured'])
        self.assertEqual(descriptor['eligibleOnlyFor']['strength'], 1)
        self.assertEqual(lighting.canonical({'b': 1.0, 'a': 0.0}), '{"a":0,"b":1}')


if __name__ == '__main__': unittest.main()
