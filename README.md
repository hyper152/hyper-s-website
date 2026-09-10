# Hyper 的个人网站

基于 Python 构建的个人博客与数字花园 —— 记录开发日志、旅行见闻、装机折腾、游戏故事和校园回忆。

在线访问：[https://hyp.asia/](https://hyp.asia/) · [首页](https://hyp.asia/home/)

首页路径为 `/home/`，根路径 `/` 和旧地址 `/pages/home/` 会自动跳转到新首页。

## 内容分类

| 分类 | 内容 |
|------|------|
| **开发日志** | CQU-coursehelper、CRTC 机器人比赛、Gsing 战队、步道乐跑、个人博客、声控开关灯 |
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
- **AI 知识库** — 基于 OceanBase seekdb 的网站内容语义检索
- **IP 归属地** — 访客 IP 分析，支持城市级定位
- **限流保护** — 按 IP 限流，防止恶意请求
- **路径保护** — 禁止访问 `data/` 等敏感目录，防止路径遍历攻击

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
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

首次使用 AI 知识库前，扫描网站内容并建立向量索引：

```bash
python src/knowledge_base.py
```

`pyseekdb` 的 Python 嵌入式模式目前仅支持 Linux。Windows 开发环境请先启动
seekdb Docker：

```powershell
docker volume create hyper-seekdb
docker run -d --name hyper-seekdb -p 2881:2881 -p 2886:2886 `
  -e ROOT_PASSWORD=Seekdb123456 -e SEEKDB_DATABASE=hyper_site `
  -v hyper-seekdb:/var/lib/oceanbase oceanbase/seekdb:latest

$env:SEEKDB_HOST = "127.0.0.1"
$env:SEEKDB_PASSWORD = "Seekdb123456"
python src/knowledge_base.py
python main.py
```

启动网站与重建索引时须使用相同的 `SEEKDB_*` 环境变量。Linux 可以不设置
`SEEKDB_HOST`，直接使用默认的 `data/seekdb` 嵌入式数据库。

文章发生变化后重新执行该命令即可更新索引。知识库页面地址为
`http://localhost:8000/talk/knowledge-search.html`。

访问 [http://localhost:8000/home/](http://localhost:8000/home/) 即可查看首页。

### 启动参数

```bash
python main.py -p 8000 -H 0.0.0.0       # 指定端口和地址
python main.py -H 127.0.0.1 -p 8000 --certfile certs/hyp.asia.crt --keyfile certs/hyp.asia.key  # HTTPS
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
├── home/                    # 首页（/home/）
├── media/                   # 媒体资源文件（已 gitignore）
├── pages/                   # 内容页面
│   ├── HappyNewYear/        # 新年特别页面
│   ├── devlog/              # 开发日志
│   ├── diy/                 # 装机记录
│   ├── games/               # 游戏栏
│   ├── home/                # 旧首页地址跳转
│   ├── login/               # 登录/注册
│   ├── resume/              # 个人简历
│   ├── travel/              # 旅行记录
│   └── YY往事/              # 校园回忆
├── talk/                    # 留言板 & AI 聊天
├── src/                     # 后端 Python 模块
├── static/                  # 静态资源
├── data/                    # 数据存储（已 gitignore）
└── logs/                    # 访问日志（已 gitignore）
```

## 相关链接

- [个人网站](https://hyp.asia/)
- [GitHub](https://github.com/hyper152/hyper-s-website)

## 许可

MIT © 2026 CQU.hyper
