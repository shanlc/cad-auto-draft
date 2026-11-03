"""DXF output (ezdxf). AutoCAD and Tianzheng can open DXF directly.

Layer convention (draft only, rename to the project / Tianzheng
standard before formal use):
    ARCH 建筑底图  WS 给水  DR 排水  RW 雨水
    FH 消火栓  SP 喷淋  FE 灭火器  ANNO 标注说明
Chinese text uses the default DXF text style; in AutoCAD set the font
to a Chinese font (e.g. SimSun) if glyphs do not display.
"""
from __future__ import annotations

import ezdxf

from .layout import Layout
from .models import Building

LAYERS = {
    "ARCH": 9, "WS": 5, "DR": 3, "RW": 4, "FH": 1, "SP": 6, "FE": 2, "ANNO": 7,
}
NAMES = {
    "ARCH": "建筑底图", "WS": "给水", "DR": "排水", "RW": "雨水",
    "FH": "消火栓", "SP": "喷淋", "FE": "灭火器", "ANNO": "标注",
}


def write_dxf(b: Building, layout: Layout, path: str) -> str:
    doc = ezdxf.new("R2010", setup=True)
    msp = doc.modelspace()
    for layer, color in LAYERS.items():
        doc.layers.add(layer, color=color)

    # Building outline, rooms, obstacles.
    msp.add_lwpolyline([(0, 0), (b.width, 0), (b.width, b.depth), (0, b.depth)],
                       close=True, dxfattribs={"layer": "ARCH"})
    for room in b.rooms:
        msp.add_lwpolyline(
            [(room.x, room.y), (room.x_max, room.y), (room.x_max, room.y_max),
             (room.x, room.y_max)], close=True, dxfattribs={"layer": "ARCH"})
        if room.name:
            msp.add_text(room.name, dxfattribs={"layer": "ANNO", "height": 0.6}
                         ).set_placement((room.x + 0.5, room.y + room.d - 1.0))
    for ob in b.obstacles:
        msp.add_lwpolyline(
            [(ob.x, ob.y), (ob.x_max, ob.y), (ob.x_max, ob.y_max),
             (ob.x, ob.y_max)], close=True, dxfattribs={"layer": "ARCH"})

    # Fixtures.
    for fx in b.fixtures:
        msp.add_circle((fx.x, fx.y), 0.3, dxfattribs={"layer": "ARCH"})
        msp.add_text(fx.id, dxfattribs={"layer": "ANNO", "height": 0.4}
                     ).set_placement((fx.x + 0.4, fx.y + 0.4))

    # Pipes.
    for pipe in layout.pipes:
        msp.add_lwpolyline([p.as_tuple() for p in pipe.points],
                           dxfattribs={"layer": pipe.system})
        mid = pipe.points[len(pipe.points) // 2]
        msp.add_text(pipe.label, dxfattribs={"layer": "ANNO", "height": 0.4}
                     ).set_placement((mid.x + 0.3, mid.y + 0.3))

    # Devices.
    for dev in layout.devices:
        layer = dev.system
        if dev.system == "SP":
            msp.add_circle((dev.x, dev.y), 0.25, dxfattribs={"layer": layer})
            msp.add_line((dev.x - 0.4, dev.y), (dev.x + 0.4, dev.y),
                         dxfattribs={"layer": layer})
            msp.add_line((dev.x, dev.y - 0.4), (dev.x, dev.y + 0.4),
                         dxfattribs={"layer": layer})
        elif dev.system == "FH":
            msp.add_lwpolyline(
                [(dev.x - 0.5, dev.y - 0.5), (dev.x + 0.5, dev.y - 0.5),
                 (dev.x + 0.5, dev.y + 0.5), (dev.x - 0.5, dev.y + 0.5)],
                close=True, dxfattribs={"layer": layer})
        elif dev.system == "FE":
            msp.add_lwpolyline([(dev.x, dev.y + 0.6), (dev.x - 0.5, dev.y - 0.4),
                                (dev.x + 0.5, dev.y - 0.4)], close=True,
                               dxfattribs={"layer": layer})
        else:  # RW downspout
            msp.add_circle((dev.x, dev.y), 0.4, dxfattribs={"layer": layer})
        msp.add_text(dev.label, dxfattribs={"layer": "ANNO", "height": 0.4}
                     ).set_placement((dev.x + 0.6, dev.y + 0.2))

    # Title, legend, disclaimer.
    y = b.depth + 2.0
    msp.add_text(f"{b.name} AI 粗稿（给排水 / 雨水 / 消防）",
                 dxfattribs={"layer": "ANNO", "height": 1.0}
                 ).set_placement((0, y))
    msp.add_text("AI 粗稿，仅供工程师复核修改，非正式施工图，不得直接用于施工。",
                 dxfattribs={"layer": "ANNO", "height": 0.6}
                 ).set_placement((0, y - 1.2))
    lx = b.width + 3.0
    msp.add_text("图例", dxfattribs={"layer": "ANNO", "height": 0.8}
                 ).set_placement((lx, b.depth))
    for i, (code, name) in enumerate(NAMES.items()):
        msp.add_text(f"{code} {name}", dxfattribs={"layer": "ANNO", "height": 0.5}
                     ).set_placement((lx, b.depth - 1.5 - i))
    doc.saveas(path)
    return path
