"""Offline checks of recovery, actual upstream CLI parsing, and acceptance failures."""
import argparse
import ast
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
import os
import sys
sys.path.insert(0, str(ROOT / 'scripts'))
from local_config import upstream
UPSTREAM = upstream()
sys.path.insert(0, str(ROOT / "scripts"))
import weights
import run_experiment
import validate_outputs


class Response(io.BytesIO):
    def __init__(self, data, status=200, headers=None):
        super().__init__(data)
        self.status = status
        self.headers = headers or {}


class PreparationTests(unittest.TestCase):
    def entry(self, data):
        return {"size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                "git_blob": None, "md5": hashlib.md5(data).hexdigest(),
                "url": "https://huggingface.co/nvidia/fixed/resolve/pinned/model.pt"}

    def test_resume_206_and_streaming_verification(self):
        data = bytes(range(256)) * 19
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            path = Path(temp) / "model.pt"
            path.with_suffix(".pt.part").write_bytes(data[:137])
            def opener(request, **kw):
                self.assertEqual(request.headers["Range"], "bytes=137-")
                return Response(data[137:], 206, {"Content-Range": f"bytes 137-{len(data)-1}/{len(data)}"})
            weights.transfer(path, self.entry(data), time.time() + 60, opener)
            self.assertTrue(weights.verify(path, self.entry(data)))
            self.assertFalse(path.with_suffix(".pt.part").exists())

    def test_ignored_range_retains_partial(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            path = Path(temp) / "model.pt"
            part = path.with_suffix(".pt.part")
            part.write_bytes(b"123")
            with self.assertRaises(ValueError):
                weights.transfer(path, self.entry(b"123456"), time.time() + 60,
                                 lambda *a, **kw: Response(b"123456"))
            self.assertEqual(part.read_bytes(), b"123")

    def test_truncated_then_resume(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            path = Path(temp) / "model.pt"
            with self.assertRaises(OSError):
                weights.transfer(path, self.entry(b"abcdef"), time.time() + 60,
                                 lambda *a, **kw: Response(b"abc"))
            weights.transfer(path, self.entry(b"abcdef"), time.time() + 60,
                             lambda *a, **kw: Response(b"def", 206, {"Content-Range": "bytes 3-5/6"}))
            self.assertEqual(path.read_bytes(), b"abcdef")

    def test_corruption_retained_and_deadline_blocks(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            path = Path(temp) / "model.pt"
            with self.assertRaises(ValueError):
                weights.transfer(path, self.entry(b"good"), time.time() + 60,
                                 lambda *a, **kw: Response(b"evil"))
            self.assertFalse(path.exists())
            self.assertEqual(path.with_suffix(".pt.part").read_bytes(), b"evil")
            with self.assertRaises(TimeoutError):
                weights.check_time(time.time() - 1)

    def test_empty_partial_can_resume(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            path = Path(temp) / "model.pt"
            path.with_suffix(".pt.part").touch()
            weights.transfer(path, self.entry(b"data"), time.time() + 60,
                             lambda *a, **kw: Response(b"data"))
            self.assertTrue(weights.verify(path, self.entry(b"data")))

    def test_git_blob_verification(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            path = Path(temp) / "config.json"
            path.write_bytes(b"{}")
            entry = {"size": 2, "git_blob": hashlib.sha1(b"blob 2\0{}").hexdigest()}
            self.assertTrue(weights.verify(path, entry))
            entry["git_blob"] = "0" * 40
            self.assertFalse(weights.verify(path, entry))

    @unittest.skipUnless(UPSTREAM.is_dir(), 'external pinned upstream not configured')
    def test_actual_upstream_parsers_accept_planned_commands(self):
        args = argparse.Namespace(checkpoint_dir=ROOT / "checkpoints", run_dir=ROOT / "runs/test",
                                  height=704, width=1280, offload=False, input_dir=ROOT / ".local/inputs")
        cmds = run_experiment.commands(args)
        common = ast.parse((UPSTREAM / "cosmos_predict1/diffusion/inference/inference_utils.py").read_text())
        function = next(n for n in common.body if isinstance(n, ast.FunctionDef) and n.name == "add_common_arguments")
        for command in cmds:
            module = ast.parse((UPSTREAM / command[2]).read_text())
            nodes = [function] + [n for n in module.body if isinstance(n, ast.FunctionDef) and n.name in ("str2bool", "parse_arguments")]
            namespace = {"argparse": argparse}
            exec(compile(ast.Module(body=nodes, type_ignores=[]), "upstream_parser", "exec"), namespace)
            with patch.object(sys, "argv", [command[2]] + command[3:]):
                parsed = namespace["parse_arguments"]()
            self.assertEqual(parsed.num_video_frames, 1)
            self.assertEqual(parsed.num_steps, 15)
            self.assertTrue(parsed.save_image)
        self.assertEqual(parsed.envlight_ind, [0, 1, 2])
        self.assertTrue(parsed.use_custom_envmap)

    def test_missing_gbuffers_and_identical_lighting_rejected(self):
        from PIL import Image
        import numpy as np
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            root = Path(temp)
            with self.assertRaises(ValueError):
                validate_outputs.validate_inverse(root, 16, 32)
            values = np.arange(16*32*3, dtype=np.uint8).reshape(16, 32, 3)
            for index in range(3):
                folder = root / f"relit_frames_{index:04d}"
                folder.mkdir()
                Image.fromarray(values).save(folder / "image.jpg")
            with self.assertRaises(ValueError):
                validate_outputs.validate_forward(root, 16, 32)

    def test_constant_material_channels_are_warnings_but_other_checks_remain(self):
        from PIL import Image
        import numpy as np
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            frames = root / 'gbuffer_frames'
            frames.mkdir()
            values = np.arange(16 * 32 * 3, dtype=np.uint8).reshape(16, 32, 3)
            for label in validate_outputs.PASSES:
                pixels = np.zeros_like(values) if label in ('roughness', 'metallic') else values
                Image.fromarray(pixels).save(frames / ('image.' + label + '.jpg'))
            records = validate_outputs.validate_inverse(root, 16, 32)
            self.assertEqual(sum(bool(r.get('warnings')) for r in records), 2)
            Image.new('RGB', (32, 16)).save(frames / 'image.basecolor.jpg')
            with self.assertRaisesRegex(ValueError, 'constant output'):
                validate_outputs.validate_inverse(root, 16, 32)
            Image.fromarray(values).save(frames / 'image.basecolor.jpg')
            Image.new('RGB', (16, 16)).save(frames / 'image.metallic.jpg')
            with self.assertRaisesRegex(ValueError, 'size/mode'):
                validate_outputs.validate_inverse(root, 16, 32)

    @unittest.skipUnless(UPSTREAM.is_dir(), 'external pinned upstream not configured')
    def test_manifest_is_immutable_official_and_matches_prior_md5(self):
        manifest = json.loads((ROOT / "manifests/weights_manifest.json").read_text())
        self.assertEqual(manifest["total_bytes"], sum(f["size"] for f in manifest["files"]))
        source = ast.parse((UPSTREAM / "scripts/download_diffusion_renderer_checkpoints.py").read_text())
        original = next(ast.literal_eval(n.value) for n in source.body if isinstance(n, ast.Assign)
                        and any(isinstance(t, ast.Name) and t.id == "MD5_CHECKSUM_LOOKUP" for t in n.targets))
        for entry in manifest["files"]:
            self.assertTrue(entry["url"].startswith("https://huggingface.co/nvidia/"))
            self.assertEqual(len(entry["revision"]), 40)
            if entry.get("md5"):
                self.assertEqual(entry["md5"], original[entry["path"]])


if __name__ == "__main__":
    unittest.main(verbosity=2)
