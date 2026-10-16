"""Authenticated route + current-scope handoff, synthetic provider only."""
from test_key_login import KeyLoginTests
from gpu_bootstrap import ControlBinding
from scope_issuer import ScopeIssuer
from types import SimpleNamespace
from pathlib import Path
import json,time

class ClickRouteTests(KeyLoginTests):
 def wire(self):
  gpu=self.gpu_fixture();gpu.protection_mode='off-host'
  policy=dict(enabled=True,resourceId='fixture',budgetUsdIncludingTax=3,hourlyUsdIncludingTax=6,billingReserveSeconds=120,maxSessionSeconds=2400,idleSeconds=60)
  control=ControlBinding(gpu,self.app.gpu_scope)
  control.scope_issuer=ScopeIssuer(self.root/'issuer',policy)
  control.scope_path=self.root/'current-scope.json'
  control.scope_path.write_text(json.dumps(self.app.gpu_scope));self.app.gpu_control=control
  return gpu,control
 def test_click_writes_new_exact_scope_and_async_route_deduplicates(self):
  gpu,c=self.wire();cookie=self.operator_cookie();old=self.app.gpu_scope['scopeId'];seen=[]
  original=gpu.start
  def start(scope):seen.append(scope);return original(scope)
  gpu.start=start
  headers={'CONTENT_TYPE':'application/json','HTTP_X_LIGHTTRY_TOKEN':self.app.handler.csrf_token};body=json.dumps({'requestId':'f'*32}).encode()
  try:
   self.assertEqual(self.req('/api/gpu/entry-start','POST',body,cookie=cookie,extra=headers)[0],202)
   self.assertTrue(gpu.entered.wait(1));self.assertNotEqual(seen[0]['scopeId'],old)
   self.assertEqual(json.loads(c.scope_path.read_text()),seen[0]);self.assertEqual(c.scope,seen[0]);self.assertEqual(self.app.gpu_scope,seen[0])
   self.assertEqual(self.req('/api/gpu/entry-start','POST',body,cookie=cookie,extra=headers)[0],202);self.assertEqual(gpu.calls,1)
  finally:gpu.release.set();self.app.entry_thread.join(2)
 def test_invalid_rate_no_scope_write_or_provider_call(self):
  gpu,c=self.wire();before=c.scope_path.read_bytes();c.scope_issuer.policy['hourlyUsdIncludingTax']=None
  cookie=self.operator_cookie();headers={'CONTENT_TYPE':'application/json','HTTP_X_LIGHTTRY_TOKEN':self.app.handler.csrf_token}
  self.assertEqual(self.req('/api/gpu/entry-start','POST',json.dumps({'requestId':'f'*32}).encode(),cookie=cookie,extra=headers)[0],409)
  self.assertEqual(c.scope_path.read_bytes(),before);self.assertEqual(gpu.calls,0)
 def test_guard_refresh_rejects_scope_swap_during_live_session(self):
  gpu,c=self.wire();scope=c.issue_scope('a'*32,'operator')
  gpu.latest=lambda:{'sessionId':'b'*32,'scopeId':scope['scopeId'],'verifiedStopped':False}
  c.refresh_scope();changed={**scope,'scopeId':'c'*32};c.scope_path.write_text(json.dumps(changed))
  with self.assertRaisesRegex(ValueError,'REPLACEMENT'):c.refresh_scope()
 def test_guard_reads_published_scope_not_old_host_approval(self):
  gpu,c=self.wire();scope=c.issue_scope('a'*32,'operator');observer=ControlBinding(gpu,{**scope,'scopeId':'b'*32})
  observer.scope_issuer=c.scope_issuer;observer.scope_path=c.scope_path;observer.refresh_scope()
  self.assertEqual(observer.scope,scope);self.assertNotIn('hostConfirmed',observer.scope)
