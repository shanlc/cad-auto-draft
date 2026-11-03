"""cad_auto_draft: deterministic draft engine for plumbing + fire systems."""
from .layout import build_layout
from .models import Building

__all__ = ["Building", "build_layout"]
__version__ = "0.1.0"
