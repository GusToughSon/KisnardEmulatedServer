@echo off
setlocal
cd /d "%~dp0"
title Kisnard Online

set "PYTHON_EXE="
if exist "%LocalAppData%\Programs\Python\Python311\pythonw.exe" set "PYTHON_EXE=%LocalAppData%\Programs\Python\Python311\pythonw.exe"
if not defined PYTHON_EXE where pyw >nul 2>nul && set "PYTHON_EXE=pyw -3.11"
if not defined PYTHON_EXE where pythonw >nul 2>nul && set "PYTHON_EXE=pythonw"

if not defined PYTHON_EXE (
    echo Kisnard Online requires Python 3.11.
    echo Install Python 3.11, then run this launcher again.
    pause
    exit /b 1
)

%PYTHON_EXE% -c "import pygame; from PIL import Image" >nul 2>nul
if errorlevel 1 (
    echo Kisnard Online is missing its Python graphics components.
    echo Run: py -3.11 -m pip install pygame Pillow
    pause
    exit /b 1
)

start "" /wait %PYTHON_EXE% "%~dp0kisnard_client.py"
if errorlevel 1 (
    echo.
    echo Kisnard Online closed because of an error.
    echo Run kisnard_client.py from a command window to see the details.
    pause
    exit /b 1
)

endlocal
