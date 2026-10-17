"""No cloud/GPU. Virtual-clock guard tests + real loopback disconnect detection."""
import http.client
import sys
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parent))
import test_worker_guard as fixtures
from client_presence import PresenceStream
from gpu_monitoring import public_failure


class BackgroundTests(unittest.TestCase):
 def setUp(self):
  self.f=fixtures.GuardTests();self.f.setUp();self.addCleanup(self.f.tearDown)
  self.f.scope['expiresAt']=self.f.clock()+5520;self.v=self.f.running();self.sid=self.v['sessionId'];self.released=0
 def stream(self):
  f=self.f
  stop=SimpleNamespace(is_set=lambda:False,wait=lambda seconds:(f.clock.step(seconds) or False))
  return PresenceStream(lambda:f.sessions,lambda:False,lambda:True,stop,lambda:setattr(self,'released',self.released+1))
 def poll(self):
  self.f.sessions.heartbeat(self.sid);return self.f.sessions.poll(self.sid)
 def test_no_browser_timers_for_ten_minutes_does_not_stop_open_connection(self):
  stream=self.stream()
  for _ in range(61):
   self.assertIn(b'connected',next(stream));self.assertFalse(self.poll()['stopSent'])
  stream.close();self.assertEqual(self.f.provider.stops,0)
 def test_last_disconnect_stops_at_exact_300_not_299(self):
  stream=self.stream();next(stream);stream.close();t=self.f.clock()
  self.f.clock.now=t+299;self.assertFalse(self.poll()['stopSent'])
  self.f.clock.now=t+300;v=self.poll();self.assertEqual(v['stopReason'],'NO_CLIENT_CONNECTION_5_MIN');self.assertEqual(self.f.provider.stops,1)
 def test_another_tab_keeps_session_alive_after_one_tab_closes(self):
  a=self.stream();b=self.stream();next(a);next(b);a.close()
  for _ in range(40):next(b);self.assertFalse(self.poll()['stopSent'])
  b.close();self.assertEqual(self.released,2)
 def test_reconnect_before_timeout_renews_but_cannot_revive_expired_lease(self):
  a=self.stream();next(a);a.close();self.f.clock.step(290);b=self.stream();next(b);self.assertFalse(self.poll()['stopSent']);b.close()
  self.f.clock.step(301);self.f.sessions.client_presence(self.sid);self.assertTrue(self.poll()['stopSent'])
 def test_connection_never_extends_one_hour(self):
  stream=self.stream()
  for _ in range(360):next(stream);self.assertFalse(self.poll()['stopSent'])
  next(stream);v=self.poll();self.assertEqual(v['stopReason'],'RUNNING_WINDOW_EXPIRED');stream.close()
 def test_cpu_lease_is_still_independent_of_browser_connection(self):
  a=self.stream();next(a);self.f.clock.step(30);next(a)
  self.assertEqual(self.f.sessions.poll(self.sid)['stopReason'],'CPU_HEARTBEAT_LOST');a.close()
 def test_close_releases_capacity_exactly_once_even_without_iteration(self):
  stream=self.stream();stream.close();stream.close();self.assertEqual(self.released,1)
 def test_stop_reason_survives_response_error_and_is_human_readable(self):
  a=self.stream();next(a);a.close();self.f.clock.step(300);v=self.poll()
  d=public_failure(v,{},True);self.assertIn('5分钟',d['detail']);self.assertIn('尚未确认',d['cost'])
  v.update(verifiedStopped=True,instancesEmpty=True);d=public_failure(v,{},True);self.assertFalse(d['active']);self.assertIn('不会自动开机',d['action'])


class RealDisconnectTests(unittest.TestCase):
 def test_waitress_detects_real_socket_disconnect_without_page_heartbeat(self):
  from waitress import create_server
  stop=threading.Event();released=threading.Event();beats=[]
  sessions=SimpleNamespace(latest=lambda:{'sessionId':'a'*32},client_presence=lambda sid:beats.append(time.monotonic()))
  def app(env,start):
   self.assertTrue(callable(env.get('waitress.client_disconnected')))
   start('200 OK',[('Content-Type','text/event-stream')])
   return PresenceStream(lambda:sessions,env['waitress.client_disconnected'],lambda:True,stop,released.set,interval=.05)
  server=create_server(app,listen='127.0.0.1:0',threads=4,channel_request_lookahead=1)
  thread=threading.Thread(target=server.run,daemon=True);thread.start()
  conn=http.client.HTTPConnection('127.0.0.1',int(server.effective_port),timeout=3)
  try:
   conn.request('GET','/');response=conn.getresponse();self.assertEqual(response.status,200);response.read(1)
   time.sleep(.2);self.assertGreater(len(beats),1)  # No POSTs, JS timers or extra requests.
   response.close();conn.close();self.assertTrue(released.wait(2),'Disconnected socket still renewed presence')
   n=len(beats);time.sleep(.15);self.assertEqual(len(beats),n)
  finally:stop.set();conn.close();server.close();thread.join(2)

if __name__=='__main__':unittest.main()
