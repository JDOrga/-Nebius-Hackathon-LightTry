"""OFFLINE SYNTHETIC scheduling/transport; no paid calls or real GPU proof."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'project'));sys.path.insert(0,str(ROOT/'project/tests'))
from inference.jobs import atomic,read
from next.runtime.key_unknowns import recipes
from next.runtime.joint import energy,verify_joint,changes
from next.runtime.calibration import pixel_difference,roi_metrics,IDS,VERSION
from light_console import synthesize,encode_hdr,decode_hdr
from next.language import RecipeLanguage
from next.accepted import load_accepted_many
import test_joint
ENVS=test_joint.ENVS
spec=importlib.util.spec_from_file_location('context_acceptance',ROOT/'scripts/nemotron_context_acceptance.py')
TEXT=importlib.util.module_from_spec(spec);spec.loader.exec_module(TEXT)
PACKAGE=ROOT/'.local/calibration-20261013/final-five-package'


class FiveTests(unittest.TestCase):
    def test_order_exact_and_legacy_preserved(self):
        self.assertEqual(list(recipes(ENVS)),IDS);self.assertEqual(list(recipes(ENVS,repeat=False)),IDS[1:])
        self.assertEqual(verify_joint(ROOT/'.local/lighttry-joint-20261012/workbench-import/next-key-package-v2/packet')['forwardTarget'],4)

    def test_five_packet_recipe_and_c_exact_historical(self):
        p=verify_joint(PACKAGE/'packet');self.assertEqual((p['forwardTarget'],p['inverseExecutionsTarget'],p['initializationsTarget']),(5,0,1))
        h=next(r for r in p['historicalReferences'] if r['caseId']=='C');c=p['cases'][0]
        self.assertEqual(c['parameters'],h['parameters']);self.assertEqual(c['hdrSha256'],h['hdrSha256'])

    def test_energy_all_rgb_and_peak_changes(self):
        import numpy as np
        r=recipes(ENVS);base=energy(decode_hdr(encode_hdr(synthesize(r['C-repeat']))))
        for n in ('width-45','width-70'):
            value=energy(decode_hdr(encode_hdr(synthesize(r[n]))))
            self.assertTrue(np.all(np.abs(np.array(value['sphericalIntegralRGB'])/base['sphericalIntegralRGB']-1)<=.005))
            self.assertLess(value['peakRGB'][0],base['peakRGB'][0]);self.assertEqual(r[n]['ambient'],r['C-repeat']['ambient'])

    def test_one_init_five_forward_rng_reset_per_item_and_resume(self):
        fixture=test_joint.SessionTests('test_one_initialization_six_forwards_and_resume_zero');fixture.setUp()
        try:
            fixture.plan['version']=VERSION
            old=fixture.plan['cases'][0];fixture.plan['cases']=[]
            for n,p in recipes(ENVS).items():
                c={**copy.deepcopy(old),'id':n,'parameters':p,'hdrFile':'recipes/'+n+'.hdr'}
                (fixture.prep/c['hdrFile']).write_bytes(b'OFFLINE_SYNTHETIC');fixture.plan['cases'].append(c)
            atomic(fixture.prep/'joint.json',fixture.plan)
            resets=[];fixture.module.misc=types.SimpleNamespace(set_random_seed=lambda seed:resets.append(seed))
            fixture.run_session();self.assertEqual(fixture.count,1);self.assertEqual(resets,[1000]*5)
            events=[json.loads(v) for v in (fixture.prep/'timing.jsonl').read_text().splitlines()]
            self.assertEqual([e['caseId'] for e in events if e['event']=='joint_forward_start'],IDS)
            last=next(e for e in events if e['event']=='joint_complete');self.assertEqual((last['initializationCount'],last['forwardCount'],last['inverseCount']),(1,5,0))
            for n in IDS:self.assertTrue((fixture.prep/'run/cases'/n/'0/complete.json').exists())
            fixture.run_session();self.assertEqual(resets,[1000]*5);self.assertEqual(fixture.count,1)
        finally:fixture.tearDown()

    def test_rng_order_independent_noise_not_gpu_equality(self):
        import numpy as np
        from next.runtime.entry import observe_generation
        calls=[]
        p=types.SimpleNamespace(generate_video=lambda self: calls.append(np.random.rand(8)))
        module=types.SimpleNamespace(misc=types.SimpleNamespace(set_random_seed=np.random.seed))
        timer=types.SimpleNamespace(emit=lambda *a,**k:None)
        from contextlib import nullcontext
        timer.span=lambda *a,**k:nullcontext()
        observe_generation(p,module,types.SimpleNamespace(seed=1000),'forward',timer)
        p.generate_video(p);np.random.rand(23);p.generate_video(p)
        self.assertTrue(np.array_equal(calls[0],calls[1]))

    def test_pixel_hash_vs_decode_independent(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as t:
            a=Path(t)/'a.png';b=Path(t)/'b.png';Image.new('RGB',(10,10),'gray').save(a);b.write_bytes(a.read_bytes()+b'trailing-metadata')
            d=pixel_difference(a,b);self.assertFalse(d['fileEqual']);self.assertTrue(d['decodedPixelsEqual']);self.assertEqual(d['mae8bit'],0)

    def test_fixed_roi_reuses_original_no_background_dominance(self):
        from PIL import Image
        import numpy as np
        roi=read(PACKAGE/'roi.json');original=read(ROOT/'controlled-tests/20261007-four-materials/prepared_inputs.json')['images'][0]
        self.assertEqual(roi['rectanglesPixels'],original['derived_roi_xyxy']);self.assertEqual(roi['subjectMaskPolygonPixels'],original['interior_mask_derived_polygon'])
        with tempfile.TemporaryDirectory() as t:
            a=Path(t)/'a.png';b=Path(t)/'b.png';im=np.ones((704,1280,3),dtype='uint8')*80;Image.fromarray(im).save(a);im[:,:300]=255;Image.fromarray(im).save(b)
            self.assertEqual(roi_metrics(a,roi),roi_metrics(b,roi))

    def test_historical_import_duplicate_idempotent(self):
        import server
        base=ROOT/'.local/lighttry-joint-20261012/ai-confirmed-package';catalog=server.load_catalog(ROOT/'.local/demo-candidate-20261010/demo-assets')
        studies,files,schemes=load_accepted_many([base,base],catalog)
        self.assertEqual((len(studies),len(files),len(schemes)),(7,7,7))

    def synthetic_finalize(self, review=None):
        from next.runtime import calibration
        import shutil
        temp=tempfile.TemporaryDirectory();base=Path(temp.name);packet=base/'packet';packet.mkdir();job=base/'execution';root=job/'results';root.mkdir(parents=True)
        plan=read(PACKAGE/'packet/joint.json');atomic(packet/'joint.json',plan)
        for name in ('roi.json','visual-review-template.json'):shutil.copyfile(PACKAGE/name,base/name)
        hist=next(r for r in plan['historicalReferences'] if r['caseId']=='C')
        results={}
        for case in plan['cases']:
            d=root/'cases'/case['id'];(d/'0').mkdir(parents=True)
            marker={'identity':{'input':'OFFLINE_SYNTHETIC','case':case,'joint':plan},'randomPolicy':'OFFLINE_SYNTHETIC_RESET'}
            atomic(d/'0/complete.json',marker);atomic(d/'model-condition.json',{'env_nrm':{'sha256':'OFFLINE_SYNTHETIC_SAME'}})
            results[case['id']]={'path':hist['paths']['frame'],'sha256':hist['outputSha256']}
        atomic(root/'execution.json',{'status':'succeeded','executionStopped':True,'OFFLINE_SYNTHETIC':True})
        events=[{'event':'calibration_rng_reset','caseId':n} for n in IDS]+[{'event':'joint_complete','initializationCount':1,'forwardCount':5,'inverseCount':0}]
        (root/'forward-timing.jsonl').write_text('\n'.join(json.dumps(e) for e in events),encoding='utf-8')
        audit={k:True for k in ('inputEqual','inverseEqual','runConfigEqual','recipeEqual','actualHDREqual')}
        audit.update(baseIdentityDiff=[],modelConditionDiff=[],conditionFieldDiff=[])
        path=None
        if review:path=base/'manual.json';atomic(path,review)
        try:
            with patch.object(calibration,'validate_case',side_effect=lambda p,r,c:results[c['id']]),patch.object(calibration,'identity_audit',return_value=audit):
                value=calibration.finalize(base,path)
            self.assertEqual(read(job/'summary.json')['visual'],value['visual'])
            return value
        finally:temp.cleanup()

    def test_default_never_auto_passes_even_identical_pixels(self):
        value=self.synthetic_finalize();self.assertFalse(value['historicalComparable']);self.assertEqual(value['visual'],'pending')
        self.assertEqual(value['direction'],'paused-historical-baseline-audit')

    def test_historical_drift_does_not_block_current_width_uncertain(self):
        review=read(PACKAGE/'visual-review-template.json');review['historicalBaseline']['visual']='fail'
        review['width'].update(verdict='uncertain',currentIdentityAudit='pass',highlights='OFFLINE_SYNTHETIC no clear range response',shadowEdges='OFFLINE_SYNTHETIC no separable edge',reason='OFFLINE_SYNTHETIC current cohort comparison independent of historical drift')
        value=self.synthetic_finalize(review);self.assertEqual(value['direction'],'paused-historical-baseline-audit')
        self.assertEqual(value['width'],'uncertain');self.assertTrue(value['currentWidthIdentityAudit']['comparable'])


class ContextTests(unittest.TestCase):
    def setUp(self):
        self.scope=read(ROOT/'.local/calibration-20261013/text/scope.json');self.f=self.scope['scheme']['parameters']
    def proposal(self,p):return {'status':'ready','action':'revise','parameters':p,'name':'暗面补光','reason':'根据 F 的实测记录，补光曾抬亮暗面，增加输入补光强度，效果仍需验证，不能保证保色。','question':''}
    def test_scope_f_selected_cf_and_seven_no_pixels(self):
        self.assertEqual([c['caseId'] for c in self.scope['cases']],list('ABCDEF')+['AI'])
        self.assertEqual(self.scope['selectedCase'],'F');self.assertEqual(self.scope['maxCalls'],4)
        self.assertFalse(self.scope['photosReceived']);self.assertFalse(self.scope['oldAdditionalScopeInherited'])
    def test_round_one_and_two_actual_diff(self):
        p=copy.deepcopy(self.f);p['zones'][1]['strength']=.9
        self.assertEqual(TEXT.semantic(self.f,self.proposal(p),'first',ENVS)[0]['field'],'/zones/1/strength')
        q=copy.deepcopy(p);q['zones'][1]['strength']=.8
        self.assertEqual(TEXT.semantic(p,self.proposal(q),'second',ENVS)[0]['before'],.9)
    def test_extra_field_rejected_and_ids_rejected(self):
        p=copy.deepcopy(self.f);p['zones'][1]['strength']=.9;p['zones'][0]['sizeDeg']=70
        with self.assertRaisesRegex(ValueError,'ONLY_FILL'):TEXT.semantic(self.f,self.proposal(p),'first',ENVS)
        p=copy.deepcopy(self.f);p['zones'].reverse()
        with self.assertRaisesRegex(ValueError,'STABLE'):TEXT.semantic(self.f,self.proposal(p),'first',ENVS)
    def test_explanation_source_required(self):
        p=copy.deepcopy(self.f);p['zones'][1]['strength']=.9;v=self.proposal(p);v['reason']='我建议提高补光。'
        with self.assertRaisesRegex(ValueError,'BASIS'):TEXT.semantic(self.f,v,'first',ENVS)
    def test_synthetic_transport_context_never_real_acceptance(self):
        p=copy.deepcopy(self.f);p['zones'][1]['strength']=.9;sent=[]
        def wire(payload,remaining):sent.append(copy.deepcopy(payload));return json.dumps(self.proposal(p),ensure_ascii=False)
        with tempfile.TemporaryDirectory() as t:
            policy=read(ROOT/'project/next/runtime/policy.json');policy['parameterized']=True
            ledger=Path(t)/'ledger.json';service=RecipeLanguage(list(ENVS.values()),policy,'OFFLINE_SYNTHETIC',ledger,max_calls=4,budget=.08,transport=wire,measured_cases=self.scope['cases'],full_procedural_recipe=True,
                acceptance_validator=lambda p:TEXT.semantic(self.f,p,'first',ENVS))
            result=service.recommend({'currentScheme':self.scope['scheme'],'currentResult':{'status':'historical-F','kind':'study','artifactId':self.scope['historicalFOutputSha256']},'text':TEXT.FIRST,'history':[],'replyLanguage':'zh'})
            self.assertFalse(result['modelCalled']);self.assertEqual(result['source'],'OFFLINE_SYNTHETIC');self.assertIn('SYNTHETIC',read(ledger)['mode'])
            context=json.loads(sent[0]['messages'][1]['content']);self.assertEqual(context['selectedScheme']['parameters'],self.f)
            self.assertEqual([c['caseId'] for c in context['verifiedMeasuredCases']],['C','F']);self.assertEqual(len(context['measuredCaseNotes']),7);self.assertFalse(context['photosReceived'])
            self.assertLessEqual(len(json.dumps(sent[0],ensure_ascii=False).encode()),15000)
    def test_second_cannot_use_unconfirmed_or_synthetic_proposal(self):
        with tempfile.TemporaryDirectory() as t:
            atomic(Path(t)/'scope.json',self.scope)
            atomic(Path(t)/'first-applied.json',{'operationId':'a'*32,'confirmed':True,'source':'OFFLINE_SYNTHETIC','modelCalled':False})
            atomic(Path(t)/'provider-ledger.json',{'mode':'OFFLINE_SYNTHETIC_NOT_NEMOTRON','records':[]})
            with self.assertRaisesRegex(ValueError,'REAL_CONFIRMED'):TEXT.confirmed(Path(t),'first')


if __name__=='__main__':unittest.main(verbosity=2)
