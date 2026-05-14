# Hyper 的个人网站

基于 Python 构建的个人博客与数字花园 —— 记录开发日志、旅行见闻、装机折腾、游戏故事和校园回忆。

## 内容分类

| 分类 | 内容 |
|------|------|
| **开发日志** | CQU-coursehelper、CRTC 机器人比赛、Gsing CTF 战队、步道乐跑、个人博客、声控开关灯 |
| **装机记录** | 从 GT610 到 RTX2060 的 DIY 升级之路 |
| **游戏栏** | 我的世界 · 温州育英重建计划 |
| **旅行记录** | 上海、杭州、南京、百丈漈、雁荡山、贵阳 |
| **校园往事** | EDG 夺冠、机房往事、觉醒年代、返校宣讲 |

## 功能特性

- **HTTP 服务** — 基于 `http.server` 的线程安全 Web 服务器，支持 PROXY Protocol 获取真实客户端 IP
- **用户系统** — 邮箱注册/登录（密码 + 验证码），Session 管理
- **留言板** — 发表留言、查看留言列表，支持游客和登录用户
- **访问计数** — 全站访问量统计，持久化存储，线程安全
- **邮件通知** — QQ 邮箱 SMTP 验证码发送，支持环境变量配置
- **AI 助手** — 基于 Ollama 的本地大模型聊天
- **IP 归属地** — 访客 IP 分析，支持城市级定位
- **限流保护** — 按 IP 限流，防止恶意请求
- **路径保护** — 禁止访问 `data/` 等敏感目录，防止路径遍历攻击

## 快速开始

### 1. 安装依赖

```bash
pip install flask requests
```

### 2. 配置环境变量（可选）

```bash
export QQ_MAIL_AUTH_CODE="your_auth_code"
export MESSAGE_BOARD_SECRET="your_secret_key"
```

### 3. 启动服务

```bash
python main.py
```

访问 **http://localhost:8000** 即可查看网站。

### 启动参数

```bash
python main.py -p 8000 -H 0.0.0.0       # 指定端口和地址
python main.py --reset-visits             # 重置访问计数
python main-proxy.py                      # 带 PROXY Protocol 支持
```

## 工具脚本

```bash
python src/analyze_visitor.py ip=39.144.109.183   # 按 IP 查询访客
python src/analyze_visitor.py 2026.4.27            # 按日期查询访问记录
```

## 项目结构

```
├── main.py                  # HTTP 服务主入口
├── main-proxy.py            # PROXY Protocol 入口
├── developing.py            # 维护模式服务
├── home/                    # 首页
├── login/                   # 登录/注册
├── resume/                  # 个人简历
├── pages/                   # 内容页面
│   ├── devlog/              # 开发日志
│   ├── diy/                 # 装机记录
│   ├── games/               # 游戏栏
│   ├── travel/              # 旅行记录
│   └── YY往事/              # 校园回忆
├── talk/                    # 留言板 & AI 聊天
├── HappyNewYear/            # 新年特别页面
├── src/                     # 后端 Python 模块
├── static/                  # 静态资源
├── data/                    # 数据存储（已 gitignore）
└── logs/                    # 访问日志（已 gitignore）
```

## 相关链接

- [个人网站](http://0o0hyper0o0.cyou/home/)
- [GitHub](https://github.com/hyper152/hyper-s-website)

## 许可

MIT © 2026 hyper（黄益鹏）
