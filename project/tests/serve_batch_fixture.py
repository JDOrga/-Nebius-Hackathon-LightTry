"""OFFLINE TEST ONLY: controlled batch events, isolated store; no cloud clients."""
import argparse
from http.server import ThreadingHTTPServer
from pathlib import Path
import sys
import threading
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import server
from serve_fixture import FixtureStore
from batch_fixture import BatchFixtureExecutor

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8774)
    parser.add_argument('--tasks-dir',type=Path,required=True)
    parser.add_argument('--timeout',type=int,default=1080)
    args=parser.parse_args()
    executor=BatchFixtureExecutor()
    store=FixtureStore(args.tasks_dir,server.load_catalog()['presets'],executor,timeout=args.timeout)
    def watch():
        seen=set()
        while True:
            for folder,request in executor.calls:
                if folder in seen:continue
                marker=folder/'test-outcome.txt'
                if marker.exists():
                    seen.add(folder);executor.finish_batch(marker.read_text().strip())
            time.sleep(.2)
    threading.Thread(target=watch,daemon=True).start()
    handler=type('OfflineBatchHandler',(server.Handler,),{'task_store':store,'catalog':server.load_catalog(),'assets_dir':server.resolve_assets_dir()})
    try:
        with ThreadingHTTPServer(('127.0.0.1',args.port),handler) as http:
            print(f'OFFLINE TEST DOUBLE, NOT GPU http://127.0.0.1:{args.port}',flush=True);http.serve_forever()
    finally:store.close()
