# GUI & Standalone-Bauen

`benchmark_gui.py` ist ein grafisches Frontend (PySide6/Qt) fuer `bench.py`. Es
benutzt **dieselbe Mess-Logik** wie das CLI — die Zahlen sind identisch.

## Was die GUI kann
- **Ollama-Host** eingeben (Standard `http://localhost:11434`).
- **Modelle suchen** → fragt Ollama ab, zeigt an, ob es erreichbar ist, und
  fuellt das Modell-Dropdown mit den lokal installierten Modellen.
- **Ein Modell** auswaehlen, **Modus** (gpu/cpu), **Wiederholungen**, **Warmup**
  und ein **Label** (Maschinenname) setzen.
- **Test starten** → laeuft alle Buero-Aufgaben durch, ohne die Oberflaeche
  einzufrieren (eigener Thread). Live-Fortschritt + Log.
- **Abbrechen** jederzeit (kooperativ, reagiert auch mitten in der Generierung).
- **Ergebnistabelle** je Task (TTFT, Prefill, Decode, Decode p95, Qualitaet) plus
  eine fette **GESAMT**-Zeile ueber alle Tasks.
- **Tatsaechliche GPU/CPU-Verteilung** nach dem Lauf (aus Ollama `/api/ps`): zeigt,
  ob das Modell komplett auf GPU/CPU lief oder hybrid (z. B. „85% GPU / 15% CPU").
- **„Aufgaben & Infos"**-Button: erklaert die Kennzahlen/Begriffe und zeigt alle
  Aufgaben inkl. vollem Prompt-Inhalt.
- **Export** als CSV, Markdown oder JSON (CSV/MD sind byte-identisch zum CLI).
- Eigenes **App-Icon** (`assets/icon.png`, generierbar via `assets/make_icon.py`).

> Voraussetzung: ein laufendes **Ollama**. Es wird bewusst **nicht** mitgebuendelt
> (Go-Binary + mehrere GB Modelle). Die App ist „standalone" im Sinne von
> *kein installiertes Python noetig* — Ollama bleibt externe Voraussetzung.

## Starten (Entwicklung)
```bash
python3 -m venv .venv
source .venv/bin/activate.fish        # fish; sonst .venv/bin/activate
pip install -r requirements.txt
python benchmark_gui.py
```

## Standalone bauen (PyInstaller)
PyInstaller **cross-kompiliert nicht** — jedes Ziel-OS muss auf genau diesem OS
gebaut werden. Konfiguration steckt in `BenchGUI.spec`.

| OS | Befehl | Ergebnis |
|---|---|---|
| Linux | `packaging/build-linux.sh` | `dist/BenchGUI/BenchGUI` |
| macOS | `packaging/build-macos.sh` | `dist/BenchGUI.app` |
| Windows | `packaging\build-windows.ps1` | `dist\BenchGUI\BenchGUI.exe` |

Oder direkt: `pyinstaller --noconfirm BenchGUI.spec`

### Laufzeit-Abhaengigkeiten
- **Alle:** Ollama muss laufen (`http://localhost:11434`).
- **Linux (Zielsystem):** `libgl1` und `libxcb-cursor0` (Qt 6.5+). Auf dem
  Build-System idealerweise auf moeglichst alter glibc bauen.
- **macOS:** unsigniert → Gatekeeper. Lokal freigeben:
  `xattr -dr com.apple.quarantine dist/BenchGUI.app` oder Rechtsklick → Oeffnen.

### Debuggen
`--windowed` verschluckt `stdout`/Tracebacks. Bei stummen Abstuerzen im Spec
`console=False` voruebergehend auf `True` setzen und neu bauen.

## Architektur (kurz)
- `bench.py` bleibt der Messkern (reine stdlib). Einzige Anpassung fuer die GUI:
  `run_once(..., should_cancel=None)` — optionaler Abbruch-Callback, CLI unveraendert.
- Host-Wechsel zur Laufzeit: die GUI setzt `bench.OLLAMA = host` (wird in `_req`
  bei jedem Request gelesen).
- Threading: QObject-Worker via `moveToThread`; der Worker fasst nie ein Widget
  an, alles laeuft ueber Signale. Abbruch ueber ein `threading.Event`.
