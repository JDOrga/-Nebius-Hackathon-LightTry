"""ProtoJSON empty-field compatibility must retain independent VM proof."""
import copy,json,unittest,threading
from types import SimpleNamespace
from unittest.mock import patch
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

 def test_omitted_startup_list_retains_phase_without_release_or_host(self):
  for state in ['PROVISIONING','STARTING','IMAGE_PULLING']:
   self.f.provider.runner.reset_mock();self.f.raw['status']={'state':state}
   v=self.f.provider.observe('devlab-fixture')
   self.assertEqual(v['state'],'STARTING');self.assertIsNone(v['instances'])
   self.assertEqual(v['instancesProof'],'startup-instance-list-pending')
   self.assertNotIn('hostIdentity',v)
   calls=[c.args[0][1:4] for c in self.f.provider.runner.call_args_list]
   self.assertEqual(calls,[['iam','v2','project'],['ai','devlab','get']])

 def test_startup_null_or_malformed_lists_are_not_pending(self):
  for state in ['PROVISIONING','STARTING','IMAGE_PULLING']:
   for instances in [None,{},'pending']:
    self.f.raw['status']={'state':state,'instances':instances}
    with self.assertRaisesRegex(ValueError,'PROOF_REQUIRED'):self.f.provider.observe('devlab-fixture')

 def test_startup_omission_does_not_skip_project_or_key_validation(self):
  self.f.raw['status']={'state':'STARTING'};self.f.raw['metadata']['parent_id']='other'
  with self.assertRaises(ValueError):self.f.provider.observe('devlab-fixture')
  self.f.raw['metadata']['parent_id']='project-fixture';self.f.raw['spec']['ssh_authorized_keys']=[]
  with self.assertRaisesRegex(ValueError,'PUBLIC_KEY_MISMATCH'):self.f.provider.observe('devlab-fixture')

 def test_missing_stopping_list_still_requires_proof(self):
  self.f.raw['status']={'state':'STOPPING'}
  with self.assertRaisesRegex(ValueError,'PROOF_REQUIRED'):self.f.provider.observe('devlab-fixture')

 def test_guard_keeps_real_startup_receipt_out_of_unknown(self):
  session=self.f.session();scope={'scopeId':'a'*32,'resourceId':'devlab-fixture','expiresAt':2500,
   'budgetApproved':True,'idleSeconds':60,'simulation':False}
  s=session.start(scope);self.assertTrue(s['startSent'])
  self.f.raw['status']={'state':'STARTING'}
  s=session.poll(s['sessionId'])
  self.assertEqual((s['state'],s['providerState']),('STARTING','STARTING'))
  self.assertIsNone(s.get('error'));self.assertIsNone(s['runningAt'])
  self.assertFalse(s['hostConfirmed']);self.assertFalse(s['verifiedStopped']);self.assertFalse(s['instancesEmpty'])
  self.assertFalse(s['stopSent'])
  from service import Application
  view=SimpleNamespace(gpu_sessions=session,gpu_scope=scope,gpu_control=None,
   entry_lock=threading.Lock(),entry_start={'scopeId':scope['scopeId'],'status':'requested'})
  with patch('service.time.time',return_value=100):info=Application.gpu_entry_info(view)
  self.assertEqual(info['state'],'STARTING');self.assertIsNone(info['diagnostic'])
  self.assertTrue(info['active']);self.assertFalse(info['canGenerate']);self.assertFalse(info['canStart'])

 def test_pending_startup_never_satisfies_start_preflight(self):
  self.f.raw['status']={'state':'STARTING'};session=self.f.session()
  scope={'scopeId':'a'*32,'resourceId':'devlab-fixture','expiresAt':2500,
   'budgetApproved':True,'idleSeconds':60,'simulation':False}
  s=session.start(scope)
  self.assertFalse(s['startSent']);self.assertEqual(s['startFailure']['stage'],'preflight')
  self.assertFalse(any('restart' in c.args[0] for c in self.f.provider.runner.call_args_list))

if __name__=='__main__':unittest.main()
