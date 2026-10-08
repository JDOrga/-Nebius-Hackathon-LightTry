"""Launch the bounded Cosmos worker in an existing environment; no VM lifecycle."""
import base64
from datetime import datetime,timezone
import json
from pathlib import Path
import subprocess
import sys

def main(q):
    prep=Path(q['prep']).resolve()
    if not prep.is_relative_to('/home/jovyan'):raise ValueError('PERSISTENT_PREPARATION_REQUIRED')
    sys.path.insert(0,str(prep/'scripts'))
    from weights import parse_utc
    deadline=parse_utc(q['deadline_utc'])
    if deadline.utcoffset().total_seconds()!=0 or deadline<=datetime.now(timezone.utc):raise ValueError('FIXED_UTC_DEADLINE_REQUIRED')
    if not q.get('license_ack'):raise ValueError('MODEL_LICENSE_ACK_REQUIRED')
    receipt=q['guard_launch_receipt']
    if receipt.get('offline') or not receipt.get('single_run') or receipt.get('budget_usd_including_tax',0)<=0 or not receipt.get('approval_reference') or deadline>parse_utc(receipt['deadline_utc']):
        raise ValueError('CURRENT_GUARDED_BUDGET_RECEIPT_REQUIRED')
    prep=Path(q['prep']).resolve();run=Path(q['run_dir']).resolve()
    if not prep.is_relative_to('/home/jovyan') or not run.is_relative_to('/home/jovyan') or run.exists():raise ValueError('NEW_PERSISTENT_RUN_REQUIRED')
    marker=prep/'preview-launch.json'
    with marker.open('x') as f:json.dump({'deadline_utc':q['deadline_utc'],'run_dir':str(run),'restart_allowed':False},f)
    receipt_path=prep/'guard-launch-receipt.json'
    with receipt_path.open('x') as f:json.dump(receipt,f)
    argv=[sys.executable,'-u','-B',str(prep/'scripts/run_experiment.py'),'--repo',q['repo'],
          '--checkpoint-dir',q['checkpoint_dir'],'--run-dir',str(run),'--input-dir',q['input_dir'],
          '--input-image',q['input_image'],'--cuda-home',q['cuda_home'],'--deadline-utc',q['deadline_utc'],
          '--license-ack','nvidia-open-model-license','--guard-launch-receipt',str(receipt_path),'--execute']
    with (prep/'preview-worker.log').open('x') as log:
        p=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    print(json.dumps({'worker_pid':p.pid,'deadline_utc':q['deadline_utc'],'run_dir':str(run)}))

if __name__=='__main__':main(json.loads(base64.b64decode(sys.argv[1])))
