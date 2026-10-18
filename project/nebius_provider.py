"""Bounded Linux Nebius Devlab adapter. Construction performs NO CLI/cloud calls."""
from contextlib import closing
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

    def _command(self,args,json_result):
        cmd=[str(self.cli),*args,'--config',self.settings['configFile'],'--profile',self.settings['profile'],
             '--no-browser','--no-check-update','--no-progress','--color=false','--auth-timeout=5s',
             '--timeout=5s','--per-retry-timeout=5s','--retries=1']
        if json_result:cmd+=['--format','json']
        return cmd

    def _diagnostic(self, args, started, code, exit_code=None, stderr=''):
        # Never persist raw commands, IDs, paths, stdout, or arbitrary stderr.
        verbs={('iam','v2','project','get'):'project_get',
               ('ai','devlab','get'):'devlab_get',
               ('compute','instance','list'):'instance_list',
               ('compute','instance','get'):'instance_get',
               ('ai','devlab','restart'):'restart',('ai','devlab','stop'):'stop'}
        verb=next((v for k,v in verbs.items() if tuple(args[:len(k)])==k),'other')
        raw=stderr if isinstance(stderr,str) else ''
        sample=raw[:8192].lower()
        categories=[label for label,words in (
            ('authentication',('unauthenticated','authentication failed','invalid token','expired token')),
            ('permission',('permission denied','forbidden')),
            ('timeout',('deadline exceeded','timed out','timeout')),
            ('network',('connection refused','connection reset','no such host','network is unreachable')),
            ('rate_limit',('resource exhausted','too many requests')),
            ('invalid_argument',('invalid argument','unknown flag')))
            if any(word in sample for word in words)]
        receipt={'stage':verb,'code':code,'exitCode':exit_code,
                 'durationMs':max(0,round((time.monotonic()-started)*1000)),
                 'stderrSummary':categories or (['redacted'] if raw else []),
                 'stderrChars':len(raw),'stderrTruncated':len(raw)>8192}
        try:
            path=self.root/'provider-diagnostics.sqlite3'
            if path.is_symlink():raise ValueError('DIAGNOSTIC_SYMLINK_FORBIDDEN')
            with closing(sqlite3.connect(path,timeout=.1)) as db, db:
                path.chmod(0o600)
                db.execute('CREATE TABLE IF NOT EXISTS diagnostics(id INTEGER PRIMARY KEY,at REAL,body TEXT)')
                db.execute('INSERT INTO diagnostics(at,body) VALUES (?,?)',(self.clock(),json.dumps(receipt)))
                db.execute('DELETE FROM diagnostics WHERE id NOT IN (SELECT id FROM diagnostics ORDER BY id DESC LIMIT 256)')
            receipt['persisted']=True
        except Exception:
            receipt['persisted']=False  # Diagnostics must never resend or mask provider outcomes.
        return receipt

    def _call(self,args,*,json_result=True,deadline=None):
        started=time.monotonic();p=None;code='OK';cause=None;result=None
        timeout=6.0 if deadline is None else min(6.0,deadline-self.clock())
        try:
            if timeout<=0:
                code='NEBIUS_DEADLINE_EXPIRED';raise RuntimeError(code)
            cmd=self._command(args,json_result)
            p=self.runner(cmd,stdin=subprocess.DEVNULL,capture_output=True,text=True,
                          timeout=timeout,shell=False,encoding='utf-8')
            if p.returncode:
                code='NEBIUS_AUTH_REQUIRED' if p.returncode==7 else 'NEBIUS_COMMAND_FAILED'
                raise RuntimeError(code)
            if len(p.stdout)>1024*1024:
                code='NEBIUS_RESPONSE_TOO_LARGE';raise RuntimeError(code)
            result=json.loads(p.stdout) if json_result else None
        except Exception as exc:
            cause=exc
            if code=='OK':
                code=('NEBIUS_TIMEOUT' if isinstance(exc,subprocess.TimeoutExpired) else
                      'NEBIUS_INVALID_JSON' if isinstance(exc,json.JSONDecodeError) else
                      'NEBIUS_RESPONSE_UNCERTAIN')
        receipt=self._diagnostic(args,started,code,p.returncode if p else None,
                                 p.stderr if p else '')
        if cause is not None:
            error=RuntimeError(code);error.diagnostic=receipt
            raise error from None
        return result

    def _read(self,resource,deadline):
        if resource!=self.settings['resourceId']:raise ValueError('NEBIUS_RESOURCE_MISMATCH')
        s={'devlab_id':resource,'project_id':self.settings['projectId'],'tenant_id':self.settings['tenantId']}
        project=self._call(['iam','v2','project','get','--id',s['project_id']],deadline=deadline)
        validate_project_owner(project,s)
        raw=self._call(['ai','devlab','get','--id',resource],deadline=deadline)
        status=raw.get('status',{})
        if 'instances' in status and not isinstance(status['instances'],list):
            raise ValueError('NEBIUS_INSTANCES_PROOF_REQUIRED')
        summary=devlab_summary(raw,s)
        if self.public_key not in [canonical_key(k) for k in raw.get('spec',{}).get('ssh_authorized_keys',[])]:
            raise ValueError('NEBIUS_AUTHORIZED_PUBLIC_KEY_MISMATCH')
        status=raw.get('status',{})
        if not isinstance(status.get('instances'),list):
            # A startup phase can precede the backing VM pointer. Preserve that
            # phase without inventing an empty-instance/release proof or host.
            if summary['state'] in ('PROVISIONING','STARTING','IMAGE_PULLING'):
                return s,{**raw,'_lighttry_instances_proof':'startup-instance-list-pending'},{**summary,'instances':None}
            # ProtoJSON omits empty repeated fields. Omission alone is NOT proof:
            # require a complete independent project-wide VM list, then recheck
            # the same STOPPED Devlab/spec. Null/malformed values stay rejected.
            if 'instances' in status or summary['state']!='STOPPED':
                raise ValueError('NEBIUS_INSTANCES_PROOF_REQUIRED')
            listing=self._call(['compute','instance','list','--parent-id',s['project_id'],'--all'],deadline=deadline)
            if type(listing) is not dict or listing not in ({},{'items':[]}):
                raise ValueError('NEBIUS_PROJECT_NOT_PROVEN_EMPTY')
            fresh=self._call(['ai','devlab','get','--id',resource],deadline=deadline)
            current=devlab_summary(fresh,s)
            fresh_status=fresh.get('status',{})
            if (current['state']!='STOPPED' or fresh.get('spec')!=raw.get('spec') or
                    ('instances' in fresh_status and fresh_status['instances']!=[])):
                raise ValueError('NEBIUS_STOPPED_CHANGED_DURING_PROOF')
            raw={**fresh,'status':{**fresh_status,'instances':[]},
                 '_lighttry_instances_proof':'project-wide-empty-list-and-stopped-recheck'}
            summary=devlab_summary(raw,s)
        return s,raw,summary

    def observe(self,resource):
        deadline=self.clock()+20
        s,raw,summary=self._read(resource,deadline)
        state=summary['state']
        mapped={'STOPPED':'STOPPED','STOPPING':'STOPPING','RUNNING':'RUNNING',
                'PROVISIONING':'STARTING','STARTING':'STARTING','IMAGE_PULLING':'STARTING'}
        if state not in mapped:raise RuntimeError('NEBIUS_RESOURCE_ABNORMAL')
        result={'resourceId':resource,'independent':True,'state':mapped[state],
                'instances':summary['instances'],'simulation':False,'image':summary['image'],
                'instancesProof':raw.get('_lighttry_instances_proof','devlab-explicit-array')}
        # Only an omitted startup list is pending. Null/malformed lists, missing
        # RUNNING identity and missing STOPPED release proof remain rejected.
        pending=(state in ('PROVISIONING','STARTING','IMAGE_PULLING') and
                 'instances' not in raw.get('status',{}) and summary['instances'] is None)
        if not isinstance(raw.get('status',{}).get('instances'),list) and not pending:
            raise ValueError('NEBIUS_INSTANCES_PROOF_REQUIRED')
        if state=='RUNNING':
            active=[x for x in summary['instances'] if x.get('state')=='RUNNING']
            if len(active)!=1:
                # Preserve only bounded state labels/counts, never IPs or VM IDs.
                states={'RUNNING','STARTING','PROVISIONING','IMAGE_PULLING','STOPPING','STOPPED','FAILED','ERROR'}
                receipt={'stage':'devlab_instance_binding','code':'NEBIUS_CURRENT_VM_NOT_UNIQUE',
                         'instanceCount':len(summary['instances']),'activeCount':len(active),
                         'instances':[{'state':x.get('state') if x.get('state') in states else 'UNKNOWN',
                                       'computeState':x.get('compute_instance_state') if x.get('compute_instance_state') in states else 'UNKNOWN'}
                                      for x in summary['instances'][:8]]}
                try:
                    path=self.root/'provider-diagnostics.sqlite3'
                    if path.is_symlink():raise ValueError('DIAGNOSTIC_SYMLINK_FORBIDDEN')
                    with closing(sqlite3.connect(path,timeout=.1)) as db,db:
                        path.chmod(0o600)
                        db.execute('CREATE TABLE IF NOT EXISTS diagnostics(id INTEGER PRIMARY KEY,at REAL,body TEXT)')
                        db.execute('INSERT INTO diagnostics(at,body) VALUES (?,?)',(self.clock(),json.dumps(receipt)))
                        db.execute('DELETE FROM diagnostics WHERE id NOT IN (SELECT id FROM diagnostics ORDER BY id DESC LIMIT 256)')
                except Exception:pass  # A diagnostic failure must not change the rejection.
                raise ValueError('NEBIUS_CURRENT_VM_NOT_UNIQUE')
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
