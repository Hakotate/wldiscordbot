@echo off
setlocal
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$root = '%~dp0'.TrimEnd('\');" ^
  "$pidFile = Join-Path $root 'logs\\discord_bot.pid';" ^
  "if (-not (Test-Path $pidFile)) {" ^
  "  Write-Host 'No PID file found. The bot may already be stopped.';" ^
  "  exit 0;" ^
  "}" ^
  "$botPid = Get-Content -LiteralPath $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1;" ^
  "if ($botPid -and (Get-Process -Id $botPid -ErrorAction SilentlyContinue)) {" ^
  "  Stop-Process -Id $botPid -Force;" ^
  "  Write-Host ('Stopped Discord bot PID ' + $botPid);" ^
  "} else {" ^
  "  Write-Host 'PID file was present, but the process was not running.';" ^
  "}" ^
  "Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue;"

echo.
pause
