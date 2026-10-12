"""Canonical local LightTry launch. Existing next.server only; no credentials/inference."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
PROJECT=ROOT/'project'
sys.path.insert(0,str(PROJECT))
if __name__=='__main__':
    try: __import__('numpy')
    except ImportError:
        import os
        runtime=ROOT/'.local/lighttry-development-20261011/cpu-venv/Scripts/python.exe'
        if runtime.is_file() and Path(sys.executable).resolve()!=runtime.resolve():
            os.execv(str(runtime),[str(runtime),'-X','utf8','-B',str(Path(__file__).resolve()),*sys.argv[1:]])
        raise SystemExit('Existing NumPy runtime required; no dependencies installed. Use the existing CPU venv.')
from next.server import main
if __name__=='__main__':
    assets=ROOT/'.local/demo-candidate-20261010/demo-assets'
    evidence=ROOT/'.local/lighttry-development-20261011/workbench-evidence.local.json'
    args=['--assets-dir',str(assets if assets.is_dir() else PROJECT/'demo-assets'),'--tasks-dir',str(ROOT/'.local/lighttry-development-20261011/workbench-tasks')]
    if evidence.is_file():args+=['--evidence-config',str(evidence)]
    accepted=ROOT/'.local/lighttry-joint-20261012/ai-confirmed-package'
    if accepted.is_dir():args+=['--accepted-package',str(accepted)]
    sys.argv=[sys.argv[0],*args,*sys.argv[1:]]
    main()
