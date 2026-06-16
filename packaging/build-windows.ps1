# Windows-Standalone bauen (.exe, onedir, windowed).
# Aufruf in PowerShell:  .\packaging\build-windows.ps1
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

if (Test-Path .venv\Scripts\Activate.ps1) {
    . .venv\Scripts\Activate.ps1
}

pyinstaller --noconfirm BenchGUI.spec
Write-Host ""
Write-Host "Fertig: dist\BenchGUI\BenchGUI.exe"
Write-Host "Hinweis: Ollama muss laufen (http://localhost:11434)."
Write-Host "Zum Debuggen im Spec console=True setzen (zeigt Tracebacks)."
