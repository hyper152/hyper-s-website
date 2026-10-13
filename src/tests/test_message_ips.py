from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from src.storage import Store
from src.backfill_message_ips import backfill, timestamp


class MessageIPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = Store(self.root / 'data/site.db')
        self.logs = self.root / 'logs'
        self.logs.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def message(self, id, text, **extra):
        self.store.append('messages', dict(id=id, username='hyper', content='原始内容',
                                          create_time_str=text, create_time=timestamp(text), **extra))

    def visit(self, text, ip, **extra):
        self.store.append('visits', dict(time=text, ip=ip, user='hyper', path='/api/talk/add', method='POST', status=200, **extra))

    def test_backfill_backs_up_preserves_records_and_is_idempotent(self):
        self.message('1', '2026-10-01 10:00:00')
        self.message('2', '2026-10-01 11:00:00')
        self.visit('2026-10-01 10:00:01', '198.51.100.10')
        (self.logs / 'access_test.log').write_text('2026-10-01 11:00:01 ⚡ 👤 hyper [2409:8a2b::1] [地点] | POST /api/talk/add | 200 | 10ms\n', encoding='utf-8')
        original = self.store.export()
        self.assertEqual(backfill(self.store, self.logs)['matched'], 2)
        self.assertEqual(self.store.export(), original)
        result = backfill(self.store, self.logs, apply=True)
        self.assertEqual(result['applied'], 2)
        with closing(sqlite3.connect(result['backup'])) as db:
            backed_up = [json.loads(row[0]) for row in db.execute('SELECT record FROM messages ORDER BY row_id')]
        self.assertEqual(backed_up, original['messages'])
        updated = self.store.records('messages')
        self.assertEqual([m['ip'] for m in updated], ['198.51.100.10', '2409:8a2b::1'])
        for old, new in zip(original['messages'], updated):
            self.assertTrue(all(new[key] == value for key, value in old.items()))
            self.assertTrue(new['ip_backfilled'])
        self.assertEqual(backfill(self.store, self.logs, apply=True)['applied'], 0)
        self.assertEqual(self.store.export()['visitor'], original['visitor'])

    def test_conflicts_wrong_user_loopback_failed_and_nearby_messages_are_not_guessed(self):
        self.message('1', '2026-10-01 10:00:00')
        self.visit('2026-10-01 10:00:00', '198.51.100.1')
        self.visit('2026-10-01 10:00:01', '198.51.100.2')
        self.message('2', '2026-10-01 11:00:00')
        self.store.append('visits', {'time': '2026-10-01 11:00:00', 'ip': '198.51.100.1', 'user': 'other', 'path': '/api/talk/add', 'method': 'POST', 'status': 200})
        self.message('3', '2026-10-01 12:00:00')
        self.visit('2026-10-01 12:00:00', '127.0.0.1')
        self.message('4', '2026-10-01 13:00:00')
        self.store.append('visits', {'time': '2026-10-01 13:00:00', 'ip': '198.51.100.1', 'user': 'hyper', 'path': '/api/talk/add', 'method': 'POST', 'status': 500})
        self.message('5', '2026-10-01 14:00:00')
        self.message('6', '2026-10-01 14:00:01')
        self.visit('2026-10-01 14:00:01', '198.51.100.1')
        result = backfill(self.store, self.logs, apply=True)
        self.assertEqual(result['applied'], 0)
        self.assertEqual((result['ambiguous'], result['unmatched']), (3, 3))
        self.assertFalse(any('ip' in message for message in self.store.records('messages')))

    def test_guest_nickname_does_not_need_to_equal_visit_user(self):
        self.message('guest', '2026-10-01 10:00:00', is_guest=True)
        self.store.append('visits', {'time': '2026-10-01 10:00:00', 'ip': '198.51.100.1', 'user': '游客', 'path': '/api/talk/add', 'method': 'POST', 'status': 200})
        self.assertEqual(backfill(self.store, self.logs, apply=True)['applied'], 1)
