"""Shared-disk simulated provider for independent-process tests, never cloud APIs."""
import json
from pathlib import Path
from gpu_session import Sessions,Deadman


def create(root, configuration):
    root=Path(root)
    clock=lambda:float((root/'fixture-clock').read_text())
    class Peer:
        simulation=True
        def health(self):
            value=json.loads((root/'fixture-provider.json').read_text())
            return {'sessionId':value['sid'],'resourceId':'RESOURCE_FIXTURE','modelState':'ready'}
        def query(self,identity):return {'status':'not_found'}
    class Provider:
        simulation=True
        def observe(self,resource):
            value=json.loads((root/'fixture-provider.json').read_text())
            return {'independent':True,'resourceId':resource,'state':value['state'],
                    'instances':[] if value['state']=='STOPPED' else ['INSTANCE_FIXTURE'],'hostIdentity':'HOST_FIXTURE'}
        def preflight(self,resource):return self.observe(resource)
        def start(self,resource,sid,deadline):
            (root/'fixture-provider.json').write_text(json.dumps({'state':'RUNNING','sid':sid,'starts':1,'stops':0}))
        def stop(self,resource,sid):
            value=json.loads((root/'fixture-provider.json').read_text());value['state']='STOPPING';value['stops']+=1
            (root/'fixture-provider.json').write_text(json.dumps(value))
    provider=Provider()
    return Sessions(root,provider,Peer(),Deadman(root/'OFF_HOST_FIXTURE',provider,clock),clock)
