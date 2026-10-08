"""Offline regression runner. No cloud initialization or component installation."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=ROOT/'.local/selftest.json');a=p.parse_args()
    commands=[['-m','unittest','discover','-s','prototype','-v'],
              ['-m','unittest','discover','-s','tests','-p','test_preparation.py','-v'],
              ['-m','unittest','discover','-s','tests','-p','test_portability.py','-v']]
    commands.extend([['-m','unittest','discover','-s','tests','-p',pattern,'-v']
                     for pattern in ('test_cli_read_retry.py','test_utc_precision.py','test_native_failure_metadata.py')])
    for name in ('test_api_worker.py','test_budget.py','test_host_capture.py','test_output_complete.py','test_running_guard.py','test_absolute_deadline.py'):
        commands.append(['tests/'+name])
    rows=[]
    for argv in commands:
        before=time.monotonic()
        r=subprocess.run([sys.executable,'-B',*argv],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=240)
        rows.append({'command':argv,'exit_code':r.returncode,'seconds':round(time.monotonic()-before,3)})
        print(json.dumps(rows[-1]),flush=True)
        a.out.parent.mkdir(parents=True,exist_ok=True)
        log=a.out.parent/('test-'+str(len(rows))+'.log');log.write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:break
    report={'offline':True,'cloud_calls':0,'passed':len(rows)==len(commands) and all(r['exit_code']==0 for r in rows),'groups':rows,'optional_gpu_and_external_upstream_checks':'see explicit unittest skips'}
    a.out.write_text(json.dumps(report,indent=2));return 0 if report['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
