import base64
import json
from pathlib import Path
import sys
import threading
import time
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from web_app import App, Handler, ThreadingHTTPServer


class WebAppTests(unittest.TestCase):
    def setUp(self):
        self.app = App()

    def test_print_uses_cached_bytes_and_consumes_job(self):
        self.app.jobs['preview'] = (time.monotonic(), b'exact raster')
        with patch('web_app.send_raster') as send:
            self.app.print_once(dict(job='preview', address='printer'))
            with self.assertRaises(ValueError):
                self.app.print_once(dict(job='preview', address='printer'))
        send.assert_called_once_with('printer', b'exact raster', allow_paper_use=True)

    def test_failed_print_cannot_be_retried_with_same_job(self):
        self.app.jobs['preview'] = (time.monotonic(), b'raster')
        with patch('web_app.send_raster', side_effect=RuntimeError('disconnected')) as send:
            with self.assertRaisesRegex(RuntimeError, 'partial print'):
                self.app.print_once(dict(job='preview', address='printer'))
            with self.assertRaises(ValueError):
                self.app.print_once(dict(job='preview', address='printer'))
            self.assertEqual(send.call_count, 1)
        self.assertFalse(self.app.hardware.locked())

    def test_busy_printer_preserves_unsent_job(self):
        self.app.jobs['preview'] = (time.monotonic(), b'raster')
        self.app.hardware.acquire()
        with self.assertRaisesRegex(ValueError, 'busy'):
            self.app.print_once(dict(job='preview', address='printer'))
        self.assertIn('preview', self.app.jobs)

    def test_image_upload_uses_temporary_file(self):
        def render(kind, filename, mode, settings):
            self.assertEqual(Path(filename).read_bytes(), b'image data')
            self.assertEqual(mode, 'photo')
            return {'height':1}, b'raster'
        with patch('web_app.render_job', side_effect=render) as renderer:
            result = self.app.preview(dict(kind='image', image=base64.b64encode(b'image data').decode(), mode='photo'))
            path = renderer.call_args.args[1]
        self.assertFalse(Path(path).exists())
        self.assertEqual(self.app.jobs[result['job']][1], b'raster')

    def test_loopback_api_rejects_missing_token_and_foreign_origin(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        server.app = self.app
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f'http://127.0.0.1:{server.server_port}'
        try:
            with urlopen(url) as response:
                self.assertIn(self.app.token, response.read().decode())
            for headers in [{}, {'X-Thermy9-Token':self.app.token, 'Origin':'https://other.example'}]:
                with self.assertRaises(HTTPError) as error:
                    urlopen(Request(url + '/api/init', data=b'{}', headers=headers))
                self.assertEqual(error.exception.code, 403)
            request = Request(url + '/api/init', data=b'{}', headers={'X-Thermy9-Token':self.app.token})
            with urlopen(request) as response:
                self.assertEqual(len(json.load(response)['defaults']), 2)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == '__main__':
    unittest.main()
