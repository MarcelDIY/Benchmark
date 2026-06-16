@echo off
REM Startet die Benchmark-GUI direkt aus dem Quellcode (kein Build noetig).
REM Beim ersten Start wird automatisch ein .venv angelegt und PySide6 installiert.
REM Voraussetzung: Python 3.9+ und ein laufendes Ollama (http://localhost:11434).
setlocal

REM Immer relativ zum Skript-Ordner arbeiten (kein hartcodierter Pfad).
cd /d "%~dp0"

REM Python finden (py-Launcher bevorzugt, sonst python).
set "PY=py -3"
%PY% --version >nul 2>&1
if errorlevel 1 set "PY=python"
%PY% --version >nul 2>&1
if errorlevel 1 (
  echo Fehler: Python 3 nicht gefunden. Bitte installieren ^(https://python.org^).
  pause
  exit /b 1
)

REM venv beim ersten Start anlegen und Abhaengigkeit installieren.
if not exist ".venv\Scripts\python.exe" (
  echo Erstelle virtuelle Umgebung ^(.venv^) und installiere PySide6 ...
  %PY% -m venv .venv
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  ".venv\Scripts\python.exe" -m pip install "PySide6>=6.6"
)

REM GUI starten (Argumente werden durchgereicht).
".venv\Scripts\python.exe" benchmark_gui.py %*
