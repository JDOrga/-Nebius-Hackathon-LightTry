"""HTTP client for an actual container. Password read from private mounted runtime file."""
import base64
import hashlib
import json
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'project/tests'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'project'))
from inference_fixture import image_bytes

def main():
    phase, password_path, state_path = sys.argv[1:]
    password = Path(password_path).read_text().split('password=')[-1].splitlines()[0].strip()
    # Runtime account handoff format may be JSON; never print its contents.
    raw = Path(password_path).read_text()
    try: password = json.loads(raw)['password']
    except (ValueError, KeyError):
        for line in raw.splitlines():
            if line.lower().startswith('password:'): password = line.split(':',1)[1].strip()
    auth = 'Basic ' + base64.b64encode(('lighttry:'+password).encode()).decode()
    token = None
    evidence = []
    def http(path, method='GET', data=None, mime='application/json', extra=None, anonymous=False, expected=200):
        headers = {'Host':'localhost:8080'}
        if not anonymous: headers['Authorization']=auth
        if method != 'GET': headers.update({'Origin':'http://localhost:8080','X-LightTry-Token':token or '', 'Content-Type':mime})
        headers.update(extra or {})
        req=Request('http://127.0.0.1:18080'+path,data=data,method=method,headers=headers)
        try:
            with urlopen(req,timeout=5) as response:
                status, body=response.status,response.read()
                if path.endswith('/download'): assert 'attachment' in response.headers.get('Content-Disposition','')
        except HTTPError as e: status,body=e.code,e.read();e.close()
        assert status==expected,(path,status,expected,body[:100])
        evidence.append({'method':method,'path':path,'status':status,'bytes':len(body)})
        return body
    for _ in range(100):
        try: http('/api/health');break
        except OSError: time.sleep(.2)
    else: raise RuntimeError('CONTAINER_NOT_READY')
    if phase != 'restart': http('/',anonymous=True,expected=401)
    http('/'); assert json.loads(http('/api/me'))['username']=='lighttry'
    http('/workbench.js')
    token=json.loads(http('/api/inference'))['csrfToken']
    payload=image_bytes()
    if phase=='create':
        http('/api/photos/'+'a'*32,'POST',payload,'image/png',{'X-LightTry-Photo':base64.b64encode(json.dumps({'name':'synthetic.png'}).encode()).decode()},expected=201)
        scheme={'schemaVersion':1,'planId':'b'*32,'version':1,'parentVersion':None,'inputId':'a'*32,'name':'容器测试方案','parameters':{'environmentId':'sunny','offsetDeg':0,'strength':1}}
        http('/api/workspace','POST',json.dumps({'schemaVersion':1,'schemes':[scheme]}).encode())
        metadata={'inputId':'a'*32,'requestId':'d'*32,'presetId':'sunny','name':'synthetic'}
        task=json.loads(http('/api/tasks','POST',payload,'image/png',{'X-LightTry-Request':base64.b64encode(json.dumps(metadata).encode()).decode()},expected=202))
        for _ in range(50):
            task=json.loads(http('/api/tasks/'+task['taskId']))
            if task['status']=='succeeded':break
            time.sleep(.2)
        assert task['status']=='succeeded',task
        result=http(task['result']['url'])
        state={'taskId':task['taskId'],'resultUrl':task['result']['url'],'resultSha256':hashlib.sha256(result).hexdigest(),'photoSha256':hashlib.sha256(payload).hexdigest()}
        Path(state_path).write_text(json.dumps(state))
    else: state=json.loads(Path(state_path).read_text())
    assert hashlib.sha256(http('/api/photos/'+'a'*32)).hexdigest()==state['photoSha256']
    if phase != 'restart': http('/api/photos/'+'a'*32,anonymous=True,expected=401)
    assert len(json.loads(http('/api/workspace'))['schemes'])==1
    assert json.loads(http('/api/tasks/'+state['taskId']))['status']=='succeeded'
    assert hashlib.sha256(http(state['resultUrl'])).hexdigest()==state['resultSha256']
    assert hashlib.sha256(http('/api/tasks/'+state['taskId']+'/download')).hexdigest()==state['resultSha256']
    if phase != 'restart': http(state['resultUrl'],anonymous=True,expected=401)
    http('/api/gpu/start',expected=405)
    if phase != 'restart': http('/api/gpu/start','POST',b'{}',anonymous=True,expected=401)
    if phase!='create':http('/api/tasks','POST',payload,'image/png',expected=503)
    print(json.dumps({'phase':phase,'realContainerHTTP':True,'realGPUStarts':0,'fixtureOnly':True,'observations':evidence,'persisted':state},ensure_ascii=False))

if __name__=='__main__': main()
