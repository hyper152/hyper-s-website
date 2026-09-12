# 启动命令

```powershell
# 1. 激活环境 + 启动服务
(C:\.software\anaconda\shell\condabin\conda-hook.ps1) ; (conda activate web_env)
& python projects\web\hyper-s-website-master\main.py

# 2. Ollama（AI 聊天需要）
ollama serve

# 3. 访客分析
& python projects\web\hyper-s-website-master\src\analyze_visitor.py ip=42.81.251.36
& python projects\web\hyper-s-website-master\src\analyze_visitor.py 2026.9.1-

# 4. 更新代码
git pull origin master
```
