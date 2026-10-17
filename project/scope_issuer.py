"""Offline durable per-click scope issuance; never starts a provider or guard.

Call only after authenticated operator/CSRF checks. Policy is private operator
configuration, not a browser payload. Issuance does not imply host/model consent.
"""
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import time
import uuid


class ClosedConnection(sqlite3.Connection):
    def __exit__(self,*args):
        try:return super().__exit__(*args)
        finally:self.close()


class ScopeIssuer:
    def __init__(self, root, policy, *, clock=time.time):
        self.root=Path(root)
        if not self.root.is_absolute() or any(p.is_symlink() for p in (self.root,*self.root.parents)):
            raise ValueError('PRIVATE_SCOPE_ROOT_REQUIRED')
        self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.path=self.root/'scope-requests.sqlite3'
        if self.path.is_symlink():raise ValueError('SCOPE_DATABASE_UNSAFE')
        self.policy=dict(policy);self.clock=clock
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS requests(request TEXT PRIMARY KEY,owner TEXT NOT NULL,policy TEXT NOT NULL,body TEXT NOT NULL)')

    def db(self):
        db=sqlite3.connect(self.path,timeout=5,factory=ClosedConnection);db.execute('PRAGMA synchronous=FULL');self.path.chmod(0o600)
        return db

    def limits(self):
        p=self.policy
        required={'enabled','resourceId','budgetUsdIncludingTax','hourlyUsdIncludingTax','billingReserveSeconds','maxSessionSeconds','idleSeconds'}
        if set(p)!=required or p['enabled'] is not True:raise ValueError('CURRENT_START_POLICY_REQUIRED')
        if not isinstance(p['resourceId'],str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,200}',p['resourceId']):raise ValueError('RESOURCE_REQUIRED')
        for name in ('budgetUsdIncludingTax','hourlyUsdIncludingTax'):
            if type(p[name]) not in (int,float) or not math.isfinite(p[name]) or p[name]<=0:raise ValueError('CURRENT_RATE_AND_BUDGET_REQUIRED')
        for name,low,high in [('billingReserveSeconds',60,600),('maxSessionSeconds',60,5520),('idleSeconds',10,300)]:
            if type(p[name]) is not int or not low<=p[name]<=high:raise ValueError('BOUNDED_SESSION_POLICY_REQUIRED')
        seconds=min(p['maxSessionSeconds'],math.floor(p['budgetUsdIncludingTax']/p['hourlyUsdIncludingTax']*3600)-p['billingReserveSeconds'])
        # Keep a meaningful startup window; never silently enlarge a tiny budget.
        if seconds<600:raise ValueError('BUDGET_BELOW_STARTUP_ALLOWANCE')
        return seconds

    def issue(self,request_id,owner,*,approved=False):
        if approved is not True:raise ValueError('EXPLICIT_CLICK_APPROVAL_REQUIRED')
        if not isinstance(request_id,str) or not re.fullmatch('[a-f0-9]{32}',request_id):raise ValueError('REQUEST_ID_REQUIRED')
        if not isinstance(owner,str) or not 1<=len(owner)<=200:raise ValueError('AUTHENTICATED_OWNER_REQUIRED')
        duration=self.limits();now=self.clock()
        if type(now) not in (int,float) or not math.isfinite(now):raise ValueError('VALID_CLOCK_REQUIRED')
        policy_sha=hashlib.sha256(json.dumps(self.policy,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        db=self.db()
        try:
            with db:
                db.execute('BEGIN IMMEDIATE')
                row=db.execute('SELECT owner,policy,body FROM requests WHERE request=?',(request_id,)).fetchone()
                if row:
                    if row[0]!=owner or row[1]!=policy_sha:raise ValueError('CLICK_BINDING_CHANGED')
                    value=json.loads(row[2])
                    if now<value['approvedAt']:raise ValueError('CLOCK_REGRESSION')
                    if now>=value['scope']['expiresAt']:raise ValueError('CLICK_SCOPE_EXPIRED_NO_RENEWAL')
                    return value
                value={'scope':{'scopeId':uuid.uuid4().hex,'resourceId':self.policy['resourceId'],'expiresAt':now+duration,
                    'budgetApproved':True,'idleSeconds':self.policy['idleSeconds'],'simulation':False},
                    'approvedAt':now,'owner':owner,'requestId':request_id,'policySha256':policy_sha,
                    'budgetUsdIncludingTax':self.policy['budgetUsdIncludingTax'],'hourlyUsdIncludingTax':self.policy['hourlyUsdIncludingTax'],
                    'billingReserveSeconds':self.policy['billingReserveSeconds'],'budgetHardCap':False,
                    'hostConfirmed':False,'modelLicenseAck':False}
                db.execute('INSERT INTO requests VALUES (?,?,?,?)',(request_id,owner,policy_sha,json.dumps(value,sort_keys=True,separators=(',',':'))))
                return value
        finally:db.close()


    def approval_for_scope(self,scope):
        self.limits()
        expected=hashlib.sha256(json.dumps(self.policy,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        with self.db() as db:
            rows=db.execute("SELECT body FROM requests WHERE json_extract(body,'$.scope.scopeId')=?",(scope['scopeId'],)).fetchall()
        if len(rows)!=1:raise ValueError('CURRENT_CLICK_APPROVAL_REQUIRED')
        value=json.loads(rows[0][0]);now=self.clock()
        if (value['scope']!=scope or value['policySha256']!=expected or
                not value['approvedAt']<=now<scope['expiresAt']):raise ValueError('CURRENT_CLICK_APPROVAL_REQUIRED')
        return value
