# Lokaler Büro-LLM-Hardware-Benchmark

Reproduzierbarer Benchmark, der dieselben lokalen KI-Modelle auf verschiedener
Hardware laufen lässt, um eine **Kaufentscheidung** zu treffen:

> **16-GB-GPU-PC**  vs.  **Apple-Silicon-Mac (Unified Memory)**  vs.  **CPU + viel RAM**

Schwerpunkt der Aufgaben: **Büroarbeit** (Zusammenfassen, E-Mails/Texte, Übersetzen,
Extraktion, Dokument-Q&A) plus ein Querschnitt zur Qualitätskontrolle.

## Die eine zentrale Erkenntnis
**Genauigkeit hängt am Modell + Quantisierung, NICHT an der Hardware.** Dasselbe
Modell im selben Quant-Format liefert auf CUDA (GPU), Metal und MLX (Mac) praktisch
identische Qualität. Damit reduziert sich die Hardware-Frage auf:
**Geschwindigkeit + Preis + Speicherkapazität + Energie.**

Die eigentliche Frage ist, in welchem **Regime** deine Arbeit liegt:
- Modelle **bis ~14B** → die 16-GB-GPU gewinnt (mehr Bandbreite pro Euro).
- Modelle **30B–70B** → nur der Mac (oder ein Rechner mit viel RAM) kann sie laden;
  die 16-GB-GPU fällt in CPU-Offload und kollabiert ~10×.

Details: siehe [`docs/01-konzept.md`](docs/01-konzept.md).

---

## Schnellstart

**Voraussetzungen (jedes Gerät):** [Ollama](https://ollama.com/download) + Python 3.9+
(keine weiteren Pakete nötig — nur Standardbibliothek).

```bash
# Windows-PC (CPU + GPU)
python bench.py --label laptop-i9 --pull

# Mac (nur Metal/GPU sinnvoll)
python3 bench.py --label mac-m4-pro-48gb --modes gpu --pull

# Grosser Rechner im Netz (von hier aus messen, ohne dort etwas zu installieren):
#   Windows:  $env:OLLAMA_HOST="http://<ip>:11434"; python bench.py --label bigpc-rtx --modes gpu
#   Linux/Mac: OLLAMA_HOST=http://<ip>:11434 python3 bench.py --label bigpc-rtx --modes gpu

# Nur Setup prüfen, nichts ausführen
python bench.py --check
```

Ergebnisse landen in `results/` als `summary_<label>_<zeit>.md` (Tabelle),
`.csv` und `raw_*.csv` (jeder Einzellauf inkl. Modell-Antwort).
**Die `summary`-Dateien zurückschicken** → daraus entsteht der Geräte-Vergleich.

## Dateien
| Datei | Zweck |
|---|---|
| `bench.py` | Messläufer (Prefill, Decode, TTFT, Qualität) |
| `tasks.json` | Modell-Liste + 5 Büro-Aufgaben (hier anpassen) |
| `docs/01-konzept.md` | Warum/Was: Konzept, 3 Pfade, Kennzahlen, Entscheidungsregel |
| `docs/02-recherche.md` | Recherche: Hardware-/Modell-Zahlen, Methodik, Quellen |
| `docs/03-status-handoff.md` | Aktueller Stand, getroffene Entscheidungen, offene Punkte |

## Gemessene Kennzahlen
- **Prefill** (t/s) – Verarbeitung langer Eingaben (rechenlastig)
- **Decode** (t/s) – Token-Generierung (bandbreitenlastig)
- **TTFT** (ms) – Zeit bis zum ersten Token
- **Qualität** – deterministischer Check (JSON-Schlüssel / erwarteter Inhalt)
- (geplant) **Energie** – Wh pro 1000 Token via Steckdosen-Messgerät

Fair & reproduzierbar: `temperature 0`, fester Seed, feste Kontextlänge,
**Median + p95** über mehrere Läufe, Warmup, Cache-Buster für echte Prefill-Messung.
