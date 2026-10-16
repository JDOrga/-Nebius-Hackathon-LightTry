import concurrent.futures
import tempfile
from pathlib import Path
import unittest
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scope_issuer import ScopeIssuer

class ScopeTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.now=1000
  self.policy=dict(enabled=True,resourceId='fixture-resource',budgetUsdIncludingTax=3,hourlyUsdIncludingTax=6,billingReserveSeconds=120,maxSessionSeconds=2400,idleSeconds=60)
  self.make=lambda:ScopeIssuer(self.root,self.policy,clock=lambda:self.now)
 def tearDown(self):self.tmp.cleanup()
 def test_constructor_has_no_issuance_or_cloud_side_effect(self):
  issuer=self.make()
  with issuer.db() as db:self.assertEqual(db.execute('SELECT count(*) FROM requests').fetchone()[0],0)
 def test_exact_scope_and_budget_reserve(self):
  v=self.make().issue('a'*32,'operator',approved=True)
  self.assertEqual(v['scope']['expiresAt'],2680);self.assertFalse(v['hostConfirmed']);self.assertFalse(v['modelLicenseAck']);self.assertFalse(v['budgetHardCap'])
  self.assertEqual(set(v['scope']),{'scopeId','resourceId','expiresAt','budgetApproved','idleSeconds','simulation'})
 def test_restart_replay_never_extends_and_new_click_is_new(self):
  a=self.make().issue('a'*32,'operator',approved=True);self.now+=10
  self.assertEqual(self.make().issue('a'*32,'operator',approved=True),a)
  self.assertNotEqual(self.make().issue('b'*32,'operator',approved=True)['scope']['scopeId'],a['scope']['scopeId'])
 def test_concurrent_click_single_scope(self):
  self.make()
  with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:values=list(pool.map(lambda _:self.make().issue('a'*32,'operator',approved=True),range(12)))
  self.assertEqual(len({v['scope']['scopeId'] for v in values}),1)
 def test_denials(self):
  for approved in [False,None,1]:
   with self.assertRaises(ValueError):self.make().issue('a'*32,'operator',approved=approved)
  for key,value in [('enabled',False),('hourlyUsdIncludingTax',None),('hourlyUsdIncludingTax',float('nan')),('budgetUsdIncludingTax',0.01),('idleSeconds',301),('billingReserveSeconds',0)]:
   p={**self.policy,key:value}
   with self.assertRaises(ValueError):ScopeIssuer(self.root,p).issue('a'*32,'operator',approved=True)
 def test_owner_policy_expiry_and_clock_do_not_rebind(self):
  v=self.make().issue('a'*32,'operator',approved=True)
  with self.assertRaisesRegex(ValueError,'BINDING'):self.make().issue('a'*32,'other',approved=True)
  with self.assertRaisesRegex(ValueError,'BINDING'):ScopeIssuer(self.root,{**self.policy,'idleSeconds':90},clock=lambda:self.now).issue('a'*32,'operator',approved=True)
  self.now=999
  with self.assertRaisesRegex(ValueError,'CLOCK'):self.make().issue('a'*32,'operator',approved=True)
  self.now=v['scope']['expiresAt']
  with self.assertRaisesRegex(ValueError,'EXPIRED'):self.make().issue('a'*32,'operator',approved=True)

if __name__=='__main__':unittest.main()
