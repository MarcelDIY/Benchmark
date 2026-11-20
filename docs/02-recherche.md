# Recherche-Ergebnisse (Stand Mitte 2026)

Zusammenfassung einer Web-Recherche zu Methodik, Hardware, Modellen und
Genauigkeits-Evaluierung. Preise/Tempo sind Momentaufnahmen — als Erwartungswerte
zu verstehen, nicht als Garantie. Der eigentliche Test misst die echten Zahlen.

## Konsumenten-GPUs mit 16 GB (nach Bandbreite gruppiert)
Bandbreite (nicht Rechenleistung) bestimmt das Decode-Tempo.

| GPU (16 GB) | Bandbreite | Decode 7B Q4 | Karte ca. (€) |
|---|---|---|---|
| RTX 4060 Ti 16 GB | 288 GB/s (128-bit) | ~64 t/s | – |
| RTX 5060 Ti 16 GB | 448 GB/s (128-bit) | ~96 t/s | ~573 |
| RX 7900 GRE | 576 GB/s | ~96 t/s (ROCm) | – |
| RX 7800 XT | 624 GB/s | ~101 t/s (ROCm) | ~500 |
| RTX 4070 Ti SUPER | 672 GB/s | ~133 t/s | ~1.150 |
| RTX 4080 SUPER | 736 GB/s | ~147 t/s | ~1.359 |
| RTX 5070 Ti | 896 GB/s (GDDR7) | **~182 t/s** | ~889–930 |

- **16-GB-Decke ist hart**: passt das Modell + KV-Cache nicht in ~15 GB, lagert
  llama.cpp/Ollama auf CPU aus → Decode bricht 3–10× ein (oft 1–3 t/s bei 30B+).
- In 16 GB @ Q4 passen: 7–8B (langer Kontext), 14B (~32K Kontext), max. ~20B (MXFP4).
- **CUDA-Vorteil**: breiteste Tool-/Modell-Unterstützung, Flash Attention. AMD (ROCm)
  ist günstiger pro GB/s, aber mehr Reibung und spätere Modell-Unterstützung.
- Komplett-PC (GPU+CPU+64 GB RAM+Board+NT): ~950–1.250 € (5060 Ti) …
  ~1.400–1.650 € (5070 Ti) … ~1.900–2.100 € (4080 SUPER).

## Apple Silicon (Unified Memory)
*Fortgeschrieben 2026-11-06 (Rudi-Recherche, belegt). Quelle Tempo: llama.cpp Discussion #4167,
Llama 2 7B Q4_0, Metal; Bandbreiten laut Apple-Datenblättern. Vergleich: RTX 3090 = 100 %.*

| Chip | Bandbreite | Decode t/s | Decode vs. 3090 | Prefill vs. 3090 | RAM-Stufen |
|---|---|---|---|---|---|
| M1 Max | 400 GB/s | 61 | ~39 % | ~10 % | 32/64 GB |
| M2 Max | 400 GB/s | 66 | ~42 % | ~13 % | 32/64/96 GB |
| M4 Pro | 273 GB/s | 51 | ~32 % | ~8 % | 24/48 GB |
| M4 Max (40 GPU) | 546 GB/s | 83 | ~52 % | ~17 % | ab 36 GB |
| M5 Pro | 307 GB/s | 66 | ~42 % | ~31 % | 24/48/64 GB |
| M5 Max (40 GPU) | 614 GB/s | 120 | ~76 % | ~58 % | |
| M6 (Basis) | 153/170 GB/s | – | – | – | max. 32 GB; Marktstart 2026-11-06, noch kein Pro/Max |

- Decode hängt an der Bandbreite, Prefill an der Rechenleistung. Die Neural Accelerators der
  M5-Generation heben Prefill um ~3,6–4×, Decode nur um ~1,2–1,4×.
- Bild/Video (Stable Diffusion u. ä.): Mac ~2–7× hinter einer RTX 4090, z. B. SDXL 42 s (M4 Max)
  gegen 11 s (4090). **Dünn belegt** (Forum/Blog).
- Nutzbarer „VRAM" ≈ 75 % des RAM (per `sudo sysctl iogpu.wired_limit_mb` erhöhbar; ob SIP
  dabei stört, ist offen). 32 GB → ~24 GB für die GPU.
- RAM-Bedarf @ Q4: 24 GB → 14B, 36 GB → 32B, 64 GB → 70B (~42,5 GB).
- **MLX** schlägt llama.cpp-Metal bei < 14B um 20–87 %; bei 27B+ kaum noch. **Ollama**
  ist auf dem Mac ~50 % langsamer als MLX → für „Bestcase" MLX nutzen, für faire
  Cross-Plattform-Basis Ollama.
- Docker auf macOS hat **keinen GPU-Zugriff** → lokale Modelle nativ betreiben.
- Gebrauchtpreise DE (Kleinanzeigen, Stand 2026-11-06, MacBook Pro): M1 Max 32 GB 1.049–1.699 €,
  M2 Max 32 GB 1.550–2.300 €, M4 Pro 24 GB 1.649–2.599 € / 48 GB 2.450–2.999 €,
  M4 Max 36 GB 2.500–3.150 €. Refurbished: M5 Pro ab 2.649 €, M5 Max ab 4.069 €.
- Neupreise DE (Stand 2026-11-13, Jenni, Händler-Suchtreffer, nicht gegen Apple-Store geprüft):
  MacBook Pro 14" **M6 (Basis) 32 GB/1 TB** Mactrade 2.689 € (UVP 2.739 €); USA-Liste $2.399.
  **M5 Pro 48 GB/1 TB** ca. 3.180–3.450 € (15/16-Core ab ~3.181 €, 18/20-Core ab ~3.446 €, Geizhals/billiger.de).
  M6 Pro/Max noch nicht erschienen.

### Anforderung „Sprechende Crew“ (Stand 2026-11-10)
Marcel will, dass die Crew auf jedem Rechner **gleich klingt**: Qwen3-TTS-Stimmklon wie am Arbeits-PC,
keine Piper-Ersatzstimmen. Damit ist das ein Kaufkriterium für den Laptop.
- **Gemessen:** Arbeits-PC (RTX 1000 Ada, 6 GB): Modell `Qwen3-TTS-12Hz-0.6B-Base`, erster Ton nach
  ~1,1 s, braucht ~2,6 GB Grafikspeicher, mit Whisper large-v3-turbo zusammen 5,2 GB. Kubuntu
  (GTX 1050 Ti, 4 GB): 2,7-mal langsamer als Echtzeit, Speicher am Limit, also **unbrauchbar**.
  Messung 2026-11-10.
- **Mac, ungeprüft:** Der Arbeits-PC nutzt `faster-qwen3-tts`, und das baut auf CUDA-Graphen. Auf
  dem Mac läuft es deshalb **nicht**. Bleiben das Original `qwen-tts` über PyTorch-MPS oder ein
  MLX-Port, und für beide fehlt ein Beleg zu Tempo und Klangtreue. Vor dem Kauf eine Probe auf einem
  Mac machen: Stimmdateien `_Uebergabe/Sprechende_Crew/stimmen/qwen/*.wav` und Messskript
  `tts/qwen_probe.py`. Der Pfad zur Stimmdatei und `device="cuda"` müssen für den Mac angepasst werden. Maßstab ist echtzeitfähig mit erstem Ton nach höchstens ~2 s.
- Diktat (Whisper) läuft auf dem Mac nativ (whisper.cpp/MLX). Das ist allgemein bekannt, hier aber
  nicht selbst gemessen.

### Laptop-Auswahl für später (Stand 2026-11-20, Gespräch Marcel/Jenni)
**Festgelegt:** Es muss ein **Laptop** sein, so klein und leicht wie möglich (mobil, Arbeit bei
Kunden). Lokale Sprachmodelle sind die Arbeiter, Claude online der Orchestrator. Video bleibt auf
HS- oder Cloud-Hardware. Kaufzeitpunkt offen („wenn ich mal Geld verdiene“) → dann Modelle und
Preise frisch prüfen.

**Faustregel:** Tempo ≈ Bandbreite ÷ Modellgröße (praktisch 60–80 % davon). Die Speichergröße
macht nicht schneller, sie entscheidet nur, welches Modell hineinpasst.

**Bauarten im Vergleich** *(Werte aus dem Gedächtnis, nicht geprüft, außer wo die Apple-Tabelle oben belegt)*

| Gerät / Bauart | Speicher | davon fürs Modell (ca.) | Bandbreite (ca.) | Obergrenze 8B (5 GB) | größtes sinnvolles Modell |
|---|---|---|---|---|---|
| Kubuntu: GTX 1050 Ti | 4 GB VRAM | ~3,5 GB | 112 GB/s | passt nicht ganz | 3B |
| Normaler Laptop (z. B. HP OmniBook Ultra, Windows) | 32 GB gemeinsam | ~16 GB (Windows gibt der iGPU die Hälfte) | ~120–150 GB/s | ~25–30 t/s | 14B |
| MacBook Air M4 | 16–32 GB gemeinsam | bei 32 GB ~21–24 GB | 120 GB/s | ~24 t/s | 14B |
| MacBook Pro M4/M5 Pro | 24–64 GB gemeinsam | ~75 % des RAM | 273 / 307 GB/s | ~55–60 t/s | 30B |
| MacBook Pro M4/M5 Max | 36–128 GB gemeinsam | bis ~96 GB | 546 / 614 GB/s | ~110–120 t/s | 70B |
| AMD Strix Halo (Ryzen AI Max+ 395, z. B. HP ZBook Ultra G1a) | bis 128 GB gemeinsam | bis ~96 GB | ~256 GB/s | ~50 t/s | 70B (langsam) |
| Laptop mit RTX 4090 / 5090 | 16 / 24 GB VRAM | ~15 / ~22 GB | ~575 / ~900 GB/s | ~115 / ~180 t/s | 14B / 30B |
| *Desktop RTX 4090 / 5090* | 24 / 32 GB VRAM | ~22 / ~30 GB | ~1.000 / ~1.800 GB/s | ~200 / ~350 t/s | 30B |

**Auswahl unter „Laptop, leicht, Sprachmodelle“** *(Gewichte aus dem Gedächtnis, nicht geprüft)*

| Option | Gewicht (ca.) | Urteil |
|---|---|---|
| MacBook Air | ~1,2 kg | leicht, aber ohne Lüfter: bremst bei langen Läufen, max. 32 GB, 120 GB/s → scheidet aus |
| **MacBook Pro 14" Max-Chip** | ~1,6 kg | **stärkste Kombination aus klein und schnell** |
| MacBook Pro 14" Pro-Chip | ~1,6 kg | Kompromiss: halbe Bandbreite, deutlich günstiger (M5 Pro 48 GB ~3.200–3.450 €, s. o.) |
| AMD Strix Halo 14" (z. B. ZBook Ultra G1a) | ~1,5 kg | Windows-Alternative: gleich viel Speicher, halbe Bandbreite eines Max |
| Gaming-Laptop mit RTX | 2,2–3 kg | schnell, aber schwer, laut, wenig Speicher → scheidet aus |

**Video & Bild** sind etwas anderes: Sie hängen an der **Rechenleistung**, nicht an der
Bandbreite, und die Werkzeuge sind auf NVIDIA/CUDA gebaut. Auf dem Mac laufen sie (ComfyUI über
PyTorch-MPS, teils MLX-Ports), aber deutlich langsamer (Bild ~2–7× hinter einer 4090, s. o.) und
nicht jedes Werkzeug startet überhaupt (CUDA-only-Beschleuniger, gleiches Problem wie
`faster-qwen3-tts`). Für Video-Modelle bleibt deshalb NVIDIA-Hardware (HS-KI-Server) oder Cloud-GPU.

**Vorteil lokal beim Kunden:** Rohdaten bleiben auf dem Gerät, Claude bekommt nur Aufträge und
Ergebnisse. Im Einzelfall vertraglich regeln.

## Modelle & Quantisierung
**Q4_K_M** ist der Sweet-Spot: ~75 % kleiner als FP16, minimaler Qualitätsverlust.
GGUF-Größen (≈, je nach Uploader):

| Modell | Q4_K_M | Passt in 16 GB GPU? | Rolle |
|---|---|---|---|
| Llama 3.2 3B | ~2,0 GB | ✅ locker | Spitzen-Tempo / untere Kurve |
| Qwen2.5 7B / Llama 3.1 8B | ~4,7–4,9 GB | ✅ + viel Kontext | Büro-Mainstream |
| Qwen2.5 14B / Phi-4 14B | ~9,0 GB | ✅ (16-GB-Decke) | Qualitäts-Obergrenze GPU |
| Gemma 2/3 27B | ~16,6 GB | ❌ kein Kontext-Platz | nur Mac/viel-RAM |
| Qwen2.5/Qwen3 32B | ~20 GB | ❌ Offload-Kollaps | nur Mac/viel-RAM |
| Qwen3-30B-A3B (MoE) | ~18,6 GB | ❌ auf GPU | Mac: groß UND schnell (3B aktiv) |
| Llama 3.3 70B | ~42,5 GB | ❌ unmöglich | nur Mac 48/64 GB / 64 GB RAM |

Hinweis: Dateigröße ≠ Laufzeit-Bedarf — KV-Cache (wächst mit Kontextlänge) kommt dazu.
Immer die verwendete Kontextlänge mit angeben.

## Genauigkeit messen (optional, hardware-unabhängig)
- Standard: **EleutherAI lm-evaluation-harness** gegen einen OpenAI-kompatiblen
  lokalen Endpoint (`--model local-completions --model_args base_url=...`). Identischer
  Befehl auf jedem Gerät.
- Sinnvolle Tasks: MMLU(-Pro) (Wissen), GSM8K (Rechnen), HumanEval/MBPP (Code, in
  Sandbox), IFEval (Instruktions-Treue).
- **Wichtig**: Genauigkeit nur **einmal pro (Modell, Quant)** messen — gleiches
  Modell+Quant ⇒ gleiche Qualität über CUDA/Metal/MLX (Unterschiede im Rauschen).
- Quant-Sensitivität: Q4_K_M verliert ~0,3–0,4 % ggü. FP16; aggressiv (Q3) bis ~6 %
  (GSM8K am empfindlichsten). Quant-**Format** (GGUF vs MLX vs FP16) ändert Qualität
  mehr als die nominale Bit-Zahl.

## Wichtigste Quellen
- llama.cpp Benchmarks/Diskussionen: github.com/ggml-org/llama.cpp (discussions 15013/15021/4167)
- Apple Silicon: craftrigs.com/comparisons/apple-silicon-llm-benchmarks, yage.ai (MLX)
- 16-GB-GPU: glukhov.org/llm-performance, hardware-corner.net, tomshardware.com
- Modellgrößen: huggingface.co/bartowski/* (GGUF-Repos)
- Genauigkeit: github.com/EleutherAI/lm-evaluation-harness; thinkingmachines.ai
  (Nichtdeterminismus); sitepoint.com (Q4_K_M vs FP16)
