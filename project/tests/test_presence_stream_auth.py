import unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import test_key_login as fixtures

class StreamAuthTests(unittest.TestCase):
 def setUp(self):
  self.f=fixtures.KeyLoginTests();self.f.setUp();self.addCleanup(self.f.tearDown)
 def test_requires_auth_and_csrf_even_though_stream_is_get(self):
  self.assertEqual(self.f.req('/api/gpu/presence-stream')[0],401)
  cookie,_=self.f.login()
  self.assertEqual(self.f.req('/api/gpu/presence-stream',cookie=cookie)[0],403)
 def test_missing_disconnect_detection_fails_closed(self):
  cookie,_=self.f.login()
  code,_,_=self.f.req('/api/gpu/presence-stream',cookie=cookie,extra={'HTTP_X_LIGHTTRY_TOKEN':self.f.app.handler.csrf_token})
  self.assertEqual(code,503)
 def test_closed_connection_has_no_presence_updates_and_frees_slot(self):
  cookie,_=self.f.login()
  code,_,body=self.f.req('/api/gpu/presence-stream',cookie=cookie,extra={'HTTP_X_LIGHTTRY_TOKEN':self.f.app.handler.csrf_token,'waitress.client_disconnected':lambda:True})
  self.assertEqual(code,200);self.assertEqual(body,b'')
  self.assertTrue(self.f.app.presence_slots.acquire(False));self.f.app.presence_slots.release()

if __name__=='__main__':unittest.main()
