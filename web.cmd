@echo off
setlocal
chcp 65001 >nul

set "OLLAMA_MODELS=E:\PC\ollama\models"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"


echo Starting Ollama...
start "" /min "C:\Users\23615\AppData\Local\Programs\Ollama\ollama.exe" serve

echo Waiting for Ollama to initialize...
timeout /t 5 /nobreak >nul

echo Starting HTTP website...
cd /d "E:\projects\web\hyper-s-website-master"

"C:\Users\23615\.conda\envs\web_env\python.exe" -u main.py ^
  -H 127.0.0.1 ^
  -p 8000

pause
