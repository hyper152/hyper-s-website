"""网站停写后执行：python -m src.migrate_data。重复执行不会再次导入。"""
import argparse
import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path
from .storage import Store, DEFAULT_DB, LEGACY, encode


def migrate(data_dir, db_path):
    data_dir = Path(data_dir).resolve()
    store = Store(db_path)
    with store.connection() as db:
        previous = db.execute("SELECT value FROM metadata WHERE key='json_migration_v1'").fetchone()
        if previous:
            return {'already_migrated': True, **json.loads(previous[0])}
    payload, hashes = {}, {}
    for name in LEGACY:
        path = data_dir / (name + '.json')
        raw = path.read_bytes() if path.exists() else None
        value = json.loads(raw.decode('utf-8-sig')) if raw is not None else ({} if name in ('users', 'sessions', 'visit_count') else [])
        expected = dict if name in ('users', 'sessions', 'visit_count') else list
        if not isinstance(value, expected):
            raise ValueError(f'{name}.json 数据结构不正确，停止迁移')
        if name != 'visit_count' and any(not isinstance(row, dict) for row in (value.values() if isinstance(value, dict) else value)):
            raise ValueError(f'{name}.json 含无效记录，停止迁移')
        payload[name] = value
        if raw is not None:
            hashes[name] = hashlib.sha256(raw).hexdigest()
    if not hashes:
        raise RuntimeError('没有找到旧 JSON 文件，拒绝执行空迁移；恢复时请指定备份目录')
    backup = data_dir / 'backups' / datetime.now().strftime('json-before-sqlite-%Y%m%d-%H%M%S-%f')
    backup.mkdir(parents=True)
    for name, checksum in hashes.items():
        target = backup / (name + '.json')
        shutil.copy2(data_dir / target.name, target)
        if hashlib.sha256(target.read_bytes()).hexdigest() != checksum:
            raise RuntimeError('备份期间原始文件发生变化，请停止网站再迁移')
    counts = {name: len(value) for name, value in payload.items() if name != 'visit_count'}
    report = {'backup': str(backup), 'counts': counts, 'sha256': hashes}
    with store.connection(write=True) as db:
        if db.execute("SELECT 1 FROM metadata WHERE key='json_migration_v1'").fetchone():
            raise RuntimeError('另一个迁移进程已完成，请重新检查')
        for table in ('users', 'sessions', 'messages', 'visits', 'ai_questions', 'counters'):
            if db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]:
                raise RuntimeError(f'{table} 已有数据，拒绝覆盖')
        for email, user in payload['users'].items():
            db.execute('INSERT INTO users VALUES (?,?,?,?)', (email, user.get('username'), user.get('password'), encode(user)))
        for key, session in payload['sessions'].items():
            db.execute('INSERT INTO sessions VALUES (?,?,?,?)', (key, session.get('email'), session.get('expire_time'), encode(session)))
        for name, table in [('messages', 'messages'), ('visitor', 'visits'), ('ai', 'ai_questions')]:
            for row in payload[name]:
                store._insert_record(db, table, row)
        db.execute("INSERT INTO counters VALUES ('visits',?)", (encode(payload['visit_count']),))
        if store.export(db) != payload:
            raise RuntimeError('逐条校验失败，回滚迁移')
        for name, checksum in hashes.items():
            if hashlib.sha256((data_dir / (name + '.json')).read_bytes()).hexdigest() != checksum:
                raise RuntimeError('迁移期间原始数据发生变化，回滚迁移')
        db.execute("INSERT INTO metadata VALUES ('json_migration_v1',?)", (encode(report),))
    (backup / 'manifest.json').write_text(encode(report), encoding='utf-8')
    with store.connection() as db:
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise RuntimeError('SQLite 完整性检查失败')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', default=str(DEFAULT_DB.parent))
    parser.add_argument('--db-path', default=str(DEFAULT_DB))
    args = parser.parse_args()
    print(json.dumps(migrate(args.data_dir, args.db_path), ensure_ascii=False, indent=2))
