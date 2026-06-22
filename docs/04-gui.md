# GUI & Standalone-Bauen

`benchmark_gui.py` ist ein grafisches Frontend (PySide6/Qt) fuer `bench.py`. Es
benutzt **dieselbe Mess-Logik** wie das CLI — die Zahlen sind identisch.

Dark-Dashboard im Tokyo-Night-Stil; die Diagramme sind SVG (`svgcharts.py`), per
`QSvgRenderer` als scharfes Bild gerendert. Screenshots: siehe `assets/screenshots/`.
Diese werden reproduzierbar aus der echten GUI erzeugt (Demo-Daten, offscreen):
`./.venv/bin/python tools/make_screenshots.py` – nach GUI-Änderungen einmal laufen lassen.

## Was die GUI kann
- **Ollama-Host** eingeben (Standard `http://localhost:11434`, auch Rechner im Netz).
- **Modelle suchen** (synchroner Scan) → fuellt das Dropdown mit den installierten Modellen.
- **Modell**, **Modus** (gpu/cpu), **Wiederholungen**, **Warmup**, **Label** setzen,
  **Test starten** (eigener Thread, GUI friert nicht ein), jederzeit **Abbrechen**
  (kooperativ, reagiert auch mitten in der Generierung).
- Reiter **„Aktueller Lauf":** vier **KPI-Kacheln**, Ergebnis-**Tabelle** je Aufgabe
  (+ fette **GESAMT**-Zeile), **GPU/CPU-Ring** (Modell 100 % verteilt auf GPU+CPU,
  aus `/api/ps`) und **Balken je Lauf** (Aufgabe in der Tabelle waehlen; Metrik
  umschaltbar) inkl. **Warmup-Balken** (Kaltstart) und Durchschnittslinie.
- Reiter **„Vergleich":** mehrere Laeufe verschiedener Modelle in EINER Sitzung
  sammeln und gegenueberstellen (Balken + Tabelle). Kennzahl umschaltbar:
  Decode, Prefill, TTFT, **Decode p95, Qualitaet, Kaltstart, Speicherbedarf,
  Gesamtdauer**, GPU-Anteil. Der **beste Wert je Spalte** wird grün/fett markiert
  (richtungsabhaengig); **⚠**-Laeufe (z. B. Qualitaet 0 %) gelten als fehlerhaft und
  zaehlen nicht beim Bestwert. Die Groesse steht in **GB**. **„Lauf laden"** importiert
  exportierte JSON-Ergebnisse (auch von anderen Rechnern) in den Vergleich.
  **„Cloud-Referenz"**-Knopf blendet Claude Opus/Sonnet/Haiku als Richtwert ein
  (aus `reference_cloud.json`).
- **Hilfe-Menue** (oben): Bedienung, Begriffe, Aufgaben (inkl. vollem Prompt),
  Lizenz, Ueber.
- **Export** als CSV, Markdown oder JSON (CSV/MD byte-identisch zum CLI).
- Eigenes **Tacho-Icon** + Pfeil-Assets (`assets/make_icon.py`).

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

> **Ohne fremde Hardware:** `.github/workflows/build.yml` baut bei jedem Tag-Push
> (`v*`) alle vier Bundles in der Cloud — **Linux, Windows, macOS arm64 + x86_64** —
> und hängt sie an ein GitHub-Release. Ideal, wenn man (wie hier) nur Linux-Rechner
> hat. Lokaler Build nur noch für schnelle Tests nötig.

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
- `bench.py` bleibt der Messkern (reine stdlib). GUI-Anpassungen, rueckwaerts-
  kompatibel: `run_once(..., should_cancel=None, on_response=None)` (kooperativer
  Abbruch, auch waehrend Modell-Load), `http_json/installed_models(timeout=…)`.
- Host-Wechsel zur Laufzeit: die GUI setzt `bench.OLLAMA = host` (wird in `_req`
  bei jedem Request gelesen).
- **Scan synchron** (kurzer HTTP-Call) – kein Thread. Der **Benchmark** laeuft im
  QObject-Worker via `moveToThread`; der Worker fasst nie ein Widget an, alles ueber
  Signale. Abbruch ueber `threading.Event` + Schliessen der offenen Antwort.
- Wichtig (Lehre): Worker/Thread-Referenzen erst an `thread.finished` loesen, NICHT
  im Signal-Slot – sonst Heap-Korruption auf xcb. Siehe `_clear_threads`.
