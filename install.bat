@echo off
cd /d "%~dp0"
python -m pip install pandas numpy pyyaml
python -m pip install -r requirements-web.txt
pause
