#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Standalone-GUI für den lokalen Büro-LLM-Hardware-Benchmark (Dark-Theme).

Ein PySide6-Frontend für bench.py: Ollama-Host eingeben, mit "Modelle suchen" die
lokal installierten Modelle ins Dropdown laden, eines auswählen, den Test durchlaufen
lassen und Ergebnisse als KPI-Kacheln, Tabelle + Diagramme ansehen und exportieren.

Voraussetzung zur Laufzeit: ein laufendes Ollama (Standard http://localhost:11434).
Ollama wird NICHT mitgebündelt – es ist eine externe Voraussetzung.

Die Messung kommt unverändert aus bench.py. Läuft auf Windows, macOS und Linux;
mit PyInstaller als Standalone baubar (siehe BenchGUI.spec).
"""
import html
import json
import os
import platform
import statistics
import sys
import threading
from datetime import datetime, timezone

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, QObject, QThread, Signal, Slot
from PySide6.QtGui import (QAction, QColor, QFont, QIcon, QPainter, QPen)
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFrame,
    QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QScrollArea, QSizePolicy,
    QSpinBox, QSplitter, QTabWidget, QTableWidget, QTableWidgetItem, QTextBrowser,
    QVBoxLayout, QWidget,
)

import bench

VERSION = "1.0"

# --- Farb-Palette (Dark) ---
BG = "#161a22"
CARD = "#20262f"
INPUT = "#2a313c"
BORDER = "#333b47"
TXT = "#e8ebf0"
TXT2 = "#9aa6b8"
TEAL = "#2dd4bf"
AMBER = "#f5b14d"
GREEN = "#45d488"

TASK_NAMES = {
    "zusammenfassen_prefill": "Zusammenfassen",
    "email_decode": "E-Mail schreiben",
    "uebersetzen": "Übersetzen",
    "extrahieren_json": "JSON-Extraktion",
    "doc_qa": "Dokument-Frage",
}


def friendly(task_id):
    return TASK_NAMES.get(task_id, task_id)


def resource_path(rel):
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, rel)


def default_output_dir():
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
        if sys.platform == "darwin" and base.endswith("/Contents/MacOS"):
            base = os.path.dirname(os.path.dirname(os.path.dirname(base)))
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    p = os.path.join(base, "results")
    try:
        os.makedirs(p, exist_ok=True)
    except Exception:
        p = os.path.expanduser("~")
    return p


def normalize_host(host):
    host = (host or "").strip()
    if not host:
        host = "http://localhost:11434"
    if not host.startswith("http"):
        host = "http://" + host
    return host


def safe_label(label):
    out = label or "rechner"
    for ch in ' \t/\\:':
        out = out.replace(ch, "_")
    return out or "rechner"


TABLE_COLS = [
    ("task", "Aufgabe"),
    ("ttft_ms_med", "TTFT (ms)"),
    ("prefill_toks_med", "Prefill (t/s)"),
    ("decode_toks_med", "Decode (t/s)"),
    ("quality", "Qualität"),
]


# ============================================================ Diagramm-Widgets ==
class DonutChart(QWidget):
    """Ringdiagramm: das Modell (100%) verteilt auf GPU (teal) und CPU (amber)."""

    def __init__(self):
        super().__init__()
        self._gpu = None
        self.setMinimumHeight(150)
        self.setMaximumHeight(180)

    def set_value(self, gpu_pct):
        self._gpu = gpu_pct
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        d = min(w, h, 168) - 8
        x, y = (w - d) / 2, (h - d) / 2
        rect = QRectF(x, y, d, d)
        thick = max(13, d * 0.16)

        if self._gpu is None:
            p.setPen(QPen(QColor(BORDER), thick, Qt.SolidLine, Qt.FlatCap))
            p.drawArc(rect, 0, 360 * 16)
            p.setPen(QColor(TXT2))
            p.setFont(QFont("", 9))
            p.drawText(rect, Qt.AlignCenter, "noch\nkein Lauf")
            return

        gpu = max(0, min(100, self._gpu))
        cpu = 100 - gpu
        gspan = 360 * gpu / 100
        p.setPen(QPen(QColor(TEAL), thick, Qt.SolidLine, Qt.FlatCap))
        p.drawArc(rect, 90 * 16, -int(gspan * 16))
        p.setPen(QPen(QColor(AMBER), thick, Qt.SolidLine, Qt.FlatCap))
        p.drawArc(rect, int((90 - gspan) * 16), -int((360 - gspan) * 16))

        p.setFont(QFont("", max(9, int(d * 0.11)), QFont.Bold))
        p.setPen(QColor(TEAL))
        p.drawText(QRectF(x, y + d * 0.30, d, d * 0.20), Qt.AlignCenter, f"GPU {gpu}%")
        p.setPen(QColor(AMBER))
        p.drawText(QRectF(x, y + d * 0.50, d, d * 0.20), Qt.AlignCenter, f"CPU {cpu}%")


class BarChart(QWidget):
    """Balkendiagramm: ein Balken pro Lauf + Durchschnittslinie. Warmup amber."""

    def __init__(self):
        super().__init__()
        self._bars = []
        self._avg = None
        self._fmt = lambda v: f"{v:.0f}"
        self._caption = ""
        self.setMinimumHeight(150)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_data(self, bars, avg, fmt, caption=""):
        self._bars, self._avg, self._fmt, self._caption = bars, avg, fmt, caption
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        left, right, top, bottom = 10, 10, 24, 32
        plot = QRectF(left, top, w - left - right, h - top - bottom)

        if not self._bars:
            p.setPen(QColor(TXT2))
            p.setFont(QFont("", 9))
            p.drawText(self.rect(), Qt.AlignCenter,
                       "Aufgabe in der Tabelle wählen,\num die Läufe zu sehen.")
            return

        vals = [v for _, v, _ in self._bars if v is not None]
        vmax = (max(vals + ([self._avg] if self._avg else []), default=1) or 1) * 1.18
        n = len(self._bars)
        gap = 9
        bw = max(6, (plot.width() - gap * (n - 1)) / n)

        if self._avg:
            ay = plot.bottom() - (self._avg / vmax) * plot.height()
            p.setPen(QPen(QColor(TXT2), 1.3, Qt.DashLine))
            p.drawLine(QPointF(plot.left(), ay), QPointF(plot.right(), ay))
            p.setPen(QColor(TXT))
            p.setFont(QFont("", 8, QFont.Bold))
            p.drawText(QRectF(plot.left() + 2, ay - 15, plot.width(), 14),
                       Qt.AlignLeft | Qt.AlignVCenter, f"Ø {self._fmt(self._avg)}")

        for i, (lbl, val, warm) in enumerate(self._bars):
            if val is None:
                continue
            bx = plot.left() + i * (bw + gap)
            bh = (val / vmax) * plot.height()
            by = plot.bottom() - bh
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(AMBER) if warm else QColor(TEAL))
            p.drawRoundedRect(QRectF(bx, by, bw, bh), 4, 4)
            p.setPen(QColor(TXT))
            p.setFont(QFont("", 8))
            p.drawText(QRectF(bx - 6, by - 17, bw + 12, 14), Qt.AlignCenter, self._fmt(val))
            p.setPen(QColor(AMBER) if warm else QColor(TXT2))
            p.setFont(QFont("", 8, QFont.Bold if warm else QFont.Normal))
            p.drawText(QRectF(bx - 6, plot.bottom() + 4, bw + 12, 16), Qt.AlignCenter, lbl)

        if self._caption:
            p.setPen(QColor(TXT2))
            p.setFont(QFont("", 9))
            p.drawText(QRectF(left, 2, plot.width(), 16), Qt.AlignLeft, self._caption)


class StatTile(QFrame):
    """Kompakte KPI-Kachel: großer Wert + Beschriftung."""

    def __init__(self, caption, accent=TEAL):
        super().__init__()
        self.setObjectName("tile")
        v = QVBoxLayout(self)
        v.setContentsMargins(12, 9, 12, 9)
        v.setSpacing(1)
        self.val = QLabel("–")
        self.val.setStyleSheet(f"color:{accent};font-size:18pt;font-weight:700;")
        cap = QLabel(caption)
        cap.setStyleSheet(f"color:{TXT2};font-size:9pt;")
        v.addWidget(self.val)
        v.addWidget(cap)

    def set(self, text):
        self.val.setText(text)


# ================================================================ Benchmark =====
class BenchWorker(QObject):
    log = Signal(str)
    progress = Signal(object)
    task_row = Signal(object)
    finished = Signal(bool, str, object)

    def __init__(self, host, model, mode, reps, warmup, label, tasks, sys_info):
        super().__init__()
        self.host, self.model, self.mode = host, model, mode
        self.reps, self.warmup, self.label = reps, warmup, label
        self.tasks, self.sys_info = tasks, sys_info
        self._cancel = threading.Event()
        self._active_resp = None

    def request_cancel(self):
        self._cancel.set()
        r = self._active_resp
        if r is not None:
            try:
                r.close()
            except Exception:
                pass

    def _set_resp(self, r):
        self._active_resp = r

    @Slot()
    def run(self):
        try:
            bench.OLLAMA = self.host
            if not bench.ollama_up():
                self.finished.emit(False, f"Ollama nicht erreichbar ({self.host})", {})
                return
            model, mode = self.model, self.mode
            num_gpu = 0 if mode == "cpu" else None
            tasks, reps, warmup = self.tasks, self.reps, self.warmup
            total = len(tasks) * reps
            done = 0
            sum_rows = []
            comb = {"ttft": [], "prefill": [], "decode": [], "qual": []}
            self.log.emit(f"Start: {model} | {mode} | {len(tasks)} Aufgaben × {reps} "
                          f"Wiederholungen (+{warmup} Warmup)")

            for ti, task in enumerate(tasks):
                if self._cancel.is_set():
                    break
                tid = task["id"]
                self.log.emit(f"Aufgabe {ti + 1}/{len(tasks)}: {friendly(tid)}")
                self._emit_progress(done, total, tid, ti + 1, len(tasks), 0, reps)

                warm = None
                for w in range(warmup):
                    if self._cancel.is_set():
                        break
                    try:
                        wr = bench.run_once(model, task["prompt"], 16,
                                            task.get("num_ctx", 4096), num_gpu,
                                            rep=-1 - w, should_cancel=self._cancel.is_set,
                                            on_response=self._set_resp)
                        if w == 0:
                            warm = wr
                    except Exception as e:
                        self.log.emit(f"  Warmup-Fehler: {e}")

                samples = []
                for rep in range(reps):
                    if self._cancel.is_set():
                        break
                    self._emit_progress(done, total, tid, ti + 1, len(tasks), rep + 1, reps)
                    try:
                        r = bench.run_once(model, task["prompt"],
                                           task.get("num_predict", 256),
                                           task.get("num_ctx", 4096), num_gpu,
                                           rep=rep, should_cancel=self._cancel.is_set,
                                           on_response=self._set_resp)
                    except Exception as e:
                        self.log.emit(f"  Fehler (übersprungen): {e}")
                        continue
                    if self._cancel.is_set():
                        break
                    q = bench.quality_check(task, r["text"])
                    samples.append(r)
                    done += 1
                    self._emit_progress(done, total, tid, ti + 1, len(tasks), rep + 1, reps)
                    self.log.emit(
                        f"  Lauf {rep + 1}: TTFT {bench._f(r['ttft_ms'], 0)} ms · "
                        f"Prefill {bench._f(r['prefill_toks'], 1)} t/s · "
                        f"Decode {bench._f(r['decode_toks'], 1)} t/s"
                        + ("" if q is None else f" · Qualität {'ok' if q else 'FAIL'}"))

                if not samples:
                    continue
                ttft_m, ttft_p = bench.agg([s["ttft_ms"] for s in samples])
                pre_m, _ = bench.agg([s["prefill_toks"] for s in samples])
                dec_m, dec_p = bench.agg([s["decode_toks"] for s in samples])
                quals = [bench.quality_check(task, s["text"]) for s in samples]
                quals = [x for x in quals if x is not None]
                qrate = "" if not quals else f"{round(100 * sum(quals) / len(quals))}%"
                row = {
                    "label": self.label, "model": model, "mode": mode, "task": tid,
                    "ttft_ms_med": bench._f(ttft_m, 0), "ttft_ms_p95": bench._f(ttft_p, 0),
                    "prefill_toks_med": bench._f(pre_m, 1),
                    "decode_toks_med": bench._f(dec_m, 1),
                    "decode_toks_p95": bench._f(dec_p, 1),
                    "prompt_tokens": samples[0]["prompt_tokens"],
                    "gen_tokens": samples[0]["gen_tokens"], "quality": qrate,
                }
                sum_rows.append(row)
                detail = {
                    "reps_ttft": [s["ttft_ms"] for s in samples],
                    "reps_decode": [s["decode_toks"] for s in samples],
                    "reps_prefill": [s["prefill_toks"] for s in samples],
                    "warmup": ({"ttft_ms": warm["ttft_ms"], "decode_toks": warm["decode_toks"],
                                "prefill_toks": warm["prefill_toks"]} if warm else None),
                }
                self.task_row.emit({"summary": row, "detail": detail})
                comb["ttft"] += [s["ttft_ms"] for s in samples]
                comb["prefill"] += [s["prefill_toks"] for s in samples]
                comb["decode"] += [s["decode_toks"] for s in samples]
                comb["qual"] += quals

            cancelled = self._cancel.is_set()
            if sum_rows and not cancelled:
                g_ttft_m, _ = bench.agg(comb["ttft"])
                g_pre_m, _ = bench.agg(comb["prefill"])
                g_dec_m, g_dec_p = bench.agg(comb["decode"])
                g_qual = ("" if not comb["qual"]
                          else f"{round(100 * sum(comb['qual']) / len(comb['qual']))}%")
                gesamt = {
                    "label": self.label, "model": model, "mode": mode, "task": "GESAMT",
                    "ttft_ms_med": bench._f(g_ttft_m, 0), "ttft_ms_p95": "",
                    "prefill_toks_med": bench._f(g_pre_m, 1),
                    "decode_toks_med": bench._f(g_dec_m, 1),
                    "decode_toks_p95": bench._f(g_dec_p, 1),
                    "prompt_tokens": "", "gen_tokens": "", "quality": g_qual,
                }
                sum_rows.append(gesamt)
                self.task_row.emit({"summary": gesamt, "detail": None})

            placement = self._placement(model) if sum_rows else {"gpu_pct": None}
            ok = (not cancelled) and bool(sum_rows)
            msg = ("abgebrochen" if cancelled else
                   ("ohne Messwerte (Ollama/Modell prüfen)" if not sum_rows else "fertig"))
            payload = {
                "rows": sum_rows, "sys_info": self.sys_info, "label": self.label,
                "placement": placement,
                "config": {"model": model, "mode": mode, "reps": reps, "warmup": warmup,
                           "tasks": [t["id"] for t in tasks], "ollama": self.host,
                           "aborted": cancelled, "gpu_pct": placement.get("gpu_pct")},
            }
            self.finished.emit(ok, msg, payload)
        except Exception as e:  # pragma: no cover
            self.finished.emit(False, f"Fehler: {e}", {})

    def _placement(self, model):
        try:
            data = bench.http_json("/api/ps", timeout=5)
            for m in data.get("models", []):
                if model in (m.get("name"), m.get("model")):
                    total = m.get("size", 0) or 0
                    vram = m.get("size_vram", 0) or 0
                    pct = round(100 * vram / total) if total else None
                    return {"gpu_pct": pct,
                            "vram_mb": round(vram / 1e6) if total else None,
                            "total_mb": round(total / 1e6) if total else None}
        except Exception:
            pass
        return {"gpu_pct": None, "vram_mb": None, "total_mb": None}

    def _emit_progress(self, done, total, tid, ti, tt, rep, rep_total):
        self.progress.emit({"done": done, "total": total, "task": tid, "task_idx": ti,
                            "task_total": tt, "rep": rep, "rep_total": rep_total})


# ================================================================ Hilfe-Dialog ==
HELP_STYLE = (f"<style>body{{color:{TXT};font-size:10.5pt;}} h2,h3{{color:{TEAL};}}"
              f"a{{color:{TEAL};}} code{{color:{AMBER};}}"
              f"pre{{background:{BG};color:#d8dee9;padding:8px;border-radius:6px;"
              "white-space:pre-wrap;}}</style>")


class HelpDialog(QDialog):
    def __init__(self, parent, tasks):
        super().__init__(parent)
        self.setWindowTitle("Hilfe & Infos")
        self.resize(740, 600)
        lay = QVBoxLayout(self)
        tabs = QTabWidget()
        tabs.addTab(self._page(self._bedienung()), "Bedienung")
        tabs.addTab(self._page(self._begriffe()), "Begriffe")
        tabs.addTab(self._page(self._aufgaben(tasks)), "Aufgaben")
        tabs.addTab(self._page(self._lizenz()), "Lizenz")
        tabs.addTab(self._page(self._ueber()), "Über")
        lay.addWidget(tabs)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        bb.accepted.connect(self.accept)
        lay.addWidget(bb)

    @staticmethod
    def _page(htmltext):
        b = QTextBrowser()
        b.setOpenExternalLinks(True)
        b.setHtml(HELP_STYLE + htmltext)
        return b

    @staticmethod
    def _bedienung():
        return (
            "<h2>So benutzt du das Programm</h2><ol>"
            "<li><b>Ollama starten.</b> Das Programm misst lokale KI-Modelle über Ollama "
            "(<a href='https://ollama.com'>ollama.com</a>). Es muss laufen.</li>"
            "<li><b>Host prüfen.</b> Standard <code>http://localhost:11434</code> (dein Rechner). "
            "Für einen anderen Rechner im Netz dessen <code>http://&lt;ip&gt;:11434</code> "
            "eintragen – dann wird DESSEN Hardware gemessen.</li>"
            "<li><b>Modelle suchen.</b> Füllt das Dropdown mit den installierten Modellen.</li>"
            "<li><b>Modell &amp; Modus wählen</b> (gpu/cpu), Wiederholungen und Warmup einstellen.</li>"
            "<li><b>Test starten.</b> Es laufen alle Büro-Aufgaben durch. Jederzeit abbrechbar.</li>"
            "<li><b>Ergebnis ansehen.</b> Oben die Kennzahlen, links die Tabelle, rechts die "
            "Diagramme (Ring = GPU/CPU-Verteilung, Balken = einzelne Läufe). Klicke eine Aufgabe "
            "in der Tabelle, um ihre Läufe zu sehen.</li>"
            "<li><b>Exportieren</b> als CSV, Markdown oder JSON.</li></ol>"
            "<p><i>Tipp für einen schnellen Eindruck: kleines Modell, Wiederholungen auf 1–2.</i></p>")

    @staticmethod
    def _begriffe():
        return (
            "<h2>Was gemessen wird</h2><ul>"
            "<li><b>Prefill</b> (t/s): Tempo beim Verarbeiten der Eingabe (rechenlastig).</li>"
            "<li><b>Decode</b> (t/s): Tempo beim Erzeugen der Antwort (bandbreitenlastig – "
            "hier trennen sich GPU und Mac).</li>"
            "<li><b>TTFT</b> (ms): Zeit bis zum ersten Token – die gefühlte Reaktionszeit.</li>"
            "<li><b>Qualität</b>: deterministischer Stichprobentest (nur bei prüfbaren Aufgaben).</li>"
            "<li><b>Median / p95</b>: typischer Wert bzw. nahe Worst-Case über die Wiederholungen.</li>"
            "</ul><h3>Begriffe</h3><ul>"
            "<li><b>Modus gpu</b>: Ollama nutzt die GPU; passt das Modell nicht in den VRAM, wird "
            "ein Teil auf die CPU ausgelagert (Hybrid). <b>Modus cpu</b>: erzwingt reine CPU.</li>"
            "<li><b>Warmup</b>: nicht gewerteter Vorlauf, der das Modell lädt. Der Kaltstart ist viel "
            "langsamer – im Balkendiagramm als oranger Balken sichtbar.</li>"
            "<li><b>Wiederholungen</b>: mehrere Messungen → stabiler Durchschnitt.</li>"
            "<li><b>GPU/CPU-Verteilung</b>: der Ring zeigt, wie sich das Modell (100%) auf GPU "
            "(VRAM) und CPU verteilt hat.</li></ul>")

    @staticmethod
    def _aufgaben(tasks):
        def esc(s):
            return html.escape(str(s))
        p = [f"<h2>Aufgaben ({len(tasks)})</h2>"]
        if not tasks:
            p.append("<p><i>Keine Aufgaben geladen (tasks.json fehlt?).</i></p>")
        for t in tasks:
            if "check_keys" in t:
                qc = "JSON-Schlüssel: " + ", ".join(t["check_keys"])
            elif "expect_contains" in t:
                qc = f'Antwort muss enthalten: "{t["expect_contains"]}"'
            else:
                qc = "keine (reine Tempo-Messung)"
            p.append(f"<h3>{esc(friendly(t.get('id')))} "
                     f"<span style='color:{TXT2};font-weight:normal'>({esc(t.get('id'))})</span></h3>")
            p.append(f"<p><i>{esc(t.get('beschreibung', ''))}</i></p>")
            p.append(f"<p>Kontext: {t.get('num_ctx', 4096)} Tokens &middot; "
                     f"max. Ausgabe: {t.get('num_predict', 256)} Tokens &middot; "
                     f"Qualitätsprüfung: {esc(qc)}</p>")
            p.append(f"<p><b>Prompt:</b></p><pre>{esc(t.get('prompt', ''))}</pre>")
        return "".join(p)

    @staticmethod
    def _lizenz():
        try:
            with open(resource_path("LICENSE"), encoding="utf-8") as f:
                text = f.read()
        except Exception:
            text = "MIT License – siehe LICENSE-Datei im Projekt."
        return "<h2>Lizenz</h2><pre>" + html.escape(text) + "</pre>"

    @staticmethod
    def _ueber():
        return (
            f"<h2>Lokaler LLM-Benchmark</h2><p>Version {VERSION}</p>"
            "<p>Misst Geschwindigkeit (Prefill, Decode, Time-to-First-Token) und eine einfache "
            "Qualitätsprüfung lokaler KI-Modelle über Ollama – um Hardware zu vergleichen: "
            "<b>GPU-PC vs. Apple-Silicon-Mac vs. CPU&nbsp;+&nbsp;viel RAM</b>.</p>"
            "<p>Kernidee: Genauigkeit hängt am Modell, nicht an der Hardware. Die Hardware-Frage "
            "ist <b>Tempo + Preis + Speicher + Energie</b>.</p>"
            "<p>Autor: Marcel Räuber · "
            "<a href='https://github.com/MarcelDIY/Benchmark'>github.com/MarcelDIY/Benchmark</a></p>")


# ================================================================== Fenster =====
class MainWindow(QMainWindow):
    IDLE, SCANNING, RUNNING = "idle", "scanning", "running"
    METRICS = [("Decode (t/s)", "reps_decode", "decode_toks", lambda v: f"{v:.1f}"),
               ("Prefill (t/s)", "reps_prefill", "prefill_toks", lambda v: f"{v:.0f}"),
               ("TTFT (ms)", "reps_ttft", "ttft_ms", lambda v: f"{v:.0f}")]

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Lokaler LLM-Benchmark")
        _icon = QIcon(resource_path(os.path.join("assets", "icon.png")))
        if not _icon.isNull():
            self.setWindowIcon(_icon)
        # an den Bildschirm anpassen (passt auch auf kleine Displays)
        scr = QApplication.primaryScreen().availableGeometry()
        self.resize(min(1040, int(scr.width() * 0.94)), min(880, int(scr.height() * 0.94)))
        self.setMinimumSize(760, 500)

        self._thread = None
        self._worker = None
        self._last_payload = None
        self._details = {}
        self.sys_info = bench.system_info()
        self.tasks = self._load_tasks()

        self._build_menu()
        self._build_ui()
        self._set_state(self.IDLE)
        self._auto_scan_on_start()

    def _load_tasks(self):
        try:
            with open(resource_path("tasks.json"), encoding="utf-8") as f:
                cfg = json.load(f)
            self._cfg = cfg
            return cfg.get("tasks", [])
        except Exception as e:
            self._cfg = {}
            QMessageBox.warning(self, "tasks.json", f"Konnte tasks.json nicht laden:\n{e}")
            return []

    def _build_menu(self):
        m = self.menuBar().addMenu("&Hilfe")
        a = QAction("Handbuch && Infos …", self)
        a.triggered.connect(lambda: self.show_help())
        m.addAction(a)
        m.addSeparator()
        ab = QAction("Über", self)
        ab.triggered.connect(lambda: self.show_help(tab=4))
        m.addAction(ab)

    def show_help(self, *, tab=0):
        dlg = HelpDialog(self, self.tasks)
        tabsw = dlg.findChild(QTabWidget)
        if tabsw and isinstance(tab, int):
            tabsw.setCurrentIndex(tab)
        dlg.exec()

    # ---- UI ----
    def _build_ui(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        inner = QWidget()
        root = QVBoxLayout(inner)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(9)

        # Verbindung
        conn_box = QGroupBox("Verbindung")
        conn = QHBoxLayout(conn_box)
        conn.addWidget(QLabel("Ollama-Host:"))
        self.host_edit = QLineEdit(os.environ.get("OLLAMA_HOST", "http://localhost:11434"))
        self.host_edit.setToolTip(
            "Adresse, unter der Ollama läuft.\nEigener Rechner: http://localhost:11434\n"
            "Anderer Rechner im Netz (misst DESSEN Hardware): http://<ip>:11434")
        conn.addWidget(self.host_edit, 1)
        self.scan_btn = QPushButton("Modelle suchen")
        self.scan_btn.clicked.connect(self.on_scan)
        conn.addWidget(self.scan_btn)
        self.status_label = QLabel("Noch nicht gescannt.")
        self.status_label.setStyleSheet(f"color:{TXT2};")
        conn.addWidget(self.status_label)
        root.addWidget(conn_box)

        # Parameter
        par_box = QGroupBox("Parameter")
        grid = QGridLayout(par_box)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(8)
        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(220)
        self.model_combo.setToolTip("Eines der in Ollama installierten Modelle.")
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["gpu", "cpu"])
        self.mode_combo.setToolTip(
            "gpu = GPU nutzen (bei zu wenig VRAM teils CPU-Auslagerung).\n"
            "cpu = erzwingt reine CPU.\nDie tatsächliche Verteilung zeigt der Ring nach dem Lauf.")
        self.reps_spin = QSpinBox()
        self.reps_spin.setRange(1, 50)
        self.reps_spin.setValue(int(self._cfg.get("reps", 5)) if hasattr(self, "_cfg") else 5)
        self.reps_spin.setToolTip("Anzahl gewerteter Messungen pro Aufgabe (mehr = stabiler).")
        self.warmup_spin = QSpinBox()
        self.warmup_spin.setRange(0, 5)
        self.warmup_spin.setValue(int(self._cfg.get("warmup", 1)) if hasattr(self, "_cfg") else 1)
        self.warmup_spin.setToolTip("Nicht gewertete Vorläufe, die das Modell laden (Kaltstart).")
        self.label_edit = QLineEdit(platform.node() or "rechner")
        self.label_edit.setToolTip("Etikett für die Ergebnisse/Exportdateien (Gerätename).")
        grid.addWidget(QLabel("Modell:"), 0, 0)
        grid.addWidget(self.model_combo, 0, 1)
        grid.addWidget(QLabel("Modus:"), 0, 2)
        grid.addWidget(self.mode_combo, 0, 3)
        grid.addWidget(QLabel("Wiederholungen:"), 1, 0)
        grid.addWidget(self.reps_spin, 1, 1)
        grid.addWidget(QLabel("Warmup:"), 1, 2)
        grid.addWidget(self.warmup_spin, 1, 3)
        grid.addWidget(QLabel("Label:"), 2, 0)
        grid.addWidget(self.label_edit, 2, 1)
        self.start_btn = QPushButton("▶  Test starten")
        self.start_btn.setObjectName("primary")
        self.start_btn.clicked.connect(self.on_start)
        self.cancel_btn = QPushButton("Abbrechen")
        self.cancel_btn.clicked.connect(self.on_cancel)
        brow = QHBoxLayout()
        brow.addStretch(1)
        brow.addWidget(self.start_btn)
        brow.addWidget(self.cancel_btn)
        grid.addLayout(brow, 2, 2, 1, 2)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        root.addWidget(par_box)

        # Fortschritt
        prog_box = QGroupBox("Fortschritt")
        prog = QVBoxLayout(prog_box)
        self.prog_label = QLabel("Bereit.")
        self.prog_label.setStyleSheet("font-weight:600;")
        prog.addWidget(self.prog_label)
        self.prog_bar = QProgressBar()
        self.prog_bar.setTextVisible(False)
        prog.addWidget(self.prog_bar)
        self.detail_btn = QPushButton("▸ Protokoll anzeigen")
        self.detail_btn.setObjectName("link")
        self.detail_btn.setCheckable(True)
        self.detail_btn.toggled.connect(self._toggle_log)
        prog.addWidget(self.detail_btn, 0, Qt.AlignLeft)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(2000)
        self.log_view.setFixedHeight(110)
        self.log_view.setVisible(False)
        prog.addWidget(self.log_view)
        root.addWidget(prog_box)

        # Ergebnisse
        res_box = QGroupBox("Ergebnisse")
        res = QVBoxLayout(res_box)
        kpi = QHBoxLayout()
        kpi.setSpacing(8)
        self.tile_decode = StatTile("Decode Ø (t/s)")
        self.tile_prefill = StatTile("Prefill Ø (t/s)")
        self.tile_ttft = StatTile("TTFT (ms)")
        self.tile_qual = StatTile("Qualität", GREEN)
        for t in (self.tile_decode, self.tile_prefill, self.tile_ttft, self.tile_qual):
            kpi.addWidget(t, 1)
        res.addLayout(kpi)

        split = QSplitter(Qt.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget(0, len(TABLE_COLS))
        self.table.setHorizontalHeaderLabels([c[1] for c in TABLE_COLS])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for i in range(1, len(TABLE_COLS)):
            self.table.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.itemSelectionChanged.connect(self.on_row_selected)
        self.table.setMinimumHeight(150)
        ll.addWidget(self.table)
        legend = QLabel("Prefill = Eingabe-Tempo · Decode = Ausgabe-Tempo · "
                        "TTFT = Reaktionszeit · Qualität = Korrektheit")
        legend.setWordWrap(True)
        legend.setStyleSheet(f"color:{TXT2};font-size:9pt;")
        ll.addWidget(legend)
        split.addWidget(left)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(self._titled("GPU/CPU-Verteilung"))
        self.donut = DonutChart()
        rl.addWidget(self.donut)
        self.placement_label = QLabel("")
        self.placement_label.setAlignment(Qt.AlignCenter)
        self.placement_label.setWordWrap(True)
        self.placement_label.setStyleSheet(f"color:{TXT2};font-size:9pt;")
        rl.addWidget(self.placement_label)
        mrow = QHBoxLayout()
        mrow.addWidget(self._titled("Läufe je Aufgabe"))
        mrow.addStretch(1)
        self.metric_combo = QComboBox()
        self.metric_combo.addItems([m[0] for m in self.METRICS])
        self.metric_combo.currentIndexChanged.connect(lambda _i: self._update_charts())
        mrow.addWidget(self.metric_combo)
        rl.addLayout(mrow)
        self.bars = BarChart()
        rl.addWidget(self.bars, 1)
        split.addWidget(right)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        split.setSizes([560, 420])
        res.addWidget(split, 1)

        exp_row = QHBoxLayout()
        self.help_btn = QPushButton("Hilfe && Infos")
        self.help_btn.clicked.connect(lambda: self.show_help())
        exp_row.addWidget(self.help_btn)
        exp_row.addStretch(1)
        self.export_csv_btn = QPushButton("Export CSV")
        self.export_csv_btn.clicked.connect(lambda: self.on_export("csv"))
        self.export_md_btn = QPushButton("Export Markdown")
        self.export_md_btn.clicked.connect(lambda: self.on_export("md"))
        self.export_json_btn = QPushButton("Export JSON")
        self.export_json_btn.clicked.connect(lambda: self.on_export("json"))
        for b in (self.export_csv_btn, self.export_md_btn, self.export_json_btn):
            exp_row.addWidget(b)
        res.addLayout(exp_row)
        root.addWidget(res_box, 1)

        scroll.setWidget(inner)
        self.setCentralWidget(scroll)
        self.statusBar().showMessage(
            f"System: {self.sys_info['os']} | {self.sys_info['cpu']} | "
            f"{self.sys_info['ram_gb']} GB RAM")

    @staticmethod
    def _titled(text):
        lab = QLabel(text)
        lab.setStyleSheet(f"font-weight:600;color:{TXT};")
        return lab

    def _toggle_log(self, on):
        self.log_view.setVisible(on)
        self.detail_btn.setText(("▾ " if on else "▸ ") + "Protokoll anzeigen")

    # ---- Zustand ----
    def _set_state(self, state):
        self._state = state
        idle = state == self.IDLE
        running = state == self.RUNNING
        has_model = self.model_combo.count() > 0
        has_results = self._last_payload is not None and bool(self._last_payload.get("rows"))
        for w in (self.host_edit, self.scan_btn, self.mode_combo, self.reps_spin,
                  self.warmup_spin, self.label_edit):
            w.setEnabled(idle)
        self.model_combo.setEnabled(idle and has_model)
        self.start_btn.setEnabled(idle and has_model)
        self.cancel_btn.setEnabled(running)
        for b in (self.export_csv_btn, self.export_md_btn, self.export_json_btn):
            b.setEnabled(idle and has_results)
        if state == self.SCANNING:
            self.statusBar().showMessage("Scanne Host …")
        elif running:
            self.statusBar().showMessage("Benchmark läuft …")

    # ---- Scan (synchron) ----
    def _auto_scan_on_start(self):
        QTimer.singleShot(0, self.on_scan)

    def on_scan(self):
        if self._state != self.IDLE:
            return
        host = normalize_host(self.host_edit.text())
        self.host_edit.setText(host)
        self.status_label.setText("Suche …")
        self._set_state(self.SCANNING)
        QApplication.processEvents()
        bench.OLLAMA = host
        try:
            reachable = bench.ollama_up()
            models = bench.installed_models(timeout=6) if reachable else []
        except Exception as e:
            reachable, models = False, []
            self.status_label.setText(f"⚠ Scan fehlgeschlagen: {e}")
        else:
            if reachable:
                msg = (f"✓ erreichbar – {len(models)} Modell(e)" if models
                       else "✓ erreichbar, keine Modelle")
            else:
                msg = "⚠ nicht erreichbar"
            self.status_label.setText(msg)
        prev = self.model_combo.currentText()
        self.model_combo.clear()
        if models:
            self.model_combo.addItems(models)
            if prev in models:
                self.model_combo.setCurrentText(prev)
        self._set_state(self.IDLE)

    # ---- Benchmark ----
    def on_start(self):
        if self._state != self.IDLE or self.model_combo.count() == 0:
            return
        if not self.tasks:
            QMessageBox.warning(self, "Keine Aufgaben", "tasks.json enthält keine Aufgaben.")
            return
        host = normalize_host(self.host_edit.text())
        self.host_edit.setText(host)
        self.table.setRowCount(0)
        self._details.clear()
        self.log_view.clear()
        self.prog_bar.setValue(0)
        self.prog_label.setText("Starte …")
        self.placement_label.setText("")
        self.donut.set_value(None)
        self.bars.set_data([], None, lambda v: f"{v}")
        for t in (self.tile_decode, self.tile_prefill, self.tile_ttft, self.tile_qual):
            t.set("–")
        self._last_payload = None

        self._worker = BenchWorker(
            host=host, model=self.model_combo.currentText(),
            mode=self.mode_combo.currentText(), reps=self.reps_spin.value(),
            warmup=self.warmup_spin.value(),
            label=self.label_edit.text().strip() or "rechner",
            tasks=self.tasks, sys_info=self.sys_info)
        self._thread = QThread()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.log.connect(self.on_log)
        self._worker.progress.connect(self.on_progress)
        self._worker.task_row.connect(self.on_task_row)
        self._worker.finished.connect(self.on_finished)
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._clear_threads)
        self._set_state(self.RUNNING)
        self._thread.start()

    def _clear_threads(self):
        self._worker = None
        self._thread = None
        self._set_state(self.IDLE)

    def on_cancel(self):
        if self._worker is not None and isinstance(self._worker, BenchWorker):
            self._worker.request_cancel()
            self.cancel_btn.setEnabled(False)
            self.statusBar().showMessage("Breche ab …")

    @Slot(str)
    def on_log(self, text):
        self.log_view.appendPlainText(text)

    @Slot(object)
    def on_progress(self, d):
        self.prog_bar.setMaximum(max(1, d["total"]))
        self.prog_bar.setValue(d["done"])
        if d["rep"]:
            txt = (f"Aufgabe {d['task_idx']}/{d['task_total']}: {friendly(d['task'])} – "
                   f"Wiederholung {d['rep']}/{d['rep_total']}")
        else:
            txt = (f"Aufgabe {d['task_idx']}/{d['task_total']}: {friendly(d['task'])} – "
                   "wärme Modell auf …")
        self.prog_label.setText(txt + f"   ({d['done']}/{d['total']} Messungen)")

    @Slot(object)
    def on_task_row(self, msg):
        row = msg["summary"]
        detail = msg.get("detail")
        tid = row.get("task")
        if detail is not None:
            self._details[tid] = detail
        r = self.table.rowCount()
        self.table.insertRow(r)
        is_total = tid == "GESAMT"
        for c, (key, _label) in enumerate(TABLE_COLS):
            val = friendly(row[key]) if key == "task" else row.get(key, "")
            item = QTableWidgetItem("" if val == "" or val is None else str(val))
            if c == 0:
                item.setData(Qt.UserRole, tid)
            else:
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if is_total:
                f = item.font()
                f.setBold(True)
                item.setFont(f)
                item.setForeground(QColor(TEAL))
            self.table.setItem(r, c, item)

    @Slot(bool, str, object)
    def on_finished(self, ok, msg, payload):
        self._last_payload = payload if payload else None
        self.statusBar().showMessage(f"Benchmark {msg}.")
        self.prog_label.setText("Fertig." if ok else f"Benchmark {msg}.")
        self._show_placement(payload)
        self._fill_kpis(payload)
        if self.table.rowCount():
            for r in range(self.table.rowCount()):
                cell = self.table.item(r, 0)
                if cell and cell.data(Qt.UserRole) != "GESAMT":
                    self.table.selectRow(r)
                    break
        rows = payload.get("rows") if payload else None
        if not rows and msg != "abgebrochen":
            QTimer.singleShot(0, lambda m=msg: QMessageBox.warning(
                self, "Kein Ergebnis", m or "Unbekannter Fehler"))

    def _fill_kpis(self, payload):
        rows = (payload or {}).get("rows") or []
        g = next((r for r in rows if r.get("task") == "GESAMT"), None) or (rows[0] if rows else None)
        if not g:
            return
        self.tile_decode.set(f"{g.get('decode_toks_med', '–')}")
        self.tile_prefill.set(f"{g.get('prefill_toks_med', '–')}")
        self.tile_ttft.set(f"{g.get('ttft_ms_med', '–')}")
        self.tile_qual.set(g.get("quality") or "n/a")

    def _show_placement(self, payload):
        pl = payload.get("placement") if payload else None
        cfg = payload.get("config") if payload else {}
        if not pl or pl.get("gpu_pct") is None:
            self.donut.set_value(None)
            self.placement_label.setText("")
            return
        gp = pl["gpu_pct"]
        self.donut.set_value(gp)
        extra = (f"{pl['vram_mb']} von {pl['total_mb']} MB im VRAM · "
                 if pl.get("total_mb") else "")
        self.placement_label.setText(f"{extra}Modus '{cfg.get('mode', '?')}'")

    # ---- Diagramme ----
    def on_row_selected(self):
        self._update_charts()

    def _selected_task(self):
        items = self.table.selectedItems()
        if not items:
            return None
        cell = self.table.item(items[0].row(), 0)
        return cell.data(Qt.UserRole) if cell else None

    def _update_charts(self):
        tid = self._selected_task()
        _name, reps_key, warm_key, fmt = self.METRICS[self.metric_combo.currentIndex()]
        detail = self._details.get(tid)
        if not detail:
            self.bars.set_data([], None, fmt, "GESAMT" if tid == "GESAMT" else "")
            return
        bars = []
        warm = detail.get("warmup")
        if warm and warm.get(warm_key) is not None:
            bars.append(("Warmup", warm[warm_key], True))
        for i, v in enumerate(detail.get(reps_key, []) or []):
            bars.append((f"#{i + 1}", v, False))
        valid = [v for _, v, w in bars if (not w) and v is not None]
        avg = statistics.mean(valid) if valid else None
        self.bars.set_data(bars, avg, fmt, f"{friendly(tid)} – {self.metric_combo.currentText()}")

    # ---- Export ----
    def on_export(self, fmt):
        if not self._last_payload or not self._last_payload.get("rows"):
            return
        label = safe_label(self._last_payload.get("label", "rechner"))
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        ext = {"csv": "csv", "md": "md", "json": "json"}[fmt]
        default = os.path.join(default_output_dir(), f"summary_{label}_{stamp}.{ext}")
        filt = {"csv": "CSV (*.csv)", "md": "Markdown (*.md)", "json": "JSON (*.json)"}[fmt]
        path, _ = QFileDialog.getSaveFileName(self, "Export speichern", default, filt)
        if not path:
            return
        rows = self._last_payload["rows"]
        info = self._last_payload["sys_info"]
        lab = self._last_payload["label"]
        try:
            if fmt == "csv":
                bench._write_dict_csv(path, rows)
            elif fmt == "md":
                bench._write_md(path, lab, info, rows)
            else:
                obj = {"schema_version": 1, "label": lab,
                       "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                       "system": info, "config": self._last_payload.get("config", {}),
                       "rows": rows}
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(obj, f, ensure_ascii=False, indent=2)
            self.statusBar().showMessage(f"Exportiert: {path}")
        except Exception as e:
            QMessageBox.critical(self, "Export fehlgeschlagen", str(e))

    def closeEvent(self, event):
        if self._worker is not None and hasattr(self._worker, "request_cancel"):
            self._worker.request_cancel()
        th = self._thread
        if th is not None:
            th.quit()
            if not th.wait(7000):
                th.terminate()
                th.wait(2000)
        event.accept()


STYLESHEET = f"""
QMainWindow, QDialog, QScrollArea {{ background: {BG}; }}
QWidget {{ color: {TXT}; font-size: 10.5pt; }}
QScrollArea {{ border: none; }}
QGroupBox {{
    background: {CARD}; border: 1px solid {BORDER}; border-radius: 12px;
    margin-top: 16px; padding: 14px 14px 12px 14px; font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin; subcontrol-position: top left; left: 14px; top: 1px;
    padding: 1px 8px; color: {TXT2}; background: transparent;
}}
QLabel {{ background: transparent; }}
QPushButton {{
    background: {INPUT}; border: 1px solid {BORDER}; border-radius: 8px;
    padding: 7px 14px; color: {TXT};
}}
QPushButton:hover {{ border-color: {TEAL}; }}
QPushButton:disabled {{ color: #5b6678; background: #232932; border-color: #2b313c; }}
QPushButton#primary {{ background: {TEAL}; color: #08231f; border: none; font-weight: 700; }}
QPushButton#primary:hover {{ background: #45e0cd; }}
QPushButton#primary:disabled {{ background: #2a4a45; color: #5e7a75; }}
QPushButton#link {{ background: transparent; border: none; color: {TEAL}; text-align: left; padding: 2px; }}
QLineEdit, QComboBox, QSpinBox {{
    background: {INPUT}; border: 1px solid {BORDER}; border-radius: 8px; padding: 6px 8px; color: {TXT};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{ border: 1px solid {TEAL}; }}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox QAbstractItemView {{ background: {INPUT}; color: {TXT}; selection-background-color: {TEAL}; selection-color: #08231f; }}
QProgressBar {{ background: {INPUT}; border: none; border-radius: 7px; min-height: 12px; }}
QProgressBar::chunk {{ background: {TEAL}; border-radius: 7px; }}
QFrame#tile {{ background: {INPUT}; border: 1px solid {BORDER}; border-radius: 10px; }}
QTableWidget {{
    background: {CARD}; border: 1px solid {BORDER}; border-radius: 8px;
    gridline-color: #2b313c; alternate-background-color: #242b35;
    selection-background-color: #214a45; selection-color: {TXT};
}}
QTableWidget::item {{ padding: 5px; }}
QHeaderView::section {{
    background: {INPUT}; color: {TXT2}; border: none; border-bottom: 2px solid {BORDER};
    padding: 7px; font-weight: 600;
}}
QTableCornerButton::section {{ background: {INPUT}; border: none; }}
QTextBrowser {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 6px; color: {TXT}; }}
QTabWidget::pane {{ border: 1px solid {BORDER}; border-radius: 6px; top: -1px; }}
QTabBar::tab {{
    background: {INPUT}; color: {TXT2}; padding: 7px 16px;
    border-top-left-radius: 8px; border-top-right-radius: 8px; margin-right: 2px;
}}
QTabBar::tab:selected {{ background: {TEAL}; color: #08231f; }}
QMenuBar {{ background: {CARD}; color: {TXT}; border-bottom: 1px solid {BORDER}; }}
QMenuBar::item {{ padding: 6px 10px; background: transparent; }}
QMenuBar::item:selected {{ background: {INPUT}; }}
QMenu {{ background: {CARD}; color: {TXT}; border: 1px solid {BORDER}; }}
QMenu::item:selected {{ background: {INPUT}; }}
QStatusBar {{ background: {CARD}; color: {TXT2}; }}
QScrollBar:vertical {{ background: {BG}; width: 11px; margin: 0; }}
QScrollBar::handle:vertical {{ background: #3a4250; border-radius: 5px; min-height: 24px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QToolTip {{ background: {INPUT}; color: {TXT}; border: 1px solid {BORDER}; padding: 6px; }}
"""


def main():
    if "--selftest" in sys.argv:
        with open(resource_path("tasks.json"), encoding="utf-8") as f:
            n = len(json.load(f).get("tasks", []))
        print(f"selftest OK: tasks.json gefunden, {n} Aufgaben, "
              f"frozen={getattr(sys, 'frozen', False)}")
        return
    app = QApplication(sys.argv)
    app.setApplicationName("LLM-Benchmark")
    app.setStyleSheet(STYLESHEET)
    _icon = QIcon(resource_path(os.path.join("assets", "icon.png")))
    if not _icon.isNull():
        app.setWindowIcon(_icon)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
