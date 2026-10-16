"""Durable session/dispatch latches and deadline guard; adapters are injected.

No real provider is registered by this module. Refresh/status is strictly read-only.
"""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3
import threading
import time
import uuid

from inference.jobs import JobError, ID
from model_readiness import ready as model_ready
from lighting import canonical

STATES={'STOPPED','STARTING','LOADING','READY','EXECUTING','STOPPING','UNKNOWN'}
LABELS=dict(zip(('STOPPED','STARTING','LOADING','READY','EXECUTING','STOPPING','UNKNOWN'),
               ('停止','启动中','模型加载中','就绪','执行中','停机中','异常待核实')))


class Sessions:
    def __init__(self, root, provider, worker, fallback, clock=time.time, *, protection_mode='off-host'):
        if protection_mode not in ('off-host','cpu-only'):raise ValueError('INVALID_PROTECTION_MODE')
        self.protection_mode=protection_mode
        self.root=Path(root)
        if not self.root.is_absolute() or any(p.is_symlink() for p in (self.root,*self.root.parents)):
            raise ValueError('PRIVATE_ABSOLUTE_GUARD_ROOT_REQUIRED')
        self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.path=self.root/'sessions.sqlite3'
        if self.path.is_symlink():raise ValueError('GUARD_DATABASE_SYMLINK_FORBIDDEN')
        self.provider,self.worker,self.fallback,self.clock=provider,worker,fallback,clock
        self.lock=threading.RLock()
        with self.db() as db:
            db.executescript('''PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY,scope TEXT UNIQUE NOT NULL,resource TEXT NOT NULL,body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS dispatches(job TEXT PRIMARY KEY,session TEXT NOT NULL,fingerprint TEXT NOT NULL,body TEXT NOT NULL,state TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS cpu_liveness(session TEXT PRIMARY KEY,at REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS events(sequence INTEGER PRIMARY KEY AUTOINCREMENT,session TEXT,event TEXT,at REAL);''')

    @contextmanager
    def db(self):
        db=sqlite3.connect(self.path,timeout=5);db.execute('PRAGMA synchronous=FULL')
        self.path.chmod(0o600)
        try:
            with db:yield db
        finally:db.close()

    def get(self, identity):
        with self.db() as db:
            row=db.execute('SELECT body FROM sessions WHERE id=?',(identity,)).fetchone()
            heartbeat=db.execute('SELECT at FROM cpu_liveness WHERE session=?',(identity,)).fetchone()
        if not row:raise JobError('SESSION_NOT_FOUND','会话不存在。',404)
        value=json.loads(row[0])
        if heartbeat:value['cpuHeartbeatAt']=max(value['cpuHeartbeatAt'],heartbeat[0])
        return value

    def latest(self):
        with self.db() as db:row=db.execute('SELECT body FROM sessions ORDER BY rowid DESC LIMIT 1').fetchone()
        value=json.loads(row[0]) if row else {'state':'STOPPED','label':LABELS['STOPPED'],'providerState':None,'verifiedStopped':False,'configured':True}
        if row:
            with self.db() as db:heartbeat=db.execute('SELECT at FROM cpu_liveness WHERE session=?',(value['sessionId'],)).fetchone()
            if heartbeat:value['cpuHeartbeatAt']=max(value['cpuHeartbeatAt'],heartbeat[0])
        if self.protection_mode=='cpu-only' and (not row or value.get('verifiedStopped')):
            snapshot=self.fallback.snapshot()
            value.update(snapshot)
        return value

    def save(self, value, event):
        if value['state'] not in STATES:raise ValueError('INVALID_GPU_STATE')
        value['label']=LABELS[value['state']]
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            current=db.execute('SELECT body FROM sessions WHERE id=?',(value['sessionId'],)).fetchone()
            if not current or json.loads(current[0]).get('revision',0)!=value.get('revision',0):
                raise JobError('SESSION_CHANGED','会话已变化；重新查询，不重复副作用。',409)
            value['revision']=value.get('revision',0)+1
            db.execute('UPDATE sessions SET body=? WHERE id=?',(canonical(value),value['sessionId']))
            db.execute('INSERT INTO events(session,event,at) VALUES (?,?,?)',(value['sessionId'],event,self.clock()))

    def change(self,identity,event,apply,*,record_noop=False):
        """Short atomic transition. No network or caller-supplied code inside the DB lock."""
        with self.lock,self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT body FROM sessions WHERE id=?',(identity,)).fetchone()
            if not row:raise JobError('SESSION_NOT_FOUND','会话不存在。',404)
            value=json.loads(row[0])
            heartbeat=db.execute('SELECT at FROM cpu_liveness WHERE session=?',(identity,)).fetchone()
            if heartbeat:value['cpuHeartbeatAt']=max(value['cpuHeartbeatAt'],heartbeat[0])
            if apply(value) is False:
                if record_noop:db.execute('INSERT INTO events(session,event,at) VALUES (?,?,?)',(identity,event,self.clock()))
                return value,False
            if value['state'] not in STATES:raise ValueError('INVALID_GPU_STATE')
            value['label']=LABELS[value['state']];value['revision']=value.get('revision',0)+1
            db.execute('UPDATE sessions SET body=? WHERE id=?',(canonical(value),identity))
            db.execute('INSERT INTO events(session,event,at) VALUES (?,?,?)',(identity,event,self.clock()))
            return value,True

    def start(self, scope):
        now=self.clock()
        required={'scopeId','resourceId','expiresAt','budgetApproved','idleSeconds','simulation'}
        if (not isinstance(scope,dict) or set(scope)!=required or not ID.fullmatch(scope['scopeId']) or
                not isinstance(scope['resourceId'],str) or not scope['resourceId'] or
                scope['budgetApproved'] is not True or not 10<=scope['idleSeconds']<=300 or now>=scope['expiresAt']):
            raise JobError('CURRENT_SCOPE_REQUIRED','需要新的服务端范围、预算、空闲上限和有效授权。',403)
        if type(scope['simulation']) is not bool or (scope['simulation'] is False and any(getattr(x,'simulation',False) for x in (self.provider,self.worker,self.fallback))):
            raise JobError('SIMULATION_NOT_REAL_AUTHORIZATION','离线替身不可用于真实云授权。',403)
        with self.lock,self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT body FROM sessions WHERE scope=?',(scope['scopeId'],)).fetchone()
            if old:return json.loads(old[0])  # Different clicks/tabs still bind one scope, one start.
            previous=db.execute('SELECT body FROM sessions WHERE resource=? ORDER BY rowid DESC LIMIT 1',(scope['resourceId'],)).fetchone()
            if previous and not json.loads(previous[0]).get('verifiedStopped'):
                raise JobError('RESOURCE_UNVERIFIED','已有执行或停机待核实，禁止新启动。',409)
            sid=uuid.uuid4().hex
            value={'sessionId':sid,'scopeId':scope['scopeId'],'resourceId':scope['resourceId'],
                'state':'STARTING','providerState':None,'simulation':scope['simulation'],
                'protectionMode':self.protection_mode,
                'recoveryMode':getattr(self,'recovery_mode',False) is True,'createdAt':now,'startupDeadline':min(now+600,scope['expiresAt']),
                'absoluteDeadline':min(now+2400,scope['expiresAt']),
                'runningAt':None,'workDeadline':None,'stopDeadline':None,'verifyDeadline':None,
                'idleSeconds':scope['idleSeconds'],'idleDeadline':None,'stopWaitDeadline':None,
                'lastObservedAt':now,'cpuHeartbeatAt':now,'cpuLeaseSeconds':30,
                'startSent':False,'stopSent':False,'hostConfirmed':False,'hostIdentity':None,
                'verifiedStopped':False,'instancesEmpty':False,'guardExited':False,'sleepHeld':False,
                'error':None,'label':LABELS['STARTING'],'revision':0}
            db.execute('INSERT INTO sessions VALUES (?,?,?,?)',(sid,scope['scopeId'],scope['resourceId'],canonical(value)))
            db.commit()  # Reserve identity before any side effects or network.
        try:
            preflight=self.provider.preflight(scope['resourceId'])
            if not self.proof(preflight,value) or preflight['state']!='STOPPED' or preflight.get('instances')!=[]:
                raise ValueError('PREFLIGHT_NOT_STOPPED_EMPTY')
            bootstrap=getattr(self,'bootstrap',None)
            if bootstrap is not None:bootstrap.preflight(preflight)
            receipt=self.fallback.arm(sid,scope['resourceId'],value['absoluteDeadline'],30)
            protection_ok=(receipt.get('independentHost') is True if self.protection_mode=='off-host' else
                receipt.get('independentHost') is False and receipt.get('protectionMode')=='cpu-only' and
                receipt.get('cpuHostRiskAccepted') is True)
            if (receipt.get('sessionId')!=sid or receipt.get('resourceId')!=scope['resourceId'] or
                    not protection_ok or receipt.get('ready') is not True or
                    receipt.get('deadline')!=value['absoluteDeadline'] or receipt.get('leaseSeconds')!=30 or
                    (scope['simulation'] is False and receipt.get('simulation') is not False)):
                raise ValueError('SUPERVISOR_NOT_READY')
            def latch(current):
                if current['startSent']:return False
                if current['stopSent'] or current['state']!='STARTING' or self.clock()>=current['startupDeadline']:
                    raise ValueError('CURRENT_START_WINDOW_CLOSED')
                current['startSent']=True
            value,send=self.change(sid,'START_ATTEMPT_LATCHED',latch)
            if not send:return value
            self.provider.start(scope['resourceId'],sid,value['absoluteDeadline'])
        except Exception:
            def uncertain(current):
                if current['stopSent'] or current['verifiedStopped']:return False
                current['state']='UNKNOWN';current['error']='START_OR_PREFLIGHT_UNCERTAIN'
            self.change(sid,'START_UNCERTAIN',uncertain,record_noop=True)
        return self.get(sid)

    @staticmethod
    def proof(observation,value):
        return (isinstance(observation,dict) and observation.get('independent') is True and
                observation.get('resourceId')==value['resourceId'] and
                observation.get('state') in ('STOPPED','STOPPING','STARTING','RUNNING'))

    def confirm_host(self, identity, host_identity):
        with self.lock:
            value=self.get(identity)
            if (value['state']!='LOADING' or not value['hostIdentity'] or host_identity!=value['hostIdentity'] or
                self.clock()>=value['workDeadline'] or not 0<=self.clock()-value['lastObservedAt']<=30 or
                not value.get('recoveryMode') and value['idleDeadline'] is not None and self.clock()>=value['idleDeadline']):
                raise JobError('CURRENT_HOST_CONFIRMATION_REQUIRED','当前 RUNNING 主机身份不匹配。',409)
            value['hostConfirmed']=True;self.save(value,'CURRENT_HOST_CONFIRMED');return value

    def heartbeat(self, identity):
        with self.lock:
            value=self.get(identity);now=self.clock()
            if now<max(value['lastObservedAt'],value['cpuHeartbeatAt']):raise JobError('CLOCK_REGRESSED','时钟回退；不得续租。',409)
            # Heartbeats must not invalidate a slow provider observation's revision.
            with self.db() as db:
                db.execute('INSERT INTO cpu_liveness VALUES (?,?) ON CONFLICT(session) DO UPDATE SET at=max(at,excluded.at)',(identity,now))
                db.execute('INSERT INTO events(session,event,at) VALUES (?,?,?)',(identity,'CPU_HEARTBEAT',now))
            # Remote deadman never receives a later absolute deadline.
            self.fallback.heartbeat(identity,value['resourceId'],now)

    def request_stop(self, identity, reason='OPERATOR_STOP'):
        with self.lock:
            def latch(value):
                if value['state']=='STOPPED' or value['stopSent']:return False
                now=self.clock();value['state']='STOPPING';value['error']=reason
                upper=value['verifyDeadline'] or min(value['startupDeadline']+120,value['absoluteDeadline'])
                value['stopWaitDeadline']=min(now+120,upper,value['absoluteDeadline']);value['stopSent']=True
            value,send=self.change(identity,'STOP_ATTEMPT_LATCHED',latch)
            if not send:return value
            try:self.provider.stop(value['resourceId'],identity)
            except Exception:
                def uncertain(current):
                    if current['verifiedStopped']:return False
                    current['error']='STOP_RESPONSE_UNCERTAIN'
                self.change(identity,'STOP_UNCERTAIN',uncertain,record_noop=True)
            return self.get(identity)

    def poll(self, identity):
        """Independent guard only; never called from application GET/status."""
        with self.lock:
            value=self.get(identity);now=self.clock()
            if value['verifiedStopped']:return value
            if now<max(value['lastObservedAt'],value['cpuHeartbeatAt']):
                value['state']='UNKNOWN';value['error']='CLOCK_REGRESSED';self.save(value,'CLOCK_REGRESSED');return value
            value['lastObservedAt']=now
            stopping=value['stopSent'];ready=False
            due=(now>=value['absoluteDeadline'] or now-value['cpuHeartbeatAt']>=value['cpuLeaseSeconds'] or
                 (value['runningAt'] is None and now>=value['startupDeadline']) or
                 (value['workDeadline'] is not None and now>=value['workDeadline']) or
                 (not value.get('recoveryMode') and value['idleDeadline'] is not None and value['state'] in ('READY','LOADING') and now>=value['idleDeadline']))
            if due and not stopping:
                self.save(value,'DEADLINE_DUE');return self.request_stop(identity,'DEADLINE_OR_CPU_LEASE')
            stop_bound_exceeded=stopping and now>=value['stopWaitDeadline']
            if stop_bound_exceeded:
                value['state']='UNKNOWN';value['error']='STOPPING_BOUND_EXCEEDED';self.save(value,'STOPPING_BOUND_EXCEEDED')
                # Off-host stop-only fallback remains armed; do not extend work/verification.
            try:
                observed=self.provider.observe(value['resourceId'])
                received=self.clock()
                if received<now:raise ValueError('CLOCK_REGRESSED_DURING_OBSERVATION')
                now=received;value['lastObservedAt']=received
                value['cpuHeartbeatAt']=max(value['cpuHeartbeatAt'],self.get(identity)['cpuHeartbeatAt'])
                if not stopping and (now>=value['absoluteDeadline'] or now-value['cpuHeartbeatAt']>=value['cpuLeaseSeconds'] or
                    value['runningAt'] is None and now>=value['startupDeadline'] or
                    value['workDeadline'] is not None and now>=value['workDeadline'] or
                    not value.get('recoveryMode') and value['idleDeadline'] is not None and value['state'] in ('READY','LOADING') and now>=value['idleDeadline']):
                    self.save(value,'DEADLINE_DURING_OBSERVATION');return self.request_stop(identity,'DEADLINE_DURING_OBSERVATION')
                stop_bound_exceeded=bool(stopping and now>=value['stopWaitDeadline'])
                if stop_bound_exceeded:value['error']='STOPPING_BOUND_EXCEEDED'
                if not self.proof(observed,value):raise ValueError('PROVIDER_IDENTITY_MISMATCH')
                if value.get('error')=='OBSERVATION_UNCERTAIN':value['error']=None
                value['providerState']=observed['state']
                if observed['state']=='STOPPED':
                    if observed.get('instances')!=[]:raise ValueError('STOPPED_NOT_EMPTY')
                    if value['stopSent'] or value['runningAt'] is not None:
                        value.update(state='STOPPED',verifiedStopped=True,instancesEmpty=True)
                    # STOPPED just after start may be stale: never declare start success/retry.
                elif value['stopSent']:
                    value['state']='UNKNOWN' if stop_bound_exceeded else 'STOPPING'
                elif observed['state']=='RUNNING':
                    if not value['startSent']:raise ValueError('UNOWNED_RUNNING_INSTANCE')
                    if value['runningAt'] is not None and (observed.get('hostIdentity')!=value['hostIdentity'] or
                            value.get('image') is not None and observed.get('image')!=value['image']):
                        if value.get('recoveryMode'):
                            value.update(state='UNKNOWN',hostConfirmed=False,error='CURRENT_HOST_CHANGED',observedUnconfirmedHostIdentity=observed.get('hostIdentity'))
                            self.save(value,'RECOVERY_HOLD_IDENTITY_CHANGED_NO_DISPATCH');return value
                        self.save(value,'CURRENT_HOST_CHANGED');return self.request_stop(identity,'CURRENT_HOST_CHANGED')
                    if value['runningAt'] is None:
                        value['runningAt']=now
                        value['workDeadline']=min(now+1080,value['absoluteDeadline'])
                        value['stopDeadline']=min(now+1500,value['absoluteDeadline'])
                        value['verifyDeadline']=min(now+1620,value['absoluteDeadline'])
                        value['idleDeadline']=min(now+value['idleSeconds'],value['workDeadline'])
                        value['hostIdentity']=observed.get('hostIdentity')
                        value['image']=observed.get('image')
                        value['state']='LOADING'
                    if not value['hostConfirmed']:value['state']='LOADING'
                    bootstrap=getattr(self,'bootstrap',None)
                    if hasattr(self.worker,'bind_session'):self.worker.bind_session(value)
                    if value['hostConfirmed'] and (bootstrap is None or bootstrap.connected(identity) or getattr(self.worker,'direct_available',False) is True):
                        health=self.worker.health()
                        if (health.get('sessionId')!=identity or health.get('resourceId')!=value['resourceId']):
                            raise ValueError('WORKER_SESSION_MISMATCH')
                        ready=model_ready(health,{'sessionId':identity,'resourceId':value['resourceId'],
                            'hostIdentity':value['hostIdentity']},simulation=value['simulation'])
                        if ready and value['state']!='EXECUTING':value['state']='READY'
                        elif not ready:value['state']='LOADING'
                    elif value['hostConfirmed']:value['state']='LOADING'
                else:value['state']='STARTING'
                if not value['stopSent']:
                    with self.db() as db:pending=db.execute("SELECT body FROM dispatches WHERE session=? AND state IN ('active','uncertain','attempted') ORDER BY rowid LIMIT 1",(identity,)).fetchone()
                    if pending:
                        envelope=json.loads(pending[0]);remote=self.worker.query(envelope['jobId'])
                        if any(remote.get(k)!=v for k,v in envelope.items()) or remote.get('status')=='not_found':raise ValueError('TASK_UNKNOWN')
                        if remote['status'] in ('succeeded','failed'):
                            with self.db() as db:db.execute("UPDATE dispatches SET state='done' WHERE job=?",(envelope['jobId'],))
                            value['state']='READY' if ready else 'LOADING';value['idleDeadline']=min(now+value['idleSeconds'],value['workDeadline'])
                        elif remote['status'] in ('queued','dispatching'):value['state']='EXECUTING'
                        else:raise ValueError('TASK_UNKNOWN')
            except Exception as failure:
                allowed={'NEBIUS_AUTH_REQUIRED','NEBIUS_COMMAND_FAILED','NEBIUS_RESPONSE_UNCERTAIN',
                    'NEBIUS_RESPONSE_TOO_LARGE','NEBIUS_INSTANCES_PROOF_REQUIRED','NEBIUS_PROJECT_NOT_PROVEN_EMPTY',
                    'NEBIUS_STOPPED_CHANGED_DURING_PROOF','NEBIUS_VM_CHANGED_DURING_OBSERVATION',
                    'NEBIUS_CURRENT_VM_NOT_UNIQUE','NEBIUS_CURRENT_VM_ID_INVALID','NEBIUS_AUTHORIZED_PUBLIC_KEY_MISMATCH',
                    'PROVIDER_IDENTITY_MISMATCH','CLOCK_REGRESSED_DURING_OBSERVATION','API_IP_MISMATCH',
                    'VM_NOT_RUNNING','CURRENT_VM_NOT_UNIQUE','WORKER_RESPONSE_UNCERTAIN'}
                code=str(failure)
                if code not in allowed:code='UNCLASSIFIED_OBSERVATION_FAILURE'
                value['lastObservationFailure']={'code':code,'at':self.clock()}
                value['state']='UNKNOWN';value['error']='OBSERVATION_UNCERTAIN'
            self.save(value,'GUARD_OBSERVATION');return value

    def submit(self, identity, envelope):
        with self.lock:
            value=self.get(identity)
            if (envelope.get('sessionId')!=identity or envelope.get('resourceId')!=value['resourceId'] or
                    not ID.fullmatch(envelope.get('jobId',''))):raise JobError('JOB_BINDING_INVALID','任务与会话不匹配。',422)
            fingerprint=hashlib.sha256(canonical(envelope).encode()).hexdigest();job=envelope['jobId']
            with self.db() as db:
                old=db.execute('SELECT fingerprint,state FROM dispatches WHERE job=?',(job,)).fetchone()
                if old and old[0]!=fingerprint:raise JobError('JOB_CONFLICT','任务身份内容冲突。',409)
                if not old:
                    if (value['state']!='READY' or self.clock()>=value['workDeadline'] or not value['hostConfirmed']):
                        raise JobError('GPU_NOT_READY','当前会话未就绪或工作窗口已关闭。',409)
                    if db.execute("SELECT 1 FROM dispatches WHERE session=? AND state IN ('attempted','uncertain','active')",(identity,)).fetchone():
                        raise JobError('GPU_BUSY','单 GPU 已占用或任务待核实。',409)
            try:remote=self.worker.query(job)
            except Exception:return self.uncertain_job(value,envelope,fingerprint)
            if remote.get('status')!='not_found':
                if any(remote.get(k)!=v for k,v in envelope.items()):return self.uncertain_job(value,envelope,fingerprint)
                with self.db() as db:db.execute('INSERT OR REPLACE INTO dispatches VALUES (?,?,?,?,?)',(job,identity,fingerprint,canonical(envelope),'active' if remote['status'] in ('queued','dispatching','uncertain') else 'done'))
                if remote['status']=='uncertain':return self.uncertain_job(value,envelope,fingerprint)
                value['state']='EXECUTING' if remote['status'] in ('queued','dispatching') else 'READY'
                if value['state']=='READY':value['idleDeadline']=min(self.clock()+value['idleSeconds'],value['workDeadline'])
                self.save(value,'TASK_RECONCILED');return remote
            if old:return self.uncertain_job(value,envelope,fingerprint)  # 404 after lost ACK is not permission to rerun.
            with self.db() as db:db.execute('INSERT INTO dispatches VALUES (?,?,?,?,?)',(job,identity,fingerprint,canonical(envelope),'attempted'))
            value['state']='EXECUTING';self.save(value,'TASK_ATTEMPT_LATCHED')
            try:
                remote=self.worker.submit(envelope)
                if any(remote.get(k)!=v for k,v in envelope.items()) or remote.get('status') not in ('queued','dispatching','succeeded','failed'):
                    raise ValueError('WORKER_ACK_MISMATCH')
                with self.db() as db:db.execute("UPDATE dispatches SET state='active' WHERE job=?",(job,))
                return remote
            except Exception:return self.uncertain_job(value,envelope,fingerprint)

    def uncertain_job(self,value,envelope,fingerprint):
        with self.db() as db:db.execute('INSERT OR REPLACE INTO dispatches VALUES (?,?,?,?,?)',(envelope['jobId'],value['sessionId'],fingerprint,canonical(envelope),'uncertain'))
        value['state']='UNKNOWN';value['error']='TASK_RESPONSE_UNCERTAIN';self.save(value,'TASK_UNCERTAIN')
        return {'jobId':envelope['jobId'],'status':'uncertain','mustQueryBeforeRetry':True}

    def record_guard_exit(self, identity, observed_exited, sleep_released):
        value=self.get(identity)
        if not value['verifiedStopped'] or observed_exited is not True or sleep_released is not True:
            raise JobError('RELEASE_UNVERIFIED','独立停机/退出/释放证明不齐。',409)
        value['guardExited']=True;value['sleepHeld']=False;self.save(value,'GUARD_EXIT_EXTERNALLY_VERIFIED')
        return value


class Deadman:
    simulation=True
    """Stop-only management-host fallback; independent machine/storage/provider credentials.

    Must be deployed OUTSIDE CPU/GPU before real start. Here only simulation is wired.
    """
    def __init__(self, root, provider, clock=time.time):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.provider,self.clock=provider,clock
        self.path=self.root/'deadman.sqlite3'
        with self.db() as db:db.execute('CREATE TABLE IF NOT EXISTS leases(session TEXT PRIMARY KEY,resource TEXT,deadline REAL,heartbeat REAL,lease INTEGER,sent INTEGER,stopped INTEGER)')

    @contextmanager
    def db(self):
        db=sqlite3.connect(self.path)
        try:
            with db:yield db
        finally:db.close()

    def arm(self,sid,resource,deadline,lease_seconds):
        with self.db() as db:
            old=db.execute('SELECT resource,deadline,lease FROM leases WHERE session=?',(sid,)).fetchone()
            if old and old!=(resource,deadline,lease_seconds):raise ValueError('DEADMAN_DEADLINE_IMMUTABLE')
            db.execute('INSERT OR IGNORE INTO leases VALUES (?,?,?,?,?,0,0)',(sid,resource,deadline,self.clock(),lease_seconds))
        return {'sessionId':sid,'resourceId':resource,'deadline':deadline,'leaseSeconds':lease_seconds,'independentHost':True,'ready':True,'simulation':True}

    def heartbeat(self,sid,resource,now):
        with self.db() as db:
            row=db.execute('SELECT deadline,heartbeat,sent FROM leases WHERE session=? AND resource=?',(sid,resource)).fetchone()
            if not row or row[2] or now<row[1] or now>=row[0]:raise ValueError('DEADMAN_LEASE_CLOSED')
            db.execute('UPDATE leases SET heartbeat=? WHERE session=?',(min(now,self.clock()),sid))

    def tick(self):
        with self.db() as db:
            for sid,resource,deadline,beat,lease,sent,stopped in db.execute('SELECT * FROM leases').fetchall():
                if stopped:continue
                if self.clock()>=deadline or self.clock()-beat>=lease:
                    if not sent:
                        db.execute('UPDATE leases SET sent=1 WHERE session=?',(sid,));db.commit()
                        try:self.provider.stop(resource,sid+'-deadman')
                        except Exception:pass  # One idempotency key; uncertain stop remains an alarm, not success.
                    try:
                        observed=self.provider.observe(resource)
                        if observed.get('independent') is True and observed.get('resourceId')==resource and observed.get('state')=='STOPPED' and observed.get('instances')==[]:
                            db.execute('UPDATE leases SET stopped=1 WHERE session=?',(sid,))
                    except Exception:pass
