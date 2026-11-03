"""PyInstaller / standalone entry point.

PyInstaller builds a single file from this script; it adds src/ to the
path so the package imports work both in the frozen exe and when run
as `python main.py` from the repository root.
"""
import sys
from pathlib import Path

# Same UTF-8 stdout fix as cli.main(), applied as early as possible
# so even import-time output cannot fail on a cp1252 Windows console.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))


def should_launch_gui(argv: list[str]) -> bool:
    """Double-clicking the exe (no arguments) opens the GUI instead of
    printing a command-line error and exiting, which is what users saw
    before. --gui does the same explicitly."""
    return not argv or "--gui" in argv


if __name__ == "__main__":
    if should_launch_gui(sys.argv[1:]):
        from cad_auto_draft.gui import launch_gui
        launch_gui()
    else:
        from cad_auto_draft.cli import main
        raise SystemExit(main())
