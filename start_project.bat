@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "EXIT_CODE="
set "VENV_DIR=venv"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"
set "VENV_ACTIVATE=%VENV_DIR%\Scripts\activate.bat"

if not exist "%VENV_PYTHON%" (
    echo Creating virtual environment...
    where py >nul 2>&1
    if not errorlevel 1 (
        py -3 -m venv "%VENV_DIR%"
    ) else (
        python -m venv "%VENV_DIR%"
    )
    if errorlevel 1 goto :error
)

echo Activating virtual environment...
call "%VENV_ACTIVATE%"
if errorlevel 1 goto :error

echo Installing project dependencies...
python -m pip install --upgrade pip
if errorlevel 1 goto :error
python -m pip install -r requirement.txt
if errorlevel 1 goto :error

if not exist ".env" (
    copy /Y ".env.example" ".env" >nul
    echo.
    echo A new .env file was created.
    echo Set BALE_BOT_TOKEN and DJANGO_SECRET_KEY, then run this file again.
    goto :pause_error
)

echo Applying database migrations...
python manage.py migrate --noinput
if errorlevel 1 goto :error

set "LOCAL_IP=127.0.0.1"
for /f "delims=" %%I in ('python "scripts\get_local_ip.py"') do set "LOCAL_IP=%%I"
set "DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,%LOCAL_IP%"

echo.
echo Local panel:   http://127.0.0.1:8000/panel/
echo Phone access: http://%LOCAL_IP%:8000/panel/
echo Bale polling will start with Django.
echo Opening the panel in your browser...
start "" "http://127.0.0.1:8000/panel/"

echo Starting Django server on 0.0.0.0:8000...
python manage.py runserver 0.0.0.0:8000
set "EXIT_CODE=%ERRORLEVEL%"
goto :finish

:error
set "EXIT_CODE=%ERRORLEVEL%"
if "%EXIT_CODE%"=="0" set "EXIT_CODE=1"
echo.
echo Project startup failed with exit code %EXIT_CODE%.

:pause_error
if not defined EXIT_CODE set "EXIT_CODE=1"
pause

:finish
endlocal & exit /b %EXIT_CODE%
