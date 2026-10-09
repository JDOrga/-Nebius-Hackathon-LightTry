"""Only actual worker events; missing events never mean success."""
import base64
import json
from pathlib import Path
import sys


def main(q):
    prep = Path(q['prep']).resolve()
    if not prep.is_relative_to('/home/jovyan'):
        raise ValueError('PERSISTENT_PREPARATION_REQUIRED')
    path = prep / 'run/execution.json'
    print(path.read_text() if path.is_file() else json.dumps({'status': 'queued'}))


if __name__ == '__main__':
    main(json.loads(base64.b64decode(sys.argv[1])))
