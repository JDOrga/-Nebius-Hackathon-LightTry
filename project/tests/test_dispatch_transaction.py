"""Hermetic cross-controller dispatch races, no real cloud or model calls."""
import sys,sqlite3,threading,concurrent.futures,unittest,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import test_worker_guard as fixtures
from gpu_session import Sessions
from inference.jobs import JobError

class DispatchTransactionTests(unittest.TestCase):
 def setUp(self):
  self.f=fixtures.GuardTests();self.f.setUp();self.addCleanup(self.f.tearDown)
  self.v=self.f.running();self.sid=self.v['sessionId'];self.job=self.f.job(self.sid)
  self.other=Sessions(self.f.root/'cpu-guard',self.f.provider,self.f.peer,self.f.fallback,self.f.clock)
 def intercept(self,action):
  original=self.f.peer.query;once=[]
  def query(job):
   if not once:once.append(1);action()
   return original(job)
  self.f.peer.query=query
 def records(self):
  with self.f.sessions.db() as db:return db.execute('SELECT state FROM dispatches').fetchall(),db.execute("SELECT event FROM events WHERE event='TASK_ATTEMPT_LATCHED'").fetchall()
 def test_guard_revision_advances_during_query(self):
  self.intercept(lambda:self.other.change(self.sid,'GUARD_TEST',lambda v:v.update(lastObservedAt=self.f.clock())))
  before={k:self.v[k] for k in ['workDeadline','stopDeadline','verifyDeadline','absoluteDeadline']}
  result=self.f.sessions.submit(self.sid,self.job);self.assertEqual(result['status'],'queued');self.assertEqual(self.f.peer.posts,1);self.assertEqual(self.records(),([('active',)],[('TASK_ATTEMPT_LATCHED',)]))
  for k,v in before.items():self.assertEqual(self.f.sessions.get(self.sid)[k],v)
 def test_stop_during_query_blocks_dispatch(self):
  self.intercept(lambda:self.other.request_stop(self.sid,'OPERATOR_STOP'))
  with self.assertRaises(JobError):self.f.sessions.submit(self.sid,self.job)
  self.assertEqual(self.f.peer.posts,0);self.assertEqual(self.records(),([],[]));self.assertTrue(self.f.sessions.get(self.sid)['stopSent'])
 def test_expiry_during_query_blocks_dispatch(self):
  self.intercept(lambda:self.f.clock.step(self.v['workDeadline']-self.f.clock()+1))
  with self.assertRaises(JobError):self.f.sessions.submit(self.sid,self.job)
  self.assertEqual(self.f.peer.posts,0);self.assertEqual(self.records(),([],[]))
 def test_host_changes_during_query_blocks_dispatch(self):
  self.intercept(lambda:self.other.change(self.sid,'HOST_TEST',lambda v:v.update(hostIdentity='DIFFERENT_HOST',hostConfirmed=True)))
  with self.assertRaises(JobError):self.f.sessions.submit(self.sid,self.job)
  self.assertEqual(self.f.peer.posts,0);self.assertEqual(self.records(),([],[]))
 def test_stale_observation_during_query_blocks_dispatch(self):
  self.intercept(lambda:self.f.clock.step(31))
  with self.assertRaises(JobError):self.f.sessions.submit(self.sid,self.job)
  self.assertEqual(self.f.peer.posts,0);self.assertEqual(self.records(),([],[]))
 def test_database_error_rolls_back_marker_and_state(self):
  with self.f.sessions.db() as db:db.execute("CREATE TRIGGER fail_latch BEFORE INSERT ON events WHEN NEW.event='TASK_ATTEMPT_LATCHED' BEGIN SELECT RAISE(ABORT,'SYNTHETIC_COMMIT_FAILURE'); END")
  with self.assertRaises(sqlite3.IntegrityError):self.f.sessions.submit(self.sid,self.job)
  self.assertEqual(self.records(),([],[]));self.assertEqual(self.f.sessions.get(self.sid)['state'],'READY');self.assertEqual(self.f.peer.posts,0)
 def test_two_controllers_same_job_post_at_most_once(self):
  barrier=threading.Barrier(2);counter=[];lock=threading.Lock();original=self.f.peer.query
  def query(job):
   with lock:first=len(counter)<2;counter.append(1)
   if first:barrier.wait(timeout=3);return {'status':'not_found'}
   return original(job)
  self.f.peer.query=query
  with concurrent.futures.ThreadPoolExecutor(2) as pool:results=list(pool.map(lambda s:s.submit(self.sid,self.job),[self.f.sessions,self.other]))
  self.assertEqual(self.f.peer.posts,1);self.assertEqual(len(self.records()[0]),1);self.assertEqual(len(self.records()[1]),1)
 def test_uncertain_response_does_not_overwrite_stop(self):
  original=self.f.peer.submit
  def submit(job):self.other.request_stop(self.sid,'OPERATOR_STOP');raise OSError('SYNTHETIC_ACK_LOSS')
  self.f.peer.submit=submit
  result=self.f.sessions.submit(self.sid,self.job);current=self.f.sessions.get(self.sid)
  self.assertEqual(result['status'],'uncertain');self.assertEqual(current['state'],'STOPPING');self.assertEqual(current['error'],'OPERATOR_STOP');self.assertTrue(current['stopSent'])
 def test_reconcile_after_stop_does_not_restore_ready(self):
  self.f.peer.jobs[self.job['jobId']]={**self.job,'status':'succeeded'}
  self.intercept(lambda:self.other.request_stop(self.sid,'OPERATOR_STOP'))
  result=self.f.sessions.submit(self.sid,self.job);self.assertEqual(result['status'],'succeeded');self.assertEqual(self.f.sessions.get(self.sid)['state'],'STOPPING');self.assertEqual(self.f.peer.posts,0)
if __name__=='__main__':unittest.main()
