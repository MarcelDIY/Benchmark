#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Erzeugt die README-Screenshots reproduzierbar aus der echten GUI.

Statt die Oberflaeche von Hand zu bedienen, instanziiert das Skript das echte
MainWindow, fuettert es mit kuratierten DEMO-Daten (keine Live-Messung, kein
Ollama noetig) und rendert die Tabs per Qt-`grab()` offscreen als PNG. So bleiben
die Bilder bei jeder GUI-Aenderung mit einem Aufruf aktuell:

    ./.venv/bin/python tools/make_screenshots.py

Erzeugt:
    assets/screenshots/overview.png   – ganzes Fenster (Aktueller Lauf)
    assets/screenshots/dashboard.png  – nur der Reiter "Aktueller Lauf"
    assets/screenshots/vergleich.png  – Reiter "Vergleich" + Cloud-Referenz
"""
import os
import sys

# Offscreen rendern – kein sichtbares Fenster, kein Display noetig.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)  # benchmark_gui / svgcharts / bench liegen im Projektroot

from PySide6.QtWidgets import QApplication, QSplitter  # noqa: E402

import benchmark_gui as G  # noqa: E402

OUT = os.path.join(ROOT, "assets", "screenshots")


# ----------------------------------------------------------------- Demo-Daten ---
# Dashboard: ein einzelner Lauf (llama3.2:3b auf einem Kubuntu-Rechner).
DASH_ROWS = [
    # task-id,                ttft, prefill, decode, qualitaet
    ("zusammenfassen_prefill", 412, 920.0, 48.2, ""),
    ("email_decode",           120, 880.0, 50.3, ""),
    ("uebersetzen",            115, 430.0, 49.0, ""),
    ("extrahieren_json",        98, 410.0, 49.7, "100%"),
    ("doc_qa",                 105, 430.0, 48.9, "100%"),
]
DASH_GESAMT = ("GESAMT", 150, 650.0, 49.3, "100%", 45.8)  # +decode_p95
DASH_PLACEMENT = {"gpu_pct": 85, "vram_mb": 3031, "total_mb": 3566}

# Balken fuer die (zuerst markierte) Aufgabe "Zusammenfassen", Kennzahl Decode.
DASH_DETAIL = {
    "reps_decode":  [47.9, 48.5, 48.0, 49.1, 47.6],   # Ø 48.2
    "reps_prefill": [910.0, 925.0, 918.0, 922.0, 915.0],
    "reps_ttft":    [400, 415, 410, 418, 405],
    "warmup": {"decode_toks": 12.0, "prefill_toks": 300.0, "ttft_ms": 1800},
}

# Vergleich: drei lokale Laeufe (verschiedene Rechner/Modelle) – so verteilen sich
# die Bestwerte sinnvoll: GPU-PC fuehrt beim Prefill, der Mac beim Decode/TTFT,
# das grosse 14B-Modell auf CPU ist langsam, aber qualitativ top.
def _rec(name, model, mode, label, decode, prefill, ttft, p95, gpu, qual,
         kalt, groesse_mb, dauer):
    return {
        "name": name, "model": model, "mode": mode, "label": label,
        "decode": decode, "prefill": prefill, "ttft": ttft, "decode_p95": p95,
        "gpu_pct": gpu, "quality": qual, "qual_pct": G._pct(qual),
        "kaltstart": kalt, "groesse": groesse_mb, "dauer": dauer,
        "is_reference": False, "imported": False,
    }


CMP_RUNS = [
    _rec("llama3.2:3b @ gpu-pc",     "llama3.2:3b",  "gpu", "gpu-pc",
         58.0, 1020, 150, 54.0, 100, "80%",  1.9, 2000, 58),
    _rec("llama3.2:3b @ mac-m4",     "llama3.2:3b",  "gpu", "mac-m4",
         64.5,  610, 120, 61.0, 100, "80%",  2.4, 2000, 54),
    _rec("qwen2.5:14b @ cpu-server", "qwen2.5:14b",  "cpu", "cpu-server",
          7.2,  110, 1250, 6.5,   0, "100%", 13.0, 9000, 230),
]


# ----------------------------------------------------------------- Befuellung ---
def build_window(app):
    # Auto-Scan abschalten: keine Ollama-Abfrage, voll reproduzierbar.
    G.MainWindow.on_scan = lambda self: None
    win = G.MainWindow()
    win.resize(1100, 1015)

    # Verbindung / Parameter so setzen, wie sie nach einem echten Lauf aussehen.
    win.host_edit.setText("http://localhost:11434")
    win.status_label.setText("✓ erreichbar – 5 Modell(e)")
    win.model_combo.addItems(
        ["llama3.2:3b", "qwen2.5:7b", "qwen2.5:14b", "mistral:7b", "gemma2:9b"])
    win.model_combo.setCurrentText("llama3.2:3b")
    win.mode_combo.setCurrentText("gpu")
    win.reps_spin.setValue(5)
    win.warmup_spin.setValue(1)
    win.label_edit.setText("marcel-Kubuntu")
    win.prog_bar.setMaximum(100)
    win.prog_bar.setValue(100)
    win.prog_label.setText("Fertig.")

    # --- Dashboard (Reiter "Aktueller Lauf") befuellen ---
    rows = []
    for tid, ttft, prefill, decode, qual in DASH_ROWS:
        rows.append({"task": tid, "ttft_ms_med": ttft, "prefill_toks_med": prefill,
                     "decode_toks_med": decode, "quality": qual})
    tid, ttft, prefill, decode, qual, p95 = DASH_GESAMT
    rows.append({"task": tid, "ttft_ms_med": ttft, "prefill_toks_med": prefill,
                 "decode_toks_med": decode, "quality": qual, "decode_toks_p95": p95})

    payload = {"rows": rows, "placement": DASH_PLACEMENT,
               "config": {"model": "llama3.2:3b", "mode": "gpu"},
               "label": "marcel-Kubuntu"}

    for i, r in enumerate(rows):
        detail = DASH_DETAIL if i == 0 else None   # Balken nur fuer "Zusammenfassen"
        win.on_task_row({"summary": r, "detail": detail})
    win._last_payload = payload
    win._fill_kpis(payload)
    win._show_placement(payload)
    win.table.selectRow(0)  # markiert "Zusammenfassen" -> Balkendiagramm erscheint

    # --- Vergleich (Reiter "Vergleich") befuellen: lokale Laeufe + Cloud-Referenz ---
    win._runs = list(CMP_RUNS)
    win._runs.extend(win._load_reference())
    win.ref_btn.setText("☁ Cloud-Referenz ausblenden")
    win.tabs.setTabText(1, f"Vergleich ({len(win._runs)})")
    win._refresh_compare()
    # Splitter zugunsten der Tabelle verschieben, damit alle Laeufe (inkl. der
    # letzten Cloud-Referenz) ohne Scrollbalken im Screenshot stehen.
    cmp_split = win.tabs.widget(1).findChild(QSplitter)
    if cmp_split:
        cmp_split.setSizes([170, 430])

    win.show()
    for _ in range(6):
        app.processEvents()
    return win


def grab(widget, name):
    path = os.path.join(OUT, name)
    widget.grab().save(path)
    print(f"  geschrieben: {os.path.relpath(path, ROOT)}")


def main():
    os.makedirs(OUT, exist_ok=True)
    app = QApplication(sys.argv)
    G.apply_theme(app)
    win = build_window(app)

    win.tabs.setCurrentIndex(0)
    for _ in range(4):
        app.processEvents()
    grab(win, "overview.png")
    grab(win.tabs, "dashboard.png")

    win.tabs.setCurrentIndex(1)
    for _ in range(4):
        app.processEvents()
    grab(win.tabs, "vergleich.png")

    print("Fertig.")


if __name__ == "__main__":
    main()
