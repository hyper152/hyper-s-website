# -*- coding: utf-8 -*-
"""
QQ邮箱验证码发送模块（完整导出版）
"""
import smtplib
import logging
import random
import string
from email.mime.text import MIMEText
from email.utils import formataddr

import os

# ===================== 配置 =====================
QQ_MAIL_USER = os.environ.get("QQ_MAIL_USER", "2361542526@qq.com")           # 你的QQ邮箱（优先使用环境变量）
QQ_MAIL_AUTH_CODE = os.environ.get("QQ_MAIL_AUTH_CODE", "omelrirsldmsdhha")  # QQ邮箱SMTP授权码（优先使用环境变量）
SMTP_SERVER = "smtp.qq.com"
SMTP_PORT = 465                          # SSL端口

# ===================== 日志 =====================
logger = logging.getLogger("qqmail")
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# ===================== 验证码生成 =====================
def generate_code(length=6):
    """生成6位数字验证码"""
    return ''.join(random.choices(string.digits, k=length))

# ===================== 核心函数 =====================
def send_verify_code(to_email, code=None):
    """
    发送验证码到指定邮箱（使用SSL连接）
    返回：(success, message, code)
    """
    if not to_email or '@' not in to_email:
        return False, "邮箱地址无效", None
    
    # 如果没有提供验证码，自动生成
    if code is None:
        code = generate_code()
    
    # 邮件内容
    mail_title = "hyper的博客验证码"
    content = f"""
您的验证码是：{code}

验证码有效期为5分钟，请勿泄露给他人。
如非本人操作，请忽略此邮件。

(此邮件由系统自动发送，请勿回复)
    """
    
    try:
        # 创建邮件
        msg = MIMEText(content, "plain", "utf-8")
        msg["From"] = formataddr(("hyper的博客", QQ_MAIL_USER))
        msg["To"] = to_email
        msg["Subject"] = mail_title
        
        # 使用SSL连接（465端口）- 刚才测试成功的
        logger.info(f"正在连接QQ邮箱服务器 {SMTP_SERVER}:{SMTP_PORT}...")
        server = smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, timeout=30)
        
        # 登录
        logger.info("正在登录...")
        server.login(QQ_MAIL_USER, QQ_MAIL_AUTH_CODE)
        
        # 发送
        logger.info(f"正在发送邮件到 {to_email}...")
        server.sendmail(QQ_MAIL_USER, [to_email], msg.as_string())
        
        # 关闭连接
        server.quit()
        
        logger.info(f"✅ 验证码 {code} 发送至 {to_email} 成功")
        return True, "验证码发送成功，请查收邮箱", code
        
    except smtplib.SMTPAuthenticationError as e:
        logger.error(f"SMTP认证失败：{e}")
        return False, "邮箱授权码错误，请检查配置", None
    except smtplib.SMTPConnectError as e:
        logger.error(f"SMTP连接失败：{e}")
        return False, "无法连接邮箱服务器，请稍后重试", None
    except smtplib.SMTPServerDisconnected as e:
        logger.error(f"服务器断开连接：{e}")
        return False, "服务器连接断开，请稍后重试", None
    except Exception as e:
        logger.error(f"发送验证码异常：{e}", exc_info=True)
        return False, f"发送失败：{str(e)}", None

# ===================== 明确导出函数 =====================
__all__ = ['send_verify_code', 'generate_code', 'send_verification_code']

# 兼容旧函数名
send_verification_code = send_verify_code

# 测试代码（当直接运行此文件时）
if __name__ == "__main__":
    test_email = input("请输入测试邮箱：").strip()
    if test_email:
        success, msg, code = send_verify_code(test_email)
        print(f"发送结果：{success}")
        print(f"消息：{msg}")
        print(f"验证码：{code}")