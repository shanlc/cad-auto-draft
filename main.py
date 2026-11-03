"""PyInstaller / standalone entry point.

PyInstaller builds a single file from this script; it adds src/ to the
path so the package imports work both in the frozen exe and when run
as `python main.py` from the repository root.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from cad_auto_draft.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
