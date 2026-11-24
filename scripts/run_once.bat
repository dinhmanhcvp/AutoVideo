@echo off
REM Chay 1 luot tu dong (tim truyen -> lam video -> ready\ va gui Telegram neu bat)
cd /d "%~dp0\.."
if exist .venv call .venv\Scripts\activate.bat
set PYTHONUTF8=1
python -m autovideo auto
pause
