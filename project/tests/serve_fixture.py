"""Explicit OFFLINE TEST server. No cloud execution imports or network clients."""
import argparse
from pathlib import Path
import sys
import threading
from http.server import ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import server
from inference.jobs import TaskStore
from inference_fixture import OfflineExecutor


class FixtureStore(TaskStore):
    def capabilities(self):
        return {**super().capabilities(), 'developmentTestMode': True,
                'message': '离线测试替身，非 GPU 结果；只用于本机验证。'}


class UIExecutor(OfflineExecutor):
    def submit(self, folder, request):
        super().submit(folder, request)
        self.event('running', 'inverse')
        # The tester controls completion by creating a local marker. These are
        # explicitly simulated executor events, not an elapsed-time progress bar.
        def finish():
            self.release.wait()
            self.succeed()
        self.release = threading.Event()
        def watch():
            while not (folder / 'test-complete').exists():
                if self.release.wait(0.25): return
            self.release.set()
        threading.Thread(target=watch, daemon=True).start()
        threading.Thread(target=finish, daemon=True).start()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8769)
    parser.add_argument('--tasks-dir', type=Path, required=True)
    args = parser.parse_args()
    store = FixtureStore(args.tasks_dir, server.load_catalog()['presets'], UIExecutor())
    handler = type('ExplicitOfflineFixtureHandler', (server.Handler,), {
        'task_store': store, 'catalog': server.load_catalog(), 'assets_dir': server.resolve_assets_dir()})
    try:
        with ThreadingHTTPServer(('127.0.0.1', args.port), handler) as http:
            print('OFFLINE TEST DOUBLE, NOT GPU: http://127.0.0.1:' + str(args.port), flush=True)
            http.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        store.close()
