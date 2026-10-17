import unittest,sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from gpu_monitoring import public_failure
class WebErrorTests(unittest.TestCase):
 def test_remote_error_not_loading_and_warns_cost(self):
  v=public_failure({'state':'LOADING'},{'stage':'uncertain','error':'BOOTSTRAP_REMOTE_UNCERTAIN'},True)
  self.assertTrue(v['active']);self.assertIn('指纹',v['detail']);self.assertIn('计费',v['cost'])
 def test_preflight_stage_and_unknown_reason(self):
  v=public_failure({'startFailure':{'stage':'bootstrap_preflight','code':'PRIVATE_SECRET'},'error':'START_OR_PREFLIGHT_UNCERTAIN'},{},True)
  self.assertEqual(v['stage'],'bootstrap_preflight');self.assertNotIn('PRIVATE_SECRET',json.dumps(v))
 def test_released_error_is_historical(self):
  v=public_failure({'verifiedStopped':True,'instancesEmpty':True},{'stage':'uncertain'},True)
  self.assertFalse(v['active']);self.assertIn('释放',v['cost'])
 def test_stale_is_not_safe_stop(self):
  v=public_failure({'state':'READY'},{},False);self.assertTrue(v['active'])
 def test_ready_no_error(self):self.assertIsNone(public_failure({'state':'READY'},{'stage':'deployed'},True))
