@echo off
setlocal
cd /d "%~dp0"

echo Installing or updating dependencies...
py -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo Dependency installation failed.
  pause
  exit /b 1
)

echo.
echo Ensuring the Chromium snapshot renderer is installed...
py -m playwright install chromium
if errorlevel 1 (
  echo.
  echo Playwright Chromium installation failed.
  pause
  exit /b 1
)

echo.
echo Starting the Discord bot...
py discord_bot.py

echo.
echo The bot process stopped.
pause
