import functools
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import main


class StaticSecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        for name in ['.git/HEAD', '.git/config', '.git/objects/ab/object', '.env',
                     'src/secret.py', 'certs/site.key', 'logs/access.log', 'data/site.db',
                     'main.py', 'private.css', 'pages/.git/HEAD', 'pages/.env',
                     'pages/settings.py', 'pages/home/index.html', 'static/home.css',
                     'media/photo.webp', 'robots.txt', 'pages/list/visible.html',
                     'pages/list/.env', 'pages/list/secret.key']:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('fixture', encoding='utf-8')
        # Exercise production routing without recording test traffic in site.db.
        self.guard = patch.object(main.BeautifulDirectoryHandler, 'handle_one_request',
                                  BaseHTTPRequestHandler.handle_one_request)
        self.guard.start()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(
            main.BeautifulDirectoryHandler, directory=str(self.root)))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.guard.stop()
        self.temp.cleanup()

    def request(self, path, method='GET'):
        conn = http.client.HTTPConnection(*self.server.server_address)
        conn.request(method, path)
        response = conn.getresponse()
        result = response.status, response.read()
        conn.close()
        return result

    def test_sensitive_files_and_bypasses(self):
        paths = ['/.git/HEAD', '/.git/config', '/.git/objects/ab/object', '/.env',
                 '/src/secret.py', '/certs/site.key', '/logs/access.log', '/data/site.db',
                 '/main.py', '/private.css', '/%2egit/HEAD', '/.GIT/HEAD',
                 '/%252egit/HEAD', '/pages/../.git/HEAD', '/pages/%2e%2e/.git/HEAD',
                 '/pages%5c..%5c.git%5cHEAD', '/pages/.git/HEAD', '/pages/.env',
                 '/pages/settings.py', '/pages/home/index.html::$DATA',
                 '/.git/HEAD?download=1', '/static/../src/secret.py']
        for method in ('GET', 'HEAD', 'POST'):
            for path in paths:
                with self.subTest(method=method, path=path):
                    status, body = self.request(path, method)
                    self.assertIn(status, (403, 404))
                    self.assertNotEqual(body, b'fixture')

    def test_public_files_and_redirect(self):
        for method in ('GET', 'HEAD'):
            for path in ('/pages/home/', '/static/home.css', '/media/photo.webp', '/robots.txt'):
                with self.subTest(method=method, path=path):
                    status, body = self.request(path, method)
                    self.assertEqual(status, 200)
                    self.assertEqual(body, b'fixture' if method == 'GET' else b'')
            self.assertEqual(self.request('/', method)[0], 301)

    def test_listing_hides_private_files(self):
        status, body = self.request('/pages/list/')
        self.assertEqual(status, 200)
        self.assertIn(b'visible.html', body)
        self.assertNotIn(b'.env', body)
        self.assertNotIn(b'secret.key', body)

    def test_symlink_escape(self):
        link = self.root / 'pages' / 'leak'
        try:
            link.symlink_to(self.root / '.git', target_is_directory=True)
        except OSError:
            self.skipTest('Symlink creation requires Windows privileges')
        for method in ('GET', 'HEAD'):
            self.assertIn(self.request('/pages/leak/HEAD', method)[0], (403, 404))


if __name__ == '__main__':
    unittest.main()
