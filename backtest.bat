@echo off
cd /d "%~dp0"
python backtest.py --market crypto --top 30 --split
pause
