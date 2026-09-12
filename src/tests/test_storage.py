import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from src.storage import Store, LEGACY, get_store
from src.migrate_data import migrate


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = self.root / 'site.db'
        self.env = patch.dict(os.environ, SITE_DB_PATH=str(self.db))
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def write_legacy(self):
        from src.auth import hash_password
        self.payload = {
            'users': {'test@example.invalid': {'email': 'test@example.invalid', 'username': '测试用户', 'password': hash_password('test-password'), 'extra': [1, '保留']}},
            'sessions': {'original-token': {'email': 'test@example.invalid', 'expire_time': time.time()+3600, 'login_time': '2026-01-01'}},
            'messages': [{'id': '1', 'content': '你好', 'create_time': 1}, {'id': '1', 'content': '历史重复 ID 也保留', 'create_time': 2}],
            'visitor': [{'path': '/中文/', 'ip': '127.0.0.1', 'status': 200, 'extra': {'x': 1}}],
            'ai': [{'question': '问题\n第二行', 'user': '游客'}],
            'visit_count': {'count': 123, 'total_visits': 123, 'update_time': '原始时间'},
        }
        for name in LEGACY:
            (self.root / (name + '.json')).write_text(json.dumps(self.payload[name], ensure_ascii=False), encoding='utf-8')

    def test_migration_is_lossless_backed_up_and_idempotent(self):
        self.write_legacy()
        report = migrate(self.root, self.db)
        self.assertEqual(Store(self.db).export(), self.payload)
        for name in LEGACY:
            self.assertEqual((Path(report['backup']) / (name+'.json')).read_bytes(), (self.root / (name+'.json')).read_bytes())
        self.assertTrue(migrate(self.root, self.db)['already_migrated'])
        self.assertEqual(Store(self.db).counter(), 123)

    def test_invalid_json_is_not_silently_discarded(self):
        self.write_legacy()
        (self.root / 'visitor.json').write_text('[broken', encoding='utf-8')
        with self.assertRaises(ValueError):
            migrate(self.root, self.db)
        self.assertEqual(Store(self.db).count_visits(), 0)

    def test_import_failure_rolls_back_all_tables(self):
        self.write_legacy()
        (self.root / 'visitor.json').write_text('[{"status": {"invalid": true}}]', encoding='utf-8')
        with self.assertRaises(Exception):
            migrate(self.root, self.db)
        self.assertEqual(Store(self.db).users(), {})
        with Store(self.db).connection() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM metadata').fetchone()[0], 0)

    def test_concurrent_counter_and_appends_have_no_lost_updates(self):
        store = Store(self.db)
        def write(i):
            store.counter(increment=True)
            store.append('visits', {'path': f'/{i}'})
            store.append('messages', {'id': str(i), 'content': str(i)})
            store.append('ai_questions', {'question': str(i)})
            return store.create_user('same@example.invalid', {'username': str(i)})
        with ThreadPoolExecutor(max_workers=8) as executor:
            created = list(executor.map(write, range(80)))
        self.assertEqual(store.counter(), 80)
        self.assertEqual(store.count_visits(), 80)
        self.assertEqual(len(store.records('messages')), 80)
        self.assertEqual(len(store.records('ai_questions')), 80)
        self.assertEqual(sum(created), 1)

    def test_login_sessions_message_and_ai_routes(self):
        self.write_legacy()
        migrate(self.root, self.db)
        from src import auth, message_board, ollama
        self.assertTrue(auth.check_login_status('original-token'))
        self.assertEqual(auth.get_current_user('original-token')['username'], '测试用户')
        client = message_board.app.test_client()
        result = client.post('/api/login/password', json={'email': 'test@example.invalid', 'password': 'test-password'}).get_json()
        self.assertEqual(result['code'], 200)
        self.assertTrue(auth.check_login_status(result['data']['session_id']))
        self.assertEqual(client.post('/api/talk/add', json={'content': '迁移后留言'}).get_json()['code'], 200)
        self.assertEqual(len(client.get('/api/talk/list').get_json()['data']), 3)
        self.assertEqual(client.post('/api/logout').get_json()['code'], 200)
        self.assertFalse(auth.check_login_status(result['data']['session_id']))
        get_store().put_session('expired', {'email': 'test@example.invalid', 'expire_time': 1})
        self.assertFalse(auth.check_login_status('expired'))
        with message_board.app.test_request_context(json={'question': '测试问题'}):
            self.assertEqual(ollama.save_ai_question().get_json()['status'], 'ok')
        self.assertEqual(len(get_store().records('ai_questions')), 2)

    def test_private_paths_get_and_head_use_same_guard(self):
        import main
        handler = object.__new__(main.BeautifulDirectoryHandler)
        handler.directory = str(Path(main.__file__).parent)
        for path in ['/data/site.db', '/data/site.db-wal', '/data/backups/test/users.json',
                     '/%64ata/site.db', '/DATA/site.db?download=1', '/pages/../data/site.db', '/data']:
            handler.path = path
            self.assertTrue(handler.is_protected_path(path), path)
            handler.send_error = lambda code, message: self.assertEqual(code, 403)
            self.assertIsNone(handler.send_head())
        self.assertFalse(handler.is_protected_path('/pages/home/index.html'))


if __name__ == '__main__':
    unittest.main()
