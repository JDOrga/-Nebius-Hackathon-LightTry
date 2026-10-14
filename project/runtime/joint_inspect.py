import base64,json
from pathlib import Path
import sys

def main(q):
    prep=Path(q['prep']).resolve()
    if not prep.is_relative_to('/home/jovyan'):raise ValueError('PERSISTENT_PREPARATION_REQUIRED')
    plan=json.loads((prep/'joint.json').read_text())
    path=prep/'run/execution.json'
    event=json.loads(path.read_text()) if path.is_file() else {'status':'queued'}
    event.setdefault('taskId',plan['taskId']);event.setdefault('nonce',plan['nonce']);event['completed']=[]
    for case in plan['cases']:
        marker=prep/'run/cases'/case['id']/'0/complete.json'
        if marker.is_file() and not marker.is_symlink():event['completed'].append(case['id'])
    print(json.dumps(event))
if __name__=='__main__':main(json.loads(base64.b64decode(sys.argv[1])))
