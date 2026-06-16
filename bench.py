#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Lokaler Buero-LLM-Hardware-Benchmark.

Misst Geschwindigkeit (Prefill, Decode, Time-to-First-Token) und eine
einfache Qualitaetspruefung lokaler Modelle ueber Ollama. Laeuft identisch
auf Windows (GPU/CPU) und macOS (Metal). Benoetigt nur Python 3.9+ und Ollama
-- KEINE pip-Installationen.

Beispiele:
    python bench.py --check                  # nur pruefen, nichts ausfuehren
    python bench.py --label laptop-i9        # vollen Lauf starten
    python bench.py --modes gpu              # auf dem Mac: nur Metal-Lauf
    python bench.py --models qwen2.5:7b      # nur ein Modell
    python bench.py --pull                   # fehlende Modelle automatisch laden
"""
import argparse
import json
import os
import platform
import statistics
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

OLLAMA = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
if not OLLAMA.startswith("http"):
    OLLAMA = "http://" + OLLAMA
HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(HERE, "results")


# ---------------------------------------------------------------- HTTP -------
def _req(path, payload=None, method="GET", stream=False, timeout=1800):
    url = OLLAMA + path
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"Content-Type": "application/json"},
    )
    return urllib.request.urlopen(req, timeout=timeout)


def http_json(path, payload=None, method="GET", timeout=1800):
    with _req(path, payload, method, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def ollama_up():
    try:
        with _req("/api/tags", timeout=5):
            return True
    except Exception:
        return False


def installed_models(timeout=1800):
    try:
        return sorted(m["name"] for m in
                      http_json("/api/tags", timeout=timeout).get("models", []))
    except Exception:
        return []


def pull_model(name):
    print(f"  lade {name} ... (kann dauern)", flush=True)
    last = ""
    with _req("/api/pull", {"model": name, "stream": True}, method="POST") as r:
        for line in r:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line.decode("utf-8"))
            status = obj.get("status", "")
            if status != last:
                print(f"    {status}", flush=True)
                last = status
            if obj.get("error"):
                raise RuntimeError(obj["error"])


# ----------------------------------------------------------- Messung ---------
def run_once(model, prompt, num_predict, num_ctx, num_gpu, rep, should_cancel=None,
             on_response=None):
    """Ein einzelner Lauf. Liefert TTFT, Prefill-/Decode-Durchsatz, Text.

    should_cancel: optionales Callable () -> bool. Liefert es True, wird der
    Stream sofort verlassen (kooperativer Abbruch aus der GUI). Default None
    laesst das CLI-Verhalten unveraendert.
    on_response: optionales Callable(resp). Erhaelt das offene HTTP-Response-
    Objekt, sobald der Stream steht -- erlaubt der GUI, den blockierenden Read
    bei Abbruch aktiv zu schliessen (auch waehrend Modell-Load/Prefill).
    """
    # Cache-Buster: ein eindeutiger Praefix erzwingt echte Prompt-Auswertung
    # pro Lauf (sonst meldet Ollama prompt_eval_duration=0 bei Wiederholungen).
    busted = f"<!--lauf:{rep}-->\n{prompt}"
    payload = {
        "model": model,
        "prompt": busted,
        "stream": True,
        "options": {
            "temperature": 0,
            "seed": 42,
            "num_predict": num_predict,
            "num_ctx": num_ctx,
        },
    }
    if num_gpu is not None:
        payload["options"]["num_gpu"] = num_gpu

    t0 = time.perf_counter()
    ttft = None
    final = None
    chunks = []
    with _req("/api/generate", payload, method="POST") as r:
        if on_response is not None:
            on_response(r)
        for line in r:
            # Kooperativer Abbruch (GUI): Stream verlassen, Verbindung schliesst via with.
            if should_cancel is not None and should_cancel():
                break
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line.decode("utf-8"))
            piece = obj.get("response", "")
            if piece:
                if ttft is None:
                    ttft = time.perf_counter() - t0
                chunks.append(piece)
            if obj.get("done"):
                final = obj
    wall = time.perf_counter() - t0
    final = final or {}
    pe_c = final.get("prompt_eval_count", 0) or 0
    pe_d = final.get("prompt_eval_duration", 0) or 0      # Nanosekunden
    e_c = final.get("eval_count", 0) or 0
    e_d = final.get("eval_duration", 0) or 0
    prefill = pe_c / (pe_d / 1e9) if pe_d else None
    decode = e_c / (e_d / 1e9) if e_d else None
    return {
        "ttft_ms": (ttft * 1000) if ttft is not None else None,
        "wall_s": wall,
        "prefill_toks": prefill,
        "decode_toks": decode,
        "prompt_tokens": pe_c,
        "gen_tokens": e_c,
        "text": "".join(chunks),
    }


def _norm(s):
    """Kleinschreibung + Umlaut-Normalisierung, damit 'Maerz' == 'Maerz' == 'Marz'."""
    s = s.lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        s = s.replace(a, b)
    return s


def quality_check(task, text):
    """Einfacher, deterministischer Qualitaets-Smoketest. None = nicht anwendbar."""
    if "check_keys" in task:
        try:
            start, end = text.find("{"), text.rfind("}")
            obj = json.loads(text[start:end + 1])
            return all(k in obj for k in task["check_keys"])
        except Exception:
            return False
    if "expect_contains" in task:
        return _norm(task["expect_contains"]) in _norm(text)
    return None


# ----------------------------------------------------------- Aggregat --------
def agg(values):
    vals = [v for v in values if v is not None]
    if not vals:
        return (None, None)
    med = statistics.median(vals)
    p95 = sorted(vals)[min(len(vals) - 1, int(round(0.95 * (len(vals) - 1))))]
    return (med, p95)


def system_info():
    cpu = platform.processor() or platform.machine()
    ram = None
    sysname = platform.system()
    if sysname == "Windows":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as k:
                cpu = winreg.QueryValueEx(k, "ProcessorNameString")[0].strip()
        except Exception:
            pass
        try:
            import ctypes

            class _MS(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            ms = _MS()
            ms.dwLength = ctypes.sizeof(_MS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms))
            ram = ms.ullTotalPhys / (1024 ** 3)
        except Exception:
            ram = None
    elif sysname == "Darwin":
        import subprocess
        try:
            cpu = subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string"]).decode().strip() or cpu
        except Exception:
            pass
        try:
            ram = int(subprocess.check_output(["sysctl", "-n", "hw.memsize"]).strip()) / (1024 ** 3)
        except Exception:
            ram = None
    else:  # Linux u. a.
        try:
            if hasattr(os, "sysconf") and "SC_PHYS_PAGES" in os.sysconf_names:
                ram = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / (1024 ** 3)
        except Exception:
            ram = None
    return {
        "os": f"{platform.system()} {platform.release()}",
        "cpu": cpu,
        "machine": platform.machine(),
        "ram_gb": round(ram, 1) if ram else "",
    }


# --------------------------------------------------------------- Main --------
def main():
    ap = argparse.ArgumentParser(description="Lokaler Buero-LLM-Benchmark (Ollama)")
    ap.add_argument("--config", default=os.path.join(HERE, "tasks.json"))
    ap.add_argument("--label", default=platform.node() or "rechner",
                    help="Name dieser Maschine (z. B. laptop-i9, mac-m4-pro)")
    ap.add_argument("--modes", default="gpu,cpu",
                    help="Komma-Liste: gpu (Auto/Metal) und/oder cpu (num_gpu=0). Mac: nur 'gpu'.")
    ap.add_argument("--models", default=None, help="Komma-Liste ueberschreibt Config-Modelle")
    ap.add_argument("--reps", type=int, default=None)
    ap.add_argument("--pull", action="store_true", help="fehlende Modelle automatisch laden")
    ap.add_argument("--check", action="store_true", help="nur pruefen, nichts ausfuehren")
    args = ap.parse_args()

    with open(args.config, encoding="utf-8") as f:
        cfg = json.load(f)

    models = (args.models.split(",") if args.models else cfg["models"])
    models = [m.strip() for m in models if m.strip()]
    modes = [m.strip() for m in args.modes.split(",") if m.strip()]
    reps = args.reps or cfg.get("reps", 5)
    warmup = cfg.get("warmup", 1)
    tasks = cfg["tasks"]
    info = system_info()

    print("=" * 64)
    print(f" Maschine : {args.label}")
    print(f" System   : {info['os']} | {info['cpu']} | {info['ram_gb']} GB RAM")
    print(f" Ollama   : {OLLAMA}  ({'erreichbar' if ollama_up() else 'NICHT erreichbar!'})")
    print(f" Modelle  : {', '.join(models)}")
    print(f" Modi     : {', '.join(modes)}   Tasks: {len(tasks)}   Reps: {reps}")
    print(f" Laeufe   : {len(models) * len(modes) * len(tasks) * (reps + warmup)} (inkl. Warmup)")
    print("=" * 64)

    if not ollama_up():
        print("Ollama laeuft nicht. Starte es (App oder 'ollama serve') und versuche erneut.")
        sys.exit(1)

    have = installed_models()
    missing = [m for m in models if m not in have and m.split(":")[0] not in
               [h.split(":")[0] for h in have]]
    if missing:
        print(f" Fehlende Modelle: {', '.join(missing)}")
        if args.pull and not args.check:
            for m in missing:
                pull_model(m)
        elif not args.check:
            print("   -> mit --pull automatisch laden, oder vorher 'ollama pull <name>'.")

    if args.check:
        print("\n--check: nichts ausgefuehrt. Setup sieht "
              + ("vollstaendig aus." if not missing else "ok aus, Modelle fehlen noch.")
              + " Ohne --check startet der echte Lauf.")
        return

    os.makedirs(RESULTS_DIR, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    raw_path = os.path.join(RESULTS_DIR, f"raw_{args.label}_{stamp}.csv")
    sum_path = os.path.join(RESULTS_DIR, f"summary_{args.label}_{stamp}.csv")
    md_path = os.path.join(RESULTS_DIR, f"summary_{args.label}_{stamp}.md")

    raw_rows, sum_rows = [], []
    raw_cols = ["label", "os", "cpu", "ram_gb", "model", "mode", "task", "rep",
                "ttft_ms", "prefill_toks", "decode_toks", "prompt_tokens",
                "gen_tokens", "wall_s", "quality", "antwort"]
    raw_rows.append(raw_cols)

    for model in models:
        for mode in modes:
            num_gpu = 0 if mode == "cpu" else None
            for task in tasks:
                tid = task["id"]
                print(f"\n[{model} | {mode} | {tid}]", flush=True)
                # Warmup (laedt Modell, nicht gewertet)
                for w in range(warmup):
                    try:
                        run_once(model, task["prompt"], 16,
                                 task.get("num_ctx", 4096), num_gpu, rep=-1 - w)
                    except Exception as e:
                        print(f"  Warmup-Fehler: {e}")
                samples = []
                for rep in range(reps):
                    try:
                        r = run_once(model, task["prompt"], task.get("num_predict", 256),
                                     task.get("num_ctx", 4096), num_gpu, rep=rep)
                    except urllib.error.URLError as e:
                        print(f"  Fehler (uebersprungen): {e}")
                        continue
                    q = quality_check(task, r["text"])
                    samples.append(r)
                    answer = " ".join(r["text"].split())[:200]
                    raw_rows.append([args.label, info["os"], info["cpu"], info["ram_gb"],
                                     model, mode, tid, rep,
                                     _f(r["ttft_ms"]), _f(r["prefill_toks"]),
                                     _f(r["decode_toks"]), r["prompt_tokens"],
                                     r["gen_tokens"], _f(r["wall_s"]),
                                     "" if q is None else ("ok" if q else "FAIL"),
                                     answer])
                    print(f"  rep{rep}: TTFT {_f(r['ttft_ms'],0)} ms | "
                          f"prefill {_f(r['prefill_toks'],1)} t/s | "
                          f"decode {_f(r['decode_toks'],1)} t/s"
                          + ("" if q is None else f" | qual {'ok' if q else 'FAIL'}"),
                          flush=True)
                if not samples:
                    continue
                ttft_m, ttft_p = agg([s["ttft_ms"] for s in samples])
                pre_m, _ = agg([s["prefill_toks"] for s in samples])
                dec_m, dec_p = agg([s["decode_toks"] for s in samples])
                quals = [quality_check(task, s["text"]) for s in samples]
                quals = [x for x in quals if x is not None]
                qrate = "" if not quals else f"{round(100*sum(quals)/len(quals))}%"
                sum_rows.append({
                    "label": args.label, "model": model, "mode": mode, "task": tid,
                    "ttft_ms_med": _f(ttft_m, 0), "ttft_ms_p95": _f(ttft_p, 0),
                    "prefill_toks_med": _f(pre_m, 1),
                    "decode_toks_med": _f(dec_m, 1), "decode_toks_p95": _f(dec_p, 1),
                    "prompt_tokens": samples[0]["prompt_tokens"],
                    "gen_tokens": samples[0]["gen_tokens"], "quality": qrate,
                })

    _write_csv(raw_path, raw_rows)
    _write_dict_csv(sum_path, sum_rows)
    _write_md(md_path, args.label, info, sum_rows)
    print("\n" + "=" * 64)
    print("Fertig. Ergebnisse:")
    print(f"  Roh      : {raw_path}")
    print(f"  Zusammen : {sum_path}")
    print(f"  Tabelle  : {md_path}")
    print("Schicke die Datei summary_*.md/.csv zurueck -- daraus baue ich den Vergleich.")


def _f(x, nd=2):
    return "" if x is None else round(x, nd)


def _write_csv(path, rows):
    import csv
    with open(path, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)


def _write_dict_csv(path, rows):
    import csv
    if not rows:
        open(path, "w").close()
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def _write_md(path, label, info, rows):
    lines = [f"# Benchmark: {label}", "",
             f"- System: {info['os']} | {info['cpu']} | {info['ram_gb']} GB RAM",
             f"- Erstellt: {datetime.now(timezone.utc).isoformat(timespec='seconds')}", "",
             "| Modell | Modus | Task | TTFT med (ms) | Prefill med (t/s) "
             "| Decode med (t/s) | Decode p95 | Qualitaet |",
             "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['model']} | {r['mode']} | {r['task']} | {r['ttft_ms_med']} "
                     f"| {r['prefill_toks_med']} | {r['decode_toks_med']} "
                     f"| {r['decode_toks_p95']} | {r['quality']} |")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
