"""Architectural base-plan recognition (DXF only, v0.1).

Why DXF, not DWG, in this module:
    DWG is a proprietary binary format. ezdxf cannot read it, and this
    project does not ship a DWG reader. Convert first, in AutoCAD /
    Tianzheng with DXFOUT, or with the free ODA File Converter
    (DWG -> DXF), then run this parser. See docs/plan_recognition.md.

What the parser does, deterministically (no AI coordinates):
    1. Walks modelspace and expands BLOCK references recursively,
       applying insertion point, scale and rotation, up to depth 10,
       with cycle detection. Nested blocks are therefore recognised,
       not just top-level geometry.
    2. External references (xrefs): an INSERT whose block has no
       geometry in the host file is treated as an xref. If the caller
       supplies that xref as a DXF file (xref_files mapping, or a file
       next to the host file with the same name), it is loaded and
       expanded in place. Otherwise it is recorded in
       ``missing_xrefs`` and NEVER silently ignored -- a missing base
       plan must be visible in the report.
    3. Classifies what it found:
       - closed polylines  -> rooms (name = nearest TEXT inside it)
       - block names / layers containing fixture keywords
         (Chinese + English) -> fixtures, at the INSERT point
       - block / layer names for shaft / stair / lift / column
         -> obstacles (bounding box of the expanded block)
       - TEXT containing 出口 / 疏散 -> exits
    4. Normalises coordinates: the bounding-box minimum becomes
       (0, 0), and units are converted (mm -> m by default, because
       most Chinese institute drawings are in mm; use units="m" for
       metre drawings, or units="auto").

Limitations (read before formal use):
    - Walls are NOT reconstructed as double lines here; the engine
      only needs the floor outline, rooms, fixtures and obstacles.
      Wall thickness / door swings are not inferred.
    - A block whose name does not contain a known keyword is expanded
      for geometry but not classified as a fixture. Add your institute's
      block naming to FIXTURE_KEYWORDS / OBSTACLE_KEYWORDS.
    - Text recognition is by DXF TEXT/MTEXT only, not OCR on a scanned
      image. For a PDF / image base plan, convert / vectorise first.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

FIXTURE_KEYWORDS: dict[str, str] = {
    # Chinese
    "马桶": "toilet", "坐便": "toilet", "蹲便": "toilet",
    "洗脸盆": "washbasin", "洗手盆": "washbasin", "面盆": "washbasin",
    "淋浴": "shower", "花洒": "shower",
    "洗菜盆": "kitchen_sink", "水槽": "kitchen_sink", "洗涤盆": "kitchen_sink",
    "洗衣机": "washing_machine", "地漏": "floor_drain",
    # English
    "toilet": "toilet", "wc": "toilet", "basin": "washbasin",
    "shower": "shower", "sink": "kitchen_sink",
    "washing": "washing_machine", "floor_drain": "floor_drain",
}

OBSTACLE_KEYWORDS = ("管井", "楼梯", "电梯", "柱", "shaft", "stair", "lift", "column")
EXIT_KEYWORDS = ("出口", "疏散", "exit", "escape")


@dataclass
class Transform:
    x: float = 0.0
    y: float = 0.0
    rotation_deg: float = 0.0
    sx: float = 1.0
    sy: float = 1.0

    def apply(self, px: float, py: float) -> tuple[float, float]:
        rad = math.radians(self.rotation_deg)
        cos_r, sin_r = math.cos(rad), math.sin(rad)
        qx, qy = px * self.sx, py * self.sy
        return (self.x + qx * cos_r - qy * sin_r,
                self.y + qx * sin_r + qy * cos_r)

    def compose(self, inner: "Transform") -> "Transform":
        ox, oy = self.apply(inner.x, inner.y)
        return Transform(ox, oy, self.rotation_deg + inner.rotation_deg,
                         self.sx * inner.sx, self.sy * inner.sy)


@dataclass
class _Collector:
    polylines: list[dict] = field(default_factory=list)  # {points, closed, layer}
    texts: list[dict] = field(default_factory=list)      # {text, x, y, layer}
    fixtures: list[dict] = field(default_factory=list)
    obstacles: list[dict] = field(default_factory=list)
    exits: list[dict] = field(default_factory=list)
    missing_xrefs: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    block_counts: dict[str, int] = field(default_factory=dict)


def _fixture_kind(name: str, layer: str) -> str | None:
    hay = f"{name} {layer}".lower()
    for keyword, kind in FIXTURE_KEYWORDS.items():
        if keyword.lower() in hay:
            return kind
    return None


def _is_obstacle(name: str, layer: str) -> bool:
    hay = f"{name} {layer}".lower()
    return any(k.lower() in hay for k in OBSTACLE_KEYWORDS)


class PlanParser:
    def __init__(self, xref_files: dict[str, str] | None = None):
        self.xref_files = xref_files or {}
        self._xref_docs: dict[str, Any] = {}

    # -- entity walking -------------------------------------------------
    def _walk_layout(self, doc: Any, layout: Any, transform: Transform,
                     collector: _Collector, stack: tuple[str, ...],
                     scale: float) -> None:
        try:
            entities = list(layout)
        except Exception:
            return
        for ent in entities:
            try:
                self._walk_entity(doc, ent, transform, collector, stack, scale)
            except Exception as exc:  # one bad entity must not kill the plan
                collector.warnings.append(f"跳过异常图元 {ent.dxftype()}: {exc}")

    def _walk_entity(self, doc: Any, ent: Any, transform: Transform,
                     collector: _Collector, stack: tuple[str, ...],
                     scale: float) -> None:
        etype = ent.dxftype()
        layer = str(ent.dxf.layer) if hasattr(ent.dxf, "layer") else ""
        if etype == "LINE":
            a = transform.apply(ent.dxf.start.x, ent.dxf.start.y)
            b = transform.apply(ent.dxf.end.x, ent.dxf.end.y)
            collector.polylines.append({"points": [a, b], "closed": False,
                                        "layer": layer})
        elif etype in ("LWPOLYLINE", "POLYLINE"):
            # ezdxf quirk: LWPolyline.points() is an edit context
            # manager, not an iterable; get_points() is the read API.
            # POLYLINE.points() does return Vec3 points.
            if etype == "LWPOLYLINE":
                raw_pts = [(float(p[0]), float(p[1]))
                           for p in ent.get_points()]
            else:
                raw_pts = [(float(v.x), float(v.y)) for v in ent.points()]
            pts = [transform.apply(x, y) for x, y in raw_pts]
            closed = bool(getattr(ent, "closed", False))
            collector.polylines.append({"points": pts, "closed": closed,
                                        "layer": layer})
        elif etype == "CIRCLE":
            c = transform.apply(ent.dxf.center.x, ent.dxf.center.y)
            # Circles are kept as a 4-point closed polyline approximation
            # so room / obstacle bounding boxes can use them.
            r = float(ent.dxf.radius) * abs(transform.sx)
            collector.polylines.append({
                "points": [(c[0] - r, c[1]), (c[0] + r, c[1]),
                           (c[0] + r, c[1] + 2 * r), (c[0] - r, c[1] + 2 * r)],
                "closed": True, "layer": layer})
        elif etype in ("TEXT", "MTEXT"):
            text = ent.dxf.text if etype == "TEXT" else ent.text
            ins = ent.dxf.insert
            x, y = transform.apply(ins.x, ins.y)
            collector.texts.append({"text": str(text), "x": x, "y": y,
                                    "layer": layer})
            if any(k in str(text) for k in EXIT_KEYWORDS):
                collector.exits.append({"x": round(x, 2), "y": round(y, 2)})
        elif etype == "INSERT":
            name = str(ent.dxf.name)
            ins = ent.dxf.insert
            inner = Transform(ins.x, ins.y, float(getattr(ent.dxf, "rotation", 0.0)),
                              float(getattr(ent.dxf, "xscale", 1.0)),
                              float(getattr(ent.dxf, "yscale", 1.0)))
            combined = transform.compose(inner)
            ix, iy = combined.x, combined.y
            collector.block_counts[name] = collector.block_counts.get(name, 0) + 1
            kind = _fixture_kind(name, layer)
            if kind:
                collector.fixtures.append(
                    {"id": f"{name}-{collector.block_counts[name]}",
                     "kind": kind, "x": round(ix, 2), "y": round(iy, 2)})
            # Obstacle bounding box is filled after expansion, below.
            before = len(collector.polylines)
            block = None
            try:
                block = doc.blocks.get(name)
            except Exception:
                block = None
            if block is None or len(list(block)) == 0:
                # No geometry in host file -> external reference (or a
                # broken block). Try to load it, otherwise record it.
                loaded = self._load_xref(doc, name)
                if loaded is not None:
                    self._walk_layout(loaded, loaded.modelspace(), combined,
                                      collector, stack + (name,), scale)
                else:
                    if name not in collector.missing_xrefs:
                        collector.missing_xrefs.append(name)
                    collector.warnings.append(
                        f"外部参照 / 空块未展开：{name}，须提供其 DXF 文件")
                return
            if name in stack:
                collector.warnings.append(f"块循环引用，已截断：{' > '.join(stack + (name,))}")
                return
            if len(stack) >= 10:
                collector.warnings.append(f"块嵌套超过 10 层，已截断：{name}")
                return
            self._walk_layout(doc, block, combined, collector,
                              stack + (name,), scale)
            if _is_obstacle(name, layer):
                new = collector.polylines[before:]
                if new:
                    xs = [p[0] for pl in new for p in pl["points"]]
                    ys = [p[1] for pl in new for p in pl["points"]]
                    collector.obstacles.append({
                        "x": round(min(xs), 2), "y": round(min(ys), 2),
                        "w": round(max(xs) - min(xs), 2),
                        "d": round(max(ys) - min(ys), 2), "name": name})
        # Other types (DIMENSION, HATCH, etc.) are ignored for v0.1.

    def _load_xref(self, host_doc: Any, name: str) -> Any | None:
        import ezdxf
        candidates: list[Path] = []
        if name in self.xref_files:
            candidates.append(Path(self.xref_files[name]))
        # Same-name DXF next to the host file is a common institute layout.
        for suffix in (".dxf", ".DXF"):
            candidates.append(Path(name + suffix))
            candidates.append(Path(Path(name).name + suffix))
        for path in candidates:
            if path.is_file():
                try:
                    return ezdxf.readfile(str(path))
                except Exception:
                    continue
        return None

    # -- public API -----------------------------------------------------
    def parse(self, path: str, units: str = "mm") -> dict[str, Any]:
        import ezdxf
        src = Path(path)
        if src.suffix.lower() == ".dwg":
            raise ValueError(
                "不支持直接读取 DWG：请先在 AutoCAD / 天正中用 DXFOUT，"
                "或用 ODA File Converter 把 DWG 转成 DXF，再用本程序解析。")
        if src.suffix.lower() != ".dxf":
            raise ValueError(f"只支持 DXF 文件，当前文件：{src.suffix}")
        doc = ezdxf.readfile(str(src))
        collector = _Collector()
        # First pass in raw units to decide auto scaling, then rescale.
        self._walk_layout(doc, doc.modelspace(), Transform(), collector, (), 1.0)
        all_x = [p[0] for pl in collector.polylines for p in pl["points"]]
        all_x += [f["x"] for f in collector.fixtures]
        all_y = [p[1] for pl in collector.polylines for p in pl["points"]]
        all_y += [f["y"] for f in collector.fixtures]
        if not all_x or not all_y:
            raise ValueError("底图中没有可识别的几何图形（直线 / 多段线 / 块）")
        raw_w, raw_d = max(all_x) - min(all_x), max(all_y) - min(all_y)
        if units == "mm":
            scale = 0.001
        elif units == "m":
            scale = 1.0
        elif units == "auto":
            scale = 0.001 if max(raw_w, raw_d) > 500 else 1.0
        else:
            raise ValueError(f"未知单位：{units}，可用 mm / m / auto")
        ox, oy = min(all_x), min(all_y)

        def norm(x: float, y: float) -> tuple[float, float]:
            return (round((x - ox) * scale, 2), round((y - oy) * scale, 2))

        rooms: list[dict] = []
        obstacle_boxes = [(o["x"], o["y"], o["w"], o["d"])
                          for o in collector.obstacles]
        for pl in collector.polylines:
            if not pl["closed"] or len(pl["points"]) < 3:
                continue
            raw_xs = [p[0] for p in pl["points"]]
            raw_ys = [p[1] for p in pl["points"]]
            # A closed outline that is exactly an obstacle (shaft, etc.)
            # is not a room.
            if any(abs(min(raw_xs) - ox) < 0.01 and abs(min(raw_ys) - oy) < 0.01
                   and abs((max(raw_xs) - min(raw_xs)) - ow) < 0.01
                   and abs((max(raw_ys) - min(raw_ys)) - od) < 0.01
                   for ox, oy, ow, od in obstacle_boxes):
                continue
            pts = [norm(*p) for p in pl["points"]]
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            w, d = max(xs) - min(xs), max(ys) - min(ys)
            area = w * d
            if w < 1.0 or d < 1.0 or area < 2.0:
                continue
            # Room name: first TEXT whose point lies inside the rectangle.
            name = ""
            for t in collector.texts:
                tx, ty = norm(t["x"], t["y"])
                if min(xs) <= tx <= max(xs) and min(ys) <= ty <= max(ys):
                    name = str(t["text"]).strip()
                    break
            rooms.append({"x": min(xs), "y": min(ys), "w": round(w, 2),
                          "d": round(d, 2), "name": name})
        # De-duplicate identical rooms (same outline drawn twice).
        seen: set[tuple] = set()
        unique_rooms: list[dict] = []
        for r in rooms:
            key = (r["x"], r["y"], r["w"], r["d"])
            if key not in seen:
                seen.add(key)
                unique_rooms.append(r)

        fixtures: list[dict] = []
        for f in collector.fixtures:
            x, y = norm(f["x"], f["y"])
            if any(abs(x - g["x"]) < 0.3 and abs(y - g["y"]) < 0.3
                   for g in fixtures):
                continue
            room = ""
            for r in unique_rooms:
                if r["x"] <= x <= r["x"] + r["w"] and r["y"] <= y <= r["y"] + r["d"]:
                    room = r["name"]
                    break
            fixtures.append({"id": f["id"], "kind": f["kind"], "x": x, "y": y,
                             "room": room})
        obstacles: list[dict] = []
        for o in collector.obstacles:
            x, y = norm(o["x"], o["y"])
            obstacles.append({"x": x, "y": y,
                              "w": round(o["w"] * scale, 2),
                              "d": round(o["d"] * scale, 2), "name": o["name"]})
        exits = [{"x": x, "y": y} for x, y in
                 (norm(e["x"], e["y"]) for e in collector.exits)]
        if not unique_rooms:
            collector.warnings.append("未识别到房间：底图可能全是块 / 参照，或房间不是闭合多段线")
        if not fixtures:
            collector.warnings.append("未识别到洁具：请检查块名是否含马桶 / 洗脸盆等关键词，或在 docs/plan_recognition.md 里补充块名映射")
        return {
            "name": src.stem,
            "width": round(raw_w * scale, 2),
            "depth": round(raw_d * scale, 2),
            "units": units,
            "scale": scale,
            "origin_offset_raw": [round(ox, 2), round(oy, 2)],
            "rooms": unique_rooms,
            "fixtures": fixtures,
            "obstacles": obstacles,
            "exits": exits,
            "missing_xrefs": collector.missing_xrefs,
            "warnings": collector.warnings,
            "block_counts": collector.block_counts,
            "counts": {
                "polylines": len(collector.polylines),
                "texts": len(collector.texts),
                "rooms": len(unique_rooms),
                "fixtures": len(fixtures),
                "obstacles": len(obstacles),
            },
        }


def parse_plan(path: str, units: str = "mm",
               xref_files: dict[str, str] | None = None) -> dict[str, Any]:
    return PlanParser(xref_files=xref_files).parse(path, units=units)
