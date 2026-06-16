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
| Chip-Klasse | Bandbreite | Decode 7–8B Q4 | Decode 70B Q4 |
|---|---|---|---|
| M-Base | 68–120 GB/s | 25–33 t/s | – |
| M-Pro | 150–273 GB/s | 38–48 t/s | – |
| M-Max | 300–546 GB/s | 52–59 t/s | 11–12,5 t/s |
| M-Ultra | 800–819 GB/s | – | 14–18 t/s |

- Nutzbarer „VRAM" ≈ 75 % des RAM (per `sysctl iogpu.wired_limit_mb` erhöhbar).
- RAM-Bedarf @ Q4: 24 GB → 14B, 36 GB → 32B, 64 GB → 70B (~42,5 GB).
- **MLX** schlägt llama.cpp-Metal bei < 14B um 20–87 %; bei 27B+ kaum noch. **Ollama**
  ist auf dem Mac ~50 % langsamer als MLX → für „Bestcase" MLX nutzen, für faire
  Cross-Plattform-Basis Ollama.
- Preise DE: Mac mini M4 Pro 48 GB ~1.799–1.999 €; Mac Studio M4 Max 36 GB ~1.999–2.199 €.

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
