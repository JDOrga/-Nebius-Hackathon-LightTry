"""Explicit isolated multi-turn transport. NOT Nemotron, never GPU or upload."""
import argparse,json,sys,time
from pathlib import Path
from http.server import ThreadingHTTPServer
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import shared_http as legacy
from studio import Handler
from scheme_store import SchemeStore
from evidence import load_evidence
from recipe_language import RecipeLanguage
from language import LanguageError
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--assets-dir',required=True);p.add_argument('--evidence-config',type=Path);p.add_argument('--tasks-dir',type=Path,required=True);p.add_argument('--port',type=int,default=8898);a=p.parse_args();a.tasks_dir.mkdir(parents=True,exist_ok=True)
 def wire(payload,timeout):
  ctx=json.loads(payload['messages'][1]['content'])
  with (a.tasks_dir/'received-context.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(ctx,ensure_ascii=False)+'\n')
  text=ctx['request'];params={k:ctx['selectedScheme']['parameters'][k] for k in ('environmentId','offsetDeg','strength')};status='ready';reason='隔离传输替身：提出允许档位的备选，效果仍需另行生成。';question=''
  if '超时' in text:raise LanguageError('LANGUAGE_TIMEOUT','隔离 transport 超时；未调用模型，不自动重试。')
  if '延迟' in text:time.sleep(4)
  if '为什么' in text:
   status='explanation';reason='隔离传输替身：最近会话有'+str(len(ctx.get('boundedConversation',{}).get('messages',[])))+'条对话；未应用建议不改变当前配置。';params=None
  elif '随便' in text:status='clarification';params=None;reason='';question='希望保留环境还是换一个环境？'
  elif '色温' in text:status='unsupported';params=None;reason='当前不提供色温控制；只能使用已有环境和档位。'
  elif '危险' in text:reason='<img src=x onerror=alert(1)>'
  elif '无效' in text:params['strength']=1.4
  elif '无变化' in text:pass
  elif '方向' in text:params={'environmentId':'sunny','offsetDeg':45,'strength':1}
  else:params={'environmentId':'sunny','offsetDeg':0,'strength':.7}
  return json.dumps({'status':status,'action':'revise','parameters':params,'name':'','reason':reason,'question':question},ensure_ascii=False)
 Handler.assets_dir=legacy.resolve_assets_dir(a.assets_dir);Handler.catalog=legacy.load_catalog(Handler.assets_dir);Handler.lighting_capabilities,Handler.studies,Handler.study_files=load_evidence(a.evidence_config)
 Handler.recipe_language=RecipeLanguage(Handler.catalog['presets'],Handler.lighting_capabilities,'OFFLINE_SYNTHETIC_KEY',a.tasks_dir/'fixture-ledger.json',transport=wire,max_calls=12,budget=.20)
 Handler.task_store=SchemeStore(a.tasks_dir/'tasks',Handler.catalog['presets'],None,lighting_capabilities=Handler.lighting_capabilities)
 print('ISOLATED TEST TRANSPORT, NOT NEMOTRON/GPU http://127.0.0.1:'+str(a.port),flush=True)
 with ThreadingHTTPServer(('127.0.0.1',a.port),Handler) as http:
  try:http.serve_forever()
  finally:Handler.task_store.close()
