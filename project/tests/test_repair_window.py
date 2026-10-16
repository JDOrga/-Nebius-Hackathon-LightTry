"""Explicit same-window repair policy; startup/work/absolute/lease protections unchanged."""
import copy,unittest
import test_worker_guard as fixtures

class RepairTests(unittest.TestCase):
 def setUp(self):self.f=fixtures.GuardTests();self.f.setUp();self.f.sessions.recovery_mode=True
 def tearDown(self):self.f.tearDown()
 def test_idle_does_not_abort_active_authorized_repair_but_work_deadline_still_stops(self):
  f=self.f;v=f.running();deadlines={k:v[k] for k in ['startupDeadline','workDeadline','absoluteDeadline']}
  f.clock.now=v['idleDeadline']+1;f.sessions.heartbeat(v['sessionId']);v=f.sessions.poll(v['sessionId']);self.assertFalse(v['stopSent']);self.assertEqual(f.provider.stops,0)
  self.assertEqual({k:v[k] for k in deadlines},deadlines)
  f.clock.now=v['workDeadline'];f.sessions.heartbeat(v['sessionId']);v=f.sessions.poll(v['sessionId']);self.assertTrue(v['stopSent']);self.assertEqual(f.provider.stops,1)
 def test_host_change_holds_running_vm_but_revokes_dispatch_trust(self):
  f=self.f;v=f.running();old=copy.deepcopy(v);observe=f.provider.observe
  f.provider.observe=lambda resource:{**observe(resource),'hostIdentity':'DIFFERENT_VM'}
  v=f.sessions.poll(v['sessionId']);self.assertEqual(v['state'],'UNKNOWN');self.assertFalse(v['hostConfirmed']);self.assertFalse(v['stopSent']);self.assertEqual(v['hostIdentity'],old['hostIdentity']);self.assertEqual(v['workDeadline'],old['workDeadline'])
  with self.assertRaises(Exception):f.sessions.submit(v['sessionId'],f.job(v['sessionId']))
  self.assertEqual(f.peer.posts,0)
 def test_cpu_lease_loss_still_stops_repair_session(self):
  f=self.f;v=f.running();f.clock.step(31);v=f.sessions.poll(v['sessionId']);self.assertTrue(v['stopSent']);self.assertEqual(f.provider.stops,1)

if __name__=='__main__':unittest.main()
