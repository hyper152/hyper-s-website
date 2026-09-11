# Hyper 的个人网站

基于 Python 的个人博客与数字花园，包含文章、旅行与项目记录、用户系统、留言板、访问统计、Ollama AI 助手。

- 在线网站：[https://hyp.asia/](https://hyp.asia/)
- 本地首页：[http://127.0.0.1:8000/home/](http://127.0.0.1:8000/home/)

根路径 `/`、`/home` 和旧路径 `/pages/home/` 会重定向至 `/home/`。

## 功能

- 多线程 HTTP/HTTPS 服务及 PROXY Protocol 支持
- 注册、登录、邮箱验证码与 Session 管理
- 游客及用户留言板
- 线程安全、持久化的访问统计
- Ollama 本地 AI 聊天
- 真实 IP、限流、路径保护及访客分析

## 环境要求

- Python 3.11
- Ollama（仅 AI 聊天需要）

当前 Windows Python 环境：

```text
C:\Users\23615\.conda\envs\web_env\python.exe
```

## 安装依赖

```powershell
cd E:\projects\web\hyper-s-website-master
C:\Users\23615\.conda\envs\web_env\python.exe -m pip install -r requirements.txt
```

## 启动网站

HTTP：

```powershell
C:\Users\23615\.conda\envs\web_env\python.exe -u main.py -H 127.0.0.1 -p 8000
```

HTTPS：

```powershell
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

C:\Users\23615\.conda\envs\web_env\python.exe -u main.py `
  -H 127.0.0.1 `
  -p 8000 `
  --certfile "certs\hyp.asia.crt" `
  --keyfile "certs\hyp.asia.key"
```

其他参数：

```powershell
python main.py --reset-visits
python main.py -H 0.0.0.0 -p 8000
```

## Ollama AI 助手

```powershell
$env:OLLAMA_MODELS = "E:\PC\ollama\models"
ollama serve
```

Ollama 未启动时，留言板及其他功能仍可使用。

## 数据与日志

| 路径 | 内容 |
|---|---|
| `data/site.db` | SQLite：用户、会话、留言、访客、访问计数与 AI 提问 |
| `data/site.db-wal`、`data/site.db-shm` | SQLite 运行期间的辅助文件，不要手动删除 |
| `data/backups/json-before-sqlite-*/` | 迁移前 JSON 原件及校验清单 |
| `logs/` | 网站日志 |

`data/`、`logs/`、媒体和证书包含本地运行数据。

SQLite 由 Python 标准库提供，无需安装数据库服务。采用 WAL、独立连接和短事务，
计数增量、留言及访问记录直接逐条提交。常用字段可通过 SQL 查询，`record` 列保留原始字段，
兼容历史记录的额外信息。数据库和备份目录禁止 HTTP GET/HEAD 下载。

从旧版迁移时，先停止网站，执行 `python -m src.migrate_data`，再启动网站。
迁移会备份六个 JSON 文件、在事务中导入并逐条校验；重复执行不会重复导入。
迁移完成后旧 JSON 不再用于运行。本机原始 JSON 已归档到 `data/backups/`。
启动时若发现未迁移的旧数据，会要求先执行迁移，不会静默建立空库。

运行中的数据库请通过 SQLite backup API 备份，不要只复制主数据库文件：

```powershell
python -c "import sqlite3; from datetime import datetime; from pathlib import Path; p=Path('data/backups'); p.mkdir(exist_ok=True); src=sqlite3.connect('data/site.db'); dst=sqlite3.connect(str(p / ('site-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '.db'))); src.backup(dst); dst.close(); src.close()"
```

验证存储与迁移：`python -m unittest discover -s tests -p test_storage.py -v`。

## 访客分析

```powershell
python src\analyze_visitor.py ip=39.144.109.183
python src\analyze_visitor.py 2026.4.27
python src\analyze_visitor.py 2026.5.1-
```

## 项目结构

```text
├── main.py                       # Web 服务入口
├── requirements.txt              # Python 依赖
├── home/                         # 首页
├── pages/                        # 内容页面
├── talk/
│   ├── ai-chat.html              # Ollama AI 助手
│   └── comment.html              # 留言板
├── src/
│   ├── storage.py                # SQLite 存储与原子读写
│   ├── migrate_data.py           # JSON 备份、导入及一致性校验
│   ├── analyze_visitor.py        # 访客分析
│   ├── auth.py                   # 用户认证
│   ├── message_board.py          # 留言板后端
│   └── ollama.py                 # Ollama API
├── data/                         # 运行数据
├── static/                       # 静态资源
├── logs/                         # 运行日志
└── certs/                        # HTTPS 证书
```

## 常见问题

端口占用：

```powershell
Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
```

查看日志：

```powershell
Get-Content .\logs\server-stderr.log -Tail 100
```

## 相关链接

- [个人网站](https://hyp.asia/)
- [GitHub 仓库](https://github.com/hyper152/hyper-s-website)

## 许可

MIT © 2026 CQU.hyper
