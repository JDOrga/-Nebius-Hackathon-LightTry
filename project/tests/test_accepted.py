import copy,hashlib,json,pathlib,sys,tempfile,unittest,urllib.request
import threading
from http.server import ThreadingHTTPServer
ROOT=pathlib.Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'project'))
import shared_http as server
from accepted import load_accepted,measured_context
from runtime.key_unknowns import recipes
from runtime.joint import energy,verify_joint
from light_console import synthesize,encode_hdr,decode_hdr
from recipe_language import RecipeLanguage
BASE=ROOT/'.local/lighttry-joint-20261012/ai-confirmed-package'
class AcceptedTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.catalog=server.load_catalog(ROOT/'.local/demo-candidate-20261010/demo-assets');cls.studies,cls.files,cls.schemes=load_accepted(BASE,cls.catalog)
  from studio import Handler
  from scheme_store import SchemeStore
  from light_console import EnvironmentLibrary
  cls.temp=tempfile.TemporaryDirectory();folder=pathlib.Path(cls.temp.name)
  class FixtureHandler(Handler):
   def log_message(self,*args):pass
  FixtureHandler.assets_dir=ROOT/'.local/demo-candidate-20261010/demo-assets'
  FixtureHandler.catalog=cls.catalog
  FixtureHandler.studies=cls.studies;FixtureHandler.study_files=cls.files
  FixtureHandler.imported_schemes=cls.schemes;FixtureHandler.recipe_language=None
  FixtureHandler.lighting_capabilities={'parameterized':True,'revision':'OFFLINE_TEST','approvedVariants':{}}
  FixtureHandler.environment_library=EnvironmentLibrary(folder/'environments',cls.catalog['presets'])
  cls.store=SchemeStore(folder/'tasks',cls.catalog['presets'],None,lighting_capabilities=FixtureHandler.lighting_capabilities)
  FixtureHandler.task_store=cls.store
  cls.store.environment_library=FixtureHandler.environment_library
  cls.http=ThreadingHTTPServer(('127.0.0.1',0),FixtureHandler)
  cls.base_url='http://127.0.0.1:'+str(cls.http.server_port)
  cls.thread=threading.Thread(target=cls.http.serve_forever,daemon=True);cls.thread.start()
 @classmethod
 def tearDownClass(cls):
  cls.http.shutdown();cls.thread.join();cls.http.server_close();cls.store.close();cls.temp.cleanup()
 def test_seven_exact_photo_recipe_hashes(self):
  self.assertEqual([s['caseId'] for s in self.studies],list('ABCDEF')+['AI']);self.assertEqual(len({s['planId'] for s in self.schemes}),7)
  for s in self.studies:self.assertEqual(s['result']['sha256'],hashlib.sha256(self.files[s['result']['url'].split('/')[-1]][0].read_bytes()).hexdigest());self.assertEqual(s['recipeKey'],s['result']['recipeKey'])
 def test_wrong_photo_fails(self):
  c=copy.deepcopy(self.catalog)
  for s in c['samples']:s['input']['sha256']='a'*64
  with self.assertRaisesRegex(ValueError,'PHOTO'):load_accepted(BASE,c)
 def test_original_mismatch_fails(self):
  c=copy.deepcopy(self.catalog);c['samples'][0]['original']['sha256']='a'*64
  with self.assertRaisesRegex(ValueError,'ORIGINAL'):load_accepted(BASE,c)
 def test_ai_trusted_cases_not_intensity_whitelist(self):
  cases=measured_context(self.studies);self.assertEqual(len(cases),7);sent=[]
  scheme={k:self.schemes[2][k] for k in ['schemaVersion','planId','version','name','parameters','inputId','parentVersion']};good={'status':'ready','action':'revise','parameters':copy.deepcopy(scheme['parameters']),'name':'方向变体','reason':'方向与能量都需验证，当前结果不能保证保真。','question':''}
  def wire(payload,remaining):sent.append(payload);return json.dumps(good,ensure_ascii=False)
  with tempfile.TemporaryDirectory() as t:
   adapter=RecipeLanguage(self.catalog['presets'],{'parameterized':True,'revision':'TEST','approvedVariants':{}},'OFFLINE_SYNTHETIC',pathlib.Path(t)/'ledger.json',transport=wire,measured_cases=cases)
   adapter.recommend({'currentScheme':scheme,'currentResult':{'status':'已生成','kind':'study','artifactId':self.studies[2]['result']['sha256']},'text':'解释方向对亮度的影响','history':[],'replyLanguage':'zh'})
  context=json.loads(sent[0]['messages'][1]['content']);self.assertEqual([c['caseId'] for c in context['verifiedMeasuredCases']],['C','F']);self.assertEqual(len(context['measuredCaseNotes']),7);self.assertFalse(context['photosReceived']);self.assertEqual(context['selectedScheme']['parameters'],scheme['parameters']);self.assertIn('do not prescribe multiplying all intensities',sent[0]['messages'][0]['content'])
 def test_four_targeted_cases_and_energy(self):
  env={e['id']:e for e in self.catalog['presets']};r=recipes(env,repeat=False);self.assertEqual(list(r),['direction-225','direction-315','width-45','width-70'])
  C=self.studies[2]['parameters'];target=energy(decode_hdr(encode_hdr(synthesize(C))))['sphericalIntegralRGB'][0]
  for k,p in r.items():
   for f in ['ambient','offsetDeg','strength']:self.assertEqual(p[f],C[f])
   if k.startswith('width'):
    e=energy(decode_hdr(encode_hdr(synthesize(p))))['sphericalIntegralRGB'][0];self.assertLess(abs(e/target-1),.005);self.assertNotEqual(p['zones'][0]['strength'],3)
 def test_next_packet_four_no_full_rerun(self):
  p=verify_joint(ROOT/'.local/lighttry-joint-20261012/workbench-import/next-key-package-v2/packet');self.assertEqual(p['forwardTarget'],4);self.assertEqual([c['caseId'] for c in p['reusedReferences']],['B','C'])
 def test_imported_scheme_wire_roundtrip(self):
  token=json.load(urllib.request.urlopen(self.base_url+'/api/inference'))['csrfToken']
  for scheme in self.schemes:
   wire={k:scheme[k] for k in ('schemaVersion','planId','version','name','parameters','inputId','parentVersion')}
   request=urllib.request.Request(self.base_url+'/api/lighting/normalize',data=json.dumps(wire).encode(),headers={'Content-Type':'application/json','X-LightTry-Token':token})
   result=json.load(urllib.request.urlopen(request));self.assertEqual(result['recipeKey'],scheme['recipeKey'])
 def test_actual_http_downloads_all_seven(self):
  response=json.load(urllib.request.urlopen(self.base_url+'/api/accepted-results'));self.assertEqual(len(response['schemes']),7)
  for s in response['studies']:
   q=urllib.request.urlopen(self.base_url+s['result']['downloadUrl']);self.assertIn('attachment',q.headers['Content-Disposition']);self.assertEqual(hashlib.sha256(q.read()).hexdigest(),s['result']['sha256'])
if __name__=='__main__':unittest.main(verbosity=2)
