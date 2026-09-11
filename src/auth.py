# -*- coding: utf-8 -*-
"""
用户认证模块（带密码加密）- 日志优化版
"""
import json
import os
import time
import uuid
import hashlib
import secrets
from datetime import datetime
import logging

# 配置日志
logger = logging.getLogger("auth")

from src.storage import get_store
from threading import RLock
TEMP_SESSIONS = {}
_temp_lock = RLock()


def init_files():
    """兼容旧调用，初始化 SQLite 存储。"""
    get_store()

# ==================== 密码加密函数 ====================

def hash_password(password):
    """
    密码加密
    使用盐值+SHA256加密
    """
    salt = secrets.token_hex(16)
    hash_obj = hashlib.sha256((password + salt).encode('utf-8'))
    return f"{salt}${hash_obj.hexdigest()}"

def verify_password(password, hashed_password):
    """
    验证密码
    hashed_password格式: 盐值$哈希值
    """
    try:
        salt, hash_value = hashed_password.split('$')
        hash_obj = hashlib.sha256((password + salt).encode('utf-8'))
        return hash_obj.hexdigest() == hash_value
    except:
        return False

# ==================== 会话管理函数 ====================

def create_session(email, persistent=True):
    """创建用户会话"""
    init_files()
    
    session_id = str(uuid.uuid4())
    expire_time = time.time() + 30*24*60*60  # 30天过期
    
    session = {
        "email": email,
        "login_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "expire_time": expire_time
    }
    if not persistent:
        with _temp_lock:
            TEMP_SESSIONS[session_id] = session
        logger.debug(f"创建临时会话: {email}")
        return session_id

    get_store().put_session(session_id, session)

    logger.debug(f"创建会话: {email}")
    return session_id

def _active_session(session_id):
    if not session_id:
        return None
    with _temp_lock:
        session = TEMP_SESSIONS.get(session_id)
        if session is not None:
            if time.time() > session['expire_time']:
                TEMP_SESSIONS.pop(session_id, None)
                return None
            return session
    session = get_store().session(session_id)
    if session and time.time() > session['expire_time']:
        get_store().delete_session(session_id)
        return None
    return session


def check_login_status(session_id):
    return _active_session(session_id) is not None


def get_current_user(session_id):
    session = _active_session(session_id)
    if not session:
        return {}
    email = session['email']
    user = get_store().user(email)
    return {'username': user.get('username', ''), 'email': email} if user else {}


def logout_user(session_id):
    if not session_id:
        return False
    with _temp_lock:
        if TEMP_SESSIONS.pop(session_id, None) is not None:
            return True
    return get_store().delete_session(session_id)


def register(username, email, password):
    """用户注册（密码加密存储）"""
    init_files()
    user = {
        "username": username,
        "password": hash_password(password),
        "email": email,
        "create_time": time.time(),
        "create_time_str": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    if not get_store().create_user(email, user):
        return {"code": 1, "msg": "邮箱已存在"}

    logger.info(f"新用户注册: {username}({email})")
    return {"code": 0, "msg": "注册成功"}

def login(email, password):
    """密码登录（验证加密密码）"""
    init_files()
    users = get_store().users()

    if email not in users:
        return {"code": 1, "msg": "邮箱或密码错误"}
    
    if not verify_password(password, users[email]["password"]):
        return {"code": 1, "msg": "邮箱或密码错误"}
    
    session_id = create_session(email)
    
    logger.info(f"用户登录: {users[email]['username']}({email})")
    
    return {
        "code": 0, 
        "msg": "登录成功", 
        "data": {
            "session_id": session_id, 
            "username": users[email]["username"],
            "email": email
        }
    }
