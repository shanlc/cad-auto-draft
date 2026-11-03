"""Bind a DXF host + its xrefs into one flattened DXF.

"Binding" here means what AutoCAD's -XREF Bind does in effect:
the externally referenced geometry becomes a permanent part of the
host file, so the result can be opened on its own, with no xref
files alongside it. This implementation does it in Python with
ezdxf, by expanding INSERTs recursively (host blocks, nested
blocks, and xref documents supplied in xref_files), applying
insertion point / scale / rotation, and writing the expanded
geometry to modelspace.

It is NOT a full AutoCAD: only the entity types the base-plan
parser cares about are expanded (LINE, LWPOLYLINE, POLYLINE,
CIRCLE, ARC, TEXT, MTEXT). DIMENSION, HATCH, SPLINE, 3D solids
and Tianzheng custom objects are skipped and counted, and the
count is returned so the caller can warn the user. If the user
needs a byte-perfect bind (including Tianzheng objects), the
AutoCAD route in dwg_convert.py (_convert_with_autocad) is the
right one; this binder is for the common case where the base
plan is ordinary lines / polylines / blocks.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from .plan_parser import Transform


def _copy_attribs(ent: Any) -> dict:
    attribs: dict = {}
    for key in ("layer", "color", "linetype"):
        try:
            value = getattr(ent.dxf, key, None)
        except Exception:
            value = None
        if value not in (None, "", 256):
            attribs[key] = value
    return attribs


def _walk(doc: Any, layout: Any, transform: Transform, out: Any,
          xref_docs: dict[str, Any], stack: tuple[str, ...],
          stats: dict) -> None:
    try:
        entities = list(layout)
    except Exception:
        return
    for ent in entities:
        try:
            _walk_entity(doc, ent, transform, out, xref_docs, stack, stats)
        except Exception:
            stats["skipped"] += 1


def _walk_entity(doc: Any, ent: Any, transform: Transform, out: Any,
                 xref_docs: dict[str, Any], stack: tuple[str, ...],
                 stats: dict) -> None:
    etype = ent.dxftype()
    attribs = _copy_attribs(ent)
    if etype == "LINE":
        a = transform.apply(ent.dxf.start.x, ent.dxf.start.y)
        b = transform.apply(ent.dxf.end.x, ent.dxf.end.y)
        out.add_line(a, b, dxfattribs=attribs)
        stats["written"] += 1
    elif etype in ("LWPOLYLINE", "POLYLINE"):
        if etype == "LWPOLYLINE":
            raw = [(float(p[0]), float(p[1])) for p in ent.get_points()]
        else:
            raw = [(float(v.x), float(v.y)) for v in ent.points()]
        pts = [transform.apply(x, y) for x, y in raw]
        out.add_lwpolyline(pts, close=bool(getattr(ent, "closed", False)),
                           dxfattribs=attribs)
        stats["written"] += 1
    elif etype == "CIRCLE":
        c = transform.apply(ent.dxf.center.x, ent.dxf.center.y)
        r = float(ent.dxf.radius) * abs(transform.sx)
        out.add_circle(c, r, dxfattribs=attribs)
        stats["written"] += 1
    elif etype == "ARC":
        c = transform.apply(ent.dxf.center.x, ent.dxf.center.y)
        r = float(ent.dxf.radius) * abs(transform.sx)
        start = float(ent.dxf.start_angle) + transform.rotation_deg
        end = float(ent.dxf.end_angle) + transform.rotation_deg
        out.add_arc(c, r, start, end, dxfattribs=attribs)
        stats["written"] += 1
    elif etype == "TEXT":
        ins = ent.dxf.insert
        x, y = transform.apply(ins.x, ins.y)
        height = float(ent.dxf.height) * abs(transform.sx)
        text_attribs = dict(attribs)
        text_attribs["height"] = height
        text_attribs["rotation"] = float(getattr(ent.dxf, "rotation", 0.0)) + transform.rotation_deg
        out.add_text(str(ent.dxf.text), dxfattribs=text_attribs).set_placement((x, y))
        stats["written"] += 1
    elif etype == "MTEXT":
        ins = ent.dxf.insert
        x, y = transform.apply(ins.x, ins.y)
        mtext = out.add_mtext(str(ent.text), dxfattribs=attribs)
        mtext.dxf.insert = (x, y)
        mtext.dxf.char_height = float(ent.dxf.char_height) * abs(transform.sx)
        stats["written"] += 1
    elif etype == "INSERT":
        name = str(ent.dxf.name)
        ins = ent.dxf.insert
        inner = Transform(ins.x, ins.y, float(getattr(ent.dxf, "rotation", 0.0)),
                          float(getattr(ent.dxf, "xscale", 1.0)),
                          float(getattr(ent.dxf, "yscale", 1.0)))
        combined = transform.compose(inner)
        if name in stack:
            stats["skipped"] += 1
            return
        if len(stack) >= 10:
            stats["skipped"] += 1
            return
        # Xref document first, then a block in the current document.
        if name in xref_docs:
            xref_doc = xref_docs[name]
            _walk(xref_doc, xref_doc.modelspace(), combined, out,
                  xref_docs, stack + (name,), stats)
            return
        block = None
        try:
            block = doc.blocks.get(name)
        except Exception:
            block = None
        if block is None or len(list(block)) == 0:
            stats["missing_xrefs"].append(name) if name not in stats["missing_xrefs"] else None
            stats["skipped"] += 1
            return
        _walk(doc, block, combined, out, xref_docs, stack + (name,), stats)
    else:
        stats["skipped"] += 1


def bind_dxf(host_dxf: str | Path, xref_files: dict[str, str] | None,
             out_dxf: str | Path) -> dict:
    """Write a flattened DXF with all xrefs expanded. Returns stats."""
    import ezdxf
    host = ezdxf.readfile(str(host_dxf))
    xref_docs: dict[str, Any] = {}
    for name, path in (xref_files or {}).items():
        try:
            xref_docs[name] = ezdxf.readfile(str(path))
        except Exception:
            continue
    out = ezdxf.new("R2010")
    # Copy layers so the bound file keeps its layer structure.
    for layer in host.layers:
        if layer.dxf.name not in ("0", "*Defpoints"):
            try:
                out.layers.add(layer.dxf.name, color=layer.dxf.color)
            except Exception:
                pass
    for doc in xref_docs.values():
        for layer in doc.layers:
            if layer.dxf.name not in ("0", "*Defpoints"):
                try:
                    out.layers.add(layer.dxf.name, color=layer.dxf.color)
                except Exception:
                    pass
    stats = {"written": 0, "skipped": 0, "missing_xrefs": []}
    _walk(host, host.modelspace(), Transform(), out.modelspace(),
          xref_docs, (), stats)
    out.saveas(str(out_dxf))
    return stats
