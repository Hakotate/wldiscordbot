@echo off
setlocal
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$root = '%~dp0'.TrimEnd('\');" ^
  "$logDir = Join-Path $root 'logs';" ^
  "$pidFile = Join-Path $logDir 'discord_bot.pid';" ^
  "New-Item -ItemType Directory -Force -Path $logDir | Out-Null;" ^
  "if (Test-Path $pidFile) {" ^
  "  $existingPid = Get-Content -LiteralPath $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1;" ^
  "  if ($existingPid -and (Get-Process -Id $existingPid -ErrorAction SilentlyContinue)) {" ^
  "    Write-Host ('Discord bot is already running with PID ' + $existingPid);" ^
  "    exit 0;" ^
  "  }" ^
  "}" ^
  "py -m pip install -r (Join-Path $root 'requirements.txt') | Out-Host;" ^
  "if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }" ^
  "py -m playwright install chromium | Out-Host;" ^
  "if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }" ^
  "$pythonExe = py -c \"import sys; print(sys.executable)\";" ^
  "$pythonExe = $pythonExe | Select-Object -Last 1;" ^
  "$stdout = Join-Path $logDir 'discord_bot.stdout.log';" ^
  "$stderr = Join-Path $logDir 'discord_bot.stderr.log';" ^
  "$process = Start-Process -FilePath $pythonExe -ArgumentList 'discord_bot.py' -WorkingDirectory $root -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru;" ^
  "Set-Content -LiteralPath $pidFile -Value $process.Id -Encoding ascii;" ^
  "Write-Host ('Discord bot started with PID ' + $process.Id);"

if errorlevel 1 (
  echo.
  echo Failed to start the Discord bot.
  exit /b 1
)
