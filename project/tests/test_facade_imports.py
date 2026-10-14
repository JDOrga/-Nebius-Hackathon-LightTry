import sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'project'))
from runtime.worker import install_legacy_imports
class FacadeImportTests(unittest.TestCase):
 def test_standalone_legacy_import_resolves_exact_bundled_module(self):
  from inference import weights_reuse
  saved=sys.modules.pop('weights_reuse',None)
  try:
   install_legacy_imports();import weights_reuse as direct
   self.assertIs(direct,weights_reuse);self.assertEqual(Path(direct.__file__).resolve(),ROOT/'project/inference/weights_reuse.py')
  finally:
   sys.modules.pop('weights_reuse',None)
   if saved is not None:sys.modules['weights_reuse']=saved
 def test_unknown_existing_module_is_not_overwritten(self):
  from types import SimpleNamespace
  saved=sys.modules.get('weights_reuse');sys.modules['weights_reuse']=SimpleNamespace(__file__='/UNTRUSTED/weights_reuse.py')
  try:
   with self.assertRaises(ValueError):install_legacy_imports()
  finally:
   sys.modules.pop('weights_reuse',None)
   if saved is not None:sys.modules['weights_reuse']=saved
if __name__=='__main__':unittest.main()
