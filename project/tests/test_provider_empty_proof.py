"""ProtoJSON empty-field compatibility must retain independent VM proof."""
import copy,json,unittest
from types import SimpleNamespace
import test_real_links as fixtures

class ProofTests(unittest.TestCase):
 def setUp(self):
  self.f=fixtures.NebiusTests();self.f.setUp();self.f.raw['status'].pop('instances');self.listing={};self.changed=False;self.gets=0
  original=self.f.provider.runner.side_effect
  def run(cmd,**kw):
   if cmd[1:4]==['compute','instance','list']:
    self.assertIn('--all',cmd);self.assertIn('project-fixture',cmd)
    return SimpleNamespace(returncode=0,stdout=json.dumps(self.listing),stderr='')
   if cmd[1:4]==['ai','devlab','get']:
    self.gets+=1
    if self.changed and self.gets%2==0:
     raw=copy.deepcopy(self.f.raw);raw['status']['state']='STARTING'
     return SimpleNamespace(returncode=0,stdout=json.dumps(raw),stderr='')
   return original(cmd,**kw)
  self.f.provider.runner.side_effect=run
 def tearDown(self):self.f.tearDown()
 def test_omission_requires_independent_empty_list_and_recheck(self):
  for listing in [{},{'items':[]}]:
   self.listing=listing;v=self.f.provider.preflight('devlab-fixture')
   self.assertEqual(v['instances'],[]);self.assertEqual(v['instancesProof'],'project-wide-empty-list-and-stopped-recheck')
  self.assertEqual(self.gets,4)
 def test_nonempty_malformed_partial_or_paginated_listing_never_proves_release(self):
  for value in [None,[],{'items':None},{'items':[{'metadata':{'id':'any-vm'}}]},{'next_page_token':'more'},{'items':[],'next_page_token':'more'},{'error':'denied'}]:
   self.listing=value
   with self.assertRaises(ValueError):self.f.provider.preflight('devlab-fixture')
 def test_state_changes_rejected(self):
  self.changed=True
  with self.assertRaisesRegex(ValueError,'CHANGED'):self.f.provider.preflight('devlab-fixture')
 def test_null_or_missing_running_not_normalized(self):
  self.f.raw['status']['instances']=None
  with self.assertRaisesRegex(ValueError,'PROOF_REQUIRED'):self.f.provider.preflight('devlab-fixture')
  self.f.raw['status'].pop('instances');self.f.raw['status']['state']='RUNNING'
  with self.assertRaisesRegex(ValueError,'PROOF_REQUIRED'):self.f.provider.preflight('devlab-fixture')

if __name__=='__main__':unittest.main()
