"""Static validation: deliberately not called a successful dynamic import."""
import ast
import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
import os
import sys
sys.path.insert(0, str(ROOT / 'scripts'))
from local_config import upstream
UPSTREAM = upstream()
PACKAGE = UPSTREAM / "cosmos_predict1/diffusion/inference/diffusion_renderer_utils"


class PatchTests(unittest.TestCase):
    def test_pinned_commit_and_patch_scope(self):
        commit = json.loads((ROOT / "manifests/upstream.json").read_text())["commit"]
        self.assertEqual(commit, "0f3e2dc435032ecbad654c2fc2153df85384b138")
        text = (ROOT / "patches/replace_hdr_sampling.patch").read_text(encoding="utf-8")
        changed = [line.split()[3][2:] for line in text.splitlines() if line.startswith("diff --git")]
        self.assertEqual(set(changed), {"cosmos_predict1/diffusion/inference/diffusion_renderer_utils/" + name
                         for name in ("rendering_utils.py", "utils_env_proj.py", "env_sampling.py")})

    @unittest.skipUnless(PACKAGE.is_dir(), 'external patched upstream not configured')
    def test_syntax_and_no_nvdiffrast_import_or_dr_calls(self):
        for name in ("rendering_utils.py", "utils_env_proj.py", "env_sampling.py"):
            text = (PACKAGE / name).read_text(encoding="utf-8")
            tree = ast.parse(text)
            compile(tree, str(PACKAGE / name), "exec")
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    self.assertTrue(all(not a.name.startswith("nvdiffrast") for a in node.names))
                if isinstance(node, ast.ImportFrom):
                    self.assertFalse((node.module or "").startswith("nvdiffrast"))
                if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                    self.assertNotEqual(node.value.id, "dr")

    @unittest.skipUnless(PACKAGE.is_dir(), 'external patched upstream not configured')
    def test_replacement_imports_and_three_cube_calls(self):
        rendering = ast.parse((PACKAGE / "rendering_utils.py").read_text(encoding="utf-8"))
        projection = ast.parse((PACKAGE / "utils_env_proj.py").read_text(encoding="utf-8"))
        self.assertTrue(any(isinstance(n, ast.ImportFrom) and n.module == "env_sampling"
                            and any(a.name == "latlong_to_cubemap" for a in n.names) for n in ast.walk(rendering)))
        calls = [n for n in ast.walk(projection) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                 and n.func.id == "sample_cubemap"]
        self.assertEqual(len(calls), 3)
        self.assertEqual((PACKAGE / "env_sampling.py").read_bytes(), (ROOT / "prototype/env_sampling.py").read_bytes())


if __name__ == "__main__":
    unittest.main(verbosity=2)
