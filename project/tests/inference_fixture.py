"""Independent offline executor double. Never imports/calls the real driver."""
import io
from PIL import Image, ImageDraw
from inference.images import digest
from inference.jobs import atomic


def image_bytes(size=(640, 960), fmt='PNG'):
    image = Image.new('RGB', size, '#788496')
    draw = ImageDraw.Draw(image)
    draw.rectangle((size[0] // 4, size[1] // 4, size[0] * 3 // 4, size[1] * 3 // 4), fill='#eab77e')
    draw.line((0, 0, size[0] - 1, size[1] - 1), fill='white', width=4)
    out = io.BytesIO(); image.save(out, format=fmt)
    return out.getvalue()


class OfflineExecutor:
    """Tests explicitly drive the events; no time-based pretend GPU progression."""
    def __init__(self):
        self.calls = []

    def submit(self, folder, request):
        self.calls.append((folder, request))

    def event(self, status='running', stage='inverse', stopped=False, index=-1):
        folder, request = self.calls[index]
        atomic(folder / 'execution.json', {'taskId': request['taskId'], 'nonce': request['nonce'],
            'status': status, 'stage': stage, 'executionStopped': stopped})

    def succeed(self, index=-1):
        folder, request = self.calls[index]
        payload = image_bytes((1280, 704), 'JPEG')
        (folder / 'result.jpg').write_bytes(payload)
        receipt = {'taskId': request['taskId'], 'nonce': request['nonce'], 'inputId': request['input']['id'],
            'presetId': request['preset']['id'], 'inputSha256': request['input']['sha256'],
            'originalSha256': request['original']['sha256'], 'runConfig': request['runConfig'],
            'file': 'result.jpg', 'sha256': digest(payload), 'bytes': len(payload), 'processExitCodes': [0, 0]}
        atomic(folder / 'receipt.json', receipt)
        self.event('succeeded', 'validating', True, index)
        return receipt
