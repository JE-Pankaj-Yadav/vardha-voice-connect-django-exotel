@echo off
setlocal
cd /d "%~dp0"
if not exist ".env" (
  copy /Y ".env.example" ".env" >nul
  echo Created .env from .env.example.
)
echo.
echo Opening .env in Notepad...
notepad ".env"
echo.
echo Save the file, close Notepad, then run run.bat again.
echo.
pause
