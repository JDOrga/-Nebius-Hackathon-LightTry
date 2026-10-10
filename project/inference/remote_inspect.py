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
    event = json.loads(path.read_text()) if path.is_file() else {'status': 'queued'}
    event['presets'] = {}
    for index in (0, 1, 2):
        item = prep / 'run/presets' / str(index)
        state = item / 'state.json'
        marker = item / 'complete.json'
        if state.is_file() and not state.is_symlink():
            status = json.loads(state.read_text())
            if marker.is_file() and not marker.is_symlink():
                completed = json.loads(marker.read_text())
                status.update(completedEpoch=completed.get('completedEpoch'), result=completed['result'],
                              source=completed['source'])
            event['presets'][str(index)] = status
    print(json.dumps(event))


if __name__ == '__main__':
    main(json.loads(base64.b64decode(sys.argv[1])))
