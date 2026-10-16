"""Explicit private CPU control binding. No provider discovery or cloud calls at boot."""
import importlib
import json
import logging
import math
from pathlib import Path
import re
import threading
import time

from gpu_session import Sessions
from inference.jobs import ID
from security import runtime_file
from cpu_supervisor import CPUHostSupervisor

LOG = logging.getLogger('lighttry.service')


class ControlBinding:
    def __init__(self, sessions, scope, clock=time.time):
        self.sessions, self.scope, self.clock = sessions, scope, clock
        self.stop = threading.Event()
        self.thread = None

    def heartbeat_once(self):
        """CPU liveness only; never poll provider, start, extend scope or confirm host."""
        state = self.sessions.latest()
        if (state.get('scopeId') == self.scope['scopeId'] and
                state.get('resourceId') == self.scope['resourceId'] and
                state.get('sessionId') and not state.get('verifiedStopped') and
                self.clock() < self.scope['expiresAt']):
            self.sessions.heartbeat(state['sessionId'])

    def start_heartbeat(self):
        if self.thread is not None:
            return
        def run():
            while not self.stop.is_set():
                try:
                    self.heartbeat_once()
                except Exception:
                    # Stop renewal after uncertainty. The selected supervisor
                    # owns shutdown; CPU-only is NOT host-loss protection.
                    LOG.error('GPU CPU heartbeat failed; lease renewal stopped')
                    return
                self.stop.wait(5)
        self.thread = threading.Thread(target=run, name='gpu-cpu-heartbeat', daemon=True)
        self.thread.start()

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=1)
        # Web exit never asserts STOPPED/guard exit; separate guard remains owner.


def load_control(path, code_root, clock=time.time, *, observer=False):
    if not path:
        return None
    value = json.loads(runtime_file(path, code_root).decode('utf-8'))
    if (not isinstance(value, dict) or
            set(value)-{'schemaVersion','enabled','factory','guardRoot','scopeFile','binding','protection'} or
            not {'schemaVersion','enabled','factory','guardRoot','scopeFile','binding'}<=set(value) or
            value['schemaVersion'] != 1 or type(value['enabled']) is not bool or (not observer and not value['enabled']) or
            not isinstance(value['factory'], str) or
            not re.fullmatch(r'[a-zA-Z_][a-zA-Z0-9_.]*:[a-zA-Z_][a-zA-Z0-9_]*',value['factory']) or
            not isinstance(value['binding'], dict)):
        raise ValueError('EXPLICIT_PRIVATE_CONTROL_BINDING_REQUIRED')
    policy=value.get('protection')
    if policy is not None and (not isinstance(policy,dict) or set(policy)!={'mode','cpuHostRiskAccepted'} or
            policy.get('mode')!='cpu-only' or policy.get('cpuHostRiskAccepted') is not True):
        raise ValueError('EXPLICIT_CPU_HOST_RISK_ACCEPTANCE_REQUIRED')
    root = Path(value['guardRoot'])
    if (not root.is_absolute() or root.resolve().is_relative_to(Path(code_root).resolve()) or
            any(p.is_symlink() for p in (root,*root.parents))):
        raise ValueError('PRIVATE_GUARD_ROOT_REQUIRED')
    scope = json.loads(runtime_file(value['scopeFile'], code_root).decode('utf-8'))
    if (not isinstance(scope, dict) or
            set(scope) != {'scopeId','resourceId','expiresAt','budgetApproved','idleSeconds','simulation'} or
            not isinstance(scope['scopeId'],str) or not ID.fullmatch(scope['scopeId']) or
            not isinstance(scope['resourceId'],str) or not scope['resourceId'] or
            (scope['budgetApproved'] is not True and not observer) or
            type(scope['expiresAt']) not in (int,float) or not math.isfinite(scope['expiresAt']) or
            (scope['expiresAt'] <= clock() and not observer) or
            type(scope['idleSeconds']) is not int or not 10 <= scope['idleSeconds'] <= 300 or
            type(scope['simulation']) is not bool):
        raise ValueError('NEW_APPROVED_UNEXPIRED_SCOPE_REQUIRED')
    # Private configuration is executable operator trust, not browser input.
    # Factory MUST only construct adapters; preflight/arm/start belong to start().
    module, symbol = value['factory'].split(':')
    sessions = getattr(importlib.import_module(module),symbol)(root,value['binding'])
    if not isinstance(sessions,Sessions):
        raise ValueError('CONTROL_FACTORY_SESSIONS_REQUIRED')
    if policy:
        if sessions.root.resolve()!=root.resolve():raise ValueError('CONTROL_GUARD_ROOT_MISMATCH')
        sessions.protection_mode='cpu-only'
        sessions.fallback=CPUHostSupervisor(root,scope['resourceId'],risk_accepted=True,clock=clock)
    elif getattr(sessions,'protection_mode','off-host')!='off-host':
        raise ValueError('CPU_POLICY_REQUIRED')
    if not scope['simulation'] and any(getattr(x,'simulation',False)
            for x in (sessions.provider,sessions.worker,sessions.fallback)):
        raise ValueError('SIMULATION_CANNOT_BIND_REAL_SCOPE')
    return ControlBinding(sessions,scope,clock)
