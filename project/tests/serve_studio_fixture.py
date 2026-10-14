"""Isolated studio UI language fixture. NEVER model/GPU; production frontend unchanged."""
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

def wire(payload,timeout):
    ctx=json.loads(payload['messages'][1]['content']);text=ctx['request'];p={k:ctx['selectedScheme']['parameters'][k] for k in ('environmentId','offsetDeg','strength')}
    if text=='超时':raise LanguageError('LANGUAGE_TIMEOUT','隔离替身模拟超时；未调用模型。')
    if text=='延迟':time.sleep(3)
    if text=='无效':p['strength']=1.4
    elif text!='无变化':p={'environmentId':'street','offsetDeg':0,'strength':1}
    return json.dumps({'status':'ready','action':'revise','parameters':p,'name':'','reason':'隔离测试建议：比较另一种环境，实际效果仍需生成。','question':''},ensure_ascii=False)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--assets-dir',required=True);parser.add_argument('--evidence-config',type=Path);parser.add_argument('--tasks-dir',type=Path,required=True);parser.add_argument('--port',type=int,default=8897);a=parser.parse_args()
    Handler.assets_dir=legacy.resolve_assets_dir(a.assets_dir);Handler.catalog=legacy.load_catalog(Handler.assets_dir)
    Handler.lighting_capabilities,Handler.studies,Handler.study_files=load_evidence(a.evidence_config)
    Handler.recipe_language=RecipeLanguage(Handler.catalog['presets'],Handler.lighting_capabilities,'OFFLINE_SYNTHETIC_KEY',a.tasks_dir/'fixture-ledger.json',transport=wire,max_calls=12,budget=.20)
    Handler.task_store=SchemeStore(a.tasks_dir/'tasks',Handler.catalog['presets'],None,lighting_capabilities=Handler.lighting_capabilities)
    print('OFFLINE SYNTHETIC STUDIO; no inference; http://127.0.0.1:'+str(a.port),flush=True)
    with ThreadingHTTPServer(('127.0.0.1',a.port),Handler) as http:
        try:http.serve_forever()
        finally:Handler.task_store.close()


