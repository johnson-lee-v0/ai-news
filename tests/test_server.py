from http.server import ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import json
from unittest.mock import patch

from pulse.server import make_handler, refresh
from pulse import storage


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.db = Path(cls.tmp.name) / 'pulse.sqlite3'
        storage.initialize(cls.db)
        cls.httpd = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(cls.db))
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = 'http://127.0.0.1:%s' % cls.httpd.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join()
        cls.tmp.cleanup()

    def fetch(self, path, data=None, headers=None):
        request = urllib.request.Request(self.base + path, data=data, headers=headers or {})
        return urllib.request.urlopen(request, timeout=5)

    def test_dashboard_empty_and_health(self):
        with self.fetch('/api/dashboard') as response:
            body = json.load(response)
            self.assertEqual(body['articles'], [])
            self.assertEqual(body['leads'], [])
            self.assertIn('frame-ancestors', response.headers['Content-Security-Policy'])
        with self.fetch('/api/health') as response:
            self.assertEqual(json.load(response)['status'], 'ok')

    def test_cannot_expose_files_or_different_host(self):
        for path in ('/../pulse/server.py', '/data/pulse.sqlite3'):
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.fetch(path)
            self.assertEqual(error.exception.code, 404)
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.fetch('/api/dashboard', headers={'Host':'evil.example'})
        self.assertEqual(error.exception.code, 403)

    def test_cross_origin_and_nonjson_writes_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.fetch('/api/leads', b'{}', {'Content-Type':'application/json','Origin':'https://evil.example'})
        self.assertEqual(error.exception.code, 403)
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.fetch('/api/leads', b'{}', {'Content-Type':'text/plain'})
        self.assertEqual(error.exception.code, 415)

    def test_invalid_lead_returns_actionable_error(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.fetch('/api/leads', b'{"url":"https://example.com"}', {'Content-Type':'application/json'})
        self.assertEqual(error.exception.code, 400)
        self.assertIn('post URL', json.load(error.exception)['error'])


class SnapshotTests(unittest.TestCase):
    def test_refresh_saves_daily_receipt_without_network(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / 'pulse.sqlite3'
            with patch('pulse.server.ingest.refresh', return_value={'new_count':0,'error_count':0}):
                refresh(db)
            files = list(Path(temp).glob('daily/*/*.json'))
            self.assertEqual(len(files), 1)
            self.assertEqual(json.loads(files[0].read_text())['articles'], [])


if __name__ == '__main__':
    unittest.main()
