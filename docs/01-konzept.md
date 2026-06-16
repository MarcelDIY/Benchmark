# Konzept & Entscheidungsrahmen

## Ziel
Herausfinden, ob sich für lokale KI (Schwerpunkt Büroarbeit) der Kauf von
**GPU-Hardware** oder einem **Apple-Silicon-Mac** lohnt — oder ob ein Rechner mit
**viel RAM + starker CPU** schon ausreicht. Getestet werden Modelle, die bis max.
**16 GB GPU** brauchen oder **komplett im RAM** laufen.

## Die zentrale Erkenntnis
**Qualität/Genauigkeit ist eine Eigenschaft von (Modell + Quantisierung), nicht der Hardware.**
Dasselbe Modell im selben Quant-Format liefert auf CUDA, Metal und MLX praktisch
identische Antworten (Unterschiede liegen im Floating-Point-Rauschen, < 1 Punkt).

Folge: Genauigkeit misst man **einmal pro Modell** — die Hardware-Entscheidung ist
rein **Geschwindigkeit + Preis + Speicherkapazität + Energie**.

## Die zwei Engpässe (getrennt messen!)
- **Prefill** (Prompt-Verarbeitung): eher **rechenlastig**. Wichtig bei *langem Input*
  (z. B. langes Dokument zusammenfassen). Bestimmt maßgeblich die TTFT.
- **Decode** (Token-Generierung): **bandbreitenlastig**. Wichtig bei *langer Ausgabe*.
  Hier unterscheiden sich GPU und Apple-Silicon am deutlichsten.

Die Büro-Aufgaben sind so gewählt, dass sie diese Engpässe gezielt belasten.

## Die 3 Kaufpfade
| Pfad | Stärke | Schwäche | Womit getestet |
|---|---|---|---|
| **A) 16-GB-GPU-Desktop** | höchste Bandbreite pro €, bestes CUDA-Tooling | harte Decke ~14–20B, dann Offload-Kollaps | großer Rechner im Netz / geliehene/gemietete GPU |
| **B) Mac Unified Memory** | 48–128 GB → große Modelle (30–70B) laufen; sehr energieeffizient | geringere Bandbreite pro € im Mittelfeld | 2 Macs von Bekannten |
| **C) CPU + viel RAM** | billigster Pfad; 64 GB fassen sogar 70B (Q4) | langsamster Decode | der vorhandene Laptop (i9 + 64 GB) |

## Entscheidungsregel (was der Test liefert)
- Büroaufgaben mit **8B–14B** gut genug? → **GPU-PC**: klar bestes Tempo pro Euro.
- Du brauchst spürbar **32B/70B-Qualität**? → **Mac** (oder viel-RAM-Rechner), weil die
  16-GB-GPU diese Modelle gar nicht laden kann.
- Faustregel: ein **14B @ Q4** ist oft besser als ein **24B @ Q3**, der nur „gerade so passt".

## Kennzahlen
| Kennzahl | Einheit | Bedeutung |
|---|---|---|
| Decode-Durchsatz | t/s | Ausgabe-Tempo (bandbreitenlastig) |
| Prefill-Durchsatz | t/s | Eingabe-Verarbeitung (rechenlastig) |
| Time-to-First-Token | ms | gefühlte Reaktionszeit |
| Genauigkeit | % / Check | Qualität (1× pro Modell, hardware-unabhängig) |
| Energie / 1000 Token | Wh + W | Effizienz / Betriebskosten (großer Mac-Vorteil) |
| Speicher-Decke | größtes lauffähiges Modell | Kapazität — oft die entscheidende Spalte |
| **t/s pro 1000 €** | — | finale Preis-Leistungs-Zahl |

## Faire Durchführung
- **Gemeinsame Laufzeit = Ollama** auf allen Geräten → maximal niedrige Hürde
  (Bekannte installieren nur Ollama + starten das Skript) und direkte Vergleichbarkeit.
- Optionaler **Track B** für „natives Bestcase": auf dem Mac wäre **MLX** ~20–87 %
  schneller als Ollama/llama.cpp-Metal; auf NVIDIA bringt llama.cpp-CUDA + Flash
  Attention bzw. vLLM mehr. Ollama ist die faire gemeinsame Basis; MLX/vLLM zeigen das Maximum.
- **Reproduzierbar**: identisches Modell+Quant, `temperature 0`, fester Seed, feste
  Kontextlänge, Warmup, **Median + p95** über mehrere Läufe, Dauerlast statt Peak
  (Thermal-Throttling beachten). **Chat-Template muss überall identisch sein** — eine
  falsche Vorlage zerstört still die Genauigkeit.

## Energie messen
Nicht `nvidia-smi` (nur GPU) gegen `powermetrics` (ganzer SoC) vergleichen — das ist
unfair. Fairster Weg: ein **Steckdosen-Messgerät** (~15 €) für den realen
Gesamtverbrauch beider Maschinen, daraus **Wh pro 1000 Token**.
