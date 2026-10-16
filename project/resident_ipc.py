"""Private, deadline-bounded single-attempt IPC; never accepts browser code."""
import hashlib
import json
from pathlib import Path
import time
import uuid

from inference.jobs import atomic,read


def safe(path,root):
    path=Path(path)
    if (not path.is_absolute() or not path.resolve().is_relative_to(Path(root).resolve()) or
            any(x.is_symlink() for x in (path,*path.parents))):
        raise ValueError('RESIDENT_PATH_UNSAFE')
    return path


def phase_command(command,prep):
    """Only the two installed, hash-identical phase entries are delegatable."""
    if not isinstance(command,list) or len(command)<5 or not all(isinstance(x,str) for x in command):
        return None
    if '--phase' not in command:return None
    index=command.index('--phase')
    if index+1>=len(command):raise ValueError('RESIDENT_PHASE_INVALID')
    phase=command[index+1]
    expected={'inverse':'project/inference/measured_entry.py','forward':'project/runtime/entry.py'}
    if phase not in expected:raise ValueError('RESIDENT_PHASE_INVALID')
    path=safe(command[2],prep)
    if path!=Path(prep)/expected[phase] or command[1]!='-B':
        raise ValueError('RESIDENT_ENTRY_INVALID')
    return phase


def call(root,phase,command,logfile,prep,deadline,*,clock=time.time,sleep=time.sleep):
    root=Path(root);prep=Path(prep)
    if phase_command(command,prep)!=phase:raise ValueError('RESIDENT_PHASE_INVALID')
    if clock()>=deadline:raise TimeoutError('RESIDENT_DEADLINE')
    status=read(root/phase/'state.json')
    if status.get('state')!='ready' or status.get('modelLoaded') is not True:
        raise OSError('RESIDENT_NOT_READY')
    identity=uuid.uuid4().hex
    requests=safe(root/phase/'requests',root);requests.mkdir(exist_ok=True,mode=0o700)
    body={'id':identity,'prep':str(prep),'argv':command,'logfile':str(safe(logfile,prep/'run')),
          'deadline':deadline,'bootId':status['bootId']}
    # Each original worker phase is dispatched once; never resubmit after timeout.
    atomic(requests/(identity+'.json'),body)
    result=root/phase/'responses'/(identity+'.json')
    while clock()<deadline:
        if result.exists():
            value=read(result)
            if value.get('id')!=identity or value.get('bootId')!=status['bootId']:
                raise OSError('RESIDENT_RESPONSE_MISMATCH')
            if value.get('exitCode')!=0:raise OSError('RESIDENT_EXECUTION_UNCERTAIN')
            return value
        latest=read(root/phase/'state.json')
        if latest.get('bootId')!=status['bootId'] or latest.get('state')=='failed':
            raise OSError('RESIDENT_PROCESS_UNCERTAIN')
        sleep(.1)
    raise TimeoutError('RESIDENT_PHASE_DEADLINE')
