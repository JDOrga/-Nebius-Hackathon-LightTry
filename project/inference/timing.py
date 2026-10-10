"""Append-only process-local monotonic observations; no CUDA synchronization."""
import contextlib
import json
import os
import time
import uuid


class Timeline:
    def __init__(self, path, phase, clock=time.perf_counter, *, process_entry=False):
        self.path, self.phase, self.clock = path, phase, clock
        self.origin = clock()
        self.process = uuid.uuid4().hex
        self.emit('process_start' if process_entry else 'session_start', pid=os.getpid(),
                  freshPythonChild=process_entry, filesystemCacheTemperature='unknown')

    def emit(self, event, **fields):
        now = self.clock()
        with self.path.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps({'event': event, 'phase': self.phase, 'process': self.process,
                'monotonicSeconds': now, 'elapsedSeconds': now - self.origin, 'utcEpoch': time.time(), **fields}) + '\n')

    @contextlib.contextmanager
    def span(self, event, **fields):
        start = self.clock()
        self.emit(event + '_start', **fields)
        try:
            yield
        except BaseException:
            self.emit(event + '_end', seconds=self.clock() - start, success=False, **fields)
            raise
        else:
            self.emit(event + '_end', seconds=self.clock() - start, success=True, **fields)
