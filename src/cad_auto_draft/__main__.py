"""Entry point for `python -m cad_auto_draft` and for PyInstaller."""
from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
