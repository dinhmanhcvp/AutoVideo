@echo off
REM Mo giao dien cho DIEN THOAI cung Wi-Fi (co ma bao ve). Dong cua so nay de tat.
cd /d "%~dp0"
if exist .venv call .venv\Scripts\activate.bat
set PYTHONUTF8=1
python -m autovideo ui --lan
pause
