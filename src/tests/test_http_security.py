import functools
import http.client
import json
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from flask import Flask, request
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
            ([('Transfer-Encoding', 'gzip')], 400),
            ([('Transfer-Encoding', 'chunked, chunked')], 400),
            ([('Transfer-Encoding', 'chunked'), ('Transfer-Encoding', 'chunked')], 400),
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

    def chunked_request(self, path, method, body, extra_headers=()):
        conn = http.client.HTTPConnection(*self.server.server_address, timeout=3)
        try:
            conn.putrequest(method, path)
            conn.putheader('Transfer-Encoding', 'chunked')
            for name, value in extra_headers:
                conn.putheader(name, value)
            conn.endheaders(body)
            # Allow incomplete bodies to reach EOF rather than waiting for a timeout.
            conn.sock.shutdown(socket.SHUT_WR)
            response = conn.getresponse()
            return response.status, response.read()
        finally:
            conn.close()

    def test_empty_chunked_visit_count_and_page_reads(self):
        with patch.object(main, 'get_total_visits', return_value=12345):
            status, body = self.chunked_request('/visit-count', 'GET', b'0\r\n\r\n')
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['data']['total_visits'], 12345)
        for method in ('GET', 'HEAD'):
            status, body = self.chunked_request('/pages/home/', method, b'0\r\n\r\n')
            self.assertEqual(status, 200)
            self.assertEqual(body, b'fixture' if method == 'GET' else b'')
            status, _ = self.chunked_request('/pages/home/', method, b'1\r\nx\r\n0\r\n\r\n')
            self.assertEqual(status, 400)

    def test_chunked_api_body_is_decoded_before_flask(self):
        app = Flask(__name__)

        @app.route('/api/check-login', methods=['POST', 'DELETE'])
        def echo_body():
            return {
                'body': request.get_data().decode('utf-8'),
                'length': request.content_length,
                'encoding': request.headers.get('Transfer-Encoding'),
                'trailer': request.headers.get('Trailer'),
                'auth': request.headers.get('Authorization'),
            }

        payload = '{"text":"你好"}'.encode('utf-8')
        chunks = [payload[:11], payload[11:]]
        encoded = b''.join(format(len(chunk), 'x').encode() + b';name="value"\r\n' + chunk + b'\r\n'
                           for chunk in chunks)
        encoded += b'0\r\nAuthorization: attacker\r\nContent-Length: 999\r\n\r\n'
        headers = [('Content-Type', 'application/json'), ('Authorization', 'Session legitimate'),
                   ('Trailer', 'Authorization, Content-Length')]
        with patch.object(main, 'FLASK_AVAILABLE', True), \
                patch.object(main, 'message_board', SimpleNamespace(app=app)):
            for method in ('POST', 'DELETE'):
                status, body = self.chunked_request('/api/check-login', method, encoded, headers)
                self.assertEqual(status, 200)
                result = json.loads(body)
                self.assertEqual(result['body'], payload.decode())
                self.assertEqual(result['length'], len(payload))
                self.assertIsNone(result['encoding'])
                self.assertIsNone(result['trailer'])
                self.assertEqual(result['auth'], 'Session legitimate')
            status, body = self.chunked_request('/api/check-login', 'POST', b'0\r\n\r\n')
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)['length'], 0)
            self.assertEqual(json.loads(body)['body'], '')

    def test_chunked_size_limit_and_malformed_bodies(self):
        cases = [
            (b'9\r\n', 413),
            (b'5\r\n12345\r\n4\r\n', 413),
            (b'f' * 1000 + b'\r\n', 413),
            (b'xyz\r\n', 400),
            (b'+1\r\nx\r\n0\r\n\r\n', 400),
            (b'1\nx\n0\n\n', 400),
            (b'2\r\nx', 400),
            (b'1\r\nx!!', 400),
            (b'1\r\nx\r\n', 400),
            (b'0\r\n folded: trailer\r\n\r\n', 400),
        ]
        with patch.object(main.Config, 'MAX_POST_SIZE', 8), \
                patch.object(main.BeautifulDirectoryHandler, '_forward_to_flask') as forward:
            for body, expected in cases:
                with self.subTest(body=body):
                    status, _ = self.chunked_request('/api/check-login', 'POST', body)
                    self.assertEqual(status, expected)
            forward.assert_not_called()

    def test_fixed_length_body_at_size_limit_reaches_flask(self):
        app = Flask(__name__)
        app.add_url_rule('/api/check-login', view_func=lambda: request.get_data(), methods=['POST'])
        with patch.object(main.Config, 'MAX_POST_SIZE', 8), \
                patch.object(main, 'FLASK_AVAILABLE', True), \
                patch.object(main, 'message_board', SimpleNamespace(app=app)):
            conn = http.client.HTTPConnection(*self.server.server_address, timeout=3)
            try:
                conn.request('POST', '/api/check-login', b'12345678')
                response = conn.getresponse()
                self.assertEqual(response.status, 200)
                self.assertEqual(response.read(), b'12345678')
            finally:
                conn.close()
            status, body = self.chunked_request('/api/check-login', 'POST', b'8\r\n12345678\r\n0\r\n\r\n')
            self.assertEqual(status, 200)
            self.assertEqual(body, b'12345678')

    def test_chunked_read_timeout_does_not_dispatch(self):
        with patch.object(main, 'read_chunked_body', side_effect=socket.timeout), \
                patch.object(main.BeautifulDirectoryHandler, '_forward_to_flask') as forward:
            status, _ = self.chunked_request('/api/check-login', 'POST', b'0\r\n\r\n')
            self.assertEqual(status, 408)
            forward.assert_not_called()

    def test_incomplete_fixed_length_body_does_not_dispatch_to_flask(self):
        conn = http.client.HTTPConnection(*self.server.server_address, timeout=3)
        with patch.object(main, 'FLASK_AVAILABLE', True), \
                patch.object(main, 'message_board') as board:
            try:
                conn.putrequest('POST', '/api/check-login')
                conn.putheader('Content-Length', '10')
                conn.endheaders(b'short')
                conn.sock.shutdown(socket.SHUT_WR)
                response = conn.getresponse()
                self.assertEqual(response.status, 400)
                response.read()
                board.app.test_client.assert_not_called()
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
