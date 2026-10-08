"""Read compact worker status without raw stderr, tensors or full directory dumps."""
import base64
import json
from pathlib import Path
import sys

def main(q):
    root=Path(q['run_dir']).resolve()
    if not root.is_relative_to('/home/jovyan'):raise ValueError('PERSISTENT_RUN_REQUIRED')
    status=root/'status.json'
    if not status.exists():print(json.dumps({'state':'not_ready'}));return
    value=json.loads(status.read_text())
    print(json.dumps({k:value[k] for k in ('state','started_utc','finished_utc') if k in value}))

if __name__=='__main__':main(json.loads(base64.b64decode(sys.argv[1])))
