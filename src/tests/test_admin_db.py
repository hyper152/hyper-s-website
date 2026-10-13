import functools
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import main
from src.storage import Store
from src.admin_db import browse, is_admin


class AdminTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, SITE_DB_PATH=str(self.root / 'site.db'))
        self.env.start()
        self.store = Store(self.root / 'site.db')
        for email, name, token in [('owner@example.invalid', 'hyper', 'owner-token'),
                                   ('user@example.invalid', 'visitor', 'user-token'),
                                   ('duplicate@example.invalid', 'pretender', 'duplicate-token')]:
            self.store.create_user(email, {'username': name, 'password': 'password-hidden',
                                           'session_id': 'nested-session-secret'})
            self.store.put_session(token, {'email': email, 'expire_time': time.time() + 3600})
        for i in range(5):
            self.store.append('messages', {'id': str(i), 'content': '100%_' if i == 0 else f'留言 {i}',
                                          'create_time': i, 'ip': '198.51.100.20'})
        page = self.root / 'pages/admin/index.html'
        page.parent.mkdir(parents=True)
        page.write_text('admin-fixture')
        self.guard = patch.object(main.BeautifulDirectoryHandler, 'handle_one_request', BaseHTTPRequestHandler.handle_one_request)
        self.guard.start()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(main.BeautifulDirectoryHandler, directory=str(self.root)))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.guard.stop()
        self.env.stop()
        self.temp.cleanup()

    def request(self, path, token=None, method='GET', payload=None, headers=None):
        headers = dict(headers or {})
        if token:
            headers['Authorization'] = 'Session ' + token
        body = None
        if payload is not None:
            body = json.dumps(payload)
            headers['Content-Type'] = 'application/json'
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=10)
        connection.request(method, path, body, headers)
        response = connection.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return result

    def test_only_original_hyper_account_can_read_api_and_page(self):
        self.assertFalse(is_admin({'username': 'hyper', 'email': 'duplicate@example.invalid'}))
        for token, status in [(None, 401), ('expired-token', 401), ('user-token', 403), ('duplicate-token', 403)]:
            for method in ('GET', 'HEAD', 'POST', 'DELETE'):
                with self.subTest(token=token, method=method):
                    result = self.request('/api/admin/tables', token, method)
                    self.assertEqual(result[0], status)
                    self.assertNotIn(b'password-hidden', result[2])
            page_status = self.request('/pages/admin/', token)[0]
            self.assertEqual(page_status, 302 if status == 401 else 403)
        self.assertEqual(self.request('/pages/admin/', 'owner-token')[0], 200)
        self.assertEqual(self.request('/pages/admin/', 'owner-token', 'HEAD')[0], 200)
        response = self.request('/api/admin/tables', 'owner-token')
        self.assertEqual(response[0], 200)
        self.assertEqual(response[1]['Cache-Control'], 'no-store')
        self.assertEqual(len(json.loads(response[2])['tables']), 7)
        for method in ('POST', 'DELETE'):
            self.assertEqual(self.request('/api/admin/rows', 'owner-token', method)[0], 405)

    def test_pagination_literal_search_redaction_and_bad_parameters(self):
        response = self.request('/api/admin/rows?table=messages&page=2&page_size=2', 'owner-token')
        self.assertEqual(response[0], 200)
        data = json.loads(response[2])
        self.assertEqual([row['record']['create_time'] for row in data['rows']], [2, 1])
        self.assertEqual((data['total'], data['pages']), (5, 3))
        self.assertEqual(browse('messages', query='100%_')['total'], 1)
        for table in ('users', 'sessions'):
            body = self.request('/api/admin/rows?table=' + table, 'owner-token')[2]
            for secret in (b'password-hidden', b'owner-token', b'nested-session-secret'):
                self.assertNotIn(secret, body)
        self.assertEqual(browse('users', query='password-hidden')['total'], 0)
        for params in ('table=unknown', 'page=0', 'page_size=101', 'page=abc', 'table=users%3BDROP%20TABLE%20users'):
            self.assertEqual(self.request('/api/admin/rows?' + params, 'owner-token')[0], 400)
        self.assertEqual(len(self.store.users()), 3)

    def test_message_stores_forwarded_ip_and_public_list_omits_it(self):
        result = self.request('/api/talk/add', 'owner-token', 'POST',
                              {'content': '新留言', 'ip': '1.1.1.1'}, {'X-Forwarded-For': '2409:8a2b::1, 127.0.0.1'})
        self.assertEqual(json.loads(result[2])['code'], 200)
        message = self.store.records('messages')[-1]
        self.assertEqual(message['ip'], '2409:8a2b::1')
        self.assertEqual(message['ip_source'], 'request')
        public = json.loads(self.request('/api/talk/list')[2])['data']
        self.assertTrue(all('ip' not in item and 'ip_source' not in item for item in public))
        check = self.request('/api/check-login', 'owner-token', 'POST', {})
        self.assertTrue(json.loads(check[2])['can_admin'])
        check = self.request('/api/check-login', 'duplicate-token', 'POST', {})
        self.assertFalse(json.loads(check[2])['can_admin'])

    def test_registration_rejects_duplicate_names_in_both_entry_points(self):
        from src import auth, message_board
        for username in ('hyper', 'HYPER', '  Hyper  '):
            response = self.request('/api/register', method='POST', payload={
                'username': username, 'email': 'new@example.invalid', 'password': 'test-password', 'code': '123456'})
            result = json.loads(response[2])
            self.assertEqual(result['code'], 400)
            self.assertIn('用户名已被使用', result['msg'])
            self.assertIn('用户名已被使用', auth.register(username, 'new@example.invalid', 'test-password')['msg'])
        self.assertEqual(len(self.store.users()), 3)
        email = 'new@example.invalid'
        message_board.VERIFY_CACHE[email] = {'type': 'register', 'code': '123456', 'expire': time.time() + 300}
        response = self.request('/api/register', method='POST', payload={
            'username': '  unique  ', 'email': email, 'password': 'test-password', 'code': '123456'})
        self.assertEqual(json.loads(response[2])['code'], 200)
        self.assertEqual(self.store.user(email)['username'], 'unique')

    def test_chat_proxy_saves_full_answer_and_real_client_identity(self):
        from src import ollama
        from unittest.mock import Mock
        upstream = Mock()
        upstream.iter_content.return_value = [b'{"message":{"role":"assistant","content":"complete answer"},"done":true}\n']
        with patch.object(ollama.requests, 'post', return_value=upstream):
            response = self.request('/api/ollama/chat', 'owner-token', 'POST',
                                    {'model': 'test-model', 'messages': [{'role': 'user', 'content': 'full question'}], 'stream': True},
                                    {'X-Forwarded-For': '2409:8a2b::1'})
        self.assertEqual(response[0], 200)
        records = self.store.records('ai_questions')
        self.assertEqual(len(records), 1)
        self.assertEqual((records[0]['question'], records[0]['answer']), ('full question', 'complete answer'))
        self.assertEqual((records[0]['user'], records[0]['ip']), ('hyper', '2409:8a2b::1'))
