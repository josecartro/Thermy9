"""Local web editor. Standard-library HTTP, Linux rendering, native BLE printing."""
import argparse
import base64
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import threading
import time
import webbrowser

from editor_presets import DEFAULTS, read_presets, save_preset
from render_bridge import render_job
from printer_ble import send_raster, status
from discovery import discover

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / 'web'


class App:
    def __init__(self):
        self.token = secrets.token_urlsafe(32)
        self.jobs = OrderedDict()
        self.jobs_lock = threading.Lock()
        self.hardware = threading.Lock()
        self.renderer = threading.Semaphore(1)

    def preview(self, data):
        kind = data['kind']
        with self.renderer:
            if kind == 'image':
                image = base64.b64decode(data['image'], validate=True)
                if len(image) > 20 * 1024 * 1024:
                    raise ValueError('Choose an image smaller than 20 MB.')
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / 'image'
                    path.write_bytes(image)
                    meta, raster = render_job(kind, str(path), data.get('mode', 'sticker'), data.get('settings'))
            else:
                meta, raster = render_job(kind, data['content'], settings=data.get('settings'))
        job = secrets.token_urlsafe(24)
        with self.jobs_lock:
            self.jobs[job] = (time.monotonic(), raster)
            while len(self.jobs) > 12:
                self.jobs.popitem(last=False)
        return dict(job=job, **meta)

    def print_once(self, data):
        address = data.get('address', '').strip()
        if not address:
            raise ValueError('Choose a printer first.')
        if not self.hardware.acquire(blocking=False):
            raise ValueError('The printer is busy. Wait for the current operation.')
        try:
            with self.jobs_lock:
                job = self.jobs.pop(data.get('job'), None)
            if job is None or time.monotonic() - job[0] > 3600:
                raise ValueError('This preview has expired or was already sent. Refresh it before printing.')
            try:
                send_raster(address, job[1], allow_paper_use=True)
            except Exception as exc:
                raise RuntimeError(f'Print stopped: {exc}. Check for a partial print before trying again.') from exc
            return dict(message='One copy sent. Check the paper before printing another.')
        finally:
            self.hardware.release()

    def query(self, action):
        if not self.hardware.acquire(blocking=False):
            raise ValueError('The printer is busy.')
        try:
            return action()
        finally:
            self.hardware.release()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, code, value, mime='application/json'):
        body = json.dumps(value).encode() if mime == 'application/json' else value
        self.send_response(code)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        self.wfile.write(body)

    def valid_host(self):
        return self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}'

    def do_GET(self):
        if not self.valid_host():
            return self.reply(403, {'error': 'Invalid host'})
        files = {'/': ('index.html', 'text/html; charset=utf-8'), '/app.js': ('app.js', 'text/javascript'), '/style.css': ('style.css', 'text/css')}
        if self.path not in files:
            return self.reply(404, {'error': 'Not found'})
        filename, mime = files[self.path]
        body = (WEB / filename).read_bytes()
        if self.path == '/':
            body = body.replace(b'__TOKEN__', self.server.app.token.encode())
        self.reply(200, body, mime)

    def do_POST(self):
        origin = self.headers.get('Origin')
        if (not self.valid_host() or self.headers.get('X-Thermy9-Token') != self.server.app.token
                or origin not in (None, f'http://127.0.0.1:{self.server.server_port}')):
            return self.reply(403, {'error': 'Open the editor from Start Thermy9.cmd.'})
        try:
            length = int(self.headers.get('Content-Length', 0))
            if not 0 < length <= 29 * 1024 * 1024:
                raise ValueError('Request too large or empty.')
            data = json.loads(self.rfile.read(length))
            app = self.server.app
            if self.path == '/api/init':
                address = ''
                try:
                    address = json.loads((ROOT / 'config/paperang.json').read_text()).get('macaddress', '')
                except (OSError, ValueError):
                    pass
                warning = ''
                try:
                    personal = read_presets()
                except (OSError, ValueError) as exc:
                    personal, warning = {}, f'Could not load personal presets: {exc}'
                result = dict(defaults=DEFAULTS, personal=personal, address=address, warning=warning)
            elif self.path == '/api/preview':
                result = app.preview(data)
            elif self.path == '/api/print':
                result = app.print_once(data)
            elif self.path == '/api/preset':
                save_preset(data['name'], data['kind'], data['settings'])
                result = dict(personal=read_presets())
            elif self.path == '/api/status':
                if not data.get('address', '').strip():
                    raise ValueError('Enter a printer address first.')
                result = app.query(lambda: status(data['address']))
            elif self.path == '/api/discover':
                result = dict(devices=app.query(discover))
            else:
                return self.reply(404, {'error': 'Not found'})
            self.reply(200, result)
        except Exception as exc:
            self.reply(400, {'error': str(exc) or type(exc).__name__})


def open_window(url):
    for directory in (os.environ.get('PROGRAMFILES(X86)', ''), os.environ.get('PROGRAMFILES', '')):
        edge = Path(directory) / 'Microsoft/Edge/Application/msedge.exe'
        if edge.is_file():
            subprocess.Popen([str(edge), '--app=' + url, '--window-size=1500,960'])
            return
    webbrowser.open(url)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--no-open', action='store_true')
    parser.add_argument('--port', type=int, default=0)
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    server.daemon_threads = True
    server.app = App()
    url = f'http://127.0.0.1:{server.server_port}'
    print(url, flush=True)
    if not args.no_open:
        open_window(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
