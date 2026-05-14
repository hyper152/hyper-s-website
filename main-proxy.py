# -*- coding: utf-8 -*-
"""
个人Vlog HTTP服务端（支持 PROXY Protocol 获取真实IP）
✅ 纯 Python 实现 PROXY Protocol 解析，无需第三方库
✅ 极简日志格式，单行显示
✅ 添加emoji标识，一目了然
✅ 响应时间显示，便于性能监控
✅ 用户状态实时显示
✅ 日志带日期显示
"""
import socket
import sys
import os
import time
import json
import logging
import argparse
import contextlib
import struct
from functools import partial
from datetime import datetime
from collections import defaultdict
from http.server import CGIHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

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

# ===================== 配置抽离 =====================
class Config:
    HOST = "0.0.0.0"
    PORT = 8000
    SERVER_DIR = None

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
        '/', '/home/', '/talk', '/login/', '/pages/',
        '/static/', '/api/', '/visit-count', '/banner/',
        '/favicon.ico', '/HappyNewYear/', '/dwcc/'
    ]

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
home_dir = os.path.join(current_script_dir, 'home')
talk_dir = os.path.join(current_script_dir, 'talk')

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

sys.path.insert(0, src_dir)

# ===================== 依赖导入 =====================
FLASK_AVAILABLE = False
try:
    import message_board
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

# 简化访问计数（内置版，无需额外模块）
VISIT_COUNT_FILE = os.path.join(data_dir, 'visit_count.json')
def count_visit():
    """计数访问量"""
    try:
        if not os.path.exists(VISIT_COUNT_FILE):
            with open(VISIT_COUNT_FILE, 'w', encoding='utf-8') as f:
                json.dump({"count": 0, "total_visits": 0}, f)
        
        with open(VISIT_COUNT_FILE, 'r+', encoding='utf-8') as f:
            data = json.load(f)
            current_count = data.get("count", 0)
            data["count"] = current_count + 1
            data["total_visits"] = data["count"]  # 同步total_visits
            data["update_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.seek(0)
            json.dump(data, f, ensure_ascii=False, indent=4)
            f.truncate()
        return data["count"]
    except Exception as e:
        logger.error(f"计数失败：{e}")
        return 0

def get_total_visits():
    """获取总访问量"""
    try:
        if not os.path.exists(VISIT_COUNT_FILE):
            return 0
        with open(VISIT_COUNT_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get("count", data.get("total_visits", 0))
    except Exception as e:
        logger.error(f"获取计数失败：{e}")
        return 0

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

    def validate_path(self, path):
        """路径校验"""
        try:
            safe_path = os.path.abspath(path)
            server_root = os.path.abspath(self.directory)
            
            # 安全检查：防止路径遍历
            if not safe_path.startswith(server_root):
                self._log_access("🚫 非法路径", path, "403", "0.0")
                self.send_error(403, "禁止访问：非法路径")
                return None
                
            return safe_path
        except Exception as e:
            logger.error(f"路径校验异常：{e}")
            self.send_error(400, "路径格式错误")
            return None

    def is_protected_path(self, path):
        """检查是否是受保护的路径"""
        for protected_dir in Config.PROTECTED_DIRS:
            if path.startswith(protected_dir):
                return True
        
        for sensitive_file in Config.SENSITIVE_FILES:
            if path.endswith(f'/data/{sensitive_file}') or path.endswith(f'\\data\\{sensitive_file}'):
                return True
        
        return False

    def is_allowed_path(self, path):
        """检查路径是否在白名单内（防止扫描）"""
        # 如果是静态资源文件，直接放行
        if any(path.lower().endswith(ext) for ext in Config.EXCLUDE_STATIC_EXT):
            return True
            
        # 检查是否以允许的路径开头
        for allowed in Config.ALLOWED_PATHS:
            if path.startswith(allowed):
                return True
        
        # 如果是目录浏览请求（以/结尾），检查父路径
        if path.endswith('/'):
            parent = path.rstrip('/')
            for allowed in Config.ALLOWED_PATHS:
                if parent.startswith(allowed):
                    return True
        
        return False

    def get_real_client_ip(self):
        """获取经过 PROXY Protocol 解析后的真实客户端 IP"""
        # 如果已经解析过，直接返回缓存
        if self.real_client_ip:
            return self.real_client_ip
        
        # 尝试解析 PROXY Protocol
        try:
            real_ip = self.proxy_parser.parse(self.connection)
            if real_ip:
                self.real_client_ip = real_ip
                return real_ip
        except Exception as e:
            pass
        
        # 回退到原始 remote_addr
        self.real_client_ip = self.client_address[0]
        return self.real_client_ip

    def _log_access(self, emoji, path, status, duration, username="", method="GET", visits=0, client_ip=""):
        """统一的访问日志输出 - 极简单行（带日期和IP）"""
        # 日期时间格式化
        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H:%M:%S")
        
        # 用户标识
        if username:
            user_part = f"👤 {username}"
        else:
            user_part = "👤 游客"
        
        # 构建日志消息（带日期和IP）
        if client_ip:
            log_msg = f"{date_str} {time_str} {emoji} {user_part} [{client_ip}] | {method} {path} | {status} | {duration}ms | 👁️ {visits}"
        else:
            log_msg = f"{date_str} {time_str} {emoji} {user_part} | {method} {path} | {status} | {duration}ms | 👁️ {visits}"
        
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

        start_time = time.time()
        client_ip = None
        request_path = '/'
        request_method = 'GET'
        status_code = 200
        
        try:
            # 先获取真实IP（在调用父类之前）
            client_ip = self.get_real_client_ip()
            
            # 调用父类方法处理请求
            super().handle_one_request()
            
            # 请求处理成功后的统计
            process_time = (time.time() - start_time) * 1000
            request_path = getattr(self, 'path', '/')
            request_method = getattr(self, 'command', 'GET')
            status_code = getattr(self, 'status', 200)
            
            # 限流记录（使用真实 IP）
            now = time.time()
            self.ip_request_cache[client_ip] = [t for t in self.ip_request_cache[client_ip] if now - t < Config.RATE_LIMIT_WINDOW]
            self.ip_request_cache[client_ip].append(now)
            
            # 获取用户信息（安全地检查 headers 是否存在）
            username = ''
            if AUTH_AVAILABLE:
                try:
                    if hasattr(self, 'headers') and self.headers:
                        user_info = get_user_info_from_request(self)
                        username = user_info.get('username', '') if user_info else ''
                except Exception as e:
                    logger.debug(f"获取用户信息失败: {e}")
            
            # 计数访问
            is_static = any(request_path.lower().endswith(ext) for ext in Config.EXCLUDE_STATIC_EXT)
            is_exclude_path = any(request_path.startswith(path) for path in Config.EXCLUDE_COUNT_PATHS)
            
            if not is_static and not is_exclude_path:
                total_visits = count_visit()
            else:
                total_visits = get_total_visits()

            # 根据路径选择emoji
            if request_path == '/':
                emoji = "🏠"
            elif request_path.startswith('/api/'):
                emoji = "⚡"
            elif request_path == '/talk':
                emoji = "💬"
            elif request_path == '/visit-count':
                emoji = "📊"
            elif request_path.endswith(('.html', '.htm')):
                emoji = "📄"
            elif request_path.endswith(('.jpg', '.png', '.gif', '.jpeg')):
                emoji = "🖼️"
            elif request_path.endswith(('.css', '.js')):
                emoji = "🎨"
            elif any(request_path.startswith(p) for p in ['/home', '/pages', '/login']):
                emoji = "📁"
            else:
                emoji = "📡"

            # 根据状态码添加标识
            if status_code >= 400:
                emoji = "❌"
            elif status_code == 304:
                emoji = "🔄"

            # 输出单行日志（带真实IP）
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
            request_count = len(self.ip_request_cache[client_ip])
            if request_count > Config.RATE_LIMIT:
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
</head>
<body>
    <div class="container">
        <h1>📂 目录列表: {path}</h1>
        <div class="breadcrumb">{breadcrumb}</div>
        {back_button}
        <div class="items">{items}</div>
    </div>
</body>
</html>
        """

    def do_GET(self):
        """处理GET请求"""
        parsed = urlparse(self.path)
        path = parsed.path

        # 路径白名单检查（防止扫描）
        if not self.is_allowed_path(path):
            logger.warning(f"拦截非法路径扫描: {path}")
            self.send_error(404, "Not Found")
            return

        # 检查是否是受保护的路径
        if self.is_protected_path(path):
            logger.warning(f"阻止访问受保护路径: {path}")
            self.send_error(403, "禁止访问")
            return

        # 处理/talk路径，返回静态页面
        if path == '/talk':
            self._serve_talk_static_page()
            return

        # 访问计数接口
        if path == '/visit-count':
            self._handle_visit_count()
            return

        # 转发API请求到Flask
        if FLASK_AVAILABLE and path.startswith('/api/'):
            self._forward_to_flask()
            return

        # 首页重定向
        if path in ('', '/'):
            self.send_response(301)
            self.send_header('Location', '/home/')
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
            self.send_error(403, "禁止访问")
            return
            
        local = self.translate_path(self.path)
        if not self.validate_path(local):
            return
        
        if FLASK_AVAILABLE and self.path.startswith('/api/'):
            self._forward_to_flask()
            return
        super().do_POST()

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
            self.send_error(403, "禁止访问")
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
        talk_html_path = os.path.join(current_script_dir, 'talk', 'comment.html')
        try:
            with open(talk_html_path, 'rb') as f:
                self.send_response(200)
                self.send_header("Content-type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(f.read())
        except FileNotFoundError:
            logger.error(f"留言板静态页面不存在：{talk_html_path}")
            self.send_error(404, "留言板页面不存在，请检查talk/comment.html文件")
        except Exception as e:
            logger.error(f"读取留言板页面失败：{e}")
            self.send_error(500, "读取留言板页面失败")

    def _handle_visit_count(self):
        """处理访问计数请求"""
        self.send_response(200)
        self.send_header("Content-type", "application/json; charset=utf-8")
        self.end_headers()
        
        try:
            if os.path.exists(VISIT_COUNT_FILE):
                with open(VISIT_COUNT_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            else:
                total = get_total_visits()
                data = {"count": total, "total_visits": total, "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        except:
            total = get_total_visits()
            data = {"count": total, "total_visits": total, "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        
        self.wfile.write(json.dumps({
            "code": 200, 
            "message": "success",
            "data": data
        }, ensure_ascii=False).encode('utf-8'))

    def _forward_to_flask(self):
        """转发请求到Flask"""
        if not FLASK_AVAILABLE:
            self.send_error(500, "留言板模块未加载")
            return
        try:
            data = b""
            if self.command in ["POST", "PUT", "DELETE"]:
                cl = int(self.headers.get("Content-Length", 0))
                if 0 < cl < Config.MAX_POST_SIZE:
                    data = self.rfile.read(cl)

            with message_board.app.test_client() as client:
                headers = dict(self.headers)
                if self.command == "GET":
                    resp = client.get(self.path, headers=headers)
                elif self.command == "DELETE":
                    resp = client.delete(self.path, headers=headers)
                else:
                    content_type = self.headers.get('Content-Type', 'application/x-www-form-urlencoded')
                    resp = client.post(self.path, data=data, headers=headers, content_type=content_type)

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
            <head><title>500 服务器内部错误</title></head>
            <body style='padding:40px'>
                <h1>500 接口请求处理失败</h1>
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

        lst.sort(key=lambda x: (not os.path.isdir(os.path.join(path, x)), x.lower()))
        cur = unquote(self.path)
        if not cur.endswith('/'):
            cur += '/'

        bread = []
        p = ''
        bread.append('<a href="/"><i class="fas fa-home"></i> 首页</a>')
        for part in cur.strip('/').split('/'):
            if part:
                p += part + '/'
                bread.append(f'<span>/</span><a href="/{p}">{part}</a>')

        back = ''
        if cur != '/':
            parent = os.path.dirname(cur.rstrip('/')).replace('\\', '/') or '/'
            back = f'<a href="{parent}" class="back-btn"><i class="fas fa-arrow-left"></i> 返回上一级</a>'

        items = []
        for name in lst:
            fp = os.path.join(path, name)
            url = self.path + name
            if os.path.isdir(fp):
                items.append(f'''
                <a href="{url}/" class="item folder">
                    <i class="fas fa-folder"></i>
                    <div class="item-name">{name}</div>
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
                    <div class="item-name">{name}</div>
                </a>''')

        html = self.get_template().format(
            title=f"目录列表 - {cur}",
            path=cur,
            breadcrumb=''.join(bread),
            back_button=back,
            items=''.join(items)
        )
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))
        return None

# ===================== 服务器 =====================
class DualStackServer(ThreadingHTTPServer):
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
def run_server():
    """启动服务器"""
    if Config.RESET_VISITS:
        try:
            with open(VISIT_COUNT_FILE, 'w', encoding='utf-8') as f:
                json.dump({"count": 0, "total_visits": 0}, f)
            logger.info("✅ 访问计数已重置为0")
        except Exception as e:
            logger.error(f"重置计数失败：{e}")

    server_dir = Config.SERVER_DIR or current_script_dir
    os.chdir(server_dir)
    handler = partial(BeautifulDirectoryHandler, directory=server_dir)
    httpd = DualStackServer((Config.HOST, Config.PORT), handler)
    httpd.timeout = 10
    httpd.daemon_threads = True

    local_ip = socket.gethostbyname(socket.gethostname())
    current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    print("\n" + "="*60)
    print(f"🚀 服务启动成功！ {current_date}")
    print("="*60)
    print(f"📌 本地访问: http://localhost:{Config.PORT}")
    print(f"📌 外网访问: http://{local_ip}:{Config.PORT}")
    print(f"📌 留言板: http://localhost:{Config.PORT}/talk")
    print(f"📌 计数查询: http://localhost:{Config.PORT}/visit-count")
    print(f"📌 根目录: {os.path.abspath(server_dir)}")
    print(f"📌 PROXY Protocol: ✅ 已启用（纯Python实现，可获取真实IP）")
    print("="*60)
    print("📊 访问日志格式: [日期 时间] 图标 用户 [真实IP] | 方法 路径 | 状态 | 耗时 | 访问量")
    print("="*60 + "\n")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 服务正在停止...")
        httpd.server_close()
        print("✅ 服务已停止")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="个人Vlog HTTP服务端")
    parser.add_argument("-p", "--port", type=int, default=8000, help="监听端口")
    parser.add_argument("-H", "--host", type=str, default="0.0.0.0", help="监听地址")
    parser.add_argument("--reset-visits", action="store_true", help="重置访问次数")
    args = parser.parse_args()
    
    Config.PORT = args.port
    Config.HOST = args.host
    Config.RESET_VISITS = args.reset_visits 
    
    run_server()