#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
visitor.json 分析工具 - 极速离线版（集成 ip2region.db，0.0x毫秒查询，永不封禁）
用法：
  python analyze_visitor.py                        # 完整分析所有记录
  python analyze_visitor.py 2026.4.23              # 只分析 2026-04-23 当天的记录
  python analyze_visitor.py 2026-04-23             # 同上
  python analyze_visitor.py 2026.4.23-             # 分析 2026-04-23 及之后的记录
  python analyze_visitor.py 2026-04-23-            # 同上
  python analyze_visitor.py ip=8.8.8.8             # 查询指定 IP 的详细信息
  python analyze_visitor.py ip=8.8.8.8 date=2026.4.23  # 查询指定 IP 在指定日期的记录（当天）
"""

import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime

# 导入本地的 ip2Region 库
try:
    from ip2Region import Ip2Region
except ImportError:
    print("❌ 未找到 ip2Region.py，请确保它和 analyze_visitor.py 在同一目录！")
    sys.exit(1)

# 路径配置
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), 'data')
VISITOR_FILE = os.path.join(DATA_DIR, 'visitor.json')

# ip2region.db 数据库文件的精确路径配置
DB_PATH = os.path.join(DATA_DIR, 'ip2region-master', 'data', 'ip2region.db')

# 全局初始化 IP 查询库
ip_searcher = None
if os.path.exists(DB_PATH):
    ip_searcher = Ip2Region(DB_PATH)
else:
    print(f"⚠️ 警告: 未找到 IP 数据库文件: {DB_PATH}")


def is_internal_ip(ip):
    """判断是否为内网 IP"""
    internal_prefixes = (
        '127.', '192.168.', '10.', '172.16.', '172.17.', '172.18.',
        '172.19.', '172.20.', '172.21.', '172.22.', '172.23.',
        '172.24.', '172.25.', '172.26.', '172.27.', '172.28.',
        '172.29.', '172.30.', '172.31.'
    )
    return any(ip.startswith(prefix) for prefix in internal_prefixes)


def is_logged_in_user(user):
    """判断是否为登录用户（排除游客/guest）"""
    if not user:
        return False
    user_lower = user.lower()
    return user_lower not in ('游客', 'guest')


def query_ip_location(ip):
    """使用本地 ip2region.db 离线查询 IP (0.0x毫秒极速查询)"""
    if is_internal_ip(ip):
        return {"country": "本地网络", "region": "内网", "city": "本地", "isp": ""}
    
    if not ip_searcher:
        return {"country": "未配置IP库", "region": "未知", "city": "未知", "isp": ""}

    try:
        # 使用 btreeSearch 算法查询
        result = ip_searcher.btreeSearch(ip)
        
        if isinstance(result, dict) and "region" in result:
            # Python3 读取二进制文件返回 bytes，需要解码成字符串
            region_data = result["region"]
            if isinstance(region_data, bytes):
                region_str = region_data.decode('utf-8', errors='ignore')
            else:
                region_str = region_data
                
            # 数据格式：国家|区域|省份|城市|ISP
            parts = region_str.split('|')
            return {
                "country": parts[0] if len(parts) > 0 and parts[0] != '0' else '未知',
                "region": parts[2] if len(parts) > 2 and parts[2] != '0' else '未知',
                "city": parts[3] if len(parts) > 3 and parts[3] != '0' else '未知',
                "isp": parts[4] if len(parts) > 4 and parts[4] != '0' else '未知'
            }
        return {"country": "未知", "region": "未知", "city": "未知", "isp": ""}
    except Exception as e:
        return {"country": "查询出错", "region": "未知", "city": "未知", "isp": ""}


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
    """加载 visitor.json 数据"""
    if not os.path.exists(VISITOR_FILE):
        print(f"❌ 未找到文件: {VISITOR_FILE}")
        return None

    try:
        with open(VISITOR_FILE, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            if not content:
                print("❌ visitor.json 文件为空")
                return None
            return json.loads(content)
    except json.JSONDecodeError as e:
        print(f"❌ JSON 解析失败: {e}")
        return None
    except IOError as e:
        print(f"❌ 读取文件失败: {e}")
        return None


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


def print_by_region(ip_counter, ip_details):
    """按地区分类输出 IP"""
    regions = defaultdict(list)  # 地区名 → [(ip, count, user_str)]
    internal_ips = []
    failed = 0

    for ip, count in sorted(ip_counter.items(), key=lambda x: x[1], reverse=True):
        if is_internal_ip(ip):
            internal_ips.append((ip, count))
            continue
        loc = query_ip_location(ip)
        country = loc.get('country', '未知')
        province = loc.get('region', '未知')
        city = loc.get('city', '未知')
        users = ','.join(ip_details[ip]["usernames"]) if ip_details[ip]["usernames"] else ''

        if country in ('查询失败', '查询出错', '未配置IP库'):
            failed += 1
            region = '⚠️ 查询失败'
        elif country == '中国':
            region = f"🇨🇳 {province}" if province != '未知' else '🇨🇳 中国'
            if city and city != '未知':
                region += f" · {city}"
        else:
            region = f"🌍 {country}"

        regions[region].append((ip, count, users))

    # 输出
    for region in sorted(regions.keys(), key=lambda r: (
        0 if r.startswith('🇨🇳') else 1 if r.startswith('🌍') else 2, r
    )):
        ips = regions[region]
        total = sum(c for _, c, _ in ips)
        print(f"\n{region} ({len(ips)} IP, {total} 次请求):")
        for ip, count, users in ips:
            tag = f" [{users}]" if users else ""
            print(f"   {ip:<18} {count:>4} 次{tag}")

    if internal_ips:
        total = sum(c for _, c in internal_ips)
        print(f"\n🏠 内网 ({len(internal_ips)} IP, {total} 次请求):")
        for ip, count in internal_ips:
            print(f"   {ip:<18} {count:>4} 次")

    if failed:
        print(f"\n⚠️ {failed} 个 IP 查询失败")


def query_single_ip(ip, records, date_desc=""):
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
        print(f"\n   ⚠️ 在 visitor.json 中未找到该 IP 的访问记录")
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
        print(f"\n   User-Agent:")
        for ua in user_agents:
            print(f"      {ua}")

    if paths:
        print(f"\n   访问路径 (共 {len(paths)} 个):")
        for path in sorted(paths):
            print(f"      {path}")

    print(f"\n📋 详细记录:")
    print("-" * 80)
    for r in sorted(records, key=lambda x: x.get('time', '')):
        user = r.get('user', '游客')
        # 如果用户是游客/guest，显示为"游客"
        if not is_logged_in_user(user):
            user = "游客"
        print(f"   [{r.get('time', '')}] {user} | {r.get('method', '')} {r.get('path', '')} | 状态: {r.get('status', 200)}")
        if r.get('user_agent'):
            print(f"      UA: {r.get('user_agent')[:80]}...")

    print("\n" + "=" * 80)


def main():
    """主函数"""

    print(f"📂 数据文件: {VISITOR_FILE}\n")

    # 加载数据
    all_records = load_visitor_data()
    if not all_records:
        return

    # 解析参数
    date_filter = None
    ip_filter = None

    for arg in sys.argv[1:]:
        if arg.startswith('ip='):
            ip_filter = arg[3:]
        elif arg.startswith('date='):
            date_filter = arg[5:]
        else:
            # 日期参数
            date_filter = arg

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
        print(f"📅 过滤日期: {date_desc}")
        print(f"✅ 筛选出 {len(records)} 条记录（共 {len(all_records)} 条）\n")
    else:
        records = all_records
        print(f"✅ 成功加载 {len(records)} 条访问记录")

    if not records:
        print("❌ 没有符合条件的记录")
        return

    # 单 IP 查询
    if ip_filter:
        ip_records = [r for r in records if r.get('ip') == ip_filter]
        query_single_ip(ip_filter, ip_records, date_desc)
        return

    # 按地区分类输出
    ip_counter, ip_details = analyze_visitor_data(records)

    if not ip_counter:
        print("❌ 未找到有效的 IP 数据")
        return

    print_by_region(ip_counter, ip_details)


if __name__ == "__main__":
    if ip_searcher is not None:
        try:
            main()
        finally:
            ip_searcher.close()
    else:
        main()