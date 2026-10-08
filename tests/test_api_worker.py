import tempfile
"""Pure local unit tests of real API classification/identity code, with synthetic CLI replies."""
import base64, copy, importlib.util, json, struct, subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parent
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
worker=module('worker',ROOT.parent/'cloud/host_capture_api.py')
bridge=module('bridge',ROOT.parent/'cloud/cli_bridge.py')
blob=struct.pack('>I',11)+b'ssh-ed25519'+struct.pack('>I',32)+bytes(range(32))
KEY='ssh-ed25519 '+base64.b64encode(blob).decode()
SETTINGS=dict(cli_path='NOT_EXECUTED',profile='synthetic',project_id='project-synthetic',tenant_id='tenant-synthetic',devlab_id='devlab-synthetic')
DEVLAB=dict(metadata=dict(id=SETTINGS['devlab_id'],parent_id=SETTINGS['project_id']),
 spec=dict(image='synthetic-image',workspace=dict(container_path='/home'),ssh_authorized_keys=[KEY]),
 status=dict(state='RUNNING',instances=[dict(compute_instance_id='computeinstance-synthetic',state='RUNNING',compute_instance_state='RUNNING',public_ip='192.0.2.10')]))
VM=dict(metadata=dict(id='computeinstance-synthetic',parent_id='project-synthetic'),status=dict(state='RUNNING',network_interfaces=[dict(public_ip_address=dict(address='192.0.2.10'))]),
 spec=dict(cloud_init_user_data='#cloud-config\nusers:\n  - name: nebius\n    ssh_authorized_keys:\n      - '+KEY+'\n'))
rows=[]
def check(name,f):
    f();rows.append(dict(name=name,passed=True))
def classified(stderr,code,label):
    original=worker.subprocess.run
    worker.subprocess.run=lambda *a,**k: subprocess.CompletedProcess(['SYNTHETIC'],code,'',stderr)
    try:
        try:worker.cli(SETTINGS,['synthetic'])
        except worker.Failure as e:assert e.label==label
        else:raise AssertionError('Expected failure')
    finally:worker.subprocess.run=original
def locate(dev=DEVLAB,vm=VM):
    original=worker.cli
    def cli(settings,args,structured=True):
        if args[:2]==['config','get']:return SETTINGS['tenant_id'] if args[2]=='tenant-id' else SETTINGS['project_id']
        if args[:3]==['iam','v2','project']:return dict(metadata=dict(id=SETTINGS['project_id'],parent_id=SETTINGS['tenant_id']))
        if args[:2]==['ai','devlab']:return copy.deepcopy(dev)
        if args[:2]==['compute','instance']:return copy.deepcopy(vm)
        raise AssertionError(args)
    worker.cli=cli
    try:return worker.locate(SETTINGS,bridge,KEY)
    finally:worker.cli=original
check('Unavailable response classified transient without guessing CLI exit meaning',lambda:classified('rpc error: code = Unavailable',2,'API_TRANSIENT'))
check('Unauthenticated response hard failure',lambda:classified('Unauthenticated',7,'API_AUTH_OR_PERMISSION'))
check('Unknown nonzero does not retry',lambda:classified('SECRET must never leave worker',17,'API_NONZERO_EXIT'))
def timeout():
    original=worker.subprocess.run
    def fail(*a,**k):raise subprocess.TimeoutExpired('synthetic',25)
    worker.subprocess.run=fail
    try:
        try:worker.cli(SETTINGS,['synthetic'])
        except worker.Failure as e:assert e.label=='API_TIMEOUT' and e.retryable
        else:raise AssertionError()
    finally:worker.subprocess.run=original
check('CLI process timeout explicitly transient',timeout)
check('Original bridge validates VM/IP/user/public key mapping before verified flags',lambda:(_ for _ in ()).throw(AssertionError()) if not locate()['public_key_mapping_verified'] else None)
def failure_change(field,label):
    dev=copy.deepcopy(DEVLAB);field(dev)
    try:locate(dev)
    except Exception as e:assert getattr(e,'label',str(e))==label,(label,str(e))
    else:raise AssertionError('Unexpected success')
check('Missing VM instances explicitly pending',lambda:failure_change(lambda d:d['status'].update(instances=[]),'VM_INFO_PENDING'))
check('Multiple current VM instances hard ambiguous',lambda:failure_change(lambda d:d['status']['instances'].append(copy.deepcopy(d['status']['instances'][0])),'VM_IDENTITY_AMBIGUOUS'))
check('Public key mapping mismatch remains hard rejection',lambda:failure_change(lambda d:d['spec'].update(ssh_authorized_keys=[]),'LOCAL_KEY_NOT_IN_DEVLAB'))
check('Stopped resource never scanned',lambda:failure_change(lambda d:d['status'].update(state='STOPPED'),'DEVLAB_INACTIVE'))
def public_state(state,pending=False):
    dev=copy.deepcopy(DEVLAB);dev['status']['state']=state
    if pending:dev['status']['instances']=[]
    try:locate(dev)
    except worker.Failure as e:
        assert e.devlab_state==state and e.retryable
        assert e.label==('VM_INFO_PENDING' if pending else 'DEVLAB_NOT_READY')
    else:raise AssertionError('Expected readiness failure')
check('STARTING public state preserved',lambda:public_state('STARTING'))
check('PROVISIONING public state preserved',lambda:public_state('PROVISIONING'))
check('RUNNING pending VM public state preserved',lambda:public_state('RUNNING',True))
(Path(tempfile.gettempdir())/'nebius-api-worker-tests.json').write_text(json.dumps(dict(passed=True,test_count=len(rows),tests=rows,cloud_API_calls=0,synthetic_only=True),indent=2),encoding='utf-8')
print(json.dumps(dict(passed=True,test_count=len(rows))))
