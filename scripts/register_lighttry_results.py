"""Register downloaded real executor results locally; never starts inference."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'project'))
from inference.jobs import TaskStore, read

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--job',required=True,help='relative directory inside workspace/.local')
    p.add_argument('--run',required=True)
    p.add_argument('--original-task',required=True)
    args=p.parse_args()
    store=TaskStore(ROOT/'project/.tasks',read(ROOT/'project/data/catalog.json')['presets'])
    try:
        print(json.dumps(store.register_execution(args.job,args.run,args.original_task),ensure_ascii=False,indent=2))
    finally: store.close()
