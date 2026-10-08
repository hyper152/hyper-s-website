# 启动命令

```powershell
# 1. 激活环境 + 启动服务
(C:\.software\anaconda\shell\condabin\conda-hook.ps1) ; (conda activate web_env)
& python projects\web\hyper-s-website-master\main.py

# 2. Ollama（AI 聊天需要）
ollama serve

# 3. 访客分析
# 默认只打印概要，完整报告覆盖写入 projects\web\hyper-s-website-master\data\reports\visitor_report.txt
& python projects\web\hyper-s-website-master\src\analyze_visitor.py ip=42.81.251.36
& python projects\web\hyper-s-website-master\src\analyze_visitor.py 2026.9.1-
# 想直接在控制台看全部内容时加 --full
& python projects\web\hyper-s-website-master\src\analyze_visitor.py 2026.9.1- --full

# 主程序启动时会自动生成/更新该报告（每天最多一次），--force-report 可强制立即重生成
& python projects\web\hyper-s-website-master\main.py --force-report

# 4. 更新代码
git pull origin master
```
