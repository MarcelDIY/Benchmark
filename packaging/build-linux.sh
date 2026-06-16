#!/usr/bin/env bash
# Linux-Standalone bauen (onedir, GUI).
# Tipp: auf moeglichst ALTER glibc bauen (aelteres Ubuntu / manylinux-Container),
# damit das Binary auch auf neueren Systemen laeuft (glibc ist nur vorwaerts-kompatibel).
set -euo pipefail
cd "$(dirname "$0")/.."

if [ -d .venv ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

pyinstaller --noconfirm BenchGUI.spec
echo
echo "Fertig: dist/BenchGUI/BenchGUI"
echo "Laufzeit-Abhaengigkeiten auf dem Zielsystem: libGL (libgl1) und libxcb-cursor0."
echo "Ausserdem muss Ollama laufen (http://localhost:11434)."
