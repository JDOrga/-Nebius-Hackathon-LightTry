"""One owned SSH process; continuous local guard/deadline checks, no reconnect."""
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import time
from inference.jobs import atomic, read


def guard_ok(run, wall):
    beat = read(run / 'heartbeat.json')
    from weights import parse_deadline
    age = wall - parse_deadline(beat['utc'])
    if (beat.get('offline') or not beat.get('sleep_held') or beat.get('stopped_verified')
            or beat.get('supervision_stop_latched') or not 0 <= age <= 30):
        raise ValueError('WATCH_LOCAL_GUARD_UNAVAILABLE')
    if any((run / f).exists() for f in ('complete.json', 'cancel.json', 'supervision-stop.json')):
        raise ValueError('WATCH_GUARD_STOP_ALREADY_REQUESTED')
    # No API. Existing guard owns lifecycle checks; verify the local PID is alive.
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        kernel=ctypes.windll.kernel32
        kernel.OpenProcess.restype=wintypes.HANDLE
        kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
        kernel.GetExitCodeProcess.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes=[wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, int(beat['pid']))
        if not handle:
            raise ValueError('WATCH_GUARD_PROCESS_MISSING')
        try:
            code = wintypes.DWORD()
            if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value != 259:
                raise ValueError('WATCH_GUARD_PROCESS_MISSING')
        finally:
            kernel.CloseHandle(handle)
    else:
        os.kill(int(beat['pid']), 0)


def observe(spec, run, plan, deadline, job):
    guard_ok(run, time.time())
    if time.time()>=deadline:raise TimeoutError('FIXED_WATCH_DEADLINE_REACHED')
    monotonic_deadline=time.monotonic()+max(0.,deadline-time.time())
    process = subprocess.Popen([spec['executable'], *spec['arguments']], stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    try:
        atomic(job / 'watch-process.json', {'pid': process.pid, 'sshSessions': 1, 'reconnectAllowed': False})
    except BaseException:
        process.kill();process.wait(timeout=5);process.stdout.close();raise
    messages = queue.Queue(maxsize=128); stopping=threading.Event()
    def enqueue(value):
        while not stopping.is_set():
            try:messages.put(value,timeout=.1);return
            except queue.Full:pass
    def reader():
        try:
            while True:
                line = process.stdout.readline(8193)
                if not line:break
                if len(line) > 8192 or not line.endswith(b'\n'):
                    enqueue(ValueError('WATCH_FRAME_TOO_LARGE'));return
                enqueue(line)
        except BaseException:
            enqueue(ValueError('WATCH_PIPE_READ_FAILED'))
        finally:enqueue(None)
    thread = threading.Thread(target=reader, daemon=True)
    try:thread.start()
    except BaseException:
        stopping.set();process.kill();process.wait(timeout=5);process.stdout.close();raise
    last, silence, total = None, time.monotonic(), 0
    try:
        while True:
            now = time.time(); guard_ok(run, now)
            if now >= deadline or time.monotonic()>=monotonic_deadline:raise TimeoutError('FIXED_WATCH_DEADLINE_REACHED')
            if time.monotonic() - silence > 60:raise TimeoutError('WATCH_HEARTBEAT_MISSING')
            try:line = messages.get(timeout=min(1., max(.001, deadline-now)))
            except queue.Empty:continue
            if line is None:
                code = process.wait(timeout=min(5., max(.001, deadline-time.time())))
                if code or last is None or last['status'] not in ('succeeded', 'failed'):
                    raise ValueError('WATCH_EXIT_UNCONFIRMED_NO_RECONNECT')
                if not last['executionStopped']:raise ValueError('WATCH_WORKER_STOP_UNCONFIRMED')
                return last
            if isinstance(line, BaseException):raise line
            total += len(line)
            if total > 1024*1024:raise ValueError('WATCH_OUTPUT_BOUND_EXCEEDED')
            value = json.loads(line)
            if (value.get('watchNonce'),value.get('taskId'),value.get('nonce')) != (spec['watchNonce'],plan['taskId'],plan['nonce']):
                raise ValueError('WATCH_STREAM_IDENTITY_MISMATCH')
            if value.get('status') not in ('queued','running','succeeded','failed'):
                raise ValueError('WATCH_STATUS_INVALID')
            done = value.get('completed')
            expected = [c['id'] for c in plan['cases']]
            if not isinstance(done,list) or len(done)!=len(set(done)) or any(c not in expected for c in done):
                raise ValueError('WATCH_COMPLETED_IDENTITY_MISMATCH')
            if last and (last['status'] in ('succeeded','failed') or not set(last['completed'])<=set(done)):
                raise ValueError('WATCH_STATE_REGRESSION')
            last = value; silence = time.monotonic()
            atomic(job/'last-observed.json',value)
            with (job/'watch-events.jsonl').open('a',encoding='utf-8') as log:
                log.write(json.dumps({'receivedMonotonic':silence,**value})+'\n')
    finally:
        stopping.set()
        if process.poll() is None:
            process.kill(); process.wait(timeout=5)  # kill owned handle, not arbitrary PID
        process.stdout.close(); thread.join(timeout=2)
        atomic(job/'watch-cleanup.json',{'pid':process.pid,'exitCode':process.returncode,'ownedProcessExited':process.poll() is not None,'readerExited':not thread.is_alive(),'reconnectAllowed':False})
