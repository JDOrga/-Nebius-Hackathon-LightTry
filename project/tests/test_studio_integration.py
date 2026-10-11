"""Offline studio integration guards. Browser evidence remains separate."""
import unittest,sys,tempfile,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tests'))
from run_candidate_offline import run
from freeze_language_candidate import snapshot
class StudioIntegrationTests(unittest.TestCase):
 def test_missing_explicit_manifest_refused(self):
  with tempfile.TemporaryDirectory() as t:self.assertEqual(run(Path(t)/'out.json',Path(t)/'missing.json'),2)
 def test_mismatch_manifest_refused(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'snapshot.json';p.write_text(json.dumps({'candidateSHA256':'wrong'}));self.assertEqual(run(Path(t)/'out.json',p),2)
 def test_no_simulation_controls_in_formal_frontend(self):
  h=(ROOT/'next/web/index.html').read_text(encoding='utf-8');self.assertNotIn('run-state',h);self.assertNotIn('scenario',h);self.assertIn('generate-dialog',h)
 def test_no_new_dependencies_or_default_paid_configuration(self):
  s=(ROOT/'start_studio.py').read_text(encoding='utf-8');self.assertNotIn('--inference-config',s);self.assertNotIn('--language-key-file',s);self.assertIn('from next.server import main',s)
 def test_snapshot_source_hash_matches_current(self):
  import hashlib
  v=snapshot();self.assertEqual(v['filesSHA256']['project/server.py'],hashlib.sha256((ROOT/'server.py').read_bytes()).hexdigest());self.assertEqual(v['modelAcceptance'],'not-tested')
if __name__=='__main__':unittest.main()
