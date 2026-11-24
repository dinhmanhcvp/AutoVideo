@echo off
REM Bot Telegram thuong truc: duyet video tu dien thoai + tu chay hang ngay.
REM Dat shortcut file nay vao thu muc Startup (Win+R, go shell:startup) de tu bat cung Windows.
set PYTHONUTF8=1
cd /d "%~dp0\.."
if not exist logs mkdir logs
:loop
if exist .venv call .venv\Scripts\activate.bat
python -m autovideo bot >> logs\bot.log 2>&1
REM Bot thoat bat thuong thi tu khoi dong lai sau 15 giay
timeout /t 15 /nobreak > nul
goto loop
