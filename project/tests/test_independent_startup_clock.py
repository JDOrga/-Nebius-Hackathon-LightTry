import unittest,sys,tempfile,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_worker_guard import GuardTests
from scope_issuer import ScopeIssuer
class IndependentClockTests(unittest.TestCase):
 def test_late_running_gets_entire_post_running_windows(self):
  f=GuardTests();f.setUp();self.addCleanup(f.tearDown);f.scope['expiresAt']=f.clock()+5520
  v=f.sessions.start(f.scope);sid=v['sessionId'];start=f.clock();self.assertEqual(v['startupDeadline'],start+1800)
  f.clock.step(1790);f.sessions.heartbeat(sid);f.provider.state='RUNNING';v=f.sessions.poll(sid)
  for key,seconds in [('workDeadline',3600),('stopDeadline',3600),('verifyDeadline',3720)]:self.assertEqual(v[key]-v['runningAt'],seconds)
  self.assertEqual(v['absoluteDeadline'],start+5520)
  f.sessions.confirm_host(sid,'HOST_FIXTURE_CURRENT');f.peer.model='ready';f.clock.step(30);f.sessions.heartbeat(sid);v=f.sessions.poll(sid);self.assertEqual(v['runningAt'],start+1790);self.assertEqual(v['workDeadline'],start+5390)
 def test_budget_still_caps_scope(self):
  with tempfile.TemporaryDirectory() as t:
   p={'enabled':True,'resourceId':'FIXTURE','budgetUsdIncludingTax':3,'hourlyUsdIncludingTax':1.7343,'billingReserveSeconds':120,'maxSessionSeconds':3600,'idleSeconds':300};issuer=ScopeIssuer(Path(t),p);self.assertEqual(issuer.limits(),3600)
   issuer.policy['budgetUsdIncludingTax']=.5;self.assertLess(issuer.limits(),1800)
if __name__=='__main__':unittest.main()
