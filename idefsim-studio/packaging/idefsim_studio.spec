# -*- mode: python ; coding: utf-8 -*-
"""Empacotamento PyInstaller do IDEF-SIM Studio (Windows, macOS e Linux).

Uso (na pasta idefsim-studio):
    pip install -r requirements.txt pyinstaller pillow
    pyinstaller --noconfirm packaging/idefsim_studio.spec

Resultado em dist/:
    Windows: dist/IDEF-SIM Studio/IDEF-SIM Studio.exe
    macOS:   dist/IDEF-SIM Studio.app
    Linux:   dist/IDEF-SIM Studio/IDEF-SIM Studio
"""
import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent
APP = "IDEF-SIM Studio"
ICON = str(ROOT / "idefsim" / "resources" / "icon.png")  # convertido p/ .ico/.icns pelo Pillow

# Módulos Qt pesados que o programa não usa
QT_EXCLUDES = [f"PySide6.{m}" for m in (
    "QtWebEngineCore", "QtWebEngineWidgets", "QtWebEngineQuick", "QtWebChannel",
    "QtQml", "QtQuick", "QtQuickWidgets", "Qt3DCore", "Qt3DRender", "QtMultimedia",
    "QtMultimediaWidgets", "QtCharts", "QtDataVisualization", "QtGraphs", "QtPdf",
    "QtPdfWidgets", "QtBluetooth", "QtNfc", "QtPositioning", "QtLocation", "QtSensors",
    "QtSerialPort", "QtSql", "QtDesigner", "QtHelp", "QtOpenGL", "QtOpenGLWidgets",
    "QtRemoteObjects", "QtScxml", "QtSpatialAudio", "QtTextToSpeech", "QtWebSockets",
    "QtHttpServer", "QtNetworkAuth", "QtUiTools")]

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    datas=[(str(ROOT / "idefsim" / "resources"), "idefsim/resources"),
           (str(ROOT / "examples"), "examples")],
    hiddenimports=["PySide6.QtSvg"],
    excludes=QT_EXCLUDES + ["tkinter", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name=APP,
    console=False,
    icon=ICON,
    upx=False,
    argv_emulation=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name=APP, upx=False)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name=f"{APP}.app",
        icon=ICON,
        bundle_identifier="io.github.idefsim-studio",
        info_plist={
            "CFBundleShortVersionString": "0.1.0",
            "NSHighResolutionCapable": True,
            "CFBundleDocumentTypes": [{
                "CFBundleTypeName": "Modelo IDEF-SIM",
                "CFBundleTypeExtensions": ["idefsim"],
                "CFBundleTypeRole": "Editor",
            }],
        },
    )
