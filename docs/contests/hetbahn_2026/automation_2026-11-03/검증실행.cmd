@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
if exist "C:\Python314\python.exe" (
  "C:\Python314\python.exe" "%~dp0run_checks.py"
) else (
  py -3 "%~dp0run_checks.py"
)
set "HTB_RESULT=%ERRORLEVEL%"
echo.
if "%HTB_RESULT%"=="0" echo 제출 자료 검사가 통과했습니다. 실제 게시와 접수는 별도입니다.
if "%HTB_RESULT%"=="2" echo 필수 증거가 아직 남아 있습니다. reports\latest.md를 확인하세요.
if "%HTB_RESULT%"=="1" echo 검사에서 오류를 발견했습니다. reports\latest.md를 확인하세요.
echo 결과: %~dp0reports\latest.html
pause
exit /b %HTB_RESULT%
