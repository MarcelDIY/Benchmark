#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Standalone-GUI für den lokalen Büro-LLM-Hardware-Benchmark (Tokyo-Night-Dashboard).

PySide6-Frontend für bench.py: Modelle aus Ollama scannen, eines testen, Ergebnisse
als KPI-Kacheln, SVG-Diagramme (Ring + Balken) und Tabelle ansehen, mehrere Läufe
verschiedener Modelle sammeln und im Reiter "Vergleich" gegenüberstellen, exportieren.

Voraussetzung zur Laufzeit: ein laufendes Ollama (Standard http://localhost:11434).
Die Messung kommt unverändert aus bench.py. Standalone baubar via PyInstaller.
"""
import html
import json
import os
import platform
import statistics
import sys
import threading
from datetime import datetime, timezone

from PySide6.QtCore import QByteArray, QRectF, Qt, QTimer, QObject, QThread, Signal, Slot
from PySide6.QtGui import QAction, QColor, QFont, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFrame,
    QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QScrollArea, QSizePolicy,
    QSpinBox, QSplitter, QTabWidget, QTableWidget, QTableWidgetItem, QTextBrowser,
    QVBoxLayout, QWidget,
)

import bench
import svgcharts as SC

VERSION = "1.0"

# Palette (Tokyo Night)
BG = "#16161e"
CARD = "#1a1b26"
INPUT = "#1f2335"
BORDER = "#2a2e42"
TXT = "#c0caf5"
TXT2 = "#565f89"
BLUE = "#7aa2f7"
CYAN = "#7dcfff"
TEAL = "#73daca"
GREEN = "#9ece6a"
AMBER = "#e0af68"
RED = "#f7768e"

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


def _num(v):
    """'' / None / 'x' -> None, sonst float."""
    try:
        if v in ("", None):
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _pct(v):
    """'100%' -> 100.0, '' / None -> None."""
    try:
        s = str(v).strip().rstrip("%")
        return float(s) if s not in ("", "None") else None
    except ValueError:
        return None


TABLE_COLS = [
    ("task", "Aufgabe"),
    ("ttft_ms_med", "TTFT (ms)"),
    ("prefill_toks_med", "Prefill (t/s)"),
    ("decode_toks_med", "Decode (t/s)"),
    ("quality", "Qualität"),
]


# ============================================================ SVG-Diagramm ======
class SvgView(QWidget):
    """Zeigt ein dynamisch erzeugtes SVG (Generator(w,h)->str) scharf an."""

    def __init__(self, minh=140):
        super().__init__()
        self._gen = None
        self.setMinimumHeight(minh)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_gen(self, gen):
        self._gen = gen
        self.update()

    def paintEvent(self, _):
        if not self._gen:
            return
        w, h = max(1, self.width()), max(1, self.height())
        try:
            svg = self._gen(w, h)
        except Exception:
            return
        r = QSvgRenderer(QByteArray(svg.encode("utf-8")))
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r.render(p, QRectF(0, 0, w, h))
        p.end()


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
            total_wall = 0.0
            cold_start_ms = None
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
                        total_wall += wr.get("wall_s", 0) or 0
                        if cold_start_ms is None and wr.get("ttft_ms") is not None:
                            cold_start_ms = wr["ttft_ms"]
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
                    total_wall += r.get("wall_s", 0) or 0
                    if cold_start_ms is None and r.get("ttft_ms") is not None:
                        cold_start_ms = r["ttft_ms"]
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
                "cold_start_ms": cold_start_ms, "total_wall_s": round(total_wall, 1),
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
HELP_STYLE = (
    "<style>"
    f"body{{color:{TXT};font-size:11pt;line-height:150%;}}"
    f"h2{{color:{CYAN};font-size:17pt;margin:0 0 6px 0;}}"
    f"h3{{color:{TEAL};font-size:12.5pt;margin:16px 0 2px 0;}}"
    f"a{{color:{BLUE};text-decoration:none;}}"
    f"code{{color:{AMBER};font-family:monospace;}}"
    f"pre{{background:{BG};color:#a9b1d6;padding:10px;font-family:monospace;white-space:pre-wrap;}}"
    f"li{{margin-bottom:5px;}} ol,ul{{margin-left:2px;}} .lead{{color:{TXT2};}}"
    "</style>")


class HelpDialog(QDialog):
    def __init__(self, parent, tasks):
        super().__init__(parent)
        self.setWindowTitle("Hilfe & Infos")
        self.resize(760, 620)
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
        b.document().setDocumentMargin(18)
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
            "<li><b>Ergebnis ansehen</b> (Reiter „Aktueller Lauf“): Kennzahlen, Ring (GPU/CPU), "
            "Tabelle und Balken je Lauf. Klicke eine Aufgabe, um ihre Läufe zu sehen.</li>"
            "<li><b>Vergleichen.</b> Starte weitere Tests mit anderen Modellen – im Reiter "
            "„Vergleich“ stehen alle Läufe nebeneinander.</li>"
            "<li><b>Exportieren</b> als CSV, Markdown oder JSON.</li></ol>"
            "<p><i>Tipp: kleines Modell + Wiederholungen 1–2 für einen schnellen ersten Eindruck.</i></p>")

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
            "<li><b>GPU/CPU-Verteilung</b>: der Ring zeigt das Modell (100%) verteilt auf GPU "
            "(VRAM) und CPU.</li></ul>")

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
        icon = resource_path(os.path.join("assets", "icon.png")).replace("\\", "/")
        return (
            f"<table><tr><td><img src='file://{icon}' width='64' height='64'></td>"
            "<td>&nbsp;&nbsp;</td><td><h2>Lokaler LLM-Benchmark</h2>"
            f"<span class='lead'>Version {VERSION} · MIT-Lizenz · von Marcel Räuber</span></td></tr></table>"
            "<p>Misst Geschwindigkeit (Prefill, Decode, Time-to-First-Token) und eine einfache "
            "Qualitätsprüfung lokaler KI-Modelle über Ollama – um Hardware zu vergleichen:</p>"
            f"<p style='font-size:13pt'><b style='color:{TEAL}'>GPU-PC</b> &nbsp;·&nbsp; "
            f"<b style='color:{BLUE}'>Apple-Silicon-Mac</b> &nbsp;·&nbsp; "
            f"<b style='color:{AMBER}'>CPU&nbsp;+&nbsp;viel RAM</b></p>"
            "<h3>Die Kernidee</h3>"
            "<p>Genauigkeit hängt am <b>Modell</b>, nicht an der Hardware. Die Hardware-Frage ist "
            "deshalb <b>Tempo + Preis + Speicher + Energie</b>.</p>"
            "<p><a href='https://github.com/MarcelDIY/Benchmark'>github.com/MarcelDIY/Benchmark</a></p>")


# ================================================================== Fenster =====
class MainWindow(QMainWindow):
    IDLE, SCANNING, RUNNING = "idle", "scanning", "running"
    METRICS = [("Decode (t/s)", "reps_decode", "decode_toks", 1),
               ("Prefill (t/s)", "reps_prefill", "prefill_toks", 0),
               ("TTFT (ms)", "reps_ttft", "ttft_ms", 0)]
    CMP_METRICS = [("Decode (t/s)", "decode", 1, "höher = besser"),
                   ("Prefill (t/s)", "prefill", 0, "höher = besser"),
                   ("TTFT (ms)", "ttft", 0, "niedriger = besser"),
                   ("Decode p95 (t/s)", "decode_p95", 1, "höher = besser · Konsistenz"),
                   ("Qualität (%)", "qual_pct", 0, "höher = besser"),
                   ("Kaltstart (s)", "kaltstart", 1, "niedriger = besser · Modell-Ladezeit"),
                   ("Speicherbedarf (GB)", "groesse", 1, "kleiner = passt eher in den VRAM"),
                   ("Gesamtdauer (s)", "dauer", 0, "niedriger = besser · ganzer Lauf"),
                   ("GPU-Anteil (%)", "gpu_pct", 0, "Anteil des Modells im VRAM")]
    CMP_COLS = ["Modell", "Modus", "Label", "Decode", "Prefill", "TTFT", "Dec p95",
                "GPU%", "Qual", "Kaltstart", "Größe (GB)", "Dauer (s)"]
    # Pro Wert-Spalte: (rec-Schlüssel zum Vergleichen, höher_ist_besser, Tooltip-Hinweis).
    # Der beste Wert je Spalte wird unter den lokalen Läufen hervorgehoben.
    CMP_BEST = {
        3:  ("decode",     True,  "höher = besser"),
        4:  ("prefill",    True,  "höher = besser"),
        5:  ("ttft",       False, "niedriger = besser"),
        6:  ("decode_p95", True,  "höher = besser · Konsistenz"),
        7:  ("gpu_pct",    True,  "höher = mehr im VRAM"),
        8:  ("qual_pct",   True,  "höher = besser"),
        9:  ("kaltstart",  False, "niedriger = besser · Modell-Ladezeit"),
        10: ("groesse",    False, "kleiner = passt eher in den VRAM"),
        11: ("dauer",      False, "niedriger = besser · ganzer Lauf"),
    }

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Lokaler LLM-Benchmark")
        _icon = QIconSafe()
        if _icon:
            self.setWindowIcon(_icon)
        scr = QApplication.primaryScreen().availableGeometry()
        self.resize(min(1060, int(scr.width() * 0.94)), min(880, int(scr.height() * 0.94)))
        self.setMinimumSize(780, 520)

        self._thread = None
        self._worker = None
        self._last_payload = None
        self._details = {}
        self._runs = []          # gesammelte Läufe für den Vergleich
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

        # Ergebnisse: Reiter "Aktueller Lauf" + "Vergleich"
        res_box = QGroupBox("Ergebnisse")
        res = QVBoxLayout(res_box)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_run_tab(), "Aktueller Lauf")
        self.tabs.addTab(self._build_cmp_tab(), "Vergleich (0)")
        res.addWidget(self.tabs)

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

    def _build_run_tab(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(2, 8, 2, 2)
        kpi = QHBoxLayout()
        kpi.setSpacing(8)
        self.tile_decode = StatTile("Decode Ø (t/s)")
        self.tile_prefill = StatTile("Prefill Ø (t/s)")
        self.tile_ttft = StatTile("TTFT (ms)")
        self.tile_qual = StatTile("Qualität", GREEN)
        for t in (self.tile_decode, self.tile_prefill, self.tile_ttft, self.tile_qual):
            kpi.addWidget(t, 1)
        lay.addLayout(kpi)

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
        self.table.setMinimumHeight(140)
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
        self.donut = SvgView(minh=132)
        self.donut.setMaximumHeight(150)
        rl.addWidget(self.donut)
        mrow = QHBoxLayout()
        mrow.addWidget(self._titled("Läufe je Aufgabe"))
        mrow.addStretch(1)
        self.metric_combo = QComboBox()
        self.metric_combo.addItems([m[0] for m in self.METRICS])
        self.metric_combo.currentIndexChanged.connect(lambda _i: self._update_charts())
        mrow.addWidget(self.metric_combo)
        rl.addLayout(mrow)
        self.runs_view = SvgView(minh=160)
        rl.addWidget(self.runs_view, 1)
        split.addWidget(right)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        split.setSizes([560, 430])
        lay.addWidget(split, 1)
        return page

    def _build_cmp_tab(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(2, 8, 2, 2)
        top = QHBoxLayout()
        top.addWidget(QLabel("Kennzahl:"))
        self.cmp_combo = QComboBox()
        self.cmp_combo.addItems([m[0] for m in self.CMP_METRICS])
        self.cmp_combo.currentIndexChanged.connect(lambda _i: self._refresh_compare())
        top.addWidget(self.cmp_combo)
        top.addStretch(1)
        self.ref_btn = QPushButton("☁ Cloud-Referenz einblenden")
        self.ref_btn.setToolTip("Richtwerte für Claude Opus/Sonnet/Haiku einblenden.\n"
                                "Tempo ca. (Anbieter-Server, nicht deine Hardware); Qualität gemessen.")
        self.ref_btn.clicked.connect(self.on_toggle_reference)
        top.addWidget(self.ref_btn)
        self.import_btn = QPushButton("📥 Lauf laden")
        self.import_btn.setToolTip("Exportierte JSON-Ergebnisse (auch von anderen Rechnern) "
                                   "laden und in den Vergleich aufnehmen.")
        self.import_btn.clicked.connect(self.on_import_runs)
        top.addWidget(self.import_btn)
        self.clear_runs_btn = QPushButton("Läufe zurücksetzen")
        self.clear_runs_btn.clicked.connect(self.on_clear_runs)
        top.addWidget(self.clear_runs_btn)
        lay.addLayout(top)

        # Diagramm und Tabelle in einen verstellbaren Splitter – so kann die Tabelle
        # größer gezogen werden, um alle Läufe ohne Scrollen zu sehen.
        cmp_split = QSplitter(Qt.Vertical)
        self.cmp_view = SvgView(minh=140)
        cmp_split.addWidget(self.cmp_view)
        self.cmp_table = QTableWidget(0, len(self.CMP_COLS))
        self.cmp_table.setHorizontalHeaderLabels(self.CMP_COLS)
        for c, (_k, _hi, _hint) in self.CMP_BEST.items():
            hdr = self.cmp_table.horizontalHeaderItem(c)
            if hdr:
                hdr.setToolTip(_hint)
        self.cmp_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for i in range(1, len(self.CMP_COLS)):
            self.cmp_table.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeToContents)
        self.cmp_table.verticalHeader().setVisible(False)
        self.cmp_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.cmp_table.setMinimumHeight(120)
        cmp_split.addWidget(self.cmp_table)
        cmp_split.setStretchFactor(0, 1)
        cmp_split.setStretchFactor(1, 1)
        cmp_split.setSizes([240, 320])
        lay.addWidget(cmp_split, 1)
        note = QLabel("☁ = Cloud-Referenz (Tempo ca., nicht auf deiner Hardware gemessen, "
                      "Qualität gemessen). ⚠ = Messung wahrscheinlich fehlerhaft "
                      "(zählt nicht beim Bestwert; Maus drüber für Details). "
                      "Grün/fett = bester Wert. Starte mehrere Modelle, um Läufe zu sammeln.")
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{TXT2};font-size:9pt;")
        lay.addWidget(note)
        self._refresh_compare()
        return page

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
        self.clear_runs_btn.setEnabled(idle and bool(self._runs))
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
        self.donut.set_gen(lambda w, h: SC.donut(None, None, None, w, h))
        self.runs_view.set_gen(None)
        for t in (self.tile_decode, self.tile_prefill, self.tile_ttft, self.tile_qual):
            t.set("–")
        self._last_payload = None
        self.tabs.setCurrentIndex(0)

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
        if ok:
            self._add_run(payload)
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
        if not pl or pl.get("gpu_pct") is None:
            self.donut.set_gen(lambda w, h: SC.donut(None, None, None, w, h))
            return
        gp, vram, total = pl["gpu_pct"], pl.get("vram_mb"), pl.get("total_mb")
        self.donut.set_gen(lambda w, h: SC.donut(gp, vram, total, w, h))

    # ---- Lauf-Diagramm (aktueller Lauf) ----
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
        name, reps_key, warm_key, dec = self.METRICS[self.metric_combo.currentIndex()]
        detail = self._details.get(tid)
        if not detail:
            self.runs_view.set_gen(None)
            return
        bars = []
        warm = detail.get("warmup")
        if warm and warm.get(warm_key) is not None:
            bars.append(("Warmup", warm[warm_key], True))
        for i, v in enumerate(detail.get(reps_key, []) or []):
            bars.append((f"#{i + 1}", v, False))
        valid = [v for _, v, w in bars if (not w) and v is not None]
        avg = statistics.mean(valid) if valid else None
        cap = f"{friendly(tid)} – {name}"
        self.runs_view.set_gen(lambda w, h: SC.runs(bars, avg, dec, cap, w, h))

    # ---- Vergleich ----
    def _add_run(self, payload):
        rows = payload.get("rows") or []
        g = next((r for r in rows if r.get("task") == "GESAMT"), None) or (rows[0] if rows else None)
        if not g:
            return
        cfg = payload.get("config", {})
        cold = payload.get("cold_start_ms")
        pl = payload.get("placement", {}) or {}
        imported = bool(payload.get("imported"))
        label = payload.get("label", "")
        model = cfg.get("model", "?")
        # Hinter dem @ steht das Label (Rechner) – besser zuordenbar als gpu/cpu.
        name = f"{model} @ {label}" if label else f"{model} @ {cfg.get('mode', '?')}"
        rec = {
            "name": name,
            "model": cfg.get("model", "?"), "mode": cfg.get("mode", "?"),
            "label": label,
            "decode": _num(g.get("decode_toks_med")),
            "prefill": _num(g.get("prefill_toks_med")),
            "ttft": _num(g.get("ttft_ms_med")),
            "decode_p95": _num(g.get("decode_toks_p95")),
            "gpu_pct": cfg.get("gpu_pct"),
            "quality": g.get("quality") or "",
            "qual_pct": _pct(g.get("quality")),
            "kaltstart": (round(cold / 1000, 1) if cold else None),
            "groesse": pl.get("total_mb"),
            "dauer": payload.get("total_wall_s"),
            "is_reference": False,
            "imported": imported,
        }
        self._runs.append(rec)
        self.tabs.setTabText(1, f"Vergleich ({len(self._runs)})")
        self._refresh_compare()

    def on_import_runs(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Ergebnisse laden", default_output_dir(), "JSON (*.json)")
        if not paths:
            return
        added, errors = 0, []
        for path in paths:
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                if not data.get("rows"):
                    raise ValueError("keine Messdaten (rows) enthalten")
                # JSON-Export in ein _add_run-Payload überführen. Ältere Exporte ohne
                # placement/cold_start_ms/total_wall_s laden trotzdem (Werte dann „–“).
                payload = {
                    "rows": data["rows"],
                    "config": data.get("config", {}),
                    "label": data.get("label", os.path.splitext(os.path.basename(path))[0]),
                    "placement": data.get("placement", {}) or {},
                    "cold_start_ms": data.get("cold_start_ms"),
                    "total_wall_s": data.get("total_wall_s"),
                    "imported": True,
                }
                before = len(self._runs)
                self._add_run(payload)
                if len(self._runs) > before:
                    added += 1
            except Exception as e:
                errors.append(f"{os.path.basename(path)}: {e}")
        if added:
            self.clear_runs_btn.setEnabled(True)
            self.statusBar().showMessage(f"{added} Lauf/Läufe geladen.")
        if errors:
            QMessageBox.warning(self, "Teilweise nicht geladen",
                                "Konnte nicht laden:\n" + "\n".join(errors))

    def on_clear_runs(self):
        if not self._runs:
            return
        self._runs.clear()
        self.ref_btn.setText("☁ Cloud-Referenz einblenden")
        self.tabs.setTabText(1, "Vergleich (0)")
        self._refresh_compare()
        self._set_state(self._state)

    def on_toggle_reference(self):
        if any(r.get("is_reference") for r in self._runs):
            self._runs = [r for r in self._runs if not r.get("is_reference")]
            self.ref_btn.setText("☁ Cloud-Referenz einblenden")
        else:
            self._runs.extend(self._load_reference())
            self.ref_btn.setText("☁ Cloud-Referenz ausblenden")
        self.tabs.setTabText(1, f"Vergleich ({len(self._runs)})")
        self._refresh_compare()
        if self._state == self.IDLE:
            self.clear_runs_btn.setEnabled(bool(self._runs))

    def _load_reference(self):
        try:
            with open(resource_path("reference_cloud.json"), encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return []
        out = []
        for m in data.get("models", []):
            out.append({
                "name": m.get("name", m.get("model", "?")),
                "model": m.get("model", "?"), "mode": "cloud", "label": "Referenz",
                "decode": m.get("decode"), "prefill": m.get("prefill"),
                "ttft": m.get("ttft"), "decode_p95": m.get("decode_p95"),
                "gpu_pct": None, "quality": m.get("quality", ""),
                "qual_pct": m.get("qual_pct"), "kaltstart": m.get("kaltstart"),
                "groesse": m.get("groesse"), "dauer": m.get("dauer"),
                "is_reference": True,
            })
        return out

    @staticmethod
    def _run_warning(rec):
        """Gibt einen Hinweistext zurück, wenn die Messung wahrscheinlich fehlerhaft ist,
        sonst None. Referenzwerte werden nie als fehlerhaft markiert."""
        if rec.get("is_reference"):
            return None
        reasons = []
        q = rec.get("qual_pct")
        if q is not None and q == 0:
            reasons.append("Qualität 0 % – keine der prüfbaren Aufgaben bestanden")
        g = rec.get("gpu_pct")
        dec = rec.get("decode")
        if g == 0 and dec is not None and dec > 40:
            reasons.append("0 % GPU bei hohem Decode-Tempo – Platzierung/Messung unplausibel")
        if not reasons:
            return None
        return "Messung wahrscheinlich fehlerhaft – bitte wiederholen.\n• " + "\n• ".join(reasons)

    def _refresh_compare(self):
        name, key, dec, hint = self.CMP_METRICS[self.cmp_combo.currentIndex()]
        items = []
        for i, rec in enumerate(self._runs):
            v = rec.get(key)
            if v is None:
                continue
            if key == "groesse":
                v = v / 1000  # in der Tabelle wie im Diagramm in GB anzeigen
            col = CYAN if rec.get("is_reference") else SC.CYCLE[i % len(SC.CYCLE)]
            nm = ("⚠ " + rec["name"]) if self._run_warning(rec) else rec["name"]
            items.append((nm, float(v), col))
        cap = f"Modell-Vergleich – {name}"
        self.cmp_view.set_gen(lambda w, h: SC.compare(items, dec, hint, cap, w, h))
        # Tabelle
        self.cmp_table.setRowCount(0)
        # Bester Wert je Kennzahl-Spalte – nur lokale Läufe (Cloud-Referenz ist Zielwert,
        # kein Konkurrent). Nur markieren, wenn mind. zwei Läufe vergleichbar sind.
        # Fehlerhafte Läufe nehmen NICHT am Bestwert-Vergleich teil (sonst „gewinnt"
        # eine kaputte Messung).
        local = [rec for rec in self._runs
                 if not rec.get("is_reference") and not self._run_warning(rec)]
        best = {}
        for c, (key, higher, _hint) in self.CMP_BEST.items():
            nums = [_num(rec.get(key)) for rec in local]
            nums = [v for v in nums if v is not None]
            if len(nums) >= 2:
                best[c] = max(nums) if higher else min(nums)
        for rec in self._runs:
            r = self.cmp_table.rowCount()
            self.cmp_table.insertRow(r)
            warn = self._run_warning(rec)
            model_cell = ("⚠ " + rec["model"]) if warn else rec["model"]
            vals = [model_cell, rec["mode"], rec.get("label", ""),
                    _fmt(rec.get("decode"), 1), _fmt(rec.get("prefill"), 0),
                    _fmt(rec.get("ttft"), 0), _fmt(rec.get("decode_p95"), 1),
                    (f"{rec['gpu_pct']}%" if rec.get("gpu_pct") is not None else "–"),
                    rec.get("quality") or "–",
                    _fmt(rec.get("kaltstart"), 1),
                    _fmt(rec.get("groesse") / 1000 if rec.get("groesse") is not None else None, 1),
                    _fmt(rec.get("dauer"), 0)]
            ref = rec.get("is_reference")
            for c, val in enumerate(vals):
                item = QTableWidgetItem(str(val))
                if c >= 3:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if warn:
                    item.setForeground(QColor(AMBER))
                    item.setToolTip(warn)
                elif ref:
                    item.setForeground(QColor(CYAN))
                elif c in best:
                    v = _num(rec.get(self.CMP_BEST[c][0]))
                    if v is not None and abs(v - best[c]) < 1e-9:
                        item.setForeground(QColor(GREEN))
                        f = item.font()
                        f.setBold(True)
                        item.setFont(f)
                        item.setToolTip("bester Wert (" + self.CMP_BEST[c][2] + ")")
                self.cmp_table.setItem(r, c, item)

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
                       "placement": self._last_payload.get("placement", {}),
                       "cold_start_ms": self._last_payload.get("cold_start_ms"),
                       "total_wall_s": self._last_payload.get("total_wall_s"),
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


def _fmt(v, dec):
    return "–" if v is None else f"{v:.{dec}f}"


def QIconSafe():
    from PySide6.QtGui import QIcon
    ic = QIcon(resource_path(os.path.join("assets", "icon.png")))
    return ic if not ic.isNull() else None


_CD = resource_path(os.path.join("assets", "caret-down.png")).replace("\\", "/")
_CU = resource_path(os.path.join("assets", "caret-up.png")).replace("\\", "/")

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
QPushButton:hover {{ border-color: {TEAL}; color: {TEAL}; }}
QPushButton:disabled {{ color: #3b4261; background: #181a26; border-color: #232742; }}
QPushButton#primary {{ background: {TEAL}; color: #0e1018; border: none; font-weight: 700; }}
QPushButton#primary:hover {{ background: #8ee6d8; }}
QPushButton#primary:disabled {{ background: #2c4a45; color: #5e7a75; }}
QPushButton#link {{ background: transparent; border: none; color: {TEAL}; text-align: left; padding: 2px; }}
QPushButton#link:hover {{ color: {CYAN}; }}
QLineEdit, QComboBox, QSpinBox {{
    background: {INPUT}; border: 1px solid {BORDER}; border-radius: 8px; padding: 6px 9px; color: {TXT};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{ border: 1px solid {TEAL}; }}
QComboBox::drop-down {{ subcontrol-origin: padding; subcontrol-position: center right;
    width: 22px; border: none; }}
QComboBox::down-arrow {{ image: url({_CD}); width: 13px; height: 13px; }}
QComboBox QAbstractItemView {{ background: {INPUT}; color: {TXT}; border: 1px solid {BORDER};
    selection-background-color: {BLUE}; selection-color: #0e1018; outline: none; }}
QSpinBox::up-button {{ subcontrol-origin: border; subcontrol-position: top right; width: 18px;
    border-left: 1px solid {BORDER}; border-top-right-radius: 8px; background: {INPUT}; }}
QSpinBox::down-button {{ subcontrol-origin: border; subcontrol-position: bottom right; width: 18px;
    border-left: 1px solid {BORDER}; border-bottom-right-radius: 8px; background: {INPUT}; }}
QSpinBox::up-button:hover, QSpinBox::down-button:hover {{ background: {BORDER}; }}
QSpinBox::up-arrow {{ image: url({_CU}); width: 11px; height: 11px; }}
QSpinBox::down-arrow {{ image: url({_CD}); width: 11px; height: 11px; }}
QProgressBar {{ background: {INPUT}; border: none; border-radius: 7px; min-height: 12px; }}
QProgressBar::chunk {{ background: {TEAL}; border-radius: 7px; }}
QFrame#tile {{ background: {INPUT}; border: 1px solid {BORDER}; border-radius: 10px; }}
QTableWidget {{
    background: {CARD}; border: 1px solid {BORDER}; border-radius: 8px;
    gridline-color: {BORDER}; alternate-background-color: #1d1f2e;
    selection-background-color: #283a57; selection-color: {TXT};
}}
QTableWidget::item {{ padding: 5px; }}
QHeaderView::section {{
    background: {INPUT}; color: {TXT2}; border: none; border-bottom: 2px solid {BORDER};
    padding: 7px; font-weight: 600;
}}
QTableCornerButton::section {{ background: {INPUT}; border: none; }}
QTextBrowser {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 8px; color: {TXT}; }}
QTabWidget::pane {{ border: 1px solid {BORDER}; border-radius: 8px; top: -1px; }}
QTabBar::tab {{
    background: {INPUT}; color: {TXT2}; padding: 7px 18px;
    border-top-left-radius: 8px; border-top-right-radius: 8px; margin-right: 3px;
}}
QTabBar::tab:selected {{ background: {TEAL}; color: #0e1018; font-weight: 700; }}
QTabBar::tab:hover:!selected {{ color: {TXT}; }}
QMenuBar {{ background: {CARD}; color: {TXT}; border-bottom: 1px solid {BORDER}; }}
QMenuBar::item {{ padding: 6px 12px; background: transparent; }}
QMenuBar::item:selected {{ background: {INPUT}; }}
QMenu {{ background: {CARD}; color: {TXT}; border: 1px solid {BORDER}; }}
QMenu::item:selected {{ background: {INPUT}; }}
QStatusBar {{ background: {CARD}; color: {TXT2}; }}
QScrollBar:vertical {{ background: {BG}; width: 11px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 5px; min-height: 24px; }}
QScrollBar::handle:vertical:hover {{ background: #3b4261; }}
QScrollBar:horizontal {{ background: {BG}; height: 11px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: {BORDER}; border-radius: 5px; min-width: 24px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QToolTip {{ background: {INPUT}; color: {TXT}; border: 1px solid {BORDER}; padding: 6px; }}
"""


def apply_theme(app):
    """Erzwingt ein dunkles Theme (Fusion + dunkle Palette + Stylesheet), damit die
    App auf JEDEM System (auch hell-themed) und in Screenshots durchgehend dunkel ist."""
    from PySide6.QtGui import QPalette
    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(BG))
    pal.setColor(QPalette.WindowText, QColor(TXT))
    pal.setColor(QPalette.Base, QColor(INPUT))
    pal.setColor(QPalette.AlternateBase, QColor(CARD))
    pal.setColor(QPalette.Text, QColor(TXT))
    pal.setColor(QPalette.Button, QColor(INPUT))
    pal.setColor(QPalette.ButtonText, QColor(TXT))
    pal.setColor(QPalette.ToolTipBase, QColor(INPUT))
    pal.setColor(QPalette.ToolTipText, QColor(TXT))
    pal.setColor(QPalette.Highlight, QColor(BLUE))
    pal.setColor(QPalette.HighlightedText, QColor(BG))
    pal.setColor(QPalette.PlaceholderText, QColor(TXT2))
    pal.setColor(QPalette.Disabled, QPalette.Text, QColor("#3b4261"))
    pal.setColor(QPalette.Disabled, QPalette.WindowText, QColor("#3b4261"))
    app.setPalette(pal)
    app.setStyleSheet(STYLESHEET)
    ic = QIconSafe()
    if ic:
        app.setWindowIcon(ic)


def main():
    if "--selftest" in sys.argv:
        with open(resource_path("tasks.json"), encoding="utf-8") as f:
            n = len(json.load(f).get("tasks", []))
        print(f"selftest OK: tasks.json gefunden, {n} Aufgaben, "
              f"frozen={getattr(sys, 'frozen', False)}")
        return
    app = QApplication(sys.argv)
    app.setApplicationName("LLM-Benchmark")
    apply_theme(app)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
