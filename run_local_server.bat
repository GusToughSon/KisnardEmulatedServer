@echo off
title Kisnard Emulated Local Server
echo Starting Kisnard Emulated Local Server...
echo Loading SSL Certificates and starting listener on 127.0.0.1:34215...
echo.

:: Patch checksums for the truststore before starting
"C:\Users\gooro\AppData\Local\Programs\Python\Python311\python.exe" scratch\patch_checksums.py

:: Use Python 3.11
"C:\Users\gooro\AppData\Local\Programs\Python\Python311\python.exe" kisnard_server.py


if %ERRORLEVEL% neq 0 (
    echo.
    echo Server exited with an error.
    pause
)
