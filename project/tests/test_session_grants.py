"""Session grant lifecycle with synthetic host and policy; no cloud/model."""
import copy,json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scope_issuer import ScopeIssuer
from session_grants import SessionGrantIssuer
from model_contract import grant_file

class SessionGrantTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.now=1000
  self.policy=dict(enabled=True,resourceId='fixture',budgetUsdIncludingTax=3,hourlyUsdIncludingTax=6,billingReserveSeconds=120,maxSessionSeconds=2400,idleSeconds=60)
  issuer=ScopeIssuer(self.root/'approvals',self.policy,clock=lambda:self.now);scope=issuer.issue('a'*32,'operator',approved=True)['scope']
  self.state=dict(sessionId='b'*32,scopeId=scope['scopeId'],resourceId='fixture',state='LOADING',stopSent=False,hostConfirmed=True,hostIdentity={'vmId':'fixture-current'},lastObservedAt=self.now,workDeadline=2000,absoluteDeadline=2400,idleDeadline=1300)
  self.control=SimpleNamespace(scope=scope,scope_issuer=issuer,sessions=SimpleNamespace(root=self.root/'guard',get=lambda sid:copy.deepcopy(self.state)))
  (self.root/'guard').mkdir();self.path=self.root/'current.json';self.make=lambda:SessionGrantIssuer(self.control,self.path,{'schemaVersion':1,'modelLicenseAck':True,'maxJobs':20},clock=lambda:self.now)
 def tearDown(self):self.tmp.cleanup()
 def test_new_exact_v2_grant_and_restart_retains_signing_identity(self):
  a=self.make().ensure('b'*32);raw=self.path.read_bytes();self.now+=1;self.state['lastObservedAt']=self.now
  b=self.make().ensure('b'*32);self.assertEqual(a,b);self.assertEqual(raw,self.path.read_bytes())
  self.assertEqual(a['expiresAt'],2000);self.assertEqual(a['jobAuthorization']['owner'],'operator');self.assertEqual(a['budgetUsdIncludingTax'],3)
  self.assertEqual(grant_file(self.path,'b'*32,'fixture',clock=lambda:self.now),a)
 def test_unconfirmed_stale_stop_expired_and_wrong_session_rejected(self):
  original=copy.deepcopy(self.state)
  for k,v in [('hostConfirmed',False),('lastObservedAt',900),('stopSent',True),('workDeadline',999),('sessionId','c'*32),('idleDeadline',999)]:
   self.state=copy.deepcopy(original);self.state[k]=v
   with self.assertRaises(ValueError):self.make().ensure('b'*32)
   self.assertFalse(self.path.exists())
 def test_license_policy_explicit_and_no_creation_in_constructor(self):
  self.make();self.assertFalse(self.path.exists())
  with self.assertRaises(ValueError):SessionGrantIssuer(self.control,self.path,{'schemaVersion':1,'modelLicenseAck':False,'maxJobs':20})
 def test_missing_click_changed_policy_and_foreign_owner_not_rebound(self):
  self.control.scope={**self.control.scope,'scopeId':'c'*32};self.state['scopeId']='c'*32
  with self.assertRaises(ValueError):self.make().ensure('b'*32)
  self.assertFalse(self.path.exists())
 def test_modified_deleted_current_grant_not_silently_recreated(self):
  self.make().ensure('b'*32);g=json.loads(self.path.read_text());g['hostConfirmed']=False;self.path.write_text(json.dumps(g))
  with self.assertRaises(ValueError):self.make().ensure('b'*32)
  self.path.unlink()
  with self.assertRaises(ValueError):self.make().ensure('b'*32)
 def test_new_session_has_new_key_and_old_grant_is_preserved(self):
  first=self.make().ensure('b'*32);old=(self.root/'guard/model-grants'/('b'*32+'.json')).read_bytes()
  self.control.scope=self.control.scope_issuer.issue('d'*32,'operator',approved=True)['scope']
  self.state.update(sessionId='e'*32,scopeId=self.control.scope['scopeId'],hostConfirmed=False)
  with self.assertRaises(ValueError):self.make().ensure('e'*32)
  self.assertEqual(json.loads(self.path.read_text()),first)
  self.state.update(hostConfirmed=True,hostIdentity={'vmId':'new-current'})
  second=self.make().ensure('e'*32)
  self.assertNotEqual(first['jobAuthorization']['keyHex'],second['jobAuthorization']['keyHex'])
  self.assertNotEqual(first['approvalReference'],second['approvalReference'])
  self.assertEqual(old,(self.root/'guard/model-grants'/('b'*32+'.json')).read_bytes())
 def test_changed_host_does_not_rotate_key_or_extend_grant(self):
  self.make().ensure('b'*32);raw=self.path.read_bytes();self.state['hostIdentity']={'vmId':'other'}
  with self.assertRaises(ValueError):self.make().ensure('b'*32)
  self.assertEqual(raw,self.path.read_bytes())

class BootstrapGrantHandoffTests(unittest.TestCase):
 def test_confirmed_guard_creates_grant_before_single_deploy(self):
  import test_gpu_bootstrap_link as fixtures
  from unittest.mock import Mock
  fixtures.BootstrapTests.setUpClass()
  f=fixtures.BootstrapTests();f.setUp()
  try:
   f.confirmed();grant_path=f.root/'grant.json';grant_path.unlink()
   def ensure(sid):
    self.assertEqual(sid,f.sid);self.assertTrue(f.value['hostConfirmed'])
    grant_path.write_text(json.dumps(f.grant));grant_path.chmod(0o600)
   f.control.model_grant_issuer=SimpleNamespace(ensure=Mock(side_effect=ensure))
   f.bootstrap.step(f.value);f.bootstrap.thread.join(5)
   f.control.model_grant_issuer.ensure.assert_called_once_with(f.sid)
   self.assertEqual(json.loads((f.bootstrap.directory(f.sid)/'status.json').read_text())['stage'],'deployed')
   f.bootstrap.spawn.assert_called_once()
  finally:f.tearDown();fixtures.BootstrapTests.tearDownClass()

if __name__=='__main__':unittest.main()
