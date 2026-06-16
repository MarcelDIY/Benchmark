#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Erzeugt das App-Icon (icon.png 256x256 + icon.ico): ein Tacho/Speedometer.

Lauf: python assets/make_icon.py
Motiv: Tachometer (Benchmark = Tempo messen) – farbiger Skalenbogen mit Nadel
auf dunkelblauem Rundquadrat.
"""
import math
import os
import sys

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QGuiApplication, QImage, QLinearGradient,
                           QPainter, QPen, QPolygonF)

HERE = os.path.dirname(os.path.abspath(__file__))


def _needle(p, cx, cy, angle_deg, length, width, color):
    a = math.radians(angle_deg)
    tip = QPointF(cx + length * math.cos(a), cy - length * math.sin(a))
    # zwei Basispunkte senkrecht zur Nadel, plus kurzer Schwanz
    perp = math.radians(angle_deg + 90)
    bx, by = (width / 2) * math.cos(perp), (width / 2) * math.sin(perp)
    tail = QPointF(cx - length * 0.18 * math.cos(a), cy + length * 0.18 * math.sin(a))
    poly = QPolygonF([QPointF(cx + bx, cy - by), tip, QPointF(cx - bx, cy + by), tail])
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))
    p.drawPolygon(poly)


def draw(size=256):
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    s = size / 256.0

    # Hintergrund: Rundquadrat mit Verlauf (Navy -> Teal)
    grad = QLinearGradient(0, 0, size, size)
    grad.setColorAt(0.0, QColor("#243b6b"))
    grad.setColorAt(1.0, QColor("#16a394"))
    p.setBrush(QBrush(grad))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(QRectF(8 * s, 8 * s, 240 * s, 240 * s), 48 * s, 48 * s)

    cx, cy = 128 * s, 150 * s
    r = 78 * s
    rect = QRectF(cx - r, cy - r, 2 * r, 2 * r)
    thick = 20 * s
    # Skalenbogen in vier Segmenten (240 Grad, unten offen): gruen -> rot
    # Qt: 0 Grad = 3 Uhr, gegen den Uhrzeigersinn, Einheit 1/16 Grad.
    segs = [(-30, 60, "#ff5a5f"), (30, 60, "#ffb44d"),
            (90, 60, "#2bb0a0"), (150, 60, "#3ddc84")]
    for start, span, col in segs:
        p.setPen(QPen(QColor(col), thick, Qt.SolidLine, Qt.FlatCap))
        p.drawArc(rect, int(start * 16), int(span * 16))

    # Tick-Marken
    p.setPen(QPen(QColor(255, 255, 255, 200), 2.5 * s, Qt.SolidLine, Qt.RoundCap))
    for k in range(9):
        ang = math.radians(210 - k * 30)
        r1, r2 = r - thick - 4 * s, r - thick - 13 * s
        p.drawLine(QPointF(cx + r1 * math.cos(ang), cy - r1 * math.sin(ang)),
                   QPointF(cx + r2 * math.cos(ang), cy - r2 * math.sin(ang)))

    # Nadel (zeigt nach oben-rechts = schnell) + Nabe
    _needle(p, cx, cy, 38, r - 6 * s, 14 * s, "#f5f9ff")
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#ffd166"))
    p.drawEllipse(QPointF(cx, cy), 12 * s, 12 * s)
    p.setBrush(QColor("#243b6b"))
    p.drawEllipse(QPointF(cx, cy), 5 * s, 5 * s)

    p.end()
    return img


def caret(up=False, color="#8089b3", size=16):
    """Kleiner Chevron-Pfeil (für QComboBox/QSpinBox im Stylesheet)."""
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    pen = QPen(QColor(color), 2.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    s = size / 16.0
    if up:
        pts = [QPointF(4.5 * s, 10 * s), QPointF(8 * s, 6.2 * s), QPointF(11.5 * s, 10 * s)]
    else:
        pts = [QPointF(4.5 * s, 6.2 * s), QPointF(8 * s, 10 * s), QPointF(11.5 * s, 6.2 * s)]
    p.drawPolyline(QPolygonF(pts))
    p.end()
    return img


def main():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    QGuiApplication(sys.argv)
    img = draw(256)
    png = os.path.join(HERE, "icon.png")
    ico = os.path.join(HERE, "icon.ico")
    img.save(png, "PNG")
    img.save(ico, "ICO")
    cd = os.path.join(HERE, "caret-down.png")
    cu = os.path.join(HERE, "caret-up.png")
    caret(up=False).save(cd, "PNG")
    caret(up=True).save(cu, "PNG")
    print(f"geschrieben: {png} ({os.path.getsize(png)} B), {ico} ({os.path.getsize(ico)} B), "
          f"{cd}, {cu}")


if __name__ == "__main__":
    main()
