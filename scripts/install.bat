@echo off
REM Cai dat AutoVideo tren Windows: tao moi truong Python rieng, cai thu vien, tai font, chay setup.
cd /d "%~dp0\.."
where python >nul 2>nul || (echo Chua co Python. Cai tu https://www.python.org/downloads/ va tick "Add to PATH". & pause & exit /b 1)
where ffmpeg >nul 2>nul || (echo Chua co FFmpeg. Dang cai bang winget... & winget install -e --id Gyan.FFmpeg)
if not exist .venv python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python scripts\get_fonts.py
set PYTHONUTF8=1
python -m autovideo setup
python -m autovideo doctor
echo.
echo Xong! Mo lai cua so lenh neu vua cai FFmpeg. Chay thu: scripts\run_once.bat
pause
