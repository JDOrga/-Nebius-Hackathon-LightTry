"""Durable, single-GPU FIFO. Only a server-side approved adapter can dispatch.

GET never calls tick/submit/launch/stop. Uncertain dispatch blocks the entire GPU.
"""
import copy
import json
from pathlib import Path
import threading
import time
import uuid

from inference.images import decode, digest, InputError
from inference.jobs import ID, JobError, ACTIVE, read
from lighting import canonical, normalize_scheme


class GPUQueue:
    @staticmethod
    def account(owner):
        # Browser-space suffix is ownership only; paid authorization remains account-scoped.
        return owner.split('~',1)[0]

    def __init__(self, workspace, task_store):
        self.workspace,self.store=workspace,task_store
        self.root=workspace.root/'queue'
        if self.root.is_symlink():raise ValueError('QUEUE_SYMLINK_FORBIDDEN')
        self.root.mkdir(exist_ok=True,mode=0o700)
        self.mutex=threading.RLock();self.stop_event=threading.Event();self.thread=None
        with workspace.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS gpu_queue (
                id TEXT PRIMARY KEY,owner TEXT NOT NULL,request TEXT NOT NULL,
                fingerprint TEXT NOT NULL,metadata TEXT NOT NULL,mime TEXT NOT NULL,
                state TEXT NOT NULL,created REAL NOT NULL,error TEXT,
                UNIQUE(owner,request))''')

    def row(self, identity, owner):
        if not ID.fullmatch(identity):raise JobError('TASK_NOT_FOUND','任务不存在。',404)
        with self.workspace.connect() as db:
            row=db.execute('SELECT * FROM gpu_queue WHERE id=? AND owner=?',(identity,owner)).fetchone()
        if not row:raise JobError('TASK_NOT_FOUND','任务不存在。',404)
        return row

    def contains(self, identity, owner):
        try:self.row(identity,owner);return True
        except JobError:return False

    def foreign_in_flight(self, owner):
        """Fail closed on any other account's running, uncertain, or waiting work."""
        with self.mutex,self.workspace.connect() as db:
            rows=db.execute('SELECT id,owner,state FROM gpu_queue').fetchall()
            owners={identity:account for identity,account,_ in rows}
            if any(account!=owner and state in ('waiting','dispatching','active','blocked')
                   for _,account,state in rows):return True
            for folder in self.store.root.iterdir():
                if not ID.fullmatch(folder.name):continue
                if folder.is_symlink():return True
                path=folder/'task.json'
                if path.is_symlink():return True
                if not path.is_file():continue
                try:task=read(path)
                except (OSError,ValueError,TypeError,KeyError):return True
                if not isinstance(task,dict):return True
                if task.get('status') not in ACTIVE and not task.get('executionUncertain'):continue
                account=owners.get(folder.name)
                if account is None:
                    row=db.execute("SELECT owner FROM ownership WHERE kind='task' AND id=?",(folder.name,)).fetchone()
                    account=row[0] if row else None
                if account!=owner:return True
            return False

    def submit(self, payload, metadata, mime, owner):
        executor=self.store.executor
        if not executor or not callable(getattr(executor,'authorize_job',None)):
            raise JobError('SERVICE_NOT_CONNECTED','收费执行未配置或未获逐项服务端授权；未入队。',503)
        allowed={'inputId','requestId','name','lightingScheme','presetId','presetIds','languageProposalId'}
        if (not isinstance(metadata,dict) or set(metadata)-allowed or
                any(not isinstance(metadata.get(k),str) or not ID.fullmatch(metadata[k]) for k in ('inputId','requestId'))):
            raise JobError('INVALID_REQUEST','任务字段或身份无效。',422)
        if 'lightingScheme' in metadata:
            normalize_scheme(metadata['lightingScheme'],self.store.environments,self.store.lighting_capabilities)
            if metadata['lightingScheme']['inputId']!=metadata['inputId']:
                raise JobError('INVALID_REQUEST','方案与照片身份不一致。',422)
        else:
            ids=metadata.get('presetIds',[metadata.get('presetId')])
            if not isinstance(ids,list) or not 1<=len(ids)<=3 or any(x not in self.store.presets for x in ids):
                raise JobError('INVALID_REQUEST','预设无效。',422)
        name=metadata.get('name','照片')
        if not isinstance(name,str) or len(name)>200 or any(ord(c)<32 for c in name):
            raise JobError('INVALID_REQUEST','照片名称无效。',422)
        try:decode(payload,mime)
        except InputError as error:raise JobError('INVALID_IMAGE',str(error),422) from error
        with self.workspace.connect() as db:
            photo=db.execute("SELECT owner FROM ownership WHERE kind='photo' AND id=?",(metadata['inputId'],)).fetchone()
            if photo:
                if photo[0]!=owner:raise JobError('OBJECT_NOT_FOUND','照片不属于当前账号。',404)
                stored=db.execute('SELECT sha FROM photos WHERE id=?',(metadata['inputId'],)).fetchone()
                if stored and stored[0]!=digest(payload):raise JobError('PHOTO_CHANGED','提交照片不匹配已保存的原始字节。',409)
            if 'lightingScheme' in metadata:
                plan=db.execute("SELECT owner FROM ownership WHERE kind='plan' AND id=?",(metadata['lightingScheme']['planId'],)).fetchone()
                if plan and plan[0]!=owner:raise JobError('OBJECT_NOT_FOUND','方案不属于当前账号。',404)
        fingerprint=digest(canonical({'metadata':metadata,'photoSha256':digest(payload),'mime':mime}).encode())
        with self.mutex,self.workspace.lock,self.workspace.connect() as db:
            existing=db.execute('SELECT id,fingerprint FROM gpu_queue WHERE owner=? AND request=?',(owner,metadata['requestId'])).fetchone()
            if existing:
                if existing[1]!=fingerprint:raise JobError('IDEMPOTENCY_CONFLICT','重复请求内容不同。',409)
                return self.get(existing[0],owner)
            # Human/operator scope, current budget and guard are adapter checks, not client fields.
            if executor.authorize_job(self.account(owner),copy.deepcopy(metadata),fingerprint) is not True:
                raise JobError('EXECUTION_NOT_AUTHORIZED','本任务没有当前服务端收费授权。',403)
            if db.execute("SELECT count(*) FROM gpu_queue WHERE state IN ('waiting','dispatching','active','blocked')").fetchone()[0]>=20:
                raise JobError('QUEUE_FULL','串行队列已满。',429)
            identity=uuid.uuid4().hex
            self.workspace.claim('task',identity,owner,db)
            if 'lightingScheme' in metadata:self.workspace.claim('plan',metadata['lightingScheme']['planId'],owner,db)
            folder=self.root/identity;folder.mkdir(mode=0o700)
            (folder/'original').write_bytes(payload)
            db.execute('INSERT INTO gpu_queue VALUES (?,?,?,?,?,?,?,?,?)',(identity,owner,metadata['requestId'],fingerprint,
                       canonical(metadata),mime,'waiting',time.time(),None))
        return self.get(identity,owner)

    def get(self, identity, owner):
        row=self.row(identity,owner);metadata=json.loads(row[4])
        if (self.store.root/identity/'task.json').is_file():return self.store.get(identity)
        return {'taskId':identity,'input':{'id':metadata['inputId'],'name':metadata.get('name','照片'),
                'url':'/api/tasks/'+identity+'/original'},'preset':{'id':metadata.get('presetId','pending')},
                'status':'queued' if row[6]=='waiting' else 'failed','stage':None,'result':None,
                'error':{'code':'DISPATCH_UNCERTAIN','message':'派发结果未知；串行队列暂停，禁止重复生成。'} if row[6]=='blocked' else None,
                'executionUncertain':row[6] in ('dispatching','blocked'),'createdAt':row[7],
                **({'lightingScheme':metadata['lightingScheme']} if 'lightingScheme' in metadata else {})}

    def by_request(self, request, owner):
        with self.workspace.connect() as db:row=db.execute('SELECT id FROM gpu_queue WHERE owner=? AND request=?',(owner,request)).fetchone()
        if not row:raise JobError('TASK_NOT_FOUND','请求不存在。',404)
        return self.get(row[0],owner)

    def tick(self):
        # Called by the dedicated worker only. Holds one lane across all owners.
        with self.mutex,self.workspace.connect() as db:
            busy=db.execute("SELECT * FROM gpu_queue WHERE state IN ('dispatching','active','blocked') ORDER BY created LIMIT 1").fetchone()
            if busy:
                identity=busy[0]
                if not (self.store.root/identity/'task.json').is_file():
                    db.execute("UPDATE gpu_queue SET state='blocked' WHERE id=?",(identity,));return
                task=self.store.get(identity)
                if task['status'] in ACTIVE or task.get('executionUncertain'):return
                db.execute("UPDATE gpu_queue SET state='done' WHERE id=?",(identity,))
            # Existing unmanaged/legacy active or uncertain executions also hold the GPU.
            for folder in self.store.root.iterdir():
                if ID.fullmatch(folder.name) and not folder.is_symlink() and (folder/'task.json').is_file():
                    task=self.store.get(folder.name)
                    if task['status'] in ACTIVE or task.get('executionUncertain'):return
            row=db.execute("SELECT * FROM gpu_queue WHERE state='waiting' ORDER BY created,id LIMIT 1").fetchone()
            executor=self.store.executor
            if not row or not executor:return
            metadata=json.loads(row[4])
            if (not callable(getattr(executor,'authorize_job',None)) or
                    executor.authorize_job(self.account(row[1]),copy.deepcopy(metadata),row[3]) is not True):
                return  # Expired/revoked approval never becomes a dispatch.
            # Durable latch must be committed BEFORE the one and only external dispatch.
            db.execute("UPDATE gpu_queue SET state='dispatching' WHERE id=?",(row[0],));db.commit()
            try:
                folder=self.root/row[0];path=folder/'original'
                if any(p.is_symlink() for p in (path,*path.parents)):raise ValueError('UNSAFE_QUEUED_FILE')
                payload=path.read_bytes()
                expected=digest(canonical({'metadata':metadata,'photoSha256':digest(payload),'mime':row[5]}).encode())
                if expected!=row[3]:raise ValueError('QUEUED_INPUT_CHANGED')
                metadata['requestId']=row[0]  # Server-unique across owners; client id stays in queue DB.
                self.store.submit(payload,metadata,row[5],reserved_task_id=row[0])
                db.execute("UPDATE gpu_queue SET state='active' WHERE id=?",(row[0],))
            except Exception:
                db.execute("UPDATE gpu_queue SET state='blocked',error='DISPATCH_UNCERTAIN' WHERE id=?",(row[0],))

    def start(self):
        def worker():
            while not self.stop_event.wait(.5):
                try:self.tick()
                except Exception:pass  # Persistent dispatch latch is authoritative; never retry launch.
        self.thread=threading.Thread(target=worker,name='single-gpu-queue',daemon=True);self.thread.start()

    def close(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=5)
            if self.thread.is_alive():raise RuntimeError('QUEUE_WORKER_NOT_STOPPED')
