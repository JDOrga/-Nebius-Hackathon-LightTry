"""CPU classification only, no network or provider/model replacement."""
import sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'project'))
from runtime.driver import retryable_archive_failure
class ArchiveRetryTests(unittest.TestCase):
 def test_same_channel_closed_export_has_one_retry_only(self):
  s={'exit_code':255,'stderr_categories':['CONNECTION_CLOSED'],'cleanup_incomplete':False,'remaining_owned_processes':0,'process_exited':True,'output_complete':True}
  self.assertTrue(retryable_archive_failure('export_control_chunk',s));self.assertFalse(retryable_archive_failure('launch',s))
  for change in [{'stderr_categories':['AUTHENTICATION_FAILED']},{'stderr_categories':['HOST_KEY_CHANGED']},{'stderr_categories':['PERMISSION_DENIED']},{'cleanup_incomplete':True},{'remaining_owned_processes':1},{'output_complete':False},{'exit_code':3}]:self.assertFalse(retryable_archive_failure('export_control_chunk',{**s,**change}))
if __name__=='__main__':unittest.main()
