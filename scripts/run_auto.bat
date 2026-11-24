@echo off
REM Chay tu dong moi chu de trong config.yaml, ghi log vao logs\auto.log
set PYTHONUTF8=1
cd /d "%~dp0\.."
if not exist logs mkdir logs
echo ===== %date% %time% ===== >> logs\auto.log
if exist .venv call .venv\Scripts\activate.bat
python -m autovideo auto >> logs\auto.log 2>&1
