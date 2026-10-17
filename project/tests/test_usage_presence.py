import unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_worker_guard import GuardTests
from gpu_session import Sessions
class UsagePresenceTests(unittest.TestCase):
 def setUp(self):
  self.f=GuardTests();self.f.setUp();self.addCleanup(self.f.tearDown)
  self.f.scope['expiresAt']=self.f.clock()+5520
  self.v=self.f.running();self.sid=self.v['sessionId'];self.start=self.f.clock()
 def tick(self,seconds,presence=True):
  self.f.clock.now=self.start+seconds;self.f.sessions.heartbeat(self.sid)
  if presence:self.f.sessions.client_presence(self.sid)
  return self.f.sessions.poll(self.sid)
 def test_hour_not_extended_by_presence(self):
  for n in range(200,3600,200):self.assertFalse(self.tick(n)['stopSent'])
  self.assertFalse(self.tick(3599)['stopSent'])
  self.assertTrue(self.tick(3600)['stopSent'])
 def test_executing_stops_after_absence_even_during_recovery(self):
  v=self.f.sessions.get(self.sid);v['state']='EXECUTING';v['recoveryMode']=True;self.f.sessions.save(v,'TEST')
  self.assertTrue(self.tick(300,False)['stopSent'])
 def test_reboot_and_late_heartbeat_do_not_revive_expired_lease(self):
  self.tick(200)
  self.f.sessions=Sessions(self.f.root/'cpu-guard',self.f.provider,self.f.peer,self.f.fallback,self.f.clock)
  self.assertFalse(self.tick(499,False)['stopSent'])
  self.assertTrue(self.tick(500,True)['stopSent'])
if __name__=='__main__':unittest.main()
