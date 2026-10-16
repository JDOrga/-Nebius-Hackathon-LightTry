"""Signed dynamic input authorization, no cloud/model execution."""
import copy,hashlib,json,time,unittest
from unittest.mock import patch
import test_real_links as fixtures
from model_contract import job_authorization,verify_job_authorization,pack_input,unpack_input,request_sha,grant_file
from gpu_model import CosmosWorkerExecutor

class DynamicTests(unittest.TestCase):
 def setUp(self):
  self.f=fixtures.ModelTests();self.f.setUp();g=self.f.grant
  for k in ['allowedOriginalSha256','allowedRecipeKeys','allowedMetadata']:del g[k]
  g.update(schemaVersion=2,jobAuthorization={'algorithm':'hmac-sha256-v1','keyHex':'ab'*32,'owner':'lighttry'});self.f.write_grant()
 def tearDown(self):self.f.tearDown()
 def envelope(self,authorization):
  f=self.f;raw=pack_input(f.folder,f.request,authorization);sha=hashlib.sha256(raw).hexdigest();f.ledger.upload(sha,raw)
  return {'jobId':f.request['taskId'],'sessionId':f.grant['sessionId'],'resourceId':f.grant['resourceId'],'artifactSha256':sha,'requestSha256':request_sha(f.request)}
 def test_new_photo_request_signed_without_changing_warm_session_grant(self):
  f=self.f;before=f.grant_path.read_bytes();auth=job_authorization(f.request,f.grant)
  with patch('subprocess.Popen') as launch:
   executor=CosmosWorkerExecutor(f.ledger,f.config);self.assertEqual(executor.authorize(self.envelope(auth)),f.grant);launch.assert_not_called()
  self.assertEqual(f.grant_path.read_bytes(),before);self.assertNotIn('keyHex',json.dumps(auth))
 def test_cpu_attaches_signature_and_owner_gate(self):
  f=self.f;self.assertTrue(f.cpu.authorize_job('lighttry',{},'a'*64));self.assertFalse(f.cpu.authorize_job('other',{},'a'*64))
  f.cpu.submit(f.folder,f.request);raw=f.worker.upload.call_args.args[0];request,files=unpack_input(raw)
  self.assertTrue(verify_job_authorization(request,f.grant,json.loads(files['authorization.json'])))
 def test_tampered_task_nonce_host_owner_recipe_and_deadline_are_rejected(self):
  f=self.f;auth=job_authorization(f.request,f.grant)
  for field,value in [('taskId','d'*32),('nonce','e'*32),('owner','other'),('sessionId','f'*32),('hostIdentity',{'vmId':'other'}),('expiresAt',time.time()+9999),('requestSha256','a'*64)]:
   changed=copy.deepcopy(auth);changed['body'][field]=value
   with self.assertRaises(ValueError):verify_job_authorization(f.request,f.grant,changed)
  changed=copy.deepcopy(f.request);changed['preset']['parameters']={'strength':2}
  with self.assertRaises(ValueError):verify_job_authorization(changed,f.grant,auth)
  with self.assertRaises(ValueError):verify_job_authorization(f.request,f.grant,auth,clock=lambda:f.grant['expiresAt'])
 def test_missing_bad_signature_and_other_session_key_fail_before_model(self):
  f=self.f;executor=CosmosWorkerExecutor(f.ledger,f.config)
  for auth in [None,{}, {'body':{},'signature':'0'*64}]:
   with patch('subprocess.Popen') as launch:
    with self.assertRaises(ValueError):executor.authorize(self.envelope(auth))
    launch.assert_not_called()
  auth=job_authorization(f.request,{**f.grant,'jobAuthorization':{**f.grant['jobAuthorization'],'keyHex':'cd'*32}})
  with self.assertRaises(ValueError):executor.authorize(self.envelope(auth))
 def test_closed_schema_rejects_untrusted_algorithm_and_mixed_v1_fields(self):
  f=self.f
  for bad in [{**f.grant,'allowedMetadata':[]},{**f.grant,'jobAuthorization':{**f.grant['jobAuthorization'],'algorithm':'none'}},{**f.grant,'jobAuthorization':{**f.grant['jobAuthorization'],'keyHex':'short'}}]:
   f.grant_path.write_text(json.dumps(bad))
   with self.assertRaises(ValueError):grant_file(f.grant_path,f.grant['sessionId'],f.grant['resourceId'])

if __name__=='__main__':unittest.main()
