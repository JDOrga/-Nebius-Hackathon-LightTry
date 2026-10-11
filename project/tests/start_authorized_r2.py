"""Run in WJX's original private-key PowerShell; never prints/changes the key.

Only this child process receives the explicit frozen non-secret configuration.
The original shell's environment and product source files are not rewritten.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
REPO=ROOT.parent


if __name__=='__main__':
    if sys.argv[1:]:
        print('No arguments accepted. This is the already-authorized R2 run only.')
        raise SystemExit(2)
    if not os.environ.get('LIGHTTRY_TOKEN_FACTORY_KEY','').strip():
        print('LANGUAGE_NOT_CONFIGURED: run in the original privately configured PowerShell; never paste the key into chat.')
        raise SystemExit(2)
    manifest=json.loads((ROOT/'docs/LANGUAGE_CANDIDATE_20261011_R2.json').read_text(encoding='utf-8'))
    cfg=manifest['config']
    for name,value in {
        'LIGHTTRY_LANGUAGE_ENABLED':'1','LIGHTTRY_LANGUAGE_MODEL':cfg['model'],
        'LIGHTTRY_LANGUAGE_ENDPOINT':cfg['endpoint'],'LIGHTTRY_LANGUAGE_MAX_TOKENS':str(cfg['maxTokens']),
        'LIGHTTRY_LANGUAGE_THINKING':cfg['thinking'],'LIGHTTRY_LANGUAGE_TOOL_CHOICE':cfg['toolChoice'],
        'LIGHTTRY_LANGUAGE_OUTPUT_MODE':cfg['outputMode'],'LIGHTTRY_LANGUAGE_TIMEOUT':str(cfg['timeoutSeconds']),
        'LIGHTTRY_LANGUAGE_REPAIRS':str(cfg['maxRepairs']),
        'LIGHTTRY_LANGUAGE_OPERATION_BUDGET_USD':str(cfg['operationBudgetUSD'])}.items():
        os.environ[name]=value
    runner=ROOT/'tests/authorized_candidate_run.py'
    command=[sys.executable,'-X','utf8','-B',str(runner)]
    print('R2 only: Nemotron Lightning / thinking on / 40960 / auto / shared 60s / 1 repair.',flush=True)
    checked=subprocess.run(command+['--check'],cwd=REPO)
    if checked.returncode:
        raise SystemExit(checked.returncode)
    raise SystemExit(subprocess.run(command+['--execute'],cwd=REPO).returncode)
