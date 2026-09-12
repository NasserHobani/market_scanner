@echo off
chcp 65001 >nul
cd /d "%~dp0"
python serve_lan.py %1
pause
