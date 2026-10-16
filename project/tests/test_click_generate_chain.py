"""Authenticated click->guard state->grant->queue->signed GPU authorization.
Provider, supervisor and model readiness are explicit doubles. No models launch.
"""
import base64,copy,json,time,unittest,hashlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
import test_key_login as login
import test_worker_guard as guard
from gpu_bootstrap import ControlBinding
from gpu_session import Sessions
from scope_issuer import ScopeIssuer
from session_grants import SessionGrantIssuer
from https_executor import HTTPSCosmosExecutor
from worker_link import WorkerLedger
from gpu_model import CosmosWorkerExecutor
from inference_fixture import image_bytes

class ClickGenerateTests(unittest.TestCase):
 def test_authenticated_click_to_signed_request_without_model_launch(self):
  f=login.KeyLoginTests();f.setUp();ledger=None
  try:
   app=f.app;peer=guard.Peer();provider=guard.Provider(peer);provider.simulation=False;peer.simulation=False
   host={'vmId':'SYNTHETIC_OFFLINE_VM'};observe=provider.observe
   provider.observe=lambda resource:{**observe(resource),'hostIdentity':host,'image':'SYNTHETIC_IMAGE'}
   fallback=Mock(simulation=False)
   fallback.snapshot.side_effect=lambda:{'state':'STOPPED','verifiedStopped':True,'lastObservedAt':time.time()}
   fallback.arm.side_effect=lambda sid,resource,deadline,lease:{'ready':True,'independentHost':False,'protectionMode':'cpu-only','cpuHostRiskAccepted':True,'sessionId':sid,'resourceId':resource,'deadline':deadline,'leaseSeconds':lease,'simulation':False}
   sessions=Sessions(f.root/'guard',provider,peer,fallback,protection_mode='cpu-only')
   scope=dict(scopeId='0'*32,resourceId='RESOURCE_FIXTURE',expiresAt=0,budgetApproved=False,idleSeconds=300,simulation=False)
   c=ControlBinding(sessions,scope);c.scope_path=f.root/'current-scope.json';c.scope_path.write_text(json.dumps(scope))
   c.scope_issuer=ScopeIssuer(f.root/'approvals',dict(enabled=True,resourceId='RESOURCE_FIXTURE',budgetUsdIncludingTax=3,hourlyUsdIncludingTax=6,billingReserveSeconds=120,maxSessionSeconds=2400,idleSeconds=300))
   app.gpu_control=c;app.gpu_sessions=sessions;app.gpu_scope=scope
   app.accounts.users['lighttry']['role']='operator';cookie,_=f.login();headers={'CONTENT_TYPE':'application/json','HTTP_X_LIGHTTRY_TOKEN':app.handler.csrf_token}
   click=json.dumps({'requestId':'a'*32}).encode()
   self.assertEqual(f.req('/api/gpu/entry-start','POST',click,cookie=cookie,extra=headers)[0],202)
   app.entry_thread.join(3);self.assertFalse(app.entry_thread.is_alive());self.assertEqual(provider.starts,1)
   sid=sessions.latest()['sessionId'];provider.state='RUNNING';self.assertEqual(sessions.poll(sid)['state'],'LOADING')
   confirm=json.dumps({'sessionId':sid,'hostIdentity':host}).encode()
   self.assertEqual(f.req('/api/gpu/confirm-host','POST',confirm,cookie=cookie,extra=headers)[0],200)
   grant_path=f.root/'model-grant.json';c.model_grant_issuer=SessionGrantIssuer(c,grant_path,dict(schemaVersion=1,modelLicenseAck=True,maxJobs=20));grant=c.model_grant_issuer.ensure(sid)
   ledger=WorkerLedger(f.root/'gpu','SYNTHETIC_ONLY_TOKEN_'+'X'*40,sid,'RESOURCE_FIXTURE')
   cfg=f.root/'worker.json';cfg.write_text(json.dumps(dict(schemaVersion=1,enabled=True,python=__import__('sys').executable,repo=str(f.root),checkpointDir=str(f.root),cudaHome=str(f.root),grantFile=str(grant_path))));cfg.chmod(0o600)
   with patch('subprocess.Popen') as launch:
    gpu=CosmosWorkerExecutor(ledger,cfg);ledger.executor=gpu
    peer.health=lambda:dict(sessionId=sid,resourceId='RESOURCE_FIXTURE',hostIdentity=host,modelState='ready',modelLoaded=True,executionMode='resident',simulation=False) # explicit readiness double, NOT actual loaded model.
    peer.upload=lambda raw:ledger.upload(hashlib.sha256(raw).hexdigest(),raw)
    peer.query=ledger.query;peer.submit=ledger.accept
    self.assertEqual(sessions.poll(sid)['state'],'READY')
    cpu=HTTPSCosmosExecutor(c,grant_path,app.handler.task_store.root);app.handler.task_store.executor=cpu
    scheme={'schemaVersion':1,'planId':'b'*32,'version':1,'parentVersion':None,'inputId':'c'*32,'name':'offline','parameters':{'environmentId':'sunny','offsetDeg':0,'strength':1}}
    metadata={'inputId':'c'*32,'requestId':'d'*32,'name':'offline','lightingScheme':scheme}
    body=image_bytes();upload={'CONTENT_TYPE':'image/png','HTTP_X_LIGHTTRY_TOKEN':app.handler.csrf_token,'HTTP_X_LIGHTTRY_REQUEST':base64.b64encode(json.dumps(metadata).encode()).decode()}
    status,_,out=f.req('/api/tasks','POST',body,cookie=cookie,extra=upload);self.assertEqual(status,202,out)
    task=json.loads(out)['taskId'];app.queue.tick();remote=ledger.query(task)
    self.assertEqual(remote['status'],'queued',app.queue.get(task,'lighttry'))
    request,files=__import__('model_contract').unpack_input(ledger.blob(remote['artifactSha256']))
    self.assertIn('authorization.json',files);self.assertEqual(gpu.authorize(remote),grant)
    app.queue.tick();self.assertEqual(len(list((ledger.root/'executions').glob('*'))) if (ledger.root/'executions').exists() else 0,0)
    launch.assert_not_called();self.assertEqual(provider.starts,1)
  finally:
   if ledger:ledger.close()
   f.tearDown()

if __name__=='__main__':unittest.main()

