"""OFFLINE SYNTHETIC dispatch only; never evidence of Cosmos generation."""
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'project'))
from next.store import SchemeStore
from inference.jobs import JobError


class FakeExecutor:
    supports_lighting_parameters=True
    def __init__(self): self.requests=[]
    def submit(self,folder,request): self.requests.append(request)


class SchemeStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.presets=json.loads((ROOT/'project/data/catalog.json').read_text())['presets']
        self.cap={'revision':'OFFLINE_SYNTHETIC_NOT_GPU','approvedVariants':{'sunny':[[0,.7],[45,1]]}}
        self.executor=FakeExecutor()
        self.store=SchemeStore(Path(self.temp.name)/'tasks',self.presets,self.executor,lighting_capabilities=self.cap)
        from PIL import Image
        image=Image.new('RGB',(64,80),(120,100,70));image.paste((180,190,140),(10,10,50,60));out=io.BytesIO();image.save(out,'PNG');self.photo=out.getvalue()
        self.raw={'schemaVersion':1,'planId':'a'*32,'version':1,'name':'试光','parameters':{'environmentId':'sunny','offsetDeg':0,'strength':1},'inputId':'b'*32,'parentVersion':None}
        self.meta={'requestId':'c'*32,'inputId':'b'*32,'name':'OFFLINE_SYNTHETIC.png','lightingScheme':self.raw}
    def tearDown(self): self.store.close();self.temp.cleanup()
    def test_full_scheme_reaches_request_and_same_key_reuses(self):
        t=self.store.submit(self.photo,self.meta,'image/png')
        self.assertEqual(self.executor.requests[0]['preset']['scheme'],self.raw)
        self.assertEqual(t['lightingScheme']['parameters']['strength'],1)
        self.assertEqual(t['taskId'],self.store.submit(self.photo,self.meta,'image/png')['taskId'])
        self.assertEqual(len(self.executor.requests),1)
    def test_changed_parameter_and_version_conflicts_with_old_idempotency(self):
        self.store.submit(self.photo,self.meta,'image/png')
        bad=copy.deepcopy(self.meta);bad['lightingScheme']['parameters']['strength']=.7
        bad['lightingScheme'].update(version=2,parentVersion=1)
        with self.assertRaises(JobError) as cm:self.store.submit(self.photo,bad,'image/png')
        self.assertEqual(cm.exception.code,'IDEMPOTENCY_CONFLICT')
        self.assertEqual(len(self.executor.requests),1)
    def test_unapproved_combination_input_and_legacy_ignoring_adapter_rejected(self):
        for params in [{'environmentId':'sunny','offsetDeg':45,'strength':.7},
                       {'environmentId':'street','offsetDeg':0,'strength':.7},
                       {'environmentId':'sunny','offsetDeg':0,'strength':1.4}]:
            bad=copy.deepcopy(self.meta);bad['lightingScheme']['parameters']=params
            with self.assertRaises(JobError):self.store.submit(self.photo,bad,'image/png')
        bad=copy.deepcopy(self.meta);bad['inputId']='d'*32
        with self.assertRaises(JobError):self.store.submit(self.photo,bad,'image/png')
        self.executor.supports_lighting_parameters=False
        bad=copy.deepcopy(self.meta);bad['lightingScheme']['parameters']['strength']=.7
        with self.assertRaises(JobError):self.store.submit(self.photo,bad,'image/png')
        self.assertFalse(self.executor.requests)
    def test_restart_restores_snapshot_without_rewriting_history(self):
        t=self.store.submit(self.photo,self.meta,'image/png');folder=self.store.directory(t['taskId']);before=(folder/'request.json').read_bytes()
        self.store.close();self.store=SchemeStore(Path(self.temp.name)/'tasks',self.presets,lighting_capabilities=self.cap)
        self.assertIn(t['preset']['id'],self.store.presets)
        self.assertEqual(before,(folder/'request.json').read_bytes())
        self.assertEqual(self.raw,self.store.get(t['taskId'])['lightingScheme'])


    def test_language_origin_requires_accepted_same_input_params_and_survives_restart(self):
        metadata=copy.deepcopy(self.meta);metadata['languageProposalId']='e'*32
        with self.assertRaises(JobError):self.store.submit(self.photo,metadata,'image/png')
        def verify(op,input_id,parameters):
            if op!='e'*32 or input_id!='b'*32 or parameters!=self.raw['parameters']:raise ValueError('OFFLINE_SYNTHETIC_PROVENANCE_REJECT')
            return {'operationId':op,'model':'OFFLINE_SYNTHETIC_ONLY','providerRecordSha256':'f'*64,'parameters':parameters}
        self.store.approved_language_operation=verify
        t=self.store.submit(self.photo,metadata,'image/png');self.assertEqual(t['preset']['languageProposal']['operationId'],'e'*32)
        self.assertIn('languageProposal',self.executor.requests[-1]['preset'])
        self.store.close();self.store=SchemeStore(Path(self.temp.name)/'tasks',self.presets,lighting_capabilities=self.cap)
        self.assertEqual(self.store.get(t['taskId'])['preset']['languageProposal']['operationId'],'e'*32)

if __name__=='__main__':unittest.main()
