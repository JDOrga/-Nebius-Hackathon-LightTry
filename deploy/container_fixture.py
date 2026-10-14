"""EXTERNAL TEST MOUNT ONLY: no cloud imports, no production activation switch."""
import sys
import os
from pathlib import Path
sys.path.insert(0, '/opt/lighttry/project')
sys.path.insert(0, '/acceptance')
from service import Application, parser
from inference_fixture import OfflineExecutor
from waitress import serve

class Synthetic(OfflineExecutor):
    def authorize_job(self, owner, metadata, fingerprint):
        return owner == 'lighttry'
    def submit(self, folder, request):
        super().submit(folder, request)
        self.succeed()

if __name__ == '__main__':
    os.umask(0o077)
    app = Application(parser().parse_args())
    app.handler.task_store.executor = Synthetic()
    app.queue.start()
    try:
        print('OFFLINE CONTAINER FIXTURE; NO GPU OR PROVIDER', flush=True)
        serve(app, listen='0.0.0.0:8080', threads=4)
    finally:
        app.close()
