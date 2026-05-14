# -*- coding: utf-8 -*-
"""
单独测试邮件发送功能（修复版）
"""
import sys
import os
import logging
import socket  # 添加socket导入
import smtplib
import random
import string
import time
from email.mime.text import MIMEText
from email.utils import formataddr

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

def test_send_email():
    """测试发送邮件"""
    
    # 配置
    QQ_MAIL_USER = "2361542526@qq.com"
    QQ_MAIL_AUTH_CODE = "jpzeajbnlmhyechd"  # 请确认这个授权码是否正确
    SMTP_SERVER = "smtp.qq.com"
    
    # 生成验证码
    code = ''.join(random.choices(string.digits, k=6))
    print(f"生成的验证码：{code}")
    
    # 测试邮箱
    to_email = input("请输入你的测试邮箱：").strip()
    
    if not to_email:
        print("邮箱不能为空")
        return
    
    # 邮件内容
    content = f"""
您的验证码是：{code}

验证码有效期为5分钟，请勿泄露给他人。
    """
    
    # 尝试多种端口和连接方式
    connection_methods = [
        {"port": 587, "use_tls": True, "name": "TLS"},
        {"port": 465, "use_ssl": True, "name": "SSL"},
        {"port": 25, "use_tls": False, "name": "普通连接"}
    ]
    
    for method in connection_methods:
        try:
            print(f"\n尝试使用{method['name']}方式连接 (端口:{method['port']})...")
            
            # 创建邮件
            msg = MIMEText(content, "plain", "utf-8")
            msg["From"] = formataddr(("个人博客", QQ_MAIL_USER))
            msg["To"] = to_email
            msg["Subject"] = "个人博客验证码"
            
            # 根据方式选择连接
            if method.get("use_ssl"):
                print(f"1. 使用SSL连接...")
                server = smtplib.SMTP_SSL(SMTP_SERVER, method["port"], timeout=30)
            else:
                print(f"1. 使用普通连接...")
                server = smtplib.SMTP(SMTP_SERVER, method["port"], timeout=30)
                if method.get("use_tls"):
                    print("2. 启动TLS加密...")
                    server.starttls()
            
            # 设置调试级别（可看到详细通信过程）
            server.set_debuglevel(1)
            
            print("3. 登录邮箱...")
            server.login(QQ_MAIL_USER, QQ_MAIL_AUTH_CODE)
            
            print(f"4. 发送邮件到 {to_email}...")
            server.sendmail(QQ_MAIL_USER, [to_email], msg.as_string())
            
            print("5. 关闭连接...")
            server.quit()
            
            print(f"\n✅ 使用{method['name']}方式发送成功！验证码：{code}")
            print("请检查你的邮箱（包括垃圾邮件箱）")
            return True
            
        except smtplib.SMTPAuthenticationError as e:
            print(f"❌ 认证失败：{e}")
            print("建议：重新获取QQ邮箱授权码")
            break  # 认证失败就不再尝试其他方式
            
        except smtplib.SMTPServerDisconnected as e:
            print(f"❌ 服务器断开连接：{e}")
            print(f"   {method['name']}方式失败，尝试其他方式...")
            continue
            
        except socket.timeout as e:
            print(f"❌ 连接超时：{e}")
            continue
            
        except ConnectionRefusedError as e:
            print(f"❌ 连接被拒绝：{e}")
            continue
            
        except Exception as e:
            print(f"❌ 未知错误：{type(e).__name__}: {e}")
            continue
    
    print("\n❌ 所有连接方式都失败了")
    print("\n可能的原因：")
    print("1. 网络问题 - 检查是否能访问外网")
    print("2. 防火墙阻止 - 尝试关闭防火墙/杀毒软件")
    print("3. 授权码错误 - 请重新获取QQ邮箱授权码")
    print("4. QQ邮箱安全限制 - 登录QQ邮箱网页版，检查是否有安全提醒")
    
    # 提供授权码获取步骤
    print("\n📧 重新获取授权码步骤：")
    print("1. 登录QQ邮箱网页版 (https://mail.qq.com)")
    print("2. 点击【设置】→【账户】")
    print("3. 向下找到【POP3/IMAP/SMTP服务】")
    print("4. 点击【生成授权码】")
    print("5. 按照提示发送短信")
    print("6. 复制新的16位授权码")

if __name__ == "__main__":
    test_send_email()