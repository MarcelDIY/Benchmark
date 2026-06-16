#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SVG-Diagramme im Tokyo-Night-Stil für die Benchmark-GUI.

Reine String-Erzeugung (keine Abhängigkeiten). Die SVGs werden in der GUI per
QSvgRenderer als gestochen scharfes Bild gerendert – derselbe Look wie die
README-Grafiken im "zweiten Gehirn" (assets/charts.py).

Jede Funktion bekommt die Zielgröße (w, h) und liefert einen SVG-String mit
transparentem Hintergrund (die Karte kommt aus der GUI).
"""
import math

# --- Tokyo-Night-Palette ---
BG = "#16161e"
SURFACE2 = "#1f2335"
BORDER = "#2a2e42"
TRACK = "#222637"
BLUE = "#7aa2f7"
PURPLE = "#bb9af7"
CYAN = "#7dcfff"
GREEN = "#9ece6a"
ORANGE = "#e0af68"
RED = "#f7768e"
TEAL = "#73daca"
TEXT = "#c0caf5"
MUTED = "#565f89"
FAINT = "#414868"

GPU_C = TEAL
CPU_C = ORANGE

FONT = "ui-sans-serif,-apple-system,'Segoe UI',Roboto,system-ui,sans-serif"
MONO = "ui-monospace,'DejaVu Sans Mono','JetBrains Mono',monospace"

# Akzentfarben-Zyklus für Vergleichs-Balken
CYCLE = [BLUE, TEAL, PURPLE, GREEN, ORANGE, CYAN, RED]


def _defs():
    return f'''<defs>
    <linearGradient id="gTeal"  x1="0" y1="1" x2="0" y2="0"><stop offset="0" stop-color="{TEAL}"/><stop offset="1" stop-color="{CYAN}"/></linearGradient>
    <linearGradient id="gWarm"  x1="0" y1="1" x2="0" y2="0"><stop offset="0" stop-color="{RED}"/><stop offset="1" stop-color="{ORANGE}"/></linearGradient>
    <linearGradient id="gBlue"  x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{BLUE}"/><stop offset="1" stop-color="{CYAN}"/></linearGradient>
    <linearGradient id="gPurple" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{PURPLE}"/><stop offset="1" stop-color="{BLUE}"/></linearGradient>
    <filter id="soft" x="-40%" y="-40%" width="180%" height="180%"><feGaussianBlur stdDeviation="5"/></filter>
  </defs>'''


def _head(w, h):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
            f'width="{w}" height="{h}" font-family="{FONT}">{_defs()}')


def _arc(cx, cy, r, a0, a1):
    x0, y0 = cx + r * math.cos(a0), cy + r * math.sin(a0)
    x1, y1 = cx + r * math.cos(a1), cy + r * math.sin(a1)
    large = 1 if (a1 - a0) % (2 * math.pi) > math.pi else 0
    return f"M {x0:.2f} {y0:.2f} A {r:.2f} {r:.2f} 0 {large} 1 {x1:.2f} {y1:.2f}"


def _txt(x, y, s, fill, size, weight="400", anchor="start", mono=False, ls=None):
    fam = f' font-family="{MONO}"' if mono else ""
    lss = f' letter-spacing="{ls}"' if ls else ""
    return (f'<text x="{x:.1f}" y="{y:.1f}" fill="{fill}" font-size="{size}" '
            f'font-weight="{weight}" text-anchor="{anchor}"{fam}{lss}>{s}</text>')


# --------------------------------------------------------------- Donut --------
def donut(gpu_pct, vram_mb, total_mb, w, h):
    """Ring: das Modell (100%) verteilt auf GPU (teal) + CPU (amber), mit Legende."""
    s = [_head(w, h)]
    if gpu_pct is None:
        cx, cy = h / 2 + 6, h / 2
        r = min(h, w) / 2 - 16
        s.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="none" '
                 f'stroke="{TRACK}" stroke-width="{r*0.30:.1f}"/>')
        s.append(_txt(cx, cy + 4, "kein Lauf", MUTED, 12, anchor="middle"))
        s.append("</svg>")
        return "\n".join(s)

    gpu = max(0, min(100, gpu_pct))
    cpu = 100 - gpu
    r = min(h - 18, w * 0.42) / 2
    cx, cy = r + 14, h / 2
    sw = r * 0.34
    a0 = -math.pi / 2
    parts = [(gpu, GPU_C), (cpu, CPU_C)]
    # Segmente (mit kleiner Lücke + Glow)
    ang = a0
    for val, col in parts:
        if val <= 0:
            continue
        sweep = 2 * math.pi * val / 100
        gap = 0.05 if (0 < gpu < 100) else 0.0
        a1 = ang + sweep - gap
        d = _arc(cx, cy, r, ang, a1)
        s.append(f'<path d="{d}" fill="none" stroke="{col}" stroke-width="{sw+6:.1f}" '
                 f'stroke-linecap="round" opacity="0.22" filter="url(#soft)"/>')
        s.append(f'<path d="{d}" fill="none" stroke="{col}" stroke-width="{sw:.1f}" '
                 f'stroke-linecap="round"/>')
        ang += sweep
    # Zentrum: 100 % = Modell
    s.append(_txt(cx, cy - 2, "100%", TEXT, r * 0.5, "800", anchor="middle", mono=True))
    s.append(_txt(cx, cy + r * 0.34, "Modell", MUTED, max(9, r * 0.18), anchor="middle"))

    # Legende rechts
    lx = cx + r + 22
    avail = w - lx - 12
    rows = [("GPU", gpu, GPU_C, f"{vram_mb} MB im VRAM" if vram_mb is not None else "auf der GPU"),
            ("CPU", cpu, CPU_C, "ausgelagert" if cpu > 0 else "—")]
    ly = cy - 24
    for name, val, col, desc in rows:
        s.append(f'<rect x="{lx}" y="{ly-11}" width="14" height="14" rx="4" fill="{col}"/>')
        s.append(_txt(lx + 22, ly, name, TEXT, 14.5, "700", mono=True))
        s.append(_txt(lx + avail, ly, f"{val}%", col, 16, "800", anchor="end", mono=True))
        s.append(_txt(lx + 22, ly + 17, desc, MUTED, 11))
        ly += 44
    s.append("</svg>")
    return "\n".join(s)


# ----------------------------------------------------------- Lauf-Balken ------
def runs(bars, avg, dec, caption, w, h):
    """Vertikale Balken: ein Balken pro Lauf (+ Warmup amber). Durchschnittslinie."""
    s = [_head(w, h)]
    if caption:
        s.append(_txt(12, 17, caption, MUTED, 12.5))
    if not bars:
        s.append(_txt(w / 2, h / 2, "Aufgabe in der Tabelle wählen", MUTED, 12, anchor="middle"))
        s.append("</svg>")
        return "\n".join(s)

    left, right, top, bottom = 14, 14, 34, 30
    pw, ph = w - left - right, h - top - bottom
    base = top + ph
    vals = [v for _, v, _ in bars if v is not None]
    vmax = (max(vals + ([avg] if avg else []), default=1) or 1) * 1.28
    n = len(bars)
    gap = 10
    bw = max(7, (pw - gap * (n - 1)) / n)

    def fmt(v):
        return f"{v:.{dec}f}"

    # Spuren
    for i in range(n):
        bx = left + i * (bw + gap)
        s.append(f'<rect x="{bx:.1f}" y="{top}" width="{bw:.1f}" height="{ph}" rx="6" fill="{TRACK}"/>')
    # Durchschnittslinie
    if avg:
        ay = base - (avg / vmax) * ph
        s.append(f'<line x1="{left}" y1="{ay:.1f}" x2="{left+pw}" y2="{ay:.1f}" '
                 f'stroke="{MUTED}" stroke-width="1.2" stroke-dasharray="5 4"/>')
        s.append(_txt(left + 2, ay - 5, f"Ø {fmt(avg)}", TEXT, 11, "700", mono=True))
    # Balken
    for i, (lbl, val, warm) in enumerate(bars):
        if val is None:
            continue
        bx = left + i * (bw + gap)
        bh = max(3, (val / vmax) * ph)
        by = base - bh
        grad = "url(#gWarm)" if warm else "url(#gTeal)"
        col = ORANGE if warm else TEAL
        s.append(f'<rect x="{bx-1.5:.1f}" y="{by-1.5:.1f}" width="{bw+3:.1f}" height="{bh+1.5:.1f}" '
                 f'rx="7" fill="{col}" opacity="0.22" filter="url(#soft)"/>')
        s.append(f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bw:.1f}" height="{bh:.1f}" rx="6" fill="{grad}"/>')
        ly = max(top - 2, by - 6)
        s.append(_txt(bx + bw / 2, ly, fmt(val), TEXT, 11, "700", anchor="middle", mono=True))
        s.append(_txt(bx + bw / 2, base + 16, lbl, ORANGE if warm else MUTED,
                      10.5, "700" if warm else "400", anchor="middle"))
    s.append("</svg>")
    return "\n".join(s)


# ------------------------------------------------------ Vergleichs-Balken -----
def compare(items, dec, unit, caption, w, h):
    """Horizontale Balken: ein Balken je Lauf (Modell@Modus) für eine Kennzahl."""
    s = [_head(w, h)]
    s.append(_txt(14, 22, caption, TEXT, 15, "700"))
    if not items:
        s.append(_txt(w / 2, h / 2 + 10, "Noch keine Läufe – starte einen Test.",
                      MUTED, 12, anchor="middle"))
        s.append("</svg>")
        return "\n".join(s)

    top = 44
    row_h = min(46, (h - top - 12) / len(items))
    bar_h = min(22, row_h - 16)
    label_w = min(190, w * 0.32)
    val_w = 78
    bx0 = label_w + 14
    bar_max = w - bx0 - val_w - 12
    vmax = max((v for _, v, _ in items), default=1) or 1

    def fmt(v):
        return f"{v:.{dec}f}"

    for i, (label, val, col) in enumerate(items):
        cy = top + i * row_h
        bw = max(4, bar_max * (val / vmax))
        s.append(_txt(14, cy + bar_h - 5, label, TEXT, 13, "600"))
        s.append(f'<rect x="{bx0}" y="{cy}" width="{bar_max:.1f}" height="{bar_h}" rx="6" fill="{TRACK}"/>')
        s.append(f'<rect x="{bx0}" y="{cy}" width="{bw:.1f}" height="{bar_h}" rx="6" fill="{col}" '
                 f'opacity="0.25" filter="url(#soft)"/>')
        s.append(f'<rect x="{bx0}" y="{cy}" width="{bw:.1f}" height="{bar_h}" rx="6" fill="{col}"/>')
        s.append(_txt(w - 12, cy + bar_h - 5, fmt(val), col, 14, "800", anchor="end", mono=True))
    s.append(_txt(14, h - 6, unit, FAINT, 11))
    s.append("</svg>")
    return "\n".join(s)
