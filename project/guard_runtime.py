"""Separate guard/worker processes reached only through root start.py.

No built-in Nebius adapter; configuration cannot silently revive historical runs.
"""
import argparse
import importlib
import json
import os
from pathlib import Path
import re
import signal
import threading

from security import runtime_file
from gpu_session import Sessions,Deadman
from worker_link import WorkerLedger,WorkerApplication
from inference.jobs import JobError,ID

ROOT=Path(__file__).resolve().parent.parent


def cpu_guard_step(control):
    """The only CPU-only provider observation loop, separate from Web."""
    guard=control.sessions
    state=guard.latest()
    if state.get('sessionId'):
        state=guard.get(state['sessionId'])  # Durable state, not merged idle snapshot.
    observation=None
    if state.get('sessionId') and not state.get('verifiedStopped'):
        guard.poll(state['sessionId'])
    else:
        try:
            observation=guard.provider.preflight(control.scope['resourceId'])
            if not isinstance(observation,dict):observation=None
            else:observation={**observation,'simulation':getattr(guard.provider,'simulation',False) is True}
        except Exception:
            observation=None  # Unknown is never a stopped proof.
    guard.fallback.publish(observation)


def main(argv=None):
    p=argparse.ArgumentParser(description='Independent guard or TLS-ingress worker; no implicit cloud start.')
    mode=p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--worker',action='store_true');mode.add_argument('--guard',action='store_true');mode.add_argument('--deadman',action='store_true')
    p.add_argument('--data-root',type=Path,required=True)
    p.add_argument('--session-id');p.add_argument('--resource-id')
    p.add_argument('--worker-token-file',default=os.environ.get('LIGHTTRY_WORKER_TOKEN_FILE'))
    p.add_argument('--worker-config',type=Path,help='Explicit private Cosmos runtime configuration; absent means no model executor.')
    p.add_argument('--guard-config',type=Path)
    p.add_argument('--gpu-control-config',type=Path,default=os.environ.get('LIGHTTRY_GPU_CONTROL_CONFIG'))
    args=p.parse_args(argv)
    if (not args.data_root.is_absolute() or args.data_root.resolve().is_relative_to(ROOT) or
            any(x.is_symlink() for x in (args.data_root,*args.data_root.parents))):
        raise ValueError('PRIVATE_RUNTIME_ROOT_OUTSIDE_CODE_REQUIRED')
    os.umask(0o077)
    if args.worker:
        if not args.worker_token_file or not args.session_id or not ID.fullmatch(args.session_id) or not args.resource_id:
            raise ValueError('EXPLICIT_WORKER_IDENTITY_AND_RUNTIME_TOKEN_REQUIRED')
        token=runtime_file(args.worker_token_file,ROOT,4096).decode().strip()
        ledger=WorkerLedger(args.data_root/args.session_id,token,args.session_id,args.resource_id)
        executor=None
        try:
            if args.worker_config:
                from gpu_model import CosmosWorkerExecutor
                executor=CosmosWorkerExecutor(ledger,args.worker_config)
                ledger.simulation=False;ledger.executor=executor;executor.start()
            from waitress import serve
            def shutdown(*_):raise KeyboardInterrupt()
            signal.signal(signal.SIGTERM,shutdown)
            serve(WorkerApplication(ledger),listen='127.0.0.1:9080',threads=2,max_request_body_size=32*1024*1024,
                  max_request_header_size=8192,channel_timeout=10,channel_request_lookahead=0,expose_tracebacks=False)
        finally:
            if executor:executor.close()
            ledger.close()
        return
    if args.guard and args.gpu_control_config:
        from gpu_bootstrap import load_control
        control=load_control(args.gpu_control_config,ROOT,observer=True)
        guard=control.sessions
        if (guard.protection_mode!='cpu-only' or guard.root.resolve()!=args.data_root.resolve()):
            raise ValueError('CPU_GUARD_CONTROL_BINDING_MISMATCH')
        stop=threading.Event()
        signal.signal(signal.SIGTERM,lambda *_:stop.set());signal.signal(signal.SIGINT,lambda *_:stop.set())
        guard.fallback.acquire()
        try:
            while not stop.is_set():
                try:
                    cpu_guard_step(control)
                except JobError as exc:
                    # A concurrent heartbeat may have advanced the DB revision.
                    # Observe next tick, never resend a provider start/launch.
                    if exc.code!='SESSION_CHANGED':raise
                stop.wait(5)
        finally:
            try:
                current=guard.latest()
                if current.get('sessionId'):
                    current=guard.get(current['sessionId'])
                    if not current.get('verifiedStopped'):
                        guard.request_stop(current['sessionId'],'CPU_GUARD_SHUTDOWN')
            finally:guard.fallback.close()
        return
    if not args.guard_config:raise ValueError('RUNTIME_GUARD_BINDING_REQUIRED')
    value=json.loads(runtime_file(args.guard_config,ROOT).decode())
    if (value.get('enabled') is not True or value.get('schemaVersion')!=1 or
            not re.fullmatch(r'[a-zA-Z_][a-zA-Z0-9_.]*:[a-zA-Z_][a-zA-Z0-9_]*',value.get('factory',''))):
        raise ValueError('EXPLICIT_APPROVED_GUARD_FACTORY_REQUIRED')
    module,symbol=value['factory'].split(':')
    guard=getattr(importlib.import_module(module),symbol)(args.data_root,value)
    if not isinstance(guard,Deadman if args.deadman else Sessions):raise ValueError('GUARD_FACTORY_TYPE_MISMATCH')
    stop=threading.Event()
    signal.signal(signal.SIGTERM,lambda *_:stop.set());signal.signal(signal.SIGINT,lambda *_:stop.set())
    while not stop.is_set():
        if args.deadman:
            guard.tick();stop.wait(5);continue
        state=guard.latest()
        if state.get('sessionId'):
            state=guard.poll(state['sessionId'])
            if state.get('verifiedStopped'):return
        # One observer owned by this process; application status never polls cloud.
        stop.wait(5)
    # Process supervisor must record actual exit; do not self-assert release proof.
