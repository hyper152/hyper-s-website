"""hyper 的数据库只读浏览接口。身份来自服务端会话，不接受客户端角色。"""
import json
import sqlite3
from contextlib import contextmanager

from src.storage import get_store

TABLES = {
    'messages': '留言', 'visits': '访问记录', 'users': '用户',
    'sessions': '登录会话', 'ai_questions': 'AI 问答',
    'counters': '计数器', 'metadata': '数据库元数据',
}
SECRET_FIELDS = {'password', 'password_hash', 'session_id', 'token', 'secret'}


def is_admin(user):
    if not user or str(user.get('username', '')).strip().lower() != 'hyper':
        return False
    # 绑定原有的第一个 hyper 账号，兼容唯一约束建立前可能存在的同名账号。
    with get_store().connection() as db:
        owner = db.execute(
            "SELECT email FROM users WHERE trim(username) = 'hyper' COLLATE NOCASE ORDER BY rowid LIMIT 1"
        ).fetchone()
    return bool(owner and user.get('email') == owner[0])


@contextmanager
def read_database():
    path = get_store().path
    db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=10)
    db.row_factory = sqlite3.Row
    try:
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        yield db
    finally:
        db.close()


def redact(value):
    if isinstance(value, dict):
        return {key: '[已隐藏]' if key.lower() in SECRET_FIELDS else redact(item)
                for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def overview():
    with read_database() as db:
        tables = []
        for name, label in TABLES.items():
            schema = [dict(row) for row in db.execute(f'PRAGMA table_info("{name}")')]
            count = db.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
            tables.append({'name': name, 'label': label, 'count': count, 'schema': schema})
        ip_counts = db.execute("""
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN coalesce(json_extract(record, '$.ip'), '') != '' THEN 1 ELSE 0 END) AS recorded,
                   SUM(CASE WHEN json_extract(record, '$.ip_backfilled') = 1 THEN 1 ELSE 0 END) AS backfilled
            FROM messages
        """).fetchone()
        return {'database': 'site.db', 'tables': tables,
                'message_ips': {key: value or 0 for key, value in dict(ip_counts).items()}}


def browse(table, page=1, page_size=50, query=''):
    if table not in TABLES:
        raise ValueError('未知数据表')
    if page < 1 or page_size < 1 or page_size > 100 or len(query) > 200:
        raise ValueError('分页或搜索参数无效')
    with read_database() as db:
        columns = [row['name'] for row in db.execute(f'PRAGMA table_info("{table}")')]
        searchable = []
        for column in columns:
            if column.lower() in SECRET_FIELDS:
                continue
            if column == 'record' and table in ('users', 'sessions'):
                paths = ','.join("'$." + key + "'" for key in sorted(SECRET_FIELDS))
                searchable.append(f'json_remove(record,{paths})')
            else:
                searchable.append(f'"{column}"')
        if table == 'ai_questions':
            # 按实际内容搜索，避免 JSON 转义的引号、换行影响回答检索。
            searchable.extend(f"json_extract(record, '$.{field}')"
                              for field in ('answer', 'thinking', 'model', 'conversation_id'))
        where, params = '', []
        if query:
            escaped = query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
            where = ' WHERE ' + ' OR '.join(f"CAST({column} AS TEXT) LIKE ? ESCAPE '\\'" for column in searchable)
            params = ['%' + escaped + '%'] * len(searchable)
        total = db.execute(f'SELECT COUNT(*) FROM "{table}"' + where, params).fetchone()[0]
        pages = max(1, (total + page_size - 1) // page_size)
        page = min(page, pages)
        order = {'messages': 'create_time DESC, row_id DESC',
                 'visits': 'time DESC, row_id DESC', 'ai_questions': 'time DESC, row_id DESC'}.get(table, 'rowid DESC')
        rows = []
        for raw in db.execute(f'SELECT * FROM "{table}"' + where + f' ORDER BY {order} LIMIT ? OFFSET ?',
                              [*params, page_size, (page - 1) * page_size]):
            row = dict(raw)
            if 'record' in row:
                row['record'] = json.loads(row['record'])
            rows.append(redact(row))
        return {'table': table, 'label': TABLES[table], 'columns': columns, 'rows': rows,
                'total': total, 'page': page, 'pages': pages, 'page_size': page_size, 'query': query}
