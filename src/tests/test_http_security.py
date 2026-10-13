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
                     'pages/list/.env', 'pages/list/secret.key', 'pages/list/server.log',
                     'pages/list/web.config', 'pages/list/backup.sql', 'pages/list/test.cgi',
                     'pages/list/config.ini', 'pages/list/data.pdf']:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('fixture', encoding='utf-8')
        # Exercise production routing without recording test traffic in site.db.
        self.guard = patch.object(main.BeautifulDirectoryHandler, 'handle_one_request',
                                  BaseHTTPRequestHandler.handle_one_request)
        self.guard.start()
        self.warning_guard = patch.object(main.logger, 'warning')
        self.warning_guard.start()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(
            main.BeautifulDirectoryHandler, directory=str(self.root)))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.guard.stop()
        self.warning_guard.stop()
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
                 '/.git/HEAD?download=1', '/static/../src/secret.py',
                 '/home/%2e%2e/.env', '/pages/list/server.log', '/pages/list/web.config',
                 '/pages/list/backup.sql', '/pages/list/config.ini', '/pages/list/test.cgi',
                 '/pages/NUL.txt', '/pages/home/index.html%00', '/pages//home/index.html',
                 '/pages/home/index.html%3fsecret', '/pages/home/index.html%7f']
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
        status, body = self.request('/pages/list/?q=%3Cscript%3Ealert(1)%3C/script%3E')
        self.assertEqual(status, 200)
        self.assertIn(b'visible.html', body)
        self.assertNotIn(b'.env', body)
        self.assertNotIn(b'secret.key', body)
        self.assertNotIn(b'server.log', body)
        self.assertNotIn(b'web.config', body)
        self.assertNotIn(b'backup.sql', body)
        self.assertNotIn(b'test.cgi', body)
        self.assertNotIn(b'alert(1)', body)
        self.assertIn(b'data.pdf', body)

    def test_unsupported_methods_and_writes_to_static_files(self):
        for method in ('PUT', 'PATCH', 'TRACE', 'CONNECT', 'OPTIONS', 'POST', 'DELETE'):
            with self.subTest(method=method):
                self.assertEqual(405, self.request('/pages/home/index.html', method)[0])

    def test_rejects_ambiguous_and_oversized_request_bodies(self):
        cases = [
            ([('Content-Length', '-1')], 400),
            ([('Content-Length', 'invalid')], 400),
            ([('Content-Length', '1'), ('Content-Length', '1')], 400),
            ([('Transfer-Encoding', 'chunked')], 400),
            ([('Transfer-Encoding', 'chunked'), ('Content-Length', '1')], 400),
            ([('Content-Length', str(main.Config.MAX_POST_SIZE + 1))], 413),
            ([('Content-Length', '9' * 5000)], 413),
        ]
        for headers, expected in cases:
            with self.subTest(headers=headers[0][0], expected=expected):
                conn = http.client.HTTPConnection(*self.server.server_address, timeout=3)
                try:
                    conn.putrequest('POST', '/api/check-login')
                    for name, value in headers:
                        conn.putheader(name, value)
                    conn.endheaders()
                    response = conn.getresponse()
                    self.assertEqual(expected, response.status)
                    response.read()
                finally:
                    conn.close()

    def test_static_requests_do_not_enter_logs_visits_or_frequency_counts(self):
        # Run the real accounting wrapper with all storage/network effects mocked.
        self.guard.stop()
        main.BeautifulDirectoryHandler.ip_request_cache.clear()
        logged = threading.Event()
        with patch.object(main, 'AUTH_AVAILABLE', False), \
             patch.object(main, 'query_ip_city', return_value='test'), \
             patch.object(main, 'count_visit', return_value=1) as counter, \
             patch.object(main.VisitorManager, 'add_record') as records, \
             patch.object(main.logger, 'handle', side_effect=lambda record: logged.set()) as log:
            for path in ('/static/home.css?v=123', '/media/photo.webp?download=1',
                         '/pages/list/data.pdf?cache=123'):
                self.assertEqual(200, self.request(path)[0])
            counter.assert_not_called()
            records.assert_not_called()
            log.assert_not_called()
            self.assertFalse(main.BeautifulDirectoryHandler.ip_request_cache)
            self.assertEqual(200, self.request('/pages/home/?token=secret')[0])
            self.assertTrue(logged.wait(3), 'Page accounting must complete after the response')
            self.assertEqual('/pages/home/', records.call_args.args[0]['path'])
            self.assertEqual(1, counter.call_count)
            self.assertEqual(1, len(main.BeautifulDirectoryHandler.ip_request_cache['127.0.0.1']))
            self.assertEqual(1, log.call_count)
            self.assertNotIn('token=secret', log.call_args.args[0].msg)
        self.guard.start()

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
