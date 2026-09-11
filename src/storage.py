"""SQLite 存储。每次操作使用独立连接，写事务串行化，记录保留原始字段。"""
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from functools import lru_cache
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent.parent / 'data' / 'site.db'
LEGACY = ('users', 'sessions', 'messages', 'visitor', 'ai', 'visit_count')


def encode(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


class Store:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS users (
                    email TEXT PRIMARY KEY, username TEXT, password TEXT, record TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS users_username ON users(username COLLATE NOCASE);
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY, email TEXT, expire_time REAL, record TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS sessions_expiry ON sessions(expire_time);
                CREATE TABLE IF NOT EXISTS messages (
                    row_id INTEGER PRIMARY KEY, message_id TEXT, create_time REAL, record TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS messages_time ON messages(create_time);
                CREATE TABLE IF NOT EXISTS visits (
                    row_id INTEGER PRIMARY KEY, time TEXT, ip TEXT, user TEXT,
                    path TEXT, method TEXT, status INTEGER, record TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS visits_time ON visits(time);
                CREATE INDEX IF NOT EXISTS visits_ip_time ON visits(ip, time);
                CREATE TABLE IF NOT EXISTS ai_questions (
                    row_id INTEGER PRIMARY KEY, time TEXT, user TEXT, ip TEXT,
                    question TEXT, record TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS ai_time ON ai_questions(time);
                CREATE TABLE IF NOT EXISTS counters (key TEXT PRIMARY KEY, record TEXT NOT NULL);
            ''')

    @contextmanager
    def connection(self, write=False):
        db = sqlite3.connect(str(self.path), timeout=30)
        try:
            db.execute('PRAGMA busy_timeout=30000')
            db.execute('PRAGMA synchronous=FULL')
            if write:
                db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def users(self):
        with self.connection() as db:
            return {key: json.loads(value) for key, value in db.execute('SELECT email,record FROM users')}

    def user(self, email):
        with self.connection() as db:
            row = db.execute('SELECT record FROM users WHERE email=?', (email,)).fetchone()
            return json.loads(row[0]) if row else None

    def create_user(self, email, user):
        with self.connection(write=True) as db:
            cursor = db.execute('INSERT OR IGNORE INTO users VALUES (?,?,?,?)',
                                (email, user.get('username'), user.get('password'), encode(user)))
            return cursor.rowcount == 1

    def put_session(self, session_id, session):
        with self.connection(write=True) as db:
            db.execute('INSERT INTO sessions VALUES (?,?,?,?)',
                       (session_id, session.get('email'), session.get('expire_time'), encode(session)))

    def session(self, session_id):
        with self.connection() as db:
            row = db.execute('SELECT record FROM sessions WHERE session_id=?', (session_id,)).fetchone()
            return json.loads(row[0]) if row else None

    def delete_session(self, session_id):
        with self.connection(write=True) as db:
            return db.execute('DELETE FROM sessions WHERE session_id=?', (session_id,)).rowcount > 0

    @staticmethod
    def _insert_record(db, table, item):
        columns = {
            'messages': ('message_id', 'create_time'),
            'visits': ('time', 'ip', 'user', 'path', 'method', 'status'),
            'ai_questions': ('time', 'user', 'ip', 'question'),
        }[table]
        values = [item.get('id' if field == 'message_id' else field) for field in columns]
        db.execute(f"INSERT INTO {table} ({','.join(columns)},record) VALUES ({','.join('?' for _ in range(len(columns)+1))})",
                   (*values, encode(item)))

    def append(self, table, item, max_records=0):
        if not isinstance(item, dict):
            raise ValueError('记录必须是 JSON 对象')
        with self.connection(write=True) as db:
            self._insert_record(db, table, item)
            if table == 'visits' and max_records > 0:
                db.execute('DELETE FROM visits WHERE row_id NOT IN (SELECT row_id FROM visits ORDER BY row_id DESC LIMIT ?)', (max_records,))

    def records(self, table):
        if table not in ('messages', 'visits', 'ai_questions'):
            raise ValueError('未知记录表')
        with self.connection() as db:
            return [json.loads(row[0]) for row in db.execute(f'SELECT record FROM {table} ORDER BY row_id')]

    def count_visits(self):
        with self.connection() as db:
            return db.execute('SELECT COUNT(*) FROM visits').fetchone()[0]

    def counter(self, increment=False, reset=False):
        with self.connection(write=increment or reset) as db:
            row = db.execute("SELECT record FROM counters WHERE key='visits'").fetchone()
            data = json.loads(row[0]) if row else {}
            count = int(data.get('count', data.get('total_visits', 0)) or 0)
            if increment or reset:
                count = 0 if reset else count + 1
                data.update(count=count, total_visits=count,
                            update_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                db.execute("INSERT INTO counters VALUES ('visits',?) ON CONFLICT(key) DO UPDATE SET record=excluded.record", (encode(data),))
            return count

    def export(self, db=None):
        if db is None:
            with self.connection() as connection:
                connection.execute('BEGIN')
                return self.export(connection)
        result = {}
        for table, key in [('users', 'email'), ('sessions', 'session_id')]:
            result[table] = {k: json.loads(v) for k, v in db.execute(f'SELECT {key},record FROM {table}')}
        for name, table in [('messages', 'messages'), ('visitor', 'visits'), ('ai', 'ai_questions')]:
            result[name] = [json.loads(row[0]) for row in db.execute(f'SELECT record FROM {table} ORDER BY row_id')]
        row = db.execute("SELECT record FROM counters WHERE key='visits'").fetchone()
        result['visit_count'] = json.loads(row[0]) if row else {}
        return result


@lru_cache(maxsize=8)
def _store(path):
    store = Store(path)
    with store.connection() as db:
        migrated = db.execute("SELECT 1 FROM metadata WHERE key='json_migration_v1'").fetchone()
    legacy_exists = any((store.path.parent / (name + '.json')).exists() for name in LEGACY)
    backup_exists = any((store.path.parent / 'backups').glob('json-before-sqlite-*/manifest.json'))
    if not migrated and (legacy_exists or backup_exists):
        raise RuntimeError('检测到旧 JSON 数据，请先停止网站并运行 python -m src.migrate_data')
    return store


def get_store():
    return _store(str(Path(os.environ.get('SITE_DB_PATH', str(DEFAULT_DB))).resolve()))
