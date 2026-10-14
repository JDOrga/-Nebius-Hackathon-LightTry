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

ROOT=Path(__file__).resolve().parent.parent


def main(argv=None):
    p=argparse.ArgumentParser(description='Independent guard or TLS-ingress worker; no implicit cloud start.')
    mode=p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--worker',action='store_true');mode.add_argument('--guard',action='store_true');mode.add_argument('--deadman',action='store_true')
    p.add_argument('--data-root',type=Path,required=True)
    p.add_argument('--session-id');p.add_argument('--resource-id')
    p.add_argument('--worker-token-file',default=os.environ.get('LIGHTTRY_WORKER_TOKEN_FILE'))
    p.add_argument('--guard-config',type=Path)
    args=p.parse_args(argv)
    if (not args.data_root.is_absolute() or args.data_root.resolve().is_relative_to(ROOT) or
            any(x.is_symlink() for x in (args.data_root,*args.data_root.parents))):
        raise ValueError('PRIVATE_RUNTIME_ROOT_OUTSIDE_CODE_REQUIRED')
    os.umask(0o077)
    if args.worker:
        if not args.worker_token_file or not args.session_id or not args.resource_id:
            raise ValueError('EXPLICIT_WORKER_IDENTITY_AND_RUNTIME_TOKEN_REQUIRED')
        token=runtime_file(args.worker_token_file,ROOT,4096).decode().strip()
        ledger=WorkerLedger(args.data_root,token,args.session_id,args.resource_id)
        # Model adapter remains unset; GET cannot load/execute a model.
        from waitress import serve
        serve(WorkerApplication(ledger),listen='127.0.0.1:9080',threads=2,max_request_body_size=32*1024*1024,
              max_request_header_size=8192,channel_timeout=10,channel_request_lookahead=0,expose_tracebacks=False)
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
