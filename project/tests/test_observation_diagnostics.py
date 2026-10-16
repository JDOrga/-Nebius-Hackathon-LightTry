"""Local failed provider observation evidence; no cloud or model."""
import unittest
import test_worker_guard as fixtures

class ObservationTests(unittest.TestCase):
 def setUp(self):self.f=fixtures.GuardTests();self.f.setUp();self.value=self.f.sessions.start(self.f.scope)
 def tearDown(self):self.f.tearDown()
 def test_exact_reviewed_error_retained_and_success_clears_active_error_only(self):
  f=self.f;observe=f.provider.observe
  def fail(resource):raise RuntimeError('NEBIUS_RESPONSE_UNCERTAIN')
  f.provider.observe=fail;v=f.sessions.poll(self.value['sessionId']);self.assertEqual(v['state'],'UNKNOWN');self.assertEqual(v['lastObservationFailure']['code'],'NEBIUS_RESPONSE_UNCERTAIN')
  f.provider.observe=observe;f.provider.state='RUNNING';v=f.sessions.poll(self.value['sessionId']);self.assertEqual(v['state'],'LOADING');self.assertIsNone(v['error']);self.assertEqual(v['lastObservationFailure']['code'],'NEBIUS_RESPONSE_UNCERTAIN')
  self.assertEqual(f.provider.starts,1)
 def test_untrusted_error_text_is_not_persisted(self):
  f=self.f;secret='PRIVATE_TOKEN_AUTH_URL'
  def fail(resource):raise RuntimeError(secret)
  f.provider.observe=fail;v=f.sessions.poll(self.value['sessionId']);self.assertEqual(v['lastObservationFailure']['code'],'UNCLASSIFIED_OBSERVATION_FAILURE');self.assertNotIn(secret,str(v));self.assertFalse(v['hostConfirmed'])

if __name__=='__main__':unittest.main()
