"""Bounded Linux Nebius Devlab adapter. Construction performs NO CLI/cloud calls."""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import time

from security import runtime_file
from inference.jobs import ID

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'cloud'))
import cli_bridge as reviewed_bridge
if Path(reviewed_bridge.__file__).resolve()!=ROOT/'cloud/cli_bridge.py':
    raise ValueError('REVIEWED_NEBIUS_BRIDGE_IDENTITY_REQUIRED')
from cli_bridge import devlab_summary,validate_project_owner,canonical_key,connection_target


def build(binding):return NebiusProvider(binding)


class NebiusProvider:
    simulation=False

    def __init__(self,binding):
        required={'cliPath','configFile','profile','tenantId','projectId','resourceId','publicKeyFile','guardRoot'}
        if not isinstance(binding,dict) or set(binding)!=required:
            raise ValueError('EXPLICIT_NEBIUS_BINDING_REQUIRED')
        self.settings=dict(binding)
        for field in ('profile','tenantId','projectId','resourceId'):
            if not isinstance(binding[field],str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',binding[field]):
                raise ValueError('NEBIUS_IDENTITY_INVALID')
        self.cli=Path(binding['cliPath']);self.root=Path(binding['guardRoot'])
        if (not self.cli.is_absolute() or not self.cli.is_file() or self.cli.is_symlink() or
                not self.root.is_absolute() or self.root.resolve().is_relative_to(ROOT) or
                any(p.is_symlink() for p in (self.root,*self.root.parents))):
            raise ValueError('EXPLICIT_CLI_AND_PRIVATE_GUARD_ROOT_REQUIRED')
        runtime_file(binding['configFile'],ROOT)
        self.public_key=canonical_key(runtime_file(binding['publicKeyFile'],ROOT,16384).decode())
        self.clock=time.time
        self.runner=subprocess.run

    def _call(self,args,*,json_result=True,deadline=None):
        timeout=6.0 if deadline is None else min(6.0,deadline-self.clock())
        if timeout<=0:raise RuntimeError('NEBIUS_DEADLINE_EXPIRED')
        cmd=[str(self.cli),*args,'--config',self.settings['configFile'],'--profile',self.settings['profile'],
             '--no-browser','--no-check-update','--no-progress','--color=false','--auth-timeout=2s',
             '--timeout=5s','--per-retry-timeout=5s','--retries=1']
        if json_result:cmd+=['--format','json']
        try:
            p=self.runner(cmd,stdin=subprocess.DEVNULL,capture_output=True,text=True,
                          timeout=timeout,shell=False,encoding='utf-8')
            if p.returncode:
                raise RuntimeError('NEBIUS_AUTH_REQUIRED' if p.returncode==7 else 'NEBIUS_COMMAND_FAILED')
            if len(p.stdout)>1024*1024:raise RuntimeError('NEBIUS_RESPONSE_TOO_LARGE')
            return json.loads(p.stdout) if json_result else None
        except RuntimeError:raise
        except Exception:raise RuntimeError('NEBIUS_RESPONSE_UNCERTAIN') from None

    def _read(self,resource,deadline):
        if resource!=self.settings['resourceId']:raise ValueError('NEBIUS_RESOURCE_MISMATCH')
        s={'devlab_id':resource,'project_id':self.settings['projectId'],'tenant_id':self.settings['tenantId']}
        project=self._call(['iam','v2','project','get','--id',s['project_id']],deadline=deadline)
        validate_project_owner(project,s)
        raw=self._call(['ai','devlab','get','--id',resource],deadline=deadline)
        if not isinstance(raw.get('status',{}).get('instances'),list):
            raise ValueError('NEBIUS_INSTANCES_PROOF_REQUIRED')
        summary=devlab_summary(raw,s)
        if self.public_key not in [canonical_key(k) for k in raw.get('spec',{}).get('ssh_authorized_keys',[])]:
            raise ValueError('NEBIUS_AUTHORIZED_PUBLIC_KEY_MISMATCH')
        return s,raw,summary

    def observe(self,resource):
        deadline=self.clock()+20
        s,raw,summary=self._read(resource,deadline)
        state=summary['state']
        mapped={'STOPPED':'STOPPED','STOPPING':'STOPPING','RUNNING':'RUNNING',
                'PROVISIONING':'STARTING','STARTING':'STARTING','IMAGE_PULLING':'STARTING'}
        if state not in mapped:raise RuntimeError('NEBIUS_RESOURCE_ABNORMAL')
        result={'resourceId':resource,'independent':True,'state':mapped[state],
                'instances':summary['instances'],'simulation':False}
        # Missing/null instances never counts as release proof (legacy summary defaults []).
        if not isinstance(raw.get('status',{}).get('instances'),list):
            raise ValueError('NEBIUS_INSTANCES_PROOF_REQUIRED')
        if state=='RUNNING':
            active=[x for x in summary['instances'] if x.get('state')=='RUNNING']
            if len(active)!=1:raise ValueError('NEBIUS_CURRENT_VM_NOT_UNIQUE')
            if not re.fullmatch(r'computeinstance-[a-z0-9]+',active[0]['compute_instance_id']):
                raise ValueError('NEBIUS_CURRENT_VM_ID_INVALID')
            vm=self._call(['compute','instance','get','--id',active[0]['compute_instance_id']],deadline=deadline)
            target=connection_target(raw,vm,self.public_key,s)
            fresh=devlab_summary(self._call(['ai','devlab','get','--id',resource],deadline=deadline),s)
            if fresh['state']!=summary['state'] or fresh['instances']!=summary['instances']:
                raise ValueError('NEBIUS_VM_CHANGED_DURING_OBSERVATION')
            result['hostIdentity']={'resourceId':resource,'vmId':target['vm_id'],'ip':target['ip'],
                'sshUser':target['ssh_user'],'authorizedKeySha256':hashlib.sha256(self.public_key.encode()).hexdigest()}
        return result

    def preflight(self,resource):return self.observe(resource)

    def _mutate(self,resource,sid,kind,deadline=None):
        if resource!=self.settings['resourceId'] or not isinstance(sid,str) or not ID.fullmatch(sid):
            raise ValueError('NEBIUS_SESSION_BINDING_REQUIRED')
        path=self.root/'sessions.sqlite3'
        if not path.is_file() or path.is_symlink():raise ValueError('DURABLE_SESSION_REQUIRED')
        db=sqlite3.connect('file:'+path.as_posix()+'?mode=rw',uri=True,timeout=5)
        try:
            row=db.execute('SELECT body FROM sessions WHERE id=?',(sid,)).fetchone()
            value=json.loads(row[0]) if row else {}
            if value.get('resourceId')!=resource or value.get('startSent' if kind=='restart' else 'stopSent') is not True:
                raise ValueError('NEBIUS_SESSION_ATTEMPT_LATCH_REQUIRED')
            if kind=='restart' and (type(deadline) not in (float,int) or not math.isfinite(deadline) or
                    deadline!=value.get('absoluteDeadline') or self.clock()>=min(deadline,value['startupDeadline'])):
                raise ValueError('NEBIUS_CURRENT_START_WINDOW_REQUIRED')
            db.execute('CREATE TABLE IF NOT EXISTS provider_attempts(session TEXT,kind TEXT,PRIMARY KEY(session,kind))')
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM provider_attempts WHERE session=? AND kind=?',(sid,kind)).fetchone():return
            # Commit BEFORE the command. Lost ACK is never permission to repeat.
            db.execute('INSERT INTO provider_attempts VALUES (?,?)',(sid,kind));db.commit()
            bound=min(deadline,value['startupDeadline'],self.clock()+20) if kind=='restart' else self.clock()+20
            _,_,summary=self._read(resource,bound)
            if kind=='restart' and (summary['state']!='STOPPED' or summary['instances']!=[]):
                raise ValueError('NEBIUS_START_REQUIRES_STOPPED_EMPTY')
            self._call(['ai','devlab',kind,'--id',resource,'--async'],json_result=False,deadline=bound)
        finally:db.close()

    def start(self,resource,sid,deadline):self._mutate(resource,sid,'restart',deadline)
    def stop(self,resource,sid):self._mutate(resource,sid,'stop')
