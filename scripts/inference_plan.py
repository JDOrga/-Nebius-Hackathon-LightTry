"""Emit the local plan from the machine-local config; no inference or network."""
import argparse
import json
from pathlib import Path
from local_config import load
from run_experiment import commands

def main():
    p=argparse.ArgumentParser();p.add_argument('--run-dir',type=Path,required=True);a=p.parse_args();cfg=load()
    args=argparse.Namespace(checkpoint_dir=Path(cfg['container_checkpoint_dir']),run_dir=a.run_dir,
                            height=704,width=1280,offload=False,input_dir=Path(cfg['container_data_dir'])/'inputs')
    inverse,forward=commands(args)
    # Replace this planner's interpreter with the separately prepared inference interpreter.
    inverse[0]=forward[0]=cfg['container_python']
    print(json.dumps({'mode':'LOCAL_PLAN','cloud_calls':0,'repo':cfg['container_repo'],'inverse_argv':inverse,'forward_argv':forward},indent=2))

if __name__=='__main__':main()
