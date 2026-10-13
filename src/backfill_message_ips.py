"""按提交记录补回留言 IP。默认预览，--apply 先备份再写入，有歧义时保留未知。"""
import argparse
from contextlib import closing
from datetime import datetime
import ipaddress
import json
from pathlib import Path
import re
import sqlite3
from urllib.parse import urlsplit

from src.storage import get_store, encode

WINDOW_SECONDS = 2


def valid_ip(value):
    try:
        address = ipaddress.ip_address(str(value))
        return str(address) if not address.is_loopback and not address.is_unspecified else None
    except ValueError:
        return None


def timestamp(text):
    try:
        return datetime.strptime(text, '%Y-%m-%d %H:%M:%S').timestamp()
    except (ValueError, TypeError):
        return None


def submission_evidence(store, logs):
    evidence = []
    with store.connection() as db:
        for row_id, text, ip, user, path in db.execute(
            "SELECT row_id,time,ip,user,path FROM visits WHERE method='POST' AND status=200 AND path LIKE '/api/talk/add%'"
        ):
            if urlsplit(path).path != '/api/talk/add':
                continue
            when, address = timestamp(text), valid_ip(ip)
            if when is not None and address:
                evidence.append({'time': when, 'ip': address, 'user': user,
                                 'source': 'visit_record', 'reference': str(row_id)})
    # 新访问日志含真实客户端地址；旧的 localhost 代理日志无法恢复访客 IP。
    pattern = re.compile(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*?👤\s*(.*?)\s*\[([^\]]+)\].*?\|\s*POST\s+/api/talk/add(?:\?[^\s|]*)?\s*\|\s*200\s*\|')
    for path in sorted(Path(logs).glob('access*.log')):
        with path.open(encoding='utf-8', errors='replace') as file:
            for number, line in enumerate(file, 1):
                match = pattern.search(line)
                if not match:
                    continue
                text, user, ip = match.groups()
                when, address = timestamp(text), valid_ip(ip)
                if when is not None and address:
                    evidence.append({'time': when, 'ip': address, 'user': user,
                                     'source': 'access_log', 'reference': f'{path.name}:{number}'})
    return evidence


def match_messages(messages, evidence):
    def matches(message, candidate):
        when = timestamp(message.get('create_time_str'))
        if when is None:
            try:
                when = float(message.get('create_time'))
            except (ValueError, TypeError):
                return False
        if abs(when - candidate['time']) > WINDOW_SECONDS:
            return False
        if message.get('is_guest'):
            return candidate['user'] in ('游客', '', None)
        return bool(message.get('username') and message['username'] == candidate['user'])

    proposals, counts = [], {'total': len(messages), 'already_recorded': 0, 'matched': 0, 'ambiguous': 0, 'unmatched': 0}
    for row_id, original, message in messages:
        if message.get('ip'):
            counts['already_recorded'] += 1
            continue
        candidates = [item for item in evidence if matches(message, item)]
        ips = {item['ip'] for item in candidates}
        if len(ips) != 1:
            counts['ambiguous' if ips else 'unmatched'] += 1
            continue
        # 同一提交证据不能用于两个时间靠近的留言，防止猜测关联。
        unique = [item for item in candidates if sum(matches(other, item) for _, _, other in messages) == 1]
        if not unique:
            counts['ambiguous'] += 1
            continue
        item = next((item for item in unique if item['source'] == 'visit_record'), unique[0])
        updated = dict(message, ip=item['ip'], ip_source=item['source'], ip_backfilled=True,
                       ip_evidence={'time': datetime.fromtimestamp(item['time']).strftime('%Y-%m-%d %H:%M:%S'),
                                    'reference': item['reference']})
        proposals.append((row_id, original, updated))
        counts['matched'] += 1
    return proposals, counts


def backfill(store=None, logs=None, apply=False):
    store = store or get_store()
    logs = logs or store.path.parent.parent / 'logs'
    with store.connection() as db:
        messages = [(row_id, raw, json.loads(raw)) for row_id, raw in db.execute('SELECT row_id,record FROM messages')]
    proposals, counts = match_messages(messages, submission_evidence(store, logs))
    counts.update(applied=0, backup=None)
    if apply and proposals:
        backup_dir = store.path.parent / 'backups'
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup = backup_dir / ('message-ip-before-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.db')
        with store.connection(write=True) as db:
            # 使用独立只读连接获取一致的 SQLite 备份；写锁阻止备份后的并发修改。
            with closing(sqlite3.connect(store.path.as_uri() + '?mode=ro', uri=True)) as source:
                with closing(sqlite3.connect(backup)) as destination:
                    source.backup(destination)
            for row_id, original, updated in proposals:
                counts['applied'] += db.execute('UPDATE messages SET record=? WHERE row_id=? AND record=?',
                                               (encode(updated), row_id, original)).rowcount
        counts['backup'] = str(backup)
    return counts


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='先备份数据库，再写入能够确认的 IP')
    args = parser.parse_args()
    print(json.dumps(backfill(apply=args.apply), ensure_ascii=False, indent=2))
