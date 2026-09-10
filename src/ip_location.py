"""访问日志使用的本地 IP 归属地查询。"""

import ipaddress
import logging
from functools import lru_cache
from pathlib import Path
from threading import Lock

from src.ip2Region import Ip2Region


DB_PATH = Path(__file__).resolve().parent / "ip2region-master" / "data" / "ip2region.db"
_lock = Lock()
_searcher = None
_initialized = False


@lru_cache(maxsize=4096)
def query_ip_city(ip):
    """优先返回城市，缺失时回退到省份、国家；失败不影响请求日志。"""
    global _searcher, _initialized
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return "未知城市"
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    if address.is_loopback:
        return "本地"
    if address.is_private or address.is_link_local:
        return "内网"
    if address.version != 4:
        return "未知城市"

    # 旧版查询器即使使用 memorySearch，也会 seek/read 地域字段。
    # 初始化和查询共用锁，避免并发请求读错文件位置。
    with _lock:
        if not _initialized:
            _initialized = True
            try:
                _searcher = Ip2Region(str(DB_PATH))
            except (Exception, SystemExit):
                logging.getLogger(__name__).warning("无法加载 IP 城市数据库：%s", DB_PATH)
        if _searcher is None:
            return "未知城市"
        try:
            result = _searcher.memorySearch(str(address))
            if not isinstance(result, dict):
                return "未知城市"
            region = result.get("region", "")
            if isinstance(region, bytes):
                region = region.decode("utf-8", errors="replace")
            parts = region.split("|")
            for index in (3, 2, 0):
                if len(parts) > index and parts[index].strip() not in ("", "0", "未知"):
                    return parts[index].strip()
        except Exception:
            pass
    return "未知城市"
