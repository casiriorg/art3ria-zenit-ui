# -*- mode: python ; coding: utf-8 -*-
# Config de build para empaquetar la app como .exe con PyInstaller.
# Ver docs/specs-exe-installer.md para el detalle de cada decision.
#
# Uso: pyinstaller art3ria.spec --clean

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("config.example.json", "."),
        ("assets/models", "assets/models"),
        ("assets/audio/test_tone.wav", "assets/audio"),
    ],
    hiddenimports=[
        "OpenGL.platform.win32",
        "OpenGL.arrays.numpymodule",
        "scipy.io.wavfile",
    ],
    hookspath=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="art3ria",
    console=False,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="art3ria",
)
