"""Run only the renderer in Linux. No network, host mounts or printer access."""
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import uuid

IMAGE = 'thermy9-render:local'


def render_job(kind, content, mode='sticker', settings=None):
    if kind not in ('paragraph', 'image', 'cable') or not content.strip():
        raise ValueError('Enter text or choose an image first.')
    request = dict(kind=kind, mode=mode, settings=settings or {})
    if kind == 'image':
        path = Path(content)
        if path.stat().st_size > 20 * 1024 * 1024:
            raise ValueError('Choose an image smaller than 20 MB.')
        request['image'] = base64.b64encode(path.read_bytes()).decode('ascii')
    else:
        if len(content) > 10000:
            raise ValueError('This note is too long; use at most 10,000 characters.')
        request['text'] = content
    name = 'thermy9-render-' + uuid.uuid4().hex
    command = ['docker', 'run', '--rm', '-i', '--name', name, '--network=none',
               '--read-only', '--cap-drop=ALL', '--security-opt=no-new-privileges',
               '--memory=1g', '--cpus=2', '--pids-limit=64',
               '--tmpfs', '/tmp:rw,noexec,nosuid,size=64m', IMAGE]
    try:
        process = subprocess.run(command, input=json.dumps(request), capture_output=True,
                                 text=True, encoding='utf-8', timeout=90,
                                 creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except FileNotFoundError as exc:
        raise RuntimeError('Docker Desktop is required for rendering. Start Docker and try again.') from exc
    except subprocess.TimeoutExpired as exc:
        subprocess.run(['docker', 'rm', '-f', name], capture_output=True, timeout=15,
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        raise RuntimeError('Rendering timed out. No print was sent.') from exc
    if process.returncode:
        raise RuntimeError('Rendering failed (no print sent): ' + (process.stdout or process.stderr).strip())
    payload = json.loads(process.stdout)
    if payload.get('status') != 'ok':
        raise RuntimeError(payload.get('message', 'Renderer failed'))
    result = payload['result']
    raster = base64.b64decode(result.pop('raster'), validate=True)
    if result['width'] != 576 or not 0 < result['height'] <= 12000 or len(raster) != result['height'] * 72:
        raise RuntimeError('Renderer returned invalid dimensions')
    result.update(bytes_prepared=len(raster), sha256=hashlib.sha256(raster).hexdigest(),
                  feed_rows=result.get('trailing_rows', 0), paper_used=False, renderer='Docker/Linux')
    return result, raster
