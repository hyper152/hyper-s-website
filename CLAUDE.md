# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

A personal vlog/blog website built mostly on Python stdlib `http.server`, with a Flask sub-app for API routes (message board, auth, Ollama AI proxy). Static HTML pages under `home/`, `pages/`, `talk/`, `login/`, etc. serve content; the Python server handles routing, access logging, visitor analytics, and rate limiting.

## Quick Commands

```bash
pip install flask requests          # Install dependencies
python main.py                      # Start the server (default :8000)
python main.py -p 8080 -H 0.0.0.0   # Custom port/host
python main.py --reset-visits       # Reset visit counter
python main-proxy.py                # Start with PROXY Protocol support
python developing.py                # Maintenance mode (Flask, shows "under construction")
python src/analyze_visitor.py                            # Full visitor analysis
python src/analyze_visitor.py ip=1.2.3.4                 # Query by IP
python src/analyze_visitor.py 2026.4.27                  # Query by date
python src/analyze_visitor.py 2026.4.23-                 # From date onward
```

## Architecture

### Dual-Server Model

The site uses **two servers in one file** — a stdlib HTTP server (`main.py`) and a Flask app (`src/message_board.py`). The HTTP server is the primary front-facing server; for paths starting with `/api/`, it creates an in-process Flask test client and forwards the request internally:

```
Client → HTTP Server (main.py, port 8000)
           ├── Static files / pages (served directly)
           ├── /api/* → Flask app (in-process test_client forwarding)
           │              ├── /api/talk/*          (message board CRUD)
           │              ├── /api/login/*         (auth: email + password/code)
           │              ├── /api/register/*      (registration with email verification)
           │              ├── /api/ollama/*        (AI chat proxy to local Ollama)
           │              └── /api/check-login     (session check)
           ├── /visit-count     (JSON endpoint, served by HTTP server)
           └── /talk            (static page served by HTTP server)
```

### Key Modules (`src/`)

| Module | Role | Notes |
|--------|------|-------|
| `message_board.py` | Flask app — all API endpoints | Creates the Flask app; self-registers Ollama routes via `register_ollama_routes()` |
| `auth.py` | User authentication | Password hashing (salt+SHA256), session management (UUID + 30-day expiry), JSON file storage |
| `ollama.py` | Ollama AI chat proxy | Proxies to `http://localhost:11434`; supports streaming; used in `talk/ai-chat.html` |
| `qqmail.py` | Email verification | QQ Mail SMTP (SSL port 465); sends 6-digit codes; env vars `QQ_MAIL_USER`, `QQ_MAIL_AUTH_CODE` |
| `ip2Region.py` | IP geolocation | Local offline IP lookup via `data/ip2region-master/`; used by `analyze_visitor.py` |
| `analyze_visitor.py` | Visitor analytics CLI | Queries `data/visitor.json` by IP, date, or generates full reports |
| `visit_counter.py` | Async visit counter | Thread-safe counter with 30s auto-save interval; separate from the inline counter in `main.py` |

### Data Storage

All persistent data is in `data/` (gitignored):
- `users.json` — user accounts (username, hashed password, email, creation time)
- `sessions.json` — active sessions (UUID → email, expiry)
- `messages.json` — message board entries
- `visitor.json` — every HTTP request logged with IP, user, path, UA, timestamp
- `visit_count.json` — total visit counter
- `ai.json` — saved Ollama chat questions
- `ip2region-master/` — IP geolocation database (gitignored db file)

### Authentication Flow

- Password stored as `salt$sha256(password+salt)`
- Sessions stored as UUID with 30-day expiry in `sessions.json`
- Session ID communicated via cookie (`session_id`) or `Authorization: Session <id>` header
- Login options: password-based or email verification code (via QQ Mail SMTP)

### Main Server Features (main.py)

- **PROXY Protocol v2** — pure Python parser (`SimpleProxyProtocol`) extracts real client IP behind reverse proxies
- **HTTP header IP fallback** — `X-Forwarded-For` → `X-Real-IP` → `CF-Connecting-IP` → `True-Client-IP`
- **Rate limiting** — per-IP, configurable window (default: 60 req / 60s)
- **Path protection** — `data/` directory blocked; path traversal detection; whitelist-based routing
- **Directory listing** — beautified HTML directory browser with Font Awesome icons
- **Logging** — emoji-coded single-line logs; static assets (images, videos, CSS, JS) silently filtered
- **Thread-safe visitor storage** — writes via `VisitorManager` with atomic file replacement

### Frontend Pages

- `home/index.html` — landing/home page
- `login/index.html` + `login/register.html` — login/register forms
- `talk/comment.html` — message board
- `talk/ai-chat.html` — Ollama AI chat interface
- `resume/index.html` — personal resume
- `pages/` — content pages organized by category (devlog, diy, games, travel, YY往事)
- `pages/study/` — course study pages (数据结构与算法, 思法, etc.)
- `pages/study/math/` — 高等数学复习资料（从 `.hyper/study/高等数学下/试卷/` 提取整理的期末分类精选题）
- `HappyNewYear/` — special NYE page

### Network / Proxy Setup

- `main.py` — direct exposure (std server)
- `main-proxy.py` — same server pre-configured for behind a reverse proxy (expects PROXY Protocol)
- `developing.py` — maintenance mode: all requests return a "site under construction" page (replaces `main.py`)
