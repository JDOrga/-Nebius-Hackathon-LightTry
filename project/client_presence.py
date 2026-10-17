"""Authenticated connection liveness, separate from page JS and CPU liveness.

Waitress must have channel_request_lookahead=1 for disconnect detection.
Bounded stream slots reserve worker capacity for normal requests/stop controls.
"""
class PresenceStream:
    def __init__(self, sessions, disconnected, authorized, stop, release, interval=10):
        self.sessions,self.disconnected,self.authorized=sessions,disconnected,authorized
        self.stop,self.release,self.interval=stop,release,interval
        self.closed=False;self.first=True;self.sid=None

    def __iter__(self):return self

    def __next__(self):
        if self.closed:raise StopIteration
        if not self.first and self.stop.wait(self.interval):self.close();raise StopIteration
        self.first=False
        if self.stop.is_set() or self.disconnected() or not self.authorized():
            self.close();raise StopIteration
        try:
            sessions=self.sessions()
            if sessions:
                current=sessions.latest();self.sid=current.get('sessionId')
                if self.sid and not current.get('verifiedStopped') and not current.get('stopSent'):
                    sessions.client_presence(self.sid)
            return b'event: presence\ndata: {"connected":true}\n\n'
        except BaseException:
            self.close();raise

    def close(self):
        if self.closed:return
        self.closed=True
        try:
            # Start the five-minute grace at the observed disconnect, not one
            # heartbeat interval earlier. Never revive an already-expired lease.
            if self.sid and not self.stop.is_set():
                sessions=self.sessions()
                if sessions:sessions.client_presence(self.sid)
        finally:self.release()
