# -*- mode: python ; coding: utf-8 -*-
# PyInstaller-Spec fuer die Benchmark-GUI (onedir, windowed).
#
# Bauen (auf JEDEM Ziel-OS SEPARAT -- PyInstaller cross-kompiliert NICHT):
#   pyinstaller --noconfirm BenchGUI.spec
#
# Ergebnis:
#   Windows : dist\BenchGUI\BenchGUI.exe
#   Linux   : dist/BenchGUI/BenchGUI
#   macOS   : dist/BenchGUI.app  (+ dist/BenchGUI/ )
#
# tasks.json wird mitgebuendelt und zur Laufzeit ueber resource_path()/_MEIPASS
# gelesen. bench.py kommt als importiertes Modul automatisch mit (NICHT als data).

block_cipher = None

a = Analysis(
    ['benchmark_gui.py'],
    pathex=[],
    binaries=[],
    datas=[('tasks.json', '.'), ('assets/icon.png', 'assets'), ('LICENSE', '.')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Ungenutzte, grosse Qt-Module ausschliessen -> kleineres Bundle.
        'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets',
        'PySide6.QtQuick', 'PySide6.QtQml', 'PySide6.QtMultimedia',
        'PySide6.Qt3DCore', 'PySide6.QtPdf', 'PySide6.QtCharts',
        'PySide6.QtDataVisualization', 'PySide6.QtNetworkAuth',
    ],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='BenchGUI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,            # windowed; zum Debuggen voruebergehend True setzen
    disable_windowed_traceback=False,
    target_arch=None,         # macOS-Universal: 'universal2' (braucht universal2-Wheels)
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico',   # Windows-/EXE-Icon (auf Linux ignoriert)
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='BenchGUI',
)
app = BUNDLE(
    coll,
    name='BenchGUI.app',      # nur auf macOS wirksam
    icon=None,
    bundle_identifier='com.marcel.benchgui',
)
