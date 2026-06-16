#!/usr/bin/env bash
# Startet die Benchmark-GUI direkt aus dem Quellcode (kein Build noetig).
# Beim ersten Start wird automatisch ein .venv angelegt und PySide6 installiert.
# Voraussetzung: Python 3.9+ und ein laufendes Ollama (http://localhost:11434).
set -euo pipefail

# Immer relativ zum Skript-Ordner arbeiten (kein hartcodierter Pfad -> portabel).
cd "$(dirname "$0")"

# Python finden (PYTHON=... erlaubt Override, sonst python3, sonst python).
PY="${PYTHON:-python3}"
command -v "$PY" >/dev/null 2>&1 || PY=python
command -v "$PY" >/dev/null 2>&1 || {
  echo "Fehler: Python 3 nicht gefunden. Bitte installieren (https://python.org)." >&2
  exit 1
}

# venv beim ersten Start anlegen und Abhaengigkeit installieren.
if [ ! -x .venv/bin/python ]; then
  echo "Erstelle virtuelle Umgebung (.venv) und installiere PySide6 ..."
  "$PY" -m venv .venv
  ./.venv/bin/python -m pip install --upgrade pip
  ./.venv/bin/python -m pip install "PySide6>=6.6"
fi

# GUI starten (Argumente werden durchgereicht, z.B. --selftest).
exec ./.venv/bin/python benchmark_gui.py "$@"
