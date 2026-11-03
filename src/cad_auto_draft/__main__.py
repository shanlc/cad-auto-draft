"""Entry point for `python -m cad_auto_draft` and for PyInstaller.

No arguments (or --gui) opens the graphical interface, so
double-clicking the exe does not end in a command-line error.
"""
import sys

if __name__ == "__main__":
    if not sys.argv[1:] or "--gui" in sys.argv[1:]:
        from .gui import launch_gui
        launch_gui()
    else:
        from .cli import main
        raise SystemExit(main())
