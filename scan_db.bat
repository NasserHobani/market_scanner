@echo off
chcp 65001 >nul
cd /d "%~dp0"
python web\manage.py scan --market crypto --live
pause
