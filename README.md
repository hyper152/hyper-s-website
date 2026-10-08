# Hyper 的个人网站

基于 Python 的个人博客与数字花园，包含文章、旅行与项目记录、用户系统、留言板、访问统计、Ollama AI 助手。

- 在线网站：[https://hyp.asia/](https://hyp.asia/)
- 本地首页：[http://127.0.0.1:8000/pages/home/](http://127.0.0.1:8000/pages/home/)

根路径 `/`、`/home` 和旧路径 `/home/` 会重定向至 `/pages/home/`。

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
python main.py --force-report      # 启动时立即重新生成访客分析报告
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

验证存储与迁移：`python -m unittest discover -s src/tests -p test_storage.py -v`。

## 访客分析

```powershell
python src\analyze_visitor.py                 # 概要输出，完整报告覆盖写入 data/reports/visitor_report.txt
python src\analyze_visitor.py --full          # 直接在控制台打印完整报告
python src\analyze_visitor.py --top 20        # 每个地区只列出请求最多的前 20 个 IP
python src\analyze_visitor.py ip=39.144.109.183
python src\analyze_visitor.py 2026.4.27
python src\analyze_visitor.py 2026.5.1-
```

默认只打印地区排名、请求最多的 IP 等概要（约 30 行），完整明细覆盖写入 `data/reports/visitor_report.txt`（已被 .gitignore 忽略），用 VS Code 打开即可搜索。单 IP 查询默认只显示最近 200 条记录、前 50 个路径和前 10 个 User-Agent，加 `--full` 查看全部。

报告排序为：国内省份（按访问次数降序）→ 国外地区（按访问次数降序）→ 内网。

主程序（`main.py`）启动时会确保该文件存在：文件缺失或距上次生成超过 24 小时才重新覆盖生成，之后由后台线程每 30 分钟检查一次，因此全程只保留这一个文件。加 `--force-report` 启动可强制立即重新生成；设置环境变量 `DISABLE_VISITOR_REPORT=1` 可关闭该后台任务。

### 访问分析页面

页面地址 `/pages/visit/`，首页“总访问次数”徽标和“快速链接”都能进入。页面展示总请求、独立 IP、国内 / 国外占比、异常请求、最近 30 天趋势、国内省份与国外地区分布（可点开看具体 IP）、请求最多的 IP 和热门路径。

数据来自 `/api/visit-stats`，由 `src/analyze_visitor.py` 的 `get_stats_payload()` 生成并缓存 5 分钟；页面“刷新数据”按钮会带 `?refresh=1` 强制重新分析。

访客 IP 属于隐私数据，接口默认要求登录（`main.py` 顶部的 `VISIT_STATS_REQUIRE_LOGIN = True`）。未登录打开页面会看到登录提示并跳转登录页。想公开该页面就把它改成 `False`；想只允许特定账号查看，就填写 `VISIT_STATS_ALLOWED_USERS = {'hyper'}`。

点击任意 IP 会弹出详细记录：归属地、总请求、错误请求、登录用户、首次 / 最后访问、请求方法、访问路径排行，以及最新的访问明细（每页 200 条，“加载更多”继续翻）。该功能只对 `main.py` 里的 `VISIT_DETAIL_ALLOWED_USERS`（默认 `{'hyper'}`）开放，接口 `/api/visit-detail?ip=<IP>` 会独立校验账号，其他账号点击只会看到提示。

## 项目结构

```text
├── main.py                       # Web 服务入口
├── requirements.txt              # Python 依赖
├── pages/                        # 内容页面及对应的 CSS、JS
│   ├── _shared/                  # 全站主题、分类样式、返回导航
│   ├── home/                     # 首页、home.css、home.js
│   ├── login/                    # 登录页面与认证脚本
│   ├── resume/                   # 个人简介与样式
│   ├── talk/                     # AI 助手、留言板及对应资源
│   ├── diy/                      # 装机记录与文章样式
│   ├── travel/                   # 旅行页面、journal.css、journal.js
│   ├── visit/                    # 访问分析页面及对应资源
│   └── ...                       # 其他内容分类
├── src/
│   ├── storage.py                # SQLite 存储与原子读写
│   ├── migrate_data.py           # JSON 备份、导入及一致性校验
│   ├── analyze_visitor.py        # 访客分析
│   ├── auth.py                   # 用户认证
│   ├── message_board.py          # 留言板后端
│   └── ollama.py                 # Ollama API
├── data/                         # 运行数据
├── logs/                         # 运行日志
└── certs/                        # HTTPS 证书
```

页面专用 CSS、JS 与 HTML 放在对应目录；跨页面共用资源放在 `pages/_shared/`。原 `/static/` 资源地址由服务端跳转到新地址（修改服务端后需重启）。

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


## HTTP 文件访问安全（2026-09-12）

只公开 `pages/`、`static/`、`media/`、`banner/`、`dwcc/` 和明确列出的入口。
根路径精确匹配，不再作为全站放行前缀；GET/HEAD 共用文件保护。
隐藏路径、源码、证书、数据库、备份及越界链接禁止下载，公开目录列表过滤敏感文件。
`robots.txt` 只约束守规矩的爬虫，访问控制由服务端执行。

验证：`python -m unittest discover -s src/tests -v`。
修改 `main.py` 后需要重启网站进程；如果另有静态文件代理，必须确保代理也不公开项目根目录。

### 已暴露凭据的处置

`src/qqmail.py` 和 `src/test_email.py` 曾包含 SMTP 授权码。
必须在 QQ 邮箱端撤销旧码并生成新码，保存在 `data/qq_mail_auth_code.txt`（仅授权码一行），再重启服务。
也可通过 `QQ_MAIL_AUTH_CODE` 环境变量覆盖文件配置。凭据文件已被 Git 忽略，禁止 HTTP 下载。
不要将新码写入源码、提交或访问日志。未配置时邮件验证码服务明确返回未配置错误。
密码登录不依赖此授权码。移除源码中的旧值不会删除 Git 历史，也无法撤回攻击者已下载的数据。

本次有限 Git 历史检查未发现 `certs/`、`.env`、`data/users.json`、`data/sessions.json` 的提交记录；
这不代表运行目录从未被直接下载，也不是完整的密钥审计。
保留访问日志，检查这些路径及 `logs/`、`src/` 的成功下载记录。
如确认私钥、账户数据或会话泄露，应更换对应证书/凭据并使相关会话失效。
