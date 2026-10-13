# -*- coding: utf-8 -*-
"""
个人Vlog HTTP服务端（支持 PROXY Protocol 获取真实IP）
✅ 纯 Python 实现 PROXY Protocol 解析，无需第三方库
✅ 极简日志格式，单行显示
✅ 添加emoji标识，一目了然
✅ 响应时间显示，便于性能监控
✅ 用户状态实时显示
✅ 日志带日期显示
✅ URL解码，显示中文路径
✅ 过滤静态资源日志（图片/视频/CSS/JS等）
✅ 页面及接口访问记录保存到 site.db / visits（线程安全）
"""
import socket
import ssl
import sys
import os
import time
import json
import logging
import argparse
import contextlib
import struct
import threading
import html
from functools import partial
from datetime import datetime
from collections import defaultdict
from http.server import CGIHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse, quote
import posixpath
from src.ip_location import query_ip_city
from src.storage import get_store
from src.admin_db import is_admin, overview as admin_overview, browse as admin_browse

FUTURE_SCHOLAR_ALLOWED_USERS = {'caibo', 'hyper', 'admin'}

# 访问分析页面（/pages/visit/）数据接口：访客 IP 属于隐私数据，默认仅登录账号可见。
VISIT_STATS_REQUIRE_LOGIN = True
# 留空表示任意已登录账号；填写则只允许名单内的账号（小写）。
VISIT_STATS_ALLOWED_USERS = set()
# 单个 IP 的详细记录只对这些账号开放（小写），默认仅站长本人。
VISIT_DETAIL_ALLOWED_USERS = {'hyper'}

# ===================== PROXY Protocol 解析器（纯Python实现） =====================
class SimpleProxyProtocol:
    """简单的 PROXY Protocol v2 解析器"""

    # PROXY Protocol v2 签名 (12字节)
    PROXY_SIGNATURE = b'\x0D\x0A\x0D\x0A\x00\x0D\x0A\x51\x55\x49\x54\x0A'

    @classmethod
    def parse(cls, sock):
        """
        从 socket 解析 PROXY Protocol v2 头部
        返回真实客户端 IP，如果没有 PROXY 头部返回 None
        """
        original_timeout = None
        try:
            # 保存原始超时设置
            original_timeout = sock.gettimeout()
            # 设置短超时，避免阻塞
            sock.settimeout(0.1)

            # 查看前 16 字节（不移除，只 peek）
            header = sock.recv(16, socket.MSG_PEEK)
            if len(header) < 16:
                sock.settimeout(original_timeout)
                return None

            # 检查 PROXY 签名
            if header[:12] != cls.PROXY_SIGNATURE:
                sock.settimeout(original_timeout)
                return None

            # 解析版本和命令（第13字节）- 高4位是版本，低4位是命令
            ver_cmd = header[12]
            # 解析协议族（第14字节）- 高4位是地址族，低4位是传输协议
            family = header[13]
            # 解析地址长度（第15-16字节）
            addr_len = struct.unpack('!H', header[14:16])[0]

            # 读取完整的 PROXY 头部（包括前面16字节 + 地址信息）
            full_header = sock.recv(16 + addr_len)

            # 根据协议族解析 IP
            if family & 0x10:  # TCP over IPv4 (0x11 或 0x12)
                # IPv4 地址是 4 字节（源IP 4字节 + 目的IP 4字节 + 源端口 2字节 + 目的端口 2字节）
                src_addr = socket.inet_ntoa(full_header[16:20])
                sock.settimeout(original_timeout)
                return src_addr
            elif family & 0x20:  # TCP over IPv6 (0x21 或 0x22)
                # IPv6 地址是 16 字节
                src_addr = socket.inet_ntop(socket.AF_INET6, full_header[16:32])
                sock.settimeout(original_timeout)
                return src_addr
            else:
                # 其他协议族，不支持
                sock.settimeout(original_timeout)
                return None

        except socket.timeout:
            # 超时说明没有 PROXY 头部，是普通连接
            return None
        except Exception as e:
            # 其他错误，忽略
            return None
        finally:
            if original_timeout is not None:
                with contextlib.suppress(Exception):
                    sock.settimeout(original_timeout)

# ===================== 配置抽离 =====================
class Config:
    HOST = "0.0.0.0"
    PORT = 8000
    SERVER_DIR = None
    CERT_FILE = None
    KEY_FILE = None

    RATE_LIMIT = 60  # 60秒内允许的最大请求数
    RATE_LIMIT_WINDOW = 60  # 时间窗口（秒）
    MAX_POST_SIZE = 1 * 1024 * 1024  # 1MB
    ALLOWED_EXTENSIONS = None

    LOG_DIR = "logs"
    LOG_LEVEL = logging.INFO
    LOG_ROTATE = True

    # 排除计数的路径
    EXCLUDE_COUNT_PATHS = ['/visit-count']
    EXCLUDE_STATIC_EXT = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.css', '.js', '.ico', '.svg']
    RESET_VISITS = False

    # 敏感文件列表
    SENSITIVE_FILES = ['users.json', 'sessions.json', 'messages.json', 'visit_count.json']
    # 保护的数据目录
    PROTECTED_DIRS = ['/data/', '/data\\']

    # 允许的路径白名单（防止扫描）
    ALLOWED_PATHS = [
        '/', '/home', '/home/', '/talk', '/talk/', '/pages/',
        '/static/', '/api/', '/visit-count', '/banner/',
        '/favicon.ico', '/robots.txt', '/dwcc/', '/media/'
    ]

    # Relocated page assets: keep cached HTML and old links working.
    LEGACY_ASSET_PATHS = {
        '/static/css/home.css': '/pages/home/home.css',
        '/static/js/home.js': '/pages/home/home.js',
        '/static/css/resume.css': '/pages/resume/resume.css',
        '/static/css/ai-chat.css': '/pages/talk/ai-chat.css',
        '/static/js/ai-log.js': '/pages/talk/ai-log.js',
        '/static/js/auth.js': '/pages/login/auth.js',
        '/static/js/auth-interceptor.js': '/pages/login/auth-interceptor.js',
        '/static/css/hardware-article.css': '/pages/diy/hardware-article.css',
        '/static/travel/journal.css': '/pages/travel/journal.css',
        '/static/travel/journal.js': '/pages/travel/journal.js',
        '/static/css/visit-stats.css': '/pages/visit/visit-stats.css',
        '/static/js/visit-stats.js': '/pages/visit/visit-stats.js',
        '/static/css/category.css': '/pages/_shared/category.css',
        '/static/css/site-theme.css': '/pages/_shared/site-theme.css',
        '/static/js/page-navigation.js': '/pages/_shared/page-navigation.js',
    }

    # 不记录日志的静态资源扩展名（图片、视频、CSS、JS等）
    SKIP_LOG_EXT = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.ico', '.svg',
                    '.mp4', '.avi', '.mov', '.wmv', '.flv', '.mkv', '.webm', '.mpeg', '.mpg',
                    '.css', '.js', '.map', '.woff', '.woff2', '.ttf', '.eot']

    # site.db / visits 最大记录数（0表示不限制）
    MAX_VISITOR_RECORDS = 0

    # 访客分析报告：启动时若文件已过期则覆盖生成，--force-report 强制立即重生成
    FORCE_REPORT = False


def decode_path(path: str) -> str:
    """
    将 URL 编码的路径解码为中文
    例如: YY%E5%BE%80%E4%BA%8B/ -> YY往事/
    """
    try:
        return unquote(path, encoding='utf-8')
    except Exception:
        return path


# ===================== 日志初始化 =====================
def init_logging():
    """初始化日志：极简格式"""
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), Config.LOG_DIR)
    os.makedirs(log_dir, exist_ok=True)
    log_filename = f"access_{datetime.now().strftime('%Y%m%d')}.log" if Config.LOG_ROTATE else "access.log"
    log_file = os.path.join(log_dir, log_filename)

    # 自定义日志格式 - 极简版（带日期）
    class SimpleFormatter(logging.Formatter):
        def format(self, record):
            if hasattr(record, 'simple_msg'):
                return record.simple_msg
            return f"{self.formatTime(record, '%Y-%m-%d %H:%M:%S')} - {record.getMessage()}"

    # 控制台处理器 - 使用简单格式（带日期）
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(SimpleFormatter())

    # 文件处理器 - 保留完整信息
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))

    # 配置日志
    logging.basicConfig(
        level=Config.LOG_LEVEL,
        handlers=[file_handler, console_handler]
    )
    return logging.getLogger(__name__)

logger = init_logging()

# ===================== 目录创建 =====================
current_script_dir = os.path.dirname(os.path.abspath(__file__))
data_dir = os.path.join(current_script_dir, 'data')
src_dir = os.path.join(current_script_dir, 'src')
home_dir = os.path.join(current_script_dir, 'pages', 'home')
talk_dir = os.path.join(current_script_dir, 'pages', 'talk')

for d in [data_dir, src_dir, home_dir, talk_dir]:
    try:
        os.makedirs(d, exist_ok=True)
    except Exception as e:
        logger.warning(f"创建目录 {d} 失败：{e}")

# 在data目录创建index.html防止目录浏览
data_index_path = os.path.join(data_dir, 'index.html')
if not os.path.exists(data_index_path):
    try:
        with open(data_index_path, 'w', encoding='utf-8') as f:
            f.write("""<!DOCTYPE html>
<html>
<head><title>禁止访问</title></head>
<body style="background:#f8f9fa; text-align:center; padding:50px;">
    <h1 style="color:#6a5acd;">403 Forbidden</h1>
    <p style="color:#495057;">你没有权限访问此目录</p>
</body>
</html>""")
    except Exception as e:
        logger.warning(f"创建data目录保护文件失败：{e}")

# 将 src 目录添加到 Python 路径
sys.path.insert(0, current_script_dir)

# ===================== 线程安全的 Visitor 管理器 =====================
class VisitorManager:
    """SQLite 访问记录管理器。"""
    @classmethod
    def add_record(cls, record):
        item = dict(record)
        if 'path' in item:
            item['path'] = decode_path(item['path'])
        get_store().append('visits', item, Config.MAX_VISITOR_RECORDS)

    @classmethod
    def get_count(cls):
        return get_store().count_visits()

# ===================== 依赖导入 =====================
FLASK_AVAILABLE = False
message_board = None

try:
    from src import message_board as mb
    message_board = mb
    FLASK_AVAILABLE = True
    logger.info("✅ 留言板模块导入成功")
except ImportError as e:
    logger.warning(f"⚠️ 留言板模块导入失败：{e}")

# 导入认证模块获取用户信息
try:
    from src.auth import get_current_user, check_login_status
    AUTH_AVAILABLE = True
    logger.info("✅ 认证模块导入成功")
except ImportError as e:
    logger.warning(f"⚠️ 认证模块导入失败：{e}")
    AUTH_AVAILABLE = False
    # 定义空函数避免错误
    def get_current_user(session_id): return {}
    def check_login_status(session_id): return False

def count_visit():
    return get_store().counter(increment=True)


def get_total_visits():
    return get_store().counter()


def get_session_id_from_request(request_handler):
    """从请求中获取session_id"""
    # 从cookie获取
    cookie_header = request_handler.headers.get('Cookie', '')
    cookies = {}
    for cookie in cookie_header.split(';'):
        if '=' in cookie:
            key, value = cookie.strip().split('=', 1)
            cookies[key] = value

    session_id = cookies.get('session_id', '')
    if session_id:
        return session_id

    # 从Authorization头获取
    auth_header = request_handler.headers.get('Authorization', '')
    if auth_header.startswith('Session '):
        session_id = auth_header[8:].strip()
        return session_id

    return ''

def get_user_info_from_request(request_handler):
    """从请求中获取用户信息"""
    if not AUTH_AVAILABLE:
        return {}

    session_id = get_session_id_from_request(request_handler)
    if not session_id:
        return {}

    if not check_login_status(session_id):
        return {}

    return get_current_user(session_id)



def should_skip_log(path):
    """只记录页面和接口路由；资源文件及其查询参数不进入访问日志。"""
    path_only = unquote(urlparse(path).path).lower()
    if any(path_only == prefix or path_only.startswith(prefix + '/')
           for prefix in ('/static', '/media', '/banner')):
        return True
    if path_only.endswith('/'):
        return False
    extension = posixpath.splitext(path_only.rstrip('/'))[1]
    return bool(extension and extension not in ('.html', '.htm'))

# ===================== HTTP 处理器 =====================
class BeautifulDirectoryHandler(CGIHTTPRequestHandler):
    ip_request_cache = defaultdict(list)

    def __init__(self, *args, **kwargs):
        self.request_handled = False
        self.real_client_ip = None  # 存储真实IP
        self.proxy_parser = SimpleProxyProtocol()  # 使用纯Python解析器
        super().__init__(*args, **kwargs)

    def log_message(self, format, *args):
        """完全禁用默认日志"""
        pass

    def _reject_request(self, status, reason):
        self._security_blocked = True
        self.close_connection = True
        # repr 防止换行/控制字符伪造日志，不记录查询参数中的凭据。
        target = self.path.split('?', 1)[0][:400]
        logger.warning("🛡️ 拦截请求 IP=%s 方法=%s 路径=%r 原因=%s",
                       self.get_real_client_ip(), self.command, target, reason)
        self.send_error(status)
        return False

    def parse_request(self):
        """在路由、重定向或文件读取之前统一校验所有 HTTP 请求。"""
        if not super().parse_request():
            return False
        self._security_blocked = False
        try:
            normalized = self._safe_url_path(self.path)
        except (ValueError, UnicodeError):
            return self._reject_request(403, '不安全的路径编码或路径穿越')
        if self.is_protected_path(self.path):
            return self._reject_request(403, '敏感文件或非公开目录')
        if not self.is_allowed_path(self.path):
            return self._reject_request(404, '路径不在公开路由范围内')
        # Sarcopia's manual annotation workflow has moved to the project archive.
        retired_path = normalized.lower()
        retired_pages = (
            '/pages/projects/future-scholar/ct-qc.html',
            '/pages/projects/future-scholar/mask-editor.html',
            '/pages/future-scholar/ct-qc.html',
            '/pages/future-scholar/mask-editor.html',
        )
        if (retired_path.rstrip('/') == '/api/future-scholar'
                or retired_path.startswith('/api/future-scholar/')
                or retired_path.rstrip('/') in retired_pages
                or retired_path.startswith('/pages/projects/future-scholar/assets/')
                or retired_path.startswith('/pages/future-scholar/assets/')):
            return self._reject_request(410, 'Sarcopia manual annotation has been retired')
        if self.command not in ('GET', 'HEAD', 'POST', 'DELETE'):
            return self._reject_request(405, '不支持的 HTTP 方法')
        if self.command in ('POST', 'DELETE') and not normalized.startswith('/api/'):
            return self._reject_request(405, '只允许接口路由接收写入请求')

        admin_page = normalized == '/pages/admin' or normalized.startswith('/pages/admin/')
        admin_api = normalized == '/api/admin' or normalized.startswith('/api/admin/')
        if admin_page or admin_api:
            user = get_user_info_from_request(self)
            if not is_admin(user):
                if admin_page and not user and self.command in ('GET', 'HEAD'):
                    self.send_response(302)
                    self.send_header('Location', '/pages/login/index.html?redirect=' + quote(self.path, safe=''))
                    self.send_header('Cache-Control', 'no-store')
                    self.end_headers()
                elif admin_api:
                    self._send_json(403 if user else 401, {'error': '仅 hyper 账号可访问管理后台', 'need_login': not bool(user)})
                else:
                    self.send_error(403, 'Forbidden')
                self._security_blocked = True
                self.close_connection = True
                return False
            if admin_api and self.command != 'GET':
                self._send_json(405, {'error': '此后台仅支持读取数据'})
                self.close_connection = True
                return False

        # 此服务不支持 chunked 请求体；拒绝歧义长度，避免转发解析不一致。
        if self.headers.get_all('Transfer-Encoding'):
            return self._reject_request(400, '不支持 Transfer-Encoding 请求体')
        lengths = self.headers.get_all('Content-Length', [])
        if len(lengths) > 1 or (lengths and
                               (not lengths[0].isascii() or not lengths[0].isdigit())):
            return self._reject_request(400, '无效或重复的 Content-Length')
        if lengths:
            # 先比较字符串长度，避免超长整数转换异常。
            length_text = lengths[0].lstrip('0') or '0'
            body_limit = Config.MAX_POST_SIZE
            if len(length_text) > len(str(body_limit)) or int(length_text) > body_limit:
                return self._reject_request(413, '请求体超过大小限制')
            if self.command in ('GET', 'HEAD') and int(length_text):
                return self._reject_request(400, '页面读取不接受请求体')
            self.headers.replace_header('Content-Length', length_text)

        if self.command == 'HEAD' and self._is_restricted_project(self.path):
            user = get_user_info_from_request(self)
            username = str(user.get('username', '')).strip().lower() if user else ''
            if username not in FUTURE_SCHOLAR_ALLOWED_USERS:
                return self._reject_request(403 if user else 401, '项目访问需要授权账号')
        return True

    def is_cgi(self):
        """本站只提供静态文件和明确的 API，不执行磁盘上的 CGI。"""
        return False

    def send_response(self, code, message=None):
        self.status = code
        super().send_response(code, message)

    def send_header(self, keyword, value):
        if keyword.lower() == 'content-type':
            content_type = value.split(';', 1)[0].strip().lower()
            if content_type.startswith(('image/', 'video/', 'audio/', 'font/')) or content_type in (
                'text/css', 'text/javascript', 'application/javascript',
                'application/pdf', 'application/octet-stream', 'application/zip',
            ):
                self._response_is_asset = True
        super().send_header(keyword, value)

    def validate_path(self, path):
        """路径校验"""
        try:
            safe_path = os.path.realpath(path)
            server_root = os.path.realpath(self.directory)

            # 安全检查：防止路径遍历
            if os.path.commonpath([safe_path, server_root]) != server_root:
                self._log_access("🚫 非法路径", path, "403", "0.0")
                self.send_error(403, "Forbidden")
                return None

            return safe_path
        except Exception as e:
            logger.error(f"路径校验异常：{e}")
            self.send_error(400, "Bad Request")
            return None

    @staticmethod
    def _safe_url_path(path):
        # Decode once, as translate_path does; reject ambiguous encodings and
        # Windows aliases before any filesystem normalization.
        if not path.startswith('/') or path.startswith('//') or '#' in path:
            raise ValueError('Unsafe request target')
        decoded = unquote(urlparse(path).path, errors='strict')
        if '\\' in decoded or '//' in decoded:
            raise ValueError('Ambiguous path separators')
        parts = decoded.split('/')
        if any(part.startswith('.') or part.endswith((' ', '.')) or
               any(c in part for c in ':%<>|"?*#') or
               any(ord(c) < 32 or ord(c) == 127 for c in part) or
               part.split('.')[0].upper() in {
                   'CON', 'PRN', 'AUX', 'NUL', 'COM1', 'COM2', 'COM3', 'COM4',
                   'COM5', 'COM6', 'COM7', 'COM8', 'COM9', 'LPT1', 'LPT2',
                   'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9',
               }
               for part in parts if part):
            raise ValueError('Unsafe path')
        return '/'.join(parts)

    def _is_restricted_project(self, path):
        normalized = self._safe_url_path(path).lower()
        relative = os.path.relpath(os.path.realpath(self.translate_path(path)),
                                   os.path.realpath(self.directory)).replace('\\', '/').lower()
        return any(candidate == prefix or candidate.startswith(prefix + '/')
                   for candidate in (normalized, '/' + relative)
                   for prefix in ('/pages/future-scholar', '/pages/projects/future-scholar'))

    def is_protected_path(self, path):
        """Only public trees may resolve to files, including symlink targets."""
        try:
            normalized = self._safe_url_path(path)
            root = os.path.realpath(self.directory)
            local = os.path.realpath(self.translate_path(path))
            if os.path.commonpath([local, root]) != root:
                return True
            relative = os.path.relpath(local, root).replace('\\', '/')
            if relative == '.':
                return False
            parts = relative.lower().split('/')
            public = {'pages', 'static', 'media', 'banner', 'dwcc'}
            if parts[0] not in public and relative not in ('robots.txt', 'favicon.ico'):
                # Virtual routes are checked separately and never served here.
                if os.path.exists(local):
                    return True
                return normalized not in ('/', '/home', '/home/', '/home/index.html',
                                          '/talk', '/talk/', '/talk/comment.html',
                                          '/talk/ai-chat.html', '/visit-count') and not normalized.startswith('/api/')
            private_names = {'users.json', 'sessions.json', 'messages.json',
                             'visit_count.json', 'appsettings.json', 'config.json',
                             'credentials', '__pycache__', 'web.config', 'dockerfile',
                             'id_rsa', 'id_ed25519', 'authorized_keys'}
            private_suffixes = ('.py', '.pyc', '.php', '.phtml', '.asp', '.aspx', '.jsp',
                                '.cgi', '.pl', '.sh', '.bat', '.cmd', '.ps1', '.exe', '.dll',
                                '.key', '.pem', '.pfx', '.p12', '.crt', '.cer', '.jks',
                                '.db', '.sqlite', '.sqlite3', '.db-wal', '.db-shm',
                                '.bak', '.backup', '.old', '.save', '.orig', '.swp', '.swo',
                                '.log', '.sql', '.dump', '.ini', '.conf', '.config',
                                '.yml', '.yaml', '.toml')
            return any(part.startswith('.') or part in private_names or
                       part.endswith(private_suffixes) for part in parts)
        except (ValueError, OSError, UnicodeError):
            return True

    def send_head(self):
        # Shared by GET and HEAD: neither may fall back to private files.
        if self.is_protected_path(self.path):
            self.send_error(403, 'Forbidden')
            return None
        if not self.is_allowed_path(self.path):
            self.send_error(404, 'Not Found')
            return None
        if self._is_restricted_project(self.path):
            user = get_user_info_from_request(self)
            username = str(user.get('username', '')).strip().lower() if user else ''
            if username not in FUTURE_SCHOLAR_ALLOWED_USERS:
                self._reject_request(403 if user else 401, '项目访问需要授权账号')
                return None
        normalized = self._safe_url_path(self.path)
        asset_location = Config.LEGACY_ASSET_PATHS.get(normalized)
        if asset_location:
            query = urlparse(self.path).query
            if query:
                asset_location += '?' + query
            self.send_response(301)
            self.send_header('Location', asset_location)
            self.end_headers()
            return None
        for old_prefix, new_prefix in (
            ('/media/pages/devlog/', '/media/pages/projects/'),
            ('/media/resume/', '/media/pages/resume/'),
            ('/media/home/', '/media/pages/home/'),
            ('/pages/devlog/', '/pages/projects/'),
        ):
            if normalized == old_prefix.rstrip('/'):
                suffix = ''
            elif normalized.startswith(old_prefix):
                suffix = normalized[len(old_prefix):]
            else:
                continue
            query = urlparse(self.path).query
            location = new_prefix + quote(suffix, safe='/-._~')
            if query:
                location += '?' + query
            self.send_response(301)
            self.send_header('Location', location)
            self.end_headers()
            return None
        if normalized == '/':
            self.send_response(301)
            self.send_header('Location', '/pages/home/')
            self.end_headers()
            return None
        if normalized.startswith(('/api/', '/home', '/talk')) or normalized == '/visit-count':
            self.send_error(404, 'Not Found')
            return None
        return super().send_head()

    def is_allowed_path(self, path):
        """Match complete routes or directory boundaries, never '/' as a prefix."""
        try:
            normalized = self._safe_url_path(path)
        except (ValueError, UnicodeError):
            return False
        return any(normalized == allowed or
                   (allowed != '/' and allowed.endswith('/') and
                    (normalized == allowed.rstrip('/') or normalized.startswith(allowed)))
                   for allowed in Config.ALLOWED_PATHS)

    def get_real_client_ip(self):
        """
        获取经过 PROXY Protocol 或 HTTP 头解析后的真实客户端 IP
        优先顺序：
        1. X-Forwarded-For (HTTP 隧道)
        2. X-Real-IP (某些代理)
        3. PROXY Protocol (TCP 隧道)
        4. 原始 remote_addr
        """
        # 如果已经解析过，直接返回缓存
        if self.real_client_ip:
            return self.real_client_ip

        # Proxy Protocol 在服务器接受连接时已经解析，并写入 client_address。
        # 非本机地址优先于客户端可伪造的 HTTP 转发头。
        if hasattr(self, 'client_address'):
            peer_ip = self.client_address[0]
            if peer_ip not in ('127.0.0.1', '::1'):
                self.real_client_ip = peer_ip
                return peer_ip

        # 只有在有 headers 且是有效请求时才尝试获取真实IP
        if hasattr(self, 'headers') and self.headers and hasattr(self, 'command') and self.command:
            try:
                # X-Forwarded-For: client_ip, proxy1_ip, proxy2_ip
                x_forwarded = self.headers.get('X-Forwarded-For', '')
                if x_forwarded:
                    # 取第一个（最左边）的IP，即真实客户端IP
                    self.real_client_ip = x_forwarded.split(',')[0].strip()
                    return self.real_client_ip

                # 有些服务用 X-Real-IP
                x_real_ip = self.headers.get('X-Real-IP', '')
                if x_real_ip:
                    self.real_client_ip = x_real_ip.strip()
                    return self.real_client_ip

                # CloudFlare 用的头
                cf_connecting_ip = self.headers.get('CF-Connecting-IP', '')
                if cf_connecting_ip:
                    self.real_client_ip = cf_connecting_ip.strip()
                    return self.real_client_ip

                # Akamai 等用的头
                true_client_ip = self.headers.get('True-Client-IP', '')
                if true_client_ip:
                    self.real_client_ip = true_client_ip.strip()
                    return self.real_client_ip
            except Exception as e:
                pass

        # 回退到原始 remote_addr
        if hasattr(self, 'client_address'):
            self.real_client_ip = self.client_address[0]
        else:
            self.real_client_ip = 'unknown'

        return self.real_client_ip

    def _set_question_log(self, label, text):
        """只记录当前问题，转义控制字符，保持访问日志为单行。"""
        if isinstance(text, str) and text.strip():
            text = text.strip()
            if len(text) > 2000:
                text = text[:2000] + "…（已截断）"
            escaped = json.dumps(text, ensure_ascii=False)
            for char in ("\u0085", "\u2028", "\u2029"):
                escaped = escaped.replace(char, f"\\u{ord(char):04x}")
            self._question_log = f"{label}={escaped}"

    def _log_access(self, emoji, path, status, duration, username="", method="GET", visits=0, client_ip=""):
        """统一的访问日志输出 - 只记录路由，不记录静态资源"""
        # 解码路径显示中文
        decoded_path = decode_path(urlparse(path).path)

        # 跳过静态资源日志（图片、视频、CSS、JS等）
        if should_skip_log(path) or getattr(self, '_response_is_asset', False):
            return

        # 日期时间格式化
        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H:%M:%S")

        # 用户标识
        if username:
            user_part = f"👤 {username}"
        else:
            user_part = "👤 游客"

        # 构建日志消息（带日期、IP和城市，使用解码后的路径）
        if client_ip:
            city = query_ip_city(client_ip)
            log_msg = f"{date_str} {time_str} {emoji} {user_part} [{client_ip}] [{city}] | {method} {decoded_path} | {status} | {duration}ms | 👁️ {visits}"
        else:
            log_msg = f"{date_str} {time_str} {emoji} {user_part} | {method} {decoded_path} | {status} | {duration}ms | 👁️ {visits}"

        if getattr(self, '_question_log', ''):
            log_msg += f" | {self._question_log}"

        # 创建日志记录
        record = logging.LogRecord(
            name=logger.name,
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg=log_msg,
            args=(),
            exc_info=None
        )
        record.simple_msg = log_msg
        logger.handle(record)

    def handle_one_request(self):
        """处理单个请求"""
        if self.request_handled:
            return
        self.request_handled = True
        self._question_log = ""

        start_time = time.time()
        client_ip = None
        request_path = '/'
        request_method = 'GET'
        status_code = 200

        try:
            # 调用父类方法处理请求（这会设置 headers 等属性）
            super().handle_one_request()

            # 请求处理成功后的统计
            process_time = (time.time() - start_time) * 1000
            request_path = getattr(self, 'path', '/')
            request_method = getattr(self, 'command', 'GET')
            status_code = getattr(self, 'status', 200)

            # 无效请求只写安全告警；资源下载不进入页面访问日志、记录及计数。
            if not getattr(self, 'command', None) or getattr(self, '_security_blocked', False):
                return
            if should_skip_log(request_path) or getattr(self, '_response_is_asset', False):
                return

            # 获取真实IP（现在 headers 已经可用）
            client_ip = self.get_real_client_ip()

            # 访问频率只统计页面路径访问：排除 API、静态资源和影像请求。
            # 使用解析后的 path，避免查询参数导致扩展名判断失效。
            path_only = urlparse(request_path).path
            path_lower = path_only.lower()
            is_api_request = path_lower == '/api' or path_lower.startswith('/api/')
            is_static_request = should_skip_log(request_path)
            is_page_visit = request_method == 'GET' and not is_api_request and not is_static_request

            request_count = 0
            if is_page_visit:
                now = time.time()
                self.ip_request_cache[client_ip] = [
                    t for t in self.ip_request_cache[client_ip]
                    if now - t < Config.RATE_LIMIT_WINDOW
                ]
                self.ip_request_cache[client_ip].append(now)
                request_count = len(self.ip_request_cache[client_ip])

            # 获取用户信息
            username = ''
            if AUTH_AVAILABLE:
                try:
                    if hasattr(self, 'headers') and self.headers:
                        user_info = get_user_info_from_request(self)
                        username = user_info.get('username', '') if user_info else ''
                except Exception as e:
                    logger.debug(f"获取用户信息失败: {e}")

            # 计数访问
            is_static = any(path_lower.endswith(ext) for ext in Config.EXCLUDE_STATIC_EXT)
            is_exclude_path = any(request_path.startswith(path) for path in Config.EXCLUDE_COUNT_PATHS)

            if not is_static and not is_exclude_path:
                total_visits = count_visit()
            else:
                total_visits = get_total_visits()

            # ========== 保存访问记录到 site.db / visits（线程安全） ==========
            try:
                # 解码路径为中文
                decoded_request_path = decode_path(path_only)

                # 构建访问记录
                visit_record = {
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "ip": client_ip,
                    "user": username if username else "游客",
                    "path": decoded_request_path,  # 使用解码后的中文路径
                    "method": request_method,
                    "status": status_code
                }

                # 添加 User-Agent（如果存在）
                if hasattr(self, 'headers') and self.headers:
                    ua = self.headers.get('User-Agent', '')
                    if ua:
                        visit_record["user_agent"] = ua[:300]  # 限制长度

                # 使用线程安全的 VisitorManager 保存
                VisitorManager.add_record(visit_record)

            except Exception as e:
                logger.debug(f"保存访问记录失败: {e}")
            # =============================================================

            # 根据路径选择emoji（使用解码后的路径判断）
            decoded_path_for_emoji = decode_path(request_path)
            if decoded_path_for_emoji == '/':
                emoji = "🏠"
            elif decoded_path_for_emoji.startswith('/api/'):
                emoji = "⚡"
            elif decoded_path_for_emoji == '/talk':
                emoji = "💬"
            elif decoded_path_for_emoji == '/visit-count':
                emoji = "📊"
            elif decoded_path_for_emoji.endswith(('.html', '.htm')):
                emoji = "📄"
            elif decoded_path_for_emoji.endswith(('.jpg', '.png', '.gif', '.jpeg')):
                emoji = "🖼️"
            elif decoded_path_for_emoji.endswith(('.css', '.js')):
                emoji = "🎨"
            elif any(decoded_path_for_emoji.startswith(p) for p in ['/home', '/pages', '/login']):
                emoji = "📁"
            else:
                emoji = "📡"

            # 根据状态码添加标识
            if status_code >= 400:
                emoji = "❌"
            elif status_code == 304:
                emoji = "🔄"

            # 输出单行日志（带真实IP）- 自动过滤静态资源
            self._log_access(
                emoji=emoji,
                path=request_path,
                status=str(status_code),
                duration=f"{process_time:.1f}",
                username=username,
                method=request_method,
                visits=total_visits,
                client_ip=client_ip
            )

            # 限流警告（使用真实IP）
            if is_page_visit and request_count > Config.RATE_LIMIT:
                logger.warning(f"⚠️ {client_ip} {request_count}次/{Config.RATE_LIMIT_WINDOW}秒")

        except Exception as e:
            # 如果还没获取到 client_ip，重新获取一下
            if not client_ip:
                try:
                    client_ip = self.get_real_client_ip()
                except:
                    client_ip = 'unknown'

            logger.error(f"请求处理异常 {client_ip} - {request_path} - {str(e)}")

            # 如果还没有发送响应，尝试发送500错误
            if not hasattr(self, 'status') or self.status < 400:
                try:
                    self.send_error(500, "Internal Server Error")
                except:
                    pass

    @staticmethod
    def get_template():
        """目录美化模板"""
        return """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>{title}</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        * {{ margin:0; padding:0; box-sizing:border-box; font-family:Microsoft YaHei }}
        body {{ background:#f8f9fa; padding:40px }}
        .container {{ max-width:1000px; margin:0 auto; background:white; padding:30px; border-radius:12px; box-shadow:0 2px 10px rgba(0,0,0,0.1) }}
        h1 {{ color:#6a5acd; margin-bottom:20px }}
        .breadcrumb {{ margin:20px 0; display:flex; gap:8px }}
        .back-btn {{ display:inline-block; padding:8px 16px; background:#6a5acd; color:white; border-radius:8px; text-decoration:none }}
        .items {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(200px,1fr)); gap:15px }}
        .item {{ display:flex; align-items:center; padding:12px; border-radius:8px; text-decoration:none; color:#495057 }}
        .folder i {{ color:#ffc107 }}
        .file i {{ color:#6a5acd }}
    </style>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="/pages/_shared/site-theme.css?v=20260911-centered-navigation">
</head>
<body data-site-theme="garden" data-page-kind="directory">
<nav class="page-controls" aria-label="页面快捷导航"><a href="/pages/home/" data-page-back><svg aria-hidden="true" viewBox="0 0 24 24"><path d="m10 5-7 7 7 7M3 12h18"/></svg><span>返回上一页</span></a><a href="/pages/home/"><svg aria-hidden="true" viewBox="0 0 24 24"><path d="m3 10 9-7 9 7M5 9v12h5v-7h4v7h5V9"/></svg><span>首页</span></a></nav>
<nav class="site-navigation" aria-label="全站导航"><a class="site-brand" href="/pages/home/"><img src="/pages/home/hyper.png" alt="" width="38" height="38"><span>hyper.</span></a><div class="site-nav-links"><a href="/pages/home/#categories">探索分类</a><a href="/pages/resume/index.html">个人简介</a><a href="/pages/talk/comment.html">留言板</a></div></nav>

    <div class="container">
        <h1>📂 目录列表: {path}</h1>
        <div class="breadcrumb">{breadcrumb}</div>
        {back_button}
        <div class="items">{items}</div>
    </div>

<script src="/pages/_shared/page-navigation.js?v=20260911-1" defer></script>
</body>
</html>
        """

    def do_GET(self):
        """处理GET请求"""
        parsed = urlparse(self.path)
        path = parsed.path
        access_path = decode_path(path)
        access_path_lower = access_path.lower()

        if path.startswith('/home/') and path not in ('/home/', '/home/index.html'):
            self.send_response(302)
            self.send_header('Location', '/pages' + path + ('?' + parsed.query if parsed.query else ''))
            self.end_headers()
            return

        # 路径白名单检查（防止扫描）
        if not self.is_allowed_path(path):
            logger.warning(f"拦截非法路径扫描: {path}")
            self.send_error(404, "Not Found")
            return

        # 检查是否是受保护的路径
        if self.is_protected_path(path):
            logger.warning(f"阻止访问受保护路径: {path}")
            self.send_error(403, "Forbidden")
            return

        future_scholar_new = (
            access_path_lower == '/pages/projects/future-scholar'
            or access_path_lower.startswith('/pages/projects/future-scholar/')
        )
        future_scholar_old = (
            access_path_lower == '/pages/future-scholar'
            or access_path_lower.startswith('/pages/future-scholar/')
        )
        if future_scholar_new or future_scholar_old:
            user = get_user_info_from_request(self)
            username = str(user.get('username', '')).strip().lower() if user else ''
            if username not in FUTURE_SCHOLAR_ALLOWED_USERS:
                status = 401 if not user else 403
                message = '请先登录授权账号' if not user else '当前账号无权访问此项目'
                body = (
                    '<!doctype html><meta charset="utf-8"><title>访问受限</title>'
                    '<body style="font:18px system-ui;text-align:center;padding:12vh 20px">'
                    f'<h1>{status}</h1><p>{html.escape(message)}</p>'
                    '<p><a href="/pages/login/index.html">前往登录</a></p></body>'
                ).encode('utf-8')
                self.send_response(status)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if future_scholar_old:
                suffix = access_path[len('/pages/Future-Scholar'):]
                location = '/pages/projects/Future-Scholar' + suffix
                if parsed.query:
                    location += '?' + parsed.query
                self.send_response(301)
                self.send_header('Location', location)
                self.end_headers()
                return

        # 处理/talk路径，返回静态页面
        if path in ('/talk', '/talk/', '/talk/comment.html', '/pages/talk', '/pages/talk/', '/pages/talk/comment.html'):
            self._serve_talk_static_page()
            return

        # 处理 AI 聊天页面
        if path in ('/talk/ai-chat.html', '/pages/talk/ai-chat.html'):
            self._serve_ai_chat_page()
            return

        # 访问计数接口
        if path == '/visit-count':
            self._handle_visit_count()
            return

        if path.startswith('/api/admin/'):
            self._handle_admin_get(path)
            return


        # 访问分析页面数据（/pages/visit/）
        if path in ('/api/visit-stats', '/api/visit-stats/'):
            self._handle_visit_stats()
            return
        if path in ('/api/visit-detail', '/api/visit-detail/'):
            self._handle_visit_detail()
            return

        # 转发API请求到Flask
        if FLASK_AVAILABLE and path.startswith('/api/'):
            self._forward_to_flask()
            return

        # 首页重定向
        if path in ('', '/', '/home', '/home/', '/home/index.html', '/pages/home', '/pages/home/index.html'):
            self.send_response(301)
            self.send_header('Location', '/pages/home/' + ('?' + parsed.query if parsed.query else ''))
            self.end_headers()
            return

        # 静态文件/目录
        local = self.translate_path(self.path)
        if not self.validate_path(local):
            return
        super().do_GET()

    def do_POST(self):
        """处理POST请求"""
        parsed = urlparse(self.path)
        path = parsed.path

        # 路径白名单检查（防止扫描）
        if not self.is_allowed_path(path):
            logger.warning(f"拦截非法POST扫描: {path}")
            self.send_error(404, "Not Found")
            return

        if self.is_protected_path(self.path):
            logger.warning(f"阻止POST访问受保护路径: {self.path}")
            self.send_error(403, "Forbidden")
            return



        local = self.translate_path(self.path)
        if not self.validate_path(local):
            return

        if FLASK_AVAILABLE and self.path.startswith('/api/'):
            self._forward_to_flask()
            return
        super().do_POST()

    def _send_json(self, status, payload):
        """发送 UTF-8 JSON 响应。"""
        body = json.dumps(payload, ensure_ascii=False, allow_nan=False,
                          separators=(',', ':')).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)

    def _handle_admin_get(self, path):
        user = get_user_info_from_request(self)
        if not is_admin(user):
            self._send_json(403 if user else 401, {'error': '仅 hyper 账号可访问管理后台'})
            return
        try:
            if path == '/api/admin/tables':
                payload = admin_overview()
            elif path == '/api/admin/rows':
                params = parse_qs(urlparse(self.path).query)
                payload = admin_browse(
                    (params.get('table') or ['messages'])[0],
                    page=int((params.get('page') or ['1'])[0]),
                    page_size=int((params.get('page_size') or ['50'])[0]),
                    query=(params.get('q') or [''])[0].strip(),
                )
            else:
                self._send_json(404, {'error': '接口不存在'})
                return
            self._send_json(200, payload)
        except ValueError as exc:
            self._send_json(400, {'error': str(exc)})
        except Exception:
            logger.exception('读取管理后台数据失败')
            self._send_json(500, {'error': '数据暂时不可用，请重试'})



    def _handle_visit_stats(self):
        """返回访问分析页面所需数据（默认要求登录，避免公开访客 IP）。"""
        user = get_user_info_from_request(self)
        if VISIT_STATS_REQUIRE_LOGIN:
            if not user:
                self._send_json(401, {'need_login': True, 'error': '请先登录后再查看访问分析'})
                return
            if VISIT_STATS_ALLOWED_USERS:
                username = str(user.get('username', '')).strip().lower()
                if username not in VISIT_STATS_ALLOWED_USERS:
                    self._send_json(403, {'error': '当前账号无权查看访问分析'})
                    return
        try:
            from src.analyze_visitor import get_stats_payload
            refresh = 'refresh=1' in urlparse(self.path).query
            payload = get_stats_payload(refresh=refresh)
        except Exception as exc:
            logger.exception("生成访问分析数据失败")
            self._send_json(500, {'error': f'生成访问分析失败：{exc}'})
            return
        # 逐个请求注入查看者信息，不写进共享缓存。
        username = str(user.get('username', '')).strip() if user else ''
        payload = dict(payload)
        payload['viewer'] = {
            'username': username,
            'can_view_detail': username.lower() in VISIT_DETAIL_ALLOWED_USERS,
        }
        self._send_json(200, payload)

    def _handle_visit_detail(self):
        """单个 IP 的详细访问记录，仅 VISIT_DETAIL_ALLOWED_USERS 内的账号可见。"""
        user = get_user_info_from_request(self)
        if not user:
            self._send_json(401, {'need_login': True, 'error': '请先登录后再查看详细记录'})
            return
        username = str(user.get('username', '')).strip().lower()
        if username not in VISIT_DETAIL_ALLOWED_USERS:
            self._send_json(403, {'error': '只有 hyper 账号可以查看访客详细记录'})
            return

        query = parse_qs(urlparse(self.path).query)
        ip = (query.get('ip') or [''])[0]
        try:
            limit = int((query.get('limit') or ['200'])[0])
            offset = int((query.get('offset') or ['0'])[0])
        except ValueError:
            limit, offset = 200, 0
        try:
            from src.analyze_visitor import build_ip_detail
            detail = build_ip_detail(ip, limit=limit, offset=offset)
        except Exception as exc:
            logger.exception("生成 IP 详细记录失败")
            self._send_json(500, {'error': f'生成 IP 详细记录失败：{exc}'})
            return
        if detail is None:
            self._send_json(400, {'error': 'IP 地址无效'})
            return
        self._send_json(200, detail)




    def do_DELETE(self):
        """处理DELETE请求"""
        parsed = urlparse(self.path)
        path = parsed.path

        # 路径白名单检查（防止扫描）
        if not self.is_allowed_path(path):
            logger.warning(f"拦截非法DELETE扫描: {path}")
            self.send_error(404, "Not Found")
            return

        if self.is_protected_path(self.path):
            logger.warning(f"阻止DELETE访问受保护路径: {self.path}")
            self.send_error(403, "Forbidden")
            return

        local = self.translate_path(self.path)
        if not self.validate_path(local):
            return

        if FLASK_AVAILABLE and self.path.startswith('/api/'):
            self._forward_to_flask()
            return
        super().do_DELETE()

    def _serve_talk_static_page(self):
        """返回留言板静态页面"""
        talk_html_path = os.path.join(current_script_dir, 'pages', 'talk', 'comment.html')
        try:
            with open(talk_html_path, 'rb') as f:
                self.send_response(200)
                self.send_header("Content-type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(f.read())
        except FileNotFoundError:
            logger.error(f"留言板静态页面不存在：{talk_html_path}")
            self.send_error(404, "Not Found")
        except Exception as e:
            logger.error(f"读取留言板页面失败：{e}")
            self.send_error(500, "Internal Server Error")

    def _serve_ai_chat_page(self):
        """返回 AI 聊天静态页面"""
        ai_chat_path = os.path.join(current_script_dir, 'pages', 'talk', 'ai-chat.html')
        try:
            with open(ai_chat_path, 'rb') as f:
                self.send_response(200)
                self.send_header("Content-type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(f.read())
        except FileNotFoundError:
            logger.error(f"AI 聊天页面不存在：{ai_chat_path}")
            self.send_error(404, "Not Found")
        except Exception as e:
            logger.error(f"读取 AI 聊天页面失败：{e}")
            self.send_error(500, "Internal Server Error")

    def _handle_visit_count(self):
        """处理访问计数请求"""
        total = get_total_visits()
        self.send_response(200)
        self.send_header("Content-type", "application/json; charset=utf-8")
        # 访问数是实时数据，禁止浏览器/CDN复用曾经缓存的 0。
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.end_headers()

        self.wfile.write(json.dumps({
            "code": 200,
            "message": "success",
            "data": {
                "count": total,
                "total_visits": total,
                "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        }, ensure_ascii=False).encode('utf-8'))

    def _forward_to_flask(self):
        """转发请求到Flask"""
        if not FLASK_AVAILABLE or message_board is None:
            self.send_error(500, "Internal Server Error")
            return
        try:
            data = b""
            if self.command in ["POST", "PUT", "DELETE"]:
                cl = int(self.headers.get("Content-Length", 0))
                if 0 < cl < Config.MAX_POST_SIZE:
                    data = self.rfile.read(cl)

            if self.command == "POST" and urlparse(self.path).path == '/api/ollama/chat':
                try:
                    payload = json.loads(data)
                    messages = payload.get('messages', []) if isinstance(payload, dict) else []
                    if isinstance(messages, list):
                        for message in reversed(messages):
                            if isinstance(message, dict) and message.get('role') == 'user':
                                self._set_question_log("AI提问", message.get('content'))
                                break
                except (ValueError, UnicodeDecodeError):
                    pass

            logger.debug(f"转发请求到 Flask: {self.command} {self.path}")

            with message_board.app.test_client() as client:
                headers = dict(self.headers)
                # 移除可能导致问题的 Host 头
                headers.pop('Host', None)
                environ = {'REMOTE_ADDR': self.get_real_client_ip()}

                if self.command == "GET":
                    resp = client.get(self.path, headers=headers, environ_overrides=environ)
                elif self.command == "DELETE":
                    resp = client.delete(self.path, headers=headers, environ_overrides=environ)
                else:
                    content_type = self.headers.get('Content-Type', 'application/x-www-form-urlencoded')
                    resp = client.post(self.path, data=data, headers=headers, content_type=content_type, environ_overrides=environ)

            self.send_response(resp.status_code)
            for k, v in resp.headers.items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(resp.data)
        except Exception as e:
            logger.error(f"Flask转发异常：{e}")
            self.send_response(500)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            error_html = """
            <html>
            <head><title>500 服务器内部错误</title><link rel="stylesheet" href="/pages/_shared/site-theme.css?v=20260911-centered-navigation"></head>
            <body data-site-theme='garden' style='padding:40px'>
<nav class="page-controls" aria-label="页面快捷导航"><a href="/pages/home/" data-page-back><svg aria-hidden="true" viewBox="0 0 24 24"><path d="m10 5-7 7 7 7M3 12h18"/></svg><span>返回上一页</span></a><a href="/pages/home/"><svg aria-hidden="true" viewBox="0 0 24 24"><path d="m3 10 9-7 9 7M5 9v12h5v-7h4v7h5V9"/></svg><span>首页</span></a></nav>
                <h1>500 接口请求处理失败</h1>
                <p>请检查服务是否正常运行</p>

<script src="/pages/_shared/page-navigation.js?v=20260911-1" defer></script>
</body>
            </html>
            """
            self.wfile.write(error_html.encode('utf-8'))

    def list_directory(self, path):
        """目录列表美化"""
        if not self.validate_path(path):
            return None
        try:
            lst = os.listdir(path)
        except OSError as e:
            logger.error(f"读取目录 {path} 失败：{e}")
            self.send_error(404)
            return None

        lst = [name for name in lst if not self.is_protected_path(
            urlparse(self.path).path.rstrip('/') + '/' + quote(name))]
        lst.sort(key=lambda x: (not os.path.isdir(os.path.join(path, x)), x.lower()))
        cur = unquote(urlparse(self.path).path)
        if not cur.endswith('/'):
            cur += '/'

        bread = []
        p = ''
        bread.append('<a href="/"><i class="fas fa-home"></i> 首页</a>')
        for part in cur.strip('/').split('/'):
            if part:
                p += part + '/'
                bread.append(f'<span>/</span><a href="/{quote(p, safe="/")}">{html.escape(part)}</a>')

        back = ''
        if cur != '/':
            parent = os.path.dirname(cur.rstrip('/')).replace('\\', '/') or '/'
            back = f'<a href="{quote(parent, safe="/")}" class="back-btn"><i class="fas fa-arrow-left"></i> 返回上一级</a>'

        items = []
        for name in lst:
            fp = os.path.join(path, name)
            url = quote(cur, safe='/') + quote(name, safe='')
            safe_name = html.escape(name)
            if os.path.isdir(fp):
                items.append(f'''
                <a href="{url}/" class="item folder">
                    <i class="fas fa-folder"></i>
                    <div class="item-name">{safe_name}</div>
                </a>''')
            else:
                file_ext = os.path.splitext(name)[1].lower()
                icon = 'fas fa-file'
                if file_ext in ['.html', '.htm']: icon = 'fas fa-file-html'
                elif file_ext in ['.jpg', '.jpeg', '.png']: icon = 'fas fa-file-image'
                elif file_ext in ['.mp4', '.avi']: icon = 'fas fa-file-video'
                items.append(f'''
                <a href="{url}" class="item file">
                    <i class="{icon}"></i>
                    <div class="item-name">{safe_name}</div>
                </a>''')

        page_html = self.get_template().format(
            title=f"目录列表 - {html.escape(cur)}",
            path=html.escape(cur),
            breadcrumb=''.join(bread),
            back_button=back,
            items=''.join(items)
        )
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(page_html.encode('utf-8'))
        return None

# ===================== 服务器 =====================
class DualStackServer(ThreadingHTTPServer):
    tls_context = None

    def server_bind(self):
        """绑定服务器"""
        try:
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.settimeout(10)
            with contextlib.suppress(Exception):
                self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
            super().server_bind()
            logger.info(f"✅ 服务器绑定成功：{self.server_address}")
        except Exception as e:
            logger.error(f"服务器绑定异常：{e}")
            raise

    def get_request(self):
        """先解析 frpc 的 Proxy Protocol，再进行 TLS 握手。"""
        request, client_address = self.socket.accept()
        proxy_ip = SimpleProxyProtocol.parse(request)
        if proxy_ip:
            client_address = (proxy_ip, client_address[1])

        if self.tls_context:
            try:
                request = self.tls_context.wrap_socket(request, server_side=True)
            except Exception:
                with contextlib.suppress(Exception):
                    request.close()
                raise

        return request, client_address

    def finish_request(self, request, client_address):
        """处理请求"""
        try:
            request.settimeout(10)
            super().finish_request(request, client_address)
        except Exception as e:
            logger.error(f"请求处理超时 {client_address}：{e}")
            with contextlib.suppress(Exception):
                request.close()


# ===================== 启动 =====================
def start_visitor_report(force=False):
    """启动访客分析后台任务：启动时生成一次，之后每 24 小时覆盖同一个文件。

    force=True 时忽略文件时间戳，启动后立刻重新生成。
    设置环境变量 DISABLE_VISITOR_REPORT=1 可关闭（自动化测试用）。
    """
    if os.environ.get('DISABLE_VISITOR_REPORT') == '1':
        return None
    try:
        from src.analyze_visitor import DEFAULT_REPORT_FILE, start_daily_report_thread
    except Exception as exc:
        logger.error(f"访客分析模块加载失败：{exc}")
        return None
    start_daily_report_thread(force=force)
    return DEFAULT_REPORT_FILE


def run_server():
    """启动服务器"""
    get_store()
    report_file = start_visitor_report(force=Config.FORCE_REPORT)
    if Config.RESET_VISITS:
        try:
            get_store().counter(reset=True)
            logger.info("✅ 访问计数已重置为0")
        except Exception as e:
            logger.error(f"重置计数失败：{e}")

    server_dir = Config.SERVER_DIR or current_script_dir
    os.chdir(server_dir)
    handler = partial(BeautifulDirectoryHandler, directory=server_dir)
    httpd = DualStackServer((Config.HOST, Config.PORT), handler)
    scheme = "http"
    if Config.CERT_FILE and Config.KEY_FILE:
        tls_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls_context.minimum_version = ssl.TLSVersion.TLSv1_2
        tls_context.load_cert_chain(
            certfile=Config.CERT_FILE,
            keyfile=Config.KEY_FILE,
        )
        httpd.tls_context = tls_context
        scheme = "https"
    httpd.timeout = 10
    httpd.daemon_threads = True

    local_ip = socket.gethostbyname(socket.gethostname())
    current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print("\n" + "="*60)
    print(f"🚀 服务启动成功！ {current_date}")
    print("="*60)
    print(f"📌 本地访问: {scheme}://localhost:{Config.PORT}")
    print(f"📌 外网访问: {scheme}://{local_ip}:{Config.PORT}")
    print(f"📌 留言板: {scheme}://localhost:{Config.PORT}/pages/talk/comment.html")
    print(f"📌 AI 助手: {scheme}://localhost:{Config.PORT}/pages/talk/ai-chat.html")
    print(f"📌 计数查询: {scheme}://localhost:{Config.PORT}/visit-count")
    if scheme == "https":
        print(f"📌 TLS 证书: {os.path.abspath(Config.CERT_FILE)}")
    print(f"📌 根目录: {os.path.abspath(server_dir)}")
    print(f"📌 真实IP获取: ✅ X-Forwarded-For / X-Real-IP / PROXY Protocol (自动识别)")
    if report_file:
        print(f"📄 访客分析报告: {os.path.relpath(report_file, server_dir)}（启动时生成，每 24 小时覆盖）")
    print("="*60)
    print("📊 访问日志格式: [日期 时间] 图标 用户 [真实IP] | 方法 路径 | 状态 | 耗时 | 访问量")
    print("📊 静态资源过滤: 不记录图片/视频/CSS/JS等文件")
    print(f"📊 访问记录保存: data/site.db（SQLite，当前 {VisitorManager.get_count()} 条）")
    print("📊 路径格式: URL编码已自动转换为中文")
    print("="*60 + "\n")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 服务正在停止...")
        httpd.server_close()
        print("✅ 服务已停止")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="个人Vlog HTTP/HTTPS服务端")
    parser.add_argument("-p", "--port", type=int, default=8000, help="监听端口")
    parser.add_argument("-H", "--host", type=str, default="0.0.0.0", help="监听地址")
    parser.add_argument("--certfile", help="TLS 证书文件（PEM 格式，必须与 --keyfile 同时使用）")
    parser.add_argument("--keyfile", help="TLS 私钥文件（PEM 格式，必须与 --certfile 同时使用）")
    parser.add_argument("--reset-visits", action="store_true", help="重置访问次数")
    parser.add_argument("--force-report", action="store_true",
                        help="启动时立即重新生成访客分析报告（默认每天最多生成一次）")
    args = parser.parse_args()

    if bool(args.certfile) != bool(args.keyfile):
        parser.error("--certfile 和 --keyfile 必须同时提供")
    for option, path in (("--certfile", args.certfile), ("--keyfile", args.keyfile)):
        if path and not os.path.isfile(path):
            parser.error(f"{option} 指定的文件不存在: {path}")

    Config.PORT = args.port
    Config.HOST = args.host
    Config.CERT_FILE = os.path.abspath(args.certfile) if args.certfile else None
    Config.KEY_FILE = os.path.abspath(args.keyfile) if args.keyfile else None
    Config.RESET_VISITS = args.reset_visits 
    Config.FORCE_REPORT = args.force_report

    run_server()
