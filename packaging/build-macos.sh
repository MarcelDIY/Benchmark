#!/usr/bin/env bash
# macOS-Standalone bauen (.app-Bundle, windowed).
set -euo pipefail
cd "$(dirname "$0")/.."

if [ -d .venv ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

pyinstaller --noconfirm BenchGUI.spec
echo
echo "Fertig: dist/BenchGUI.app"
echo
echo "Unsigniert -> Gatekeeper meckert evtl. Lokal freigeben mit:"
echo "  xattr -dr com.apple.quarantine dist/BenchGUI.app"
echo "Oder Rechtsklick auf die App > Oeffnen."
echo "Universal (Intel+ARM) nur mit target_arch='universal2' im Spec UND universal2-Wheels."
echo "Ausserdem muss Ollama laufen (http://localhost:11434)."
