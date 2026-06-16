# Status & Handoff

Stand: 2026-06-16. Dieses Dokument fasst zusammen, was bis hierhin gebaut/entschieden
wurde und wie es weitergeht.

## Umgebung (dieser Laptop)
- **CPU**: 13th Gen Intel Core i9-13980HX (24 Kerne / 32 Threads)
- **GPU**: NVIDIA RTX 1000 Ada Laptop, **nur 6 GB VRAM** (+ Intel UHD iGPU)
- **RAM**: 64 GB
- **OS**: Windows 11 Enterprise
- Installiert: **Ollama 0.30.8**, Python 3.12, git, huggingface-cli

→ Dieser Laptop deckt **Pfad C** (CPU + viel RAM) und einen **kleinen-GPU-Fall** ab.
Er ist **kein** 16-GB-GPU-Test (nur 6 GB). Pfad A muss über den großen Rechner im Netz
oder eine geliehene/gemietete 16-GB-GPU kommen.

## Getroffene Entscheidungen
1. **Gemeinsame Laufzeit: Ollama** auf allen Geräten (niedrigste Hürde, direkt vergleichbar).
2. **Modell-Speicher nach `D:` ausgelagert**: `OLLAMA_MODELS = D:\KI\ollama-models`
   (dauerhaft als User-Variable gesetzt). Grund: `C:` hatte nur 29 GB frei; nach Umzug
   wieder ~46 GB frei. Bereits vorhandene Modelle wurden mitverschoben (nichts verloren).
3. **Aufgaben-Fokus**: Büroarbeit + Querschnitt (siehe `tasks.json`).

## Was gebaut wurde
- `bench.py` — Messläufer (reines Python/Stdlib). Misst Prefill, Decode, TTFT, Qualität;
  Modi `gpu`/`cpu`; schreibt `results/summary_*.md|csv` und `raw_*.csv` (inkl. Antworttext).
- `tasks.json` — Modell-Liste + 5 Büro-Aufgaben (Zusammenfassen, E-Mail, Übersetzen,
  JSON-Extraktion, Doc-Q&A).
- `README.md`, `docs/01-konzept.md`, `docs/02-recherche.md`, dieses Dokument.

### Update (GUI)
- `benchmark_gui.py` — grafisches Frontend (PySide6) für `bench.py`: Ollama-Host,
  **„Modelle suchen"** (Scan installierter Modelle + Erreichbarkeits-Check), Modell-Dropdown,
  Modus/Reps/Warmup/Label, **Test starten/Abbrechen** (eigener QThread, GUI friert nicht ein),
  Live-Fortschritt + Log, Ergebnistabelle + **GESAMT**-Zeile, Export **CSV/MD/JSON**.
- Einzige `bench.py`-Anpassung: `run_once(..., should_cancel=None)` für kooperativen Abbruch
  (rückwärtskompatibel, CLI unverändert).
- Standalone baubar mit PyInstaller (`BenchGUI.spec`, `packaging/build-*`), Doku in
  `docs/04-gui.md`. Läuft auf Windows/macOS/Linux (pro OS separat bauen). **Ollama bleibt
  externe Voraussetzung** (nicht gebündelt).
- `requirements.txt` (PySide6, pyinstaller), `tests/test_bench.py` (13 Unit-Tests, grün).
  Getestet: voller End-to-End-Lauf über die echten QThreads gegen Ollama (`llama3.2:3b`).

## Bereits vorhandene Ollama-Modelle (auf diesem Laptop)
`llama3.1:8b`, `gemma3:4b`, `gemma3:12b` (+ Embeddings `bge-m3`, `nomic-embed-text`).
→ Diese könnten als Basis dienen, um Downloads zu sparen.

## Smoke-Test-Ergebnis (Beweis, dass die Messkette läuft)
`llama3.1:8b`, GPU-Modus (hybrid, da 8B nicht in 6 GB passt), 2 Wiederholungen:

| Task | TTFT | Prefill (t/s) | Decode (t/s) | Qualität |
|---|---|---|---|---|
| Zusammenfassen (langer Input) | 3,1 s | ~920 | ~9 | – |
| E-Mail schreiben | 2,5 s | ~470 | ~12 | – |
| Übersetzen | 2,5 s | ~430 | ~14 | – |
| JSON-Extraktion | 2,6 s | ~327 | ~14 | ✅ ok |
| Doc-Q&A | 2,6 s | ~335 | ~11 | ✅ ok* |

\* Doc-Q&A schlug zuerst fehl, weil die Prüfung ASCII („Maerz") gegen den Umlaut
(„März") verglich. **Behoben**: Qualitätsprüfung ist jetzt umlaut-tolerant
(`ä→ae` usw.), und die Modell-Antwort wird ins Roh-CSV geschrieben.

Einordnung: ~9–14 t/s Decode = CPU/hybrid-limitiert (nur 6 GB GPU). Genau diese Art
Zahl liefert am Ende den Plattform-Vergleich.

## Offene Punkte (für die Fortsetzung)
1. **Modell-Liste / Aufgaben bestätigen** — passt `tasks.json`, oder etwas rein/raus?
   Vorschlag: vorhandene Modelle (`llama3.1:8b`, `gemma3:4b/12b`) als Basis nutzen.
2. **Großer Rechner im Netz** (Pfad A): GPU + VRAM, RAM, OS, **IP/Hostname**, und ob
   Ollama dort im Netz erreichbar ist (`OLLAMA_HOST=0.0.0.0:11434` + Firewall Port 11434).
   Welche großen Modelle dort testen (32B / 70B / größer)?
3. **Die 2 Macs**: jeweils **Chip + RAM** (z. B. „M3 Pro / 36 GB", „M4 Max / 64 GB").

## Nächste Schritte / Befehle
```bash
# Voller Lauf auf diesem Laptop (GPU + CPU), Standardmodelle ziehen:
python bench.py --label laptop-i9 --pull

# Grossen Rechner im Netz von hier aus messen (nichts dort installieren ausser Ollama):
#   Windows:  $env:OLLAMA_HOST="http://<ip>:11434"; python bench.py --label bigpc --modes gpu
#   Linux/Mac: OLLAMA_HOST=http://<ip>:11434 python3 bench.py --label bigpc --modes gpu

# Mac (Bekannte): Ollama installieren, dann:
python3 bench.py --label mac-m4-pro-48gb --modes gpu --pull
```
Große Modelle aktivieren: in `tasks.json` aus `models_optional_gross` nach `models` kopieren.

## Auswertung (Ziel)
Pro Modell-Tier eine Tabelle: **t/s pro 1000 €**, **Wh/1000 Token**, Genauigkeit (1×),
und „läuft / läuft nicht" pro Modellgröße. Daraus die finale GPU-vs-Mac-vs-RAM-Empfehlung.
