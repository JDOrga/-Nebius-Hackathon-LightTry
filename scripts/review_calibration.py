"""Offline review/report only. Never start cloud/GPU/model calls."""
import argparse
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'project'))
from next.runtime.calibration import finalize
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--package',type=Path,required=True);p.add_argument('--review',type=Path);o=p.parse_args()
    v=finalize(o.package.resolve(),o.review);print(v['execution'],v['visual'],v['direction'],v['width'],v['workbench'])
