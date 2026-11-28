# Start Chappa V2 inside WSL Ubuntu, from Windows.
#
#   .\scripts\start-wsl.ps1
#
# The server binds loopback inside WSL; WSL2 forwards it to localhost on
# Windows, so open http://127.0.0.1:7480/ in your normal browser.
#
# First run:  wsl -d Ubuntu -e bash scripts/wsl-bootstrap.sh
param(
  [string]$Distro = "Ubuntu",
  [int]$Port = 7480
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot

# Translate C:\a\b to /mnt/c/a/b so the script path works inside WSL.
$wslRepo = "/mnt/" + $repo.Substring(0, 1).ToLower() + $repo.Substring(2).Replace('\', '/')
$script = "$wslRepo/scripts/start-wsl.sh"

Write-Host "[chappa] repo (WSL): $wslRepo"
Write-Host "[chappa] starting on http://127.0.0.1:$Port/  (Ctrl+C to stop)"

wsl.exe -d $Distro -e bash -lc "CHAPPA_PORT=$Port bash '$script'"
