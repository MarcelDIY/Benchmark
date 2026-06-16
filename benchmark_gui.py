#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Standalone-GUI fuer den lokalen Buero-LLM-Hardware-Benchmark.

Ein PySide6-Frontend fuer bench.py: Ollama-Host eingeben, mit "Modelle suchen"
die lokal installierten Modelle ins Dropdown laden, eines auswaehlen, den Test
durchlaufen lassen (alle Buero-Aufgaben), das Ergebnis als Tabelle ansehen und
als CSV / Markdown / JSON exportieren.

Voraussetzung zur Laufzeit: ein laufendes Ollama (Standard http://localhost:11434).
Ollama selbst wird NICHT mitgebuendelt -- es ist eine externe Voraussetzung.

Die eigentliche Messung kommt unveraendert aus bench.py (gleiche Zahlen wie das CLI).
Laeuft auf Windows, macOS und Linux; mit PyInstaller als Standalone baubar
(siehe BenchGUI.spec / packaging/).
"""
import html
import json
import os
import platform
import sys
import threading
from datetime import datetime, timezone

from PySide6.QtCore import QObject, QThread, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QPlainTextEdit, QProgressBar, QPushButton, QSpinBox, QTableWidget,
    QTableWidgetItem, QTextBrowser, QVBoxLayout, QWidget,
)

import bench  # Mess-Logik (run_once, agg, installed_models, system_info, _write_*, ...)


# --------------------------------------------------------- Pfade (auch frozen) --
def resource_path(rel):
    """Pfad zu GEBUENDELTEN read-only-Ressourcen (tasks.json) -- Dev und PyInstaller."""
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, rel)


def default_output_dir():
    """Beschreibbarer Ordner fuer Exporte (neben der App / dem Skript)."""
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
        # macOS: sys.executable liegt in BenchGUI.app/Contents/MacOS -> aus dem
        # Bundle heraus, damit "results" NEBEN dem .app landet (nicht darin).
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
    """Label fuer Dateinamen saeubern (Doppelpunkt/Slash/Leerzeichen -> _)."""
    out = label or "rechner"
    for ch in ' \t/\\:':
        out = out.replace(ch, "_")
    return out or "rechner"


# Spalten der Ergebnistabelle: (Schluessel in der Summary-Zeile, sichtbares Label).
TABLE_COLS = [
    ("task", "Task"),
    ("ttft_ms_med", "TTFT med (ms)"),
    ("prefill_toks_med", "Prefill med (t/s)"),
    ("decode_toks_med", "Decode med (t/s)"),
    ("decode_toks_p95", "Decode p95 (t/s)"),
    ("quality", "Qualitaet"),
]


# ------------------------------------------------------------------- Worker -----
class ScanWorker(QObject):
    """Prueft kurz, ob Ollama erreichbar ist, und holt die installierten Modelle."""

    done = Signal(bool, object, str)  # erreichbar, list[str] modelle, statustext

    def __init__(self, host):
        super().__init__()
        self.host = host

    @Slot()
    def run(self):
        try:
            bench.OLLAMA = self.host  # Modul-Global wird zur Aufrufzeit gelesen
            up = bench.ollama_up()
            if not up:
                self.done.emit(False, [], f"Ollama NICHT erreichbar unter {self.host}")
                return
            models = bench.installed_models(timeout=6)  # kurz halten: Schliessen darf nicht haengen
            msg = (f"Ollama erreichbar - {len(models)} Modell(e) gefunden"
                   if models else "Ollama erreichbar, aber keine Modelle installiert")
            self.done.emit(True, models, msg)
        except Exception as e:  # pragma: no cover - defensiv
            self.done.emit(False, [], f"Fehler beim Scan: {e}")


class BenchWorker(QObject):
    """Faehrt den kompletten Benchmark fuer EIN Modell + EINEN Modus durch.

    Laeuft in einem eigenen Thread. Beruehrt NIE ein Widget -- jede Ausgabe geht
    ausschliesslich ueber Signale an den GUI-Thread.
    """

    log = Signal(str)
    progress = Signal(object)   # dict: done, total, task, task_idx, task_total, rep, rep_total
    task_row = Signal(object)   # dict: eine fertige Summary-Zeile
    finished = Signal(bool, str, object)  # ok, statustext, payload-dict

    def __init__(self, host, model, mode, reps, warmup, label, tasks, sys_info):
        super().__init__()
        self.host = host
        self.model = model
        self.mode = mode
        self.reps = reps
        self.warmup = warmup
        self.label = label
        self.tasks = tasks
        self.sys_info = sys_info
        self._cancel = threading.Event()
        self._active_resp = None  # offene HTTP-Antwort des laufenden run_once

    def request_cancel(self):
        """Aus dem GUI-Thread: Flag setzen UND eine offene Antwort schliessen.

        Das Schliessen bricht den blockierenden Stream-Read in run_once auf --
        so wirkt der Abbruch auch waehrend Modell-Load/Prefill (kein Token-Fluss),
        nicht erst zwischen den Wiederholungen.
        """
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
            bench.OLLAMA = self.host  # Host im Worker-Thread setzen, vor jedem HTTP-Call
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

            self.log.emit(f"Start: {model} | {mode} | {len(tasks)} Tasks x {reps} Reps "
                          f"(+{warmup} Warmup)")

            for ti, task in enumerate(tasks):
                if self._cancel.is_set():
                    break
                tid = task["id"]
                self.log.emit(f"Task {ti + 1}/{len(tasks)}  {tid}")
                self._emit_progress(done, total, tid, ti + 1, len(tasks), 0, reps)

                # Warmup (laedt Modell, nicht gewertet)
                for w in range(warmup):
                    if self._cancel.is_set():
                        break
                    try:
                        bench.run_once(model, task["prompt"], 16,
                                       task.get("num_ctx", 4096), num_gpu,
                                       rep=-1 - w, should_cancel=self._cancel.is_set,
                                       on_response=self._set_resp)
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
                        self.log.emit(f"  Fehler (uebersprungen): {e}")
                        continue
                    if self._cancel.is_set():
                        break  # abgebrochener Rep wird nicht gewertet
                    q = bench.quality_check(task, r["text"])
                    samples.append(r)
                    done += 1
                    self._emit_progress(done, total, tid, ti + 1, len(tasks), rep + 1, reps)
                    self.log.emit(
                        f"  rep{rep}: TTFT {bench._f(r['ttft_ms'], 0)} ms | "
                        f"prefill {bench._f(r['prefill_toks'], 1)} t/s | "
                        f"decode {bench._f(r['decode_toks'], 1)} t/s"
                        + ("" if q is None else f" | qual {'ok' if q else 'FAIL'}"))

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
                self.task_row.emit(row)

                comb["ttft"] += [s["ttft_ms"] for s in samples]
                comb["prefill"] += [s["prefill_toks"] for s in samples]
                comb["decode"] += [s["decode_toks"] for s in samples]
                comb["qual"] += quals

            # GESAMT-Zeile nur bei vollstaendigem Lauf (nicht abgebrochen) -- sonst
            # taeuschte sie eine Aggregation ueber ALLE Tasks vor. Echte cross-task-
            # Aggregation der Rohwerte.
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
                self.task_row.emit(gesamt)

            # Tatsaechliche GPU/CPU-Verteilung des geladenen Modells abfragen.
            placement = self._placement(model) if sum_rows else {"gpu_pct": None}

            # ok nur, wenn nicht abgebrochen UND tatsaechlich Messwerte entstanden.
            ok = (not cancelled) and bool(sum_rows)
            if cancelled:
                msg = "abgebrochen"
            elif not sum_rows:
                msg = "ohne Messwerte (Ollama/Modell pruefen)"
            else:
                msg = "fertig"
            payload = {
                "rows": sum_rows,
                "sys_info": self.sys_info,
                "label": self.label,
                "placement": placement,
                "config": {
                    "model": model, "mode": mode, "reps": reps, "warmup": warmup,
                    "tasks": [t["id"] for t in tasks], "ollama": self.host,
                    "aborted": cancelled, "gpu_pct": placement.get("gpu_pct"),
                },
            }
            self.finished.emit(ok, msg, payload)
        except Exception as e:  # pragma: no cover - defensiv
            self.finished.emit(False, f"Fehler: {e}", {})

    def _placement(self, model):
        """Tatsaechliche GPU/CPU-Verteilung des geladenen Modells via Ollama /api/ps.

        Liefert {gpu_pct, vram_mb, total_mb}. gpu_pct = Anteil des Modells im VRAM
        (100 = komplett GPU, 0 = komplett CPU, dazwischen = Hybrid). None, wenn
        nicht ermittelbar (Modell schon entladen o. ae.).
        """
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
        self.progress.emit({
            "done": done, "total": total, "task": tid,
            "task_idx": ti, "task_total": tt, "rep": rep, "rep_total": rep_total,
        })


# ----------------------------------------------------------------- Fenster ------
class MainWindow(QMainWindow):
    IDLE, SCANNING, RUNNING = "idle", "scanning", "running"

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Lokaler LLM-Benchmark (Ollama)")
        self.resize(820, 760)
        _icon = QIcon(resource_path(os.path.join("assets", "icon.png")))
        if not _icon.isNull():
            self.setWindowIcon(_icon)

        self._thread = None
        self._worker = None
        self._last_payload = None
        self.sys_info = bench.system_info()
        self.tasks = self._load_tasks()

        self._build_ui()
        self._set_state(self.IDLE)
        self._auto_scan_on_start()

    # ---- Konfiguration ----
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

    # ---- UI-Aufbau ----
    def _build_ui(self):
        central = QWidget()
        root = QVBoxLayout(central)

        # Verbindung
        conn_box = QGroupBox("Verbindung")
        conn = QVBoxLayout(conn_box)
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Ollama-Host:"))
        self.host_edit = QLineEdit(os.environ.get("OLLAMA_HOST", "http://localhost:11434"))
        self.host_edit.setToolTip(
            "Adresse, unter der Ollama laeuft und die Modelle bereitstellt.\n"
            "Eigener Rechner: http://localhost:11434\n"
            "Anderer Rechner im Netz (misst DESSEN Hardware): http://<ip>:11434")
        row1.addWidget(self.host_edit, 1)
        self.scan_btn = QPushButton("Modelle suchen")
        self.scan_btn.setToolTip("Prueft, ob Ollama erreichbar ist, und fuellt das Dropdown\n"
                                 "mit den dort installierten Modellen.")
        self.scan_btn.clicked.connect(self.on_scan)
        row1.addWidget(self.scan_btn)
        conn.addLayout(row1)
        self.status_label = QLabel("Noch nicht gescannt.")
        conn.addWidget(self.status_label)
        root.addWidget(conn_box)

        # Parameter
        par_box = QGroupBox("Parameter")
        form = QFormLayout(par_box)
        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(260)
        self.model_combo.setToolTip("Eines der in Ollama installierten Modelle "
                                    "(per \"Modelle suchen\" geladen).")
        form.addRow("Modell:", self.model_combo)
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["gpu", "cpu"])
        self.mode_combo.setToolTip(
            "Wo gerechnet wird (Vorgabe an Ollama):\n"
            "gpu = GPU nutzen; passt das Modell nicht in den VRAM, wird ein Teil\n"
            "      automatisch auf die CPU ausgelagert (Hybrid).\n"
            "cpu = erzwingt reine CPU (ohne Grafikkarte).\n"
            "Die tatsaechliche GPU/CPU-Verteilung wird nach dem Lauf angezeigt.")
        form.addRow("Modus:", self.mode_combo)
        self.reps_spin = QSpinBox()
        self.reps_spin.setRange(1, 50)
        self.reps_spin.setValue(int(self._cfg.get("reps", 5)) if hasattr(self, "_cfg") else 5)
        self.reps_spin.setToolTip("Anzahl gewerteter Messungen pro Aufgabe.\n"
                                  "Mehr = stabiler (Median + p95 statt Zufallswert).")
        form.addRow("Wiederholungen:", self.reps_spin)
        self.warmup_spin = QSpinBox()
        self.warmup_spin.setRange(0, 5)
        self.warmup_spin.setValue(int(self._cfg.get("warmup", 1)) if hasattr(self, "_cfg") else 1)
        self.warmup_spin.setToolTip("Nicht gewertete Vorlaeufe, die das Modell laden.\n"
                                    "Der Kaltstart ist viel langsamer und wuerde sonst die Messung verfaelschen.")
        form.addRow("Warmup:", self.warmup_spin)
        self.label_edit = QLineEdit(platform.node() or "rechner")
        self.label_edit.setToolTip("Nur ein Etikett fuer die Ergebnisse/Exportdateien -\n"
                                   "praktisch beim Vergleich mehrerer Geraete (z. B. laptop-i9, mac-m4).")
        form.addRow("Label (Maschinenname):", self.label_edit)

        btn_row = QHBoxLayout()
        self.info_btn = QPushButton("Aufgaben & Infos")
        self.info_btn.setToolTip("Zeigt, welche Aufgaben getestet werden (inkl. Prompt-Inhalt)\n"
                                 "und was gemessen wird.")
        self.info_btn.clicked.connect(self.show_tasks_info)
        self.start_btn = QPushButton("Test starten")
        self.start_btn.clicked.connect(self.on_start)
        self.cancel_btn = QPushButton("Abbrechen")
        self.cancel_btn.clicked.connect(self.on_cancel)
        btn_row.addWidget(self.info_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(self.start_btn)
        btn_row.addWidget(self.cancel_btn)
        form.addRow(btn_row)
        root.addWidget(par_box)

        # Fortschritt
        prog_box = QGroupBox("Fortschritt")
        prog = QVBoxLayout(prog_box)
        self.prog_label = QLabel("-")
        prog.addWidget(self.prog_label)
        self.prog_bar = QProgressBar()
        self.prog_bar.setValue(0)
        prog.addWidget(self.prog_bar)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(2000)
        self.log_view.setMinimumHeight(150)
        prog.addWidget(self.log_view)
        root.addWidget(prog_box, 1)

        # Ergebnisse
        res_box = QGroupBox("Ergebnisse")
        res = QVBoxLayout(res_box)
        self.table = QTableWidget(0, len(TABLE_COLS))
        self.table.setHorizontalHeaderLabels([c[1] for c in TABLE_COLS])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for i in range(1, len(TABLE_COLS)):
            self.table.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeToContents)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        res.addWidget(self.table)

        self.placement_label = QLabel("")
        self.placement_label.setToolTip("Tatsaechliche GPU/CPU-Verteilung des Modells "
                                        "waehrend des Laufs (aus Ollama /api/ps).")
        self.placement_label.setStyleSheet("color: #2b6; font-weight: bold;")
        res.addWidget(self.placement_label)

        exp_row = QHBoxLayout()
        exp_row.addStretch(1)
        self.export_csv_btn = QPushButton("Export CSV")
        self.export_csv_btn.clicked.connect(lambda: self.on_export("csv"))
        self.export_md_btn = QPushButton("Export Markdown")
        self.export_md_btn.clicked.connect(lambda: self.on_export("md"))
        self.export_json_btn = QPushButton("Export JSON")
        self.export_json_btn.clicked.connect(lambda: self.on_export("json"))
        exp_row.addWidget(self.export_csv_btn)
        exp_row.addWidget(self.export_md_btn)
        exp_row.addWidget(self.export_json_btn)
        res.addLayout(exp_row)
        root.addWidget(res_box, 1)

        self.setCentralWidget(central)
        self.statusBar().showMessage(
            f"System: {self.sys_info['os']} | {self.sys_info['cpu']} | "
            f"{self.sys_info['ram_gb']} GB RAM")

    # ---- Zustands-Maschine: welche Bedienelemente sind aktiv ----
    def _set_state(self, state):
        self._state = state
        idle = state == self.IDLE
        scanning = state == self.SCANNING
        running = state == self.RUNNING
        has_model = self.model_combo.count() > 0
        has_results = self._last_payload is not None and bool(self._last_payload.get("rows"))

        self.host_edit.setEnabled(idle)
        self.scan_btn.setEnabled(idle)
        self.model_combo.setEnabled(idle and has_model)
        self.mode_combo.setEnabled(idle)
        self.reps_spin.setEnabled(idle)
        self.warmup_spin.setEnabled(idle)
        self.label_edit.setEnabled(idle)
        self.start_btn.setEnabled(idle and has_model)
        self.cancel_btn.setEnabled(running)
        for b in (self.export_csv_btn, self.export_md_btn, self.export_json_btn):
            b.setEnabled(idle and has_results)

        if scanning:
            self.statusBar().showMessage("Scanne Host ...")
        elif running:
            self.statusBar().showMessage("Benchmark laeuft ...")

    # ---- Scan ----
    def _auto_scan_on_start(self):
        # Beim Start automatisch scannen -- aber ERST, wenn die Event-Loop laeuft und
        # das Fenster steht. Den Scan-Thread schon im __init__ (vor app.exec/show()) zu
        # starten, fuehrt auf xcb zu einem Race -> Segfault. singleShot(0) verschiebt
        # den Start auf die erste Event-Loop-Iteration.
        QTimer.singleShot(0, self.on_scan)

    def on_scan(self):
        if self._state != self.IDLE:
            return
        host = normalize_host(self.host_edit.text())
        self.host_edit.setText(host)
        self.status_label.setText("Suche Modelle ...")
        self._set_state(self.SCANNING)

        self._worker = ScanWorker(host)
        self._thread = QThread(self)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.done.connect(self.on_scan_done)
        self._worker.done.connect(self._thread.quit)
        self._worker.done.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    @Slot(bool, object, str)
    def on_scan_done(self, reachable, models, msg):
        self._thread = None
        self._worker = None
        self.status_label.setText(("OK - " if reachable else "FEHLER - ") + msg)
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
            QMessageBox.warning(self, "Keine Aufgaben", "tasks.json enthaelt keine Aufgaben.")
            return
        host = normalize_host(self.host_edit.text())
        self.host_edit.setText(host)
        self.table.setRowCount(0)
        self.log_view.clear()
        self.prog_bar.setValue(0)
        self.prog_label.setText("-")
        self.placement_label.setText("")
        self._last_payload = None

        self._worker = BenchWorker(
            host=host,
            model=self.model_combo.currentText(),
            mode=self.mode_combo.currentText(),
            reps=self.reps_spin.value(),
            warmup=self.warmup_spin.value(),
            label=self.label_edit.text().strip() or "rechner",
            tasks=self.tasks,
            sys_info=self.sys_info,
        )
        self._thread = QThread(self)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.log.connect(self.on_log)
        self._worker.progress.connect(self.on_progress)
        self._worker.task_row.connect(self.on_task_row)
        self._worker.finished.connect(self.on_finished)
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._set_state(self.RUNNING)
        self._thread.start()

    def on_cancel(self):
        if self._worker is not None and isinstance(self._worker, BenchWorker):
            self._worker.request_cancel()
            self.cancel_btn.setEnabled(False)
            self.statusBar().showMessage("Breche ab ...")

    @Slot(str)
    def on_log(self, text):
        self.log_view.appendPlainText(text)

    @Slot(object)
    def on_progress(self, d):
        self.prog_bar.setMaximum(max(1, d["total"]))
        self.prog_bar.setValue(d["done"])
        rep = d["rep"]
        rep_txt = f"Wiederholung {rep}/{d['rep_total']}" if rep else "Warmup ..."
        self.prog_label.setText(
            f"Task {d['task_idx']}/{d['task_total']}: {d['task']}   {rep_txt}   "
            f"({d['done']}/{d['total']})")

    @Slot(object)
    def on_task_row(self, row):
        r = self.table.rowCount()
        self.table.insertRow(r)
        is_total = row.get("task") == "GESAMT"
        for c, (key, _label) in enumerate(TABLE_COLS):
            val = row.get(key, "")
            item = QTableWidgetItem("" if val == "" or val is None else str(val))
            if c > 0:
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if is_total:
                f = item.font()
                f.setBold(True)
                item.setFont(f)
            self.table.setItem(r, c, item)

    @Slot(bool, str, object)
    def on_finished(self, ok, msg, payload):
        self._thread = None
        self._worker = None
        self._last_payload = payload if payload else None
        self._set_state(self.IDLE)
        self.statusBar().showMessage(f"Benchmark {msg}.")
        self._show_placement(payload)
        # Warnen, wenn gar keine Messwerte entstanden (echter Ausfall) -- aber nicht
        # bei bewusstem Abbruch ohne Ergebnisse.
        rows = payload.get("rows") if payload else None
        if not rows and msg != "abgebrochen":
            QMessageBox.warning(self, "Kein Ergebnis", msg or "Unbekannter Fehler")

    def _show_placement(self, payload):
        """Zeigt die tatsaechliche GPU/CPU-Verteilung unter der Tabelle an."""
        pl = payload.get("placement") if payload else None
        cfg = payload.get("config") if payload else {}
        if not pl or pl.get("gpu_pct") is None:
            self.placement_label.setText("")
            return
        gp = pl["gpu_pct"]
        if gp >= 99:
            wo = "komplett auf der GPU"
        elif gp <= 1:
            wo = "komplett auf der CPU"
        else:
            wo = f"hybrid: {gp}% GPU / {100 - gp}% CPU"
        extra = (f" - {pl['vram_mb']} von {pl['total_mb']} MB im VRAM"
                 if pl.get("total_mb") else "")
        self.placement_label.setText(
            f"Modell lief {wo} (Modus '{cfg.get('mode', '?')}'){extra}")

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
                obj = {
                    "schema_version": 1,
                    "label": lab,
                    "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "system": info,
                    "config": self._last_payload.get("config", {}),
                    "rows": rows,
                }
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(obj, f, ensure_ascii=False, indent=2)
            self.statusBar().showMessage(f"Exportiert: {path}")
        except Exception as e:
            QMessageBox.critical(self, "Export fehlgeschlagen", str(e))

    # ---- Aufgaben & Infos ----
    def show_tasks_info(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Aufgaben & Infos")
        dlg.resize(740, 620)
        lay = QVBoxLayout(dlg)
        browser = QTextBrowser()
        browser.setOpenExternalLinks(False)
        browser.setHtml(self._tasks_info_html())
        lay.addWidget(browser)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(dlg.reject)
        bb.accepted.connect(dlg.accept)
        lay.addWidget(bb)
        dlg.exec()

    def _tasks_info_html(self):
        def esc(s):
            return html.escape(str(s))

        p = ["<h2>Was misst dieser Benchmark?</h2><ul>"
             "<li><b>Prefill</b> (t/s): Tempo beim Verarbeiten der Eingabe "
             "(rechenlastig, wichtig bei langen Texten).</li>"
             "<li><b>Decode</b> (t/s): Tempo beim Erzeugen der Antwort "
             "(bandbreitenlastig - hier trennen sich GPU und Mac).</li>"
             "<li><b>TTFT</b> (ms): Zeit bis zum ersten Token - die gefuehlte Reaktionszeit.</li>"
             "<li><b>Qualitaet</b>: deterministischer Stichprobentest "
             "(nur bei Aufgaben mit pruefbarer Antwort).</li></ul>"
             "<h3>Begriffe</h3><ul>"
             "<li><b>Modus gpu</b>: Ollama nutzt die GPU automatisch; passt das Modell nicht "
             "in den VRAM, wird ein Teil auf die CPU ausgelagert (Hybrid). "
             "<b>Modus cpu</b>: erzwingt reine CPU.</li>"
             "<li><b>Warmup</b>: nicht gewerteter Vorlauf, der das Modell laedt "
             "(Kaltstart ist viel langsamer).</li>"
             "<li><b>Wiederholungen</b>: mehrere Messungen -> stabiler Median + p95.</li>"
             "<li>Nach dem Lauf wird die <b>tatsaechliche GPU/CPU-Verteilung</b> angezeigt.</li>"
             "</ul>"]
        p.append(f"<h2>Aufgaben ({len(self.tasks)})</h2>")
        if not self.tasks:
            p.append("<p><i>Keine Aufgaben geladen (tasks.json fehlt?).</i></p>")
        for t in self.tasks:
            if "check_keys" in t:
                qc = "JSON-Schluessel: " + ", ".join(t["check_keys"])
            elif "expect_contains" in t:
                qc = f'Antwort muss enthalten: "{t["expect_contains"]}"'
            else:
                qc = "keine (reine Tempo-Messung)"
            p.append(f"<h3>{esc(t.get('id'))}</h3>")
            p.append(f"<p><i>{esc(t.get('beschreibung', ''))}</i></p>")
            p.append(f"<p>Kontext: {t.get('num_ctx', 4096)} Tokens &middot; "
                     f"max. Ausgabe: {t.get('num_predict', 256)} Tokens &middot; "
                     f"Qualitaetspruefung: {esc(qc)}</p>")
            p.append("<p><b>Prompt:</b></p>"
                     "<pre style='white-space:pre-wrap; background:#f4f4f4; "
                     f"padding:8px; border-radius:6px;'>{esc(t.get('prompt', ''))}</pre>")
        return "".join(p)

    # ---- Sauberes Beenden ----
    def closeEvent(self, event):
        # Laufenden Worker kooperativ stoppen (BenchWorker: Flag + offene Antwort
        # schliessen). ScanWorker hat kein request_cancel -> wird durch den kurzen
        # Netzwerk-Timeout (6 s) ohnehin begrenzt.
        if self._worker is not None and hasattr(self._worker, "request_cancel"):
            self._worker.request_cancel()
        th = self._thread
        if th is not None:
            th.quit()
            if not th.wait(7000):
                # Worker haengt in blockierendem Read -> harter Abbruch als letzte
                # Reserve, danach joinen. Verhindert den Qt-Abort
                # "QThread: Destroyed while thread is still running".
                th.terminate()
                th.wait(2000)
        event.accept()


def main():
    if "--selftest" in sys.argv:
        # Bundle-/Build-Check (auch fuer das gefrorene Binary): tasks.json ueber
        # resource_path laden und beenden, ohne die GUI zu starten.
        with open(resource_path("tasks.json"), encoding="utf-8") as f:
            n = len(json.load(f).get("tasks", []))
        print(f"selftest OK: tasks.json gefunden, {n} Aufgaben, "
              f"frozen={getattr(sys, 'frozen', False)}")
        return
    app = QApplication(sys.argv)
    app.setApplicationName("LLM-Benchmark")
    _icon = QIcon(resource_path(os.path.join("assets", "icon.png")))
    if not _icon.isNull():
        app.setWindowIcon(_icon)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
