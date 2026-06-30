@echo off
echo Checking Python environment...

:: Target the working Python 3.11 installation first
set PYTHON_EXE="C:\Users\gooro\AppData\Local\Programs\Python\Python311\python.exe"

if not exist %PYTHON_EXE% (
    echo Python 3.11 not found at default path, falling back to system 'python'...
    set PYTHON_EXE=python
)

echo Using Python: %PYTHON_EXE%
echo Installing dependencies (pygame)...
%PYTHON_EXE% -m pip install pygame

echo Starting Kisnard Python Client...
if exist "%~dp0kisnard_client.py" (
    %PYTHON_EXE% "%~dp0kisnard_client.py"
) else (
    %PYTHON_EXE% "%~dp0python_client\kisnard_client.py"
)

if %ERRORLEVEL% neq 0 (
    echo Client exited with an error.
    pause
)
