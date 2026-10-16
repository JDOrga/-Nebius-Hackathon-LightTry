"""Guard-only session model grant creation. No network, provider or model calls."""
import json
import math
import os
from pathlib import Path
import secrets
import tempfile
import time
from inference.jobs import ID
from security import runtime_file
from model_contract import grant_file

ROOT=Path(__file__).resolve().parent.parent

class SessionGrantIssuer:
    def __init__(self,control,path,policy,clock=time.time):
        self.control,self.path,self.clock=control,Path(path),clock
        if (not self.path.is_absolute() or self.path.resolve().is_relative_to(ROOT) or
                any(p.is_symlink() for p in (self.path,*self.path.parents))):raise ValueError('PRIVATE_MODEL_GRANT_PATH_REQUIRED')
        if (not isinstance(policy,dict) or set(policy)!={'schemaVersion','modelLicenseAck','maxJobs'} or
                type(policy['schemaVersion']) is not int or policy['schemaVersion']!=1 or policy['modelLicenseAck'] is not True or
                type(policy['maxJobs']) is not int or not 1<=policy['maxJobs']<=20):raise ValueError('EXPLICIT_CURRENT_MODEL_LICENSE_POLICY_REQUIRED')
        self.policy=dict(policy)

    def ensure(self,sid):
        state=self.control.sessions.get(sid);scope=self.control.scope;now=self.clock()
        if (not isinstance(sid,str) or not ID.fullmatch(sid) or state.get('sessionId')!=sid or
                state.get('scopeId')!=scope['scopeId'] or state.get('resourceId')!=scope['resourceId'] or
                state.get('state') not in ('LOADING','READY','EXECUTING') or state.get('stopSent') or
                state.get('hostConfirmed') is not True or not isinstance(state.get('hostIdentity'),dict) or not state['hostIdentity'] or
                type(state.get('lastObservedAt')) not in (int,float) or not 0<=now-state['lastObservedAt']<=30):
            raise ValueError('CURRENT_CONFIRMED_MODEL_SESSION_REQUIRED')
        deadlines=[state.get('workDeadline'),state.get('absoluteDeadline'),scope.get('expiresAt')]
        if any(type(x) not in (int,float) or not math.isfinite(x) or x<=now for x in deadlines):raise ValueError('ORIGINAL_MODEL_WINDOW_EXPIRED')
        if not state.get('recoveryMode') and state.get('idleDeadline') is not None and now>=state['idleDeadline']:raise ValueError('MODEL_SESSION_IDLE_EXPIRED')
        approval=self.control.scope_issuer.approval_for_scope(scope)
        directory=Path(self.control.sessions.root)/'model-grants'
        if any(p.is_symlink() for p in (directory,*directory.parents)):raise ValueError('PRIVATE_MODEL_GRANT_PATH_REQUIRED')
        directory.mkdir(mode=0o700,exist_ok=True)
        archive=directory/(sid+'.json');published=directory/(sid+'.published');deadline=min(deadlines)
        if published.exists() and not self.path.exists():raise ValueError('CURRENT_SESSION_MODEL_GRANT_REVOKED_OR_CHANGED')
        def validate(value):
            if (value['schemaVersion']!=2 or value['hostIdentity']!=state['hostIdentity'] or
                    value['expiresAt']!=deadline or value['jobAuthorization']['owner']!=approval['owner'] or
                    value['approvalReference']!=scope['scopeId'] or value['budgetUsdIncludingTax']!=approval['budgetUsdIncludingTax'] or
                    value['maxJobs']!=self.policy['maxJobs']):raise ValueError('SESSION_MODEL_GRANT_CHANGED')
        if archive.exists():
            value=grant_file(archive,sid,scope['resourceId'],clock=self.clock);validate(value)
        else:
            value={'schemaVersion':2,'sessionId':sid,'resourceId':scope['resourceId'],'hostIdentity':state['hostIdentity'],
                'hostConfirmed':True,'modelLicenseAck':True,'expiresAt':deadline,
                'budgetUsdIncludingTax':approval['budgetUsdIncludingTax'],'approvalReference':scope['scopeId'],
                'maxJobs':self.policy['maxJobs'],'jobAuthorization':{'algorithm':'hmac-sha256-v1','keyHex':secrets.token_hex(32),'owner':approval['owner']}}
            try:
                fd=os.open(archive,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
                with os.fdopen(fd,'w',encoding='utf-8') as stream:json.dump(value,stream);stream.flush();os.fsync(stream.fileno())
            except FileExistsError:
                value=grant_file(archive,sid,scope['resourceId'],clock=self.clock);validate(value)
        # Preserve one immutable grant per session. Publish only its exact bytes.
        # Do not silently repair revoked/modified current-session authorization.
        if self.path.exists():
            current=json.loads(runtime_file(self.path,ROOT).decode())
            if current.get('sessionId')==sid:
                if current!=value:raise ValueError('CURRENT_SESSION_MODEL_GRANT_REVOKED_OR_CHANGED')
                return value
        self.path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        fd,name=tempfile.mkstemp(prefix='.model-grant-',dir=self.path.parent)
        try:
            with os.fdopen(fd,'wb') as stream:stream.write(archive.read_bytes());stream.flush();os.fsync(stream.fileno())
            os.replace(name,self.path)
            try:
                with published.open('xb') as receipt:receipt.write(b'published\n')
                published.chmod(0o600)
            except FileExistsError:pass
        finally:
            if os.path.exists(name):os.unlink(name)
        return value
