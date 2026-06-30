@echo off
title Compile Kisnard Server to EXE
echo ===================================================
echo Compiling Kisnard Emulated Server to Standalone EXE
echo ===================================================
echo.

:: Ensure PyInstaller is installed
echo [*] Checking for PyInstaller...
"C:\Users\gooro\AppData\Local\Programs\Python\Python311\python.exe" -m pip show pyinstaller >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [!] PyInstaller not found. Installing via pip...
    "C:\Users\gooro\AppData\Local\Programs\Python\Python311\python.exe" -m pip install pyinstaller
) else (
    echo [*] PyInstaller is already installed.
)
echo.

:: Build the executable
echo [*] Building standalone executable with PyInstaller...
"C:\Users\gooro\AppData\Local\Programs\Python\Python311\python.exe" -m PyInstaller --onefile --noconsole --add-data "java_serialization;java_serialization" kisnard_server.py

if %ERRORLEVEL% eq 0 (
    echo.
    echo [*] Compilation successful!
    echo [*] Executable created in Server/dist/kisnard_server.exe
    
    echo [*] Cleaning up temporary build files...
    rmdir /s /q build
    del /f /q kisnard_server.spec
    
    echo.
    echo ===================================================
    echo Done! You can now run the server using:
    echo dist\kisnard_server.exe
    echo ===================================================
) else (
    echo.
    echo [!] Error: PyInstaller compilation failed.
)
pause
