# PyInstaller spec for the Windows exe (also works on Linux/macOS for testing).
# Build locally on Windows with:
#   pip install pyinstaller
#   pyinstaller cad-auto-draft.spec
# Or let GitHub Actions do it: .github/workflows/build-exe.yml
# The exe is a windowed GUI program when double-clicked (no arguments);
# with arguments it still works as a console program. It does NOT need
# AutoCAD installed to generate a DXF draft, but AutoCAD / Tianzheng
# is still needed to open, review and finalise the drawing.
# Note: tkinter is imported lazily in main.py, so list it explicitly
# here or PyInstaller may miss it in the frozen exe.
block_cipher = None

a = Analysis(
    ["main.py"],
    pathex=["src"],
    binaries=[],
    datas=[],
    hiddenimports=["cad_auto_draft", "cad_auto_draft.gui", "tkinter",
                   "tkinter.ttk", "tkinter.filedialog", "tkinter.messagebox"],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name="cad-auto-draft",
    debug=False,
    strip=False,
    upx=True,
    console=True,
)
