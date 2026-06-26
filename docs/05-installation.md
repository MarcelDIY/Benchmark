# 📥 Installation – Schritt für Schritt

Diese Anleitung richtet sich an **Anwender**, die das fertige Programm einfach
ausprobieren wollen – **ohne Python, ohne Programmierkenntnisse**. Du lädst ein
fertiges Doppelklick-Programm herunter und startest es.

> **Kurzfassung:** 1) Ollama installieren + ein Modell laden → 2) das passende
> Benchmark-Paket von der [Release-Seite](https://github.com/MarcelDIY/Benchmark/releases/latest)
> laden → 3) entpacken → 4) starten. Fertig.

---

## Schritt 1 – Ollama installieren (Pflicht, einmalig)

Das Benchmark-Programm misst **deine lokalen KI-Modelle**. Diese Modelle laufen in
**Ollama** – einem kostenlosen Programm, das die KI auf deinem Rechner ausführt.
**Ohne laufendes Ollama mit mindestens einem Modell zeigt das Benchmark nichts an.**

1. **Ollama herunterladen und installieren:** <https://ollama.com/download>
   (Windows, macOS und Linux – ganz normaler Installer).
2. **Ollama starten.** Auf Windows/macOS startet es nach der Installation von selbst
   und legt ein kleines Symbol in die Menü-/Taskleiste. Unter Linux läuft es als
   Dienst bzw. per `ollama serve`.
3. **Ein Modell laden** – öffne ein Terminal (Windows: *PowerShell* oder
   *Eingabeaufforderung*; macOS: *Terminal*; Linux: deine Shell) und tippe:

   ```bash
   ollama pull llama3.2:3b
   ```

   Das ist ein kleines, schnelles Einsteigermodell (~2 GB), das auf fast jeder
   Hardware läuft. Wer mehr RAM/VRAM hat, kann später größere Modelle nehmen, z. B.:

   ```bash
   ollama pull qwen2.5:7b
   ollama pull qwen2.5:14b
   ```

> **Test, ob Ollama läuft:** Öffne im Browser <http://localhost:11434> – es sollte
> *„Ollama is running"* erscheinen. Klappt das, ist die wichtigste Voraussetzung erfüllt.

---

## Schritt 2 – Das richtige Paket herunterladen

Alle fertigen Programme liegen auf der **Release-Seite**:

👉 **<https://github.com/MarcelDIY/Benchmark/releases/latest>**

Scrolle dort zu **„Assets"** und lade **genau die eine Datei** für dein System:

| Dein System | Datei |
|---|---|
| **Windows** (10/11, 64-Bit) | `BenchGUI-windows-x64.zip` |
| **Mac mit Apple Silicon** (M1/M2/M3/M4) | `BenchGUI-macos-arm64.tar.gz` |
| **Mac mit Intel-Prozessor** | `BenchGUI-macos-x64.tar.gz` |
| **Linux** (64-Bit) | `BenchGUI-linux-x64.tar.gz` |

> **Welcher Mac bin ich?** Apple-Menü () oben links → *„Über diesen Mac"*. Steht
> dort ein **Apple-Chip (M1/M2/…)** → `arm64`. Steht dort **Intel** → `x64`.

Dann weiter beim passenden Abschnitt:
[Windows](#windows) · [macOS](#macos) · [Linux](#linux).

---

## Windows

1. **ZIP entpacken:** Rechtsklick auf `BenchGUI-windows-x64.zip` → *„Alle extrahieren…"*.
   Es entsteht ein **Ordner `BenchGUI`** – wichtig: den **ganzen Ordner** behalten,
   nicht nur die `.exe` herausziehen (die Datei braucht die Dateien daneben).
2. **Starten:** In den Ordner `BenchGUI` gehen und **`BenchGUI.exe` doppelklicken**.
3. **Sicherheitswarnung von Windows** („Der Computer wurde durch Windows geschützt"):
   Das Programm ist neu und nicht teuer signiert – die Meldung ist hier normal.
   → **„Weitere Informationen"** klicken → **„Trotzdem ausführen"**.

> Optional: `BenchGUI.exe` per Rechtsklick → *„An Start anheften"* oder eine
> Verknüpfung auf den Desktop legen.

---

## macOS

1. **Entpacken:** Die geladene `…tar.gz` im *Downloads*-Ordner **doppelklicken** –
   macOS entpackt sie zu **`BenchGUI.app`**. Verschiebe die App nach *Programme*
   (oder lass sie liegen, beides geht).
2. **Erststart (wichtig – die App ist nicht signiert):** Ein normaler Doppelklick
   wird beim ersten Mal **blockiert** („… kann nicht geöffnet werden, da Apple sie
   nicht überprüfen kann"). Stattdessen:
   **Rechtsklick** (bzw. Ctrl-Klick) auf `BenchGUI.app` → **„Öffnen"** → im Dialog
   nochmal **„Öffnen"**. Das ist nur **einmal** nötig, danach startet sie normal.

   Falls der Rechtsklick-Weg nicht erscheint, im *Terminal* einmal ausführen:

   ```bash
   xattr -dr com.apple.quarantine /Pfad/zu/BenchGUI.app
   ```

   (Tipp: `xattr -dr com.apple.quarantine ` tippen, dann die App ins Terminal ziehen
   – der Pfad wird automatisch eingefügt – und Enter drücken.)

> **Achtung Architektur:** Auf einem Apple-Silicon-Mac das **arm64**-Paket nehmen,
> auf einem Intel-Mac das **x64**-Paket. Das falsche Paket startet nicht oder ist
> deutlich langsamer.

---

## Linux

1. **Entpacken** (Dateimanager: Rechtsklick → *Entpacken*; oder im Terminal):

   ```bash
   tar -xzf BenchGUI-linux-x64.tar.gz
   ```

   Es entsteht ein **Ordner `BenchGUI`**.
2. **Starten:**

   ```bash
   ./BenchGUI/BenchGUI
   ```

   (Im Dateimanager ggf. erst Rechtsklick → *Eigenschaften* → *„Als Programm
   ausführbar"* aktivieren, dann Doppelklick auf `BenchGUI`.)
3. **Falls beim Start eine Qt-Bibliothek fehlt** (Fehlermeldung mit `libGL` oder
   `xcb-cursor`), die zwei System-Pakete nachinstallieren:

   ```bash
   # Debian/Ubuntu/Mint:
   sudo apt install libgl1 libxcb-cursor0
   # Fedora:
   sudo dnf install mesa-libGL xcb-util-cursor
   # Arch:
   sudo pacman -S libglvnd xcb-util-cursor
   ```

---

## Erste Schritte im Programm

1. Oben den **Ollama-Host** prüfen (Standard `http://localhost:11434` ist richtig,
   wenn Ollama auf demselben Rechner läuft).
2. **„Modelle suchen"** klicken → das Dropdown füllt sich mit deinen geladenen Modellen.
3. Ein **Modell** wählen, **Modus** (gpu/cpu) und ggf. **Label** setzen → **„Test starten"**.
4. Nach dem Lauf siehst du KPIs, Tabelle, GPU/CPU-Ring und Balken. Mehrere Modelle
   nacheinander testen → Reiter **„Vergleich"**. Auf Knopfdruck die **Cloud-Referenz**
   (Claude Opus/Sonnet/Haiku) als Richtwert einblenden.

---

## Häufige Probleme

| Problem | Ursache & Lösung |
|---|---|
| **„Modelle suchen" findet nichts / leere Liste** | Ollama läuft nicht oder hat kein Modell. Prüfe <http://localhost:11434> und lade ein Modell: `ollama pull llama3.2:3b`. |
| **„Verbindung fehlgeschlagen" / Timeout** | Ollama ist nicht gestartet. Ollama-App öffnen (Win/macOS) bzw. `ollama serve` (Linux). Anderer Rechner? Host als `http://<ip>:11434` eintragen – dort muss Ollama Verbindungen erlauben (`OLLAMA_HOST=0.0.0.0`). |
| **Windows blockiert den Start (SmartScreen)** | „Weitere Informationen" → „Trotzdem ausführen". Die App ist unsigniert, aber harmlos. |
| **macOS: „kann nicht geöffnet werden"** | Rechtsklick → „Öffnen" (statt Doppelklick), oder `xattr -dr com.apple.quarantine BenchGUI.app`. |
| **macOS startet nicht / sehr langsam** | Falsche Architektur geladen – Intel braucht `x64`, Apple Silicon braucht `arm64`. |
| **Linux: Fehler mit `libGL`/`xcb-cursor`** | System-Pakete `libgl1` + `libxcb-cursor0` nachinstallieren (siehe oben). |

---

## Alternative: aus dem Quellcode starten

Wer Python kennt und lieber den Quellcode nutzt, findet den Entwickler-Weg
(Starter-Skripte bzw. `venv` + `pip install -r requirements.txt`) in der
[README → Schnellstart](../README.md#-schnellstart) und in [`04-gui.md`](04-gui.md).
