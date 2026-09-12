"""共享的 IPv4/IPv6 离线归属地查询（ip2region XDB）。"""
import ipaddress
import logging
from functools import lru_cache
from importlib import import_module
from pathlib import Path
from threading import Lock

DATA_DIR = Path(__file__).resolve().parent / "ip2region-master" / "data"
DB_PATHS = {v: DATA_DIR / f"ip2region_v{v}.xdb" for v in (4, 6)}
_lock = Lock()
_searchers = {}


def _address(ip):
    address = ipaddress.ip_address(ip)
    return getattr(address, "ipv4_mapped", None) or address


def is_internal_ip(ip):
    try:
        address = _address(ip)
        return address.is_loopback or address.is_private or address.is_link_local
    except (ValueError, TypeError):
        return False


def _get_searcher(version):
    with _lock:
        if version not in _searchers:
            try:
                try:
                    from ip2region import util, searcher
                except ModuleNotFoundError as exc:
                    if exc.name != "ip2region":
                        raise
                    util = import_module("src.ip2region-master._vendor.ip2region.util")
                    searcher = import_module("src.ip2region-master._vendor.ip2region.searcher")
                path = str(DB_PATHS[version])
                util.verify_from_file(path)
                header = util.load_header_from_file(path)
                db_version = util.version_from_header(header)
                if db_version.byte_num != (4 if version == 4 else 16):
                    raise ValueError("XDB IP version mismatch")
                content = util.load_content_from_file(path)
                if len(content) < 524544:
                    raise ValueError("Truncated XDB")
                # 官方全内存查询器支持并发共享，无需保持文件句柄。
                _searchers[version] = searcher.new_with_buffer(db_version, content)
            except Exception:
                logging.getLogger(__name__).exception("无法加载 IPv%s 数据库", version)
                _searchers[version] = None
        return _searchers[version]


def _parse_region(raw, version=4):
    # XDB：国家|省份|城市|ISP|ISO 国家代码，不能沿用旧 DB 的字段下标。
    parts = raw.split("|")
    if version == 6:
        # GeoCN/GeoLite2 融合库：洲|国家|省份|城市|区县|ISP|网络类型。
        parts = [parts[i] if len(parts) > i else "" for i in (1, 2, 3, 5)]
    return tuple(parts[i].strip() if len(parts) > i and parts[i].strip() not in ("", "0")
                 else ("" if i == 3 else "未知") for i in range(4))


@lru_cache(maxsize=4096)
def _lookup(ip):
    try:
        address = _address(ip)
    except (ValueError, TypeError):
        return ("未知", "未知", "未知", "")
    if is_internal_ip(str(address)):
        return ("本地网络", "内网", "本地", "")
    searcher = _get_searcher(address.version)
    if searcher is not None:
        try:
            return _parse_region(searcher.search(str(address)), address.version)
        except Exception:
            logging.getLogger(__name__).warning("IP 归属地查询失败", exc_info=True)
    return ("未知", "未知", "未知", "")


def query_ip_location(ip):
    """返回独立字典，调用者修改结果不会污染缓存。"""
    return dict(zip(("country", "region", "city", "isp"), _lookup(ip)))


def query_ip_city(ip):
    """城市缺失时回退到省份、国家；查询失败不影响访问记录。"""
    try:
        address = _address(ip)
        if address.is_loopback:
            return "本地"
        if is_internal_ip(str(address)):
            return "内网"
    except (ValueError, TypeError):
        return "未知城市"
    result = query_ip_location(str(address))
    for key in ("city", "region", "country"):
        if result[key] not in ("", "0", "未知"):
            return result[key]
    return "未知城市"
