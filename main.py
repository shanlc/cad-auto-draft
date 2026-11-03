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

from cad_auto_draft.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
