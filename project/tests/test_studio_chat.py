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
