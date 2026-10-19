import copy,json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from recipe_language import RecipeLanguage,validate
from lighting import normalize_scheme
from language import LanguageError
class ChatTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.presets=json.loads((ROOT/'data/catalog.json').read_text(encoding='utf-8'))['presets'];self.env={p['id']:p for p in self.presets};self.policy={'revision':'OFFLINE_SYNTHETIC','approvedVariants':{'sunny':[[0,.7],[45,1]]}};self.sent=[]
  self.good={'status':'ready','action':'revise','parameters':{'environmentId':'sunny','offsetDeg':0,'strength':.7},'name':'','reason':'较低倍率可能偏暗，需比较实际结果。','question':''}
  self.scheme={'schemaVersion':1,'planId':'a'*32,'version':1,'name':'当前方案','parameters':{'environmentId':'sunny','offsetDeg':0,'strength':1},'inputId':'b'*32,'parentVersion':None}
  self.body={'currentScheme':self.scheme,'currentResult':{'status':'已生成','kind':'none','artifactId':None},'text':'偏暗','history':[],'replyLanguage':'zh'}
  self.normal=normalize_scheme(self.scheme,self.env,self.policy)
  self.body['chat']={'schemaVersion':1,'sessionId':'c'*32,'requestId':'d'*32,'snapshot':{k:self.normal[k] for k in ('inputId','planId','version','recipeKey')},'messages':[],'operations':[]}
 def tearDown(self):self.tmp.cleanup()
 def adapter(self,values):
  def wire(p,t):
   self.sent.append(copy.deepcopy(p));v=values.pop(0)
   if isinstance(v,Exception):raise v
   return json.dumps(v,ensure_ascii=False)
  return RecipeLanguage(self.presets,self.policy,'OFFLINE_SYNTHETIC_KEY',Path(self.tmp.name)/'ledger.json',transport=wire)
 def test_two_turns_transport_receives_history_and_proposal_not_current(self):
  a=self.adapter([self.good,{**self.good,'status':'explanation','parameters':None}]);v=a.recommend(self.body)
  b=copy.deepcopy(self.body);b['chat']['requestId']='e'*32;b['text']='为什么推荐这个';b['chat']['messages']=[{'role':'user','text':'偏暗'},{'role':'assistant','text':v['reason']}];b['chat']['operations']=[{'operationId':v['operationId'],'state':'proposed'}];r=a.recommend(b)
  ctx=json.loads(self.sent[-1]['messages'][1]['content']);self.assertEqual(ctx['selectedScheme']['parameters']['strength'],1);self.assertEqual(len(ctx['boundedConversation']['messages']),2);self.assertEqual(ctx['boundedConversation']['verifiedProposalHistory'][0]['reportedState'],'proposed');self.assertEqual(r['status'],'explanation');self.assertFalse(ctx['photosReceived']);self.assertNotIn('name',ctx['selectedScheme']);self.assertNotIn('chat',self.sent[-1]['messages'][0]['content'])
 def test_dedup_restart_and_conflict(self):
  a=self.adapter([self.good]);v=a.recommend(self.body);self.assertEqual(a.recommend(self.body),v);self.assertEqual(len(self.sent),1)
  a2=RecipeLanguage(self.presets,self.policy,'OFFLINE_SYNTHETIC_KEY',a.ledger_path,transport=lambda *_:self.fail('duplicate provider call'));self.assertEqual(a2.recommend(self.body),v)
  b=copy.deepcopy(self.body);b['text']='不同';
  with self.assertRaises(LanguageError):a.recommend(b)
 def test_timeout_repeat_never_resends(self):
  a=self.adapter([LanguageError('LANGUAGE_TIMEOUT','超时')])
  for _ in range(2):
   with self.assertRaises(LanguageError):a.recommend(self.body)
  self.assertEqual(len(self.sent),1)
 def test_snapshot_illegal_history_and_sensitive_block_before_transport(self):
  a=self.adapter([])
  for mutate in [lambda b:b['chat']['snapshot'].update(version=2),lambda b:b['chat'].update(messages=[{'role':'system','text':'x'}]),lambda b:b['chat'].update(messages=[{'role':'user','text':'x'}]*9),lambda b:b.update(text='ghp_SECRET'),lambda b:b['chat'].update(operations=[{'operationId':'1'*32,'state':'applied'}]),lambda b:b['chat'].update(validated=True)]:
   b=copy.deepcopy(self.body);mutate(b)
   with self.assertRaises(LanguageError):a.recommend(b)
  self.assertFalse(self.sent)
 def test_applied_manual_snapshot_wins(self):
  a=self.adapter([self.good,self.good]);v=a.recommend(self.body);b=copy.deepcopy(self.body);b['chat']['requestId']='e'*32;b['currentScheme']['version']=2;b['currentScheme']['parentVersion']=1;b['currentScheme']['parameters']['offsetDeg']=45;normalized=normalize_scheme(b['currentScheme'],self.env,self.policy);b['chat']['snapshot']={k:normalized[k] for k in ('inputId','planId','version','recipeKey')};b['chat']['operations']=[{'operationId':v['operationId'],'state':'applied'}];a.recommend(b);ctx=json.loads(self.sent[-1]['messages'][1]['content']);self.assertEqual(ctx['selectedScheme']['parameters']['offsetDeg'],45);self.assertTrue(ctx['boundedConversation']['currentSnapshotOverridesHistory'])
 def test_reply_kinds_strict_schema_html_and_no_illegal_parameters(self):
  for status in ('explanation','clarification','unsupported'):
   v={**self.good,'status':status,'parameters':None,'question':'需要保留哪个环境？' if status=='clarification' else ''};validate(v,self.env,self.policy,'zh',True)
  for v in [{**self.good,'reason':'ghp_SECRET'},{**self.good,'parameters':{**self.good['parameters'],'strength':1.4}},{**self.good,'validated':True}]:
   with self.assertRaises(LanguageError):validate(v,self.env,self.policy,'zh',True)
  self.assertIsNone(validate({**self.good,'status':'explanation'},self.env,self.policy,'zh',True)['parameters'])
  with self.assertRaises(LanguageError):validate({**self.good,'status':'explanation','parameters':None},self.env,self.policy)
 def test_chat_language_is_a_preference_not_a_rejection_gate(self):
  mixed={**self.good,'status':'explanation','parameters':None,'reason':'\u6211\u53ef\u4ee5\u89e3\u91ca lighting plan \u7684\u8bbe\u7f6e\uff0c\u5e76\u534f\u52a9\u4f60\u8c03\u6574\u5e03\u5149\u3002'}
  self.assertEqual(validate(mixed,self.env,self.policy,'zh',True)['status'],'explanation')
  with self.assertRaises(LanguageError) as caught:validate({**self.good,'reason':mixed['reason']},self.env,self.policy,'zh',False)
  self.assertEqual(caught.exception.code,'LANGUAGE_MISMATCH')
  self.assertEqual(validate({**mixed,'reason':'I can explain the lighting plan'},self.env,self.policy,'zh',True)['status'],'explanation')
 def test_ready_chat_proposal_may_include_followup_but_still_needs_reason(self):
  answer={**self.good,'question':'你想先试这个亮度吗？'}
  self.assertEqual(validate(answer,self.env,self.policy,'zh',True)['question'],answer['question'])
  with self.assertRaises(LanguageError):validate(answer,self.env,self.policy,'zh',False)
  with self.assertRaises(LanguageError):validate({**answer,'reason':''},self.env,self.policy,'zh',True)
 def test_chinese_chat_repairs_english_only_but_allows_mixed_and_requested_english(self):
  english={**self.good,'reason':'Try a slightly lower input multiplier.'}
  chinese={**self.good,'reason':'略微降低输入倍率试试。'}
  a=self.adapter([english,chinese,{**self.good,'reason':'略微降低 HDR input 倍率试试。'},english])
  b=copy.deepcopy(self.body);b['text']='帮我调暗一点';r=a.recommend(b)
  self.assertEqual(r['reason'],chinese['reason']);self.assertEqual(len(self.sent),2)
  self.assertEqual(json.loads(a.ledger_path.read_text())['records'][0]['outcome'],'LANGUAGE_MISMATCH')
  b['chat']['requestId']='e'*32;r=a.recommend(b)
  self.assertIn('HDR input',r['reason']);self.assertEqual(len(self.sent),3)
  b['chat']['requestId']='f'*32;b['text']='请用英文回答：帮我调暗一点';r=a.recommend(b)
  self.assertEqual(r['reason'],english['reason']);self.assertEqual(len(self.sent),4)
 def test_environment_zone_request_repairs_to_procedural_proposal(self):
  from light_console import initial
  self.policy['parameterized']=True;self.body['currentScheme']['parameters']=initial(self.env['sunny'])
  self.normal=normalize_scheme(self.body['currentScheme'],self.env,self.policy)
  self.body['chat']['snapshot']={k:self.normal[k] for k in ('inputId','planId','version','recipeKey')}
  self.body['text']='然后在左上角加一个暖光区'
  zone={'id':'warm_left','name':'左上暖光','enabled':True,'azimuthDeg':315,'elevationDeg':30,'strength':2,'color':'#ffbb88','sizeDeg':40}
  wrong={**self.good,'parameters':{'operations':[{'op':'add_zone','zone':zone}]},'reason':'在左上方添加柔和暖光区。'}
  corrected={**wrong,'parameters':{'operations':[{'op':'set','field':'mode','value':'procedural'},
    {'op':'set','field':'environmentId','value':None},{'op':'set','field':'environmentSha256','value':None},
    {'op':'add_zone','zone':zone}]},'reason':'改为程序化布光并添加暖光区；原环境图会退出，应用前可预览。'}
  a=self.adapter([wrong,corrected]);r=a.recommend(self.body)
  self.assertEqual(len(self.sent),2);self.assertEqual(r['status'],'ready')
  self.assertEqual(r['parameters']['mode'],'procedural');self.assertIsNone(r['parameters']['environmentId'])
  self.assertEqual(r['parameters']['zones'],[zone]);self.assertEqual(self.body['currentScheme']['parameters']['mode'],'environment')
  self.assertIn('Do not require the user to request the mode switch separately.',self.sent[0]['messages'][0]['content'])
  self.assertEqual(json.loads(a.ledger_path.read_text())['records'][0]['outcome'],'INACTIVE_ZONE_CHANGE')
 def test_zero_repair_chinese_ready_keeps_usable_plan_without_paid_retry(self):
  english={**self.good,'reason':'Try a slightly lower input multiplier.','question':'Would you like it darker?'}
  a=self.adapter([english]);a.repair_limit=0;self.body['text']='给我一个方案，帮场景调暗些'
  r=a.recommend(self.body)
  self.assertEqual(r['status'],'ready');self.assertEqual(r['parameters'],english['parameters'])
  self.assertIn('核对下方参数差异',r['reason']);self.assertEqual(r['question'],'')
  self.assertEqual(len(self.sent),1)
  record=json.loads(a.ledger_path.read_text(encoding='utf-8'))['records'][0]
  self.assertEqual(record['repairLimitThisOperation'],0)
  self.assertEqual(record['languageFallback'],'validated-ready-chinese-summary')
 def test_zero_repair_zone_request_converts_only_with_user_intent(self):
  from light_console import initial
  self.policy['parameterized']=True;self.body['currentScheme']['parameters']=initial(self.env['sunny'])
  self.normal=normalize_scheme(self.body['currentScheme'],self.env,self.policy)
  self.body['chat']['snapshot']={k:self.normal[k] for k in ('inputId','planId','version','recipeKey')}
  zone={'id':'warm_left','name':'左上暖光','enabled':True,'azimuthDeg':315,'elevationDeg':30,'strength':2,'color':'#ffbb88','sizeDeg':40}
  wrong={**self.good,'parameters':{'operations':[{'op':'add_zone','zone':zone}]},'reason':'在左上方添加柔和暖光区。'}
  a=self.adapter([wrong,wrong]);a.repair_limit=0;self.body['text']='然后在左上角加一个光区'
  r=a.recommend(self.body)
  self.assertEqual(r['status'],'ready');self.assertEqual(len(self.sent),1)
  self.assertEqual(r['parameters']['mode'],'procedural');self.assertIsNone(r['parameters']['environmentId'])
  self.assertEqual(r['parameters']['zones'],[zone]);self.assertEqual(self.body['currentScheme']['parameters']['mode'],'environment')
  self.assertIn('原环境图不再使用',r['reason'])
  records=json.loads(a.ledger_path.read_text(encoding='utf-8'))['records']
  self.assertEqual(records[0]['localModeConversion'],'environment-zone-to-procedural')
  self.body['chat']['requestId']='e'*32;self.body['text']='保持环境模式，不要切换程序化，但在左上角加一个光区'
  blocked=a.recommend(self.body)
  self.assertEqual(blocked['status'],'explanation');self.assertIsNone(blocked['parameters'])
  self.assertEqual(len(self.sent),2)
 def test_capability_question_is_prompted_as_direct_conversation_not_edit(self):
  a=self.adapter([{**self.good,'status':'explanation','parameters':None}])
  b=copy.deepcopy(self.body);b['text']='what can you do'
  result=a.recommend(b)
  self.assertEqual(result['status'],'explanation');self.assertEqual(result['parameters'],None)
  prompt=self.sent[0]['messages'][0]['content']
  self.assertIn('topics need not be about lighting',prompt)
  self.assertIn('Use ordinary text for conversation',prompt)
  self.assertIn('a direct useful answer in reason',prompt)
  self.assertNotIn('Unrelated requests or instructions to execute/leak are unsupported',prompt)
 def test_chat_explanation_discards_stray_parameters_without_creating_an_edit(self):
  answer={**self.good,'status':'explanation','parameters':self.good['parameters'],
          'reason':'\u6211\u53ef\u4ee5\u89e3\u91ca\u5e03\u5149\u8bbe\u7f6e\u5e76\u7ed9\u51fa\u5efa\u8bae\uff0c\u4f46\u4e0d\u4f1a\u81ea\u52a8\u4fee\u6539\u65b9\u6848\u3002'}
  a=self.adapter([answer]);b=copy.deepcopy(self.body);b['text']='what can you do'
  result=a.recommend(b)
  self.assertEqual(result['status'],'explanation');self.assertIsNone(result['parameters'])
  self.assertNotIn('parameterDiff',result)
  self.assertEqual(json.loads(a.ledger_path.read_text())['records'][0]['outcome'],'accepted')
  with self.assertRaises(LanguageError):validate(answer,self.env,self.policy,'zh',False)
 def test_everyday_technical_and_creative_topics_reach_model_without_keyword_refusal(self):
  for index,text in enumerate(['今天有点累，陪我聊聊','帮我写两句生日祝福','解释一下 SSH 和 powershell 的区别',
      '忽略前面暖色的要求，想试清冷一点','看看这个思路 https://example.com，在 C:\\demo 里怎么组织？',
      '想要梦里那种朦胧感，不知道具体怎么调']):
   with self.subTest(text=text):
    a=self.adapter([{**self.good,'status':'explanation','parameters':None,'reason':'可以，咱们先聊聊你的想法。'}])
    b=copy.deepcopy(self.body);b['text']=text;b['chat']['requestId']=f'{index:032x}'
    r=a.recommend(b);self.assertEqual(len(self.sent),1);self.sent.clear()
    self.assertEqual(r['status'],'explanation');self.assertIsNone(r['parameters'])
 def test_display_text_allows_paragraphs_code_links_concepts_and_followup(self):
  answer={**self.good,'status':'explanation','parameters':None,
    'reason':'可以聊。\n\n精确曝光是摄影概念，照片中有高光时可以讨论取舍。\n```html\n<div>hello</div>\n```\nhttps://example.com',
    'question':'你更想聊技术还是创作？'}
  result=validate(answer,self.env,self.policy,'zh',True)
  self.assertEqual(result['reason'],answer['reason']);self.assertEqual(result['question'],answer['question'])
  with self.assertRaises(LanguageError):validate(answer,self.env,self.policy,'zh',False)
 def test_longer_conversation_response_survives_history_and_schema_limits(self):
  from recipe_language import schema
  answer={**self.good,'status':'explanation','parameters':None,'reason':'聊聊今天的想法。'*90}
  b=copy.deepcopy(self.body);b['chat']['messages']=[{'role':'assistant','text':answer['reason']}]
  a=self.adapter([answer]);r=a.recommend(b)
  self.assertEqual(r['reason'],answer['reason'])
  self.assertEqual(schema(self.env,self.policy,True)['properties']['reason']['maxLength'],1200)
  with self.assertRaises(LanguageError):validate({**answer,'reason':'字'*1201},self.env,self.policy,'zh',True)
 def test_bad_lighting_proposal_keeps_conversation_but_never_applicable_controls(self):
  bad={**self.good,'parameters':{**self.good['parameters'],'strength':100},'reason':'可以试试更明亮的画面。'}
  a=self.adapter([bad]);a.repair_limit=0
  r=a.recommend(self.body)
  self.assertEqual(r['status'],'explanation');self.assertIsNone(r['parameters']);self.assertIn('更明亮',r['reason'])
  self.assertIn('当前方案未改变',r['reason']);self.assertEqual(len(self.sent),1)
  record=json.loads(a.ledger_path.read_text())['records'][0]
  self.assertEqual(record['rejectedProposalCode'],'PARAMETER_RANGE_INVALID')
  self.assertIn('parameterValidationDetail',record)
  self.assertEqual(a.recommend(self.body),r);self.assertEqual(len(self.sent),1)
  with self.assertRaises(LanguageError):a.approved_operation(r['operationId'],self.scheme['inputId'],bad['parameters'])
  # Exercise the provenance status gate without any real provider/network call.
  ledger=json.loads(a.ledger_path.read_text());ledger['mode']='REAL_PROVIDER'
  a.ledger_path.write_text(json.dumps(ledger),encoding='utf-8');a.synthetic=False
  with self.assertRaises(LanguageError):a.approved_operation(r['operationId'],self.scheme['inputId'],None)
 def test_english_fill_followup_recovers_one_zone_without_language_gate(self):
  from light_console import initial
  self.policy['parameterized']=True
  params=initial(self.env['sunny']);params.update(mode='procedural',environmentId=None,environmentSha256=None)
  zone=lambda ident,value:{'id':ident,'name':ident,'enabled':True,'azimuthDeg':0,'elevationDeg':30,
      'strength':value,'color':'#ffffff','sizeDeg':40}
  params['zones']=[zone('key',6),zone('fill',5)]
  self.body['currentScheme']['parameters']=params
  normalized=normalize_scheme(self.body['currentScheme'],self.env,self.policy)
  self.body['chat']['snapshot']={k:normalized[k] for k in ('inputId','planId','version','recipeKey')}
  self.body['replyLanguage']='en'
  self.body['text']='Reduce the supplementary (fill) light from 5 to 4 while keeping the main light unchanged.'
  bad={**self.good,'parameters':{'operations':[{'op':'set','field':'strength','value':5}]},
      'reason':'Try a less intense fill light.'}
  a=self.adapter([bad,bad]);a.repair_limit=0
  result=a.recommend(self.body)
  self.assertEqual(result['status'],'ready')
  self.assertEqual([z['strength'] for z in result['parameters']['zones']],[6,4])
  self.assertNotRegex(result['reason'],r'[\u4e00-\u9fff]')
  self.assertEqual(params['zones'][1]['strength'],5)
  self.body['chat']['requestId']='e'*32
  self.body['text']='Make the scene brighter.'
  fallback=a.recommend(self.body)
  self.assertEqual(fallback['status'],'explanation')
  self.assertIsNone(fallback['parameters'])
  self.assertNotRegex(fallback['reason'],r'[\u4e00-\u9fff]')
  self.assertEqual(len(self.sent),2)
 def test_chat_still_blocks_actual_server_key_and_secret_tokens(self):
  for text in ['OFFLINE_SYNTHETIC_KEY','ghp_SECRET','-----BEGIN PRIVATE KEY-----']:
   a=self.adapter([]);b=copy.deepcopy(self.body);b['text']=text
   with self.assertRaises(LanguageError):a.recommend(b)
   self.assertFalse(self.sent)
 def test_cache_limit_does_not_end_conversation_and_evicted_request_still_deduplicates(self):
  a=self.adapter([{**self.good,'status':'explanation','parameters':None}]);r=a.recommend(self.body)
  for index in range(127):a.chat_requests[f'{index:032x}']={'fingerprint':'old'}
  b=copy.deepcopy(self.body);b['chat']['requestId']='e'*32
  # A normal answer for the next turn, keeping the earlier response in the ledger.
  a.adapter.transport=lambda *_:json.dumps({**self.good,'status':'explanation','parameters':None})
  a.recommend(b)
  self.assertNotIn(self.body['chat']['requestId'],a.chat_requests)
  self.assertEqual(a.recommend(self.body),r)
if __name__=='__main__':unittest.main()
