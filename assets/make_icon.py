#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Erzeugt das App-Icon (icon.png 256x256 + icon.ico) mit QPainter.

Lauf: python assets/make_icon.py
Motiv: aufsteigendes Balkendiagramm (Benchmark/Performance) auf dunkelblauem
Rundquadrat, der hoechste Balken in Amber als "Spitzenwert".
"""
import os
import sys

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QGuiApplication, QImage, QLinearGradient,
                           QPainter)

HERE = os.path.dirname(os.path.abspath(__file__))


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

    # Balken (aufsteigend), abgerundet
    base_y = 196 * s
    widths = 30 * s
    xs = [54, 96, 138, 180]
    heights = [62, 96, 130, 168]
    colors = ["#eaf2ff", "#eaf2ff", "#eaf2ff", "#ffd166"]
    for x, h, c in zip(xs, heights, colors):
        p.setBrush(QColor(c))
        rect = QRectF(x * s, base_y - h * s, widths, h * s)
        p.drawRoundedRect(rect, 7 * s, 7 * s)

    p.end()
    return img


def main():
    # QGuiApplication fuer den ICO-/PNG-Imageformat-Support (offscreen).
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    QGuiApplication(sys.argv)
    img = draw(256)
    png = os.path.join(HERE, "icon.png")
    ico = os.path.join(HERE, "icon.ico")
    img.save(png, "PNG")
    img.save(ico, "ICO")
    print(f"geschrieben: {png} ({os.path.getsize(png)} B), {ico} ({os.path.getsize(ico)} B)")


if __name__ == "__main__":
    main()
