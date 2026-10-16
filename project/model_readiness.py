"""No real READY without a live, current-session resident model report."""
import math
import re


def ready(health, session, *, simulation=False):
    if not isinstance(health,dict):return False
    if (health.get('sessionId')!=session['sessionId'] or
        health.get('resourceId')!=session['resourceId'] or health.get('modelState')!='ready'):
        return False
    if simulation:return True  # Explicit offline fixtures only; cannot authorize real scope.
    return (health.get('simulation') is False and health.get('modelLoaded') is True and
            health.get('executionMode')=='resident' and
            bool(session.get('hostIdentity')) and health.get('hostIdentity')==session['hostIdentity'])


def resident_receipt(receipt,task_id,nonce):
    """Resident phases finish calls, not processes; never invent process exits."""
    proof=receipt.get('residentExecution',{})
    if not isinstance(proof,dict):return False
    if (receipt.get('executionMode')!='resident' or receipt.get('runConfig',{}).get('modelExecutionMode')!='resident-v1' or receipt.get('processExitCodes')!=[None,None] or
        receipt.get('inverseReuse',{}).get('reused') is not False or
        proof.get('version')!=1 or proof.get('taskId')!=task_id or proof.get('nonce')!=nonce):return False
    phases=proof.get('phases',[])
    if not isinstance(phases,list) or len(phases)!=2 or {p.get('phase') for p in phases if isinstance(p,dict)}!={'inverse','forward'}:return False
    for p in phases:
        if (p.get('exitCode')!=0 or p.get('cudaSynchronized') is not True or
            type(p.get('pid')) is not int or p['pid']<=0 or
            not isinstance(p.get('id'),str) or not re.fullmatch('[a-f0-9]{32}',p['id']) or
            not isinstance(p.get('bootId'),str) or not re.fullmatch('[a-f0-9]{32}',p['bootId']) or
            not isinstance(p.get('modelObjectId'),str) or not re.fullmatch('0x[a-f0-9]+',p['modelObjectId']) or
            type(p.get('completedAt')) not in (int,float) or not math.isfinite(p['completedAt']) or
            not 0<p['completedAt']<=receipt.get('finishedAt',0)):return False
    return True
