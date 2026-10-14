"""CPU/math and durable wiring acceptance. Never a neural/photo quality claim."""
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'project'))
import light_console as c
import lighting
import numpy as np

class ConsoleTests(unittest.TestCase):
    def setUp(self):
        self.envs={e['id']:e for e in json.loads((ROOT/'project/runtime/environments.json').read_text())}
        self.p=c.initial(self.envs['sunny'])
        self.policy={'revision':'parameterized-engineering-v2','legacyRevision':'sunny-bounded-approximate-preview-v1','parameterized':True,'approvedVariants':{'sunny':[[0,.7],[45,1]]}}
    def procedural(self):
        p=copy.deepcopy(self.p);p.update(mode='procedural',environmentId=None,environmentSha256=None,zones=[{'id':'key','name':'主光','enabled':True,'azimuthDeg':0,'elevationDeg':30,'strength':3,'color':'#ffffff','sizeDeg':25}]);return p
    def test_periodic(self):
        for a,b in [(0,360),(-30,330),(15,375)]:
            self.assertEqual(lighting.identity(c.normalize({**self.p,'offsetDeg':a},self.envs)),lighting.identity(c.normalize({**self.p,'offsetDeg':b},self.envs)))
    def test_rotation_direction_and_precision(self):
        a=np.zeros((16,32,3),dtype='float32');a[8,4]=1
        x=c.loaded_latlong(a,0,1);y=c.loaded_latlong(a,45,1)
        self.assertEqual(np.argmax(x[8,:,0]),11);self.assertEqual(np.argmax(y[8,:,0]),15)
        np.testing.assert_array_equal(x,c.loaded_latlong(a,360,1))
        np.testing.assert_array_equal(x,c.loaded_latlong(a,.1,1)) # subpixel input rotation deliberately quantized
    def test_rejects_nonfinite_unknown_paths_and_versions(self):
        for p in [{**self.p,'offsetDeg':float('nan')},{**self.p,'strength':float('inf')},{**self.p,'strength':True},{**self.p,'strength':4.1},{**self.p,'path':'C:/secret.hdr'},{**self.p,'preprocessingVersion':'other'},{**self.p,'environmentId':'../../secret'}]:
            with self.subTest(p=p),self.assertRaises(ValueError):c.normalize(p,self.envs)
    def test_hdr_roundtrip_deterministic(self):
        p=self.procedural();a=c.synthesize(c.normalize(p,self.envs));data=c.encode_hdr(a);b=c.decode_hdr(data)
        self.assertEqual(data,c.encode_hdr(c.synthesize(p)));self.assertTrue(np.isfinite(b).all());self.assertLess(np.abs(a-b).max(),.016)
    def test_color_linear(self):
        self.assertAlmostEqual(c.srgb('#808080')[0],.2158605,6)
        p=self.procedural();p['zones'][0]['color']='#0080ff';a=c.synthesize(p)
        self.assertGreater(a[:,:,2].max(),a[:,:,1].max());self.assertGreater(a[:,:,1].max(),a[:,:,0].max())
    def test_seam_poles(self):
        p=self.procedural();a=c.synthesize(p);np.testing.assert_allclose(a[:,0],a[:,-1],atol=1e-6)
        p['zones'][0]['elevationDeg']=90;a=c.synthesize(p);np.testing.assert_allclose(a[:,0],a[:,128],atol=1e-6)
    def test_switch_size_multi_strength(self):
        p=self.procedural();a=c.synthesize(p)
        for kind in ('enabled','sizeDeg','color','strength','multi'):
            q=copy.deepcopy(p)
            if kind=='multi':q['zones'].append({**q['zones'][0],'id':'fill','azimuthDeg':180})
            else:q['zones'][0][kind]={'enabled':False,'sizeDeg':70,'color':'#6688ff','strength':.5}[kind]
            self.assertNotEqual(c.sha(a.tobytes()),c.sha(c.synthesize(q).tobytes()))
    def test_resource_limits(self):
        p=self.procedural()
        for q in [{**p,'zones':p['zones']*4},{**p,'zones':p['zones']*2},{**p,'zones':[{**p['zones'][0],'sizeDeg':0}]}]:
            with self.assertRaises(ValueError):c.normalize(q,self.envs)
        for w,h in [(64,64),(8192,4096)]:
            with self.assertRaises(ValueError):c.synthesize(p,w,h)
    def test_decode_failure_and_oversized_header(self):
        for data in [b'bad',b'#?RADIANCE\n'+b'x'*2048,c.encode_hdr(c.synthesize(self.procedural()))[:-1],b'#?RADIANCE\nFORMAT=32-bit_rle_rgbe\n\n-Y 3000 +X 6000\n']:
            with self.assertRaises(ValueError):c.decode_hdr(data)
    def test_import_content_identity_and_preservation(self):
        with tempfile.TemporaryDirectory() as t:
            library=c.EnvironmentLibrary(t,list(self.envs.values()));data=c.encode_hdr(c.synthesize(self.procedural()));v=library.import_bytes(data,'灯光')
            self.assertEqual(v['sha256'],c.sha(data));self.assertEqual((Path(t)/(v['sha256']+'.original.hdr')).read_bytes(),data)
            v2=library.import_bytes(data,'同字节新名称');self.assertEqual(v['id'],v2['id'])
            q={**self.p,'environmentId':v['id'],'environmentSha256':v['sha256']};c.normalize(q,library.environments)
            self.assertIsNotNone(library.derived(q));self.assertIn(v['id'],c.EnvironmentLibrary(t,list(self.envs.values())).environments)
    def test_relative_ai_equals_manual_without_mutation(self):
        p=self.procedural();q=c.resolve_operations(p,[{'op':'rotate','delta':30},{'op':'exposure','delta':-.5},{'op':'edit_zone','id':'key','changes':{'sizeDeg':50}}],self.envs)
        manual=copy.deepcopy(p);manual.update(offsetDeg=30,strength=2**-.5);manual['zones'][0]['sizeDeg']=50
        self.assertEqual(q,c.normalize(manual,self.envs));self.assertEqual(p['zones'][0]['sizeDeg'],25)
    def test_invalid_ai_operations(self):
        for operations in [[{'op':'exposure','delta':3}],[{'op':'set','field':'path','value':'C:/secret'}],[{'op':'edit_zone','id':'missing','changes':{}}],[{'op':'upload','path':'x'}]]:
            with self.assertRaises(ValueError):c.resolve_operations(self.p,operations,self.envs)
    def test_legacy_identity_exact(self):
        for offset,strength in [(0,1),(0,.7),(45,1)]:
            raw={'environmentId':'sunny','offsetDeg':offset,'strength':strength}
            before={'schemaVersion':1,'environmentId':'sunny','hdrSha256':self.envs['sunny']['sha256'],'offsetDeg':offset,'strength':strength,'processing':'fixed-upstream-loading-v1' if (offset,strength)==(0,1) else 'hdr-controls-v1','capabilityRevision':'legacy-fixed-preset' if (offset,strength)==(0,1) else self.policy['legacyRevision']}
            after=lighting.normalize_parameters(raw,self.envs,self.policy)
            self.assertEqual(before,after);self.assertEqual(lighting.identity(before),lighting.identity(after))
    def test_forward_identity_changes_and_inverse_excludes_light(self):
        a=c.normalize(self.procedural(),self.envs);b=c.normalize({**a,'strength':.25},self.envs)
        self.assertNotEqual(lighting.identity(a),lighting.identity(b))
        from inference.reuse import identity
        import inspect
        self.assertNotIn("request['preset']",inspect.getsource(identity))
        self.assertNotIn('lightingAdapterVersion',inspect.getsource(identity))
    def test_offline_ai_contract_preserves_reference(self):
        from recipe_language import RecipeLanguage
        sent=[]
        proposal={'status':'ready','action':'revise','parameters':{'operations':[{'op':'rotate','delta':30},{'op':'exposure','delta':-.5}]},'name':'','reason':'旋转环境并降低输入强度，尚未应用。','question':''}
        def transport(payload,remaining):sent.append(payload);return json.dumps(proposal,ensure_ascii=False)
        scheme={'schemaVersion':1,'planId':'a'*32,'version':1,'name':'测试','parameters':self.p,'inputId':'b'*32,'parentVersion':None}
        with tempfile.TemporaryDirectory() as t:
            ai=RecipeLanguage(list(self.envs.values()),self.policy,'OFFLINE_SYNTHETIC_KEY',Path(t)/'ledger.json',transport=transport)
            value=ai.recommend({'currentScheme':scheme,'currentResult':{'status':'草稿','kind':'none','artifactId':None},'text':'环境顺时针转30度，整体暗半档','history':[],'replyLanguage':'zh'})
            self.assertEqual(value['parameters']['offsetDeg'],30);self.assertEqual(value['parameters']['strength'],2**-.5);self.assertEqual(scheme['parameters']['offsetDeg'],0)
            context=json.loads(sent[0]['messages'][1]['content']);self.assertFalse(context['photosReceived']);self.assertIsNone(context['allowedCombinations'])
    def test_real_store_and_executor_derived_wiring_restart(self):
        from scheme_store import SchemeStore
        from runtime.executor import SchemeExecutor
        from PIL import Image
        class DispatchOnly:
            supports_lighting_parameters=True
            def submit(self,folder,request):self.request=request
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);dispatch=DispatchOnly();store=SchemeStore(root/'tasks',list(self.envs.values()),dispatch,lighting_capabilities=self.policy)
            try:
                recipe=self.procedural();recipe['offsetDeg']=360
                scheme={'schemaVersion':1,'planId':'a'*32,'version':1,'name':'主光','parameters':recipe,'inputId':'b'*32,'parentVersion':None}
                photo=io.BytesIO();Image.new('RGB',(64,80),(120,90,50)).save(photo,'PNG')
                task=store.submit(photo.getvalue(),{'requestId':'c'*32,'inputId':'b'*32,'name':'synthetic','lightingScheme':scheme},'image/png')
                request=dispatch.request;p=request['preset'];self.assertEqual(p['scheme']['parameters']['offsetDeg'],0)
                self.assertEqual(p['derivedHdrSha256'],c.sha(c.encode_hdr(c.synthesize(c.normalize(recipe,self.envs)))))
                config=root/'config.json';config.write_text(json.dumps({'required_environment_ids':['sunny']}))
                executor=SchemeExecutor.__new__(SchemeExecutor);executor.config_path=config
                folder=store.directory(task['taskId']);executor.prepare_request(folder,request)
                self.assertEqual(c.sha((folder/'inputs/lighting.hdr').read_bytes()),p['derivedHdrSha256'])
                original=(folder/'request.json').read_bytes();store.close()
                store=SchemeStore(root/'tasks',list(self.envs.values()),lighting_capabilities=self.policy)
                self.assertEqual((folder/'request.json').read_bytes(),original);self.assertIn(p['id'],store.presets)
            finally:store.close()
    def test_bounded_session_one_constructor_math_stub_only(self):
        from runtime import entry
        from types import SimpleNamespace
        roots=[];events=[];count=[]
        class ModelStub:
            def __init__(self,**kw):count.append(1);self.generate_video=lambda:None
        module=SimpleNamespace(DiffusionRendererPipeline=ModelStub)
        timeline=SimpleNamespace(emit=lambda *a,**kw:events.append((a,kw)))
        def offline(args,module,timeline,root,validator):module.DiffusionRendererPipeline();module.DiffusionRendererPipeline()
        with tempfile.TemporaryDirectory() as t:
            for i in range(3):
                p=Path(t)/str(i);p.mkdir();(p/'identities.json').write_text('{"0":{}}');roots.append(p)
            with patch.object(entry,'_scheme_forward',offline):entry.run_recipe_session(SimpleNamespace(),module,timeline,roots,lambda x:None)
        self.assertEqual(len(count),1);self.assertIs(module.DiffusionRendererPipeline,ModelStub)

if __name__=='__main__':unittest.main()
