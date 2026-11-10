# Qwen-Probe: schafft die GTX 1050 Ti Maries Stimme (Qwen3-TTS 0.6B, Stimmklon)?
# Aufruf: qwen_probe.py <bf16|fp16>
import os
import subprocess
import sys

# Fragmentierung vermeiden – auf 4 GB zählt jedes MB
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
os.environ["HF_HUB_OFFLINE"] = "1"
import time
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
from faster_qwen3_tts import FasterQwen3TTS

DTYPE = {"bf16": torch.bfloat16, "fp16": torch.float16}[sys.argv[1]]
AUS = Path(__file__).parent
STIMME = Path.home() / "Öffentlich/SynologyDrive/_Uebergabe/Sprechende_Crew/stimmen/qwen/marie.wav"
REF_TEXT = ("Guten Morgen. Ich habe mir das schon angesehen und kann dir gleich sagen, "
            "wie es aussieht und was als Nächstes zu tun ist.")
TEXTE = ["Kurzer Test.",
         "Deine Forschungsfrage trägt. Lass uns jetzt die Methodik schärfen, bevor du weiterschreibst."]

t0 = time.perf_counter()
modell = FasterQwen3TTS.from_pretrained("Qwen/Qwen3-TTS-12Hz-0.6B-Base", dtype=DTYPE)
print(f"Modell geladen: {time.perf_counter()-t0:.1f} s, VRAM {torch.cuda.max_memory_allocated()/2**30:.2f} GB", flush=True)

for i, text in enumerate(TEXTE):
    t = time.perf_counter()
    erster = None
    stuecke, sr = [], 24000
    for stueck, sr, _ in modell.generate_voice_clone_streaming(
            text=text, language="German", ref_audio=str(STIMME), ref_text=REF_TEXT, chunk_size=8):
        if erster is None:
            erster = time.perf_counter() - t
        stuecke.append(np.asarray(stueck, dtype=np.float32).reshape(-1))
    gesamt = time.perf_counter() - t
    audio = np.concatenate(stuecke)
    dauer = len(audio) / sr
    print(f"[{i}] erster Ton nach {erster:.1f} s, fertig nach {gesamt:.1f} s für {dauer:.1f} s Audio "
          f"(Faktor {gesamt/dauer:.2f}), VRAM max {torch.cuda.max_memory_allocated()/2**30:.2f} GB", flush=True)
    ziel = AUS / f"marie_{sys.argv[1]}_{i}.wav"
    sf.write(str(ziel), audio, sr)

subprocess.run(["pw-play", str(AUS / f"marie_{sys.argv[1]}_1.wav")], check=False)
