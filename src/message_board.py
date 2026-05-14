# -*- coding: utf-8 -*-
"""
Flask留言板&用户认证核心模块 - 支持游客留言
"""
import os
import json
import time
import logging
import random
import string
from flask import Flask, request, jsonify, make_response
from email.mime.text import MIMEText
from email.utils import formataddr

# ===================== 配置日志 =====================
logger = logging.getLogger("message_board")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
    logger.addHandler(console_handler)

# ===================== 基础配置 =====================
app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False
app.config["SECRET_KEY"] = os.environ.get("MESSAGE_BOARD_SECRET", "personal_vlog_2026_key")

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(ROOT_DIR, "data")
USER_FILE = os.path.join(DATA_DIR, "users.json")
MESSAGES_FILE = os.path.join(DATA_DIR, "messages.json")
VERIFY_CACHE = {}  # 验证码缓存

os.makedirs(DATA_DIR, exist_ok=True)

# ===================== 导入认证模块 =====================
try:
    from src.auth import (
        create_session,
        check_login_status,
        get_current_user,
        logout_user,
        hash_password,
        verify_password
    )
    logger.info("✅ auth模块导入成功")
except ImportError as e:
    logger.error(f"导入auth模块失败：{e}")
    # 简易版函数...
    def create_session(email):
        session_id = f"session_{int(time.time())}_{email}"
        return session_id
    
    def check_login_status(session_id):
        return bool(session_id and session_id.startswith("session_"))
    
    def get_current_user(session_id):
        if session_id and session_id.startswith("session_"):
            return {"username": "测试用户", "email": session_id.split("_")[-1]}
        return {}
    
    def logout_user(session_id):
        return True
    
    import hashlib
    import secrets
    def hash_password(password):
        salt = secrets.token_hex(16)
        hash_obj = hashlib.sha256((password + salt).encode('utf-8'))
        return f"{salt}${hash_obj.hexdigest()}"
    
    def verify_password(password, hashed_password):
        try:
            salt, hash_value = hashed_password.split('$')
            hash_obj = hashlib.sha256((password + salt).encode('utf-8'))
            return hash_obj.hexdigest() == hash_value
        except:
            return False

# ===================== 导入邮件模块 =====================
try:
    from src.qqmail import send_verify_code, generate_code
    logger.info("✅ 邮件模块导入成功")
except ImportError as e:
    logger.warning(f"导入邮件模块失败：{e}，使用内置函数")
    def generate_code(length=6):
        return ''.join(random.choices(string.digits, k=length))
    
    def send_verify_code(to_email, code=None):
        if code is None:
            code = generate_code()
        logger.debug(f"[模拟发送] 验证码 {code} 发送至 {to_email}")
        return True, "验证码发送成功（测试模式）", code

# ===================== 工具函数 =====================
def load_users():
    """加载用户数据"""
    try:
        if not os.path.exists(USER_FILE):
            return {}
        with open(USER_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"加载用户数据失败：{e}")
        return {}

def save_users(users):
    """保存用户数据"""
    try:
        with open(USER_FILE, "w", encoding="utf-8") as f:
            json.dump(users, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"保存用户数据失败：{e}")
        return False

def load_messages():
    """加载留言数据"""
    try:
        if not os.path.exists(MESSAGES_FILE):
            return []
        with open(MESSAGES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"加载留言数据失败：{e}")
        return []

def save_messages(messages):
    """保存留言数据"""
    try:
        with open(MESSAGES_FILE, "w", encoding="utf-8") as f:
            json.dump(messages, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"保存留言数据失败：{e}")
        return False

def get_session_id_from_request():
    """从请求中获取session_id"""
    session_id = request.cookies.get('session_id', '')
    if session_id:
        return session_id
    
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Session '):
        session_id = auth_header[8:].strip()
        return session_id
    
    session_id = request.args.get('session_id', '') or request.form.get('session_id', '')
    if session_id:
        return session_id
    
    if request.is_json:
        data = request.get_json(silent=True) or {}
        session_id = data.get('session_id', '')
        if session_id:
            return session_id
    
    return ''

def validate_nickname(nickname):
    """校验游客昵称"""
    if not nickname or not nickname.strip():
        return False, "昵称不能为空"
    
    nickname = nickname.strip()
    
    if len(nickname) < 2:
        return False, "昵称至少需要2个字符"
    
    if len(nickname) > 15:
        return False, "昵称不能超过15个字符"
    
    # 过滤敏感词（简单示例，可根据需要扩展）
    banned_words = ['admin', '管理员', '站长', 'hyper']
    for word in banned_words:
        if word.lower() in nickname.lower():
            return False, f"昵称不能包含「{word}」"
    
    return True, nickname

# ===================== API接口 =====================

@app.route("/api/register/send-code", methods=["POST"])
def send_register_code():
    """发送注册验证码"""
    try:
        data = request.get_json(silent=True) or {}
        email = data.get("email", "").strip()
        
        if not email or "@" not in email:
            return jsonify({"code": 400, "msg": "请输入有效的邮箱地址"})
        
        users = load_users()
        if email in users:
            return jsonify({"code": 400, "msg": "该邮箱已注册，请直接登录"})
        
        if email in VERIFY_CACHE:
            cache = VERIFY_CACHE[email]
            if cache["expire"] > time.time() + 240:
                return jsonify({"code": 400, "msg": "验证码已发送，请5分钟后重试"})
        
        success, msg, code = send_verify_code(email)
        
        if success:
            VERIFY_CACHE[email] = {
                "code": code,
                "expire": time.time() + 300,
                "type": "register"
            }
            logger.info(f"注册验证码发送: {email}")
            return jsonify({"code": 200, "msg": "验证码发送成功，请查收邮箱"})
        else:
            logger.error(f"注册验证码发送失败: {email}")
            return jsonify({"code": 500, "msg": msg})
            
    except Exception as e:
        logger.error(f"发送注册验证码异常：{e}")
        return jsonify({"code": 500, "msg": "服务器内部错误"})

@app.route("/api/register", methods=["POST"])
def register():
    """用户注册"""
    try:
        data = request.get_json(silent=True) or {}
        username = data.get("username", "").strip()
        email = data.get("email", "").strip()
        password = data.get("password", "").strip()
        code = data.get("code", "").strip()
        
        if not all([username, email, password, code]):
            return jsonify({"code": 400, "msg": "请填写完整注册信息"})
        
        if email not in VERIFY_CACHE:
            return jsonify({"code": 400, "msg": "验证码已过期，请重新获取"})
        
        cache = VERIFY_CACHE[email]
        if cache["type"] != "register" or cache["code"] != code:
            return jsonify({"code": 400, "msg": "验证码错误"})
        
        if time.time() > cache["expire"]:
            del VERIFY_CACHE[email]
            return jsonify({"code": 400, "msg": "验证码已过期，请重新获取"})
        
        users = load_users()
        if email in users:
            return jsonify({"code": 400, "msg": "该邮箱已注册"})
        
        encrypted_password = hash_password(password)
        
        users[email] = {
            "username": username,
            "password": encrypted_password,
            "email": email,
            "create_time": time.time(),
            "create_time_str": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        
        if save_users(users):
            del VERIFY_CACHE[email]
            logger.info(f"用户注册成功: {username}({email})")
            return jsonify({"code": 200, "msg": "注册成功，请登录"})
        else:
            return jsonify({"code": 500, "msg": "保存用户信息失败"})
            
    except Exception as e:
        logger.error(f"注册异常：{e}")
        return jsonify({"code": 500, "msg": "服务器内部错误"})

@app.route("/api/login/send-code", methods=["POST"])
def send_login_code():
    """发送登录验证码"""
    try:
        data = request.get_json(silent=True) or {}
        email = data.get("email", "").strip()
        
        if not email or "@" not in email:
            return jsonify({"code": 400, "msg": "请输入有效的邮箱地址"})
        
        users = load_users()
        if email not in users:
            return jsonify({"code": 400, "msg": "该邮箱未注册，请先注册"})
        
        success, msg, code = send_verify_code(email)
        
        if success:
            VERIFY_CACHE[email] = {
                "code": code,
                "expire": time.time() + 300,
                "type": "login"
            }
            logger.info(f"登录验证码发送: {email}")
            return jsonify({"code": 200, "msg": "验证码发送成功，请查收邮箱"})
        else:
            return jsonify({"code": 500, "msg": msg})
            
    except Exception as e:
        logger.error(f"发送登录验证码异常：{e}")
        return jsonify({"code": 500, "msg": "服务器内部错误"})

@app.route("/api/login/code", methods=["POST"])
def login_by_code():
    """验证码登录"""
    try:
        data = request.get_json(silent=True) or {}
        email = data.get("email", "").strip()
        code = data.get("code", "").strip()
        
        if not email or not code:
            return jsonify({"code": 400, "msg": "请输入邮箱和验证码"})
        
        if email not in VERIFY_CACHE:
            return jsonify({"code": 400, "msg": "验证码已过期，请重新获取"})
        
        cache = VERIFY_CACHE[email]
        if cache["type"] != "login" or cache["code"] != code:
            return jsonify({"code": 400, "msg": "验证码错误"})
        
        if time.time() > cache["expire"]:
            del VERIFY_CACHE[email]
            return jsonify({"code": 400, "msg": "验证码已过期，请重新获取"})
        
        users = load_users()
        if email not in users:
            return jsonify({"code": 400, "msg": "用户不存在"})
        
        user = users[email]
        session_id = create_session(email)
        
        del VERIFY_CACHE[email]
        
        response = make_response(jsonify({
            "code": 200,
            "msg": "登录成功",
            "data": {
                "username": user["username"],
                "email": email,
                "session_id": session_id
            }
        }))
        
        response.set_cookie('session_id', session_id, max_age=30*24*60*60, path='/')
        
        logger.info(f"验证码登录成功: {user['username']}({email})")
        return response
        
    except Exception as e:
        logger.error(f"验证码登录异常：{e}")
        return jsonify({"code": 500, "msg": "服务器内部错误"})

@app.route("/api/login/password", methods=["POST"])
def login_by_password():
    """密码登录"""
    try:
        data = request.get_json(silent=True) or {}
        email = data.get("email", "").strip()
        password = data.get("password", "").strip()
        
        if not email or not password:
            return jsonify({"code": 400, "msg": "请输入邮箱和密码"})
        
        users = load_users()
        if email not in users:
            return jsonify({"code": 400, "msg": "邮箱或密码错误"})
        
        user = users[email]
        
        if not verify_password(password, user["password"]):
            return jsonify({"code": 400, "msg": "邮箱或密码错误"})
        
        session_id = create_session(email)
        
        response = make_response(jsonify({
            "code": 200,
            "msg": "登录成功",
            "data": {
                "username": user["username"],
                "email": email,
                "session_id": session_id
            }
        }))
        
        response.set_cookie('session_id', session_id, max_age=30*24*60*60, path='/')
        
        logger.info(f"密码登录成功: {user['username']}({email})")
        return response
        
    except Exception as e:
        logger.error(f"密码登录异常：{e}")
        return jsonify({"code": 500, "msg": "服务器内部错误"})

@app.route("/api/check-login", methods=["POST", "GET"])
def check_login():
    """检查登录状态"""
    try:
        session_id = get_session_id_from_request()
        is_login = check_login_status(session_id)
        user = get_current_user(session_id) if is_login else {}
        
        if is_login:
            logger.debug(f"登录状态检查: {user.get('username', '')}")
        
        return jsonify({
            "isLogin": is_login,
            "user": user
        })
    except Exception as e:
        logger.error(f"检查登录状态异常：{e}")
        return jsonify({"isLogin": False, "user": {}})

@app.route("/api/logout", methods=["POST"])
def logout():
    """退出登录"""
    try:
        session_id = get_session_id_from_request()
        
        if session_id and logout_user(session_id):
            response = make_response(jsonify({"code": 200, "msg": "退出登录成功"}))
            response.set_cookie('session_id', '', expires=0, path='/')
            logger.info(f"用户退出登录")
            return response
        else:
            return jsonify({"code": 400, "msg": "退出失败"})
            
    except Exception as e:
        logger.error(f"退出登录异常：{e}")
        return jsonify({"code": 500, "msg": "服务器内部错误"})

@app.route("/api/talk/list", methods=["GET"])
def get_message_list():
    """获取留言列表"""
    try:
        messages = load_messages()
        messages.sort(key=lambda x: x.get("create_time", 0), reverse=True)
        return jsonify({"code": 200, "msg": "获取成功", "data": messages})
    except Exception as e:
        logger.error(f"获取留言列表异常：{e}")
        return jsonify({"code": 500, "msg": "服务器内部错误"})

@app.route("/api/talk/add", methods=["POST"])
def add_message():
    """
    添加留言
    支持已登录用户和游客留言
    游客需要提供 nickname 字段
    """
    try:
        session_id = get_session_id_from_request()
        data = request.get_json(silent=True) or {}
        content = data.get("content", "").strip()
        
        if not content:
            return jsonify({"code": 400, "msg": "留言内容不能为空"})
        
        if len(content) > 500:
            return jsonify({"code": 400, "msg": "留言内容不能超过500字"})
        
        # 判断登录状态
        is_login = check_login_status(session_id) if session_id else False
        
        if is_login:
            # 已登录用户
            user = get_current_user(session_id)
            username = user.get("username", "匿名用户") if user else "匿名用户"
            logger.info(f"留言添加成功（已登录）: {username}")
        else:
            # 游客模式：验证昵称
            nickname = data.get("nickname", "").strip()
            valid, result = validate_nickname(nickname)
            
            if not valid:
                return jsonify({"code": 400, "msg": result})
            
            username = result
            logger.info(f"留言添加成功（游客）: {username}")
        
        messages = load_messages()
        
        message = {
            "id": str(int(time.time() * 1000)) + str(random.randint(100, 999)),
            "username": username,
            "content": content,
            "create_time": time.time(),
            "create_time_str": time.strftime("%Y-%m-%d %H:%M:%S"),
            "is_guest": not is_login  # 标记是否为游客留言
        }
        
        messages.append(message)
        
        if save_messages(messages):
            return jsonify({"code": 200, "msg": "留言成功"})
        else:
            return jsonify({"code": 500, "msg": "保存留言失败"})
        
    except Exception as e:
        logger.error(f"添加留言异常：{e}")
        return jsonify({"code": 500, "msg": "服务器内部错误"})

# 导入 ollama 模块
try:
    from src.ollama import register_ollama_routes
    register_ollama_routes(app)
    logger.info("✅ Ollama 模块加载成功")
except ImportError as e:
    logger.warning(f"⚠️ Ollama 模块加载失败：{e}")
except Exception as e:
    logger.error(f"❌ Ollama 路由注册失败：{e}")

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8001, debug=True)