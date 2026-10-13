@echo off
cd /d "%~dp0"
if exist "%LOCALAPPDATA%\Thermy9\thermy9.exe" (
  start "" "%LOCALAPPDATA%\Thermy9\thermy9.exe"
  exit /b
)
if exist "dist\thermy9.exe" (
  start "" "dist\thermy9.exe"
  exit /b
)
call "Start Thermy9 Legacy.cmd"
