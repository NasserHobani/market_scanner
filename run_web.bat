@echo off
cd /d "%~dp0"
python web\manage.py migrate
if errorlevel 1 goto fail
python web\manage.py scan --market crypto
start "" http://127.0.0.1:8000/
python web\manage.py runserver
goto end
:fail
echo Setup failed. Run install.bat first.
:end
pause
