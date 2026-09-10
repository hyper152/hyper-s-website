# Hyper 的个人网站

基于 Python 的个人博客与数字花园，包含文章、旅行与项目记录、用户系统、留言板、访问统计、Ollama AI 助手，以及基于 OceanBase seekdb 的网站知识库。

- 在线网站：[https://hyp.asia/](https://hyp.asia/)
- 本地首页：[http://127.0.0.1:8000/home/](http://127.0.0.1:8000/home/)
- AI 知识库：[http://127.0.0.1:8000/talk/knowledge-search.html](http://127.0.0.1:8000/talk/knowledge-search.html)
- seekdb 控制台：[http://127.0.0.1:2886](http://127.0.0.1:2886)

根路径 `/`、`/home` 和旧路径 `/pages/home/` 会重定向至 `/home/`。

## 功能

- 多线程 HTTP/HTTPS 服务及 PROXY Protocol 支持
- 注册、登录、邮箱验证码与 Session 管理
- 游客及用户留言板
- 线程安全、持久化的访问统计
- Ollama 本地 AI 聊天
- seekdb 网站正文语义检索
- 向量召回与中文关键词混合重排
- HTML 正文自动提取、分块和索引更新
- 真实 IP、限流、路径保护及访客分析

## 环境要求

- Python 3.11
- Docker Desktop（Windows 使用知识库时需要）
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

## seekdb 知识库

### 当前配置

| 配置 | 值 |
|---|---|
| 容器 | `hyper-seekdb` |
| 镜像 | `oceanbase/seekdb:latest` |
| 数据库 | `hyper_site` |
| Collection | `site_pages` |
| 数据库端口 | `2881` |
| 控制台端口 | `2886` |
| 本地数据目录 | `data/seekdb-server` |
| 容器数据目录 | `/var/lib/seekdb` |

Windows 使用 Docker 运行 seekdb；当前电脑已经部署完成。以下命令仅用于其他电脑首次部署：

```powershell
cd E:\projects\web\hyper-s-website-master
New-Item -ItemType Directory -Force .\data\seekdb-server | Out-Null

docker run -d `
  --name hyper-seekdb `
  --restart unless-stopped `
  -p 2881:2881 `
  -p 2886:2886 `
  --mount "type=bind,source=$PWD\data\seekdb-server,target=/var/lib/seekdb" `
  oceanbase/seekdb:latest
```

首次启动后创建数据库并设置本地密码：

```powershell
@'
import pymysql

connection = pymysql.connect(
    host="127.0.0.1",
    port=2881,
    user="root",
    password="",
    autocommit=True,
)
with connection.cursor() as cursor:
    cursor.execute("CREATE DATABASE IF NOT EXISTS hyper_site")
    cursor.execute("ALTER USER 'root' IDENTIFIED BY 'Seekdb123456'")
connection.close()
'@ | C:\Users\23615\.conda\envs\web_env\python.exe -
```

> `Seekdb123456` 仅为本地开发密码。公网部署必须更换密码并限制 2881、2886 端口访问。

### 连接环境变量

启动网站或重建索引前，在同一 PowerShell 会话设置：

```powershell
$env:SEEKDB_HOST = "127.0.0.1"
$env:SEEKDB_PORT = "2881"
$env:SEEKDB_USER = "root"
$env:SEEKDB_PASSWORD = "Seekdb123456"
$env:SEEKDB_DATABASE = "hyper_site"
```

开机启动脚本已经包含这些变量：

```text
C:\Users\23615\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\web.cmd
```

### 建立或更新索引

```powershell
C:\Users\23615\.conda\envs\web_env\python.exe src\knowledge_base.py
```

该命令扫描 `home/`、`pages/` 和 `talk/`，排除脚本、样式、登录页等无关内容，然后重建 `site_pages`。添加或修改文章后重新执行即可。

测试搜索：

```powershell
C:\Users\23615\.conda\envs\web_env\python.exe -c "from src.knowledge_base import search; print(search('机器人比赛', 'data/seekdb', 3))"
```

测试 HTTP API：

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/api/knowledge/search" `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"query":"机器人比赛","limit":3}'
```

## 操作数据库

进入 MySQL 命令行：

```powershell
docker exec -it hyper-seekdb mysql -h 127.0.0.1 -P 2881 -u root -p
```

输入密码后执行：

```sql
SHOW DATABASES;
USE hyper_site;
SHOW TABLES;
SELECT collection_name FROM sdk_collections;
EXIT;
```

名称类似 `c$v2$...` 的表是 seekdb 自动维护的内部向量表，不要直接修改。网站知识库应通过 `src/knowledge_base.py` 和 `pyseekdb` 管理。

常用容器命令：

```powershell
docker ps
docker logs --tail 100 hyper-seekdb
docker stop hyper-seekdb
docker start hyper-seekdb
docker restart hyper-seekdb
```

不要在容器运行时直接修改 `data/seekdb-server` 中的文件。

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

Ollama 未启动时，知识库、留言板及其他功能仍可使用。

## 数据与日志

| 路径 | 内容 |
|---|---|
| `data/visit_count.json` | 访问次数 |
| `data/visitor.json` | 访客记录 |
| `data/users.json` | 用户数据 |
| `data/sessions.json` | Session 数据 |
| `data/messages.json` | 留言数据 |
| `data/ai.json` | AI 提问记录 |
| `data/seekdb-server/` | seekdb 数据库文件 |
| `logs/` | 网站日志 |

`data/`、`logs/`、媒体和证书均不会提交到 Git。备份 `data/seekdb-server` 前先执行 `docker stop hyper-seekdb`，复制完成后再启动容器。

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
│   ├── comment.html              # 留言板
│   └── knowledge-search.html     # seekdb 知识库
├── src/
│   ├── knowledge_base.py         # 建库与检索
│   ├── analyze_visitor.py        # 访客分析
│   ├── auth.py                   # 用户认证
│   ├── message_board.py          # 留言板后端
│   └── ollama.py                 # Ollama API
├── static/                       # 静态资源
├── data/                         # 运行数据与 seekdb
├── logs/                         # 运行日志
└── certs/                        # HTTPS 证书
```

## 常见问题

知识库返回 503：

```powershell
docker ps
docker start hyper-seekdb
C:\Users\23615\.conda\envs\web_env\python.exe -m pip show pyseekdb
```

端口占用：

```powershell
Get-NetTCPConnection -LocalPort 2881,2886,8000 -ErrorAction SilentlyContinue
```

查看日志：

```powershell
Get-Content .\logs\server-stderr.log -Tail 100
docker logs --tail 100 hyper-seekdb
```

## 相关链接

- [个人网站](https://hyp.asia/)
- [GitHub 仓库](https://github.com/hyper152/hyper-s-website)
- [OceanBase seekdb](https://github.com/oceanbase/seekdb)
- [pyseekdb](https://github.com/oceanbase/pyseekdb)

## 许可

MIT © 2026 CQU.hyper
