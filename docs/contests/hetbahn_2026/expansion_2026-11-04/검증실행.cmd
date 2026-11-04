@echo off
chcp 65001 >nul
set PYTHONUTF8=1
C:\Python314\python.exe "%~dp0verify.py"
set RESULT=%errorlevel%
echo Exit code %RESULT%: 1=failed, 2=files passed but real evidence pending.
pause
exit /b %RESULT%
