#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SQLite visits 表分析工具（官方 ip2region XDB，支持 IPv4 / IPv6 离线查询）
用法：
  python analyze_visitor.py                        # 概要输出，完整报告覆盖写入 data/reports/visitor_report.txt
  python analyze_visitor.py --full                 # 直接在控制台打印完整报告
  python analyze_visitor.py --top 20               # 每个地区只列出请求最多的前 20 个 IP
  python analyze_visitor.py --out report.txt       # 指定完整报告的输出路径
  python analyze_visitor.py --no-file              # 不写报告文件，只在控制台输出概要
  python analyze_visitor.py 2026.4.23              # 只分析 2026-04-23 当天的记录
  python analyze_visitor.py 2026-04-23             # 同上
  python analyze_visitor.py 2026.4.23-             # 分析 2026-04-23 及之后的记录
  python analyze_visitor.py 2026-04-23-            # 同上
  python analyze_visitor.py ip=8.8.8.8             # 查询指定 IP 的详细信息
  python analyze_visitor.py ip=8.8.8.8 date=2026.4.23  # 查询指定 IP 在指定日期的记录（当天）
  python analyze_visitor.py ip=8.8.8.8 --full      # 该 IP 的全部明细（默认只显示最近 200 条）
"""

import json
import ipaddress
import logging
import os
import sys
import threading
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.storage import get_store
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from src.ip_location import is_internal_ip, query_ip_location

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), 'data')
VISITOR_FILE = str(get_store().path)

# 控制台只输出概要，完整报告写入文件，避免终端 / VS Code 滚动缓冲区装不下。
RECORD_LIMIT = 200
PATH_LIMIT = 50
UA_LIMIT = 10
SUMMARY_REGIONS = 12
SUMMARY_IPS = 15

# 主程序启动时生成、之后每 24 小时覆盖一次的访客分析文件（全站只保留这一个）。
REPORT_INTERVAL_SECONDS = 24 * 60 * 60
REPORT_CHECK_SECONDS = 30 * 60
DEFAULT_REPORT_FILE = os.path.join(DATA_DIR, 'reports', 'visitor_report.txt')


def setup_console_encoding():
    """控制台编码不是 UTF-8 时用替换字符兜底，避免 emoji 触发 UnicodeEncodeError。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors='replace')
        except (AttributeError, ValueError, OSError):
            pass


def print_usage():
    print(__doc__.strip())


def parse_args(argv):
    """解析命令行参数，返回 (options, date_filter, ip_filter)。"""
    options = {'full': False, 'no_file': False, 'out': None, 'top': 0}
    date_filter = None
    ip_filter = None

    def take_value(flag, index):
        if index + 1 >= len(argv):
            print(f"❌ {flag} 缺少参数值")
            sys.exit(2)
        return argv[index + 1]

    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg in ('--full', '-f'):
            options['full'] = True
        elif arg == '--no-file':
            options['no_file'] = True
        elif arg in ('-o', '--out', '--report'):
            options['out'] = take_value(arg, index)
            index += 1
        elif arg.startswith('--out='):
            options['out'] = arg.split('=', 1)[1]
        elif arg == '--top':
            raw_top = take_value(arg, index)
            index += 1
            try:
                options['top'] = max(0, int(raw_top))
            except ValueError:
                print(f"❌ --top 需要整数: {raw_top}")
                sys.exit(2)
        elif arg.startswith('--top='):
            try:
                options['top'] = max(0, int(arg.split('=', 1)[1]))
            except ValueError:
                print(f"❌ --top 需要整数: {arg}")
                sys.exit(2)
        elif arg in ('-h', '--help', 'help'):
            print_usage()
            sys.exit(0)
        elif arg.startswith('ip='):
            ip_filter = arg[3:]
        elif arg.startswith('date='):
            date_filter = arg[5:]
        else:
            # 位置参数按日期处理
            date_filter = arg
        index += 1

    return options, date_filter, ip_filter


def is_logged_in_user(user):
    """判断是否为登录用户（排除游客/guest）"""
    if not user:
        return False
    user_lower = user.lower()
    return user_lower not in ('游客', 'guest')


def parse_date_arg(date_str):
    """
    解析日期参数
    "2026.4.23" 或 "2026-04-23" -> 当天
    "2026.4.23-" 或 "2026-04-23-" -> 该天及之后
    返回 (start_date, end_date) 元组
    """
    date_str = date_str.strip()
    
    after_mode = False
    if date_str.endswith('-'):
        after_mode = True
        date_str = date_str[:-1]
    
    # 统一格式
    date_str = date_str.replace('.', '-')
    
    try:
        target_date = datetime.strptime(date_str, '%Y-%m-%d')
    except ValueError:
        return None, None
    
    if after_mode:
        # 该天及之后
        return target_date, None
    else:
        # 只查询当天
        return target_date, target_date


def filter_records_by_date(records, start_date, end_date):
    """按日期过滤记录"""
    filtered = []
    for r in records:
        time_str = r.get('time', '')
        if not time_str:
            continue
        try:
            # 提取日期部分
            record_date = datetime.strptime(time_str[:10], '%Y-%m-%d')
            if start_date and end_date:
                # 当天
                if record_date.date() == start_date.date():
                    filtered.append(r)
            elif start_date and not end_date:
                # 该天及之后
                if record_date.date() >= start_date.date():
                    filtered.append(r)
        except ValueError:
            continue
    return filtered


def load_visitor_data():
    """从 SQLite 加载访问记录。"""
    return get_store().records('visits')


def analyze_visitor_data(records):
    """分析 visitor 数据，构建 ip_counter 和 ip_details"""

    ip_counter = Counter()
    ip_details = defaultdict(lambda: {
        "count": 0,
        "usernames": set(),
        "errors": 0,
        "first_seen": None,
        "last_seen": None,
        "paths": set(),
        "methods": Counter(),
        "user_agents": set()
    })

    for record in records:
        ip = record.get('ip')
        if not ip:
            continue

        user = record.get('user', '')
        # 只有非游客用户才记录到 usernames
        if is_logged_in_user(user):
            logged_user = user
        else:
            logged_user = None

        path = record.get('path', '')
        method = record.get('method', '')
        status = record.get('status', 200)
        timestamp = record.get('time', '')
        user_agent = record.get('user_agent', '')

        ip_counter[ip] += 1
        ip_details[ip]["count"] += 1

        if logged_user:
            ip_details[ip]["usernames"].add(logged_user)

        if status and str(status).startswith(('4', '5')):
            ip_details[ip]["errors"] += 1

        if path:
            ip_details[ip]["paths"].add(path)

        if method:
            ip_details[ip]["methods"][method] += 1

        if user_agent:
            ip_details[ip]["user_agents"].add(user_agent)

        if timestamp:
            if not ip_details[ip]["first_seen"] or timestamp < ip_details[ip]["first_seen"]:
                ip_details[ip]["first_seen"] = timestamp
            if not ip_details[ip]["last_seen"] or timestamp > ip_details[ip]["last_seen"]:
                ip_details[ip]["last_seen"] = timestamp

    return ip_counter, ip_details


def region_label(ip):
    """把 IP 归属地整理成单行地区标签。"""
    loc = query_ip_location(ip)
    country = loc.get('country', '未知')
    province = loc.get('region', '未知')
    city = loc.get('city', '未知')

    if country in ('查询失败', '查询出错', '未配置IP库'):
        return '⚠️ 查询失败'
    if country == '中国':
        label = f"🇨🇳 {province}" if province != '未知' else '🇨🇳 中国'
        if city and city != '未知':
            label += f" · {city}"
        return label
    return f"🌍 {country}"


def group_by_region(ip_counter, ip_details):
    """按地区归类，返回 (regions, internal_ips, failed)。"""
    regions = defaultdict(list)
    internal_ips = []
    failed = 0

    for ip, count in sorted(ip_counter.items(), key=lambda x: x[1], reverse=True):
        if is_internal_ip(ip):
            internal_ips.append((ip, count))
            continue
        users = ','.join(ip_details[ip]["usernames"]) if ip_details[ip]["usernames"] else ''
        region = region_label(ip)
        if region == '⚠️ 查询失败':
            failed += 1
        regions[region].append((ip, count, users))

    return regions, internal_ips, failed


def sort_regions(regions):
    """国内省份在前、国外在后，各自按请求次数降序；查询失败排最后。"""
    def sort_key(region):
        if region.startswith('⚠️ '):
            group = 2
        elif region.startswith('🌍 '):
            group = 1
        else:
            group = 0
        total = sum(count for _, count, _ in regions[region])
        return (group, -total, -len(regions[region]), region)

    return sorted(regions, key=sort_key)


def layout_entries(entries, width=150):
    """把短条目排成紧凑多列文本，每行不超过 width 个字符。"""
    lines = []
    line = "   "
    for entry in entries:
        if line.strip() and len(line) + len(entry) > width:
            lines.append(line)
            line = "   " + entry
        else:
            line += entry
    if line.strip():
        lines.append(line)
    return lines


def format_region_section(ip_counter, ip_details, top=0, width=150):
    """生成按地区分类的报告正文，返回 (lines, stats)。"""
    regions, internal_ips, failed = group_by_region(ip_counter, ip_details)
    lines = []
    region_stats = []

    for region in sort_regions(regions):
        ips = regions[region]
        total = sum(c for _, c, _ in ips)
        region_stats.append((region, len(ips), total))

        lines.append("")
        lines.append(f"{region} ({len(ips)} IP, {total} 次请求):")
        shown = ips if top <= 0 else ips[:top]
        entries = []
        for ip, count, users in shown:
            tag = f"--{users}" if users else ""
            entries.append(f"{ip}--{count}次{tag}  ")
        lines.extend(layout_entries(entries, width))
        if top > 0 and len(ips) > top:
            lines.append(f"   ...另有 {len(ips) - top} 个 IP 未列出（--top 0 可显示全部）")

    if internal_ips:
        total = sum(c for _, c in internal_ips)
        lines.append("")
        lines.append(f"🏠 内网 ({len(internal_ips)} IP, {total} 次请求):")
        lines.extend(layout_entries([f"{ip}--{count}次  " for ip, count in internal_ips], width))

    if failed:
        lines.append("")
        lines.append(f"⚠️ {failed} 个 IP 查询失败")

    stats = {
        'region_stats': region_stats,
        'internal_ips': internal_ips,
        'public_ips': sum(len(ips) for ips in regions.values()),
        'failed': failed,
    }
    return lines, stats


def format_summary(ip_counter, ip_details, stats, error_count):
    """生成控制台概要，控制在几十行以内。"""
    lines = []
    lines.append("📊 概要")
    lines.append(f"   独立 IP:   {len(ip_counter)} 个（公网 {stats['public_ips']} · 内网 {len(stats['internal_ips'])}）")
    lines.append(f"   错误请求:  {error_count} 次（4xx / 5xx）")
    if stats['failed']:
        lines.append(f"   查询失败:  {stats['failed']} 个 IP（ip2region 库可能缺失）")

    regions = stats['region_stats']
    lines.append("")
    lines.append(f"👀 请求最多的地区（共 {len(regions)} 个地区）:")
    for region, ip_count, total in regions[:SUMMARY_REGIONS]:
        lines.append(f"   {region} — {ip_count} IP / {total} 次请求")
    if len(regions) > SUMMARY_REGIONS:
        lines.append(f"   ...其余 {len(regions) - SUMMARY_REGIONS} 个地区见完整报告")

    lines.append("")
    lines.append(f"🔥 请求最多的 IP（前 {SUMMARY_IPS}）:")
    for ip, count in sorted(ip_counter.items(), key=lambda x: x[1], reverse=True)[:SUMMARY_IPS]:
        users = ','.join(ip_details[ip]["usernames"])
        extra = f" · {users}" if users else ""
        lines.append(f"   {ip} — {count} 次{extra} · {region_label(ip)}")

    return lines


def write_report(lines, out_arg=None):
    """把报告覆盖写入单个文件，成功返回绝对路径，失败返回 None。"""
    if out_arg:
        path = os.path.abspath(os.path.expanduser(out_arg))
    else:
        path = DEFAULT_REPORT_FILE

    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write("\n".join(lines) + "\n")
    except OSError as exc:
        print(f"⚠️ 报告写入失败: {exc}")
        return None
    return path


def build_report_lines(records, header_lines=(), top=0):
    """把访问记录渲染成报告文本，返回 (lines, stats, ip_counter, ip_details)。"""
    ip_counter, ip_details = analyze_visitor_data(records)
    if not ip_counter:
        return [], None, ip_counter, ip_details
    lines, stats = format_region_section(ip_counter, ip_details, top=top)
    return list(header_lines) + lines, stats, ip_counter, ip_details


def report_header_lines(record_count, total_count=None, date_desc=None):
    """报告表头：数据来源、生成时间、条数与排序说明。"""
    lines = [
        f"📂 数据文件: {VISITOR_FILE}",
        f"🕒 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
    ]
    if date_desc:
        lines.append(f"📅 过滤日期: {date_desc}")
        lines.append(f"✅ 筛选出 {record_count} 条记录（共 {total_count} 条）")
    else:
        lines.append(f"✅ 成功加载 {record_count} 条访问记录")
    lines.append("📑 排序: 国内省份（按访问次数降序）→ 国外（按访问次数降序）→ 内网")
    return lines


def generate_report(path=DEFAULT_REPORT_FILE, top=0):
    """重新分析全部记录并覆盖写入报告文件，返回文件路径（无数据时返回 None）。"""
    records = load_visitor_data()
    if not records:
        return None

    lines, _, _, _ = build_report_lines(records, report_header_lines(len(records)), top=top)
    if not lines:
        return None
    return write_report(lines, path)


def report_is_stale(path=DEFAULT_REPORT_FILE, interval=REPORT_INTERVAL_SECONDS):
    """报告文件缺失或超过 interval 未更新时返回 True。"""
    try:
        return time.time() - os.path.getmtime(path) >= interval
    except OSError:
        return True


def ensure_daily_report(force=False, path=DEFAULT_REPORT_FILE, interval=REPORT_INTERVAL_SECONDS):
    """文件过期才重新覆盖生成，返回生成的文件路径（跳过时返回 None）。"""
    if not force and not report_is_stale(path, interval):
        return None
    try:
        return generate_report(path)
    except Exception:
        logging.getLogger(__name__).exception("生成访客分析报告失败")
        return None


def start_daily_report_thread(path=DEFAULT_REPORT_FILE,
                              interval=REPORT_INTERVAL_SECONDS,
                              check_seconds=REPORT_CHECK_SECONDS,
                              force=False):
    """后台线程：启动时生成一次报告，之后按 interval 定期覆盖更新。

    force=True 时忽略文件时间戳，启动后立刻重新生成。
    """
    def worker():
        first = True
        while True:
            ensure_daily_report(force=force and first, path=path, interval=interval)
            first = False
            time.sleep(check_seconds)

    thread = threading.Thread(target=worker, name='visitor-report', daemon=True)
    thread.start()
    return thread


# ===================== 页面接口数据 =====================
# /api/visit-stats 的内存缓存：分析一次约几秒，缓存期内直接复用。
STATS_CACHE_SECONDS = 5 * 60
_stats_cache = {'time': 0.0, 'payload': None}
_stats_lock = threading.Lock()


def region_group(label):
    """地区分组：0 = 国内，1 = 国外，2 = 查询失败。"""
    if label.startswith('⚠️ '):
        return 2
    if label.startswith('🌍 '):
        return 1
    return 0


def build_stats_payload(records=None, top_ips=20, top_paths=12, trend_days=30):
    """构建访问分析页面用的结构化数据（可直接 json.dumps）。

    每个地区的 entries 是紧凑数组：[IP, 访问次数, 登录用户列表, 最后访问时间]。
    """
    if records is None:
        records = load_visitor_data()

    ip_counter, ip_details = analyze_visitor_data(records)
    region_ips = defaultdict(list)
    internal_entries = []
    totals = {
        'records': len(records),
        'ips': len(ip_counter),
        'internal_ips': 0,
        'errors': 0,
        'domestic_ips': 0,
        'domestic_visits': 0,
        'overseas_ips': 0,
        'overseas_visits': 0,
        'domestic_regions': 0,
        'overseas_regions': 0,
        'first_visit': '',
        'last_visit': '',
    }

    for record in records:
        if str(record.get('status', 200)).startswith(('4', '5')):
            totals['errors'] += 1
        stamp = record.get('time', '')
        if stamp:
            if not totals['first_visit'] or stamp < totals['first_visit']:
                totals['first_visit'] = stamp
            if not totals['last_visit'] or stamp > totals['last_visit']:
                totals['last_visit'] = stamp

    for ip, count in sorted(ip_counter.items(), key=lambda x: x[1], reverse=True):
        detail = ip_details[ip]
        # 紧凑数组：完整 IP 列表是这个接口体积的主要来源。
        entry = [ip, count, sorted(detail['usernames']), detail['last_seen'] or '']
        if is_internal_ip(ip):
            internal_entries.append(entry)
            continue

        label = region_label(ip)
        region_ips[label].append(entry)
        group = region_group(label)
        if group == 0:
            totals['domestic_ips'] += 1
            totals['domestic_visits'] += count
        elif group == 1:
            totals['overseas_ips'] += 1
            totals['overseas_visits'] += count

    def pack_regions(labels):
        packed = []
        for label in sorted(labels, key=lambda item: (
                -sum(entry[1] for entry in region_ips[item]), item)):
            entries = sorted(region_ips[label], key=lambda entry: (-entry[1], entry[0]))
            packed.append({
                'label': label,
                'name': label.split(' ', 1)[1] if ' ' in label else label,
                'ips': len(entries),
                'visits': sum(entry[1] for entry in entries),
                'entries': entries,
            })
        return packed

    labels = list(region_ips)
    domestic = pack_regions([l for l in labels if region_group(l) == 0])
    overseas = pack_regions([l for l in labels if region_group(l) == 1])
    failed = pack_regions([l for l in labels if region_group(l) == 2])
    totals['internal_ips'] = len(internal_entries)
    totals['domestic_regions'] = len(domestic)
    totals['overseas_regions'] = len(overseas)

    top_ip_entries = []
    for ip, count in sorted(ip_counter.items(), key=lambda x: x[1], reverse=True)[:top_ips]:
        detail = ip_details[ip]
        top_ip_entries.append({
            'ip': ip,
            'visits': count,
            'users': sorted(detail['usernames']),
            'last_seen': detail['last_seen'] or '',
            'region': '🏠 内网' if is_internal_ip(ip) else region_label(ip),
        })

    path_counter = Counter(record.get('path', '') for record in records if record.get('path'))
    daily_counter = Counter(
        record.get('time', '')[:10] for record in records if len(record.get('time', '')) >= 10
    )
    today = datetime.now().date()
    daily = []
    for offset in range(trend_days - 1, -1, -1):
        key = (today - timedelta(days=offset)).strftime('%Y-%m-%d')
        daily.append({'date': key, 'visits': daily_counter.get(key, 0)})

    return {
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'report_file': os.path.relpath(DEFAULT_REPORT_FILE, os.path.dirname(DATA_DIR)).replace('\\', '/'),
        'totals': totals,
        'domestic': domestic,
        'overseas': overseas,
        'failed': failed,
        'internal': {
            'label': '🏠 内网',
            'ips': len(internal_entries),
            'visits': sum(entry[1] for entry in internal_entries),
            'entries': internal_entries,
        },
        'top_ips': top_ip_entries,
        'top_paths': [{'path': path, 'visits': count}
                      for path, count in path_counter.most_common(top_paths)],
        'daily': daily,
    }


def get_stats_payload(max_age=STATS_CACHE_SECONDS, refresh=False):
    """带缓存的 build_stats_payload：缓存期内不重复分析。"""
    with _stats_lock:
        cached = _stats_cache['payload']
        if not refresh and cached is not None and time.time() - _stats_cache['time'] < max_age:
            return cached
        payload = build_stats_payload()
        _stats_cache['time'] = time.time()
        _stats_cache['payload'] = payload
        return payload


def build_ip_detail(ip, records=None, limit=200, offset=0):
    """单个 IP 的详细访问记录（页面弹窗用），IP 非法时返回 None。

    records 按时间倒序分页返回，paths 为该 IP 访问最多的前 50 条路径。
    """
    cleaned = str(ip or '').strip()
    try:
        ipaddress.ip_address(cleaned)
    except (ValueError, TypeError):
        return None

    if records is None:
        records = load_visitor_data()

    limit = max(1, min(int(limit or 200), 500))
    offset = max(0, int(offset or 0))

    matched = [record for record in records if record.get('ip') == cleaned]
    matched.sort(key=lambda record: record.get('time', ''), reverse=True)

    def is_error(record):
        return str(record.get('status', 200)).startswith(('4', '5'))

    methods = Counter(record.get('method', '') for record in matched if record.get('method'))
    path_counter = Counter(record.get('path', '') for record in matched if record.get('path'))
    path_errors = Counter(record.get('path', '') for record in matched
                          if record.get('path') and is_error(record))
    users = sorted({record.get('user') for record in matched
                    if is_logged_in_user(record.get('user'))})
    times = [record.get('time', '') for record in matched if record.get('time')]
    internal = is_internal_ip(cleaned)

    page = [{
        'time': record.get('time', ''),
        'user': record.get('user') or '游客',
        'method': record.get('method', ''),
        'path': record.get('path', ''),
        'status': record.get('status', 200),
    } for record in matched[offset:offset + limit]]

    return {
        'ip': cleaned,
        'internal': internal,
        'region': '🏠 内网' if internal else region_label(cleaned),
        'location': query_ip_location(cleaned),
        'totals': {
            'records': len(matched),
            'errors': sum(1 for record in matched if is_error(record)),
            'users': users,
            'first_seen': min(times) if times else '',
            'last_seen': max(times) if times else '',
            'paths': len(path_counter),
            'methods': [{'method': method, 'visits': count}
                        for method, count in methods.most_common()],
        },
        'paths': [{'path': path, 'visits': count, 'errors': path_errors.get(path, 0)}
                  for path, count in path_counter.most_common(50)],
        'records': page,
        'limit': limit,
        'offset': offset,
        'has_more': offset + limit < len(matched),
    }


def query_single_ip(ip, records, date_desc="", show_all=False):
    """查询单个 IP 的详细信息"""
    print("\n" + "=" * 80)
    if date_desc:
        print(f"🔍 查询 IP: {ip} ({date_desc})")
    else:
        print(f"🔍 查询 IP: {ip}")
    print("=" * 80)

    if is_internal_ip(ip):
        print(f"\n📌 IP 类型: 内网/本地 IP")
    else:
        print(f"\n📌 IP 类型: 公网 IP")

    print(f"\n🌍 地理位置信息:")
    print("-" * 80)
    loc = query_ip_location(ip)

    print(f"   国家/地区: {loc.get('country', '未知')}")
    print(f"   省份/州:   {loc.get('region', '未知')}")
    print(f"   城市:      {loc.get('city', '未知')}")
    print(f"   ISP:       {loc.get('isp', '未知')}")

    if not records:
        print(f"\n   ⚠️ 在 SQLite visits 表 中未找到该 IP 的访问记录")
        print("\n" + "=" * 80)
        return

    print(f"\n📊 访问记录统计 (共 {len(records)} 条):")
    print("-" * 80)

    methods = Counter(r.get('method', '') for r in records)
    paths = set(r.get('path', '') for r in records if r.get('path'))
    # 只统计真实登录用户（排除游客/guest）
    usernames = set(r.get('user', '') for r in records if r.get('user') and is_logged_in_user(r.get('user')))
    errors = sum(1 for r in records if str(r.get('status', 200)).startswith(('4', '5')))
    user_agents = set(r.get('user_agent', '') for r in records if r.get('user_agent'))

    times = [r.get('time', '') for r in records if r.get('time')]
    times.sort()

    print(f"   总请求次数: {len(records)}")
    print(f"   首次访问:   {times[0] if times else '-'}")
    print(f"   最后访问:   {times[-1] if times else '-'}")
    print(f"   错误请求:   {errors}")

    if usernames:
        print(f"   登录用户:   {', '.join(usernames)}")
    else:
        print(f"   登录用户:   游客")

    print(f"\n   请求方法统计:")
    for method, count in methods.items():
        print(f"      {method}: {count} 次")

    if user_agents:
        ua_list = sorted(user_agents)
        shown_uas = ua_list if show_all else ua_list[:UA_LIMIT]
        print(f"\n   User-Agent (共 {len(ua_list)} 个):")
        for ua in shown_uas:
            print(f"      {ua}")
        if len(ua_list) > len(shown_uas):
            print(f"      ...另有 {len(ua_list) - len(shown_uas)} 个未列出（--full 查看全部）")

    if paths:
        path_list = sorted(paths)
        shown_paths = path_list if show_all else path_list[:PATH_LIMIT]
        print(f"\n   访问路径 (共 {len(path_list)} 个):")
        for path in shown_paths:
            print(f"      {path}")
        if len(path_list) > len(shown_paths):
            print(f"      ...另有 {len(path_list) - len(shown_paths)} 个路径未列出（--full 查看全部）")

    print(f"\n📋 详细记录:")
    print("-" * 80)

    detail_records = sorted(records, key=lambda x: x.get('time', ''))
    hidden = 0
    if not show_all and len(detail_records) > RECORD_LIMIT:
        hidden = len(detail_records) - RECORD_LIMIT
        detail_records = detail_records[-RECORD_LIMIT:]

    for r in detail_records:
        user = r.get('user', '游客')
        # 如果用户是游客/guest，显示为"游客"
        if not is_logged_in_user(user):
            user = "游客"
        print(f"   [{r.get('time', '')}] {user} | {r.get('method', '')} {r.get('path', '')} | 状态: {r.get('status', 200)}")

    if hidden:
        print(f"   ...（更早的 {hidden} 条记录已省略，使用 --full 查看全部）")

    print("\n" + "=" * 80)


def main():
    """主函数"""

    setup_console_encoding()
    options, date_filter, ip_filter = parse_args(sys.argv[1:])

    # 加载数据
    all_records = load_visitor_data()
    if not all_records:
        print(f"📂 数据文件: {VISITOR_FILE}")
        print("❌ visits 表中没有访问记录")
        return

    # 处理日期过滤
    start_date = None
    end_date = None
    date_desc = ""

    if date_filter:
        start_date, end_date = parse_date_arg(date_filter)
        if start_date is None:
            print(f"❌ 无效的日期格式: {date_filter}")
            return

        if date_filter.endswith('-') or date_filter.endswith('-后') or date_filter.endswith('-之后'):
            date_desc = f"{start_date.strftime('%Y-%m-%d')} 及之后"
        else:
            date_desc = start_date.strftime('%Y-%m-%d')

        records = filter_records_by_date(all_records, start_date, end_date)
        header_lines = report_header_lines(len(records), len(all_records), date_desc)
    else:
        records = all_records
        header_lines = report_header_lines(len(records))

    if not records:
        for line in header_lines:
            print(line)
        print("❌ 没有符合条件的记录")
        return

    # 单 IP 查询
    if ip_filter:
        ip_records = [r for r in records if r.get('ip') == ip_filter]
        for line in header_lines:
            print(line)
        query_single_ip(ip_filter, ip_records, date_desc, show_all=options['full'])
        return

    # 按地区分类输出
    report_lines, stats, ip_counter, ip_details = build_report_lines(
        records, header_lines, top=options['top'])

    if not report_lines:
        for line in header_lines:
            print(line)
        print("❌ 未找到有效的 IP 数据")
        return

    error_count = sum(1 for r in records if str(r.get('status', 200)).startswith(('4', '5')))

    report_path = None
    if not options['no_file']:
        report_path = write_report(report_lines, options['out'])
        if report_path is None:
            # 写文件失败时退回完整控制台输出，避免丢结果
            options['full'] = True

    if options['full']:
        for line in report_lines:
            print(line)
        if report_path:
            print(f"\n📄 完整报告副本: {report_path}")
        return

    for line in header_lines:
        print(line)
    print()
    for line in format_summary(ip_counter, ip_details, stats, error_count):
        print(line)
    if report_path:
        print()
        print(f"📄 完整报告已写入: {report_path}")
        print("   单文件，每次运行覆盖；--full 可直接在控制台打印，--out 可另存到其他路径")


if __name__ == "__main__":
    main()
