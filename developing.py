# -*- coding: utf-8 -*-
"""
个人博客升级维护临时服务（移除预计恢复时间版）
替换 main.py 即可启动，无需依赖其他模块
"""
import os
import logging
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ===================== 基础配置（和原项目保持一致） =====================
HOST = "0.0.0.0"
PORT = 8000
# 升级提示配置（移除预计恢复时间）
MAINTENANCE_TITLE = "个人博客升级中 🚧"
MAINTENANCE_MSG = "网站正在进行内容优化和功能升级，暂无法访问"
CONTACT_INFO = "如有紧急问题，可通过邮箱 2361542526@qq.com 联系"

# ===================== 日志初始化（极简版） =====================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# ===================== 升级页面处理器 =====================
class MaintenanceHandler(BaseHTTPRequestHandler):
    # 覆盖日志输出，和原项目格式对齐
    def log_message(self, format, *args):
        client_ip = self.address_string()
        logger.info(f"[{client_ip}] {format % args}")

    # 生成升级提示页面（移除恢复时间相关内容）
    def _get_maintenance_html(self):
        html = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{MAINTENANCE_TITLE}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; font-family: Microsoft YaHei; }}
        body {{ 
            background: #f8f9fa; 
            padding: 40px; 
            display: flex; 
            justify-content: center; 
            align-items: center; 
            min-height: 100vh;
        }}
        .container {{ 
            max-width: 800px; 
            background: white; 
            padding: 50px; 
            border-radius: 12px; 
            box-shadow: 0 2px 20px rgba(0,0,0,0.1); 
            text-align: center;
        }}
        h1 {{ 
            color: #6a5acd; 
            font-size: 2.5em; 
            margin-bottom: 20px;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 15px;
        }}
        h1 i {{ font-size: 1.2em; }}
        .msg {{ 
            color: #495057; 
            font-size: 1.2em; 
            line-height: 1.8; 
            margin: 30px 0;
        }}
        .contact {{ 
            color: #6c757d; 
            margin-top: 30px; 
            font-size: 1em;
        }}
        /* 适配原项目的图标风格 */
        @import url("https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css");
    </style>
</head>
<body>
    <div class="container">
        <h1><i class="fas fa-tools"></i> {MAINTENANCE_TITLE}</h1>
        <div class="msg">{MAINTENANCE_MSG}</div>
        <div class="contact">📧 {CONTACT_INFO}</div>
    </div>
</body>
</html>
        """
        return html

    # 处理所有GET请求
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        # 返回升级提示页面
        self.wfile.write(self._get_maintenance_html().encode('utf-8'))

    # 处理POST请求（兼容留言板等POST场景）
    def do_POST(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        # 同样返回升级提示
        self.wfile.write(self._get_maintenance_html().encode('utf-8'))

# ===================== 启动服务器 =====================
def run_maintenance_server():
    # 确保日志目录存在（和原项目对齐）
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
    os.makedirs(log_dir, exist_ok=True)

    # 创建服务器
    try:
        server = ThreadingHTTPServer((HOST, PORT), MaintenanceHandler)
        # 端口复用，避免重启报错
        server.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        # 输出启动信息（和原项目格式一致）
        local_ip = socket.gethostbyname(socket.gethostname())
        logger.info("\n🚧 个人博客升级维护服务已启动！")
        logger.info(f"├─ 本地访问: http://localhost:{PORT}")
        logger.info(f"├─ 外网访问: http://{local_ip}:{PORT}")
        logger.info(f"└─ 维护提示：{MAINTENANCE_MSG}")
        
        # 持续运行
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("\n🛑 维护服务已停止")
        server.server_close()
    except Exception as e:
        logger.error(f"服务启动失败：{e}")
        exit(1)

if __name__ == "__main__":
    run_maintenance_server()